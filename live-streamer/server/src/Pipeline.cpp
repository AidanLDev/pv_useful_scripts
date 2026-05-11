#include "Pipeline.hpp"
#include <gst/app/gstappsrc.h>
#include <stdexcept>
#include <sstream>
#include <cstdlib>
#include <cstring>

Pipeline::Pipeline(int width, int height, const std::string& bayerFormat, const std::string& outputDir)
{
    std::ostringstream desc;
    desc << "appsrc name=src is-live=true format=time "
         << "caps=video/x-bayer,format=" << bayerFormat
         << ",width=" << width << ",height=" << height << ",framerate=30/1 "
         << "! bayer2rgb ! videoconvert ! x264enc tune=zerolatency ! h264parse "
         << "! hlssink2 max-files=0 "
         << "location=" << outputDir << "/seg%05d.ts "
         << "playlist-location=" << outputDir << "/stream.m3u8";

    GError* err = nullptr;
    pipeline_ = gst_parse_launch(desc.str().c_str(), &err);
    if (err) {
        std::string msg = err->message;
        g_error_free(err);
        throw std::runtime_error("GStreamer pipeline error: " + msg);
    }

    appsrc_ = gst_bin_get_by_name(GST_BIN(pipeline_), "src");
    frameDur_ = gst_util_uint64_scale_int(GST_SECOND, 1, 30);
}

Pipeline::~Pipeline()
{
    if (pipeline_) {
        gst_element_set_state(pipeline_, GST_STATE_NULL);
        gst_object_unref(pipeline_);
    }
    if (appsrc_)
        gst_object_unref(appsrc_);
}

void Pipeline::start()
{
    gst_element_set_state(pipeline_, GST_STATE_PLAYING);
}

void Pipeline::stop()
{
    g_signal_emit_by_name(appsrc_, "end-of-stream", nullptr);
    gst_element_set_state(pipeline_, GST_STATE_NULL);
}

void Pipeline::pushFrame(const uint8_t* data, size_t size)
{
    GstBuffer* buf = gst_buffer_new_allocate(nullptr, size, nullptr);
    GstMapInfo map;
    gst_buffer_map(buf, &map, GST_MAP_WRITE);
    std::memcpy(map.data, data, size);
    gst_buffer_unmap(buf, &map);

    GST_BUFFER_PTS(buf) = pts_;
    GST_BUFFER_DURATION(buf) = frameDur_;
    pts_ += frameDur_;

    GstFlowReturn ret;
    g_signal_emit_by_name(appsrc_, "push-buffer", buf, &ret);
    gst_buffer_unref(buf);

    if (ret != GST_FLOW_OK)
        throw std::runtime_error("appsrc push-buffer failed: " + std::to_string(ret));
}
