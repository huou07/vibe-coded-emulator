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

#include <atomic>
#include <chrono>
#include <memory>
#include <string>
#include <thread>

#include "core/core.h"
#include "core/frontend/emu_window.h"
#include "core/frontend/graphics_context.h"
#include "core/hle/service/am/applet_manager.h"

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

class HeadlessWindow final : public Frontend::EmuWindow {
public:
    explicit HeadlessWindow(std::atomic<bool>& frame_flag) : frame_flag_(frame_flag) {
        window_info.type = Frontend::WindowSystemType::Headless;
        window_info.render_surface = nullptr;
        window_info.render_surface_scale = 1.0f;
        UpdateCurrentFramebufferLayout(width_, height_);
        NotifyClientAreaSizeChanged({width_, height_});
    }

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
    u32 width_ = 1280;
    u32 height_ = 720;
};

struct EdenState {
    std::unique_ptr<Core::System> system;
    std::unique_ptr<HeadlessWindow> window;
    std::string content_path;
    std::thread run_thread;
    std::atomic<bool> running{false};
    std::atomic<bool> frame_displayed{false};
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
        state->window = std::make_unique<HeadlessWindow>(state->frame_displayed);
        state->system = std::make_unique<Core::System>();
        state->system->Initialize();
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
    Service::AM::FrontendAppletParameters params{};
    Core::SystemResultStatus result = Core::SystemResultStatus::ErrorUnknown;
    try {
        result = state->system->Load(*state->window, std::string(content_path), params);
    } catch (const std::exception& error) {
        return fail(core, AN3_EDEN_ERR_INTERNAL, error.what());
    } catch (...) {
        return fail(core, AN3_EDEN_ERR_INTERNAL, "Eden content load failed");
    }
    switch (result) {
        case Core::SystemResultStatus::Success:
            state->content_path = content_path;
            return AN3_EDEN_OK;
        case Core::SystemResultStatus::ErrorNotInitialized:
            return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "Eden is not initialized");
        case Core::SystemResultStatus::ErrorGetLoader:
        case Core::SystemResultStatus::ErrorLoader:
            return fail(core, AN3_EDEN_ERR_UNSUPPORTED, "Eden has no loader for this content");
        case Core::SystemResultStatus::ErrorSystemFiles:
        case Core::SystemResultStatus::ErrorSharedFont:
            return fail(core, AN3_EDEN_ERR_KEYS_REQUIRED, "Eden needs system files or firmware for this content");
        case Core::SystemResultStatus::ErrorVideoCore:
            return fail(core, AN3_EDEN_ERR_UNAVAILABLE, "Eden's video core could not start on this device");
        case Core::SystemResultStatus::ErrorUnknown:
        default:
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
    if (state->content_path.empty()) {
        return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "No content is loaded");
    }
    state->running.store(true, std::memory_order_release);
    Core::System* system = state->system.get();
    state->run_thread = std::thread([system, state] {
        try {
            system->Run();
        } catch (...) {
            /* The dispatcher cannot see this thread; record and stop cleanly. */
        }
        state->running.store(false, std::memory_order_release);
    });
    return AN3_EDEN_OK;
}

an3_eden_status eden_pause(an3_eden_core* core, int paused) {
    EdenState* state = state_of(core);
    if (state == nullptr || !state->system) {
        return fail(core, AN3_EDEN_ERR_NOT_INITIALIZED, "Eden core is not initialized");
    }
    if (!paused) {
        /* Eden exposes Pause() but no matching resume entry point on System. */
        return fail(core, AN3_EDEN_ERR_UNSUPPORTED, "Resuming is not supported by this Eden revision");
    }
    state->system->Pause();
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
    if (state->running.load(std::memory_order_acquire)) {
        try {
            state->system->ShutdownMainProcess();
        } catch (...) {
        }
        if (state->run_thread.joinable()) {
            state->run_thread.join();
        }
        state->running.store(false, std::memory_order_release);
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
    if (state->run_thread.joinable()) {
        state->run_thread.join();
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
