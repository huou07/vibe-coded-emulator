// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#include "aaudio_backend.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>
#include <string>

namespace an3 {
namespace {

std::string aaudio_error(const char* operation, aaudio_result_t result) {
    return std::string(operation) + " failed: " + AAudio_convertResultToText(result) +
           " (" + std::to_string(result) + ")";
}

int16_t clamp_pcm(double value) noexcept {
    const double rounded = std::nearbyint(value);
    if (rounded <= static_cast<double>(std::numeric_limits<int16_t>::min())) {
        return std::numeric_limits<int16_t>::min();
    }
    if (rounded >= static_cast<double>(std::numeric_limits<int16_t>::max())) {
        return std::numeric_limits<int16_t>::max();
    }
    return static_cast<int16_t>(rounded);
}

} // namespace

AAudioBackend::~AAudioBackend() {
    shutdown();
}

bool AAudioBackend::initialize(double sample_rate, std::string& error) {
    shutdown();
    error.clear();

    if (!std::isfinite(sample_rate) || sample_rate < 1.0 ||
        sample_rate > static_cast<double>(kMaxSampleRate) ||
        sample_rate > static_cast<double>(std::numeric_limits<int32_t>::max())) {
        error = "AAudio requires a finite sample rate between 1 and 192000 Hz";
        return false;
    }

    const auto requested_rate = static_cast<int32_t>(std::llround(sample_rate));
    if (requested_rate < 1 || requested_rate > static_cast<int32_t>(kMaxSampleRate)) {
        error = "AAudio requires a rounded sample rate between 1 and 192000 Hz";
        return false;
    }

    const auto open_stream = [&](int32_t requested, AAudioStream** stream) {
        AAudioStreamBuilder* builder = nullptr;
        aaudio_result_t open_result = AAudio_createStreamBuilder(&builder);
        if (open_result != AAUDIO_OK || builder == nullptr) {
            return open_result == AAUDIO_OK ? AAUDIO_ERROR_NO_MEMORY : open_result;
        }

        AAudioStreamBuilder_setDirection(builder, AAUDIO_DIRECTION_OUTPUT);
        AAudioStreamBuilder_setFormat(builder, AAUDIO_FORMAT_PCM_I16);
        AAudioStreamBuilder_setChannelCount(builder, kChannelCount);
        AAudioStreamBuilder_setSampleRate(builder, requested);
        AAudioStreamBuilder_setSharingMode(builder, AAUDIO_SHARING_MODE_SHARED);
        AAudioStreamBuilder_setPerformanceMode(builder, AAUDIO_PERFORMANCE_MODE_LOW_LATENCY);
        AAudioStreamBuilder_setDataCallback(builder, &AAudioBackend::data_callback, this);
        AAudioStreamBuilder_setErrorCallback(builder, &AAudioBackend::error_callback, this);

        open_result = AAudioStreamBuilder_openStream(builder, stream);
        AAudioStreamBuilder_delete(builder);
        return open_result;
    };

    AAudioStream* opened_stream = nullptr;
    aaudio_result_t result = open_stream(requested_rate, &opened_stream);
    const aaudio_result_t requested_result = result;
    if ((result != AAUDIO_OK || opened_stream == nullptr) && requested_rate != AAUDIO_UNSPECIFIED) {
        // Some AAudio devices cannot open an exact, unusual integer rate even
        // though shared mode can negotiate a valid device rate. Let the
        // stream choose in that case and use the reported actual rate below.
        if (opened_stream != nullptr) AAudioStream_close(opened_stream);
        opened_stream = nullptr;
        result = open_stream(AAUDIO_UNSPECIFIED, &opened_stream);
    }
    if (result != AAUDIO_OK || opened_stream == nullptr) {
        error = aaudio_error("AAudioStreamBuilder_openStream", result);
        if (requested_result != result) {
            error += "; requested integer rate failed with " +
                     std::to_string(requested_result);
        }
        last_error_.store(result, std::memory_order_relaxed);
        return false;
    }

    const int32_t actual_rate = AAudioStream_getSampleRate(opened_stream);
    const int32_t actual_channels = AAudioStream_getChannelCount(opened_stream);
    const aaudio_format_t actual_format = AAudioStream_getFormat(opened_stream);
    if (actual_rate < 1 || actual_rate > static_cast<int32_t>(kMaxSampleRate) ||
        actual_channels != static_cast<int32_t>(kChannelCount) ||
        actual_format != AAUDIO_FORMAT_PCM_I16) {
        error = "AAudio opened an incompatible stream: requested stereo PCM16 near " +
                std::to_string(requested_rate) + " Hz, received " +
                std::to_string(actual_channels) + " channels at " +
                std::to_string(actual_rate) + " Hz with format " +
                std::to_string(actual_format);
        AAudioStream_close(opened_stream);
        last_error_.store(AAUDIO_ERROR_INVALID_FORMAT, std::memory_order_relaxed);
        return false;
    }

    requested_sample_rate_ = static_cast<uint32_t>(requested_rate);
    sample_rate_ = static_cast<uint32_t>(actual_rate);
    capacity_frames_.store(capacity_for_latency(latency_ms_.load(std::memory_order_relaxed)),
                           std::memory_order_release);
    core_sample_rate_ = sample_rate;
    update_input_ratio();
    have_history_input_ = false;
    have_previous_input_ = false;
    have_current_input_ = false;
    have_next_input_ = false;
    history_left_ = history_right_ = 0;
    previous_left_ = previous_right_ = 0;
    current_left_ = current_right_ = 0;
    next_left_ = next_right_ = 0;
    input_phase_ = 0.0;
    read_frame_.store(0, std::memory_order_relaxed);
    write_frame_.store(0, std::memory_order_relaxed);
    submitted_frames_.store(0, std::memory_order_relaxed);
    output_queued_frames_.store(0, std::memory_order_relaxed);
    rendered_frames_.store(0, std::memory_order_relaxed);
    overflow_frames_.store(0, std::memory_order_relaxed);
    underrun_frames_.store(0, std::memory_order_relaxed);
    underrun_callbacks_.store(0, std::memory_order_relaxed);
    submitted_nonzero_samples_.store(0, std::memory_order_relaxed);
    rendered_nonzero_samples_.store(0, std::memory_order_relaxed);
    last_error_.store(AAUDIO_OK, std::memory_order_relaxed);
    stream_ = opened_stream;
    active_.store(true, std::memory_order_release);

    result = AAudioStream_requestStart(stream_);
    if (result != AAUDIO_OK) {
        error = aaudio_error("AAudioStream_requestStart", result);
        last_error_.store(result, std::memory_order_relaxed);
        shutdown();
        return false;
    }
    return true;
}

std::size_t AAudioBackend::submit(const int16_t* input, std::size_t frames) {
    if (!active_.load(std::memory_order_acquire) || input == nullptr || frames == 0 ||
        capacity_frames_.load(std::memory_order_acquire) == 0) {
        return 0;
    }

    const uint64_t read = read_frame_.load(std::memory_order_acquire);
    uint64_t write = write_frame_.load(std::memory_order_relaxed);
    const uint64_t queued = write - read;
    const uint32_t capacity_frames = capacity_frames_.load(std::memory_order_acquire);
    uint64_t free_frames = queued < capacity_frames ? capacity_frames - queued : 0;
    const double input_frames_per_output_frame =
        input_frames_per_output_frame_.load(std::memory_order_relaxed);
    const auto quality_value = resampler_quality_.load(std::memory_order_relaxed);
    const auto quality = static_cast<AAudioResamplerQuality>(quality_value);
    std::size_t input_consumed = 0;
    uint64_t output_queued = 0;
    uint64_t input_nonzero = 0;

    // The phase is measured between previous_input_ and current_input_. A
    // phase of zero therefore emits the previous source frame, while a phase
    // in (0, 1) selects/interpolates toward the current source frame. Source
    // frames and phase are retained when a batch ends, so callback boundaries
    // cannot reset the clock or create a long-term rate error.
    while (free_frames != 0) {
        if (!have_previous_input_) {
            if (input_consumed == frames) break;
            const std::size_t source = input_consumed * kChannelCount;
            previous_left_ = input[source];
            previous_right_ = input[source + 1];
            input_nonzero += previous_left_ != 0;
            input_nonzero += previous_right_ != 0;
            ++input_consumed;
            have_previous_input_ = true;
        }
        if (!have_current_input_) {
            if (input_consumed == frames) break;
            const std::size_t source = input_consumed * kChannelCount;
            current_left_ = input[source];
            current_right_ = input[source + 1];
            input_nonzero += current_left_ != 0;
            input_nonzero += current_right_ != 0;
            ++input_consumed;
            have_current_input_ = true;
        }
        if (quality == AAudioResamplerQuality::High && !have_next_input_ &&
            input_consumed != frames) {
            const std::size_t source = input_consumed * kChannelCount;
            next_left_ = input[source];
            next_right_ = input[source + 1];
            input_nonzero += next_left_ != 0;
            input_nonzero += next_right_ != 0;
            ++input_consumed;
            have_next_input_ = true;
        }

        // A previous submit may have ended after emitting the last output but
        // before it had a look-ahead frame. Advance only with source frames
        // actually present in this submit; otherwise retain the phase for the
        // next call.
        while (input_phase_ >= 1.0 && have_current_input_) {
            input_phase_ -= 1.0;
            history_left_ = previous_left_;
            history_right_ = previous_right_;
            have_history_input_ = true;
            previous_left_ = current_left_;
            previous_right_ = current_right_;
            if (have_next_input_) {
                current_left_ = next_left_;
                current_right_ = next_right_;
                have_next_input_ = false;
            } else {
                have_current_input_ = false;
            }
            if (!have_current_input_ && input_consumed != frames) {
                const std::size_t source = input_consumed * kChannelCount;
                current_left_ = input[source];
                current_right_ = input[source + 1];
                input_nonzero += current_left_ != 0;
                input_nonzero += current_right_ != 0;
                ++input_consumed;
                have_current_input_ = true;
            }
            if (quality == AAudioResamplerQuality::High && have_current_input_ &&
                !have_next_input_ && input_consumed != frames) {
                const std::size_t source = input_consumed * kChannelCount;
                next_left_ = input[source];
                next_right_ = input[source + 1];
                input_nonzero += next_left_ != 0;
                input_nonzero += next_right_ != 0;
                ++input_consumed;
                have_next_input_ = true;
            }
        }
        if (!have_current_input_) break;

        const int16_t left = interpolate(
            quality, history_left_, have_history_input_, previous_left_, current_left_, next_left_,
            have_next_input_, input_phase_);
        const int16_t right = interpolate(
            quality, history_right_, have_history_input_, previous_right_, current_right_, next_right_,
            have_next_input_, input_phase_);
        const std::size_t target = static_cast<std::size_t>(write % kMaxBufferedFrames) * 2;
        samples_[target] = left;
        samples_[target + 1] = right;
        ++write;
        --free_frames;
        ++output_queued;
        input_phase_ += input_frames_per_output_frame;
    }

    if (output_queued != 0) {
        write_frame_.store(write, std::memory_order_release);
        output_queued_frames_.fetch_add(output_queued, std::memory_order_relaxed);
    }
    submitted_frames_.fetch_add(input_consumed, std::memory_order_relaxed);
    submitted_nonzero_samples_.fetch_add(input_nonzero, std::memory_order_relaxed);
    if (input_consumed < frames) {
        overflow_frames_.fetch_add(frames - input_consumed, std::memory_order_relaxed);
    }
    return input_consumed;
}

aaudio_data_callback_result_t AAudioBackend::data_callback(
    AAudioStream*, void* user_data, void* audio_data, int32_t num_frames) {
    if (user_data == nullptr || audio_data == nullptr || num_frames <= 0) {
        return AAUDIO_CALLBACK_RESULT_STOP;
    }
    return static_cast<AAudioBackend*>(user_data)->render(
        static_cast<int16_t*>(audio_data), num_frames);
}

void AAudioBackend::error_callback(AAudioStream*, void* user_data, aaudio_result_t error) {
    if (user_data != nullptr) {
        auto* backend = static_cast<AAudioBackend*>(user_data);
        backend->last_error_.store(error, std::memory_order_relaxed);
        backend->active_.store(false, std::memory_order_release);
    }
}

aaudio_data_callback_result_t AAudioBackend::render(int16_t* output, int32_t frames) noexcept {
    if (!active_.load(std::memory_order_acquire)) {
        std::memset(output, 0, static_cast<std::size_t>(frames) * kChannelCount * sizeof(int16_t));
        return AAUDIO_CALLBACK_RESULT_STOP;
    }

    const uint64_t read = read_frame_.load(std::memory_order_relaxed);
    const uint64_t write = write_frame_.load(std::memory_order_acquire);
    const uint64_t available = write - read;
    const uint32_t wanted = static_cast<uint32_t>(frames);
    const uint32_t consumed = static_cast<uint32_t>(std::min<uint64_t>(wanted, available));
    const bool muted = muted_.load(std::memory_order_relaxed);
    const float volume = volume_.load(std::memory_order_relaxed);
    uint64_t nonzero = 0;

    for (uint32_t frame = 0; frame < consumed; ++frame) {
        const std::size_t source = static_cast<std::size_t>((read + frame) % kMaxBufferedFrames) * 2;
        const std::size_t target = static_cast<std::size_t>(frame) * 2;
        output[target] = muted ? 0 : apply_volume(samples_[source], volume);
        output[target + 1] = muted ? 0 : apply_volume(samples_[source + 1], volume);
        nonzero += output[target] != 0;
        nonzero += output[target + 1] != 0;
    }
    if (consumed < wanted) {
        std::memset(output + static_cast<std::size_t>(consumed) * 2, 0,
                    static_cast<std::size_t>(wanted - consumed) * 2 * sizeof(int16_t));
        underrun_frames_.fetch_add(wanted - consumed, std::memory_order_relaxed);
        underrun_callbacks_.fetch_add(1, std::memory_order_relaxed);
    }

    read_frame_.store(read + consumed, std::memory_order_release);
    rendered_frames_.fetch_add(consumed, std::memory_order_relaxed);
    rendered_nonzero_samples_.fetch_add(nonzero, std::memory_order_relaxed);
    return AAUDIO_CALLBACK_RESULT_CONTINUE;
}

int16_t AAudioBackend::interpolate(AAudioResamplerQuality quality,
                                   int16_t history, bool have_history,
                                   int16_t previous, int16_t current,
                                   int16_t next, bool have_next, double phase) noexcept {
    switch (quality) {
    case AAudioResamplerQuality::Low:
        return phase < 0.5 ? previous : current;
    case AAudioResamplerQuality::High: {
        // Catmull-Rom is a bounded four-point cubic. At the stream edges the
        // missing neighbour is duplicated, while interior samples use the
        // retained history/look-ahead frames.
        const double p0 = static_cast<double>(have_history ? history : previous);
        const double p1 = static_cast<double>(previous);
        const double p2 = static_cast<double>(current);
        const double p3 = static_cast<double>(have_next ? next : current);
        const double phase_squared = phase * phase;
        const double phase_cubed = phase_squared * phase;
        const double value = 0.5 *
            (2.0 * p1 + (-p0 + p2) * phase +
             (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * phase_squared +
             (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * phase_cubed);
        return clamp_pcm(value);
    }
    case AAudioResamplerQuality::Medium:
    default:
        return clamp_pcm(static_cast<double>(previous) +
                         (static_cast<double>(current) - static_cast<double>(previous)) * phase);
    }
}

int16_t AAudioBackend::apply_volume(int16_t sample, float volume) noexcept {
    if (volume <= 0.0f) return 0;
    if (volume >= 1.0f) return sample;
    return clamp_pcm(static_cast<double>(sample) * static_cast<double>(volume));
}

bool AAudioBackend::is_supported_latency(uint32_t latency_ms) noexcept {
    return latency_ms == 32 || latency_ms == 64 || latency_ms == 96 || latency_ms == 128;
}

bool AAudioBackend::is_supported_speed(double speed) noexcept {
    if (!std::isfinite(speed)) return false;
    constexpr double kTolerance = 1e-9;
    return std::fabs(speed - 0.5) <= kTolerance ||
           std::fabs(speed - 1.0) <= kTolerance ||
           std::fabs(speed - 2.0) <= kTolerance ||
           std::fabs(speed - 4.0) <= kTolerance ||
           std::fabs(speed - 8.0) <= kTolerance;
}

bool AAudioBackend::is_supported_quality(AAudioResamplerQuality quality) noexcept {
    return quality == AAudioResamplerQuality::Low ||
           quality == AAudioResamplerQuality::Medium ||
           quality == AAudioResamplerQuality::High;
}

uint32_t AAudioBackend::capacity_for_latency(uint32_t latency_ms) const noexcept {
    if (sample_rate_ == 0) return 0;
    const double requested = std::ceil(static_cast<double>(sample_rate_) *
                                       static_cast<double>(latency_ms) / 1000.0);
    return std::max<uint32_t>(1, std::min<uint32_t>(
        kMaxBufferedFrames, static_cast<uint32_t>(requested)));
}

void AAudioBackend::update_input_ratio() noexcept {
    if (sample_rate_ == 0 || !std::isfinite(core_sample_rate_)) return;
    const double ratio = core_sample_rate_ * emulation_speed_.load(std::memory_order_relaxed) /
                         static_cast<double>(sample_rate_);
    if (std::isfinite(ratio) && ratio > 0.0) {
        input_frames_per_output_frame_.store(ratio, std::memory_order_relaxed);
    }
}

bool AAudioBackend::set_volume(float volume) noexcept {
    if (!std::isfinite(volume) || volume < 0.0f || volume > 1.0f) return false;
    volume_.store(volume, std::memory_order_release);
    return true;
}

void AAudioBackend::set_muted(bool muted) noexcept {
    muted_.store(muted, std::memory_order_release);
}

bool AAudioBackend::set_latency_ms(uint32_t latency_ms) noexcept {
    if (!is_supported_latency(latency_ms)) return false;
    latency_ms_.store(latency_ms, std::memory_order_release);
    if (sample_rate_ != 0) {
        capacity_frames_.store(capacity_for_latency(latency_ms), std::memory_order_release);
    }
    return true;
}

bool AAudioBackend::set_emulation_speed(double speed) noexcept {
    if (!is_supported_speed(speed)) return false;
    if (std::fabs(speed - 0.5) <= 1e-9) speed = 0.5;
    else if (std::fabs(speed - 1.0) <= 1e-9) speed = 1.0;
    else if (std::fabs(speed - 2.0) <= 1e-9) speed = 2.0;
    else if (std::fabs(speed - 4.0) <= 1e-9) speed = 4.0;
    else speed = 8.0;
    emulation_speed_.store(speed, std::memory_order_release);
    update_input_ratio();
    return true;
}

bool AAudioBackend::set_resampler_quality(AAudioResamplerQuality quality) noexcept {
    if (!is_supported_quality(quality)) return false;
    resampler_quality_.store(static_cast<uint8_t>(quality), std::memory_order_release);
    return true;
}

AAudioMetrics AAudioBackend::metrics() const noexcept {
    AAudioMetrics value;
    value.requested_sample_rate = requested_sample_rate_;
    value.sample_rate = sample_rate_;
    value.capacity_frames = capacity_frames_.load(std::memory_order_acquire);
    value.core_sample_rate = core_sample_rate_;
    value.input_frames_per_output_frame =
        input_frames_per_output_frame_.load(std::memory_order_relaxed);
    value.emulation_speed = emulation_speed_.load(std::memory_order_relaxed);
    value.latency_ms = latency_ms_.load(std::memory_order_relaxed);
    value.volume = volume_.load(std::memory_order_relaxed);
    value.muted = muted_.load(std::memory_order_relaxed);
    const auto quality = resampler_quality_.load(std::memory_order_relaxed);
    value.resampler_quality = is_supported_quality(static_cast<AAudioResamplerQuality>(quality))
                                  ? static_cast<AAudioResamplerQuality>(quality)
                                  : AAudioResamplerQuality::Medium;
    value.submitted_frames = submitted_frames_.load(std::memory_order_relaxed);
    value.output_queued_frames = output_queued_frames_.load(std::memory_order_relaxed);
    const uint64_t write = write_frame_.load(std::memory_order_acquire);
    const uint64_t read = read_frame_.load(std::memory_order_acquire);
    value.queued_frames = write >= read
                              ? std::min<uint64_t>(write - read, kMaxBufferedFrames)
                              : 0;
    value.rendered_frames = rendered_frames_.load(std::memory_order_relaxed);
    value.overflow_frames = overflow_frames_.load(std::memory_order_relaxed);
    value.underrun_frames = underrun_frames_.load(std::memory_order_relaxed);
    value.underrun_callbacks = underrun_callbacks_.load(std::memory_order_relaxed);
    value.submitted_nonzero_samples = submitted_nonzero_samples_.load(std::memory_order_relaxed);
    value.rendered_nonzero_samples = rendered_nonzero_samples_.load(std::memory_order_relaxed);
    value.last_error = last_error_.load(std::memory_order_relaxed);
    return value;
}

void AAudioBackend::shutdown() {
    active_.store(false, std::memory_order_release);
    AAudioStream* stream = stream_;
    stream_ = nullptr;
    if (stream != nullptr) {
        const aaudio_result_t stop_result = AAudioStream_requestStop(stream);
        if (stop_result != AAUDIO_OK) {
            last_error_.store(stop_result, std::memory_order_relaxed);
        }
        const aaudio_result_t close_result = AAudioStream_close(stream);
        if (close_result != AAUDIO_OK) {
            last_error_.store(close_result, std::memory_order_relaxed);
        }
    }
}

} // namespace an3
