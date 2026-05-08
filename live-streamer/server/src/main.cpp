#include <iostream>
#include <csignal>
#include <atomic>
#include <cstdlib>
#include <gst/gst.h>
#include "Camera.hpp"
#include "Pipeline.hpp"

static std::atomic<bool> running{true};
static void on_signal(int) { running = false; }

int main(int argc, char* argv[])
{
    std::signal(SIGINT,  on_signal);
    std::signal(SIGTERM, on_signal);

    gst_init(&argc, &argv);
    std::system("mkdir -p /tmp/hls");

    try {
        Camera   camera("192.168.1.240");
        std::cout << "Camera: " << camera.width() << "x" << camera.height()
                  << " " << camera.pixelFormat() << "\n";

        Pipeline pipeline(camera.width(), camera.height(),
                          camera.gstBayerFormat(), "/tmp/hls");

        pipeline.start();
        camera.startStream();
        std::cout << "Streaming to /tmp/hls/stream.m3u8 — Ctrl+C to stop\n";

        while (running) {
            size_t size = 0;
            const uint8_t* data = camera.grabFrame(size);
            pipeline.pushFrame(data, size);
            camera.releaseFrame();
        }

        camera.stopStream();
        pipeline.stop();
    }
    catch (const std::exception& ex) {
        std::cerr << "Error: " << ex.what() << "\n";
        return 1;
    }

    return 0;
}
