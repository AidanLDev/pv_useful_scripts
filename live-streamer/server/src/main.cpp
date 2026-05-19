#include <iostream>
#include <csignal>
#include <atomic>
#include <filesystem>
#include <string>
#include <gst/gst.h>
#include "Camera.hpp"
#include "Pipeline.hpp"
#include "DummyPipeline.hpp"
#include "SegmentDatabase.hpp"

using namespace std;

static atomic<bool> running{true};
static void on_signal(int) { running = false; }

int main(int argc, char *argv[])
{
    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);

    gst_init(&argc, &argv);

    string  cameraIp     = "";
    string  dummyFile    = "";
    string  outputDir    = "/tmp/hls";
    string  dbPath       = "./segments.db";
    int64_t switchoverKey = 0;
    bool    forceDummy   = false;

    for (int i = 1; i < argc; ++i)
    {
        string arg = argv[i];
        if (arg == "--ip" && i + 1 < argc)
            cameraIp = argv[++i];
        else if (arg == "--key" && i + 1 < argc)
            switchoverKey = stoll(argv[++i]);
        else if (arg == "--out" && i + 1 < argc)
            outputDir = argv[++i];
        else if (arg == "--db" && i + 1 < argc)
            dbPath = argv[++i];
        else if (arg == "--file" && i + 1 < argc)
        {
            dummyFile = argv[++i];
            forceDummy = true;
        }
        else if (arg == "--dummy") {
            forceDummy = true;
            dummyFile = "";
        }
    }

    filesystem::create_directories(outputDir);

    SegmentDatabase db(dbPath);

    if (!forceDummy)
    {
        try
        {
            Camera camera(cameraIp, switchoverKey);
            cout << "Camera: " << camera.ip() << " "
                 << camera.width() << "x" << camera.height()
                 << " " << camera.pixelFormat() << endl;

            Pipeline pipeline(camera.width(), camera.height(),
                              camera.gstBayerFormat(), outputDir, db);
            pipeline.start();
            camera.startStream();
            cout << "Recording to " << outputDir << " — Ctrl+C to stop\n";

            while (running)
            {
                size_t size = 0;
                const uint8_t *data = camera.grabFrame(size);
                pipeline.pushFrame(data, size);
                camera.releaseFrame();
            }

            camera.stopStream();
            pipeline.stop();
            return 0;
        }
        catch (const exception &ex)
        {
            cerr << "Camera unavailable (" << ex.what() << ") — falling back to dummy pipeline\n";
        }
        catch (const GenICam::GenericException& ex)
        {
            cerr << "Camera unavailable (" << ex.GetDescription() << ") — falling back to dummy pipeline\n";
        }
        catch (...)
        {
            cerr << "Camera unavailable (unknown exception) — falling back to dummy pipeline\n";
        }
    }

    try
    {
        DummyPipeline dummy(dummyFile, outputDir, db);
        cout << "Recording to " << outputDir << " — Ctrl+C to stop\n";
        dummy.run(running);
    }
    catch (const exception &ex)
    {
        cerr << "Error: " << ex.what() << "\n";
        return 1;
    }

    return 0;
}
