#include "Camera.hpp"
#include <stdexcept>

Camera::Camera(const std::string& ip)
{
    system_ = Arena::OpenSystem();
    if (!ip.empty())
        system_->AddUnicastDiscoveryDevice(ip.c_str());
    system_->UpdateDevices(1000);

    auto devices = system_->GetDevices();
    if (devices.empty())
        throw std::runtime_error(ip.empty() ? "No cameras found on network" : "No cameras found at " + ip);

    device_ = system_->CreateDevice(devices[0]);

    Arena::DeviceInfo& info = devices[0];
    ip_ = info.IpAddressStr().c_str();

    GenApi::INodeMap* nm = device_->GetNodeMap();
    width_  = static_cast<int>(GenApi::CIntegerPtr(nm->GetNode("Width"))->GetValue());
    height_ = static_cast<int>(GenApi::CIntegerPtr(nm->GetNode("Height"))->GetValue());
    pixelFormat_ = std::string(
        GenApi::CEnumerationPtr(nm->GetNode("PixelFormat"))->ToString().c_str());
    gstBayerFormat_ = toGstBayerFormat(pixelFormat_);
}

Camera::~Camera()
{
    if (device_) {
        try { device_->StopStream(); } catch (...) {}
        system_->DestroyDevice(device_);
    }
    if (system_)
        Arena::CloseSystem(system_);
}

void Camera::startStream()
{
    GenApi::INodeMap* nm       = device_->GetNodeMap();
    GenApi::INodeMap* tlStream = device_->GetTLStreamNodeMap();

    Arena::SetNodeValue<GenICam::gcstring>(nm, "AcquisitionMode", "Continuous");
    Arena::SetNodeValue<GenICam::gcstring>(nm, "PixelFormat", pixelFormat_.c_str());
    Arena::SetNodeValue<int64_t>(nm, "GevSCPD", 80);

    Arena::SetNodeValue<GenICam::gcstring>(tlStream, "StreamBufferHandlingMode", "NewestOnly");
    Arena::SetNodeValue<bool>(tlStream, "StreamAutoNegotiatePacketSize", true);
    Arena::SetNodeValue<bool>(tlStream, "StreamPacketResendEnable", true);

    device_->StartStream();
}

void Camera::stopStream()
{
    device_->StopStream();
}

const uint8_t* Camera::grabFrame(size_t& sizeOut, int timeoutMs)
{
    current_ = static_cast<Arena::IImage*>(device_->GetBuffer(timeoutMs));
    sizeOut  = current_->GetSizeOfBuffer();
    return current_->GetData();
}

void Camera::releaseFrame()
{
    if (current_) {
        device_->RequeueBuffer(current_);
        current_ = nullptr;
    }
}

std::string Camera::toGstBayerFormat(const std::string& fmt)
{
    if (fmt == "BayerRG8") return "rggb";
    if (fmt == "BayerGR8") return "grbg";
    if (fmt == "BayerBG8") return "bggr";
    if (fmt == "BayerGB8") return "gbrg";
    return "rggb";
}
