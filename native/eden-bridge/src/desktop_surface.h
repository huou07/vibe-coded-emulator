/*
 * SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * SDL3-owned desktop presentation surface for the Eden bridge.
 * SDL3 is used only as the platform windowing/input adapter; Eden still owns
 * Vulkan device, swapchain, rendering and audio.
 */
#ifndef AN3_EDEN_DESKTOP_SURFACE_H
#define AN3_EDEN_DESKTOP_SURFACE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    AN3_EDEN_DESKTOP_WINDOW_WINDOWS = 1,
    AN3_EDEN_DESKTOP_WINDOW_X11 = 2,
    AN3_EDEN_DESKTOP_WINDOW_WAYLAND = 3,
};

typedef struct an3_eden_desktop_surface_info {
    int type;
    void* display_connection;
    void* render_surface;
} an3_eden_desktop_surface_info;

void* an3_eden_desktop_create_surface(uint32_t width, uint32_t height,
                                      int visible,
                                      an3_eden_desktop_surface_info* out_info);
void an3_eden_desktop_destroy_surface(void* surface);

typedef void (*an3_eden_desktop_key_handler)(int scancode, int is_down);
void an3_eden_desktop_set_key_handler(an3_eden_desktop_key_handler handler);
void an3_eden_desktop_run(int (*should_stop)(void));
void an3_eden_desktop_focus(void);

#ifdef __cplusplus
}
#endif

#endif /* AN3_EDEN_DESKTOP_SURFACE_H */
