#pragma once
#include <glib.h>
#include <libsoup/soup.h>
#include <memory>
#include <string>
#include "WebRTCPeer.hpp"

class SignalingServer {
public:
    SignalingServer(const std::string& sourceFile, int port, GMainLoop* loop);
    ~SignalingServer();

private:
    static void onHttp(SoupServer*, SoupServerMessage*,
                       const char*, GHashTable*, gpointer);
    static void onWebSocket(SoupServer*, SoupServerMessage*, const char*,
                            SoupWebsocketConnection*, gpointer);
    static void onWsMessage(SoupWebsocketConnection*, gint,
                            GBytes*, gpointer);
    static void onWsClosed(SoupWebsocketConnection*, gpointer);

    std::string              sourceFile_;
    SoupServer*              server_ = nullptr;
    SoupWebsocketConnection* ws_     = nullptr;
    std::unique_ptr<WebRTCPeer> peer_;
};
