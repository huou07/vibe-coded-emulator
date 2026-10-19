// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#include "native_core_session.h"

#include <algorithm>
#include <chrono>
#include <cmath>

namespace an3 {

NativeCoreSession::NativeCoreSession(NativeCoreHost& host) : host_(host) {}

NativeCoreSession::~NativeCoreSession() {
    stop();
    if (!worker_.joinable() && host_.running()) host_.shutdown();
}

bool NativeCoreSession::start(std::string& error, long frame_limit) {
    if (worker_.joinable() || !host_.running()) {
        error = worker_.joinable() ? "The native core session is already running."
                                   : "The native core is not initialized.";
        return false;
    }
    {
        std::lock_guard<std::mutex> lock(command_mutex_);
        commands_.clear();
        stopping_.store(false, std::memory_order_release);
        paused_.store(false, std::memory_order_release);
        speed_.store(1.0, std::memory_order_release);
        running_.store(true, std::memory_order_release);
    }
    {
        std::lock_guard<std::mutex> lock(error_mutex_);
        runtime_error_.clear();
    }
    try {
        worker_ = std::thread([this, frame_limit] { worker_loop(frame_limit); });
    } catch (...) {
        running_.store(false, std::memory_order_release);
        error = "Could not start the native core-owner thread.";
        return false;
    }
    return true;
}

void NativeCoreSession::stop() {
    if (!worker_.joinable()) return;
    {
        std::lock_guard<std::mutex> lock(command_mutex_);
        stopping_.store(true, std::memory_order_release);
    }
    command_ready_.notify_all();
    if (worker_.joinable()) worker_.join();
    running_.store(false, std::memory_order_release);
}

void NativeCoreSession::set_paused(bool value) noexcept {
    paused_.store(value, std::memory_order_release);
    Command command;
    command.kind = value ? CommandKind::Pause : CommandKind::Resume;
    (void)enqueue_control(std::move(command));
}

void NativeCoreSession::set_speed(double value) noexcept {
    if (!std::isfinite(value)) return;
    value = std::clamp(value, 0.25, 8.0);
    speed_.store(value, std::memory_order_release);
    Command command;
    command.kind = CommandKind::SetSpeed;
    command.speed = value;
    (void)enqueue_control(std::move(command));
}

bool NativeCoreSession::enqueue_control(Command command) noexcept {
    std::lock_guard<std::mutex> lock(command_mutex_);
    if (stopping_.load(std::memory_order_acquire) || !running_.load(std::memory_order_acquire) ||
        !worker_.joinable()) return false;
    if (is_control_command(command.kind)) {
        for (auto iterator = commands_.begin(); iterator != commands_.end();) {
            if (is_control_command(iterator->kind)) iterator = commands_.erase(iterator);
            else ++iterator;
        }
    }
    if (commands_.size() >= kMaxPendingCommands) return false;
    commands_.push_back(std::move(command));
    command_ready_.notify_one();
    return true;
}

bool NativeCoreSession::is_control_command(CommandKind kind) noexcept {
    return kind == CommandKind::Pause || kind == CommandKind::Resume ||
           kind == CommandKind::SetSpeed;
}

bool NativeCoreSession::submit(Command command, std::string& error) const {
    auto result = std::make_shared<Result>();
    command.result = result;
    {
        std::lock_guard<std::mutex> lock(command_mutex_);
        if (stopping_.load(std::memory_order_acquire) || !running_.load(std::memory_order_acquire) ||
            !worker_.joinable()) {
            error = "The native core session is not running.";
            return false;
        }
        if (commands_.size() >= kMaxPendingCommands) {
            error = "The native core command queue is full; the command was not accepted.";
            return false;
        }
        commands_.push_back(std::move(command));
    }
    command_ready_.notify_one();
    std::unique_lock<std::mutex> lock(result->mutex);
    result->ready.wait(lock, [&] { return result->finished; });
    error = result->error;
    return result->success;
}

void NativeCoreSession::complete(const std::shared_ptr<Result>& result, bool success,
                                 const std::string& error) {
    if (!result) return;
    std::lock_guard<std::mutex> lock(result->mutex);
    result->success = success;
    result->error = error;
    result->finished = true;
    result->ready.notify_one();
}

void NativeCoreSession::remember_error(const std::string& error) {
    if (error.empty()) return;
    std::lock_guard<std::mutex> lock(error_mutex_);
    runtime_error_ = error;
}

bool NativeCoreSession::execute(Command& command) {
    std::string error;
    bool success = true;
    switch (command.kind) {
    case CommandKind::Pause:
        host_.reset_frame_timing_baseline();
        paused_.store(true, std::memory_order_release);
        host_.input().clear();
        break;
    case CommandKind::Resume:
        host_.reset_frame_timing_baseline();
        paused_.store(false, std::memory_order_release);
        break;
    case CommandKind::SetSpeed:
        speed_.store(command.speed, std::memory_order_release);
        break;
    case CommandKind::SaveState:
        success = host_.save_state(command.slot, error);
        break;
    case CommandKind::LoadState:
        success = host_.load_state(command.slot, error);
        break;
    case CommandKind::SaveAuto:
        success = host_.save_auto(error);
        break;
    case CommandKind::QueueSaveAuto:
        success = host_.queue_save_auto(error);
        break;
    case CommandKind::LoadAuto:
        success = host_.load_auto(error);
        break;
    case CommandKind::QueueSaveRam:
        success = host_.queue_save_ram(error);
        break;
    case CommandKind::FlushSaveRam:
        success = host_.flush_save_ram(error);
        break;
    case CommandKind::ExportState:
        success = host_.export_state(command.first, error);
        break;
    case CommandKind::ImportState:
        success = host_.import_state(command.first, error);
        break;
    case CommandKind::SetCoreOption:
        success = host_.set_core_option(command.first, command.second, error);
        break;
    case CommandKind::SetScreenLayout:
        success = host_.set_screen_layout(command.first, error);
        break;
    case CommandKind::ReadCoreOptions: {
        auto options = host_.core_options();
        if (command.result) command.result->options = std::move(options);
        break;
    }
    }
    complete(command.result, success, error);
    if (!success) remember_error(error);
    return true;
}

void NativeCoreSession::worker_loop(long frame_limit) {
    auto next_deadline = std::chrono::steady_clock::now();
    uint64_t frames = 0;
    bool keep_running = true;
    while (keep_running) {
        for (;;) {
            Command command;
            {
                std::lock_guard<std::mutex> lock(command_mutex_);
                if (commands_.empty()) break;
                command = std::move(commands_.front());
                commands_.pop_front();
            }
            keep_running = execute(command);
            if (!keep_running) break;
        }
        if (!keep_running) break;
        {
            std::lock_guard<std::mutex> lock(command_mutex_);
            if (stopping_.load(std::memory_order_acquire) && commands_.empty()) break;
            if (stopping_.load(std::memory_order_acquire)) continue;
        }
        if (paused_.load(std::memory_order_acquire)) {
            std::unique_lock<std::mutex> lock(command_mutex_);
            command_ready_.wait_for(lock, std::chrono::milliseconds(20), [this] {
                return stopping_.load(std::memory_order_acquire) || !commands_.empty() ||
                       !paused_.load(std::memory_order_acquire);
            });
            continue;
        }
        const auto now = std::chrono::steady_clock::now();
        if (now < next_deadline) {
            std::unique_lock<std::mutex> lock(command_mutex_);
            command_ready_.wait_until(lock, next_deadline, [this] {
                return stopping_.load(std::memory_order_acquire) || !commands_.empty() ||
                       paused_.load(std::memory_order_acquire);
            });
            continue;
        }
        if (stopping_.load(std::memory_order_acquire)) continue;
        const double speed = std::clamp(speed_.load(std::memory_order_acquire), 0.25, 8.0);
        const unsigned present_stride = speed > 1.0 ? static_cast<unsigned>(speed) : 1u;
        std::string error;
        if (!host_.run_one(error, frames % present_stride == 0)) {
            remember_error(error);
            break;
        }
        ++frames;
        if (frame_limit >= 0 && frames >= static_cast<uint64_t>(frame_limit)) {
            // Keep the owner alive and commandable at a bounded test boundary.
            // The adapter can export state and then call stop(), which performs
            // the same owner-thread shutdown as an interactive close.
            paused_.store(true, std::memory_order_release);
            frame_limit = -1;
        }
        const auto period = std::chrono::nanoseconds(
            static_cast<int64_t>(std::llround(host_.frame_duration().count() / speed)));
        next_deadline += period;
        if (next_deadline < std::chrono::steady_clock::now() - period * 2) {
            next_deadline = std::chrono::steady_clock::now();
        }
    }
    host_.shutdown();
    running_.store(false, std::memory_order_release);
}

NativeCoreStatus NativeCoreSession::status() const {
    auto status = host_.status();
    std::lock_guard<std::mutex> lock(error_mutex_);
    if (!runtime_error_.empty()) status.last_message = runtime_error_;
    return status;
}

bool NativeCoreSession::save_state(unsigned slot, std::string& error) {
    Command command; command.kind = CommandKind::SaveState; command.slot = slot;
    return submit(std::move(command), error);
}

bool NativeCoreSession::load_state(unsigned slot, std::string& error) {
    Command command; command.kind = CommandKind::LoadState; command.slot = slot;
    return submit(std::move(command), error);
}

bool NativeCoreSession::save_auto(std::string& error) {
    Command command; command.kind = CommandKind::SaveAuto;
    return submit(std::move(command), error);
}

bool NativeCoreSession::queue_save_auto(std::string& error) {
    Command command; command.kind = CommandKind::QueueSaveAuto;
    return submit(std::move(command), error);
}

bool NativeCoreSession::load_auto(std::string& error) {
    Command command; command.kind = CommandKind::LoadAuto;
    return submit(std::move(command), error);
}

bool NativeCoreSession::queue_save_ram(std::string& error) {
    Command command; command.kind = CommandKind::QueueSaveRam;
    return submit(std::move(command), error);
}

bool NativeCoreSession::flush_save_ram(std::string& error) {
    Command command; command.kind = CommandKind::FlushSaveRam;
    return submit(std::move(command), error);
}

bool NativeCoreSession::export_state(const std::string& path, std::string& error) {
    Command command; command.kind = CommandKind::ExportState; command.first = path;
    return submit(std::move(command), error);
}

bool NativeCoreSession::import_state(const std::string& path, std::string& error) {
    Command command; command.kind = CommandKind::ImportState; command.first = path;
    return submit(std::move(command), error);
}

bool NativeCoreSession::set_core_option(const std::string& key, const std::string& value,
                                        std::string& error) {
    Command command; command.kind = CommandKind::SetCoreOption;
    command.first = key; command.second = value;
    return submit(std::move(command), error);
}

bool NativeCoreSession::set_screen_layout(const std::string& layout, std::string& error) {
    Command command; command.kind = CommandKind::SetScreenLayout; command.first = layout;
    return submit(std::move(command), error);
}

std::vector<NativeCoreOption> NativeCoreSession::core_options(std::string& error) const {
    Command command; command.kind = CommandKind::ReadCoreOptions;
    auto result = std::make_shared<Result>();
    command.result = result;
    {
        std::lock_guard<std::mutex> lock(command_mutex_);
        if (stopping_.load(std::memory_order_acquire) || !running_.load(std::memory_order_acquire) ||
            !worker_.joinable()) {
            error = "The native core session is not running.";
            return {};
        }
        if (commands_.size() >= kMaxPendingCommands) {
            error = "The native core command queue is full; the command was not accepted.";
            return {};
        }
        commands_.push_back(std::move(command));
    }
    command_ready_.notify_one();
    std::unique_lock<std::mutex> lock(result->mutex);
    result->ready.wait(lock, [&] { return result->finished; });
    error = result->error;
    return result->options;
}

} // namespace an3
