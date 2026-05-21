"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import HlsPlayer from "./HlsPlayer";
import Timeline from "./Timeline";
import PlaybackControls from "./PlaybackControls";

interface CoverageRange {
  start: string;
  end: string;
}

interface RangesResponse {
  ranges: CoverageRange[];
  earliest: string | null;
  latest: string | null;
}

const SEGMENT_STEP_MS = 2_000;

export default function Home() {
  const [mode, setMode] = useState<"live" | "playback">("live");

  // Timeline data
  const [ranges, setRanges] = useState<CoverageRange[]>([]);
  const [earliest, setEarliest] = useState<Date | null>(null);
  const [latest, setLatest] = useState<Date | null>(null);

  // Playback state
  const [playbackStart, setPlaybackStart] = useState<Date | null>(null);
  const [currentTime, setCurrentTime] = useState<Date>(new Date());
  const [isPlaying, setIsPlaying] = useState(false);

  // Key to force HlsPlayer remount when VoD source changes
  const [vodKey, setVodKey] = useState(0);

  const fetchRanges = useCallback(async () => {
    try {
      const res = await fetch("/api/segments/ranges");
      if (!res.ok) return;
      const data: RangesResponse = await res.json();
      setRanges(data.ranges);
      if (data.earliest) setEarliest(new Date(data.earliest));
      if (data.latest) setLatest(new Date(data.latest));
    } catch {
      // silently ignore — no recordings yet
    }
  }, []);

  useEffect(() => {
    fetchRanges();
    const id = setInterval(fetchRanges, 30_000);
    return () => clearInterval(id);
  }, [fetchRanges]);

  // Advance live needle every second
  const liveNeedleRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (mode === "live") {
      setCurrentTime(new Date());
      liveNeedleRef.current = setInterval(
        () => setCurrentTime(new Date()),
        1000,
      );
    } else {
      if (liveNeedleRef.current) clearInterval(liveNeedleRef.current);
    }
    return () => {
      if (liveNeedleRef.current) clearInterval(liveNeedleRef.current);
    };
  }, [mode]);

  const handleSeek = useCallback((t: Date) => {
    setPlaybackStart(t);
    setCurrentTime(t);
    setMode("playback");
    setVodKey((k) => k + 1);
  }, []);

  const handleStep = useCallback(
    (direction: -1 | 1) => {
      const base = playbackStart ?? currentTime;
      const next = new Date(base.getTime() + direction * SEGMENT_STEP_MS);
      handleSeek(next);
    },
    [playbackStart, currentTime, handleSeek],
  );

  const handleSkipToStart = useCallback(() => {
    if (earliest) handleSeek(earliest);
  }, [earliest, handleSeek]);

  const handleSkipToEnd = useCallback(() => {
    if (latest) handleSeek(new Date(latest.getTime() - SEGMENT_STEP_MS));
  }, [latest, handleSeek]);

  const vodSrc =
    playbackStart != null
      ? `/api/hls/vod?from=${encodeURIComponent(playbackStart.toISOString())}`
      : null;

  const timelineEarliest = earliest ?? new Date(Date.now() - 3_600_000);
  const timelineLatest = latest ?? new Date();

  return (
    <div className="flex flex-col h-screen bg-gray-950 text-white">
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700">
        <span className="text-sm font-medium text-gray-200">Camera 1</span>
        <div className="flex gap-1">
          <button
            onClick={() => setMode("playback")}
            className={`px-4 py-1 text-sm rounded-l border transition-colors ${
              mode === "playback"
                ? "bg-blue-600 border-blue-500 text-white"
                : "bg-gray-800 border-gray-600 text-gray-300 hover:bg-gray-700"
            }`}
          >
            PLAYBACK
          </button>
          <button
            onClick={() => setMode("live")}
            className={`px-4 py-1 text-sm rounded-r border transition-colors ${
              mode === "live"
                ? "bg-green-600 border-green-500 text-white"
                : "bg-gray-800 border-gray-600 text-gray-300 hover:bg-gray-700"
            }`}
          >
            LIVE
          </button>
        </div>
      </div>

      {/* Video area */}
      <div className="flex-1 min-h-0 bg-black relative">
        {mode === "live" ? (
          <HlsPlayer src="/api/hls/stream.m3u8" isLive={true} />
        ) : vodSrc ? (
          <HlsPlayer
            key={vodKey}
            src={vodSrc}
            isLive={false}
            vodStartTime={playbackStart ?? undefined}
            onTimeUpdate={(t) => {
              setCurrentTime(t);
              setIsPlaying(true);
            }}
          />
        ) : (
          <div className="flex items-center justify-center h-64 text-gray-500 text-sm">
            Click on the timeline to start playback
          </div>
        )}
      </div>

      {/* Playback controls (only in playback mode) */}
      {mode === "playback" && (
        <PlaybackControls
          currentTime={currentTime}
          isPlaying={isPlaying}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onStep={handleStep}
          onSkipToStart={handleSkipToStart}
          onSkipToEnd={handleSkipToEnd}
        />
      )}

      {/* Timeline */}
      <div className="px-4 py-3 bg-gray-900 border-t border-gray-700">
        {ranges.length === 0 ? (
          <p className="text-xs text-gray-500 text-center py-2">
            No recordings available
          </p>
        ) : (
          <Timeline
            earliest={timelineEarliest}
            latest={timelineLatest}
            ranges={ranges}
            currentTime={currentTime}
            onSeek={handleSeek}
            label="Camera 1"
          />
        )}
      </div>
    </div>
  );
}
