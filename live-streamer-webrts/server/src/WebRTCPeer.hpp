#pragma once
#include <gst/gst.h>
#include <gst/webrtc/webrtc.h>
#include <functional>
#include <string>

class WebRTCPeer {
public:
    using SendFn = std::function<void(const std::string&)>;

    WebRTCPeer(const std::string& sourceFile, SendFn send);
    ~WebRTCPeer();

    WebRTCPeer(const WebRTCPeer&) = delete;
    WebRTCPeer& operator=(const WebRTCPeer&) = delete;

    void handleAnswer(const std::string& sdp);
    void handleIceCandidate(guint mlineIndex, const std::string& candidate);

private:
    static void onNegotiationNeeded(GstElement*, gpointer);
    static void onIceCandidate(GstElement*, guint, gchararray, gpointer);
    static void onOfferCreated(GstPromise*, gpointer);
    static void onDecPadAdded(GstElement*, GstPad*, gpointer);

    GstElement* pipeline_  = nullptr;
    GstElement* webrtcbin_ = nullptr;
    SendFn      send_;
};
