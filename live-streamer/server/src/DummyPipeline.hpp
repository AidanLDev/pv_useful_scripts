#pragma once
#include <string>
#include <atomic>
#include <memory>
#include <gst/gst.h>
#include "SegmentDatabase.hpp"
#include "SegmentSink.hpp"

class DummyPipeline {
public:
    // sourceFile: path to a video file, or empty to use a test pattern
    DummyPipeline(const std::string& sourceFile, const std::string& outputDir,
                  SegmentDatabase& db);
    ~DummyPipeline();

    DummyPipeline(const DummyPipeline&) = delete;
    DummyPipeline& operator=(const DummyPipeline&) = delete;

    void run(const std::atomic<bool>& running);

private:
    GstElement*              pipeline_ = nullptr;
    GstElement*              appsink_  = nullptr;
    std::unique_ptr<SegmentSink> sink_;
};
