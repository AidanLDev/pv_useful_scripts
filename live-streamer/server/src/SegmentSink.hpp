#pragma once
#include "SegmentDatabase.hpp"
#include <gst/app/gstappsink.h>
#include <string>
#include <cstdio>

// Receives encoded H.264 NAL units from a GStreamer appsink, writes them as
// raw Annex B bitstream files (.h264), and records each completed segment to
// the database.  Requires h264parse config-interval=-1 upstream so that every
// IDR frame is preceded by in-band SPS/PPS — making each file self-decodable.
class SegmentSink {
public:
    // appsink  – the GstElement* for the appsink at the end of the pipeline
    // segDuration – target segment length in seconds; split happens on the
    //               next IDR frame at or after this threshold
    SegmentSink(GstElement* appsink, const std::string& outputDir,
                SegmentDatabase& db, double segDuration = 2.0);
    ~SegmentSink();

    SegmentSink(const SegmentSink&) = delete;
    SegmentSink& operator=(const SegmentSink&) = delete;

    // Close and record the in-progress segment.  Safe to call multiple times.
    void flush();

private:
    static GstFlowReturn onSample(GstAppSink* sink, gpointer data);
    static void          onEos   (GstAppSink* sink, gpointer data);

    void handleSample(GstSample* sample);
    void openSegment (double wallNow);
    void closeSegment(double wallNow);

    GstElement*      appsink_;
    std::string      outputDir_;
    SegmentDatabase& db_;
    double           segDuration_;

    FILE*       file_     = nullptr;
    int         seqNum_   = 0;
    double      segStart_ = 0.0;
    std::string curName_;
    std::string curPath_;
};
