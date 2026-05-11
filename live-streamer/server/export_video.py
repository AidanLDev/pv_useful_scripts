#!/usr/bin/env python3
"""Export a time-range of HLS segments to a single video file.

Usage:
  python export_video.py --db ./segments.db \
      --start "2026-05-11 10:00:00" \
      --end   "2026-05-11 10:05:00" \
      --output clip.mp4

Datetimes are interpreted as local time and compared against UTC ISO 8601
timestamps stored in the database.
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
    parser = argparse.ArgumentParser(description="Export HLS segments to a video file")
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

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for (path, *_) in rows:
            f.write(f"file '{path}'\n")
        concat_file = f.name

    try:
        subprocess.run(
            ["ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_file,
             "-c", "copy", args.output],
            check=True,
        )
        print(f"Exported → {args.output}")
    finally:
        os.unlink(concat_file)


if __name__ == "__main__":
    main()
