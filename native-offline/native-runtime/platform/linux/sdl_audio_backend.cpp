// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#include "sdl_audio_backend.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <string>

namespace an3 {

LinuxSdlAudioBackend::~LinuxSdlAudioBackend() { shutdown(); }

bool LinuxSdlAudioBackend::initialize(double sample_rate, std::string& error) {
    shutdown();
    if (!std::isfinite(sample_rate) || sample_rate < 8'000.0 || sample_rate > 192'000.0) {
        error = "Linux audio needs a finite sample rate between 8000 and 192000 Hz.";
        return false;
    }
    if (SDL_InitSubSystem(SDL_INIT_AUDIO) != 0) {
        error = std::string("SDL audio initialization failed: ") + SDL_GetError();
        return false;
    }
    SDL_AudioSpec requested{};
    requested.freq = static_cast<int>(std::lround(sample_rate));
    requested.format = AUDIO_S16SYS;
    requested.channels = 2;
    requested.samples = 1024;
    device_ = SDL_OpenAudioDevice(nullptr, 0, &requested, &obtained_, SDL_AUDIO_ALLOW_FREQUENCY_CHANGE);
    if (!device_) {
        error = std::string("SDL native audio device failed to open: ") + SDL_GetError();
        return false;
    }
    if (obtained_.format != AUDIO_S16SYS || obtained_.channels != 2 || obtained_.freq <= 0) {
        error = "SDL native audio opened an incompatible stream; stereo PCM16 is required.";
        shutdown();
        return false;
    }
    stream_ = SDL_NewAudioStream(AUDIO_S16SYS, 2, requested.freq,
                                 obtained_.format, obtained_.channels, obtained_.freq);
    if (!stream_) {
        error = std::string("SDL audio conversion stream failed: ") + SDL_GetError();
        shutdown();
        return false;
    }
    // 160 ms is enough to absorb OS scheduling jitter without building a
    // latency-inducing, unbounded presentation queue.
    queue_limit_frames_ = static_cast<uint32_t>(std::max(2'048, obtained_.freq * 16 / 100));
    volume_.store(1.0f, std::memory_order_relaxed);
    muted_.store(false, std::memory_order_relaxed);
    SDL_PauseAudioDevice(device_, 0);
    return true;
}

std::size_t LinuxSdlAudioBackend::submit(const int16_t* samples, std::size_t frames) {
    if (!device_ || !stream_ || !samples || !frames) return 0;
    const uint32_t bytes_per_frame = static_cast<uint32_t>(SDL_AUDIO_BITSIZE(obtained_.format) / 8) * obtained_.channels;
    if (!bytes_per_frame) return 0;
    const uint32_t queued_frames = SDL_GetQueuedAudioSize(device_) / bytes_per_frame;
    if (queued_frames >= queue_limit_frames_) return 0;
    const std::size_t input_bytes = frames * sizeof(int16_t) * 2;
    if (input_bytes / (sizeof(int16_t) * 2) != frames || input_bytes > static_cast<std::size_t>(std::numeric_limits<int>::max())) return 0;
    if (SDL_AudioStreamPut(stream_, samples, static_cast<int>(input_bytes)) != 0) return 0;
    conversion_buffer_.resize(static_cast<size_t>(SDL_AudioStreamAvailable(stream_)));
    if (!conversion_buffer_.empty() && SDL_AudioStreamGet(stream_, conversion_buffer_.data(), static_cast<int>(conversion_buffer_.size())) < 0) return 0;
    const uint32_t available_frames = static_cast<uint32_t>(conversion_buffer_.size() / bytes_per_frame);
    const uint32_t writable_frames = queue_limit_frames_ > queued_frames ? queue_limit_frames_ - queued_frames : 0;
    const uint32_t accepted_frames = std::min(available_frames, writable_frames);
    const float requested_volume = muted_.load(std::memory_order_relaxed)
                                       ? 0.0f
                                       : volume_.load(std::memory_order_relaxed);
    if (accepted_frames && requested_volume != 1.0f) {
        auto* output = reinterpret_cast<int16_t*>(conversion_buffer_.data());
        const size_t sample_count = static_cast<size_t>(accepted_frames) * obtained_.channels;
        for (size_t index = 0; index < sample_count; ++index) {
            const int scaled = static_cast<int>(std::lround(static_cast<float>(output[index]) * requested_volume));
            output[index] = static_cast<int16_t>(std::clamp(scaled,
                static_cast<int>(std::numeric_limits<int16_t>::min()),
                static_cast<int>(std::numeric_limits<int16_t>::max())));
        }
    }
    if (accepted_frames && SDL_QueueAudio(device_, conversion_buffer_.data(), accepted_frames * bytes_per_frame) != 0) return 0;
    return frames;
}

bool LinuxSdlAudioBackend::set_volume(float value) noexcept {
    if (!std::isfinite(value) || value < 0.0f || value > 1.0f) return false;
    volume_.store(value, std::memory_order_relaxed);
    return true;
}

void LinuxSdlAudioBackend::set_muted(bool value) noexcept {
    muted_.store(value, std::memory_order_relaxed);
}

LinuxSdlAudioMetrics LinuxSdlAudioBackend::metrics() const noexcept {
    LinuxSdlAudioMetrics result;
    result.sample_rate = obtained_.freq > 0 ? static_cast<uint32_t>(obtained_.freq) : 0;
    const uint32_t bytes_per_frame = static_cast<uint32_t>(SDL_AUDIO_BITSIZE(obtained_.format) / 8) * obtained_.channels;
    result.queued_frames = device_ && bytes_per_frame ? SDL_GetQueuedAudioSize(device_) / bytes_per_frame : 0;
    result.volume = volume_.load(std::memory_order_relaxed);
    result.muted = muted_.load(std::memory_order_relaxed);
    return result;
}

void LinuxSdlAudioBackend::shutdown() {
    if (device_) SDL_CloseAudioDevice(device_);
    device_ = 0;
    if (stream_) SDL_FreeAudioStream(stream_);
    stream_ = nullptr;
    queue_limit_frames_ = 0;
    conversion_buffer_.clear();
    volume_.store(1.0f, std::memory_order_relaxed);
    muted_.store(false, std::memory_order_relaxed);
}

} // namespace an3
