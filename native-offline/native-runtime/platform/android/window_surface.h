// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#define VK_USE_PLATFORM_ANDROID_KHR 1
#include "../../core/window_surface.h"
#include <android/native_window.h>
#include <vulkan/vulkan_android.h>

namespace an3 {
class AndroidWindowSurface final : public NativeWindowSurface {
    ANativeWindow* window_;
public:
    explicit AndroidWindowSurface(ANativeWindow* window) : window_(window) {
        if (window_) ANativeWindow_acquire(window_);
    }
    ~AndroidWindowSurface() override { if (window_) ANativeWindow_release(window_); }
    ANativeWindow* native_window() const { return window_; }
    VkExtent2D extent() const override {
        if (!window_) return {0,0};
        const auto w=ANativeWindow_getWidth(window_), h=ANativeWindow_getHeight(window_);
        return {w>0?static_cast<uint32_t>(w):0u,h>0?static_cast<uint32_t>(h):0u};
    }
    std::vector<const char*> instance_extensions() const override {
        return {VK_KHR_SURFACE_EXTENSION_NAME,VK_KHR_ANDROID_SURFACE_EXTENSION_NAME};
    }
    bool create_surface(VkInstance instance, PFN_vkGetInstanceProcAddr proc,
                        VkSurfaceKHR& surface, std::string& error) override {
        const auto create=reinterpret_cast<PFN_vkCreateAndroidSurfaceKHR>(proc(instance,"vkCreateAndroidSurfaceKHR"));
        if (!window_ || !create) { error="android-surface: window or Vulkan entry point unavailable"; return false; }
        VkAndroidSurfaceCreateInfoKHR info{};
        info.sType=VK_STRUCTURE_TYPE_ANDROID_SURFACE_CREATE_INFO_KHR;
        info.window=window_;
        const auto result=create(instance,&info,nullptr,&surface);
        if (result!=VK_SUCCESS) { error="android-surface: vkCreateAndroidSurfaceKHR failed ("+std::to_string(result)+")"; return false; }
        return true;
    }
};
}
