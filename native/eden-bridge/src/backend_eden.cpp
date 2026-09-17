/*
 * SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Eden-backed implementation of the bridge. Compiled only when
 * AN3_EDEN_ENABLED=ON and linked against Eden's `core` target.
 *
 * First integration step: a headless EmuWindow drives Eden's core without a
 * host surface (Eden supports WindowSystemType::Headless with
 * render_surface == nullptr). Hosted presentation comes later and must use
 * Eden's own Vulkan device.
 */
#include "an3_eden_internal.h"

#if defined(__APPLE__)
#include "cocoa_surface.h"
#endif

#include <atomic>
#include <chrono>
#include <memory>
#include <string>
#include <thread>

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

#include "common/logging.h"

namespace {

namespace Frontend = Core::Frontend;

/* Headless graphics context: Eden's Vulkan renderer owns the device; this only
 * satisfies the frontend contract. */
class HeadlessContext final : public Frontend::GraphicsContext {
public:
    void SwapBuffers() override {}
    void MakeCurrent() override {}
    void DoneCurrent() override {}
};

/*
 * Presentation host. Eden's Vulkan renderer has no headless surface path in the
 * pinned revision: on macOS it requires a Cocoa CAMetalLayer, elsewhere a real
 * Win32/X11/Wayland surface. On macOS the bridge supplies an offscreen
 * CAMetalLayer so the core can initialise without a window.
 */
class HostWindow final : public Frontend::EmuWindow {
public:
    explicit HostWindow(std::atomic<bool>& frame_flag) : frame_flag_(frame_flag) {
#if defined(__APPLE__)
        window_info.type = Frontend::WindowSystemType::Cocoa;
        render_surface_ = an3_eden_cocoa_create_layer(width_, height_);
#else
        window_info.type = Frontend::WindowSystemType::Headless;
        render_surface_ = nullptr;
#endif
        window_info.render_surface = render_surface_;
        window_info.render_surface_scale = 1.0f;
        UpdateCurrentFramebufferLayout(width_, height_);
        NotifyClientAreaSizeChanged({width_, height_});
    }

    ~HostWindow() override {
#if defined(__APPLE__)
        an3_eden_cocoa_destroy_layer(render_surface_);
#endif
    }

    [[nodiscard]] bool HasRenderSurface() const { return render_surface_ != nullptr; }

    [[nodiscard]] std::unique_ptr<Frontend::GraphicsContext> CreateSharedContext() const override {
        return std::make_unique<HeadlessContext>();
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
    void* render_surface_ = nullptr;
    u32 width_ = 1280;
    u32 height_ = 720;
};

struct EdenState {
    std::unique_ptr<Core::System> system;
    std::unique_ptr<HostWindow> window;
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
        state->window = std::make_unique<HostWindow>(state->frame_displayed);
        if (!state->window->HasRenderSurface()) {
            return fail(core, AN3_EDEN_ERR_UNAVAILABLE,
                        "No presentation surface is available for Eden's renderer");
        }
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

an3_eden_status eden_submit_button(an3_eden_core*, uint32_t, uint32_t, int) {
    /* Input wiring is a later milestone (HID service); report honestly. */
    return AN3_EDEN_ERR_UNSUPPORTED;
}

an3_eden_status eden_submit_analog(an3_eden_core*, uint32_t, int16_t, int16_t) {
    return AN3_EDEN_ERR_UNSUPPORTED;
}

an3_eden_status eden_save_data(an3_eden_core*, const char*) {
    /* Save data is written by Eden's own save services. */
    return AN3_EDEN_ERR_UNSUPPORTED;
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
     * no separate System::Shutdown(). */
    state->window.reset();
    state->system.reset();
    delete state;
    core->backend_state = nullptr;
    return AN3_EDEN_OK;
}

const an3::eden::Backend kEdenBackend{
    "eden",        eden_initialize,    eden_load,          eden_start,
    eden_pause,    eden_run_frame,     eden_submit_button, eden_submit_analog,
    eden_save_data, eden_stop,         eden_shutdown,
};

}  // namespace

const an3::eden::Backend& an3::eden::active_backend() {
    return kEdenBackend;
}
