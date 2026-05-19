#include "Camera.hpp"
#include <stdexcept>
#include <thread>
#include <chrono>

Camera::Camera(const std::string& ip, int64_t switchoverKey)
    : switchoverKey_(switchoverKey)
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

    claimAccess();

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

void Camera::claimAccess()
{
    GenApi::INodeMap* tlDev = device_->GetTLDeviceNodeMap();

    // GigE Vision CCP heartbeat locks can persist several seconds after the
    // previous app exits. Retry for up to 15 seconds before giving up.
    for (int attempt = 0; attempt < 15; attempt++) {
        std::string status = Arena::GetNodeValue<GenICam::gcstring>(
            tlDev, "DeviceAccessStatus").c_str();

        if (status == "ReadWrite")
            return;

        std::cerr << "Camera access status: " << status
                  << " (attempt " << attempt + 1 << "/15, key=" << switchoverKey_ << ")\n";

        try {
            Arena::SetNodeValue<int64_t>(tlDev, "CcpSwitchoverKey", switchoverKey_);
        } catch (const GenICam::GenericException& ex) {
            std::cerr << "  CcpSwitchoverKey failed: " << ex.GetDescription() << "\n";
        }

        try {
            Arena::SetNodeValue<GenICam::gcstring>(tlDev, "DeviceAccessStatus", "ReadWrite");
        } catch (const GenICam::GenericException& ex) {
            std::cerr << "  DeviceAccessStatus set failed: " << ex.GetDescription() << "\n";
        }

        std::this_thread::sleep_for(std::chrono::seconds(1));
    }

    std::string finalStatus = Arena::GetNodeValue<GenICam::gcstring>(
        tlDev, "DeviceAccessStatus").c_str();
    throw std::runtime_error(
        "Cannot claim ReadWrite access to camera at " + ip_ +
        " (status: " + finalStatus + "). Stop all other applications using the camera.");
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
