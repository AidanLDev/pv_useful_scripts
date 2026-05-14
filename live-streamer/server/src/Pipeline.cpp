#include "Pipeline.hpp"
#include <gst/app/gstappsrc.h>
#include <stdexcept>
#include <sstream>
#include <cstdlib>
#include <cstring>

Pipeline::Pipeline(int width, int height, const std::string& bayerFormat,
                   const std::string& outputDir, SegmentDatabase& db)
{
    // key-int-max=60 forces an IDR every 2 s at 30 fps, aligning cleanly with
    // the 2-second segment boundary used by SegmentSink.
    // h264parse config-interval=-1 prepends in-band SPS/PPS before every IDR
    // so each .h264 file is self-decodable without the preceding segments.
    std::ostringstream desc;
    desc << "appsrc name=src is-live=true format=time "
         << "caps=video/x-bayer,format=" << bayerFormat
         << ",width=" << width << ",height=" << height << ",framerate=30/1 "
         << "! bayer2rgb ! videoconvert "
         << "! x264enc tune=zerolatency key-int-max=60 "
         << "! h264parse config-interval=-1 "
         << "! video/x-h264,stream-format=byte-stream,alignment=au "
         << "! appsink name=sink sync=false";

    GError* err = nullptr;
    pipeline_ = gst_parse_launch(desc.str().c_str(), &err);
    if (err) {
        std::string msg = err->message;
        g_error_free(err);
        throw std::runtime_error("GStreamer pipeline error: " + msg);
    }

    appsrc_  = gst_bin_get_by_name(GST_BIN(pipeline_), "src");
    appsink_ = gst_bin_get_by_name(GST_BIN(pipeline_), "sink");
    frameDur_ = gst_util_uint64_scale_int(GST_SECOND, 1, 30);

    sink_ = std::make_unique<SegmentSink>(appsink_, outputDir, db);
}

Pipeline::~Pipeline()
{
    if (pipeline_) {
        gst_element_set_state(pipeline_, GST_STATE_NULL);
        gst_object_unref(pipeline_);
    }
    // SegmentSink flush is triggered by EOS in stop(); destructor is the
    // safety net for abnormal teardown.
    if (sink_) sink_->flush();
    if (appsrc_)  gst_object_unref(appsrc_);
    if (appsink_) gst_object_unref(appsink_);
}

void Pipeline::start()
{
    gst_element_set_state(pipeline_, GST_STATE_PLAYING);
}

void Pipeline::stop()
{
    // Send EOS so the appsink receives it, triggering SegmentSink::onEos to
    // flush the in-progress segment before we tear the pipeline down.
    g_signal_emit_by_name(appsrc_, "end-of-stream", nullptr);

    GstBus* bus = gst_element_get_bus(pipeline_);
    gst_bus_timed_pop_filtered(bus, 5 * GST_SECOND,
        static_cast<GstMessageType>(GST_MESSAGE_EOS | GST_MESSAGE_ERROR));
    gst_object_unref(bus);

    gst_element_set_state(pipeline_, GST_STATE_NULL);
    if (sink_) sink_->flush();  // no-op if onEos already flushed
}

void Pipeline::pushFrame(const uint8_t* data, size_t size)
{
    GstBuffer* buf = gst_buffer_new_allocate(nullptr, size, nullptr);
    GstMapInfo map;
    gst_buffer_map(buf, &map, GST_MAP_WRITE);
    std::memcpy(map.data, data, size);
    gst_buffer_unmap(buf, &map);

    GST_BUFFER_PTS(buf)      = pts_;
    GST_BUFFER_DURATION(buf) = frameDur_;
    pts_ += frameDur_;

    GstFlowReturn ret;
    g_signal_emit_by_name(appsrc_, "push-buffer", buf, &ret);
    gst_buffer_unref(buf);

    if (ret != GST_FLOW_OK)
        throw std::runtime_error("appsrc push-buffer failed: " + std::to_string(ret));
}
