// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
//
// Headless capture backend for deterministic, non-visual testing.
//
// It implements the same NativeVideoBackend contract the windowed backends do,
// but owns no window, surface, or GPU context: it keeps the most recent core
// frame in host memory so a test can hash/diff it without a screenshot or a
// human looking at it. This is a TEST/DEBUG path; the packaged apps keep their
// platform renderers.
//
// Hardware-rendered cores (3DS/Azahar) are deliberately rejected here rather
// than emulated by readback, matching the contract comment in video_backend.h.

#include "../../core/video_backend.h"

#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

namespace an3 {

// libretro retro_pixel_format values.
inline constexpr int kCaptureFormat0RGB1555 = 0;
inline constexpr int kCaptureFormatXRGB8888 = 1;
inline constexpr int kCaptureFormatRGB565 = 2;

// A surface that owns nothing. The capture backend requires the contract's
// reference but never creates a VkSurfaceKHR.
class HeadlessSurface final : public NativeWindowSurface {
public:
    VkExtent2D extent() const override { return VkExtent2D{0, 0}; }
    std::vector<const char*> instance_extensions() const override { return {}; }
    bool create_surface(VkInstance, PFN_vkGetInstanceProcAddr, VkSurfaceKHR&, std::string& error) override {
        error = "headless capture has no presentation surface";
        return false;
    }
};

class NullAudioBackend final : public NativeAudioBackend {
public:
    bool initialize(double sample_rate, std::string&) override {
        sample_rate_ = sample_rate;
        active_ = true;
        return true;
    }
    std::size_t submit(const int16_t*, std::size_t frames) override { return active_ ? frames : 0; }
    void shutdown() override { active_ = false; }
    uint64_t submitted_frames() const { return submitted_frames_; }

private:
    double sample_rate_ = 0.0;
    bool active_ = false;
    uint64_t submitted_frames_ = 0;
};

class CaptureBackend final : public NativeVideoBackend {
public:
    bool initialize(NativeWindowSurface&, std::string&) override {
        status_.requested = "headless";
        status_.effective = "headless";
        return true;
    }
    void resize() override {}
    bool begin_frame() override { return true; }

    bool acquire_software_framebuffer(unsigned width, unsigned height, int, void*& data, std::size_t& pitch) override {
        if (!width || !height) return false;
        pitch = static_cast<std::size_t>(width) * 4u;
        scratch_.assign(static_cast<std::size_t>(height) * pitch, 0);
        data = scratch_.data();
        return true;
    }

    void present_software(const void* framebuffer, unsigned width, unsigned height, std::size_t pitch, int format) override {
        if (!framebuffer || !width || !height || !pitch) return;
        rgba_.resize(static_cast<std::size_t>(width) * height * 4u);
        const auto* rows = static_cast<const uint8_t*>(framebuffer);
        for (unsigned y = 0; y < height; ++y) {
            const uint8_t* row = rows + static_cast<std::size_t>(y) * pitch;
            uint8_t* out = rgba_.data() + static_cast<std::size_t>(y) * width * 4u;
            for (unsigned x = 0; x < width; ++x) {
                uint8_t r = 0, g = 0, b = 0;
                if (format == kCaptureFormatXRGB8888) {
                    const uint32_t pixel = reinterpret_cast<const uint32_t*>(row)[x];
                    r = static_cast<uint8_t>((pixel >> 16) & 0xFF);
                    g = static_cast<uint8_t>((pixel >> 8) & 0xFF);
                    b = static_cast<uint8_t>(pixel & 0xFF);
                } else if (format == kCaptureFormatRGB565) {
                    const uint16_t pixel = reinterpret_cast<const uint16_t*>(row)[x];
                    r = static_cast<uint8_t>(((pixel >> 11) & 0x1F) * 255 / 31);
                    g = static_cast<uint8_t>(((pixel >> 5) & 0x3F) * 255 / 63);
                    b = static_cast<uint8_t>((pixel & 0x1F) * 255 / 31);
                } else { // 0RGB1555
                    const uint16_t pixel = reinterpret_cast<const uint16_t*>(row)[x];
                    r = static_cast<uint8_t>(((pixel >> 10) & 0x1F) * 255 / 31);
                    g = static_cast<uint8_t>(((pixel >> 5) & 0x1F) * 255 / 31);
                    b = static_cast<uint8_t>((pixel & 0x1F) * 255 / 31);
                }
                out[x * 4 + 0] = r;
                out[x * 4 + 1] = g;
                out[x * 4 + 2] = b;
                out[x * 4 + 3] = 0xFF;
            }
        }
        width_ = width;
        height_ = height;
        ++captured_frames_;
        status_.frames.software_uploads = captured_frames_;
        status_.frames.presented_frames = captured_frames_;
    }

    bool initialize_hardware_renderer(const NativeHardwareRenderRequest&, std::string& error) override {
        error = "headless capture does not support a hardware (GPU) renderer; run a software core or use the windowed renderer";
        status_.failure_stage = "headless-hardware";
        status_.failure_reason = error;
        return false;
    }
    bool receive_native_gpu_frame(const void*, std::string& error) override {
        error = "headless capture has no GPU context";
        return false;
    }
    void present_native_gpu_frame(unsigned, unsigned) override {}

    NativeVideoStatus metrics() const override { return status_; }
    void shutdown() override { status_.effective.clear(); }

    bool has_frame() const { return width_ != 0 && height_ != 0 && !rgba_.empty(); }
    unsigned width() const { return width_; }
    unsigned height() const { return height_; }
    const std::vector<uint8_t>& rgba() const { return rgba_; }
    uint64_t captured_frames() const { return captured_frames_; }

private:
    NativeVideoStatus status_;
    std::vector<uint8_t> scratch_;
    std::vector<uint8_t> rgba_;
    unsigned width_ = 0;
    unsigned height_ = 0;
    uint64_t captured_frames_ = 0;
};

} // namespace an3
