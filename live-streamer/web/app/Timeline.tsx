"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface CoverageRange {
  start: string;
  end: string;
}

interface TimelineProps {
  earliest: Date;
  latest: Date;
  ranges: CoverageRange[];
  currentTime: Date;
  onSeek: (t: Date) => void;
  label?: string;
}

function formatAxisTime(d: Date): string {
  return d.toTimeString().slice(0, 5); // HH:MM
}

function formatFullTimestamp(d: Date): string {
  const pad = (n: number, len = 2) => String(n).padStart(len, "0");
  const day = pad(d.getDate());
  const month = pad(d.getMonth() + 1);
  const year = d.getFullYear();
  const h = pad(d.getHours());
  const m = pad(d.getMinutes());
  const s = pad(d.getSeconds());
  const ms = pad(d.getMilliseconds(), 3);
  return `${day}/${month}/${year} ${h}:${m}:${s}.${ms}`;
}

export default function Timeline({
  earliest,
  latest,
  ranges,
  currentTime,
  onSeek,
  label = "Camera 1",
}: TimelineProps) {
  const barRef = useRef<HTMLDivElement>(null);
  const [hoverTime, setHoverTime] = useState<Date | null>(null);
  const [hoverX, setHoverX] = useState(0);
  const [isDragging, setIsDragging] = useState(false);

  const totalMs = latest.getTime() - earliest.getTime();

  const timeToPercent = useCallback(
    (t: Date) => {
      if (totalMs <= 0) return 0;
      return Math.max(
        0,
        Math.min(100, ((t.getTime() - earliest.getTime()) / totalMs) * 100),
      );
    },
    [earliest, totalMs],
  );

  const xToTime = useCallback(
    (clientX: number): Date => {
      const rect = barRef.current!.getBoundingClientRect();
      const ratio = Math.max(
        0,
        Math.min(1, (clientX - rect.left) / rect.width),
      );
      return new Date(earliest.getTime() + ratio * totalMs);
    },
    [earliest, totalMs],
  );

  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      if (!barRef.current) return;
      onSeek(xToTime(e.clientX));
    },
    [xToTime, onSeek],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!barRef.current) return;
      const rect = barRef.current.getBoundingClientRect();
      setHoverX(e.clientX - rect.left);
      setHoverTime(xToTime(e.clientX));
      if (isDragging) onSeek(xToTime(e.clientX));
    },
    [xToTime, isDragging, onSeek],
  );

  // Stop dragging if mouse is released anywhere
  useEffect(() => {
    const up = () => setIsDragging(false);
    window.addEventListener("mouseup", up);
    return () => window.removeEventListener("mouseup", up);
  }, []);

  // Build axis tick labels (every ~1 hour or proportional)
  const axisTicks = () => {
    if (totalMs <= 0) return [];
    const hourMs = 3_600_000;
    const tickCount = Math.min(12, Math.max(2, Math.floor(totalMs / hourMs)));
    const tickInterval = totalMs / tickCount;
    const ticks: { pct: number; label: string }[] = [];
    for (let i = 0; i <= tickCount; i++) {
      const t = new Date(earliest.getTime() + i * tickInterval);
      ticks.push({ pct: (i / tickCount) * 100, label: formatAxisTime(t) });
    }
    return ticks;
  };

  const currentPct = timeToPercent(currentTime);

  return (
    <div className="select-none">
      {/* Axis labels */}
      <div className="relative h-5 text-xs text-gray-400 mb-0.5">
        {axisTicks().map((tick) => (
          <span
            key={tick.pct}
            className="absolute -translate-x-1/2"
            style={{ left: `${tick.pct}%` }}
          >
            {tick.label}
          </span>
        ))}
      </div>

      {/* Timeline bar */}
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs text-gray-400 w-16 shrink-0 truncate">
          {label}
        </span>
        <div
          ref={barRef}
          className="relative flex-1 h-4 rounded cursor-pointer"
          style={{ background: "#1a1a2e" }}
          onClick={handleClick}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoverTime(null)}
          onMouseDown={() => setIsDragging(true)}
        >
          {/* Coverage ranges */}
          {ranges.map((r, i) => {
            const left = timeToPercent(new Date(r.start));
            const right = timeToPercent(new Date(r.end));
            return (
              <div
                key={i}
                className="absolute top-0 h-full rounded-sm"
                style={{
                  left: `${left}%`,
                  width: `${right - left}%`,
                  background: "#e53935",
                }}
              />
            );
          })}

          {/* Current position needle */}
          <div
            className="absolute top-0 h-full w-0.5 z-10 pointer-events-none"
            style={{
              left: `${currentPct}%`,
              background: "#ffffff",
              boxShadow: "0 0 4px rgba(255,255,255,0.8)",
            }}
          />

          {/* Hover tooltip */}
          {hoverTime && (
            <div
              className="absolute -top-7 -translate-x-1/2 bg-gray-900 border border-gray-600 text-white text-xs px-2 py-0.5 rounded pointer-events-none whitespace-nowrap z-20"
              style={{ left: hoverX }}
            >
              {formatFullTimestamp(hoverTime)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export { formatFullTimestamp };
