// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "../../core/video_backend.h"

#include <SDL2/SDL.h>

#include <atomic>
#include <cstdint>
#include <memory>
#include <vector>

namespace an3 {

struct LinuxSdlAudioMetrics {
    uint32_t sample_rate = 0;
    uint32_t queued_frames = 0;
    float volume = 1.0f;
    bool muted = false;
};

// SDL's native PipeWire/PulseAudio/ALSA backend keeps a deliberately bounded
// queue. Audio never feeds the emulation scheduler and cannot grow without
// limit when a desktop output device is interrupted.
class LinuxSdlAudioBackend final : public NativeAudioBackend {
  public:
    ~LinuxSdlAudioBackend() override;
    bool initialize(double sample_rate, std::string& error) override;
    std::size_t submit(const int16_t* samples, std::size_t frames) override;
    void shutdown() override;
    bool set_volume(float value) noexcept;
    void set_muted(bool value) noexcept;
    LinuxSdlAudioMetrics metrics() const noexcept;

  private:
    SDL_AudioDeviceID device_ = 0;
    SDL_AudioStream* stream_ = nullptr;
    SDL_AudioSpec obtained_{};
    uint32_t queue_limit_frames_ = 0;
    std::vector<uint8_t> conversion_buffer_;
    std::atomic<float> volume_{1.0f};
    std::atomic<bool> muted_{false};
};

} // namespace an3
