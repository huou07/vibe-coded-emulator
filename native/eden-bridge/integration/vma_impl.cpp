/*
 * SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Single translation unit that instantiates VulkanMemoryAllocator for the
 * Eden-backed bridge.
 *
 * VMA is header-only, and Eden defines VMA_IMPLEMENTATION in exactly one
 * frontend translation unit (src/yuzu/main_window.cpp,
 * src/yuzu_cmd/yuzu.cpp or src/android/.../native.cpp). The bridge build is
 * configured with ENABLE_QT=OFF and YUZU_CMD=OFF, so none of those objects
 * exist and every vma* symbol referenced by video_core is undefined. This TU
 * restores exactly that one implementation. Do not compile it into a build
 * that already links an Eden frontend, or the vma* symbols will be duplicated.
 */
#define VMA_IMPLEMENTATION
#include "video_core/vulkan_common/vma.h"
