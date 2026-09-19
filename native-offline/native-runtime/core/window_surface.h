// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <vulkan/vulkan.h>
#include <string>
#include <vector>

namespace an3 {
// Surface lifetime belongs to the platform. The renderer owns the VkSurfaceKHR.
class NativeWindowSurface {
public:
    virtual ~NativeWindowSurface() = default;
    virtual VkExtent2D extent() const = 0;
    virtual std::vector<const char*> instance_extensions() const = 0;
    virtual bool create_surface(VkInstance, PFN_vkGetInstanceProcAddr,
                                VkSurfaceKHR&, std::string&) = 0;
};
}
