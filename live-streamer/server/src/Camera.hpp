#pragma once
#include <string>
#include <ArenaApi.h>

class Camera {
public:
    explicit Camera(const std::string& ip);
    ~Camera();

    // Non-copyable — only one owner of the device
    Camera(const Camera&) = delete;
    Camera& operator=(const Camera&) = delete;

    int width() const { return width_; }
    int height() const { return height_; }
    const std::string& ip() const { return ip_; }
    const std::string& pixelFormat() const { return pixelFormat_; }
    const std::string& gstBayerFormat() const { return gstBayerFormat_; }

    void startStream();
    void stopStream();

    // Grabs the next frame. Call releaseFrame() when done with the pointer.
    const uint8_t* grabFrame(size_t& sizeOut, int timeoutMs = 10000);
    void releaseFrame();

private:
    Arena::ISystem* system_  = nullptr;
    Arena::IDevice* device_  = nullptr;
    Arena::IImage*  current_ = nullptr;

    int         width_  = 0;
    int         height_ = 0;
    std::string ip_;
    std::string pixelFormat_;
    std::string gstBayerFormat_;

    void claimAccess();
    static std::string toGstBayerFormat(const std::string& genicam);
};
