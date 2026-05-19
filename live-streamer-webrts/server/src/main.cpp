#include <gst/gst.h>
#include <csignal>
#include <iostream>
#include "SignalingServer.hpp"

static GMainLoop* mainLoop = nullptr;
static void onSignal(int) { if (mainLoop) g_main_loop_quit(mainLoop); }

int main(int argc, char* argv[]) {
    std::cout << std::unitbuf;
    std::cerr << std::unitbuf;
    gst_init(&argc, &argv);
    signal(SIGINT,  onSignal);
    signal(SIGTERM, onSignal);

    std::string sourceFile;
    int port = 8080;

    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--file" && i + 1 < argc) sourceFile = argv[++i];
        if (a == "--port" && i + 1 < argc) port       = std::stoi(argv[++i]);
    }

    if (sourceFile.empty())
        std::cout << "No --file given, using test pattern\n";
    else
        std::cout << "Source file: " << sourceFile << "\n";

    mainLoop = g_main_loop_new(nullptr, FALSE);
    try {
        SignalingServer server(sourceFile, port, mainLoop);
        g_main_loop_run(mainLoop);
    } catch (const std::exception& e) {
        std::cerr << "Fatal: " << e.what() << "\n";
        return 1;
    }
    g_main_loop_unref(mainLoop);
    return 0;
}
