cmake_minimum_required(VERSION 3.16)
project(webrtc_stream CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(PkgConfig REQUIRED)
pkg_check_modules(GST        REQUIRED IMPORTED_TARGET gstreamer-1.0)
pkg_check_modules(GST_WEBRTC REQUIRED IMPORTED_TARGET gstreamer-webrtc-1.0)
pkg_check_modules(GST_SDP    REQUIRED IMPORTED_TARGET gstreamer-sdp-1.0)
pkg_check_modules(SOUP       REQUIRED IMPORTED_TARGET libsoup-3.0)

find_package(nlohmann_json 3 REQUIRED)

add_executable(webrtc_stream
    src/main.cpp
    src/SignalingServer.cpp
    src/WebRTCPeer.cpp
)

target_link_libraries(webrtc_stream PRIVATE
    PkgConfig::GST
    PkgConfig::GST_WEBRTC
    PkgConfig::GST_SDP
    PkgConfig::SOUP
    nlohmann_json::nlohmann_json
)
