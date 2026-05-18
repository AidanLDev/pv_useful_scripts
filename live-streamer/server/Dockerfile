# syntax=docker/dockerfile:1
ARG BASE_IMAGE=public.ecr.aws/x4v4q0a3/prod_camera-stream-base:1.1.0

FROM ${BASE_IMAGE} AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake \
    build-essential \
    pkg-config \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY src/ ./src/
COPY CMakeLists.txt .

RUN mkdir build && cd build && \
    cmake .. -DARENA_SDK_ROOT=/usr/local/lib/ArenaSDK_Linux_x64 && \
    make -j$(nproc) && \
    cp lucid_stream /lucid_stream

FROM ${BASE_IMAGE} AS runner

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgstreamer1.0-0 \
    libgstreamer-plugins-base1.0-0 \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    libsqlite3-0 \
    python3 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /lucid_stream .
COPY export_video.py .

CMD ["./lucid_stream", "--out", "/tmp/hls", "--db", "/app/segments.db"]
