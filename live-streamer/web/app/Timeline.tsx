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

function formatAxisTime(d: Date, spanMs: number): string {
  if (spanMs < 5 * 60_000) return d.toTimeString().slice(0, 8); // HH:MM:SS
  return d.toTimeString().slice(0, 5); // HH:MM
}

function formatFullTimestamp(d: Date): string {
  const pad = (n: number, len = 2) => String(n).padStart(len, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
}

function smartTickInterval(spanMs: number): number {
  if (spanMs <= 2 * 60_000) return 15_000;       // 15s
  if (spanMs <= 10 * 60_000) return 60_000;       // 1min
  if (spanMs <= 30 * 60_000) return 5 * 60_000;   // 5min
  if (spanMs <= 2 * 3_600_000) return 30 * 60_000; // 30min
  return 3_600_000;                                // 1hr
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

  const [viewStart, setViewStart] = useState<Date>(earliest);
  const [viewEnd, setViewEnd] = useState<Date>(latest);

  // Drag tracking
  const dragStartX = useRef<number | null>(null);
  const dragViewStart = useRef(0);
  const dragViewSpan = useRef(0);
  const didPan = useRef(false);

  const totalMs = latest.getTime() - earliest.getTime();
  const viewMs = viewEnd.getTime() - viewStart.getTime();
  const isZoomed = viewMs < totalMs * 0.99;

  // Follow latest when not zoomed
  useEffect(() => {
    if (!isZoomed) {
      setViewStart(earliest);
      setViewEnd(latest);
    }
  }, [earliest, latest, isZoomed]);

  const timeToPercent = useCallback(
    (t: Date) => {
      if (viewMs <= 0) return 0;
      return Math.max(0, Math.min(100, ((t.getTime() - viewStart.getTime()) / viewMs) * 100));
    },
    [viewStart, viewMs],
  );

  const xToTime = useCallback(
    (clientX: number): Date => {
      const rect = barRef.current!.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      return new Date(viewStart.getTime() + ratio * viewMs);
    },
    [viewStart, viewMs],
  );

  // Scroll to zoom, centered on mouse
  const handleWheel = useCallback(
    (e: WheelEvent) => {
      e.preventDefault();
      if (!barRef.current) return;
      const rect = barRef.current.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const focusMs = viewStart.getTime() + ratio * viewMs;

      const factor = e.deltaY > 0 ? 1.35 : 1 / 1.35;
      const newSpan = Math.max(30_000, Math.min(totalMs, viewMs * factor));

      let newStart = focusMs - ratio * newSpan;
      let newEnd = focusMs + (1 - ratio) * newSpan;

      if (newStart < earliest.getTime()) {
        newEnd = Math.min(latest.getTime(), newEnd + earliest.getTime() - newStart);
        newStart = earliest.getTime();
      }
      if (newEnd > latest.getTime()) {
        newStart = Math.max(earliest.getTime(), newStart - (newEnd - latest.getTime()));
        newEnd = latest.getTime();
      }

      setViewStart(new Date(newStart));
      setViewEnd(new Date(newEnd));
    },
    [viewStart, viewMs, totalMs, earliest, latest],
  );

  useEffect(() => {
    const el = barRef.current;
    if (!el) return;
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, [handleWheel]);

  // Global mouseup — seek if no pan occurred
  useEffect(() => {
    const onUp = (e: MouseEvent) => {
      if (dragStartX.current === null) return;
      if (!didPan.current && barRef.current) {
        const rect = barRef.current.getBoundingClientRect();
        if (e.clientX >= rect.left && e.clientX <= rect.right) {
          onSeek(xToTime(e.clientX));
        }
      }
      dragStartX.current = null;
      didPan.current = false;
    };
    window.addEventListener("mouseup", onUp);
    return () => window.removeEventListener("mouseup", onUp);
  }, [xToTime, onSeek]);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      dragStartX.current = e.clientX;
      dragViewStart.current = viewStart.getTime();
      dragViewSpan.current = viewMs;
      didPan.current = false;
    },
    [viewStart, viewMs],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!barRef.current) return;
      const rect = barRef.current.getBoundingClientRect();
      setHoverX(e.clientX - rect.left);
      setHoverTime(xToTime(e.clientX));

      if (dragStartX.current !== null) {
        const dx = e.clientX - dragStartX.current;
        if (Math.abs(dx) > 4) {
          didPan.current = true;
          const msPerPx = dragViewSpan.current / rect.width;
          const deltaMs = -dx * msPerPx;

          let newStart = dragViewStart.current + deltaMs;
          let newEnd = newStart + dragViewSpan.current;

          if (newStart < earliest.getTime()) {
            newStart = earliest.getTime();
            newEnd = newStart + dragViewSpan.current;
          }
          if (newEnd > latest.getTime()) {
            newEnd = latest.getTime();
            newStart = newEnd - dragViewSpan.current;
          }

          setViewStart(new Date(newStart));
          setViewEnd(new Date(newEnd));
        }
      }
    },
    [xToTime, earliest, latest],
  );

  const resetZoom = useCallback(() => {
    setViewStart(earliest);
    setViewEnd(latest);
  }, [earliest, latest]);

  const axisTicks = () => {
    if (viewMs <= 0) return [];
    const interval = smartTickInterval(viewMs);
    const first = Math.ceil(viewStart.getTime() / interval) * interval;
    const ticks: { pct: number; label: string }[] = [];
    for (let t = first; t <= viewEnd.getTime(); t += interval) {
      ticks.push({
        pct: ((t - viewStart.getTime()) / viewMs) * 100,
        label: formatAxisTime(new Date(t), viewMs),
      });
    }
    return ticks;
  };

  const currentPct = timeToPercent(currentTime);

  return (
    <div className="select-none">
      {/* Axis */}
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
        {isZoomed && (
          <button
            className="absolute right-0 top-0 text-xs text-blue-400 hover:text-blue-300"
            onClick={resetZoom}
          >
            Reset zoom
          </button>
        )}
      </div>

      {/* Bar */}
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs text-gray-400 w-16 shrink-0 truncate">{label}</span>
        <div
          ref={barRef}
          className={`relative flex-1 h-4 rounded ${isZoomed ? "cursor-grab active:cursor-grabbing" : "cursor-pointer"}`}
          style={{ background: "#1a1a2e" }}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoverTime(null)}
          onMouseDown={handleMouseDown}
          onDoubleClick={resetZoom}
        >
          {ranges.map((r, i) => {
            const left = timeToPercent(new Date(r.start));
            const right = timeToPercent(new Date(r.end));
            if (right <= 0 || left >= 100) return null;
            return (
              <div
                key={i}
                className="absolute top-0 h-full rounded-sm"
                style={{
                  left: `${Math.max(0, left)}%`,
                  width: `${Math.min(100, right) - Math.max(0, left)}%`,
                  background: "#e53935",
                }}
              />
            );
          })}

          {currentPct >= 0 && currentPct <= 100 && (
            <div
              className="absolute top-0 h-full w-0.5 z-10 pointer-events-none"
              style={{
                left: `${currentPct}%`,
                background: "#ffffff",
                boxShadow: "0 0 4px rgba(255,255,255,0.8)",
              }}
            />
          )}

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

      {isZoomed && (
        <p className="text-xs text-gray-600 text-right">
          scroll to zoom · drag to pan · double-click to reset
        </p>
      )}
    </div>
  );
}

export { formatFullTimestamp };
