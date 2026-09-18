// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#include "libretro_host.h"

#include "core_options.h"
#include "vendor/libretro.h"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <limits>
#include <mutex>
#include <sstream>
#include <utility>

#if defined(_WIN32)
#include <windows.h>
#else
#include <dlfcn.h>
#include <fcntl.h>
#include <unistd.h>
#endif

#if defined(__ANDROID__)
#include <android/log.h>
#endif

namespace an3 {
namespace {

constexpr std::uintmax_t kMaxStateBytes = 64u * 1024u * 1024u;
constexpr std::uintmax_t kMaxRomBytes = 512ull * 1024u * 1024u;
constexpr unsigned kMaxStateSlot = 10;

class DynamicLibrary {
public:
    bool open(const std::string& path, std::string& error) {
#if defined(_WIN32)
        handle_ = LoadLibraryW(std::filesystem::path(path).c_str());
        if (!handle_) error = "Could not load the native libretro core.";
#else
        handle_ = dlopen(path.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!handle_) { const char* detail=dlerror(); error=detail?detail:"Could not load the native libretro core."; }
#endif
        return handle_ != nullptr;
    }
    void close() {
        if (!handle_) return;
#if defined(_WIN32)
        FreeLibrary(static_cast<HMODULE>(handle_));
#else
        dlclose(handle_);
#endif
        handle_ = nullptr;
    }
    void* symbol(const char* name) const {
#if defined(_WIN32)
        return reinterpret_cast<void*>(GetProcAddress(static_cast<HMODULE>(handle_), name));
#else
        return dlsym(handle_, name);
#endif
    }
    ~DynamicLibrary() { close(); }
private:
    void* handle_ = nullptr;
};

struct CoreApi {
#define AN3_CORE_FN(name) decltype(&::name) name = nullptr
    AN3_CORE_FN(retro_set_environment);
    AN3_CORE_FN(retro_set_video_refresh);
    AN3_CORE_FN(retro_set_audio_sample);
    AN3_CORE_FN(retro_set_audio_sample_batch);
    AN3_CORE_FN(retro_set_input_poll);
    AN3_CORE_FN(retro_set_input_state);
    AN3_CORE_FN(retro_init);
    AN3_CORE_FN(retro_deinit);
    AN3_CORE_FN(retro_api_version);
    AN3_CORE_FN(retro_get_system_info);
    AN3_CORE_FN(retro_get_system_av_info);
    AN3_CORE_FN(retro_set_controller_port_device);
    AN3_CORE_FN(retro_reset);
    AN3_CORE_FN(retro_run);
    AN3_CORE_FN(retro_serialize_size);
    AN3_CORE_FN(retro_serialize);
    AN3_CORE_FN(retro_unserialize);
    AN3_CORE_FN(retro_cheat_reset);
    AN3_CORE_FN(retro_cheat_set);
    AN3_CORE_FN(retro_load_game);
    AN3_CORE_FN(retro_load_game_special);
    AN3_CORE_FN(retro_unload_game);
    AN3_CORE_FN(retro_get_region);
    AN3_CORE_FN(retro_get_memory_data);
    AN3_CORE_FN(retro_get_memory_size);
#undef AN3_CORE_FN

    bool load(const DynamicLibrary& library, std::string& error) {
#define AN3_LOAD(name) do { name = reinterpret_cast<decltype(name)>(library.symbol(#name)); \
        if (!name) { error = std::string("Native core is missing required symbol: ") + #name; return false; } } while (false)
        AN3_LOAD(retro_set_environment); AN3_LOAD(retro_set_video_refresh);
        AN3_LOAD(retro_set_audio_sample); AN3_LOAD(retro_set_audio_sample_batch);
        AN3_LOAD(retro_set_input_poll); AN3_LOAD(retro_set_input_state);
        AN3_LOAD(retro_init); AN3_LOAD(retro_deinit); AN3_LOAD(retro_api_version);
        AN3_LOAD(retro_get_system_info); AN3_LOAD(retro_get_system_av_info);
        AN3_LOAD(retro_set_controller_port_device); AN3_LOAD(retro_reset); AN3_LOAD(retro_run);
        AN3_LOAD(retro_serialize_size); AN3_LOAD(retro_serialize); AN3_LOAD(retro_unserialize);
        AN3_LOAD(retro_cheat_reset); AN3_LOAD(retro_cheat_set); AN3_LOAD(retro_load_game);
        AN3_LOAD(retro_load_game_special); AN3_LOAD(retro_unload_game); AN3_LOAD(retro_get_region);
        AN3_LOAD(retro_get_memory_data); AN3_LOAD(retro_get_memory_size);
#undef AN3_LOAD
        return true;
    }
};

std::string stable_rom_id(const std::filesystem::path& path) {
    std::string name = path.stem().string();
    for (char& c : name) {
        const unsigned char value = static_cast<unsigned char>(c);
        if (!std::isalnum(value) && c != '-' && c != '_') c = '_';
    }
    if (name.empty()) name = "game";
    std::uint64_t hash = 1469598103934665603ull;
    const std::string identity = std::filesystem::absolute(path).lexically_normal().string();
    for (unsigned char c : identity) { hash ^= c; hash *= 1099511628211ull; }
    std::ostringstream suffix;
    suffix << std::hex << hash;
    return name.substr(0, 80) + "-" + suffix.str();
}

NativeSystem detect_system(const std::filesystem::path& rom) {
    std::string extension=rom.extension().string();
    std::transform(extension.begin(),extension.end(),extension.begin(),[](unsigned char c){return static_cast<char>(std::tolower(c));});
    if(extension==".gba") return NativeSystem::GBA;
    if(extension==".nds" || extension==".dsi") return NativeSystem::NDS;
    if(extension==".3ds" || extension==".3dsx" || extension==".cci" || extension==".cxi" || extension==".app") return NativeSystem::ThreeDS;
    return NativeSystem::Unknown;
}

bool read_bounded(const std::filesystem::path& path, std::vector<std::uint8_t>& bytes,
                  std::string& error) {
    std::error_code ec;
    const auto size = std::filesystem::file_size(path, ec);
    if (ec || size == 0 || size > kMaxStateBytes || size > std::numeric_limits<std::size_t>::max()) {
        error = "The save state is empty, unreadable, or exceeds the 64 MiB safety limit.";
        return false;
    }
    std::ifstream input(path, std::ios::binary);
    bytes.resize(static_cast<std::size_t>(size));
    if (!input.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()))) {
        bytes.clear(); error = "Could not read the complete save state."; return false;
    }
    return true;
}

bool write_atomic(const std::filesystem::path& path, const std::vector<std::uint8_t>& bytes,
                  std::string& error) {
    std::error_code ec;
    std::filesystem::create_directories(path.parent_path(), ec);
    if (ec) { error = "Could not prepare native save-state storage."; return false; }
    const auto temporary = path.string() + ".tmp";
    {
        std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
        output.write(reinterpret_cast<const char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
        output.flush();
        if (!output) { output.close(); std::filesystem::remove(temporary, ec); error = "Could not write the save state."; return false; }
    }
#if !defined(_WIN32)
    const int fd = ::open(temporary.c_str(), O_RDONLY);
    if (fd >= 0) { (void)::fsync(fd); (void)::close(fd); }
#endif
    std::filesystem::rename(temporary, path, ec);
#if defined(_WIN32)
    if (ec) { ec.clear(); std::filesystem::remove(path, ec); ec.clear(); std::filesystem::rename(temporary, path, ec); }
#endif
    if (ec) { std::filesystem::remove(temporary, ec); error = "Could not atomically finish the save state."; return false; }
    return true;
}

} // namespace

class NativeCoreHost::Impl {
public:
    bool initialize(const std::string& core_path, const std::string& rom_path,
                    const std::string& save_directory, NativeVideoBackend& video,
                    NativeAudioBackend& audio, std::string& error, const std::string& nds_layout,
                    const std::string& graphics_api);
    bool run_one(std::string& error, bool present);
    void shutdown();
    void shutdown_locked();
    bool state(bool save, const std::filesystem::path& path, std::string& error);
    bool environment(unsigned command, void* data);
    void video(const void* data, unsigned width, unsigned height, std::size_t pitch);
    int16_t input_state(unsigned port, unsigned device, unsigned index, unsigned id) const;

    static bool RETRO_CALLCONV environment_cb(unsigned c, void* d) { return active_ && active_->environment(c, d); }
    static void RETRO_CALLCONV video_cb(const void* d, unsigned w, unsigned h, std::size_t p) { if (active_) active_->video(d,w,h,p); }
    static void RETRO_CALLCONV audio_cb(int16_t l, int16_t r) { const int16_t pair[]{l,r}; if (active_ && active_->audio_ready_) active_->audio_->submit(pair,1); }
    static std::size_t RETRO_CALLCONV audio_batch_cb(const int16_t* d, std::size_t n) { return active_ && active_->audio_ready_ ? active_->audio_->submit(d,n) : n; }
    static void RETRO_CALLCONV input_poll_cb() {}
    static int16_t RETRO_CALLCONV input_state_cb(unsigned p,unsigned d,unsigned i,unsigned id) { return active_ ? active_->input_state(p,d,i,id) : 0; }
    // The core's own diagnostics (unimplemented features, texture/shader
    // errors) must not be discarded: on Android they are the only view into
    // the vendored core's behaviour. Forward them to logcat (tag AzaharCore)
    // and to stderr on the other platforms.
    static void RETRO_CALLCONV log_cb(enum retro_log_level level, const char* format, ...) {
        if (!format) return;
        char message[1024] = {};
        va_list args;
        va_start(args, format);
        std::vsnprintf(message, sizeof(message), format, args);
        va_end(args);
#if defined(__ANDROID__)
        int priority = ANDROID_LOG_DEBUG;
        switch (level) {
        case RETRO_LOG_DEBUG: priority = ANDROID_LOG_DEBUG; break;
        case RETRO_LOG_INFO: priority = ANDROID_LOG_INFO; break;
        case RETRO_LOG_WARN: priority = ANDROID_LOG_WARN; break;
        case RETRO_LOG_ERROR: priority = ANDROID_LOG_ERROR; break;
        default: break;
        }
        __android_log_print(priority, "AzaharCore", "%s", message);
#else
        (void)level;
        std::fprintf(stderr, "%s\n", message);
#endif
    }
    // Frontend callbacks the core uses when it negotiates an OpenGL ES context.
    // The core renders into the default framebuffer; entries resolve through
    // the platform GL loader owned by the video backend.
    static uintptr_t RETRO_CALLCONV gl_current_framebuffer_cb() {
        return active_ && active_->video_ ? active_->video_->gl_current_framebuffer() : 0;
    }
    static retro_proc_address_t RETRO_CALLCONV gl_proc_address_cb(const char* name) {
        auto* address = active_ && active_->video_ ? active_->video_->gl_proc_address(name) : nullptr;
        return reinterpret_cast<retro_proc_address_t>(address);
    }

    mutable std::mutex mutex_;
    DynamicLibrary library_;
    CoreApi core_;
    NativeVideoBackend* video_ = nullptr;
    NativeAudioBackend* audio_ = nullptr;
    NativeInput input_;
    CoreOptionsRegistry options_;
    std::string core_path_, rom_path_, save_path_, system_path_, content_path_, message_, rom_id_;
    std::vector<std::uint8_t> rom_data_;
    std::atomic<std::int64_t> frame_duration_ns_{16666667};
    std::atomic<std::uint64_t> core_frames_{0};
    NativeSystem system_ = NativeSystem::Unknown;
    std::string core_name_, core_version_;
    std::string nds_layout_="top-bottom";
    // Which Azahar graphics API the core must request. Android can select
    // OpenGL ES because some Adreno drivers abort on the core's Vulkan
    // pipeline creation (VK_ERROR_UNKNOWN -> uncaught exception).
    std::string graphics_api_="Vulkan";
    bool gl_hardware_ = false;
    RetroHwRenderCallback hardware_callbacks_{};
    const void* hardware_negotiation_interface_ = nullptr;
    bool has_hardware_callbacks_ = false;
    bool hardware_context_ready_ = false;
    double core_fps_ = 0.0;
    bool hardware_render_rejected_ = false;
    unsigned pixel_format_ = RETRO_PIXEL_FORMAT_RGB565;
    unsigned last_width_ = 0, last_height_ = 0;
    bool initialized_ = false, loaded_ = false;
    bool audio_ready_ = false;
    bool present_frame_ = true;
    uint32_t sampled_buttons_=0;
    bool sampled_pointer_pressed_=false;
    int16_t sampled_pointer_x_=0,sampled_pointer_y_=0;
    std::atomic<bool> running_{false};
    static Impl* active_;
};

NativeCoreHost::Impl* NativeCoreHost::Impl::active_ = nullptr;

bool NativeCoreHost::Impl::initialize(const std::string& core_path, const std::string& rom_path,
                                      const std::string& save_directory, NativeVideoBackend& video,
                                      NativeAudioBackend& audio, std::string& error, const std::string& nds_layout,
                                      const std::string& graphics_api) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (running_) { error = "A native core is already running in this host."; return false; }
    if (active_ && active_ != this) { error = "Only one libretro core may be active in this process."; return false; }
    if (core_path.empty() || rom_path.empty() || save_directory.empty()) { error = "Core, ROM, and native save paths are required."; return false; }
    core_path_ = core_path; rom_path_ = rom_path;
    graphics_api_ = graphics_api;
    nds_layout_=nds_layout == "left-right" ? "left-right" : "top-bottom";
    system_ = detect_system(rom_path_);
    content_path_ = std::filesystem::path(rom_path_).parent_path().string();
    save_path_ = (std::filesystem::path(save_directory) / "native-libretro").string();
    system_path_ = (std::filesystem::path(save_path_) / "system").string();
    rom_id_ = stable_rom_id(rom_path_);
    std::error_code ec;
    std::filesystem::create_directories(system_path_, ec);
    std::filesystem::create_directories(std::filesystem::path(save_path_) / "states", ec);
    if (ec) { error = "Could not prepare isolated native runtime storage."; return false; }
    if (!library_.open(core_path_, error) || !core_.load(library_, error)) { library_.close(); return false; }
    if (core_.retro_api_version() != RETRO_API_VERSION) { error = "The native core uses an incompatible libretro API version."; library_.close(); return false; }
    active_ = this; video_ = &video; audio_ = &audio;
    options_.reset(std::filesystem::path(core_path_).stem().string());
    core_.retro_set_environment(environment_cb); core_.retro_set_video_refresh(video_cb);
    core_.retro_set_audio_sample(audio_cb); core_.retro_set_audio_sample_batch(audio_batch_cb);
    core_.retro_set_input_poll(input_poll_cb); core_.retro_set_input_state(input_state_cb);
    core_.retro_init(); initialized_ = true;
    // Some melonDS builds snapshot these announced options during load_game.
    // GET_VARIABLE also enforces the values for legacy option declarations.
    (void)options_.set("melonds_render_mode", "software");
    (void)options_.set("melonds_threaded_renderer", "enabled");
    (void)options_.set("melonds_touch_mode", "touch");
    (void)options_.set("melonds_show_cursor", "always");
    (void)options_.set("melonds_number_of_screen_layouts", "1");
    (void)options_.set("melonds_screen_layout1", nds_layout_);
    retro_system_info info{}; core_.retro_get_system_info(&info);
    core_name_ = info.library_name ? info.library_name : "Unknown libretro core";
    core_version_ = info.library_version ? info.library_version : "";
    retro_game_info game{rom_path_.c_str(), nullptr, 0, nullptr};
    if (!info.need_fullpath) {
        std::ifstream input(rom_path_, std::ios::binary | std::ios::ate);
        const auto size = input ? input.tellg() : std::streampos(-1);
        if (size <= 0 || static_cast<std::uintmax_t>(size) > kMaxRomBytes || static_cast<std::uintmax_t>(size) > std::numeric_limits<std::size_t>::max()) { error = "The selected ROM is empty or exceeds the 512 MiB native loading limit."; shutdown_locked(); return false; }
        input.seekg(0); rom_data_.resize(static_cast<std::size_t>(size));
        if (!input.read(reinterpret_cast<char*>(rom_data_.data()), static_cast<std::streamsize>(rom_data_.size()))) { error = "Could not read the complete ROM."; shutdown_locked(); return false; }
        game.data = rom_data_.data(); game.size = rom_data_.size();
    }
    if (!core_.retro_load_game(&game)) { error = message_.empty() ? "The native core rejected this ROM or requested unsupported hardware rendering." : message_; shutdown_locked(); return false; }
    loaded_ = true;
    if (system_ == NativeSystem::ThreeDS) {
        if (gl_hardware_) {
            // OpenGL ES: the backend already owns the EGL context, so the core
            // only needs context_reset to load its GL entry points.
            if (!hardware_callbacks_.context_reset) {
                error = "Azahar did not provide an OpenGL context-reset callback.";
                shutdown_locked();
                return false;
            }
            hardware_callbacks_.context_reset();
            hardware_context_ready_ = true;
        } else if (has_hardware_callbacks_ && hardware_negotiation_interface_) {
            NativeHardwareRenderRequest request{};
            request.callbacks = hardware_callbacks_;
            request.negotiation_interface = hardware_negotiation_interface_;
            if (!video_->initialize_hardware_renderer(request, error)) {
                shutdown_locked();
                return false;
            }
            if (!hardware_callbacks_.context_reset) {
                error = "Azahar did not provide a Vulkan context-reset callback.";
                shutdown_locked();
                return false;
            }
            hardware_callbacks_.context_reset();
            hardware_context_ready_ = true;
        } else {
            error = "The Azahar core did not negotiate its required renderer.";
            shutdown_locked();
            return false;
        }
    }
    retro_system_av_info av{}; core_.retro_get_system_av_info(&av);
    if (!std::isfinite(av.timing.fps) || av.timing.fps <= 1.0 || av.timing.fps > 1000.0) { error = "The native core reported an invalid frame rate."; shutdown_locked(); return false; }
    core_fps_=av.timing.fps;
    frame_duration_ns_.store(static_cast<std::int64_t>(1000000000.0 / av.timing.fps), std::memory_order_relaxed);
    core_frames_.store(0,std::memory_order_relaxed);
    if (!audio.initialize(av.timing.sample_rate, error)) { shutdown_locked(); return false; }
    audio_ready_ = true;
    running_ = true;
    return true;
}

bool NativeCoreHost::Impl::run_one(std::string& error, bool present) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!running_) { error = "No native core is running."; return false; }
    // Frame pacing belongs to the adapter. A temporarily unavailable present
    // target may drop presentation, but must not turn core timing into vsync.
    present_frame_ = present;
    if (present_frame_) (void)video_->begin_frame();
    // Preserve a completed short native tap for one core frame. Sampling
    // here keeps all input queries within that frame consistent.
    sampled_buttons_=input_.buttons_.load(std::memory_order_acquire) | input_.pending_buttons_.exchange(0,std::memory_order_acq_rel);
    const bool pending_pointer=input_.pending_pointer_.exchange(false,std::memory_order_acq_rel);
    sampled_pointer_pressed_=pending_pointer || input_.pointer_pressed_.load(std::memory_order_acquire);
    sampled_pointer_x_=input_.pointer_x_.load(std::memory_order_relaxed);
    sampled_pointer_y_=input_.pointer_y_.load(std::memory_order_relaxed);
    core_.retro_run();
    core_frames_.fetch_add(1,std::memory_order_relaxed);
    return true;
}

void NativeCoreHost::Impl::shutdown() {
    std::lock_guard<std::mutex> lock(mutex_);
    shutdown_locked();
}

void NativeCoreHost::Impl::shutdown_locked() {
    running_ = false;
    if (hardware_context_ready_ && hardware_callbacks_.context_destroy) hardware_callbacks_.context_destroy();
    hardware_context_ready_ = false;
    if (loaded_) core_.retro_unload_game();
    loaded_ = false;
    if (initialized_) core_.retro_deinit();
    initialized_ = false;
    if (audio_ready_ && audio_) audio_->shutdown();
    audio_ready_ = false;
    if (active_ == this) active_ = nullptr;
    library_.close(); core_ = {}; video_ = nullptr; audio_ = nullptr;
    rom_data_.clear(); options_.reset({}); input_.clear();
    hardware_callbacks_ = {};
    hardware_negotiation_interface_ = nullptr;
    has_hardware_callbacks_ = false;
    gl_hardware_ = false;
}

bool NativeCoreHost::Impl::state(bool save, const std::filesystem::path& path, std::string& error) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!running_) { error = "No native core is running."; return false; }
    if (save) {
        const std::size_t size = core_.retro_serialize_size();
        if (!size || size > kMaxStateBytes) { error = "The core reported an invalid save-state size."; return false; }
        std::vector<std::uint8_t> bytes(size);
        if (!core_.retro_serialize(bytes.data(), bytes.size())) { error = "The core could not create a save state."; return false; }
        return write_atomic(path, bytes, error);
    }
    std::vector<std::uint8_t> bytes;
    if (!read_bounded(path, bytes, error)) return false;
    if (!core_.retro_unserialize(bytes.data(), bytes.size())) { error = "The core rejected this incompatible save state."; return false; }
    return true;
}

bool NativeCoreHost::Impl::environment(unsigned command, void* data) {
    switch (command) {
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY: if(!data)return false; *static_cast<const char**>(data) = system_path_.c_str(); return true;
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY: if(!data)return false; *static_cast<const char**>(data) = save_path_.c_str(); return true;
    case RETRO_ENVIRONMENT_GET_CONTENT_DIRECTORY: if(!data)return false; *static_cast<const char**>(data) = content_path_.c_str(); return true;
    case RETRO_ENVIRONMENT_GET_LIBRETRO_PATH: if(!data)return false; *static_cast<const char**>(data) = core_path_.c_str(); return true;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT: {
        if (!data) return false;
        const auto format = *static_cast<const enum retro_pixel_format*>(data);
        if (format != RETRO_PIXEL_FORMAT_0RGB1555 && format != RETRO_PIXEL_FORMAT_XRGB8888 && format != RETRO_PIXEL_FORMAT_RGB565) return false;
        pixel_format_ = format; return true;
    }
    case RETRO_ENVIRONMENT_GET_VARIABLE: {
        auto* variable = static_cast<retro_variable*>(data); if (!variable || !variable->key) return false;
        if (system_ == NativeSystem::ThreeDS && !std::strcmp(variable->key, "citra_graphics_api")) variable->value=graphics_api_.c_str();
        else if (system_ == NativeSystem::ThreeDS && !std::strcmp(variable->key, "citra_layout_option")) variable->value=nds_layout_ == "left-right" ? "side_by_side" : "top_bottom";
#if defined(__ANDROID__)
        // The Azahar core's OpenGL ES hardware-shader path renders 3D content
        // black on Adreno GPUs. Verified on a Redmi 15 5G (Adreno 619) with
        // Pokemon X Quick Save Slot 1: the identical draw calls render
        // correctly through the software PICA shader interpreter, so the
        // defect is in the GLES hardware-shader codegen/execution - not in the
        // texture uploads, the PICA texture state, the core framebuffer, the
        // shader disk cache (disabling it still renders black) or the frontend
        // presentation. Android is the only platform that runs the core's
        // OpenGL renderer (every desktop build uses its Vulkan renderer), so
        // pin the PICA shader path to the faithful software implementation
        // there until the upstream GLES generator is fixed.
        else if (system_ == NativeSystem::ThreeDS && !std::strcmp(variable->key, "citra_use_hw_shader")) variable->value="disabled";
        // RG-081: on the Vulkan renderer a persisted core shader/pipeline cache
        // makes Adreno's driver compiler fail, so vkCreateGraphicsPipelines
        // returns VK_ERROR_UNKNOWN, vulkan-hpp throws vk::UnknownError and the
        // uncaught exception aborts the game process. The on-disk driver
        // pipeline cache is only validated against the driver UUID, so it is
        // reused after any frontend/core change and goes stale. Keep the
        // renderer off that cache until the core invalidates it itself.
        else if (system_ == NativeSystem::ThreeDS && graphics_api_ == "Vulkan" &&
                 !std::strcmp(variable->key, "citra_use_disk_shader_cache")) variable->value="disabled";
#endif
        else if (!std::strcmp(variable->key,"melonds_render_mode")) variable->value="software";

        else if (!std::strcmp(variable->key,"melonds_touch_mode")) variable->value="touch";

        else if (!std::strcmp(variable->key,"melonds_number_of_screen_layouts")) variable->value="1";
        else if (!std::strcmp(variable->key,"melonds_screen_layout1")) variable->value=nds_layout_.c_str();
        else return options_.get(variable->key, variable->value);
        return true;
    }
    case RETRO_ENVIRONMENT_SET_VARIABLES: {
        auto* vars=static_cast<retro_variable*>(data); if (!vars) return false; std::vector<const char*> pairs;
        for (;vars->key;++vars) { pairs.push_back(vars->key); pairs.push_back(vars->value); } pairs.push_back(nullptr); options_.capture_legacy_variables(pairs.data()); return true;
    }
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2: options_.capture_v2(reinterpret_cast<const RetroCoreOptionsV2*>(data)); return true;
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2_INTL: {
        auto* intl=reinterpret_cast<const RetroCoreOptionsIntl*>(data); if (intl) options_.capture_v2(intl->us ? intl->us : intl->local); return true;
    }
    case RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION: *static_cast<unsigned*>(data)=2; return true;
    case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE: *static_cast<bool*>(data)=options_.consume_update(); return true;
    case RETRO_ENVIRONMENT_GET_CAN_DUPE: if(!data)return false; *static_cast<bool*>(data)=true; return true;
    case RETRO_ENVIRONMENT_GET_INPUT_BITMASKS: return true;
    case RETRO_ENVIRONMENT_GET_CURRENT_SOFTWARE_FRAMEBUFFER: {
        if (!present_frame_) return false;
        auto* fb=static_cast<retro_framebuffer*>(data); if (!fb || !(fb->access_flags & RETRO_MEMORY_ACCESS_WRITE)) return false;
        void* mapped=nullptr; std::size_t pitch=0; if (!video_->acquire_software_framebuffer(fb->width,fb->height,pixel_format_,mapped,pitch)) return false;
        fb->data=mapped; fb->pitch=pitch; fb->format=static_cast<retro_pixel_format>(pixel_format_); fb->memory_flags=RETRO_MEMORY_TYPE_CACHED; return true;
    }
    case RETRO_ENVIRONMENT_SET_HW_RENDER: {
        if (system_ != NativeSystem::ThreeDS || !data) return false;
        auto* callbacks = const_cast<retro_hw_render_callback*>(static_cast<const retro_hw_render_callback*>(data));
        const bool gl_context = callbacks->context_type == RETRO_HW_CONTEXT_OPENGLES3 ||
                                callbacks->context_type == RETRO_HW_CONTEXT_OPENGLES2 ||
                                callbacks->context_type == RETRO_HW_CONTEXT_OPENGL ||
                                callbacks->context_type == RETRO_HW_CONTEXT_OPENGL_CORE;
        if (!gl_context && callbacks->context_type != RETRO_HW_CONTEXT_VULKAN) {
            hardware_render_rejected_ = true;
            message_ = "Azahar requested an unsupported hardware context.";
            return false;
        }
        if (gl_context) {
            // The frontend owns the GL context; the core renders into the
            // default framebuffer and resolves its GL entries through us.
            callbacks->get_current_framebuffer = &Impl::gl_current_framebuffer_cb;
            callbacks->get_proc_address = &Impl::gl_proc_address_cb;
            gl_hardware_ = true;
        }
        hardware_callbacks_.context_type = callbacks->context_type;
        hardware_callbacks_.context_reset = callbacks->context_reset;
        hardware_callbacks_.get_current_framebuffer = callbacks->get_current_framebuffer;
        hardware_callbacks_.get_proc_address = reinterpret_cast<RetroHwGetProcAddress>(callbacks->get_proc_address);
        hardware_callbacks_.depth = callbacks->depth;
        hardware_callbacks_.stencil = callbacks->stencil;
        hardware_callbacks_.bottom_left_origin = callbacks->bottom_left_origin;
        hardware_callbacks_.version_major = callbacks->version_major;
        hardware_callbacks_.version_minor = callbacks->version_minor;
        hardware_callbacks_.cache_context = callbacks->cache_context;
        hardware_callbacks_.context_destroy = callbacks->context_destroy;
        hardware_callbacks_.debug_context = callbacks->debug_context;
        has_hardware_callbacks_ = true;
        return true;
    }
    case RETRO_ENVIRONMENT_SET_HW_RENDER_CONTEXT_NEGOTIATION_INTERFACE:
        if (system_ != NativeSystem::ThreeDS || !data) return false;
        // Azahar follows RetroArch's v1 convention: data is the interface
        // struct, rather than a pointer to a pointer.
        hardware_negotiation_interface_ = data;
        return true;
    case RETRO_ENVIRONMENT_GET_HW_RENDER_INTERFACE:
        if (system_ != NativeSystem::ThreeDS || !data) return false;
        *static_cast<void**>(data) = video_ ? video_->hardware_render_interface() : nullptr;
        return *static_cast<void**>(data) != nullptr;
    case RETRO_ENVIRONMENT_GET_HW_RENDER_CONTEXT_NEGOTIATION_INTERFACE_SUPPORT:
        // Azahar 2126's stable v1 create-device interface is provided by the
        // stored negotiation payload above. Do not claim an incomplete v2 ABI.
        return false;
    case RETRO_ENVIRONMENT_GET_PREFERRED_HW_RENDER: return false;
    case RETRO_ENVIRONMENT_SET_MESSAGE: { auto* m=static_cast<retro_message*>(data); if(m&&m->msg) message_=m->msg; return true; }
    case RETRO_ENVIRONMENT_SET_MESSAGE_EXT: { auto* m=static_cast<retro_message_ext*>(data); if(m&&m->msg) message_=m->msg; return true; }
    case RETRO_ENVIRONMENT_GET_LOG_INTERFACE: static_cast<retro_log_callback*>(data)->log=log_cb; return true;
    case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
    case RETRO_ENVIRONMENT_SET_CONTROLLER_INFO:
    case RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME:
    case RETRO_ENVIRONMENT_SET_SERIALIZATION_QUIRKS:
    case RETRO_ENVIRONMENT_SET_GEOMETRY: return true;
    default: return false;
    }
}

void NativeCoreHost::Impl::video(const void* data, unsigned width, unsigned height, std::size_t pitch) {
    if (!video_ || !present_frame_) return;
    if (data == RETRO_HW_FRAME_BUFFER_VALID) {
        if (system_ != NativeSystem::ThreeDS || !hardware_context_ready_) {
            message_="Hardware frame arrived without an active native context.";
            return;
        }
        last_width_=width; last_height_=height;
        if (gl_hardware_) video_->present_gl_frame(width,height);
        else video_->present_native_gpu_frame(width,height);
        return;
    }
    if (!data) { if (last_width_ && last_height_) video_->present_software(nullptr,last_width_,last_height_,0,pixel_format_); return; }
    if (!width || !height) return;
    last_width_=width; last_height_=height;
    video_->present_software(data,width,height,pitch,pixel_format_);
}

int16_t NativeCoreHost::Impl::input_state(unsigned port, unsigned device, unsigned index, unsigned id) const {
    if (port != 0) return 0;
    const unsigned base = device & RETRO_DEVICE_MASK;
    if (base == RETRO_DEVICE_JOYPAD && index == 0) {
        const uint32_t buttons=sampled_buttons_;
        if (id == RETRO_DEVICE_ID_JOYPAD_MASK) return static_cast<int16_t>(buttons & 0xffffu);
        if (id < 32) return (buttons & (1u << id)) ? 1 : 0;
    }
    if (base == RETRO_DEVICE_POINTER && index == 0) {
        if (id == RETRO_DEVICE_ID_POINTER_X) return sampled_pointer_x_;
        if (id == RETRO_DEVICE_ID_POINTER_Y) return sampled_pointer_y_;
        if (id == RETRO_DEVICE_ID_POINTER_PRESSED) return sampled_pointer_pressed_ ? 1 : 0;
    }
    if (base == RETRO_DEVICE_ANALOG && index == RETRO_DEVICE_INDEX_ANALOG_LEFT) {
        if (id == RETRO_DEVICE_ID_ANALOG_X) return input_.analog_x_.load(std::memory_order_relaxed);
        if (id == RETRO_DEVICE_ID_ANALOG_Y) return input_.analog_y_.load(std::memory_order_relaxed);
    }
    return 0;
}

void NativeInput::set_buttons(uint32_t value) noexcept {const auto previous=buttons_.exchange(value,std::memory_order_acq_rel);pending_buttons_.fetch_or(value & ~previous,std::memory_order_release);}
void NativeInput::set_button(unsigned id,bool pressed) noexcept { if(id>=32)return; const auto mask=uint32_t{1}<<id; if(pressed){buttons_.fetch_or(mask,std::memory_order_relaxed);pending_buttons_.fetch_or(mask,std::memory_order_release);}else buttons_.fetch_and(~mask,std::memory_order_release); }
uint32_t NativeInput::buttons() const noexcept { return buttons_.load(std::memory_order_relaxed); }
void NativeInput::set_pointer(int16_t x,int16_t y,bool pressed) noexcept { if(pressed){pointer_x_.store(x,std::memory_order_relaxed);pointer_y_.store(y,std::memory_order_relaxed);pending_pointer_.store(true,std::memory_order_release);}pointer_pressed_.store(pressed,std::memory_order_release); }
void NativeInput::set_analog(int16_t x,int16_t y) noexcept { analog_x_.store(x,std::memory_order_relaxed);analog_y_.store(y,std::memory_order_relaxed); }
void NativeInput::cancel_pointer() noexcept { pointer_pressed_=false;pending_pointer_=false; }
void NativeInput::clear() noexcept { buttons_=0;pending_buttons_=0;pointer_pressed_=false;pending_pointer_=false;analog_x_=0;analog_y_=0; }

NativeCoreHost::NativeCoreHost():impl_(std::make_unique<Impl>()) {}
NativeCoreHost::~NativeCoreHost(){ shutdown(); }
bool NativeCoreHost::initialize(const std::string&a,const std::string&b,const std::string&c,NativeVideoBackend&d,NativeAudioBackend&e,std::string&f,const std::string&layout,const std::string&graphics_api){return impl_->initialize(a,b,c,d,e,f,layout,graphics_api);}
bool NativeCoreHost::run_one(std::string& e,bool p){return impl_->run_one(e,p);}
void NativeCoreHost::shutdown(){if(impl_)impl_->shutdown();}
bool NativeCoreHost::running()const noexcept{return impl_->running_.load(std::memory_order_relaxed);}
std::chrono::nanoseconds NativeCoreHost::frame_duration()const noexcept{return std::chrono::nanoseconds(impl_->frame_duration_ns_.load(std::memory_order_relaxed));}
NativeCoreStatus NativeCoreHost::status()const{std::lock_guard<std::mutex>l(impl_->mutex_);NativeCoreStatus s;s.system=impl_->system_;s.core_name=impl_->core_name_;s.core_version=impl_->core_version_;s.last_message=impl_->message_;s.core_fps=impl_->core_fps_;s.core_frames=impl_->core_frames_.load(std::memory_order_relaxed);s.hardware_render_rejected=impl_->hardware_render_rejected_;return s;}
NativeInput& NativeCoreHost::input()noexcept{return impl_->input_;}
const NativeInput& NativeCoreHost::input()const noexcept{return impl_->input_;}
bool NativeCoreHost::save_state(unsigned s,std::string&e){if(s<1||s>kMaxStateSlot){e="Quick-save slots range from 1 to 10.";return false;}return impl_->state(true,std::filesystem::path(impl_->save_path_)/"states"/(impl_->rom_id_+".slot"+std::to_string(s)+".state"),e);}
bool NativeCoreHost::load_state(unsigned s,std::string&e){if(s<1||s>kMaxStateSlot){e="Quick-save slots range from 1 to 10.";return false;}return impl_->state(false,std::filesystem::path(impl_->save_path_)/"states"/(impl_->rom_id_+".slot"+std::to_string(s)+".state"),e);}
bool NativeCoreHost::save_auto(std::string&e){return impl_->state(true,std::filesystem::path(impl_->save_path_)/"states"/(impl_->rom_id_+".autosave.state"),e);}
bool NativeCoreHost::load_auto(std::string&e){return impl_->state(false,std::filesystem::path(impl_->save_path_)/"states"/(impl_->rom_id_+".autosave.state"),e);}
bool NativeCoreHost::export_state(const std::string&p,std::string&e){return impl_->state(true,p,e);}
bool NativeCoreHost::import_state(const std::string&p,std::string&e){return impl_->state(false,p,e);}
bool NativeCoreHost::set_core_option(const std::string&k,const std::string&v,std::string&e){std::lock_guard<std::mutex>l(impl_->mutex_);if(!impl_->options_.set(k,v)){e="Unknown core option or unsupported value.";return false;}return true;}
bool NativeCoreHost::set_screen_layout(const std::string& layout,std::string& error) {
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    if (impl_->system_ != NativeSystem::NDS && impl_->system_ != NativeSystem::ThreeDS) {
        error = "Screen layouts apply only to multi-screen systems.";
        return false;
    }
    if (layout != "top-bottom" && layout != "left-right") {
        error = "Unsupported shared screen layout.";
        return false;
    }
    impl_->nds_layout_ = layout;
    const std::string key = impl_->system_ == NativeSystem::NDS ? "melonds_screen_layout1" : "citra_layout_option";
    const std::string value = impl_->system_ == NativeSystem::NDS ? layout : (layout == "left-right" ? "side_by_side" : "top_bottom");
    (void)impl_->options_.set(key, value);
    impl_->options_.mark_updated();
    return true;
}
std::vector<std::string> NativeCoreHost::core_option_keys()const{std::lock_guard<std::mutex>l(impl_->mutex_);std::vector<std::string> keys;for(const auto&o:impl_->options_.options())keys.push_back(o.key);return keys;}

std::vector<NativeCoreOption> NativeCoreHost::core_options() const {
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    std::vector<NativeCoreOption> result;
    result.reserve(impl_->options_.options().size());
    for (const auto& option : impl_->options_.options()) {
        NativeCoreOption copy;
        copy.key = option.key;
        copy.label = option.display_label;
        copy.description = option.description;
        copy.current_value = option.current_value;
        copy.restart_required = option.restart_required;
        copy.values.reserve(option.values.size());
        for (const auto& value : option.values) copy.values.push_back({value.value, value.label});
        result.push_back(std::move(copy));
    }
    return result;
}

std::string NativeCoreHost::core_options_json() const {
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    const auto quote=[](const std::string& text) {
        std::string result="\"";
        for (unsigned char c:text) {
            if (c=='"' || c=='\\') { result+='\\';result+=c; }
            else if (c=='\n') result+="\\n";
            else if (c=='\r') result+="\\r";
            else if (c=='\t') result+="\\t";
            else if (c>=32) result+=c;
        }
        return result+'"';
    };
    std::string json="[";bool first=true;
    for(const auto& option:impl_->options_.options()) {
        if(!first)json+=",";
        first=false;
        json+="{\"key\":"+quote(option.key)+",\"title\":"+quote(option.display_label)+",\"current\":"+quote(option.current_value)+",\"values\":[";
        bool first_value=true;
        for(const auto& value:option.values) { if(!first_value)json+=",";first_value=false;json+=quote(value.value); }
        json+="]}";
    }
    return json+"]";
}

} // namespace an3
