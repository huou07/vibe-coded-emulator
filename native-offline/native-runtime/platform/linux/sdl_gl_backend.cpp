// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#include "sdl_gl_backend.h"

#include "sdl_window_surface.h"

#include <SDL2/SDL.h>
#include <SDL2/SDL_opengl.h>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <limits>
#include <string>
#include <vector>

namespace an3 {
namespace {
constexpr int kPixel0Rgb1555 = 0;
constexpr int kPixelXrgb8888 = 1;
constexpr int kPixelRgb565 = 2;
constexpr unsigned kMaxDimension = 8192;
constexpr std::size_t kMaxFrameBytes = 256u * 1024u * 1024u;

bool valid_frame(unsigned width, unsigned height, std::size_t bytes_per_pixel, std::size_t& bytes) {
    if (!width || !height || width > kMaxDimension || height > kMaxDimension) return false;
    const std::size_t row = static_cast<std::size_t>(width) * bytes_per_pixel;
    if (row / bytes_per_pixel != width || height > kMaxFrameBytes / row) return false;
    bytes = row * height;
    return true;
}
} // namespace

struct LinuxSdlGlBackend::Impl {
    SDL_Window* window = nullptr;
    SDL_GLContext context = nullptr;
    GLuint texture = 0;
    unsigned texture_width = 0, texture_height = 0;
    std::array<std::vector<uint8_t>, 2> staging;
    unsigned active_slot = 0;
    bool active = false;
    NativeVideoStatus status{};

    bool current() const { return window && context && SDL_GL_MakeCurrent(window, context) == 0; }
};

LinuxSdlGlBackend::LinuxSdlGlBackend() : impl_(std::make_unique<Impl>()) {}
LinuxSdlGlBackend::~LinuxSdlGlBackend() { shutdown(); }

bool LinuxSdlGlBackend::initialize(NativeWindowSurface& native_surface, std::string& error) {
    shutdown();
    auto* surface = dynamic_cast<LinuxSdlWindowSurface*>(&native_surface);
    if (!surface || !surface->window()) { error = "OpenGL fallback needs the Linux SDL window."; return false; }
    // SDL consumes these attributes when it creates the OpenGL-capable
    // window, not when SDL_GL_CreateContext runs. Set them before replacing
    // the Vulkan window so the fallback is valid on X11 and Wayland.
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 2);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 1);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_COMPATIBILITY);
    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
    if (!surface->recreate_for_opengl(error)) return false;
    impl_->window = surface->window();
    impl_->context = SDL_GL_CreateContext(impl_->window);
    if (!impl_->context || !impl_->current()) {
        error = std::string("Desktop OpenGL context creation failed: ") + SDL_GetError();
        shutdown();
        return false;
    }
    SDL_GL_SetSwapInterval(1);
    glGenTextures(1, &impl_->texture);
    glBindTexture(GL_TEXTURE_2D, impl_->texture);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    if (glGetError() != GL_NO_ERROR) { error = "Desktop OpenGL texture allocation failed."; shutdown(); return false; }
    impl_->status.requested = "opengl";
    impl_->status.effective = "opengl";
    impl_->status.frames_in_flight = 2;
    const char* version = reinterpret_cast<const char*>(glGetString(GL_VERSION));
    const char* renderer = reinterpret_cast<const char*>(glGetString(GL_RENDERER));
    impl_->status.device_details = std::string(version ? version : "OpenGL") + " / " + (renderer ? renderer : "unknown renderer") + " / reusable texture ring=2";
    impl_->active = true;
    return true;
}

void LinuxSdlGlBackend::resize() {}
bool LinuxSdlGlBackend::begin_frame() { return impl_->active && impl_->current(); }

bool LinuxSdlGlBackend::acquire_software_framebuffer(unsigned width, unsigned height, int format, void*& data, std::size_t& pitch) {
    data = nullptr; pitch = 0;
    if (!impl_->active || format != kPixelXrgb8888 || !impl_->current()) return false;
    std::size_t bytes = 0;
    if (!valid_frame(width, height, 4, bytes)) return false;
    auto& slot = impl_->staging[impl_->active_slot];
    slot.resize(bytes);
    data = slot.data(); pitch = static_cast<std::size_t>(width) * 4;
    return true;
}

void LinuxSdlGlBackend::present_software(const void* framebuffer, unsigned width, unsigned height, std::size_t pitch, int format) {
    if (!impl_->active || !impl_->current()) return;
    const std::size_t bytes_per_pixel = format == kPixelXrgb8888 ? 4u : 2u;
    std::size_t bytes = 0;
    if (!framebuffer || (format != kPixelXrgb8888 && format != kPixelRgb565 && format != kPixel0Rgb1555) ||
        !valid_frame(width, height, bytes_per_pixel, bytes) || pitch < static_cast<std::size_t>(width) * bytes_per_pixel) {
        ++impl_->status.frames.dropped_frames;
        return;
    }
    const auto upload_start = std::chrono::steady_clock::now();
    glBindTexture(GL_TEXTURE_2D, impl_->texture);
    if (impl_->texture_width != width || impl_->texture_height != height) {
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, static_cast<GLsizei>(width), static_cast<GLsizei>(height), 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
        impl_->texture_width = width; impl_->texture_height = height;
    }
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    if (pitch == static_cast<std::size_t>(width) * bytes_per_pixel) {
        if (format == kPixelXrgb8888) glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, width, height, GL_BGRA, GL_UNSIGNED_BYTE, framebuffer);
        else if (format == kPixelRgb565) glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, width, height, GL_RGB, GL_UNSIGNED_SHORT_5_6_5, framebuffer);
        else glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, width, height, GL_RGBA, GL_UNSIGNED_SHORT_1_5_5_5_REV, framebuffer);
        ++impl_->status.frames.direct_software_uploads;
    } else {
        auto& slot = impl_->staging[impl_->active_slot];
        slot.resize(bytes);
        const auto* source = static_cast<const uint8_t*>(framebuffer);
        for (unsigned row = 0; row < height; ++row) std::memcpy(slot.data() + static_cast<std::size_t>(row) * width * bytes_per_pixel, source + static_cast<std::size_t>(row) * pitch, static_cast<std::size_t>(width) * bytes_per_pixel);
        if (format == kPixelXrgb8888) glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, width, height, GL_BGRA, GL_UNSIGNED_BYTE, slot.data());
        else if (format == kPixelRgb565) glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, width, height, GL_RGB, GL_UNSIGNED_SHORT_5_6_5, slot.data());
        else glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, width, height, GL_RGBA, GL_UNSIGNED_SHORT_1_5_5_5_REV, slot.data());
        ++impl_->status.frames.copied_software_uploads;
    }
    ++impl_->status.frames.software_uploads;
    int drawable_width = 1, drawable_height = 1;
    SDL_GL_GetDrawableSize(impl_->window, &drawable_width, &drawable_height);
    const double source_aspect = static_cast<double>(width) / height;
    const double target_aspect = static_cast<double>(drawable_width) / std::max(1, drawable_height);
    int view_width = drawable_width, view_height = drawable_height;
    if (target_aspect > source_aspect) view_width = static_cast<int>(view_height * source_aspect); else view_height = static_cast<int>(view_width / source_aspect);
    glViewport(0, 0, drawable_width, drawable_height); glClearColor(0, 0, 0, 1); glClear(GL_COLOR_BUFFER_BIT);
    glViewport((drawable_width - view_width) / 2, (drawable_height - view_height) / 2, view_width, view_height);
    glEnable(GL_TEXTURE_2D); glColor3f(1, 1, 1);
    glBegin(GL_TRIANGLE_STRIP);
    glTexCoord2f(0, 1); glVertex2f(-1, -1); glTexCoord2f(1, 1); glVertex2f(1, -1);
    glTexCoord2f(0, 0); glVertex2f(-1, 1); glTexCoord2f(1, 0); glVertex2f(1, 1);
    glEnd(); glDisable(GL_TEXTURE_2D);
    if (glGetError() != GL_NO_ERROR) { ++impl_->status.frames.dropped_frames; return; }
    SDL_GL_SwapWindow(impl_->window);
    ++impl_->status.frames.presented_frames;
    (void)upload_start;
    impl_->active_slot = (impl_->active_slot + 1) % impl_->staging.size();
}

bool LinuxSdlGlBackend::receive_native_gpu_frame(const void*, std::string& error) { error = "hardware-frame: desktop OpenGL fallback cannot consume Vulkan images"; return false; }
void LinuxSdlGlBackend::present_native_gpu_frame(unsigned, unsigned) {}
NativeVideoStatus LinuxSdlGlBackend::metrics() const { return impl_->status; }

void LinuxSdlGlBackend::shutdown() {
    if (impl_ && impl_->context && impl_->current() && impl_->texture) glDeleteTextures(1, &impl_->texture);
    if (impl_ && impl_->context) SDL_GL_DeleteContext(impl_->context);
    if (!impl_) return;
    impl_->context = nullptr; impl_->window = nullptr; impl_->texture = 0; impl_->texture_width = impl_->texture_height = 0;
    for (auto& slot : impl_->staging) slot.clear();
    impl_->active = false; impl_->status.effective.clear();
}

} // namespace an3
