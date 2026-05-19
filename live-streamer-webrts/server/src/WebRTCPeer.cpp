#include "WebRTCPeer.hpp"
#include <gst/sdp/sdp.h>
#include <nlohmann/json.hpp>
#include <iostream>

using json = nlohmann::json;

// Marshal a send onto the GLib main loop (safe to call from GStreamer threads).
// Stores a copy of the SendFn so it needs no access to WebRTCPeer internals.
struct IdleMsg { WebRTCPeer::SendFn fn; std::string msg; };
static gboolean idleSend(gpointer data) {
    auto* d = static_cast<IdleMsg*>(data);
    d->fn(d->msg);
    delete d;
    return G_SOURCE_REMOVE;
}

WebRTCPeer::WebRTCPeer(const std::string& sourceFile, SendFn send)
    : send_(std::move(send))
{
    pipeline_  = gst_pipeline_new(nullptr);
    webrtcbin_ = gst_element_factory_make("webrtcbin", "webrtcbin");
    g_object_set(webrtcbin_,
        "stun-server", "stun://stun.l.google.com:19302",
        "bundle-policy", 3,   // max-bundle
        nullptr);

    GstElement* conv  = gst_element_factory_make("videoconvert", nullptr);
    GstElement* enc   = gst_element_factory_make("x264enc",      nullptr);
    GstElement* pay   = gst_element_factory_make("rtph264pay",   nullptr);
    g_object_set(enc, "tune", 4 /*zerolatency*/, "speed-preset", 1 /*ultrafast*/,
                      "key-int-max", 30, nullptr);
    g_object_set(pay, "config-interval", -1, "pt", 96, nullptr);

    GstCaps* rtpCaps = gst_caps_from_string(
        "application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000");
    GstElement* capsf = gst_element_factory_make("capsfilter", nullptr);
    g_object_set(capsf, "caps", rtpCaps, nullptr);
    gst_caps_unref(rtpCaps);

    if (sourceFile.empty()) {
        GstElement* src = gst_element_factory_make("videotestsrc", nullptr);
        g_object_set(src, "is-live", TRUE, nullptr);
        gst_bin_add_many(GST_BIN(pipeline_), src, conv, enc, pay, capsf, webrtcbin_, nullptr);
        gst_element_link_many(src, conv, enc, pay, capsf, nullptr);
    } else {
        GstElement* src = gst_element_factory_make("filesrc",   nullptr);
        GstElement* dec = gst_element_factory_make("decodebin", nullptr);
        g_object_set(src, "location", sourceFile.c_str(), nullptr);
        gst_bin_add_many(GST_BIN(pipeline_), src, dec, conv, enc, pay, capsf, webrtcbin_, nullptr);
        gst_element_link(src, dec);
        // conv is captured as user data; dec links to it once its video pad appears
        g_signal_connect(dec, "pad-added", G_CALLBACK(onDecPadAdded), conv);
        gst_element_link_many(conv, enc, pay, capsf, nullptr);
    }

    // Link capsfilter → webrtcbin (request pad)
    GstPad* capsSrc    = gst_element_get_static_pad(capsf, "src");
    GstPad* webrtcSink = gst_element_request_pad_simple(webrtcbin_, "sink_%u");
    gst_pad_link(capsSrc, webrtcSink);
    gst_object_unref(capsSrc);
    gst_object_unref(webrtcSink);

    g_signal_connect(webrtcbin_, "on-negotiation-needed", G_CALLBACK(onNegotiationNeeded), this);
    g_signal_connect(webrtcbin_, "on-ice-candidate",      G_CALLBACK(onIceCandidate),      this);

    gst_element_set_state(pipeline_, GST_STATE_PLAYING);
}

WebRTCPeer::~WebRTCPeer() {
    if (pipeline_) {
        gst_element_set_state(pipeline_, GST_STATE_NULL);
        gst_object_unref(pipeline_);
    }
}

void WebRTCPeer::handleAnswer(const std::string& sdp) {
    GstSDPMessage* msg = nullptr;
    gst_sdp_message_new(&msg);
    gst_sdp_message_parse_buffer(
        reinterpret_cast<const guint8*>(sdp.c_str()), sdp.size(), msg);

    GstWebRTCSessionDescription* answer =
        gst_webrtc_session_description_new(GST_WEBRTC_SDP_TYPE_ANSWER, msg);

    GstPromise* p = gst_promise_new();
    g_signal_emit_by_name(webrtcbin_, "set-remote-description", answer, p);
    gst_promise_interrupt(p);
    gst_promise_unref(p);
    gst_webrtc_session_description_free(answer);
}

void WebRTCPeer::handleIceCandidate(guint mlineIndex, const std::string& candidate) {
    g_signal_emit_by_name(webrtcbin_, "add-ice-candidate", mlineIndex, candidate.c_str());
}

void WebRTCPeer::onDecPadAdded(GstElement*, GstPad* pad, gpointer data) {
    auto* conv = static_cast<GstElement*>(data);
    GstCaps* caps = gst_pad_get_current_caps(pad);
    if (!caps) caps = gst_pad_query_caps(pad, nullptr);
    const gchar* name = gst_structure_get_name(gst_caps_get_structure(caps, 0));
    gst_caps_unref(caps);
    if (!g_str_has_prefix(name, "video/")) return;
    GstPad* sink = gst_element_get_static_pad(conv, "sink");
    if (!gst_pad_is_linked(sink))
        gst_pad_link(pad, sink);
    gst_object_unref(sink);
}

void WebRTCPeer::onNegotiationNeeded(GstElement*, gpointer data) {
    auto* self = static_cast<WebRTCPeer*>(data);
    GstPromise* p = gst_promise_new_with_change_func(onOfferCreated, self, nullptr);
    g_signal_emit_by_name(self->webrtcbin_, "create-offer", nullptr, p);
}

void WebRTCPeer::onOfferCreated(GstPromise* promise, gpointer data) {
    auto* self = static_cast<WebRTCPeer*>(data);
    const GstStructure* reply = gst_promise_get_reply(promise);
    GstWebRTCSessionDescription* offer = nullptr;
    gst_structure_get(reply, "offer",
        GST_TYPE_WEBRTC_SESSION_DESCRIPTION, &offer, nullptr);
    gst_promise_unref(promise);

    GstPromise* local = gst_promise_new();
    g_signal_emit_by_name(self->webrtcbin_, "set-local-description", offer, local);
    gst_promise_interrupt(local);
    gst_promise_unref(local);

    gchar* sdpStr = gst_sdp_message_as_text(offer->sdp);
    std::string payload = json{{"type", "offer"}, {"sdp", sdpStr}}.dump();
    g_free(sdpStr);
    g_idle_add(idleSend, new IdleMsg{self->send_, std::move(payload)});
    gst_webrtc_session_description_free(offer);
}

void WebRTCPeer::onIceCandidate(GstElement*, guint mlineIndex,
                                gchararray candidate, gpointer data) {
    auto* self = static_cast<WebRTCPeer*>(data);
    std::string payload = json{{"type", "ice"}, {"mlineIndex", mlineIndex}, {"candidate", candidate}}.dump();
    g_idle_add(idleSend, new IdleMsg{self->send_, std::move(payload)});
}
