// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "libretro_host.h"

#include <atomic>
#include <condition_variable>
#include <cstddef>
#include <deque>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace an3 {

// Owns the running portable software core on exactly one thread. Input remains
// an atomic/latest snapshot on NativeInput; lifecycle, save, layout, and core
// option operations cross this bounded command boundary instead of calling a
// running libretro core from arbitrary UI threads.
class NativeCoreSession {
  public:
    static constexpr std::size_t kMaxPendingCommands = 128;

    explicit NativeCoreSession(NativeCoreHost& host);
    ~NativeCoreSession();

    NativeCoreSession(const NativeCoreSession&) = delete;
    NativeCoreSession& operator=(const NativeCoreSession&) = delete;

    bool start(std::string& error, long frame_limit = -1);
    void stop();

    bool running() const noexcept { return running_.load(std::memory_order_acquire); }
    bool paused() const noexcept { return paused_.load(std::memory_order_acquire); }
    double speed() const noexcept { return speed_.load(std::memory_order_relaxed); }
    void set_paused(bool value) noexcept;
    void set_speed(double value) noexcept;

    NativeInput& input() noexcept { return host_.input(); }
    const NativeInput& input() const noexcept { return host_.input(); }
    NativeCoreStatus status() const;

    bool save_state(unsigned slot, std::string& error);
    bool load_state(unsigned slot, std::string& error);
    bool save_auto(std::string& error);
    bool queue_save_auto(std::string& error);
    bool load_auto(std::string& error);
    bool queue_save_ram(std::string& error);
    bool flush_save_ram(std::string& error);
    bool export_state(const std::string& path, std::string& error);
    bool import_state(const std::string& path, std::string& error);
    bool set_core_option(const std::string& key, const std::string& value,
                         std::string& error);
    bool set_screen_layout(const std::string& layout, std::string& error);
    std::vector<NativeCoreOption> core_options(std::string& error) const;
    std::vector<NativeCoreOption> core_options() const {
        std::string ignored;
        return core_options(ignored);
    }

  private:
    enum class CommandKind {
        Pause,
        Resume,
        SetSpeed,
        SaveState,
        LoadState,
        SaveAuto,
        QueueSaveAuto,
        LoadAuto,
        QueueSaveRam,
        FlushSaveRam,
        ExportState,
        ImportState,
        SetCoreOption,
        SetScreenLayout,
        ReadCoreOptions,
    };

    struct Result {
        std::mutex mutex;
        std::condition_variable ready;
        bool finished = false;
        bool success = false;
        std::string error;
        std::vector<NativeCoreOption> options;
    };

    struct Command {
        CommandKind kind = CommandKind::Pause;
        unsigned slot = 0;
        double speed = 1.0;
        std::string first;
        std::string second;
        std::shared_ptr<Result> result;
    };

    bool submit(Command command, std::string& error) const;
    bool enqueue_control(Command command) noexcept;
    static bool is_control_command(CommandKind kind) noexcept;
    void worker_loop(long frame_limit);
    bool execute(Command& command);
    static void complete(const std::shared_ptr<Result>& result, bool success,
                         const std::string& error);
    void remember_error(const std::string& error);

    NativeCoreHost& host_;
    mutable std::mutex command_mutex_;
    mutable std::condition_variable command_ready_;
    mutable std::deque<Command> commands_;
    std::thread worker_;
    std::atomic<bool> running_{false};
    std::atomic<bool> stopping_{false};
    std::atomic<bool> paused_{false};
    std::atomic<double> speed_{1.0};
    mutable std::mutex error_mutex_;
    std::string runtime_error_;
};

} // namespace an3
