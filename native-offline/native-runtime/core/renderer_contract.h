// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <cstddef>
#include <cstdint>

namespace an3 {

// Platform-neutral subset of libretro's hardware-render callback ABI. Native
// software hosts do not negotiate this path, but retaining the declaration in
// the portable contract keeps a future native-GPU adapter from depending on
// the macOS presenter header.
using RetroHwContextReset = void (*)();
using RetroHwGetCurrentFramebuffer = uintptr_t (*)();
using RetroHwGetProcAddress = void* (*)(const char*);

struct RetroHwRenderCallback {
    int context_type;
    RetroHwContextReset context_reset;
    RetroHwGetCurrentFramebuffer get_current_framebuffer;
    RetroHwGetProcAddress get_proc_address;
    bool depth;
    bool stencil;
    bool bottom_left_origin;
    unsigned version_major;
    unsigned version_minor;
    bool cache_context;
    RetroHwContextReset context_destroy;
    bool debug_context;
};

// A portable libretro host keeps the callback and the optional device
// negotiation payload together until the core has loaded its game.  The
// platform renderer must use the core-provided Vulkan image/synchronization
// interface directly; this boundary deliberately has no CPU-frame escape
// hatch.
struct NativeHardwareRenderRequest {
    RetroHwRenderCallback callbacks{};
    const void* negotiation_interface = nullptr;
};

// Renderer-local timings remain separate from core emulation timing. The
// platform host augments this fixed metric envelope; renderers only own their
// upload/present fields, so no platform may infer core FPS from presentation.
struct NativeRendererMetrics {
    uint64_t presented_frames = 0;
    uint64_t dropped_frames = 0;
    uint64_t software_uploads = 0;
    uint64_t direct_software_uploads = 0;
    uint64_t copied_software_uploads = 0;
    uint64_t converted_software_uploads = 0;
    uint32_t upload_p95_us = 0;
    uint32_t upload_p99_us = 0;
    uint32_t present_p95_us = 0;
    uint32_t present_p99_us = 0;
    uint32_t emulate_p95_us = 0;
    uint32_t emulate_p99_us = 0;
    uint32_t audio_queue_depth_frames = 0;
    uint32_t audio_queue_max_frames = 0;
    uint64_t audio_underruns = 0;
    uint64_t audio_overruns = 0;
    double audio_core_sample_rate = 0.0;
    double audio_output_sample_rate = 0.0;
    double audio_hardware_sample_rate = 0.0;
    double audio_effective_input_rate = 0.0;
    uint32_t audio_core_channels = 2;
    uint32_t audio_output_channels = 2;
    uint64_t audio_sample_callbacks = 0;
    uint64_t audio_batch_callbacks = 0;
    uint64_t audio_input_frames = 0;
    uint64_t audio_output_frames = 0;
    uint64_t audio_input_nonzero_samples = 0;
    uint64_t audio_output_nonzero_samples = 0;
    uint64_t audio_input_energy = 0;
    uint64_t audio_output_energy = 0;
    uint32_t audio_input_peak = 0;
    uint32_t audio_output_peak = 0;
    uint64_t audio_converter_failures = 0;
    int32_t audio_converter_last_status = 0;
    int32_t audio_converter_last_error = 0;
    uint64_t audio_scheduled_buffers = 0;
    bool audio_player_playing = false;
    bool audio_engine_running = false;
    bool audio_muted = false;
    float audio_volume = 1.0f;
    uint64_t resident_memory_bytes = 0;
    uint64_t cpu_user_time_us = 0;
    uint64_t cpu_system_time_us = 0;
};

} // namespace an3
