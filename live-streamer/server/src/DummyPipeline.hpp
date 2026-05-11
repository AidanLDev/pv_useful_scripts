#pragma once
#include <string>
#include <atomic>
#include <gst/gst.h>

class DummyPipeline {
public:
    // sourceFile: path to a video file, or empty to use a test pattern
    DummyPipeline(const std::string& sourceFile, const std::string& outputDir);
    ~DummyPipeline();

    DummyPipeline(const DummyPipeline&) = delete;
    DummyPipeline& operator=(const DummyPipeline&) = delete;

    void run(const std::atomic<bool>& running);

private:
    GstElement* pipeline_ = nullptr;
};
