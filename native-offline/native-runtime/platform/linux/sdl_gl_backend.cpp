// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#include "sdl_gl_backend.h"

#include "sdl_window_surface.h"

#include <SDL2/SDL.h>
#include <SDL2/SDL_opengl.h>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <limits>
#include <mutex>
#include <string>
#include <string_view>
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

unsigned next_power_of_two(unsigned value) {
    unsigned result = 1;
    while (result < value) result <<= 1;
    return result;
}

bool gl_version_at_least(int wanted_major, int wanted_minor) {
    const auto* version = reinterpret_cast<const char*>(glGetString(GL_VERSION));
    int major = 0, minor = 0;
    if (!version || std::sscanf(version, "%d.%d", &major, &minor) != 2) return false;
    return major > wanted_major || (major == wanted_major && minor >= wanted_minor);
}

bool gl_has_extension(const char* extensions, std::string_view wanted) {
    if (!extensions || wanted.empty()) return false;
    const std::string_view list(extensions);
    std::size_t offset = 0;
    while ((offset = list.find(wanted, offset)) != std::string_view::npos) {
        const bool starts_token = offset == 0 || list[offset - 1] == ' ';
        const auto end = offset + wanted.size();
        const bool ends_token = end == list.size() || list[end] == ' ';
        if (starts_token && ends_token) return true;
        offset = end;
    }
    return false;
}

uint8_t expand_5_bit(uint16_t value) {
    return static_cast<uint8_t>((value << 3) | (value >> 2));
}

uint8_t expand_6_bit(uint16_t value) {
    return static_cast<uint8_t>((value << 2) | (value >> 4));
}

void convert_software_frame_to_rgba(const uint8_t* source, unsigned width, unsigned height,
                                    std::size_t pitch, int format, std::vector<uint8_t>& output) {
    output.resize(static_cast<std::size_t>(width) * height * 4u);
    const std::size_t input_bytes_per_pixel = format == kPixelXrgb8888 ? 4u : 2u;
    for (unsigned y = 0; y < height; ++y) {
        const auto* input_row = source + static_cast<std::size_t>(y) * pitch;
        auto* output_row = output.data() + static_cast<std::size_t>(y) * width * 4u;
        for (unsigned x = 0; x < width; ++x) {
            auto* rgba = output_row + static_cast<std::size_t>(x) * 4u;
            if (format == kPixelXrgb8888) {
                const auto* bgra = input_row + static_cast<std::size_t>(x) * input_bytes_per_pixel;
                rgba[0] = bgra[2]; rgba[1] = bgra[1]; rgba[2] = bgra[0];
            } else {
                uint16_t pixel = 0;
                std::memcpy(&pixel, input_row + static_cast<std::size_t>(x) * input_bytes_per_pixel, sizeof(pixel));
                rgba[0] = expand_5_bit(static_cast<uint16_t>((pixel >> (format == kPixelRgb565 ? 11 : 10)) & 0x1fu));
                rgba[1] = format == kPixelRgb565
                    ? expand_6_bit(static_cast<uint16_t>((pixel >> 5) & 0x3fu))
                    : expand_5_bit(static_cast<uint16_t>((pixel >> 5) & 0x1fu));
                rgba[2] = expand_5_bit(static_cast<uint16_t>(pixel & 0x1fu));
            }
            rgba[3] = 0xffu;
        }
    }
}
} // namespace

struct LinuxSdlGlBackend::Impl {
    SDL_Window* window = nullptr;
    SDL_GLContext context = nullptr;
    GLuint texture = 0;
    unsigned texture_width = 0, texture_height = 0;
    std::array<std::vector<uint8_t>, 2> staging;
    unsigned active_slot = 0;
    bool supports_edge_clamp = false;
    bool supports_bgra = false;
    bool supports_packed_pixels = false;
    bool supports_npot = false;
    std::array<std::vector<uint8_t>, 2> converted;
    bool active = false;
    NativeVideoStatus status{};
    mutable std::mutex status_mutex;

    bool current() const { return window && context && SDL_GL_MakeCurrent(window, context) == 0; }

    void record_present_error(const char* stage, GLenum code, const std::string& details = {}) {
        std::lock_guard<std::mutex> lock(status_mutex);
        ++status.frames.dropped_frames;
        status.failure_stage = stage;
        status.failure_reason = "Desktop OpenGL " + std::string(stage) + " failed (error " + std::to_string(code) + ").";
        if (!details.empty()) status.failure_reason += " " + details;
    }
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
    const auto* extensions = reinterpret_cast<const char*>(glGetString(GL_EXTENSIONS));
    impl_->supports_edge_clamp = gl_version_at_least(1, 2) ||
        gl_has_extension(extensions, "GL_EXT_texture_edge_clamp") ||
        gl_has_extension(extensions, "GL_SGIS_texture_edge_clamp");
    impl_->supports_bgra = gl_version_at_least(1, 2) || gl_has_extension(extensions, "GL_EXT_bgra");
    impl_->supports_packed_pixels = gl_version_at_least(1, 2) || gl_has_extension(extensions, "GL_EXT_packed_pixels");
    impl_->supports_npot = gl_version_at_least(2, 0) || gl_has_extension(extensions, "GL_ARB_texture_non_power_of_two");
    glGenTextures(1, &impl_->texture);
    glBindTexture(GL_TEXTURE_2D, impl_->texture);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    const GLint texture_wrap = impl_->supports_edge_clamp ? GL_CLAMP_TO_EDGE : GL_CLAMP;
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, texture_wrap);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, texture_wrap);
    const GLenum setup_error = glGetError();
    if (!impl_->texture || setup_error != GL_NO_ERROR) {
        const auto* version = reinterpret_cast<const char*>(glGetString(GL_VERSION));
        const auto* renderer = reinterpret_cast<const char*>(glGetString(GL_RENDERER));
        error = "Desktop OpenGL texture setup failed (error " + std::to_string(setup_error) + ", " +
            (version ? version : "unknown version") + " / " + (renderer ? renderer : "unknown renderer") + ").";
        shutdown(); return false;
    }
    impl_->status.requested = "opengl";
    impl_->status.effective = "opengl";
    impl_->status.frames_in_flight = 2;
    const char* version = reinterpret_cast<const char*>(glGetString(GL_VERSION));
    const char* renderer = reinterpret_cast<const char*>(glGetString(GL_RENDERER));
    impl_->status.device_details = std::string(version ? version : "OpenGL") + " / " + (renderer ? renderer : "unknown renderer") +
        " / reusable texture ring=2 / BGRA=" + (impl_->supports_bgra ? "direct" : "RGBA conversion") +
        " / RGB565=" + (impl_->supports_packed_pixels ? "direct" : "RGBA conversion") +
        " / NPOT=" + (impl_->supports_npot ? "direct" : "padded");
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
        std::lock_guard<std::mutex> lock(impl_->status_mutex);
        ++impl_->status.frames.dropped_frames;
        return;
    }
    const unsigned allocation_width = impl_->supports_npot ? width : next_power_of_two(width);
    const unsigned allocation_height = impl_->supports_npot ? height : next_power_of_two(height);
    const auto upload_start = std::chrono::steady_clock::now();
    glBindTexture(GL_TEXTURE_2D, impl_->texture);
    const auto* version = reinterpret_cast<const char*>(glGetString(GL_VERSION));
    const auto* renderer = reinterpret_cast<const char*>(glGetString(GL_RENDERER));
    const std::string context_details = "(frame " + std::to_string(width) + "x" + std::to_string(height) +
        ", GL " + (version ? version : "unknown") + " / " + (renderer ? renderer : "unknown renderer") + ")";
    const GLenum preallocation_error = glGetError();
    if (preallocation_error != GL_NO_ERROR) {
        impl_->record_present_error("texture preflight", preallocation_error, context_details);
        return;
    }
    if (impl_->texture_width != allocation_width || impl_->texture_height != allocation_height) {
        GLint maximum_texture_size = 0;
        glGetIntegerv(GL_MAX_TEXTURE_SIZE, &maximum_texture_size);
        const GLenum limit_query_error = glGetError();
        if (limit_query_error != GL_NO_ERROR) {
            impl_->record_present_error("texture limit query", limit_query_error, context_details);
            return;
        }
        const std::string allocation_details = "(frame " + std::to_string(width) + "x" + std::to_string(height) +
            ", allocation " + std::to_string(allocation_width) + "x" + std::to_string(allocation_height) +
            ", max texture size " + std::to_string(maximum_texture_size) + ", GL " +
            (version ? version : "unknown") + " / " + (renderer ? renderer : "unknown renderer") + ")";
        if (maximum_texture_size <= 0 || allocation_width > static_cast<unsigned>(maximum_texture_size) ||
            allocation_height > static_cast<unsigned>(maximum_texture_size)) {
            impl_->record_present_error("texture size exceeds maximum", GL_INVALID_VALUE, allocation_details);
            return;
        }
        // OpenGL 1.1 requires a component count (1–4) for the internal
        // format. Symbolic base formats such as GL_RGBA became valid in 1.2.
        const GLint internal_format = gl_version_at_least(1, 2) ? GL_RGBA : 4;
        glTexImage2D(GL_TEXTURE_2D, 0, internal_format, static_cast<GLsizei>(allocation_width),
                     static_cast<GLsizei>(allocation_height), 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
        const GLenum allocation_error = glGetError();
        if (allocation_error != GL_NO_ERROR) {
            impl_->record_present_error("texture allocation", allocation_error, allocation_details);
            return;
        }
        impl_->texture_width = allocation_width; impl_->texture_height = allocation_height;
    }
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    const bool can_upload_directly = (format == kPixelXrgb8888 && impl_->supports_bgra) ||
        (format == kPixelRgb565 && impl_->supports_packed_pixels);
    const bool tight_pitch = pitch == static_cast<std::size_t>(width) * bytes_per_pixel;
    const void* upload_pixels = framebuffer;
    GLenum upload_format = GL_RGBA;
    GLenum upload_type = GL_UNSIGNED_BYTE;
    if (can_upload_directly) {
        if (!tight_pitch) {
            auto& slot = impl_->staging[impl_->active_slot];
            const std::size_t row_bytes = static_cast<std::size_t>(width) * bytes_per_pixel;
            slot.resize(row_bytes * height);
            const auto* source = static_cast<const uint8_t*>(framebuffer);
            for (unsigned row = 0; row < height; ++row) {
                std::memcpy(slot.data() + static_cast<std::size_t>(row) * row_bytes,
                            source + static_cast<std::size_t>(row) * pitch, row_bytes);
            }
            upload_pixels = slot.data();
        }
        if (format == kPixelXrgb8888) {
            upload_format = GL_BGRA;
        } else {
            upload_format = GL_RGB;
            upload_type = GL_UNSIGNED_SHORT_5_6_5;
        }
        std::lock_guard<std::mutex> lock(impl_->status_mutex);
        if (tight_pitch) ++impl_->status.frames.direct_software_uploads;
        else ++impl_->status.frames.copied_software_uploads;
    } else {
        auto& slot = impl_->converted[impl_->active_slot];
        convert_software_frame_to_rgba(static_cast<const uint8_t*>(framebuffer), width, height, pitch, format, slot);
        upload_pixels = slot.data();
        upload_format = GL_RGBA;
        upload_type = GL_UNSIGNED_BYTE;
        std::lock_guard<std::mutex> lock(impl_->status_mutex);
        ++impl_->status.frames.copied_software_uploads;
    }
    glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, width, height, upload_format, upload_type, upload_pixels);
    const GLenum upload_error = glGetError();
    if (upload_error != GL_NO_ERROR) {
        impl_->record_present_error("frame upload", upload_error);
        return;
    }
    {
        std::lock_guard<std::mutex> lock(impl_->status_mutex);
        ++impl_->status.frames.software_uploads;
    }
    int drawable_width = 1, drawable_height = 1;
    SDL_GL_GetDrawableSize(impl_->window, &drawable_width, &drawable_height);
    const double source_aspect = static_cast<double>(width) / height;
    const double target_aspect = static_cast<double>(drawable_width) / std::max(1, drawable_height);
    int view_width = drawable_width, view_height = drawable_height;
    if (target_aspect > source_aspect) view_width = static_cast<int>(view_height * source_aspect); else view_height = static_cast<int>(view_width / source_aspect);
    glViewport(0, 0, drawable_width, drawable_height); glClearColor(0, 0, 0, 1); glClear(GL_COLOR_BUFFER_BIT);
    glViewport((drawable_width - view_width) / 2, (drawable_height - view_height) / 2, view_width, view_height);
    glEnable(GL_TEXTURE_2D); glColor3f(1, 1, 1);
    const float texture_min_u = allocation_width == width ? 0.0f : 0.5f / static_cast<float>(allocation_width);
    const float texture_min_v = allocation_height == height ? 0.0f : 0.5f / static_cast<float>(allocation_height);
    const float texture_max_u = allocation_width == width ? 1.0f : (static_cast<float>(width) - 0.5f) / allocation_width;
    const float texture_max_v = allocation_height == height ? 1.0f : (static_cast<float>(height) - 0.5f) / allocation_height;
    glBegin(GL_TRIANGLE_STRIP);
    glTexCoord2f(texture_min_u, texture_max_v); glVertex2f(-1, -1); glTexCoord2f(texture_max_u, texture_max_v); glVertex2f(1, -1);
    glTexCoord2f(texture_min_u, texture_min_v); glVertex2f(-1, 1); glTexCoord2f(texture_max_u, texture_min_v); glVertex2f(1, 1);
    glEnd(); glDisable(GL_TEXTURE_2D);
    const GLenum draw_error = glGetError();
    if (draw_error != GL_NO_ERROR) {
        impl_->record_present_error("frame draw", draw_error);
        return;
    }
    SDL_GL_SwapWindow(impl_->window);
    {
        std::lock_guard<std::mutex> lock(impl_->status_mutex);
        ++impl_->status.frames.presented_frames;
    }
    (void)upload_start;
    impl_->active_slot = (impl_->active_slot + 1) % impl_->staging.size();
}

bool LinuxSdlGlBackend::receive_native_gpu_frame(const void*, std::string& error) { error = "hardware-frame: desktop OpenGL fallback cannot consume Vulkan images"; return false; }
void LinuxSdlGlBackend::present_native_gpu_frame(unsigned, unsigned) {}
NativeVideoStatus LinuxSdlGlBackend::metrics() const {
    std::lock_guard<std::mutex> lock(impl_->status_mutex);
    return impl_->status;
}

void LinuxSdlGlBackend::shutdown() {
    if (impl_ && impl_->context && impl_->current() && impl_->texture) glDeleteTextures(1, &impl_->texture);
    if (impl_ && impl_->context) SDL_GL_DeleteContext(impl_->context);
    if (!impl_) return;
    impl_->context = nullptr; impl_->window = nullptr; impl_->texture = 0; impl_->texture_width = impl_->texture_height = 0;
    for (auto& slot : impl_->staging) slot.clear();
    for (auto& slot : impl_->converted) slot.clear();
    impl_->active = false; impl_->status.effective.clear();
}

} // namespace an3
