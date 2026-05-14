#!/usr/bin/env python3
"""Export a time-range of raw H.264 segments to a single video file.

Usage:
  python export_video.py --db ./segments.db \
      --start "2026-05-11 10:00:00" \
      --end   "2026-05-11 10:05:00" \
      --output clip.mp4

Datetimes are interpreted as local time and compared against UTC ISO 8601
timestamps stored in the database.

Segments are stored as raw Annex B H.264 bitstreams (.h264).  Each file begins
with an IDR frame preceded by in-band SPS/PPS (h264parse config-interval=-1),
so they are self-decodable and can be concatenated without re-encoding.
"""

import argparse
import os
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone


def parse_dt_to_utc_iso(s: str) -> str:
    """Parse a local datetime string and return a UTC ISO 8601 string for DB comparison."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt).astimezone(timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        except ValueError:
            pass
    raise ValueError(f"Cannot parse datetime: {s!r}  (expected YYYY-MM-DD HH:MM:SS)")


def main():
    parser = argparse.ArgumentParser(description="Export H.264 segments to a video file")
    parser.add_argument("--db",     required=True, help="Path to segments.db")
    parser.add_argument("--start",  required=True, help="Start datetime (local time, YYYY-MM-DD HH:MM:SS)")
    parser.add_argument("--end",    required=True, help="End datetime (local time, YYYY-MM-DD HH:MM:SS)")
    parser.add_argument("--output", required=True, help="Output file path (e.g. clip.mp4)")
    args = parser.parse_args()

    start_iso = parse_dt_to_utc_iso(args.start)
    end_iso   = parse_dt_to_utc_iso(args.end)

    if start_iso >= end_iso:
        parser.error("--start must be before --end")

    conn = sqlite3.connect(args.db)
    rows = conn.execute(
        "SELECT path, start_time, end_time, duration FROM segments"
        " WHERE end_time > ? AND start_time < ?"
        " ORDER BY start_time",
        (start_iso, end_iso),
    ).fetchall()
    conn.close()

    if not rows:
        print("No segments found in the specified time range.")
        return

    print(f"Found {len(rows)} segment(s) covering {rows[0][1]} → {rows[-1][2]}")

    # Build an ffconcat file with explicit per-segment durations so ffmpeg can
    # synthesise correct timestamps from the raw H.264 Annex B bitstream.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("ffconcat version 1.0\n")
        for (path, _start, _end, duration) in rows:
            f.write(f"file '{path}'\n")
            f.write(f"duration {duration:.6f}\n")
        concat_file = f.name

    try:
        subprocess.run(
            [
                "ffmpeg",
                # Input: ffconcat list of raw H.264 Annex B files.
                # -r provides a framerate hint used when the bitstream does not
                # carry VUI timing information.
                "-r", "30",
                "-f", "concat", "-safe", "0",
                "-i", concat_file,
                # Stream-copy: no re-encode, just wrap in the output container.
                "-c", "copy",
                args.output,
            ],
            check=True,
        )
        print(f"Exported → {args.output}")
    finally:
        os.unlink(concat_file)


if __name__ == "__main__":
    main()
