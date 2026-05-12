cmake_minimum_required(VERSION 3.16)
project(lucid_stream)

set(CMAKE_CXX_STANDARD 17)

# Arena SDK
set(ARENA_SDK_ROOT "/opt/ArenaSDK" CACHE PATH "Path to Arena SDK root")
set(GENICAM_LIB_DIR "${ARENA_SDK_ROOT}/GenICam/library/lib/Linux64_x64")

find_library(ARENA_LIB    NAMES arena                   HINTS "${ARENA_SDK_ROOT}/lib64" REQUIRED)
find_library(GCBASE_LIB   NAMES GCBase_gcc54_v3_3_LUCID  HINTS "${GENICAM_LIB_DIR}"     REQUIRED)
find_library(GENAPI_LIB   NAMES GenApi_gcc54_v3_3_LUCID  HINTS "${GENICAM_LIB_DIR}"     REQUIRED)
find_library(OPENCV_CORE  NAMES opencv_core               HINTS "${ARENA_SDK_ROOT}/lib64" REQUIRED)
find_library(OPENCV_IMGP  NAMES opencv_imgproc            HINTS "${ARENA_SDK_ROOT}/lib64" REQUIRED)

# SQLite3
find_package(SQLite3 REQUIRED)

# GStreamer
find_package(PkgConfig REQUIRED)
pkg_check_modules(GST REQUIRED
    gstreamer-1.0
    gstreamer-app-1.0
    gstreamer-video-1.0
)

# Build target
add_executable(lucid_stream
    src/main.cpp
    src/Camera.cpp
    src/Pipeline.cpp
    src/DummyPipeline.cpp
    src/SegmentDatabase.cpp
    src/SegmentWatcher.cpp
)

target_include_directories(lucid_stream PRIVATE
    src/
    "${ARENA_SDK_ROOT}/include/Arena"
    "${ARENA_SDK_ROOT}/include/GenTL"
    "${ARENA_SDK_ROOT}/include/GenICam"
    "${ARENA_SDK_ROOT}/GenICam/library/CPP/include"
    ${GST_INCLUDE_DIRS}
)

target_link_libraries(lucid_stream PRIVATE
    # Allow unresolved symbols in Arena's optional RDMA/Metavision transports
    -Wl,--allow-shlib-undefined
    ${ARENA_LIB}
    ${GCBASE_LIB}
    ${GENAPI_LIB}
    ${OPENCV_CORE}
    ${OPENCV_IMGP}
    ${GST_LIBRARIES}
    SQLite::SQLite3 # On Arch SQLite3::SQLite3 worked, might need to revert SQLite::SQLite3 -> SQLite3::SQLite3
)

# Use old-style RPATH (not RUNPATH) so transitive deps are also found
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -Wl,--disable-new-dtags")

set_target_properties(lucid_stream PROPERTIES
    BUILD_RPATH   "${ARENA_SDK_ROOT}/lib64:${GENICAM_LIB_DIR}:${ARENA_SDK_ROOT}/Metavision/lib:${ARENA_SDK_ROOT}/OpenCV/lib:${ARENA_SDK_ROOT}/ffmpeg:${ARENA_SDK_ROOT}/Qt/lib"
    INSTALL_RPATH "${ARENA_SDK_ROOT}/lib64:${GENICAM_LIB_DIR}:${ARENA_SDK_ROOT}/Metavision/lib:${ARENA_SDK_ROOT}/OpenCV/lib:${ARENA_SDK_ROOT}/ffmpeg:${ARENA_SDK_ROOT}/Qt/lib"
)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
