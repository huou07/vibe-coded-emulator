#pragma once

#include "../../core/video_backend.h"

#include <memory>

namespace an3 {

// Android's bounded software-frame fallback. This backend requires EGL and
// OpenGL ES 3.x; it deliberately does not claim libretro hardware-frame
// support because doing so would require a negotiated core GL context.
class AndroidGles3Backend final : public NativeVideoBackend {
public:
    AndroidGles3Backend();
    ~AndroidGles3Backend() override;
    AndroidGles3Backend(const AndroidGles3Backend&) = delete;
    AndroidGles3Backend& operator=(const AndroidGles3Backend&) = delete;

    bool initialize(NativeWindowSurface&, std::string&) override;
    void resize() override;
    bool begin_frame() override;
    bool acquire_software_framebuffer(unsigned, unsigned, int, void*&, std::size_t&) override;
    void present_software(const void*, unsigned, unsigned, std::size_t, int) override;
    bool receive_native_gpu_frame(const void*, std::string&) override;
    void present_native_gpu_frame(unsigned, unsigned) override;
    void* gl_proc_address(const char* name) const override;
    unsigned gl_current_framebuffer() const override;
    bool present_gl_frame(unsigned width, unsigned height) override;
    NativeVideoStatus metrics() const override;
    void shutdown() override;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace an3
