// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

int an3_native_probe(const char* core_path, char* details, size_t details_length);

int an3_native_start(void* content_view,
                     const char* core_path,
                     const char* moltenvk_path,
                     const char* rom_path,
                     const char* rom_id,
                     const char* save_directory,
                     const char* system_directory,
                     const char* system,
                     const char* layout,
                     char* details,
                     size_t details_length);

void an3_native_stop(void);
int an3_native_is_running(void);
uint64_t an3_native_presented_frames(void);

typedef struct an3_native_renderer_metrics {
    uint64_t presented_frames;
    uint64_t dropped_frames;
    uint64_t software_uploads;
    uint64_t direct_software_uploads;
    uint64_t copied_software_uploads;
    uint64_t converted_software_uploads;
    uint32_t upload_p95_us;
    uint32_t upload_p99_us;
    uint32_t present_p95_us;
    uint32_t present_p99_us;
    uint32_t emulate_p95_us;
    uint32_t emulate_p99_us;
    uint32_t audio_queue_depth_frames;
    uint32_t audio_queue_max_frames;
    uint64_t audio_underruns;
    uint64_t audio_overruns;
    double audio_core_sample_rate;
    double audio_output_sample_rate;
    double audio_hardware_sample_rate;
    double audio_effective_input_rate;
    uint32_t audio_core_channels;
    uint32_t audio_output_channels;
    uint64_t audio_sample_callbacks;
    uint64_t audio_batch_callbacks;
    uint64_t audio_input_frames;
    uint64_t audio_output_frames;
    uint64_t audio_input_nonzero_samples;
    uint64_t audio_output_nonzero_samples;
    uint64_t audio_input_energy;
    uint64_t audio_output_energy;
    uint32_t audio_input_peak;
    uint32_t audio_output_peak;
    uint64_t audio_converter_failures;
    int32_t audio_converter_last_status;
    int32_t audio_converter_last_error;
    uint64_t audio_scheduled_buffers;
    int audio_player_playing;
    int audio_engine_running;
    int audio_muted;
    float audio_volume;
    uint64_t resident_memory_bytes;
    uint64_t cpu_user_time_us;
    uint64_t cpu_system_time_us;
} an3_native_renderer_metrics;

// Returns zero unless a native core is currently running. This is an internal
// diagnostics ABI; it never serializes game state or includes ROM metadata.
int an3_native_get_renderer_metrics(an3_native_renderer_metrics* metrics);

// Stores/loads raw bytes supplied by the core's retro_serialize ABI. Quick-save
// slots are fixed to 1..10; no AN3 wrapper or state-version format is added
// around those bytes. The explicit import/export calls use the same raw bytes.
int an3_native_save_state(unsigned slot, char* details, size_t details_length);
int an3_native_load_state(unsigned slot, char* details, size_t details_length);
int an3_native_export_state(const char* path, char* details, size_t details_length);
int an3_native_import_state(const char* path, char* details, size_t details_length);

void an3_native_set_input(uint32_t buttons,
                          int16_t circle_x,
                          int16_t circle_y,
                          int16_t cstick_x,
                          int16_t cstick_y,
                          int16_t touch_x,
                          int16_t touch_y,
                          int touch_pressed);

#ifdef __cplusplus
}
#endif
