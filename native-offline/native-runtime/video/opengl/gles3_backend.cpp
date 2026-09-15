#include "../../platform/android/window_surface.h"
#include "gles3_backend.h"

#include <EGL/egl.h>
#include <GLES3/gl3.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <limits>
#include <mutex>
#include <string>

namespace an3 {
namespace {

constexpr int kPixel0Rgb1555 = 0;
constexpr int kPixelXrgb8888 = 1;
constexpr int kPixelRgb565 = 2;
constexpr unsigned kMaxFrameDimension = 8192;
constexpr size_t kMaxUploadBytes = 256u * 1024u * 1024u;
constexpr size_t kRingSize = 2;

bool valid_frame(unsigned width, unsigned height, size_t bytes_per_pixel, size_t& bytes) {
    if (!width || !height || width > kMaxFrameDimension || height > kMaxFrameDimension) return false;
    const size_t row = static_cast<size_t>(width) * bytes_per_pixel;
    if (row / bytes_per_pixel != width || height > kMaxUploadBytes / row) return false;
    bytes = row * height;
    return bytes <= kMaxUploadBytes;
}

GLuint compile_shader(GLenum type, const char* source, std::string& error) {
    const GLuint shader = glCreateShader(type);
    glShaderSource(shader, 1, &source, nullptr);
    glCompileShader(shader);
    GLint ok = GL_FALSE;
    glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
    if (ok == GL_TRUE) return shader;
    std::array<char, 512> log{};
    GLsizei length = 0;
    glGetShaderInfoLog(shader, static_cast<GLsizei>(log.size()), &length, log.data());
    error = "gles3-shader: " + std::string(log.data(), static_cast<size_t>(std::max(0, length)));
    glDeleteShader(shader);
    return 0;
}

} // namespace

struct AndroidGles3Backend::Impl {
    EGLDisplay display = EGL_NO_DISPLAY;
    EGLSurface surface = EGL_NO_SURFACE;
    EGLContext context = EGL_NO_CONTEXT;
    GLuint program = 0;
    GLuint texture = 0;
    GLuint vao = 0;
    // Azahar's OpenGL renderer composites into this FBO; present_gl_frame then
    // blits the core's layout region to the window with aspect-fit letterboxing.
    GLuint present_fbo = 0;
    GLuint present_texture = 0;
    unsigned present_width = 0;
    unsigned present_height = 0;
    GLint swizzle_location = -1;
    unsigned texture_width = 0;
    unsigned texture_height = 0;
    int surface_width = 0;
    int surface_height = 0;
    bool active = false;
    bool frame_begun = false;
    size_t active_slot = kRingSize;
    size_t next_slot = 0;
    NativeVideoStatus status{};

    struct Slot {
        GLuint pbo = 0;
        GLsync fence = nullptr;
        size_t capacity = 0;
        void* mapping = nullptr;
        unsigned mapped_width = 0;
        unsigned mapped_height = 0;
        int mapped_format = -1;
    };
    std::array<Slot, kRingSize> slots{};

    static constexpr size_t kSamples = 256;
    struct Timings {
        std::array<uint32_t, kSamples> values{};
        size_t count = 0;
        size_t next = 0;
        void add(uint64_t us) {
            values[next] = static_cast<uint32_t>(std::min<uint64_t>(us, UINT32_MAX));
            next = (next + 1) % values.size();
            count = std::min(count + 1, values.size());
        }
        uint32_t percentile(unsigned n, unsigned d) const {
            if (!count) return 0;
            auto sorted = values;
            std::sort(sorted.begin(), sorted.begin() + static_cast<std::ptrdiff_t>(count));
            const size_t rank = std::max<size_t>(1, (count * n + d - 1) / d);
            return sorted[std::min(count - 1, rank - 1)];
        }
    } upload_times, present_times;
    mutable std::mutex mutex;

    bool make_current() const {
        return display != EGL_NO_DISPLAY && surface != EGL_NO_SURFACE && context != EGL_NO_CONTEXT &&
               eglMakeCurrent(display, surface, surface, context) == EGL_TRUE;
    }

    void query_surface_size() {
        EGLint width = 0, height = 0;
        if (surface != EGL_NO_SURFACE) {
            eglQuerySurface(display, surface, EGL_WIDTH, &width);
            eglQuerySurface(display, surface, EGL_HEIGHT, &height);
        }
        surface_width = std::max(0, width);
        surface_height = std::max(0, height);
    }

    bool ensure_present_target(unsigned width, unsigned height) {
        if (!width || !height) return false;
        if (present_fbo && present_width >= width && present_height >= height) return true;
        if (present_texture) { glDeleteTextures(1, &present_texture); present_texture = 0; }
        if (present_fbo) { glDeleteFramebuffers(1, &present_fbo); present_fbo = 0; }
        present_width = std::max(1u, width);
        present_height = std::max(1u, height);
        glGenTextures(1, &present_texture);
        glBindTexture(GL_TEXTURE_2D, present_texture);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, static_cast<GLsizei>(present_width),
                     static_cast<GLsizei>(present_height), 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        glGenFramebuffers(1, &present_fbo);
        glBindFramebuffer(GL_FRAMEBUFFER, present_fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, present_texture, 0);
        const GLenum status = glCheckFramebufferStatus(GL_FRAMEBUFFER);
        glBindFramebuffer(GL_FRAMEBUFFER, 0);
        return status == GL_FRAMEBUFFER_COMPLETE;
    }

    bool slot_ready(size_t index) {
        Slot& slot = slots[index];
        if (!slot.fence) return true;
        const GLenum result = glClientWaitSync(slot.fence, 0, 0);
        if (result != GL_ALREADY_SIGNALED && result != GL_CONDITION_SATISFIED) return false;
        glDeleteSync(slot.fence);
        slot.fence = nullptr;
        return true;
    }

    bool reserve_slot() {
        if (active_slot < kRingSize) return true;
        if (!slot_ready(next_slot)) return false;
        active_slot = next_slot;
        next_slot = (next_slot + 1) % kRingSize;
        return true;
    }

    bool ensure_pbo(Slot& slot, size_t bytes) {
        glBindBuffer(GL_PIXEL_UNPACK_BUFFER, slot.pbo);
        if (slot.capacity >= bytes) return true;
        glBufferData(GL_PIXEL_UNPACK_BUFFER, static_cast<GLsizeiptr>(bytes), nullptr, GL_STREAM_DRAW);
        if (glGetError() != GL_NO_ERROR) return false;
        slot.capacity = bytes;
        return true;
    }

    void reset_active_slot() {
        if (active_slot < kRingSize) {
            Slot& slot = slots[active_slot];
            if (slot.mapping) {
                glBindBuffer(GL_PIXEL_UNPACK_BUFFER, slot.pbo);
                glUnmapBuffer(GL_PIXEL_UNPACK_BUFFER);
                slot.mapping = nullptr;
            }
            slot.mapped_width = slot.mapped_height = 0;
            slot.mapped_format = -1;
        }
        active_slot = kRingSize;
        frame_begun = false;
    }

    void shutdown() {
        if (display != EGL_NO_DISPLAY && context != EGL_NO_CONTEXT && surface != EGL_NO_SURFACE) make_current();
        for (auto& slot : slots) {
            if (slot.mapping) { glBindBuffer(GL_PIXEL_UNPACK_BUFFER, slot.pbo); glUnmapBuffer(GL_PIXEL_UNPACK_BUFFER); }
            if (slot.fence) glDeleteSync(slot.fence);
            if (slot.pbo) glDeleteBuffers(1, &slot.pbo);
            slot = {};
        }
        if (texture) glDeleteTextures(1, &texture);
        if (present_texture) glDeleteTextures(1, &present_texture);
        if (present_fbo) glDeleteFramebuffers(1, &present_fbo);
        if (vao) glDeleteVertexArrays(1, &vao);
        if (program) glDeleteProgram(program);
        texture = vao = program = present_texture = present_fbo = 0;
        present_width = present_height = 0;
        if (display != EGL_NO_DISPLAY) {
            eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
            if (context != EGL_NO_CONTEXT) eglDestroyContext(display, context);
            if (surface != EGL_NO_SURFACE) eglDestroySurface(display, surface);
            eglTerminate(display);
        }
        display = EGL_NO_DISPLAY; surface = EGL_NO_SURFACE; context = EGL_NO_CONTEXT;
        active = false; status.effective.clear();
    }
};

AndroidGles3Backend::AndroidGles3Backend() : impl_(std::make_unique<Impl>()) {}
AndroidGles3Backend::~AndroidGles3Backend() { shutdown(); }

bool AndroidGles3Backend::initialize(NativeWindowSurface& native_surface, std::string& error) {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->shutdown();
    impl_->status = {}; impl_->status.requested = "opengl"; impl_->status.frames_in_flight = kRingSize;
    auto* android_surface = dynamic_cast<AndroidWindowSurface*>(&native_surface);
    if (!android_surface || !android_surface->native_window()) {
        error = "gles3-initialize: Android ANativeWindow is unavailable";
        impl_->status.failure_stage = "gles3-native-window"; impl_->status.failure_reason = error; return false;
    }
    impl_->display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    EGLint major = 0, minor = 0;
    if (impl_->display == EGL_NO_DISPLAY || !eglInitialize(impl_->display, &major, &minor)) {
        error = "gles3-initialize: EGL display initialization failed"; goto fail;
    }
    if (!eglBindAPI(EGL_OPENGL_ES_API)) {
        error = "gles3-initialize: EGL could not select the OpenGL ES API"; goto fail;
    }
    {
        const EGLint attributes[] = {EGL_SURFACE_TYPE, EGL_WINDOW_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT,
                                     EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
                                     EGL_NONE};
        EGLConfig config = nullptr; EGLint count = 0;
        if (!eglChooseConfig(impl_->display, attributes, &config, 1, &count) || count != 1) {
            error = "gles3-initialize: no EGL OpenGL ES 3 window configuration"; goto fail;
        }
        impl_->surface = eglCreateWindowSurface(impl_->display, config, android_surface->native_window(), nullptr);
        const EGLint context_attributes[] = {EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE};
        impl_->context = eglCreateContext(impl_->display, config, EGL_NO_CONTEXT, context_attributes);
    }
    if (impl_->surface == EGL_NO_SURFACE || impl_->context == EGL_NO_CONTEXT || !impl_->make_current()) {
        error = "gles3-initialize: EGL surface or OpenGL ES 3 context creation failed"; goto fail;
    }
    {
        const char* vertex = "#version 300 es\nprecision mediump float;\nout vec2 uv;\nvoid main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);uv=vec2(p.x,1.0-p.y);gl_Position=vec4(p*2.0-1.0,0,1);}";
        const char* fragment = "#version 300 es\nprecision mediump float;\nin vec2 uv;uniform sampler2D frameTex;uniform bool swizzleBgr;out vec4 color;\nvoid main(){vec4 c=texture(frameTex,uv);color=swizzleBgr?vec4(c.bgr,1.0):c;}";
        GLuint vs = compile_shader(GL_VERTEX_SHADER, vertex, error);
        GLuint fs = vs ? compile_shader(GL_FRAGMENT_SHADER, fragment, error) : 0;
        if (!vs || !fs) { if (vs) glDeleteShader(vs); goto fail; }
        impl_->program = glCreateProgram(); glAttachShader(impl_->program, vs); glAttachShader(impl_->program, fs);
        glLinkProgram(impl_->program); glDeleteShader(vs); glDeleteShader(fs);
        GLint linked = GL_FALSE; glGetProgramiv(impl_->program, GL_LINK_STATUS, &linked);
        if (linked != GL_TRUE) { error = "gles3-program: shader program link failed"; goto fail; }
    }
    glGenVertexArrays(1, &impl_->vao);
    glGenTextures(1, &impl_->texture); glBindTexture(GL_TEXTURE_2D, impl_->texture);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR); glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE); glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    for (auto& slot : impl_->slots) glGenBuffers(1, &slot.pbo);
    impl_->status.device_details = std::string(reinterpret_cast<const char*>(glGetString(GL_VERSION)))+" / "+reinterpret_cast<const char*>(glGetString(GL_RENDERER))+" PBO=2 reused RGBA texture";
    impl_->swizzle_location = glGetUniformLocation(impl_->program, "swizzleBgr");
    if (glGetError() != GL_NO_ERROR) { error = "gles3-initialize: reusable GL resource creation failed"; goto fail; }
    eglSwapInterval(impl_->display, 1); impl_->query_surface_size();
    if (!impl_->ensure_present_target(static_cast<unsigned>(std::max(1, impl_->surface_width)),
                                      static_cast<unsigned>(std::max(1, impl_->surface_height)))) {
        error = "gles3-initialize: core presentation framebuffer creation failed"; goto fail;
    }
    impl_->active = true;
    impl_->status.effective = "opengl-es-3"; impl_->status.failure_stage.clear(); impl_->status.failure_reason.clear();
    return true;
fail:
    impl_->status.failure_stage = "gles3-initialize"; impl_->status.failure_reason = error; impl_->shutdown(); return false;
}

void AndroidGles3Backend::resize() {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    if (impl_->active && impl_->make_current()) impl_->query_surface_size();
}

bool AndroidGles3Backend::begin_frame() {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    if (!impl_->active || !impl_->make_current()) return false;
    if (impl_->frame_begun) return true;
    if (!impl_->reserve_slot()) { ++impl_->status.frames.dropped_frames; return false; }
    impl_->frame_begun = true;
    return true;
}

bool AndroidGles3Backend::acquire_software_framebuffer(unsigned width, unsigned height, int format,
                                                       void*& data, std::size_t& pitch) {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    data = nullptr; pitch = 0;
    if (!impl_->active || format != kPixelXrgb8888 || !impl_->make_current()) return false;
    if (!impl_->frame_begun && (!impl_->reserve_slot() || !(impl_->frame_begun = true))) return false;
    size_t bytes = 0; if (!valid_frame(width, height, 4, bytes)) return false;
    auto& slot = impl_->slots[impl_->active_slot];
    if (!impl_->ensure_pbo(slot, bytes)) return false;
    slot.mapping = glMapBufferRange(GL_PIXEL_UNPACK_BUFFER, 0, static_cast<GLsizeiptr>(bytes),
                                    GL_MAP_WRITE_BIT | GL_MAP_INVALIDATE_BUFFER_BIT);
    if (!slot.mapping) return false;
    slot.mapped_width = width; slot.mapped_height = height; slot.mapped_format = format;
    data = slot.mapping; pitch = static_cast<size_t>(width) * 4;
    return true;
}

void AndroidGles3Backend::present_software(const void* framebuffer, unsigned width, unsigned height,
                                           std::size_t pitch, int format) {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    if (!impl_->active || !impl_->make_current()) return;
    if (!impl_->frame_begun && (!impl_->reserve_slot() || !(impl_->frame_begun = true))) {
        ++impl_->status.frames.dropped_frames; return;
    }
    auto& slot = impl_->slots[impl_->active_slot];
    const bool direct = slot.mapping && framebuffer == slot.mapping && slot.mapped_width == width &&
                        slot.mapped_height == height && slot.mapped_format == format;
    size_t upload_bytes = 0;
    if (!valid_frame(width, height, 4, upload_bytes) || (!direct && !framebuffer)) {
        ++impl_->status.frames.dropped_frames; impl_->reset_active_slot(); return;
    }
    const auto upload_start = std::chrono::steady_clock::now();
    if (direct) {
        glBindBuffer(GL_PIXEL_UNPACK_BUFFER, slot.pbo);
        if (glUnmapBuffer(GL_PIXEL_UNPACK_BUFFER) != GL_TRUE) { slot.mapping = nullptr; ++impl_->status.frames.dropped_frames; impl_->reset_active_slot(); return; }
        slot.mapping = nullptr; ++impl_->status.frames.direct_software_uploads;
    } else {
        const size_t source_bpp = format == kPixelXrgb8888 ? 4u : 2u;
        size_t source_bytes = 0;
        if ((format != kPixelXrgb8888 && format != kPixel0Rgb1555 && format != kPixelRgb565) ||
            !valid_frame(width, height, source_bpp, source_bytes) || pitch < static_cast<size_t>(width) * source_bpp ||
            pitch > kMaxUploadBytes || (height > 1 && pitch > (std::numeric_limits<size_t>::max() - static_cast<size_t>(width) * source_bpp) / (height - 1)) ||
            !impl_->ensure_pbo(slot, upload_bytes)) {
            ++impl_->status.frames.dropped_frames; impl_->reset_active_slot(); return;
        }
        auto* destination = static_cast<uint8_t*>(glMapBufferRange(GL_PIXEL_UNPACK_BUFFER, 0, static_cast<GLsizeiptr>(upload_bytes),
                                                                   GL_MAP_WRITE_BIT | GL_MAP_INVALIDATE_BUFFER_BIT));
        if (!destination) { ++impl_->status.frames.dropped_frames; impl_->reset_active_slot(); return; }
        const auto* source = static_cast<const uint8_t*>(framebuffer);
        if (format == kPixelXrgb8888) {
            for (unsigned y = 0; y < height; ++y) std::memcpy(destination + static_cast<size_t>(y) * width * 4, source + static_cast<size_t>(y) * pitch, static_cast<size_t>(width) * 4);
            ++impl_->status.frames.copied_software_uploads;
        } else {
            for (unsigned y = 0; y < height; ++y) {
                const auto* row = reinterpret_cast<const uint16_t*>(source + static_cast<size_t>(y) * pitch);
                auto* out = destination + static_cast<size_t>(y) * width * 4;
                for (unsigned x = 0; x < width; ++x) {
                    const uint16_t value = row[x];
                    if (format == kPixelRgb565) {
                        out[4*x+0] = static_cast<uint8_t>(((value >> 11) & 31) * 255 / 31);
                        out[4*x+1] = static_cast<uint8_t>(((value >> 5) & 63) * 255 / 63);
                        out[4*x+2] = static_cast<uint8_t>((value & 31) * 255 / 31);
                    } else {
                        out[4*x+0] = static_cast<uint8_t>(((value >> 10) & 31) * 255 / 31);
                        out[4*x+1] = static_cast<uint8_t>(((value >> 5) & 31) * 255 / 31);
                        out[4*x+2] = static_cast<uint8_t>((value & 31) * 255 / 31);
                    }
                    out[4*x+3] = 255;
                }
            }
            ++impl_->status.frames.converted_software_uploads;
        }
        if (glUnmapBuffer(GL_PIXEL_UNPACK_BUFFER) != GL_TRUE) { ++impl_->status.frames.dropped_frames; impl_->reset_active_slot(); return; }
    }
    glBindTexture(GL_TEXTURE_2D, impl_->texture);
    if (impl_->texture_width != width || impl_->texture_height != height) {
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, static_cast<GLsizei>(width), static_cast<GLsizei>(height), 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
        impl_->texture_width = width; impl_->texture_height = height;
    }
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, static_cast<GLsizei>(width), static_cast<GLsizei>(height), GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
    ++impl_->status.frames.software_uploads;
    impl_->upload_times.add(static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - upload_start).count()));

    const auto present_start = std::chrono::steady_clock::now();
    impl_->query_surface_size();
    const double source_aspect = static_cast<double>(width) / height;
    const double surface_aspect = impl_->surface_height ? static_cast<double>(impl_->surface_width) / impl_->surface_height : source_aspect;
    int viewport_width = impl_->surface_width, viewport_height = impl_->surface_height;
    if (surface_aspect > source_aspect) viewport_width = static_cast<int>(viewport_height * source_aspect + 0.5);
    else viewport_height = static_cast<int>(viewport_width / source_aspect + 0.5);
    glViewport(0, 0, impl_->surface_width, impl_->surface_height); glClearColor(0, 0, 0, 1); glClear(GL_COLOR_BUFFER_BIT);
    glViewport((impl_->surface_width - viewport_width) / 2, (impl_->surface_height - viewport_height) / 2, viewport_width, viewport_height);
    glUseProgram(impl_->program); glUniform1i(impl_->swizzle_location, format == kPixelXrgb8888 ? GL_TRUE : GL_FALSE);
    glBindVertexArray(impl_->vao); glDrawArrays(GL_TRIANGLES, 0, 3);
    glBindBuffer(GL_PIXEL_UNPACK_BUFFER, 0);
    if (glGetError() != GL_NO_ERROR || eglSwapBuffers(impl_->display, impl_->surface) != EGL_TRUE) {
        ++impl_->status.frames.dropped_frames; impl_->reset_active_slot(); return;
    }
    slot.fence = glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0); glFlush();
    ++impl_->status.frames.presented_frames;
    impl_->present_times.add(static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - present_start).count()));
    impl_->reset_active_slot();
}

bool AndroidGles3Backend::receive_native_gpu_frame(const void*, std::string& error) {
    error = "hardware-frame: OpenGL ES fallback unsupported without a negotiated libretro GLES context";
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->status.failure_stage = "gles3-hardware-frame"; impl_->status.failure_reason = error;
    return false;
}

void AndroidGles3Backend::present_native_gpu_frame(unsigned, unsigned) {}

// Azahar's OpenGL ES renderer draws into the frontend framebuffer (0) through
// the EGL context this backend already owns; the core resolves its entries via
// eglGetProcAddress. Presenting is a single buffer swap.
void* AndroidGles3Backend::gl_proc_address(const char* name) const {
    if (!name) return nullptr;
    return reinterpret_cast<void*>(eglGetProcAddress(name));
}

unsigned AndroidGles3Backend::gl_current_framebuffer() const {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    if (!impl_->active) return 0;
    if (!impl_->present_fbo) {
        if (!impl_->ensure_present_target(static_cast<unsigned>(std::max(1, impl_->surface_width)),
                                          static_cast<unsigned>(std::max(1, impl_->surface_height)))) return 0;
    }
    return impl_->present_fbo;
}

bool AndroidGles3Backend::present_gl_frame(unsigned width, unsigned height) {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    if (!impl_->active || !width || !height) return false;
    if (impl_->display == EGL_NO_DISPLAY || impl_->surface == EGL_NO_SURFACE) return false;
    const auto started = std::chrono::steady_clock::now();
    if (!impl_->make_current()) return false;
    impl_->query_surface_size();
    const unsigned window_width = static_cast<unsigned>(std::max(1, impl_->surface_width));
    const unsigned window_height = static_cast<unsigned>(std::max(1, impl_->surface_height));
    // The core renders its layout into the frontend FBO's lower-left corner.
    // Fit that region into the window with centered letterboxing and swap.
    if (!impl_->ensure_present_target(std::max(window_width, width), std::max(window_height, height))) return false;
    const double scale = std::min(static_cast<double>(window_width) / width,
                                  static_cast<double>(window_height) / height);
    const int target_width = std::max(1, static_cast<int>(width * scale));
    const int target_height = std::max(1, static_cast<int>(height * scale));
    const int target_x = (static_cast<int>(window_width) - target_width) / 2;
    const int target_y = (static_cast<int>(window_height) - target_height) / 2;
    glBindFramebuffer(GL_READ_FRAMEBUFFER, impl_->present_fbo);
    glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0);
    glViewport(0, 0, static_cast<GLsizei>(window_width), static_cast<GLsizei>(window_height));
    glClearColor(0.0f, 0.0f, 0.0f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT);
    glBlitFramebuffer(0, 0, static_cast<GLint>(width), static_cast<GLint>(height),
                      target_x, target_y, target_x + target_width, target_y + target_height,
                      GL_COLOR_BUFFER_BIT, GL_LINEAR);
    eglSwapBuffers(impl_->display, impl_->surface);
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    impl_->present_times.add(static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - started).count()));
    impl_->status.frames.presented_frames += 1;
    return true;
}

NativeVideoStatus AndroidGles3Backend::metrics() const {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    auto result = impl_->status;
    result.frames.upload_p95_us = impl_->upload_times.percentile(95, 100);
    result.frames.upload_p99_us = impl_->upload_times.percentile(99, 100);
    result.frames.present_p95_us = impl_->present_times.percentile(95, 100);
    result.frames.present_p99_us = impl_->present_times.percentile(99, 100);
    return result;
}

void AndroidGles3Backend::shutdown() {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->shutdown();
}

} // namespace an3
