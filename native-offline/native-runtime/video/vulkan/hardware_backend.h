#pragma once

#include "../../core/video_backend.h"
#include "vulkan_backend.h"

namespace an3 {

// The portable Azahar path intentionally has one job: preserve the core's
// Vulkan image plus fences/semaphores through the shared presenter into the
// platform swapchain. It cannot fall back to a software upload or GLES path.
class VulkanHardwareBackend final : public NativeVideoBackend {
    PortableVulkanBackend renderer_;
    NativeWindowSurface* surface_ = nullptr;
    NativeVideoStatus status_;

public:
    bool initialize(NativeWindowSurface& surface, std::string&) override {
        surface_ = &surface;
        status_.requested = "vulkan";
        return true; // libretro performs the real hardware negotiation later.
    }
    void resize() override {}
    bool begin_frame() override { return renderer_.ready(); }
    bool acquire_software_framebuffer(unsigned, unsigned, int, void*&, std::size_t&) override { return false; }
    void present_software(const void*, unsigned, unsigned, std::size_t, int) override {}
    bool initialize_hardware_renderer(const NativeHardwareRenderRequest& request, std::string& error) override {
        if (!surface_) { error = "hardware-frame: native surface is unavailable"; return false; }
        if (!renderer_.initialize(surface_, "libvulkan.so", request.callbacks,
                                  request.negotiation_interface, error)) {
            status_.failure_stage = "vulkan-hardware-initialize";
            status_.failure_reason = error;
            return false;
        }
        status_.effective = "vulkan";
        return true;
    }
    void* hardware_render_interface() override { return renderer_.hardware_interface(); }
    bool receive_native_gpu_frame(const void*, std::string& error) override {
        error = "hardware-frame: Vulkan interface accepts core-provided images directly";
        return false;
    }
    void present_native_gpu_frame(unsigned width, unsigned height) override { renderer_.present(width, height); }
    NativeVideoStatus metrics() const override {
        auto result = status_;
        result.frames = renderer_.renderer_metrics();
        result.device_details = renderer_.device_details();
        return result;
    }
    void shutdown() override { renderer_.shutdown(); surface_ = nullptr; status_.effective.clear(); }
};

} // namespace an3
