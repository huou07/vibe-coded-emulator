/*
 * SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Public C ABI implementation: handle validation, lifecycle enforcement and
 * exception containment. Backends provide the actual emulation.
 */
#include "an3_eden_internal.h"

#include <cstdio>
#include <cstring>
#include <new>

namespace {

using an3::eden::State;

bool valid(const an3_eden_core* core) {
    return core != nullptr && core->magic == AN3_EDEN_CORE_MAGIC;
}

/* Runs a backend call, guaranteeing that no exception escapes the ABI. */
template <typename Callable>
an3_eden_status guard(an3_eden_core* core, Callable&& callable) {
    try {
        return callable();
    } catch (const std::bad_alloc&) {
        an3::eden::set_error(core, "out of memory in the Eden backend");
        return AN3_EDEN_ERR_INTERNAL;
    } catch (...) {
        an3::eden::set_error(core, "unhandled exception in the Eden backend");
        return AN3_EDEN_ERR_INTERNAL;
    }
}

bool empty_or_null(const char* value) {
    return value == nullptr || value[0] == '\0';
}

}  // namespace

namespace an3::eden {

void set_error(an3_eden_core* core, const char* message) {
    if (core == nullptr) {
        return;
    }
    std::snprintf(core->last_error, sizeof(core->last_error), "%s", message ? message : "");
}

}  // namespace an3::eden

extern "C" {

uint32_t an3_eden_bridge_abi_version(void) {
    return AN3_EDEN_BRIDGE_ABI_VERSION;
}

const char* an3_eden_backend_name(void) {
    const an3::eden::Backend& backend = an3::eden::active_backend();
    return backend.name ? backend.name : "unknown";
}

const char* an3_eden_status_message(an3_eden_status status) {
    switch (status) {
        case AN3_EDEN_OK: return "ok";
        case AN3_EDEN_ERR_INVALID_ARGUMENT: return "invalid argument";
        case AN3_EDEN_ERR_INVALID_HANDLE: return "invalid core handle";
        case AN3_EDEN_ERR_ALREADY_INITIALIZED: return "core is already initialized";
        case AN3_EDEN_ERR_NOT_INITIALIZED: return "core is not initialized";
        case AN3_EDEN_ERR_UNAVAILABLE: return "Eden backend is unavailable in this build or platform";
        case AN3_EDEN_ERR_UNSUPPORTED: return "operation is not supported by this backend";
        case AN3_EDEN_ERR_IO: return "I/O failure";
        case AN3_EDEN_ERR_INTERNAL: return "internal backend failure";
        case AN3_EDEN_ERR_BUSY: return "core is busy";
        case AN3_EDEN_ERR_KEYS_REQUIRED: return "decryption keys or firmware are required";
    }
    return "unknown status";
}

const char* an3_eden_last_error(const an3_eden_core* core) {
    if (!valid(core)) {
        return "";
    }
    return core->last_error;
}

an3_eden_status an3_eden_create(an3_eden_core** out_core) {
    if (out_core == nullptr) {
        return AN3_EDEN_ERR_INVALID_ARGUMENT;
    }
    *out_core = nullptr;
    an3_eden_core* core = new (std::nothrow) an3_eden_core{};
    if (core == nullptr) {
        return AN3_EDEN_ERR_INTERNAL;
    }
    core->magic = AN3_EDEN_CORE_MAGIC;
    core->state = State::Created;
    core->backend_state = nullptr;
    core->last_error[0] = '\0';
    *out_core = core;
    return AN3_EDEN_OK;
}

void an3_eden_destroy(an3_eden_core* core) {
    if (!valid(core)) {
        return;
    }
    if (core->state != State::Created && core->state != State::Stopped) {
        /* Best effort: never leak a running backend, never throw from destroy. */
        try {
            an3::eden::active_backend().shutdown(core);
        } catch (...) {
        }
    }
    core->magic = 0;
    delete core;
}

an3_eden_status an3_eden_initialize(an3_eden_core* core, const char* keys_dir, const char* firmware_dir) {
    if (!valid(core)) {
        return AN3_EDEN_ERR_INVALID_HANDLE;
    }
    if (core->state != State::Created) {
        return AN3_EDEN_ERR_ALREADY_INITIALIZED;
    }
    an3_eden_status status = guard(core, [&] {
        return an3::eden::active_backend().initialize(core, empty_or_null(keys_dir) ? nullptr : keys_dir,
                                                      empty_or_null(firmware_dir) ? nullptr : firmware_dir);
    });
    if (status == AN3_EDEN_OK) {
        core->state = State::Initialized;
    }
    return status;
}

an3_eden_status an3_eden_load(an3_eden_core* core, const char* content_path) {
    if (!valid(core)) {
        return AN3_EDEN_ERR_INVALID_HANDLE;
    }
    if (content_path == nullptr || content_path[0] == '\0') {
        return AN3_EDEN_ERR_INVALID_ARGUMENT;
    }
    if (core->state == State::Created) {
        return AN3_EDEN_ERR_NOT_INITIALIZED;
    }
    if (core->state == State::Started) {
        return AN3_EDEN_ERR_BUSY;
    }
    an3_eden_status status =
        guard(core, [&] { return an3::eden::active_backend().load(core, content_path); });
    if (status == AN3_EDEN_OK) {
        core->state = State::Loaded;
    }
    return status;
}

an3_eden_status an3_eden_start(an3_eden_core* core) {
    if (!valid(core)) {
        return AN3_EDEN_ERR_INVALID_HANDLE;
    }
    /* Content must be loaded: a stopped core has released its kernel and needs
     * a fresh load before it can start again. */
    if (core->state != State::Loaded) {
        return AN3_EDEN_ERR_NOT_INITIALIZED;
    }
    an3_eden_status status = guard(core, [&] { return an3::eden::active_backend().start(core); });
    if (status == AN3_EDEN_OK) {
        core->state = State::Started;
    }
    return status;
}

an3_eden_status an3_eden_pause(an3_eden_core* core, int paused) {
    if (!valid(core)) {
        return AN3_EDEN_ERR_INVALID_HANDLE;
    }
    if (core->state != State::Started) {
        return AN3_EDEN_ERR_NOT_INITIALIZED;
    }
    return guard(core, [&] { return an3::eden::active_backend().pause(core, paused); });
}

an3_eden_status an3_eden_run_frame(an3_eden_core* core, an3_eden_frame_callback callback, void* user_data) {
    if (!valid(core)) {
        return AN3_EDEN_ERR_INVALID_HANDLE;
    }
    if (core->state != State::Started) {
        return AN3_EDEN_ERR_NOT_INITIALIZED;
    }
    return guard(core, [&] { return an3::eden::active_backend().run_frame(core, callback, user_data); });
}

an3_eden_status an3_eden_submit_button(an3_eden_core* core, uint32_t port, uint32_t button, int pressed) {
    if (!valid(core)) {
        return AN3_EDEN_ERR_INVALID_HANDLE;
    }
    if (port > 7 || button > AN3_EDEN_BUTTON_R3) {
        return AN3_EDEN_ERR_INVALID_ARGUMENT;
    }
    if (core->state != State::Started) {
        return AN3_EDEN_ERR_NOT_INITIALIZED;
    }
    return guard(core, [&] { return an3::eden::active_backend().submit_button(core, port, button, pressed); });
}

an3_eden_status an3_eden_submit_analog(an3_eden_core* core, uint32_t port, uint32_t stick, int16_t x, int16_t y) {
    if (!valid(core)) {
        return AN3_EDEN_ERR_INVALID_HANDLE;
    }
    if (port > 7 || stick > AN3_EDEN_STICK_RIGHT) {
        return AN3_EDEN_ERR_INVALID_ARGUMENT;
    }
    if (core->state != State::Started) {
        return AN3_EDEN_ERR_NOT_INITIALIZED;
    }
    return guard(core, [&] { return an3::eden::active_backend().submit_analog(core, port, stick, x, y); });
}

an3_eden_status an3_eden_get_button(an3_eden_core* core, uint32_t port, uint32_t button, int* out_pressed) {
    if (!valid(core)) {
        return AN3_EDEN_ERR_INVALID_HANDLE;
    }
    if (out_pressed == nullptr || port > 7 || button > AN3_EDEN_BUTTON_R3) {
        return AN3_EDEN_ERR_INVALID_ARGUMENT;
    }
    *out_pressed = 0;
    if (core->state == State::Created) {
        return AN3_EDEN_ERR_NOT_INITIALIZED;
    }
    return guard(core, [&] { return an3::eden::active_backend().get_button(core, port, button, out_pressed); });
}

an3_eden_status an3_eden_get_analog(an3_eden_core* core, uint32_t port, uint32_t stick, int16_t* out_x, int16_t* out_y) {
    if (!valid(core)) {
        return AN3_EDEN_ERR_INVALID_HANDLE;
    }
    if (out_x == nullptr || out_y == nullptr || port > 7 || stick > AN3_EDEN_STICK_RIGHT) {
        return AN3_EDEN_ERR_INVALID_ARGUMENT;
    }
    *out_x = 0;
    *out_y = 0;
    if (core->state == State::Created) {
        return AN3_EDEN_ERR_NOT_INITIALIZED;
    }
    return guard(core, [&] { return an3::eden::active_backend().get_analog(core, port, stick, out_x, out_y); });
}

an3_eden_status an3_eden_save_data(an3_eden_core* core, const char* path) {
    if (!valid(core)) {
        return AN3_EDEN_ERR_INVALID_HANDLE;
    }
    if (core->state == State::Created) {
        return AN3_EDEN_ERR_NOT_INITIALIZED;
    }
    return guard(core, [&] { return an3::eden::active_backend().save_data(core, path); });
}

an3_eden_status an3_eden_get_save_dir(an3_eden_core* core, char* out_path, uint32_t size) {
    if (!valid(core)) {
        return AN3_EDEN_ERR_INVALID_HANDLE;
    }
    if (out_path == nullptr || size == 0) {
        return AN3_EDEN_ERR_INVALID_ARGUMENT;
    }
    out_path[0] = '\0';
    if (core->state == State::Created) {
        return AN3_EDEN_ERR_NOT_INITIALIZED;
    }
    return guard(core, [&] { return an3::eden::active_backend().get_save_dir(core, out_path, size); });
}

an3_eden_status an3_eden_get_audio_info(an3_eden_core* core, an3_eden_audio_info* out_info) {
    if (!valid(core)) {
        return AN3_EDEN_ERR_INVALID_HANDLE;
    }
    if (out_info == nullptr) {
        return AN3_EDEN_ERR_INVALID_ARGUMENT;
    }
    *out_info = {};
    if (core->state == State::Created) {
        return AN3_EDEN_ERR_NOT_INITIALIZED;
    }
    return guard(core, [&] { return an3::eden::active_backend().get_audio_info(core, out_info); });
}

an3_eden_status an3_eden_stop(an3_eden_core* core) {
    if (!valid(core)) {
        return AN3_EDEN_ERR_INVALID_HANDLE;
    }
    /* Idempotent when there is nothing to stop; a loaded-but-not-started core
     * still needs the backend to release its kernel. */
    if (core->state != State::Started && core->state != State::Loaded) {
        return AN3_EDEN_OK;
    }
    an3_eden_status status = guard(core, [&] { return an3::eden::active_backend().stop(core); });
    if (status == AN3_EDEN_OK) {
        core->state = State::Stopped;
    }
    return status;
}

an3_eden_status an3_eden_shutdown(an3_eden_core* core) {
    if (!valid(core)) {
        return AN3_EDEN_ERR_INVALID_HANDLE;
    }
    if (core->state == State::Created) {
        return AN3_EDEN_OK; /* nothing to release; idempotent */
    }
    if (core->state == State::Started || core->state == State::Loaded) {
        (void)guard(core, [&] { return an3::eden::active_backend().stop(core); });
    }
    an3_eden_status status = guard(core, [&] { return an3::eden::active_backend().shutdown(core); });
    if (status == AN3_EDEN_OK) {
        core->state = State::Created;
        core->backend_state = nullptr;
    }
    return status;
}

}  // extern "C"
