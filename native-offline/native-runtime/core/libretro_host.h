// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "video_backend.h"

#include <atomic>
#include <chrono>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace an3 {

enum class NativeSystem { Unknown, GBA, NDS, ThreeDS };

struct NativeCoreStatus {
    NativeSystem system = NativeSystem::Unknown;
    std::string core_name;
    std::string core_version;
    std::string last_message;
    double core_fps = 0.0;
    uint64_t core_frames = 0;
    bool hardware_render_rejected = false;
};

// Adapters render these copies in their own native controls. Keeping the
// registry-owned libretro strings private prevents a UI repaint from sharing
// mutable core memory with the emulation callback.
struct NativeCoreOptionValue {
    std::string value;
    std::string label;
};

struct NativeCoreOption {
    std::string key;
    std::string label;
    std::string description;
    std::string current_value;
    std::vector<NativeCoreOptionValue> values;
    bool restart_required = true;
};

// Values are libretro joypad button ids, so adapters can update the complete
// pad without translating on the emulation thread.
class NativeInput {
public:
    void set_buttons(uint32_t buttons) noexcept;
    void set_button(unsigned button, bool pressed) noexcept;
    uint32_t buttons() const noexcept;
    void set_pointer(int16_t x, int16_t y, bool pressed) noexcept;
    void set_analog(int16_t x, int16_t y) noexcept;
    void clear() noexcept;
    void cancel_pointer() noexcept;

private:
    friend class NativeCoreHost;
    std::atomic<uint32_t> buttons_{0};
    std::atomic<uint32_t> pending_buttons_{0};
    std::atomic<bool> pending_pointer_{false};
    std::atomic<int16_t> pointer_x_{0};
    std::atomic<int16_t> pointer_y_{0};
    std::atomic<bool> pointer_pressed_{false};
    std::atomic<int16_t> analog_x_{0};
    std::atomic<int16_t> analog_y_{0};
};

class NativeCoreHost {
public:
    NativeCoreHost();
    ~NativeCoreHost();
    NativeCoreHost(const NativeCoreHost&) = delete;
    NativeCoreHost& operator=(const NativeCoreHost&) = delete;

    bool initialize(const std::string& core_path,
                    const std::string& rom_path,
                    const std::string& save_directory,
                    NativeVideoBackend& video,
                    NativeAudioBackend& audio,
                    std::string& error,
                    const std::string& nds_layout = "top-bottom",
                    const std::string& graphics_api = "Vulkan");

    // Call from one adapter-owned emulation thread. Commands and callbacks are
    // serialized at this boundary; presentation/vsync never controls core speed.
    bool run_one(std::string& error, bool present = true);
    void shutdown();
    bool running() const noexcept;
    std::chrono::nanoseconds frame_duration() const noexcept;
    NativeCoreStatus status() const;

    NativeInput& input() noexcept;
    const NativeInput& input() const noexcept;

    bool save_state(unsigned slot, std::string& error); // slots 1..10
    bool load_state(unsigned slot, std::string& error);
    bool save_auto(std::string& error);
    bool load_auto(std::string& error);
    bool export_state(const std::string& path, std::string& error);
    bool import_state(const std::string& path, std::string& error);

    bool set_core_option(const std::string& key, const std::string& value,
                         std::string& error);
    // A shared schema owns the values passed here. Updating this field marks
    // libretro's variable state dirty so a core can recompute its geometry on
    // the next emulation tick; adapters recompute their touch geometry at the
    // same point and persist the selected layout.
    bool set_screen_layout(const std::string& layout, std::string& error);
    std::vector<std::string> core_option_keys() const;
    std::vector<NativeCoreOption> core_options() const;
    std::string core_options_json() const;

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace an3
