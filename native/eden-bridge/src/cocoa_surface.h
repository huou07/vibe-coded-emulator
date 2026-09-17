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

#ifdef __cplusplus
}
#endif

#endif /* AN3_EDEN_COCOA_SURFACE_H */
