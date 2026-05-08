cmake_minimum_required(VERSION 3.16)
project(lucid_stream)

# GStreamer
find_package(PkgConfig REQUIRED)
pkg_check_modules(GST REQUIRED
    gstreamer-1.0
    gstreamer-app-1.0
)

# Build target
add_executable(lucid_stream main.cpp)

target_include_directories(lucid_stream PRIVATE
    "${ARENA_SDK_ROOT}/include/Arena"
    "${ARENA_SDK_ROOT}/include/GenTL"
    "${ARENA_SDK_ROOT}/include/GenICam"
    ${GST_INCLUDE_DIRS}
)

target_link_libraries(lucid_stream PRIVATE
  ${ARENA_LIB}
  ${GST_LIBRARIES}
)