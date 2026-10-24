/*
 * SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Minimal macOS presentation surface for the Eden bridge.
 *
 * Eden's Vulkan renderer has no headless path in the pinned revision:
 * CreateSurface() only accepts a Cocoa CAMetalLayer on macOS. This creates an
 * offscreen CAMetalLayer (no NSWindow or NSApplication required) that MoltenVK
 * accepts as a VkSurfaceKHR and reports as present-capable.
 *
 * Only compiled on Apple platforms (see integration/CMakeLists.txt).
 */
#ifndef AN3_EDEN_COCOA_SURFACE_H
#define AN3_EDEN_COCOA_SURFACE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Returns a +1 CAMetalLayer as an opaque pointer, or NULL when no Metal device
 * is available. The caller owns the reference and must pass it to
 * an3_eden_cocoa_destroy_layer. */
void* an3_eden_cocoa_create_layer(uint32_t width, uint32_t height);

/* Releases a layer returned by an3_eden_cocoa_create_layer. NULL is ignored. */
void an3_eden_cocoa_destroy_layer(void* layer);

/* Keyboard handler for the hosted window (companion mode). `key_code` is a
 * macOS virtual key code; `is_down` is 1 on key down and 0 on key up. Installed
 * on the surface's view, which becomes first responder when the window is
 * visible. Only one handler is registered at a time; NULL clears it. */
typedef void (*an3_eden_key_handler)(int key_code, int is_down);
void an3_eden_cocoa_set_key_handler(an3_eden_key_handler handler);

/* Runs the AppKit event loop until `should_stop` returns non-zero, then
 * returns. Required for the visible companion window to receive key events.
 * Must be called on the main thread. */
void an3_eden_cocoa_run(int (*should_stop)(void));

/* Brings the companion window to the front and makes it key. No-op when the
 * window is not visible. Must be called on the main thread. */
void an3_eden_cocoa_focus(void);

#ifdef __cplusplus
}
#endif

#endif /* AN3_EDEN_COCOA_SURFACE_H */
