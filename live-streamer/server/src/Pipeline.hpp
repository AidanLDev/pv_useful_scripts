#pragma once
#include <string>
#include <cstdint>
#include <memory>
#include <gst/gst.h>
#include "SegmentDatabase.hpp"
#include "SegmentSink.hpp"

class Pipeline {
public:
    Pipeline(int width, int height, const std::string& bayerFormat,
             const std::string& outputDir, SegmentDatabase& db);
    ~Pipeline();

    Pipeline(const Pipeline&) = delete;
    Pipeline& operator=(const Pipeline&) = delete;

    void start();
    void stop();
    void pushFrame(const uint8_t* data, size_t size);

private:
    GstElement*              pipeline_ = nullptr;
    GstElement*              appsrc_   = nullptr;
    GstElement*              appsink_  = nullptr;
    GstClockTime             pts_      = 0;
    GstClockTime             frameDur_ = 0;
    std::unique_ptr<SegmentSink> sink_;
};
