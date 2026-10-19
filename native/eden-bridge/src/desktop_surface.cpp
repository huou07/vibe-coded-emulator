/*
 * SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "desktop_surface.h"

#include <SDL3/SDL.h>
#include <SDL3/SDL_properties.h>

#include <cstdlib>

namespace {

struct DesktopSurface {
    SDL_Window* window = nullptr;
};

an3_eden_desktop_key_handler g_key_handler = nullptr;
SDL_Window* g_window = nullptr;
bool g_sdl_started = false;

bool visible_requested() {
    const char* value = std::getenv("AN3_EDEN_WINDOW_VISIBLE");
    return value != nullptr && value[0] != '\0' && value[0] != '0';
}

void clear_info(an3_eden_desktop_surface_info* info) {
    if (info == nullptr) {
        return;
    }
    info->type = 0;
    info->display_connection = nullptr;
    info->render_surface = nullptr;
}

bool fill_info(SDL_Window* window, an3_eden_desktop_surface_info* info) {
    clear_info(info);
    if (window == nullptr || info == nullptr) {
        return false;
    }

    const SDL_PropertiesID properties = SDL_GetWindowProperties(window);
    if (void* hwnd = SDL_GetPointerProperty(
            properties, SDL_PROP_WINDOW_WIN32_HWND_POINTER, nullptr)) {
        info->type = AN3_EDEN_DESKTOP_WINDOW_WINDOWS;
        info->render_surface = hwnd;
        return true;
    }
    if (void* wl_display = SDL_GetPointerProperty(
            properties, SDL_PROP_WINDOW_WAYLAND_DISPLAY_POINTER, nullptr)) {
        void* wl_surface = SDL_GetPointerProperty(
            properties, SDL_PROP_WINDOW_WAYLAND_SURFACE_POINTER, nullptr);
        if (wl_surface == nullptr) {
            return false;
        }
        info->type = AN3_EDEN_DESKTOP_WINDOW_WAYLAND;
        info->display_connection = wl_display;
        info->render_surface = wl_surface;
        return true;
    }
    if (void* x11_display = SDL_GetPointerProperty(
            properties, SDL_PROP_WINDOW_X11_DISPLAY_POINTER, nullptr)) {
        const auto x11_window = SDL_GetNumberProperty(
            properties, SDL_PROP_WINDOW_X11_WINDOW_NUMBER, 0);
        if (x11_window == 0) {
            return false;
        }
        info->type = AN3_EDEN_DESKTOP_WINDOW_X11;
        info->display_connection = x11_display;
        info->render_surface = reinterpret_cast<void*>(
            static_cast<uintptr_t>(x11_window));
        return true;
    }
    return false;
}

}  // namespace

extern "C" void* an3_eden_desktop_create_surface(
    uint32_t width, uint32_t height, int visible,
    an3_eden_desktop_surface_info* out_info) {
    clear_info(out_info);
    if (!g_sdl_started) {
        if (!SDL_InitSubSystem(SDL_INIT_VIDEO)) {
            return nullptr;
        }
        g_sdl_started = true;
    }

    SDL_Window* window = SDL_CreateWindow(
        "AN3 — Nintendo Switch", static_cast<int>(width == 0 ? 1280 : width),
        static_cast<int>(height == 0 ? 720 : height),
        SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY);
    if (window == nullptr) {
        return nullptr;
    }
    if (visible || visible_requested()) {
        SDL_ShowWindow(window);
        SDL_RaiseWindow(window);
    } else {
        SDL_HideWindow(window);
    }
    if (!fill_info(window, out_info)) {
        SDL_DestroyWindow(window);
        return nullptr;
    }

    auto* surface = new DesktopSurface{window};
    g_window = window;
    return surface;
}

extern "C" void an3_eden_desktop_destroy_surface(void* opaque_surface) {
    auto* surface = static_cast<DesktopSurface*>(opaque_surface);
    if (surface == nullptr) {
        return;
    }
    if (g_window == surface->window) {
        g_window = nullptr;
    }
    SDL_DestroyWindow(surface->window);
    delete surface;
    g_key_handler = nullptr;
    if (g_sdl_started) {
        SDL_QuitSubSystem(SDL_INIT_VIDEO);
        g_sdl_started = false;
    }
}

extern "C" void an3_eden_desktop_set_key_handler(
    an3_eden_desktop_key_handler handler) {
    g_key_handler = handler;
}

extern "C" void an3_eden_desktop_run(int (*should_stop)(void)) {
    SDL_Event event{};
    while (should_stop == nullptr || !should_stop()) {
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_EVENT_QUIT) {
                return;
            }
            if ((event.type == SDL_EVENT_KEY_DOWN ||
                 event.type == SDL_EVENT_KEY_UP) &&
                g_key_handler != nullptr) {
                g_key_handler(static_cast<int>(event.key.scancode),
                              event.key.down ? 1 : 0);
            }
        }
        SDL_Delay(10);
    }
}

extern "C" void an3_eden_desktop_focus(void) {
    if (g_window != nullptr) {
        SDL_ShowWindow(g_window);
        SDL_RaiseWindow(g_window);
    }
}
