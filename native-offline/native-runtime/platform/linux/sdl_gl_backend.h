// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "../../core/video_backend.h"

#include <array>
#include <memory>

namespace an3 {

// Desktop OpenGL is a software-core fallback only. Native Vulkan-frame cores
// (Azahar) never enter this backend because copying their GPU images through
// RAM would violate the portable hardware-render contract.
class LinuxSdlGlBackend final : public NativeVideoBackend {
  public:
    LinuxSdlGlBackend();
    ~LinuxSdlGlBackend() override;
    bool initialize(NativeWindowSurface&, std::string&) override;
    void resize() override;
    bool begin_frame() override;
    bool acquire_software_framebuffer(unsigned, unsigned, int, void*&, std::size_t&) override;
    void present_software(const void*, unsigned, unsigned, std::size_t, int) override;
    bool receive_native_gpu_frame(const void*, std::string&) override;
    void present_native_gpu_frame(unsigned, unsigned) override;
    NativeVideoStatus metrics() const override;
    void shutdown() override;

  private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace an3
