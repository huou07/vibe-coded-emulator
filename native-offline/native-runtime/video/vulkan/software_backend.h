#pragma once
#include "../../core/video_backend.h"
#include "vulkan_backend.h"
namespace an3 {
class VulkanSoftwareBackend final : public NativeVideoBackend {
    PortableVulkanBackend renderer_;
    NativeVideoStatus status_;
public:
    bool initialize(NativeWindowSurface& surface,std::string& error) override {
        status_.requested="vulkan";
        if (!renderer_.initialize_software(&surface,"libvulkan.so",error)) {
            status_.failure_stage="vulkan-initialize";status_.failure_reason=error;return false;
        }
        status_.effective="vulkan";return true;
    }
    void resize() override {} // Presenter checks surface extent before each submission.
    bool begin_frame() override { return renderer_.ready(); }
    bool acquire_software_framebuffer(unsigned w,unsigned h,int format,void*& p,std::size_t& pitch) override {
        return renderer_.acquire_software_framebuffer(w,h,format,p,pitch);
    }
    void present_software(const void* p,unsigned w,unsigned h,std::size_t pitch,int format) override {
        renderer_.present_software(p,w,h,pitch,format);
    }
    bool receive_native_gpu_frame(const void*,std::string& error) override {
        error="hardware-frame: this software session has no negotiated hardware context";return false;
    }
    void present_native_gpu_frame(unsigned,unsigned) override {}
    NativeVideoStatus metrics() const override { auto result=status_;result.frames=renderer_.renderer_metrics();result.device_details=renderer_.device_details();return result; }
    void shutdown() override { renderer_.shutdown();status_.effective.clear(); }
};
}
