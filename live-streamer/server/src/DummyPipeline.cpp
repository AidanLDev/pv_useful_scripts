#include "DummyPipeline.hpp"
#include <iostream>
#include <stdexcept>

DummyPipeline::DummyPipeline(const std::string& sourceFile, const std::string& outputDir)
{
    std::string src;
    if (sourceFile.empty()) {
        std::cout << "No file given — using videotestsrc (1280x720 @ 30fps)\n";
        src = "videotestsrc is-live=true"
              " ! video/x-raw,width=1280,height=720,framerate=30/1";
    } else {
        std::cout << "Using file: " << sourceFile << "\n";
        src = "filesrc location=" + sourceFile + " ! decodebin";
    }

    std::string desc = src +
        " ! videoconvert ! x264enc tune=zerolatency ! h264parse"
        " ! hlssink2 max-files=0"
        " location=" + outputDir + "/seg%05d.ts"
        " playlist-location=" + outputDir + "/stream.m3u8";

    GError* err = nullptr;
    pipeline_ = gst_parse_launch(desc.c_str(), &err);
    if (err) {
        std::string msg = err->message;
        g_error_free(err);
        throw std::runtime_error("DummyPipeline: " + msg);
    }
}

DummyPipeline::~DummyPipeline()
{
    if (pipeline_) {
        gst_element_set_state(pipeline_, GST_STATE_NULL);
        gst_object_unref(pipeline_);
    }
}

void DummyPipeline::run(const std::atomic<bool>& running)
{
    gst_element_set_state(pipeline_, GST_STATE_PLAYING);

    GstBus* bus = gst_element_get_bus(pipeline_);
    while (running) {
        GstMessage* msg = gst_bus_timed_pop_filtered(bus, 100 * GST_MSECOND,
            static_cast<GstMessageType>(GST_MESSAGE_ERROR | GST_MESSAGE_EOS));
        if (!msg) continue;
        GstMessageType type = GST_MESSAGE_TYPE(msg);
        if (type == GST_MESSAGE_EOS)    { gst_message_unref(msg); std::cout << "End of stream\n"; break; }
        if (type == GST_MESSAGE_ERROR)  {
            GError* err = nullptr; gchar* dbg = nullptr;
            gst_message_parse_error(msg, &err, &dbg);
            std::cerr << "Pipeline error: " << (err ? err->message : "unknown")
                      << "\nDebug: " << (dbg ? dbg : "none") << "\n";
            g_clear_error(&err); g_free(dbg);
            gst_message_unref(msg);
            break;
        }
        gst_message_unref(msg);
    }

    gst_object_unref(bus);
    gst_element_set_state(pipeline_, GST_STATE_NULL);
}
