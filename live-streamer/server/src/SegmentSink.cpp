#include "SegmentSink.hpp"
#include <chrono>
#include <stdexcept>
#include <iostream>
#include <gst/gst.h>

static double nowUnix()
{
    return std::chrono::duration<double>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

SegmentSink::SegmentSink(GstElement* appsink, const std::string& outputDir,
                         SegmentDatabase& db, double segDuration)
    : appsink_(appsink), outputDir_(outputDir), db_(db), segDuration_(segDuration)
{
    GstAppSinkCallbacks cbs{};
    cbs.new_sample = onSample;
    cbs.eos        = onEos;
    gst_app_sink_set_callbacks(GST_APP_SINK(appsink_), &cbs, this, nullptr);
    gst_app_sink_set_emit_signals(GST_APP_SINK(appsink_), FALSE);
    gst_app_sink_set_drop(GST_APP_SINK(appsink_), FALSE);
}

SegmentSink::~SegmentSink()
{
    flush();
}

void SegmentSink::flush()
{
    if (!file_) return;
    closeSegment(nowUnix());
}

GstFlowReturn SegmentSink::onSample(GstAppSink* sink, gpointer data)
{
    auto* self = static_cast<SegmentSink*>(data);
    GstSample* sample = gst_app_sink_pull_sample(sink);
    if (!sample) return GST_FLOW_OK;
    self->handleSample(sample);
    gst_sample_unref(sample);
    return GST_FLOW_OK;
}

void SegmentSink::onEos(GstAppSink* /*sink*/, gpointer data)
{
    static_cast<SegmentSink*>(data)->flush();
}

void SegmentSink::handleSample(GstSample* sample)
{
    GstBuffer* buf = gst_sample_get_buffer(sample);
    if (!buf) return;

    bool   isKeyframe = !GST_BUFFER_FLAG_IS_SET(buf, GST_BUFFER_FLAG_DELTA_UNIT);
    double wallNow    = nowUnix();

    if (!file_) {
        // Hold off until we see a clean IDR so the segment is self-decodable
        if (!isKeyframe) return;
        openSegment(wallNow);
    } else if (isKeyframe && (wallNow - segStart_ >= segDuration_)) {
        closeSegment(wallNow);
        openSegment(wallNow);
    }

    GstMapInfo map;
    if (!gst_buffer_map(buf, &map, GST_MAP_READ)) return;
    fwrite(map.data, 1, map.size, file_);
    gst_buffer_unmap(buf, &map);
}

void SegmentSink::openSegment(double wallNow)
{
    char name[32];
    std::snprintf(name, sizeof(name), "seg%05d.h264", seqNum_);
    curName_ = name;
    curPath_ = outputDir_ + "/" + name;

    file_ = std::fopen(curPath_.c_str(), "wb");
    if (!file_)
        throw std::runtime_error("Cannot open segment file: " + curPath_);

    segStart_ = wallNow;
    std::cout << "Segment opened: " << curName_ << "\n";
}

void SegmentSink::closeSegment(double wallNow)
{
    if (!file_) return;

    std::fflush(file_);
    std::fclose(file_);
    file_ = nullptr;

    SegmentRecord r;
    r.filename       = curName_;
    r.path           = curPath_;
    r.sequenceNumber = seqNum_++;
    r.startTime      = segStart_;
    r.endTime        = wallNow;
    r.duration       = wallNow - segStart_;
    db_.insert(r);

    std::cout << "Segment closed:  " << r.filename
              << "  (" << r.duration << "s)\n";
}
