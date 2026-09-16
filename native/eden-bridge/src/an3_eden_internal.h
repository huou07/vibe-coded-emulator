/*
 * SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Internal shared definitions for the Eden bridge. Not installed.
 */
#ifndef AN3_EDEN_INTERNAL_H
#define AN3_EDEN_INTERNAL_H

#include "an3_eden_bridge.h"

namespace an3::eden {

/* Lifecycle states, in order. */
enum class State : int {
    Created = 0,
    Initialized = 1,
    Loaded = 2,
    Started = 3,
    Stopped = 4,
};

/* Backend vtable. Every entry point is called with a non-null, valid core from
 * the core's owning thread. Implementations must not throw and must not write
 * to `core->last_error` (the dispatcher does that). */
struct Backend {
    const char* name;
    an3_eden_status (*initialize)(an3_eden_core*, const char* keys_dir, const char* firmware_dir);
    an3_eden_status (*load)(an3_eden_core*, const char* content_path);
    an3_eden_status (*start)(an3_eden_core*);
    an3_eden_status (*pause)(an3_eden_core*, int paused);
    an3_eden_status (*run_frame)(an3_eden_core*, an3_eden_frame_callback, void* user_data);
    an3_eden_status (*submit_button)(an3_eden_core*, uint32_t port, uint32_t button, int pressed);
    an3_eden_status (*submit_analog)(an3_eden_core*, uint32_t port, int16_t x, int16_t y);
    an3_eden_status (*save_data)(an3_eden_core*, const char* path);
    an3_eden_status (*stop)(an3_eden_core*);
    an3_eden_status (*shutdown)(an3_eden_core*);
};

/* Provided by exactly one backend translation unit. */
const Backend& active_backend();

}  // namespace an3::eden

/* Core handle definition. `magic` distinguishes a live handle from garbage. */
struct an3_eden_core {
    uint32_t magic;
    an3::eden::State state;
    void* backend_state;
    char last_error[512];
};

#define AN3_EDEN_CORE_MAGIC 0x414E3345u /* "AN3E" */

namespace an3::eden {
void set_error(an3_eden_core* core, const char* message);
}  // namespace an3::eden

#endif  // AN3_EDEN_INTERNAL_H
