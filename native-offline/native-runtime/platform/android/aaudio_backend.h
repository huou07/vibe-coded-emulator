// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "../../core/video_backend.h"

#include <aaudio/AAudio.h>
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>

namespace an3 {

enum class AAudioResamplerQuality : uint8_t {
    Low = 0,
    Medium = 1,
    High = 2,
};

struct AAudioMetrics {
    uint32_t sample_rate = 0;
    uint32_t capacity_frames = 0;
    // submitted_frames counts accepted core/input frames. The output queue
    // has its own counters because resampling changes the frame count.
    uint64_t submitted_frames = 0;
    uint64_t rendered_frames = 0;
    uint64_t overflow_frames = 0;
    uint64_t underrun_frames = 0;
    uint64_t underrun_callbacks = 0;
    uint64_t submitted_nonzero_samples = 0;
    uint64_t rendered_nonzero_samples = 0;
    aaudio_result_t last_error = AAUDIO_OK;
    // The core rate is allowed to be fractional. sample_rate is the actual
    // integer rate negotiated with AAudio, not a rounded copy of this value.
    uint32_t requested_sample_rate = 0;
    double core_sample_rate = 0.0;
    double input_frames_per_output_frame = 0.0;
    double emulation_speed = 1.0;
    uint32_t latency_ms = 64;
    float volume = 1.0f;
    bool muted = false;
    AAudioResamplerQuality resampler_quality = AAudioResamplerQuality::Medium;
    uint64_t output_queued_frames = 0;
    uint64_t queued_frames = 0;
};

class AAudioBackend final : public NativeAudioBackend {
public:
    AAudioBackend() = default;
    ~AAudioBackend() override;

    AAudioBackend(const AAudioBackend&) = delete;
    AAudioBackend& operator=(const AAudioBackend&) = delete;

    bool initialize(double sample_rate, std::string& error) override;
    std::size_t submit(const int16_t* interleaved_stereo, std::size_t frames) override;
    void shutdown() override;

    // These setters are intended for the emulation/control thread. They do
    // not stop or rebuild the stream. The callback observes gain/mute through
    // atomics, while the producer applies speed and quality on its next batch.
    bool set_volume(float volume) noexcept;
    void set_muted(bool muted) noexcept;
    bool set_latency_ms(uint32_t latency_ms) noexcept;
    bool set_emulation_speed(double speed) noexcept;
    bool set_resampler_quality(AAudioResamplerQuality quality) noexcept;

    AAudioMetrics metrics() const noexcept;

private:
    static constexpr uint32_t kChannelCount = 2;
    static constexpr uint32_t kMaxSampleRate = 192000;
    static constexpr uint32_t kMaxBufferedFrames = kMaxSampleRate / 4;
    static constexpr uint32_t kDefaultLatencyMs = 64;
    static aaudio_data_callback_result_t data_callback(
        AAudioStream* stream, void* user_data, void* audio_data, int32_t num_frames);
    static void error_callback(AAudioStream* stream, void* user_data, aaudio_result_t error);
    aaudio_data_callback_result_t render(int16_t* output, int32_t frames) noexcept;
    static int16_t interpolate(AAudioResamplerQuality quality,
                                int16_t history, bool have_history,
                                int16_t previous, int16_t current,
                                int16_t next, bool have_next, double phase) noexcept;
    static int16_t apply_volume(int16_t sample, float volume) noexcept;
    static bool is_supported_latency(uint32_t latency_ms) noexcept;
    static bool is_supported_speed(double speed) noexcept;
    static bool is_supported_quality(AAudioResamplerQuality quality) noexcept;
    uint32_t capacity_for_latency(uint32_t latency_ms) const noexcept;
    void update_input_ratio() noexcept;

    std::array<int16_t, kMaxBufferedFrames * kChannelCount> samples_{};
    std::atomic<uint64_t> read_frame_{0};
    std::atomic<uint64_t> write_frame_{0};
    std::atomic<bool> active_{false};
    AAudioStream* stream_ = nullptr;
    // Published before active_ becomes true and retained across shutdown so a
    // submit already in flight can finish without racing mutable ring geometry.
    uint32_t requested_sample_rate_ = 0;
    uint32_t sample_rate_ = 0;
    std::atomic<uint32_t> capacity_frames_{0};
    double core_sample_rate_ = 0.0;
    // Number of core frames represented by one native output frame.
    std::atomic<double> input_frames_per_output_frame_{1.0};
    std::atomic<double> emulation_speed_{1.0};
    std::atomic<uint32_t> latency_ms_{kDefaultLatencyMs};
    std::atomic<float> volume_{1.0f};
    std::atomic<bool> muted_{false};
    std::atomic<uint8_t> resampler_quality_{
        static_cast<uint8_t>(AAudioResamplerQuality::Medium)};

    // Owned by the producer (submit) thread. Keeping only the adjacent source
    // frames plus one retained history/look-ahead frame makes interpolation
    // streaming and bounded; no callback storage or allocation is needed.
    bool have_history_input_ = false;
    bool have_previous_input_ = false;
    bool have_current_input_ = false;
    bool have_next_input_ = false;
    int16_t history_left_ = 0;
    int16_t history_right_ = 0;
    int16_t previous_left_ = 0;
    int16_t previous_right_ = 0;
    int16_t current_left_ = 0;
    int16_t current_right_ = 0;
    int16_t next_left_ = 0;
    int16_t next_right_ = 0;
    double input_phase_ = 0.0;

    std::atomic<uint64_t> submitted_frames_{0};
    std::atomic<uint64_t> output_queued_frames_{0};
    std::atomic<uint64_t> rendered_frames_{0};
    std::atomic<uint64_t> overflow_frames_{0};
    std::atomic<uint64_t> underrun_frames_{0};
    std::atomic<uint64_t> underrun_callbacks_{0};
    std::atomic<uint64_t> submitted_nonzero_samples_{0};
    std::atomic<uint64_t> rendered_nonzero_samples_{0};
    std::atomic<int32_t> last_error_{AAUDIO_OK};
};

} // namespace an3
