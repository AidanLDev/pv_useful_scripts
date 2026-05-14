#include "SegmentWatcher.hpp"
#include <fstream>
#include <iostream>
#include <chrono>
#include <thread>
#include <ctime>
#include <cstdio>
#include <filesystem>

static std::string fmtTime(double unixTime)
{
    time_t t = static_cast<time_t>(unixTime);
    struct tm tm;
    gmtime_r(&t, &tm);
    char buf[24];
    std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &tm);
    return buf;
}

static double nowUnix()
{
    return std::chrono::duration<double>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

SegmentWatcher::SegmentWatcher(const std::string& outputDir, SegmentDatabase& db)
    : outputDir_(outputDir), db_(db)
{
    // Pre-seed seen_ only for files still on disk — guards against re-inserting
    // segments from an in-progress stream after a server restart, without
    // blocking new runs that reuse the same filenames (e.g. seg00000.ts).
    for (const auto& fname : db_.allFilenames()) {
        if (std::filesystem::exists(outputDir_ + "/" + fname))
            seen_.insert(fname);
    }
    thread_ = std::thread(&SegmentWatcher::run, this);
}

SegmentWatcher::~SegmentWatcher()
{
    running_ = false;
    if (thread_.joinable()) thread_.join();
}

void SegmentWatcher::run()
{
    while (running_) {
        processM3u8();
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }
}

void SegmentWatcher::processM3u8()
{
    std::ifstream f(outputDir_ + "/stream.m3u8");
    if (!f) return;

    int    baseSeq       = 0;
    int    seqOffset     = 0;
    double pendingDur    = -1.0;

    std::string line;
    while (std::getline(f, line)) {
        if (line.rfind("#EXT-X-MEDIA-SEQUENCE:", 0) == 0) {
            baseSeq = std::stoi(line.substr(22));
        } else if (line.rfind("#EXTINF:", 0) == 0) {
            pendingDur = std::stod(line.substr(8));  // stops at the trailing comma
        } else if (!line.empty() && line[0] != '#') {
            int seq = baseSeq + seqOffset++;

            if (!seen_.count(line)) {
                // First new segment this session anchors the wall-clock timeline.
                if (nextStartTime_ == 0.0)
                    nextStartTime_ = nowUnix() - pendingDur;

                SegmentRecord r;
                r.filename       = line;
                r.path           = outputDir_ + "/" + line;
                r.sequenceNumber = seq;
                r.startTime      = nextStartTime_;
                r.duration       = pendingDur;
                r.endTime        = nextStartTime_ + pendingDur;
                nextStartTime_   = r.endTime;

                db_.insert(r);
                seen_.insert(line);
                std::cout << "Segment registered: " << line
                          << "  [" << fmtTime(r.startTime) << " – " << fmtTime(r.endTime) << "]\n";
            }

            pendingDur = -1.0;
        }
    }
}
