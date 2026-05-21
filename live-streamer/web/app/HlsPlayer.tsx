"use client";

import { useEffect, useRef } from "react";
import Hls from "hls.js";

interface HlsPlayerProps {
  src: string;
  isLive?: boolean;
  /** Called with the wall-clock time as the video plays (VoD mode only) */
  onTimeUpdate?: (wallClock: Date) => void;
  /** Wall-clock start time of the VoD playlist's first segment */
  vodStartTime?: Date;
}

export default function HlsPlayer({
  src,
  isLive = true,
  onTimeUpdate,
  vodStartTime,
}: HlsPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  // Keep a stable ref to callbacks so the effect doesn't re-run when they change
  const onTimeUpdateRef = useRef(onTimeUpdate);
  onTimeUpdateRef.current = onTimeUpdate;
  const vodStartTimeRef = useRef(vodStartTime);
  vodStartTimeRef.current = vodStartTime;

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const hlsConfig = isLive ? { liveSyncDurationCount: 3 } : {};

    let hls: Hls | null = null;

    if (Hls.isSupported()) {
      hls = new Hls(hlsConfig);
      hls.loadSource(src);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        if (isLive) video.play();
      });
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = src;
      if (isLive) video.play();
    }

    const handleTimeUpdate = () => {
      if (!isLive && onTimeUpdateRef.current && vodStartTimeRef.current) {
        const wallClock = new Date(
          vodStartTimeRef.current.getTime() + video.currentTime * 1000,
        );
        onTimeUpdateRef.current(wallClock);
      }
    };

    video.addEventListener("timeupdate", handleTimeUpdate);

    return () => {
      video.removeEventListener("timeupdate", handleTimeUpdate);
      hls?.destroy();
    };
  }, [src, isLive]);

  return (
    <video
      ref={videoRef}
      controls
      muted
      className="absolute inset-0 w-full h-full object-contain bg-black"
    />
  );
}
