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
import sqlite3
import subprocess
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
        "SELECT path, start_time, end_time FROM segments"
        " WHERE end_time > ? AND start_time < ?"
        " ORDER BY start_time",
        (start_iso, end_iso),
    ).fetchall()
    conn.close()

    if not rows:
        print("No segments found in the specified time range.")
        return

    print(f"Found {len(rows)} segment(s) covering {rows[0][1]} → {rows[-1][2]}")

    # Use the concat *protocol* (not the concat demuxer) so all segments are
    # treated as one continuous byte stream.  The demuxer approach processes
    # each file independently, giving each segment a DTS counter that restarts
    # near 0 — producing non-monotonic DTS at every boundary and a broken
    # duration in the output container.  Byte-level concatenation avoids this:
    # -r 30 synthesises a single monotonic timestamp sequence across the whole
    # stream, and h264parse config-interval=-1 ensures every IDR is preceded by
    # in-band SPS/PPS so repeated parameter sets at boundaries are harmless.
    concat_uri = "concat:" + "|".join(path for (path, *_) in rows)

    subprocess.run(
        [
            "ffmpeg",
            "-r", "30",      # input framerate — synthesises timestamps for raw Annex B
            "-i", concat_uri,
            "-c", "copy",    # no re-encode; just wrap in the output container
            args.output,
        ],
        check=True,
    )
    print(f"Exported → {args.output}")


if __name__ == "__main__":
    main()
