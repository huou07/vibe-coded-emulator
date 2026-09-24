/*
 * SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * an3_eden_bridge — a stable C ABI between Vibe Coded Emulator and an Eden
 * (Nintendo Switch) emulation backend.
 *
 * Design rules (see README.md):
 *  - Only opaque handles cross the boundary; no C++ type is exposed.
 *  - Every function returns an `an3_eden_status`; errors never throw.
 *  - The ABI is versioned; query `an3_eden_bridge_abi_version()` before use.
 *  - A core handle must be used from a single thread at a time.
 *
 * This header is usable from C and C++.
 */
#ifndef AN3_EDEN_BRIDGE_H
#define AN3_EDEN_BRIDGE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Bump when the ABI changes incompatibly. */
#define AN3_EDEN_BRIDGE_ABI_VERSION 3u

typedef enum an3_eden_status {
    AN3_EDEN_OK = 0,
    AN3_EDEN_ERR_INVALID_ARGUMENT = 1,
    AN3_EDEN_ERR_INVALID_HANDLE = 2,
    AN3_EDEN_ERR_ALREADY_INITIALIZED = 3,
    AN3_EDEN_ERR_NOT_INITIALIZED = 4,
    /* This build has no Eden backend, or the core cannot be initialised on
     * this platform (for example no usable Vulkan device). */
    AN3_EDEN_ERR_UNAVAILABLE = 5,
    AN3_EDEN_ERR_UNSUPPORTED = 6,
    AN3_EDEN_ERR_IO = 7,
    AN3_EDEN_ERR_INTERNAL = 8,
    AN3_EDEN_ERR_BUSY = 9,
    /* The backend requires decryption keys or firmware the caller did not
     * provide. Callers must never bundle those files. */
    AN3_EDEN_ERR_KEYS_REQUIRED = 10
} an3_eden_status;

/* Opaque core handle. Created by an3_eden_create, freed by an3_eden_destroy. */
typedef struct an3_eden_core an3_eden_core;

typedef enum an3_eden_pixel_format {
    AN3_EDEN_FORMAT_BGRA8 = 1,
    AN3_EDEN_FORMAT_RGBA8 = 2
} an3_eden_pixel_format;

/* A borrowed view of one presented frame. The pixels pointer is only valid for
 * the duration of the callback; copy anything you need to keep. */
typedef struct an3_eden_frame {
    const void* pixels;
    uint32_t width;
    uint32_t height;
    uint32_t stride; /* bytes per row */
    uint32_t format; /* an3_eden_pixel_format */
} an3_eden_frame;

typedef void (*an3_eden_frame_callback)(const an3_eden_frame* frame, void* user_data);

/* Button ids are the libretro joypad ids used elsewhere in this project. */
enum {
    AN3_EDEN_BUTTON_B = 0,
    AN3_EDEN_BUTTON_Y = 1,
    AN3_EDEN_BUTTON_SELECT = 2,
    AN3_EDEN_BUTTON_START = 3,
    AN3_EDEN_BUTTON_UP = 4,
    AN3_EDEN_BUTTON_DOWN = 5,
    AN3_EDEN_BUTTON_LEFT = 6,
    AN3_EDEN_BUTTON_RIGHT = 7,
    AN3_EDEN_BUTTON_A = 8,
    AN3_EDEN_BUTTON_X = 9,
    AN3_EDEN_BUTTON_L = 10,
    AN3_EDEN_BUTTON_R = 11,
    AN3_EDEN_BUTTON_L2 = 12,
    AN3_EDEN_BUTTON_R2 = 13,
    AN3_EDEN_BUTTON_L3 = 14,
    AN3_EDEN_BUTTON_R3 = 15
};

/* Analog stick selector for an3_eden_submit_analog. */
enum {
    AN3_EDEN_STICK_LEFT = 0,
    AN3_EDEN_STICK_RIGHT = 1
};

/* --- Version and diagnostics ------------------------------------------- */

/* Returns AN3_EDEN_BRIDGE_ABI_VERSION. */
uint32_t an3_eden_bridge_abi_version(void);

/* Backend identifier: "eden" when built against Eden, "null" otherwise. */
const char* an3_eden_backend_name(void);

/* Human-readable, static-lifetime description of a status value. Never NULL. */
const char* an3_eden_status_message(an3_eden_status status);

/* Last diagnostic for a core (may be empty). Static lifetime until the next
 * call on the same core; never NULL. */
const char* an3_eden_last_error(const an3_eden_core* core);

/* --- Lifecycle ---------------------------------------------------------- */

/* Creates an uninitialised core. Always destroy it, even if initialise fails. */
an3_eden_status an3_eden_create(an3_eden_core** out_core);

/* Supplies the native presentation surface before initialise on Android.
 * `native_window` is an ANativeWindow* borrowed for the duration of the
 * initialise/session call; the caller retains ownership and must keep it
 * alive until shutdown has returned. Other platforms return UNSUPPORTED. */
an3_eden_status an3_eden_set_android_surface(an3_eden_core* core,
                                             void* native_window);

/* Prepares the emulator. `keys_dir` and `firmware_dir` are optional (NULL or
 * empty string); encrypted commercial content needs both, homebrew may not.
 * Safe to call once; a second call returns AN3_EDEN_ERR_ALREADY_INITIALIZED. */
an3_eden_status an3_eden_initialize(an3_eden_core* core,
                                    const char* keys_dir,
                                    const char* firmware_dir);

/* Loads content (an NRO/NCA path). Requires a successful initialise. */
an3_eden_status an3_eden_load(an3_eden_core* core, const char* content_path);

/* Starts emulation. Requires loaded content. */
an3_eden_status an3_eden_start(an3_eden_core* core);

/* Pauses (paused != 0) or resumes. Requires a started core. */
an3_eden_status an3_eden_pause(an3_eden_core* core, int paused);

/* Runs one frame and presents it through `callback` when non-NULL. */
an3_eden_status an3_eden_run_frame(an3_eden_core* core,
                                   an3_eden_frame_callback callback,
                                   void* user_data);

/* --- Input -------------------------------------------------------------- */

/* `button` is an AN3_EDEN_BUTTON_* id. */
an3_eden_status an3_eden_submit_button(an3_eden_core* core, uint32_t port,
                                       uint32_t button, int pressed);

/* Analogue stick, -32768..32767, +y is down. `stick` is AN3_EDEN_STICK_*.
 * Values are clamped; (0, 0) is neutral. */
an3_eden_status an3_eden_submit_analog(an3_eden_core* core, uint32_t port,
                                       uint32_t stick, int16_t x, int16_t y);

/* --- Input diagnostics -------------------------------------------------- */

/* Reads back the emulated controller's own button state, proving that input
 * reached the emulator rather than only being accepted by the bridge.
 * `out_pressed` receives 1 when pressed, 0 when released. */
an3_eden_status an3_eden_get_button(an3_eden_core* core, uint32_t port,
                                    uint32_t button, int* out_pressed);

/* Reads back the emulated controller's own analog state as the raw emulated
 * range (-32767..32767), which is what the emulated game receives. */
an3_eden_status an3_eden_get_analog(an3_eden_core* core, uint32_t port,
                                    uint32_t stick, int16_t* out_x, int16_t* out_y);

/* --- Saves -------------------------------------------------------------- */

/* Writes the emulated save data under `path` when the backend supports it.
 * Save states are not part of this ABI. */
an3_eden_status an3_eden_save_data(an3_eden_core* core, const char* path);

/* Copies the backend's save-data directory path into `out_path` (NUL
 * terminated, truncated to `size`). Returns AN3_EDEN_ERR_UNSUPPORTED when the
 * backend has no save store, and AN3_EDEN_ERR_INVALID_ARGUMENT for a null
 * buffer or zero size. */
an3_eden_status an3_eden_get_save_dir(an3_eden_core* core, char* out_path, uint32_t size);

/* --- Audio diagnostics -------------------------------------------------- */

/* Machine-readable audio state. Fixed-size buffers keep the ABI stable. */
typedef struct an3_eden_audio_info {
    char backend[16];   /* configured engine: auto | cubeb | sdl3 | null */
    char device[256];   /* configured output device id (may be empty) */
    uint32_t channels;  /* device channel count reported by the sink */
    float volume;       /* current device volume (0.0 - 1.0) */
} an3_eden_audio_info;

/* Fills `out_info`. Eden owns audio output directly; this reports the sink it
 * selected, not a claim that audible sound was produced. */
an3_eden_status an3_eden_get_audio_info(an3_eden_core* core, an3_eden_audio_info* out_info);

/* --- Shutdown ----------------------------------------------------------- */

/* Stops emulation and releases per-session resources. Safe to call when not
 * started; safe to call repeatedly. Does not free the handle. */
an3_eden_status an3_eden_stop(an3_eden_core* core);

/* Releases everything initialise acquired. Safe to call repeatedly. */
an3_eden_status an3_eden_shutdown(an3_eden_core* core);

/* Frees the handle. NULL is ignored. Never call any other function with a
 * handle after this. */
void an3_eden_destroy(an3_eden_core* core);

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* AN3_EDEN_BRIDGE_H */
