// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "sdl_audio_backend.h"

#include "../../core/libretro_host.h"
#include "../../core/video_backend.h"

#include <functional>
#include <memory>
#include <string>

namespace an3 {

// This is a native GTK companion to the SDL game window. It deliberately
// owns controls only: the portable core continues to run in the existing SDL
// loop and the Vulkan/OpenGL presenters remain untouched.
struct LinuxControlSnapshot {
    NativeCoreStatus core;
    NativeVideoStatus video;
    LinuxSdlAudioMetrics audio;
    bool paused = false;
    std::string auto_save_mode = "off";
    double speed = 1.0;
    std::string layout;
    std::string last_message;
};

struct LinuxControlCallbacks {
    std::function<LinuxControlSnapshot()> snapshot;
    std::function<void(bool)> set_paused;
    std::function<void(double)> set_speed;
    std::function<void(const std::string&)> set_auto_save_mode;
    std::function<void()> toggle_fullscreen;
    std::function<void()> return_to_library;
    std::function<bool(const std::string&, std::string&)> set_layout;
};

class LinuxControlPanel {
  public:
    LinuxControlPanel(NativeCoreHost& host, LinuxSdlAudioBackend& audio,
                      std::string system, LinuxControlCallbacks callbacks);
    ~LinuxControlPanel();

    LinuxControlPanel(const LinuxControlPanel&) = delete;
    LinuxControlPanel& operator=(const LinuxControlPanel&) = delete;

    bool initialize(std::string& error);
    void pump();
    void show();
    void hide();
    void toggle();
    void show_pad();
    bool visible() const;

  private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace an3
