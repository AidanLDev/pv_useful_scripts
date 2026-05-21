#pragma once
#include "SegmentDatabase.hpp"
#include <gst/app/gstappsink.h>
#include <string>
#include <deque>
#include <cstdio>

class SegmentSink {
public:
    SegmentSink(GstElement* appsink, const std::string& outputDir,
                SegmentDatabase& db, double segDuration = 4.0);
    ~SegmentSink();

    SegmentSink(const SegmentSink&) = delete;
    SegmentSink& operator=(const SegmentSink&) = delete;

    void flush();

private:
    static GstFlowReturn onSample(GstAppSink* sink, gpointer data);
    static void          onEos   (GstAppSink* sink, gpointer data);

    void handleSample(GstSample* sample);
    void openSegment (double wallNow);
    void closeSegment(double wallNow);
    void writePlaylist();

    GstElement*      appsink_;
    std::string      outputDir_;
    SegmentDatabase& db_;
    double           segDuration_;

    FILE*       file_     = nullptr;
    int         seqNum_   = 0;
    double      segStart_ = 0.0;
    std::string curName_;
    std::string curPath_;

    // Sliding window of (tsFilename, duration) for the live playlist
    static constexpr int PLAYLIST_WINDOW = 5;
    std::deque<std::pair<std::string, double>> playlist_;
};
