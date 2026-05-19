#include "SignalingServer.hpp"
#include <nlohmann/json.hpp>
#include <iostream>

using json = nlohmann::json;

static const char INDEX_HTML[] = R"html(
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Live Stream</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { background: #000; display: flex; justify-content: center;
           align-items: center; height: 100vh; }
    video { max-width: 100%; max-height: 100vh; }
    #status { position: fixed; top: 12px; left: 12px; color: #fff;
              font: 14px/1 monospace; opacity: 0.7; }
  </style>
</head>
<body>
  <video id="v" autoplay playsinline muted></video>
  <div id="status">Connecting...</div>
  <script>
    const status = document.getElementById('status');
    const ws = new WebSocket(`ws://${location.host}/ws`);
    const pc = new RTCPeerConnection({
      iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
    });

    pc.ontrack = e => {
      document.getElementById('v').srcObject = e.streams[0];
      status.textContent = 'Live';
    };

    pc.onicecandidate = e => {
      if (e.candidate) {
        ws.send(JSON.stringify({
          type: 'ice',
          mlineIndex: e.candidate.sdpMLineIndex,
          candidate: e.candidate.candidate
        }));
      }
    };

    pc.onconnectionstatechange = () => { status.textContent = pc.connectionState; };
    ws.onopen  = () => status.textContent = 'Waiting for offer...';
    ws.onclose = () => status.textContent = 'Disconnected';

    ws.onmessage = async e => {
      const msg = JSON.parse(e.data);
      if (msg.type === 'offer') {
        await pc.setRemoteDescription({ type: 'offer', sdp: msg.sdp });
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        ws.send(JSON.stringify({ type: 'answer', sdp: answer.sdp }));
      } else if (msg.type === 'ice') {
        try {
          await pc.addIceCandidate({ sdpMLineIndex: msg.mlineIndex, candidate: msg.candidate });
        } catch (err) { console.warn('ICE error', err); }
      }
    };
  </script>
</body>
</html>
)html";

SignalingServer::SignalingServer(const std::string& sourceFile, int port, GMainLoop*)
    : sourceFile_(sourceFile)
{
    GError* err = nullptr;
    server_ = soup_server_new("server-header", "webrtc-stream", nullptr);

    soup_server_add_handler(server_, "/", onHttp, this, nullptr);
    soup_server_add_websocket_handler(server_, "/ws",
        nullptr, nullptr, onWebSocket, this, nullptr);

    if (!soup_server_listen_all(server_, static_cast<guint>(port),
                                SOUP_SERVER_LISTEN_IPV4_ONLY, &err)) {
        std::string msg = err ? err->message : "unknown";
        g_clear_error(&err);
        throw std::runtime_error("SoupServer listen failed: " + msg);
    }
    std::cout << "Open http://<ip>:" << port << " in a browser\n";
}

SignalingServer::~SignalingServer() {
    if (server_) {
        soup_server_disconnect(server_);
        g_object_unref(server_);
    }
}

void SignalingServer::onHttp(SoupServer*, SoupServerMessage* msg,
                              const char*, GHashTable*, gpointer) {
    soup_server_message_set_status(msg, 200, nullptr);
    soup_server_message_set_response(msg,
        "text/html; charset=utf-8", SOUP_MEMORY_STATIC,
        INDEX_HTML, sizeof(INDEX_HTML) - 1);
}

void SignalingServer::onWebSocket(SoupServer*, SoupServerMessage*,
                                   const char*, SoupWebsocketConnection* ws,
                                   gpointer data) {
    auto* self = static_cast<SignalingServer*>(data);

    if (self->ws_) {
        soup_websocket_connection_close(self->ws_, SOUP_WEBSOCKET_CLOSE_NORMAL, nullptr);
        g_object_unref(self->ws_);
    }
    self->ws_   = static_cast<SoupWebsocketConnection*>(g_object_ref(ws));
    self->peer_ = nullptr;

    g_signal_connect(ws, "message", G_CALLBACK(onWsMessage), self);
    g_signal_connect(ws, "closed",  G_CALLBACK(onWsClosed),  self);

    std::cout << "Browser connected\n";

    SoupWebsocketConnection* wsRef = self->ws_;
    self->peer_ = std::make_unique<WebRTCPeer>(
        self->sourceFile_,
        [wsRef](const std::string& msg) {
            struct Ctx { SoupWebsocketConnection* ws; std::string msg; };
            g_idle_add([](gpointer d) -> gboolean {
                auto* ctx = static_cast<Ctx*>(d);
                if (soup_websocket_connection_get_state(ctx->ws) ==
                        SOUP_WEBSOCKET_STATE_OPEN)
                    soup_websocket_connection_send_text(ctx->ws, ctx->msg.c_str());
                delete ctx;
                return G_SOURCE_REMOVE;
            }, new Ctx{wsRef, msg});
        });
}

void SignalingServer::onWsMessage(SoupWebsocketConnection*, gint,
                                   GBytes* payload, gpointer data) {
    auto* self = static_cast<SignalingServer*>(data);
    if (!self->peer_) return;

    gsize len = 0;
    const gchar* raw = static_cast<const gchar*>(g_bytes_get_data(payload, &len));
    try {
        json msg = json::parse(std::string(raw, len));
        std::string type = msg["type"];
        if (type == "answer")
            self->peer_->handleAnswer(msg["sdp"].get<std::string>());
        else if (type == "ice")
            self->peer_->handleIceCandidate(
                msg["mlineIndex"].get<guint>(),
                msg["candidate"].get<std::string>());
    } catch (const std::exception& e) {
        std::cerr << "WS parse error: " << e.what() << "\n";
    }
}

void SignalingServer::onWsClosed(SoupWebsocketConnection*, gpointer data) {
    auto* self = static_cast<SignalingServer*>(data);
    std::cout << "Browser disconnected\n";
    self->peer_ = nullptr;
    if (self->ws_) { g_object_unref(self->ws_); self->ws_ = nullptr; }
}
