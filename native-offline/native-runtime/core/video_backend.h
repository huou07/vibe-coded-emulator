// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "window_surface.h"
#include "renderer_contract.h"
#include <cstddef>
#include <cstdint>
#include <string>

namespace an3 {
enum class NativeBackend { Auto, Vulkan, OpenGL };
struct NativeVideoStatus {
    std::string requested, effective, failure_stage, failure_reason, device_details;
    NativeRendererMetrics frames;
    uint32_t frames_in_flight = 2;
};
class NativeVideoBackend {
public:
    virtual ~NativeVideoBackend() = default;
    virtual bool initialize(NativeWindowSurface&, std::string&) = 0;
    virtual void resize() = 0;
    virtual bool begin_frame() = 0;
    virtual bool acquire_software_framebuffer(unsigned,unsigned,int,void*&,std::size_t&) = 0;
    virtual void present_software(const void*,unsigned,unsigned,std::size_t,int) = 0;
    // A backend may reject hardware frames; it must never emulate support by readback.
    // The host calls this after the core has loaded and before context_reset,
    // matching libretro's Vulkan hardware-render lifecycle.
    virtual bool initialize_hardware_renderer(const NativeHardwareRenderRequest&, std::string& error) {
        error = "hardware-frame: this renderer has no negotiated Vulkan context";
        return false;
    }
    virtual void* hardware_render_interface() { return nullptr; }
    // OpenGL hardware rendering: the frontend owns the GL context and the core
    // renders into framebuffer 0. `gl_proc_address` resolves core GL entry
    // points through the platform loader; `present_gl_frame` presents the
    // finished frame. Vulkan-only backends keep these inert.
    virtual void* gl_proc_address(const char*) const { return nullptr; }
    // The FBO the core must render into (0 = default framebuffer).
    virtual unsigned gl_current_framebuffer() const { return 0; }
    virtual bool present_gl_frame(unsigned, unsigned) { return false; }
    virtual bool receive_native_gpu_frame(const void*,std::string&) = 0;
    virtual void present_native_gpu_frame(unsigned,unsigned) = 0;
    virtual NativeVideoStatus metrics() const = 0;
    virtual void shutdown() = 0;
};
class NativeAudioBackend {
public:
    virtual ~NativeAudioBackend() = default;
    virtual bool initialize(double sample_rate,std::string&) = 0;
    virtual std::size_t submit(const int16_t*,std::size_t frames) = 0;
    virtual void shutdown() = 0;
};
}
