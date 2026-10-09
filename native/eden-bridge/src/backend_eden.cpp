/*
 * SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Eden-backed implementation of the bridge. Compiled only when
 * AN3_EDEN_ENABLED=ON and linked against Eden's `core` target.
 *
 * The bridge supplies the native WSI surface required by Eden's Vulkan
 * renderer: a hosted Cocoa layer on macOS and SDL3/native WSI handles on
 * Linux and Windows. Android is wired through its ANativeWindow frontend.
 */
#include "an3_eden_internal.h"

#if defined(__APPLE__)
#include "cocoa_surface.h"
#elif defined(__ANDROID__)
#include <android/native_window.h>
#elif !defined(__ANDROID__)
#include "desktop_surface.h"
#endif

#include <atomic>
#include <algorithm>
#include <cstdlib>
#include <chrono>
#include <cstdio>
#include <filesystem>
#include <memory>
#include <string>
#include <thread>

#include "common/dynamic_library.h"
#include "common/fs/path_util.h"

#include "core/core.h"
#include "core/cpu_manager.h"
#include "core/file_sys/registered_cache.h"
#include "core/file_sys/vfs/vfs_real.h"
#include "core/frontend/emu_window.h"
#include "core/frontend/graphics_context.h"
#include "core/hle/service/am/am_types.h"
#include "core/hle/service/am/applet_manager.h"
#include "core/hle/service/filesystem/filesystem.h"
#include "video_core/gpu.h"

#include "input_common/drivers/virtual_gamepad.h"
#include "input_common/main.h"

#include "audio_core/audio_core.h"
#include "audio_core/sink/sink.h"
#include "common/settings.h"

#include "hid_core/frontend/emulated_controller.h"
#include "hid_core/hid_core.h"

#include "common/logging.h"

namespace {

namespace Frontend = Core::Frontend;

/*
 * Mirrors Eden's Vulkan::OpenLibrary search so the bridge can report a missing
 * renderer runtime instead of triggering Eden's uncatchable ErrorVideoCore
 * terminate (RG-111). Only used as a pre-flight; Eden still opens the library.
 */
bool vulkan_library_available() {
    const char* env = std::getenv("LIBVULKAN_PATH");
    if (env != nullptr && env[0] != '\0') {
        Common::DynamicLibrary library;
        if (library.Open(env)) {
            return true;
        }
    }
#if defined(__APPLE__)
    const char* fallbacks[] = {"libvulkan.1.dylib", "libMoltenVK.dylib", "libvulkan.dylib"};
#else
    const char* fallbacks[] = {"libvulkan.so.1", "libvulkan.so"};
#endif
    for (const char* name : fallbacks) {
        Common::DynamicLibrary library;
        if (library.Open(name)) {
            return true;
        }
    }
    return false;
}

/* Headless graphics context: Eden's Vulkan renderer owns the device; this only
 * satisfies the frontend contract. */
class HeadlessContext final : public Frontend::GraphicsContext {
public:
    void SwapBuffers() override {}
    void MakeCurrent() override {}
    void DoneCurrent() override {}
};

#if defined(__ANDROID__)
/* Eden's Android Vulkan loader obtains the driver from the frontend's
 * GraphicsContext.  The standalone AN3 JNI adapter does not use Eden's
 * adrenotools frontend, so keep the same contract with the system Vulkan
 * loader supplied by Android/the emulator. */
class AndroidGraphicsContext final : public Frontend::GraphicsContext {
public:
    AndroidGraphicsContext() : driver_library_(std::make_shared<Common::DynamicLibrary>()) {
        if (!driver_library_->Open("libvulkan.so")) {
            (void)driver_library_->Open("libvulkan.so.1");
        }
    }

    std::shared_ptr<Common::DynamicLibrary> GetDriverLibrary() override {
        return driver_library_;
    }

private:
    std::shared_ptr<Common::DynamicLibrary> driver_library_;
};
#endif

/*
 * Presentation host. Eden's Vulkan renderer has no headless surface path in the
 * pinned revision. macOS uses a hosted CAMetalLayer; Linux and Windows use the
 * same SDL3/native WSI path as Eden's upstream desktop frontend.
 */
class HostWindow final : public Frontend::EmuWindow {
public:
    explicit HostWindow(std::atomic<bool>& frame_flag, void* platform_surface)
        : frame_flag_(frame_flag) {
#if defined(__APPLE__)
        window_info.type = Frontend::WindowSystemType::Cocoa;
        render_surface_ = an3_eden_cocoa_create_layer(width_, height_);
#elif defined(__ANDROID__)
        auto* native_window = static_cast<ANativeWindow*>(platform_surface);
        if (native_window != nullptr) {
            window_info.type = Frontend::WindowSystemType::Android;
            render_surface_ = native_window;
            width_ = static_cast<u32>(std::max(1, ANativeWindow_getWidth(native_window)));
            height_ = static_cast<u32>(std::max(1, ANativeWindow_getHeight(native_window)));
        }
#else
        an3_eden_desktop_surface_info info{};
        desktop_surface_ = an3_eden_desktop_create_surface(width_, height_,
                                                            visible_requested(),
                                                            &info);
        if (desktop_surface_ != nullptr) {
            switch (info.type) {
                case AN3_EDEN_DESKTOP_WINDOW_WINDOWS:
                    window_info.type = Frontend::WindowSystemType::Windows;
                    break;
                case AN3_EDEN_DESKTOP_WINDOW_X11:
                    window_info.type = Frontend::WindowSystemType::X11;
                    break;
                case AN3_EDEN_DESKTOP_WINDOW_WAYLAND:
                    window_info.type = Frontend::WindowSystemType::Wayland;
                    break;
                default:
                    an3_eden_desktop_destroy_surface(desktop_surface_);
                    desktop_surface_ = nullptr;
                    break;
            }
            if (desktop_surface_ != nullptr) {
                window_info.display_connection = info.display_connection;
                render_surface_ = info.render_surface;
            }
        }
#endif
        window_info.render_surface = render_surface_;
        window_info.render_surface_scale = 1.0f;
        UpdateCurrentFramebufferLayout(width_, height_);
        NotifyClientAreaSizeChanged({width_, height_});
    }

    ~HostWindow() override {
#if defined(__APPLE__)
        an3_eden_cocoa_destroy_layer(render_surface_);
#elif defined(__ANDROID__)
        render_surface_ = nullptr;
#else
        an3_eden_desktop_destroy_surface(desktop_surface_);
#endif
    }

    [[nodiscard]] bool HasRenderSurface() const { return render_surface_ != nullptr; }

    [[nodiscard]] std::unique_ptr<Frontend::GraphicsContext> CreateSharedContext() const override {
#if defined(__ANDROID__)
        return std::make_unique<AndroidGraphicsContext>();
#else
        return std::make_unique<HeadlessContext>();
#endif
    }

    [[nodiscard]] bool IsShown() const override { return true; }

    void OnFrameDisplayed() override { frame_flag_.store(true, std::memory_order_release); }

    void SetSize(u32 width, u32 height) {
        width_ = width;
        height_ = height;
        UpdateCurrentFramebufferLayout(width_, height_);
        NotifyClientAreaSizeChanged({width_, height_});
    }

private:
    std::atomic<bool>& frame_flag_;
#if !defined(__APPLE__) && !defined(__ANDROID__)
    void* desktop_surface_ = nullptr;
#endif
    void* render_surface_ = nullptr;
    u32 width_ = 1280;
    u32 height_ = 720;

    static bool visible_requested() {
        const char* value = std::getenv("AN3_EDEN_WINDOW_VISIBLE");
        return value != nullptr && value[0] != '\0' && value[0] != '0';
    }
};

struct EdenState {
    std::unique_ptr<Core::System> system;
    std::unique_ptr<HostWindow> window;
    /* Owns Eden's input engines. Created before Core::System so the
     * `virtual_gamepad` factory is registered when HIDCore builds its
     * controllers' devices (the ABI injects input through that engine). */
    std::unique_ptr<InputCommon::InputSubsystem> input;
    std::string content_path;
    std::atomic<bool> running{false};
    std::atomic<bool> frame_displayed{false};
    /* True between a Load that left Eden's kernel initialised and the matching
     * ShutdownMainProcess. Eden calls KernelCore::Initialize() inside
     * System::Load(), so a Load can leave kernel state behind even when it
     * reports failure; destroying Core::System without shutting that kernel
     * down crashes in ~KernelCore::Impl. */
    bool kernel_initialized{false};
};

EdenState* state_of(an3_eden_core* core) {
    return static_cast<EdenState*>(core->backend_state);
}

an3_eden_status fail(an3_eden_core* core, an3_eden_status status, const char* message) {
    an3::eden::set_error(core, message);
    return status;
}

an3_eden_status eden_initialize(an3_eden_core* core, const char* keys_dir, const char* firmware_dir) {
    auto state = std::make_unique<EdenState>();
    try {
        /* Diagnostics: Eden's own frontends initialise logging before touching
         * the core; without it load failures are silent. */
        Common::Log::Initialize();
        Common::Log::SetColorConsoleBackendEnabled(true);
    } catch (...) {
        /* Logging is optional; never fail initialise because of it. */
    }
    try {
        state->window = std::make_unique<HostWindow>(state->frame_displayed,
                                                     core->platform_surface);
        if (!state->window->HasRenderSurface()) {
            return fail(core, AN3_EDEN_ERR_UNAVAILABLE,
                        "No presentation surface is available for Eden's renderer");
        }
        /* Register the input engines before the system builds controller
         * devices, so the virtual_gamepad backend is available to inject
         * input through the C ABI. */
        state->input = std::make_unique<InputCommon::InputSubsystem>();
        state->input->Initialize();
        state->system = std::make_unique<Core::System>();
        state->system->Initialize();
        /* Mirror Eden's frontends: set up the content provider and filesystem
         * factories before Load so NRO/NCA resolution has valid paths. */
        state->system->SetContentProvider(std::make_unique<FileSys::ContentProviderUnion>());
        state->system->SetFilesystem(std::make_shared<FileSys::RealVfsFilesystem>());
        state->system->GetFileSystemController().CreateFactories(*state->system->GetFilesystem());
        state->system->GetUserChannel().clear();
    } catch (const std::exception& error) {
        return fail(core, AN3_EDEN_ERR_INTERNAL, error.what());
    } catch (...) {
        return fail(core, AN3_EDEN_ERR_INTERNAL, "Eden core initialisation failed");
    }
    /* Keys/firmware directories are not yet wired; Eden reads them from its own
     * configuration for now. Encrypted commercial content will fail to load. */
    (void)keys_dir;
    (void)firmware_dir;
    core->backend_state = state.release();
    return AN3_EDEN_OK;
}

an3_eden_status eden_load(an3_eden_core* core, const char* content_path) {
    EdenState* state = state_of(core);
    if (state == nullptr || !state->system || !state->window) {
        return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "Eden core is not initialized");
    }
    if (state->running.load(std::memory_order_acquire)) {
        return fail(core, AN3_EDEN_ERR_BUSY, "Eden core is already running");
    }
    if (state->kernel_initialized) {
        return fail(core, AN3_EDEN_ERR_BUSY, "Eden already has content loaded");
    }
    /* RG-111: Eden's ErrorVideoCore path terminates inside a noexcept destructor,
     * so it cannot be caught at the ABI. Pre-flight the Vulkan runtime the
     * renderer needs and report it honestly instead of entering that path. */
    if (!vulkan_library_available()) {
        return fail(core, AN3_EDEN_ERR_UNAVAILABLE,
                    "Eden's Vulkan runtime (MoltenVK) is unavailable; the Switch renderer cannot start");
    }
    Service::AM::FrontendAppletParameters params{};
    /* System::Load() does not default to the application applet; without this
     * Eden creates no application process and the load cannot succeed. */
    params.applet_id = Service::AM::AppletId::Application;
    Core::SystemResultStatus result = Core::SystemResultStatus::ErrorUnknown;
    /* System::Load() calls KernelCore::Initialize() before it validates the
     * content, so from here the kernel must be shut down exactly once. */
    state->kernel_initialized = true;
    try {
        result = state->system->Load(*state->window, std::string(content_path), params);
    } catch (const std::exception& error) {
        state->system->ShutdownMainProcess();
        state->kernel_initialized = false;
        return fail(core, AN3_EDEN_ERR_INTERNAL, error.what());
    } catch (...) {
        state->system->ShutdownMainProcess();
        state->kernel_initialized = false;
        return fail(core, AN3_EDEN_ERR_INTERNAL, "Eden content load failed");
    }
    switch (result) {
        case Core::SystemResultStatus::Success:
            state->content_path = content_path;
            return AN3_EDEN_OK;
        case Core::SystemResultStatus::ErrorGetLoader:
            /* This revision returns ErrorGetLoader before its cleanup and
             * leaves the kernel initialised; shut it down here. */
            state->system->ShutdownMainProcess();
            state->kernel_initialized = false;
            return fail(core, AN3_EDEN_ERR_UNSUPPORTED, "Eden has no loader for this content");
        case Core::SystemResultStatus::ErrorNotInitialized:
            /* Every other Load failure path runs ShutdownMainProcess itself. */
            state->kernel_initialized = false;
            return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "Eden is not initialized");
        case Core::SystemResultStatus::ErrorLoader: {
            /* Load() encodes a loader-specific error as ErrorLoader + status. */
            const auto loader_status =
                static_cast<uint32_t>(result) - static_cast<uint32_t>(Core::SystemResultStatus::ErrorLoader);
            std::string message = "Eden could not load this content (loader error " +
                                  std::to_string(loader_status) + ")";
            state->kernel_initialized = false;
            return fail(core, AN3_EDEN_ERR_UNSUPPORTED, message.c_str());
        }
        case Core::SystemResultStatus::ErrorSystemFiles:
        case Core::SystemResultStatus::ErrorSharedFont:
            state->kernel_initialized = false;
            return fail(core, AN3_EDEN_ERR_KEYS_REQUIRED,
                        "Eden needs system files or firmware for this content");
        case Core::SystemResultStatus::ErrorVideoCore:
            state->kernel_initialized = false;
            return fail(core, AN3_EDEN_ERR_UNAVAILABLE,
                        "Eden's video core could not start on this device");
        case Core::SystemResultStatus::ErrorUnknown:
        default:
            state->kernel_initialized = false;
            return fail(core, AN3_EDEN_ERR_IO, "Eden could not load the content");
    }
}

an3_eden_status eden_start(an3_eden_core* core) {
    EdenState* state = state_of(core);
    if (state == nullptr || !state->system || !state->window) {
        return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "Eden core is not initialized");
    }
    if (state->running.load(std::memory_order_acquire)) {
        return AN3_EDEN_OK;
    }
    if (!state->kernel_initialized || state->content_path.empty()) {
        return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "No content is loaded");
    }
    /* Mirror Eden's own frontend startup: bring up the GPU, tell the CPU
     * manager the GPU is ready, then resume. System::Run() only resumes
     * emulation; it does not block, so no host thread is owned here. */
    try {
        state->system->GPU().Start();
        state->system->GetCpuManager().OnGpuReady();
        state->system->Run();
    } catch (const std::exception& error) {
        return fail(core, AN3_EDEN_ERR_INTERNAL, error.what());
    } catch (...) {
        return fail(core, AN3_EDEN_ERR_INTERNAL, "Eden could not start the GPU");
    }
    state->running.store(true, std::memory_order_release);
    return AN3_EDEN_OK;
}

an3_eden_status eden_pause(an3_eden_core* core, int paused) {
    EdenState* state = state_of(core);
    if (state == nullptr || !state->system) {
        return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "Eden core is not initialized");
    }
    if (!state->running.load(std::memory_order_acquire)) {
        return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "Eden core is not running");
    }
    try {
        if (paused) {
            state->system->Pause();
        } else {
            /* System::Run() is Eden's resume entry point. */
            state->system->Run();
        }
    } catch (const std::exception& error) {
        return fail(core, AN3_EDEN_ERR_INTERNAL, error.what());
    } catch (...) {
        return fail(core, AN3_EDEN_ERR_INTERNAL, "Eden could not change the pause state");
    }
    return AN3_EDEN_OK;
}

an3_eden_status eden_run_frame(an3_eden_core* core, an3_eden_frame_callback callback, void* user_data) {
    EdenState* state = state_of(core);
    if (state == nullptr) {
        return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "Eden core is not initialized");
    }
    if (!state->running.load(std::memory_order_acquire)) {
        return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "Eden core is not running");
    }
    /* Wait briefly for the GPU thread to present a frame. Frame readback and
     * hosted presentation are a later milestone: for now the callback is not
     * invoked, so no pixel data is faked. */
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(50);
    while (!state->frame_displayed.load(std::memory_order_acquire) &&
           std::chrono::steady_clock::now() < deadline) {
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    state->frame_displayed.store(false, std::memory_order_release);
    (void)callback;
    (void)user_data;
    return AN3_EDEN_OK;
}

/* Maps an AN3/libretro button id onto Eden's virtual gamepad button. */
bool map_virtual_button(uint32_t button, InputCommon::VirtualGamepad::VirtualButton& out) {
    using VB = InputCommon::VirtualGamepad::VirtualButton;
    switch (button) {
        case AN3_EDEN_BUTTON_B: out = VB::ButtonB; return true;
        case AN3_EDEN_BUTTON_Y: out = VB::ButtonY; return true;
        case AN3_EDEN_BUTTON_SELECT: out = VB::ButtonMinus; return true;
        case AN3_EDEN_BUTTON_START: out = VB::ButtonPlus; return true;
        case AN3_EDEN_BUTTON_UP: out = VB::ButtonUp; return true;
        case AN3_EDEN_BUTTON_DOWN: out = VB::ButtonDown; return true;
        case AN3_EDEN_BUTTON_LEFT: out = VB::ButtonLeft; return true;
        case AN3_EDEN_BUTTON_RIGHT: out = VB::ButtonRight; return true;
        case AN3_EDEN_BUTTON_A: out = VB::ButtonA; return true;
        case AN3_EDEN_BUTTON_X: out = VB::ButtonX; return true;
        case AN3_EDEN_BUTTON_L: out = VB::TriggerL; return true;
        case AN3_EDEN_BUTTON_R: out = VB::TriggerR; return true;
        case AN3_EDEN_BUTTON_L2: out = VB::TriggerZL; return true;
        case AN3_EDEN_BUTTON_R2: out = VB::TriggerZR; return true;
        case AN3_EDEN_BUTTON_L3: out = VB::StickL; return true;
        case AN3_EDEN_BUTTON_R3: out = VB::StickR; return true;
        default: return false;
    }
}

an3_eden_status eden_submit_button(an3_eden_core* core, uint32_t port, uint32_t button, int pressed) {
    EdenState* state = state_of(core);
    if (state == nullptr || !state->input) {
        return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "Eden input is not initialized");
    }
    if (!state->running.load(std::memory_order_acquire)) {
        return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "Eden core is not running");
    }
    InputCommon::VirtualGamepad::VirtualButton mapped{};
    if (!map_virtual_button(button, mapped)) {
        return fail(core, AN3_EDEN_ERR_INVALID_ARGUMENT, "Unknown button id");
    }
    InputCommon::VirtualGamepad* pad = state->input->GetVirtualGamepad();
    if (pad == nullptr) {
        return fail(core, AN3_EDEN_ERR_UNAVAILABLE, "Eden has no virtual gamepad engine");
    }
    pad->SetButtonState(static_cast<std::size_t>(port), mapped, pressed != 0);
    return AN3_EDEN_OK;
}

an3_eden_status eden_submit_analog(an3_eden_core* core, uint32_t port, uint32_t stick, int16_t x, int16_t y) {
    EdenState* state = state_of(core);
    if (state == nullptr || !state->input) {
        return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "Eden input is not initialized");
    }
    if (!state->running.load(std::memory_order_acquire)) {
        return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "Eden core is not running");
    }
    InputCommon::VirtualGamepad* pad = state->input->GetVirtualGamepad();
    if (pad == nullptr) {
        return fail(core, AN3_EDEN_ERR_UNAVAILABLE, "Eden has no virtual gamepad engine");
    }
    const auto clamp_unit = [](int16_t value) {
        const float unit = static_cast<float>(value) / 32767.0f;
        return unit < -1.0f ? -1.0f : (unit > 1.0f ? 1.0f : unit);
    };
    const auto axis = stick == AN3_EDEN_STICK_RIGHT
                          ? InputCommon::VirtualGamepad::VirtualStick::Right
                          : InputCommon::VirtualGamepad::VirtualStick::Left;
    pad->SetStickPosition(static_cast<std::size_t>(port), axis, clamp_unit(x), clamp_unit(y));
    return AN3_EDEN_OK;
}

/* Bit positions in Eden's NpadButtonState.raw (hid_core/hid_types.h). */
bool npad_bit_for_button(uint32_t button, u64& mask) {
    switch (button) {
        case AN3_EDEN_BUTTON_A: mask = u64{1} << 0; return true;
        case AN3_EDEN_BUTTON_B: mask = u64{1} << 1; return true;
        case AN3_EDEN_BUTTON_X: mask = u64{1} << 2; return true;
        case AN3_EDEN_BUTTON_Y: mask = u64{1} << 3; return true;
        case AN3_EDEN_BUTTON_L3: mask = u64{1} << 4; return true;
        case AN3_EDEN_BUTTON_R3: mask = u64{1} << 5; return true;
        case AN3_EDEN_BUTTON_L: mask = u64{1} << 6; return true;
        case AN3_EDEN_BUTTON_R: mask = u64{1} << 7; return true;
        case AN3_EDEN_BUTTON_L2: mask = u64{1} << 8; return true;
        case AN3_EDEN_BUTTON_R2: mask = u64{1} << 9; return true;
        case AN3_EDEN_BUTTON_START: mask = u64{1} << 10; return true;
        case AN3_EDEN_BUTTON_SELECT: mask = u64{1} << 11; return true;
        case AN3_EDEN_BUTTON_LEFT: mask = u64{1} << 12; return true;
        case AN3_EDEN_BUTTON_UP: mask = u64{1} << 13; return true;
        case AN3_EDEN_BUTTON_RIGHT: mask = u64{1} << 14; return true;
        case AN3_EDEN_BUTTON_DOWN: mask = u64{1} << 15; return true;
        default: return false;
    }
}

an3_eden_status eden_get_button(an3_eden_core* core, uint32_t port, uint32_t button, int* out_pressed) {
    EdenState* state = state_of(core);
    if (state == nullptr || !state->system) {
        return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "Eden core is not initialized");
    }
    Core::HID::EmulatedController* controller =
        state->system->HIDCore().GetEmulatedControllerByIndex(port);
    if (controller == nullptr) {
        return fail(core, AN3_EDEN_ERR_INVALID_ARGUMENT, "No emulated controller for this port");
    }
    u64 mask = 0;
    if (!npad_bit_for_button(button, mask)) {
        return fail(core, AN3_EDEN_ERR_INVALID_ARGUMENT, "Unknown button id");
    }
    const u64 raw = static_cast<u64>(controller->GetNpadButtons().raw);
    *out_pressed = (raw & mask) != 0 ? 1 : 0;
    return AN3_EDEN_OK;
}

an3_eden_status eden_get_analog(an3_eden_core* core, uint32_t port, uint32_t stick, int16_t* out_x, int16_t* out_y) {
    EdenState* state = state_of(core);
    if (state == nullptr || !state->system) {
        return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "Eden core is not initialized");
    }
    Core::HID::EmulatedController* controller =
        state->system->HIDCore().GetEmulatedControllerByIndex(port);
    if (controller == nullptr) {
        return fail(core, AN3_EDEN_ERR_INVALID_ARGUMENT, "No emulated controller for this port");
    }
    const auto sticks = controller->GetSticks();
    const Core::HID::AnalogStickState& axis =
        stick == AN3_EDEN_STICK_RIGHT ? sticks.right : sticks.left;
    const auto clamp_to_i16 = [](s32 value) {
        if (value > 32767) return static_cast<int16_t>(32767);
        if (value < -32768) return static_cast<int16_t>(-32768);
        return static_cast<int16_t>(value);
    };
    *out_x = clamp_to_i16(axis.x);
    *out_y = clamp_to_i16(axis.y);
    return AN3_EDEN_OK;
}

an3_eden_status eden_save_data(an3_eden_core* core, const char* path) {
    EdenState* state = state_of(core);
    if (state == nullptr || !state->system) {
        return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "Eden core is not initialized");
    }
    if (path == nullptr || path[0] == '\0') {
        return fail(core, AN3_EDEN_ERR_INVALID_ARGUMENT, "A destination path is required");
    }
    /* Eden writes saves itself; this exports its save tree to `path` so AN3 can
     * back it up or sync it, and never touches the live save data. */
    try {
        namespace fs = std::filesystem;
        const fs::path source{Common::FS::GetEdenPathString(Common::FS::EdenPath::SaveDir)};
        if (source.empty()) {
            return fail(core, AN3_EDEN_ERR_UNSUPPORTED, "Eden has no save directory on this platform");
        }
        const fs::path destination{path};
        std::error_code error;
        fs::create_directories(destination, error);
        if (error) {
            return fail(core, AN3_EDEN_ERR_IO, "Could not create the save export directory");
        }
        if (fs::exists(source, error)) {
            fs::copy(source, destination,
                     fs::copy_options::recursive | fs::copy_options::overwrite_existing, error);
            if (error) {
                return fail(core, AN3_EDEN_ERR_IO, "Could not export Eden's save data");
            }
        }
        return AN3_EDEN_OK;
    } catch (const std::exception& error) {
        return fail(core, AN3_EDEN_ERR_INTERNAL, error.what());
    } catch (...) {
        return fail(core, AN3_EDEN_ERR_INTERNAL, "Eden save export failed");
    }
}

an3_eden_status eden_get_save_dir(an3_eden_core* core, char* out_path, uint32_t size) {
    EdenState* state = state_of(core);
    if (state == nullptr || !state->system) {
        return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "Eden core is not initialized");
    }
    try {
        const std::string dir = Common::FS::GetEdenPathString(Common::FS::EdenPath::SaveDir);
        if (dir.empty()) {
            return fail(core, AN3_EDEN_ERR_UNSUPPORTED, "Eden has no save directory on this platform");
        }
        std::snprintf(out_path, size, "%s", dir.c_str());
        return AN3_EDEN_OK;
    } catch (const std::exception& error) {
        return fail(core, AN3_EDEN_ERR_INTERNAL, error.what());
    } catch (...) {
        return fail(core, AN3_EDEN_ERR_INTERNAL, "Eden save directory lookup failed");
    }
}

an3_eden_status eden_get_audio_info(an3_eden_core* core, an3_eden_audio_info* out_info) {
    EdenState* state = state_of(core);
    if (state == nullptr || !state->system) {
        return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "Eden core is not initialized");
    }
    try {
        const char* backend = "auto";
        switch (Settings::values.sink_id.GetValue()) {
            case Settings::AudioEngine::Cubeb: backend = "cubeb"; break;
            case Settings::AudioEngine::Sdl3: backend = "sdl3"; break;
            case Settings::AudioEngine::Null: backend = "null"; break;
            case Settings::AudioEngine::Auto:
            default: backend = "auto"; break;
        }
        std::snprintf(out_info->backend, sizeof(out_info->backend), "%s", backend);
        const std::string device = Settings::values.audio_output_device_id.GetValue();
        std::snprintf(out_info->device, sizeof(out_info->device), "%s", device.c_str());
        AudioCore::Sink::Sink& sink = state->system->AudioCore().GetOutputSink();
        out_info->channels = sink.GetDeviceChannels();
        out_info->volume = sink.GetDeviceVolume();
        return AN3_EDEN_OK;
    } catch (const std::exception& error) {
        return fail(core, AN3_EDEN_ERR_INTERNAL, error.what());
    } catch (...) {
        return fail(core, AN3_EDEN_ERR_INTERNAL, "Eden audio lookup failed");
    }
}

an3_eden_status eden_stop(an3_eden_core* core) {
    EdenState* state = state_of(core);
    if (state == nullptr || !state->system) {
        return AN3_EDEN_OK;
    }
    /* Shut the kernel down exactly once, whether the core was started or only
     * had content loaded. Eden's Load() leaves the kernel initialised. */
    if (state->running.load(std::memory_order_acquire) || state->kernel_initialized) {
        try {
            state->system->ShutdownMainProcess();
        } catch (...) {
        }
        state->running.store(false, std::memory_order_release);
        state->kernel_initialized = false;
    }
    state->content_path.clear();
    return AN3_EDEN_OK;
}

an3_eden_status eden_shutdown(an3_eden_core* core) {
    (void)eden_stop(core);
    EdenState* state = state_of(core);
    if (state == nullptr) {
        return AN3_EDEN_OK;
    }
    /* Core::System's destructor releases the subsystems; this revision exposes
     * no separate System::Shutdown(). Release the controllers before
     * unregistering the input engines they are bound to. */
    state->window.reset();
    state->system.reset();
    if (state->input) {
        state->input->Shutdown();
        state->input.reset();
    }
    delete state;
    core->backend_state = nullptr;
    return AN3_EDEN_OK;
}

const an3::eden::Backend kEdenBackend{
    "eden",           eden_initialize,    eden_load,         eden_start,
    eden_pause,       eden_run_frame,     eden_submit_button, eden_submit_analog,
    eden_get_button,  eden_get_analog,    eden_save_data,    eden_get_save_dir,
    eden_get_audio_info, eden_stop,       eden_shutdown,
};

}  // namespace

const an3::eden::Backend& an3::eden::active_backend() {
    return kEdenBackend;
}
