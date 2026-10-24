// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "../../core/window_surface.h"

#include <SDL2/SDL.h>
#include <SDL2/SDL_vulkan.h>

#include <algorithm>
#include <string>
#include <vector>

namespace an3 {

// SDL owns the Linux X11/Wayland selection, while this small adapter exposes
// only the portable libretro presenter's surface contract. It does not expose
// a CPU copy of a Vulkan core frame.
class LinuxSdlWindowSurface final : public NativeWindowSurface {
  public:
    ~LinuxSdlWindowSurface() override { shutdown(); }

    bool initialize(const char* title, int width, int height, std::string& error) {
        if (SDL_InitSubSystem(SDL_INIT_VIDEO | SDL_INIT_GAMECONTROLLER) != 0) {
            error = std::string("SDL video/input initialization failed: ") + SDL_GetError();
            return false;
        }
        title_ = title ? title : "VibeCodedEmulator";
        width_ = std::max(320, width); height_ = std::max(240, height);
        window_ = create(SDL_WINDOW_VULKAN, error);
        if (!window_) {
            // A missing Vulkan loader must still reach the existing OpenGL
            // fallback. This plain window cannot accept Vulkan frames.
            window_ = create(0, error);
            if (!window_) return false;
        }
        return true;
    }

    bool recreate_for_opengl(std::string& error) {
        if (window_) SDL_DestroyWindow(window_);
        window_ = create(SDL_WINDOW_OPENGL, error);
        return window_ != nullptr;
    }

    void shutdown() {
        if (window_) SDL_DestroyWindow(window_);
        window_ = nullptr;
    }

    SDL_Window* window() const { return window_; }

    VkExtent2D extent() const override {
        int width = 0, height = 0;
        if (window_) SDL_Vulkan_GetDrawableSize(window_, &width, &height);
        return {static_cast<uint32_t>(std::max(1, width)), static_cast<uint32_t>(std::max(1, height))};
    }

    std::vector<const char*> instance_extensions() const override {
        unsigned count = 0;
        if (!window_ || SDL_Vulkan_GetInstanceExtensions(window_, &count, nullptr) != SDL_TRUE || !count) return {};
        extensions_.resize(count);
        if (SDL_Vulkan_GetInstanceExtensions(window_, &count, extensions_.data()) != SDL_TRUE) return {};
        return extensions_;
    }

    bool create_surface(VkInstance instance, PFN_vkGetInstanceProcAddr, VkSurfaceKHR& surface,
                        std::string& error) override {
        surface = VK_NULL_HANDLE;
        if (!window_ || SDL_Vulkan_CreateSurface(window_, instance, &surface) != SDL_TRUE) {
            error = std::string("SDL Vulkan surface creation failed: ") + SDL_GetError();
            return false;
        }
        return true;
    }

  private:
    SDL_Window* create(Uint32 backend_flag, std::string& error) {
        SDL_Window* result = SDL_CreateWindow(title_.c_str(), SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                                              width_, height_, SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI | backend_flag);
        if (!result) error = std::string("SDL native window creation failed: ") + SDL_GetError();
        return result;
    }
    SDL_Window* window_ = nullptr;
    std::string title_;
    int width_ = 1280, height_ = 720;
    mutable std::vector<const char*> extensions_;
};

} // namespace an3
