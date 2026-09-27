// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <condition_variable>
#include <cstdio>
#include <deque>
#include <filesystem>
#include <fstream>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#if defined(AN3_SAVE_PERSISTENCE_TESTING)
#include <functional>
#endif

#include <fcntl.h>
#include <unistd.h>

#if defined(__APPLE__)
#include <pthread.h>
#endif

namespace an3 {

// Owns all save-file writes. Repeated queued snapshots for one path collapse
// to the newest bytes, so slow storage cannot grow an unbounded frame-path
// backlog. Synchronous callers wait for completion without doing file I/O.
class SavePersistenceWorker {
  public:
    using AsyncCompletion = std::function<void(bool, const std::string&)>;

#if defined(AN3_SAVE_PERSISTENCE_TESTING)
    using TestWriter = std::function<bool(const std::filesystem::path&,
                                          const std::vector<uint8_t>&,
                                          const std::string&,
                                          std::string&)>;

    SavePersistenceWorker() : worker_([this] { run(); }) {}
    explicit SavePersistenceWorker(TestWriter test_writer)
        : test_writer_(std::move(test_writer)), worker_([this] { run(); }) {}
#else
    SavePersistenceWorker() : worker_([this] { run(); }) {}
#endif
    ~SavePersistenceWorker() { shutdown(); }

    SavePersistenceWorker(const SavePersistenceWorker&) = delete;
    SavePersistenceWorker& operator=(const SavePersistenceWorker&) = delete;

    bool write_async(std::filesystem::path path,
                     std::vector<uint8_t> bytes,
                     std::string description,
                     std::string& error) {
        return enqueue(std::move(path), std::move(bytes), std::move(description), nullptr, {}, error);
    }

    bool write_async_with_completion(std::filesystem::path path,
                                     std::vector<uint8_t> bytes,
                                     std::string description,
                                     AsyncCompletion completion,
                                     std::string& error) {
        return enqueue(std::move(path), std::move(bytes), std::move(description), nullptr,
                       std::move(completion), error);
    }

    bool write_and_wait(std::filesystem::path path,
                        std::vector<uint8_t> bytes,
                        std::string description,
                        std::string& error) {
        auto completion = std::make_shared<Completion>();
        if (!enqueue(std::move(path), std::move(bytes), std::move(description), completion, {}, error)) return false;
        std::unique_lock<std::mutex> lock(completion->mutex);
        completion->ready.wait(lock, [&] { return completion->finished; });
        error = completion->error;
        return completion->success;
    }

    bool flush(std::string& error) {
        std::unique_lock<std::mutex> lock(mutex_);
        idle_.wait(lock, [&] { return queue_.empty() && !active_; });
        error = std::move(background_error_);
        background_error_.clear();
        return error.empty();
    }

    std::string take_background_error() {
        std::lock_guard<std::mutex> lock(mutex_);
        std::string error = std::move(background_error_);
        background_error_.clear();
        return error;
    }

    // Kept observable for the native persistence regression test.
    std::thread::id last_write_thread_id() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return last_write_thread_id_;
    }

  private:
    struct Completion {
        std::mutex mutex;
        std::condition_variable ready;
        bool finished = false;
        bool success = false;
        std::string error;
    };

    struct Job {
        std::filesystem::path path;
        std::vector<uint8_t> bytes;
        std::string description;
        std::vector<std::shared_ptr<Completion>> completions;
        std::vector<AsyncCompletion> async_completions;
    };

    bool enqueue(std::filesystem::path path,
                 std::vector<uint8_t> bytes,
                 std::string description,
                 std::shared_ptr<Completion> completion,
                 AsyncCompletion async_completion,
                 std::string& error) {
        if (path.empty() || path.filename().empty()) {
            error = "Choose a valid local save filename.";
            return false;
        }
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (stopping_) {
                error = "The local save worker is shutting down.";
                return false;
            }
            auto pending = std::find_if(queue_.begin(), queue_.end(), [&](const Job& job) {
                return job.path == path;
            });
            if (pending != queue_.end()) {
                constexpr size_t kMaxAsyncCompletionsPerPath = 16;
                if (async_completion && pending->async_completions.size() >= kMaxAsyncCompletionsPerPath) {
                    error = "The local save completion queue is full; the current save was not changed.";
                    return false;
                }
                pending->bytes = std::move(bytes);
                pending->description = std::move(description);
                if (completion) pending->completions.push_back(std::move(completion));
                if (async_completion) pending->async_completions.push_back(std::move(async_completion));
            } else {
                constexpr size_t kMaxPendingPaths = 16;
                if (queue_.size() >= kMaxPendingPaths) {
                    error = "The local save queue is full; the current save was not changed.";
                    return false;
                }
                Job job{std::move(path), std::move(bytes), std::move(description), {}, {}};
                if (completion) job.completions.push_back(std::move(completion));
                if (async_completion) job.async_completions.push_back(std::move(async_completion));
                queue_.push_back(std::move(job));
            }
            error.clear();
        }
        work_.notify_one();
        return true;
    }

    static bool write_bytes_atomically(const std::filesystem::path& path,
                                       const std::vector<uint8_t>& bytes,
                                       const std::string& description,
                                       std::string& error) {
        std::error_code filesystem_error;
        if (!path.parent_path().empty()) std::filesystem::create_directories(path.parent_path(), filesystem_error);
        if (filesystem_error) {
            error = "VibeCodedEmulator could not prepare local " + description + " storage.";
            return false;
        }
        const std::filesystem::path temporary = path.string() + ".tmp";
        {
            std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
            output.write(reinterpret_cast<const char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
            output.flush();
            if (!output) {
                output.close();
                std::filesystem::remove(temporary, filesystem_error);
                error = "VibeCodedEmulator could not write this " + description + ".";
                return false;
            }
        }
        const int descriptor = ::open(temporary.c_str(), O_RDONLY);
        if (descriptor >= 0) {
            (void)::fsync(descriptor);
            (void)::close(descriptor);
        }
        if (::rename(temporary.c_str(), path.c_str()) != 0) {
            std::filesystem::remove(temporary, filesystem_error);
            error = "VibeCodedEmulator could not atomically finish this " + description + ".";
            return false;
        }
        error.clear();
        return true;
    }

    void complete(const std::shared_ptr<Completion>& completion, bool success, const std::string& error) {
        std::lock_guard<std::mutex> lock(completion->mutex);
        completion->success = success;
        completion->error = error;
        completion->finished = true;
        completion->ready.notify_one();
    }

    void run() {
#if defined(__APPLE__)
        (void)pthread_setname_np("AN3 Save Worker");
#endif
        for (;;) {
            Job job;
            {
                std::unique_lock<std::mutex> lock(mutex_);
                work_.wait(lock, [&] { return stopping_ || !queue_.empty(); });
                if (stopping_ && queue_.empty()) {
                    idle_.notify_all();
                    return;
                }
                job = std::move(queue_.front());
                queue_.pop_front();
                active_ = true;
                last_write_thread_id_ = std::this_thread::get_id();
            }

            std::string error;
#if defined(AN3_SAVE_PERSISTENCE_TESTING)
            const bool success = test_writer_
                                     ? test_writer_(job.path, job.bytes, job.description, error)
                                     : write_bytes_atomically(job.path, job.bytes, job.description, error);
#else
            const bool success = write_bytes_atomically(job.path, job.bytes, job.description, error);
#endif
            {
                std::lock_guard<std::mutex> lock(mutex_);
                if (!success && job.completions.empty()) background_error_ = error;
                active_ = false;
                if (queue_.empty()) idle_.notify_all();
            }
            for (const auto& completion : job.completions) complete(completion, success, error);
            for (const auto& completion : job.async_completions) completion(success, error);
        }
    }

    void shutdown() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (stopping_) return;
            stopping_ = true;
        }
        work_.notify_one();
        if (worker_.joinable()) worker_.join();
    }

    mutable std::mutex mutex_;
    std::condition_variable work_;
    std::condition_variable idle_;
    std::deque<Job> queue_;
    std::thread::id last_write_thread_id_{};
    std::string background_error_;
    bool active_ = false;
    bool stopping_ = false;
#if defined(AN3_SAVE_PERSISTENCE_TESTING)
    TestWriter test_writer_;
#endif
    std::thread worker_;
};

} // namespace an3
