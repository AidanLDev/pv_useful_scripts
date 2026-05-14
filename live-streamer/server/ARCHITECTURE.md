# Live-Streamer Server — Architecture & Design

## Overview

The server captures a raw camera feed from a Lucid GigE camera, encodes it to H.264, and delivers it as an HLS stream. Every segment written to disk is also catalogued in a SQLite database with wall-clock timestamps, enabling precise time-range video export after the fact.

```
Camera (GigE/Arena SDK)
  └─ raw Bayer frames
       └─ GStreamer pipeline (bayer2rgb → x264enc → hlssink2)
            ├─ HLS segments + playlist  (.ts / .m3u8)
            └─ SegmentWatcher (background thread)
                 └─ SQLite database  (segments.db)
                      └─ export_video.py  →  .mp4 clip
```

---

## Components

### `main.cpp` — Entry Point

Parses CLI arguments, initialises GStreamer, and runs the main capture loop.

**Startup sequence:**

1. Parse `--ip`, `--out`, `--db`, `--file`, `--dummy` flags.
2. Attempt to open a `Camera` and build a real `Pipeline`.
3. If camera connection fails (or `--dummy` / `--file` is passed), fall back to `DummyPipeline`.
4. Start a `SegmentWatcher` background thread pointed at the output directory.
5. Enter the frame-grab loop: `Camera::grabFrame()` → `Pipeline::pushFrame()` → `Camera::releaseFrame()`.
6. On `SIGINT` / `SIGTERM`, set the `running` atomic flag to `false`; the loop exits and the pipeline is drained cleanly.

**CLI flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--ip <addr>` | `192.168.1.240` | Camera IP address |
| `--out <dir>` | `/tmp/hls` | HLS segment output directory |
| `--db <path>` | `./segments.db` | SQLite database file |
| `--file <path>` | — | Use a video file as the source (implies dummy pipeline) |
| `--dummy` | — | Force the dummy pipeline even if a camera is reachable |

---

### `Camera` — GigE Camera Abstraction

Wraps the Lucid Arena SDK to connect to a camera, configure the sensor, and deliver raw frames.

**Key methods:**

| Method | Description |
|--------|-------------|
| `Camera(ip)` | Discovers and connects to the camera at the given IP via Arena unicast |
| `startStream()` | Configures pixel format (BayerRG8/GR8/BG8/GB8) and packet size (1440 bytes for GigE), then starts acquisition |
| `grabFrame(size)` | Blocks until a frame is available; returns a pointer to raw Bayer data and sets `size` |
| `releaseFrame()` | Returns the buffer back to the device queue — must be called after every `grabFrame` |
| `toGstBayerFormat()` | Maps Arena pixel-format strings to GStreamer Bayer format strings (e.g. `BayerRG8` → `bggr`) |

---

### `Pipeline` — Real GStreamer Encoding Pipeline

Accepts raw Bayer frames from C++ code and produces HLS output.

**GStreamer graph:**

```
appsrc (raw Bayer)
  └─ bayer2rgb
       └─ videoconvert
            └─ x264enc  (tune=zerolatency)
                 └─ h264parse
                      └─ hlssink2  →  seg00000.ts, seg00001.ts, …, stream.m3u8
```

**Key details:**

- `appsrc` is set to `is-live=true`; frames are pushed by the C++ main loop with explicit PTS and duration (33.33 ms @ 30 fps).
- `tune=zerolatency` keeps encoding latency under one frame.
- `hlssink2` writes MPEG-TS segment files and keeps `stream.m3u8` up-to-date. `max-files=0` disables segment rotation so every segment is retained on disk.
- Segment duration defaults to ~10 seconds.

**Key methods:**

| Method | Description |
|--------|-------------|
| `Pipeline(description)` | Parses and instantiates a GStreamer pipeline from a description string |
| `start()` | Transitions the pipeline to `PLAYING` |
| `pushFrame(data, size)` | Wraps raw bytes in a `GstBuffer`, sets PTS/duration, and pushes to `appsrc` |
| `stop()` | Sends EOS, waits for the pipeline to drain, then transitions to `NULL` |

---

### `DummyPipeline` — Fallback / Development Source

Provides a synthetic or file-based video source using the same encoding and HLS output path as the real pipeline. Used when no camera hardware is present.

**GStreamer graph (test pattern):**

```
videotestsrc
  └─ videoconvert
       └─ x264enc
            └─ h264parse
                 └─ hlssink2
```

**GStreamer graph (file source):**

```
filesrc  →  decodebin
                └─ videoconvert
                     └─ x264enc
                          └─ h264parse
                               └─ hlssink2
```

`DummyPipeline::run(atomic<bool>&)` drives its own GStreamer main-loop iteration and returns when the pipeline posts EOS or ERROR, or when the `running` flag is cleared.

---

### `SegmentDatabase` — SQLite Segment Registry

Manages the `segments` table that maps each `.ts` file to its wall-clock time range.

**Schema:**

```sql
CREATE TABLE segments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    filename        TEXT NOT NULL UNIQUE,
    path            TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    start_time      TEXT NOT NULL,   -- ISO 8601 UTC, e.g. "2026-05-11T10:00:00.000Z"
    end_time        TEXT NOT NULL,
    duration        REAL NOT NULL
);
CREATE INDEX idx_time ON segments (start_time, end_time);
```

**Key methods:**

| Method | Description |
|--------|-------------|
| `SegmentDatabase(path)` | Opens (or creates) the SQLite file; creates the table and index if absent |
| `insert(SegmentRecord)` | `INSERT OR IGNORE` — idempotent, safe to call on already-seen segments |
| `allFilenames()` | Returns a `std::unordered_set<string>` of every filename in the DB (used on startup to pre-seed the watcher) |

---

### `SegmentWatcher` — Background Playlist Monitor

A background thread that polls `stream.m3u8` once per second, detects newly-written segments, and records them in the database.

**Algorithm:**

1. On construction, pre-populate the `seen_` set from `SegmentDatabase::allFilenames()` so already-recorded segments are skipped on restart.
2. Every second, call `processM3u8()`:
   - Parse `#EXT-X-MEDIA-SEQUENCE` to get the base sequence number.
   - Walk `#EXTINF:<duration>` / `<filename>` pairs.
   - For each filename not in `seen_`, compute its wall-clock start time anchored to `std::chrono::system_clock::now()` at the moment the segment is first observed (subsequent segments are offset by their cumulative durations from that anchor).
   - `SegmentDatabase::insert()` the record.
   - Add the filename to `seen_`.

---

### `export_video.py` — Time-Range Export Utility

Post-processing script that queries the database and concatenates segments into a single `.mp4` file.

**Usage:**

```bash
python export_video.py \
  --db   segments.db \
  --start "2026-05-11 10:00:00" \
  --end   "2026-05-11 10:05:00" \
  --output clip.mp4
```

Internally it runs `ffmpeg -f concat -safe 0 -i <list> -c copy clip.mp4`.

---

## Build

**Dependencies:**

| Library | Purpose |
|---------|---------|
| Arena SDK | Lucid GigE camera API |
| GStreamer 1.0 (`gstreamer-app`, `gstreamer-video`) | Pipeline, encoding, HLS muxing |
| SQLite3 | Segment metadata storage |
| OpenCV (`core`, `imgproc`) | Bundled with Arena SDK; available for frame pre-processing |

**CMake build:**

```bash
mkdir build && cd build
cmake .. -DARENA_SDK_ROOT=/opt/ArenaSDK
make -j$(nproc)
```

The resulting binary is `lucid_stream`. RPATH is baked in to locate Arena SDK and GStreamer shared libraries at runtime without requiring `LD_LIBRARY_PATH`.

---

## Data Flow (End-to-End)

```
1.  Camera::grabFrame()
      Raw Bayer bytes (e.g. 1920×1080 BayerRG8)

2.  Pipeline::pushFrame()
      Wrapped in GstBuffer with PTS = frame_index × 33.33 ms

3.  GStreamer pipeline
      bayer2rgb → RGB24
      videoconvert → I420 (x264 input format)
      x264enc → H.264 NAL units
      hlssink2 → /tmp/hls/seg00NNN.ts + stream.m3u8

4.  SegmentWatcher (1 Hz poll)
      Detects new segment in stream.m3u8
      Anchors wall-clock timestamp
      Writes row to segments.db

5.  export_video.py (on demand)
      SELECT path FROM segments WHERE start_time >= ? AND end_time <= ?
      ffmpeg concat → clip.mp4
```

---

## Graceful Shutdown

`SIGINT` / `SIGTERM` → sets `running = false` → main loop exits → `Pipeline::stop()` sends GStreamer EOS → hlssink2 finalises the in-progress segment → `SegmentWatcher` thread joins → process exits cleanly. No segments are truncated or left open.
