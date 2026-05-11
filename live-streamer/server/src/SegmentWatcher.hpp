#pragma once
#include <string>
#include <set>
#include <thread>
#include <atomic>
#include "SegmentDatabase.hpp"

class SegmentWatcher {
public:
    SegmentWatcher(const std::string& outputDir, SegmentDatabase& db);
    ~SegmentWatcher();

private:
    void run();
    void processM3u8();

    std::string           outputDir_;
    SegmentDatabase&      db_;
    std::thread           thread_;
    std::atomic<bool>     running_{true};
    std::set<std::string> seen_;
    double                nextStartTime_{0.0};  // wall-clock anchor for new segments
};
