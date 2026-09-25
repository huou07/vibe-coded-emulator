// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#include "../src-tauri/src/save_persistence_worker.h"

#include <chrono>
#include <atomic>
#include <condition_variable>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace {

struct CapturedWrite {
    std::filesystem::path path;
    std::vector<uint8_t> bytes;
};

struct WriterGate {
    std::mutex mutex;
    std::condition_variable changed;
    bool entered = false;
    bool released = false;
    std::vector<CapturedWrite> writes;
};

bool read_bytes(const std::filesystem::path& path, std::vector<uint8_t>& bytes) {
    std::ifstream input(path, std::ios::binary);
    if (!input) return false;
    for (char byte; input.get(byte);) bytes.push_back(static_cast<uint8_t>(byte));
    return input.eof();
}

bool wait_for_writer(const std::shared_ptr<WriterGate>& gate) {
    std::unique_lock<std::mutex> lock(gate->mutex);
    return gate->changed.wait_for(lock, std::chrono::seconds(5), [&] { return gate->entered; });
}

void release_writer(const std::shared_ptr<WriterGate>& gate) {
    {
        std::lock_guard<std::mutex> lock(gate->mutex);
        gate->released = true;
    }
    gate->changed.notify_all();
}

an3::SavePersistenceWorker::TestWriter gated_writer(const std::shared_ptr<WriterGate>& gate) {
    return [gate](const std::filesystem::path& path,
                  const std::vector<uint8_t>& bytes,
                  const std::string&,
                  std::string& error) {
        std::unique_lock<std::mutex> lock(gate->mutex);
        if (!gate->entered) {
            gate->entered = true;
            gate->changed.notify_all();
            gate->changed.wait(lock, [&] { return gate->released; });
        }
        gate->writes.push_back({path, bytes});
        error.clear();
        return true;
    };
}

} // namespace

int main() {
    const auto nonce = std::chrono::steady_clock::now().time_since_epoch().count();
    const auto root = std::filesystem::temp_directory_path() /
                      ("an3-save-worker-" + std::to_string(nonce));
    std::filesystem::create_directories(root);
    int failures = 0;
    auto check = [&](bool ok, const char* label) {
        std::cout << (ok ? "PASS " : "FAIL ") << label << '\n';
        if (!ok) ++failures;
    };

    {
        an3::SavePersistenceWorker worker;
        std::string error;
        const auto coalesced_path = root / "states" / "latest.state";
        std::vector<uint8_t> expected;
        bool accepted = true;
        for (uint8_t value = 0; value < 32; ++value) {
            expected.assign(4096, value);
            accepted = worker.write_async(coalesced_path, expected, "test state", error) && accepted;
        }
        check(accepted, "asynchronous save snapshots were accepted");
        check(worker.flush(error), "background snapshots drained successfully");
        std::vector<uint8_t> persisted;
        check(read_bytes(coalesced_path, persisted) && persisted == expected,
              "the newest coalesced snapshot reached disk");
        check(worker.last_write_thread_id() != std::this_thread::get_id(),
              "save-file I/O ran on the persistence worker");

        const auto manual_path = root / "states" / "manual.state";
        const std::vector<uint8_t> manual{1, 3, 3, 7};
        check(worker.write_and_wait(manual_path, manual, "test state", error),
              "synchronous save completion is reported to its caller");
        persisted.clear();
        check(read_bytes(manual_path, persisted) && persisted == manual,
              "synchronous save bytes are intact");
        const std::vector<uint8_t> replacement{2, 4, 6, 8};
        check(worker.write_and_wait(manual_path, replacement, "test state", error),
              "an existing save can be atomically replaced");
        persisted.clear();
        check(read_bytes(manual_path, persisted) && persisted == replacement &&
                  !std::filesystem::exists(manual_path.string() + ".tmp"),
              "replacement bytes are complete and the temporary file is renamed away");

        const auto blocked_parent = root / "not-a-directory";
        {
            std::ofstream file(blocked_parent, std::ios::binary);
            file << 'x';
        }
        const bool invalid_write = worker.write_and_wait(blocked_parent / "save.state",
                                                          manual, "test save", error);
        check(!invalid_write && error.find("could not prepare local test save storage") != std::string::npos,
              "background filesystem failures reach synchronous callers");

        const bool background_accepted = worker.write_async(blocked_parent / "background.state",
                                                              manual, "test save", error);
        std::string background_error;
        const bool background_ok = worker.flush(background_error);
        check(background_accepted && !background_ok &&
                  background_error.find("could not prepare local test save storage") != std::string::npos,
              "periodic filesystem failures remain observable");
        check(worker.take_background_error().empty(), "reported background errors are consumed once");
    }

    {
        an3::SavePersistenceWorker worker;
        std::string error;
        std::mutex result_mutex;
        std::condition_variable result_ready;
        bool result_finished = false;
        bool result_success = false;
        std::string result_error;
        std::thread::id result_thread;
        const std::vector<uint8_t> bytes{5, 4, 3, 2, 1};
        const bool accepted = worker.write_async_with_completion(
            root / "async-result.state", bytes, "test state",
            [&](bool success, const std::string& message) {
                std::lock_guard<std::mutex> lock(result_mutex);
                result_success = success;
                result_error = message;
                result_thread = std::this_thread::get_id();
                result_finished = true;
                result_ready.notify_one();
            }, error);
        bool finished = false;
        {
            std::unique_lock<std::mutex> lock(result_mutex);
            finished = result_ready.wait_for(lock, std::chrono::seconds(5), [&] { return result_finished; });
        }
        std::vector<uint8_t> persisted;
        check(accepted && finished && result_success && result_error.empty(),
              "asynchronous save completion reports successful durable persistence");
        check(result_thread != std::this_thread::get_id(),
              "asynchronous completion runs off the game caller thread");
        check(read_bytes(root / "async-result.state", persisted) && persisted == bytes,
              "asynchronous success is reported only after the complete bytes reach disk");

        const auto blocked_parent = root / "not-a-directory";
        {
            std::ofstream file(blocked_parent, std::ios::binary);
            file << 'x';
        }
        result_finished = false;
        result_success = true;
        result_error.clear();
        const bool failure_accepted = worker.write_async_with_completion(
            blocked_parent / "async-failure.state", bytes, "test state",
            [&](bool success, const std::string& message) {
                std::lock_guard<std::mutex> lock(result_mutex);
                result_success = success;
                result_error = message;
                result_finished = true;
                result_ready.notify_one();
            }, error);
        finished = false;
        {
            std::unique_lock<std::mutex> lock(result_mutex);
            finished = result_ready.wait_for(lock, std::chrono::seconds(5), [&] { return result_finished; });
        }
        check(failure_accepted && finished && !result_success &&
                  result_error.find("could not prepare local test state storage") != std::string::npos,
              "asynchronous filesystem failures reach the completion callback");
    }

    {
        const auto gate = std::make_shared<WriterGate>();
        an3::SavePersistenceWorker worker(gated_writer(gate));
        std::string error;
        const bool active_accepted = worker.write_async(root / "bounded-active.srm", {0}, "test save", error);
        const bool entered = wait_for_writer(gate);
        check(active_accepted && entered, "bounded-queue test holds one active write");

        bool coalesced_accepted = entered;
        std::vector<uint8_t> newest;
        const auto coalesced_path = root / "bounded-coalesced.srm";
        for (uint8_t value = 0; value < 32; ++value) {
            newest.assign(1, value);
            coalesced_accepted = worker.write_async(coalesced_path, newest, "test save", error) && coalesced_accepted;
        }
        bool callbacks_accepted = entered;
        for (uint8_t value = 0; value < 16; ++value) {
            newest.assign(1, value);
            callbacks_accepted = worker.write_async_with_completion(
                coalesced_path, newest, "test save", [](bool, const std::string&) {}, error) && callbacks_accepted;
        }
        const bool callback_overflow_accepted = worker.write_async_with_completion(
            coalesced_path, {16}, "test save", [](bool, const std::string&) {}, error);
        const std::string callback_overflow_error = error;
        bool distinct_accepted = entered;
        for (unsigned index = 0; index < 15; ++index) {
            const auto path = root / ("bounded-distinct-" + std::to_string(index) + ".srm");
            distinct_accepted = worker.write_async(path, {static_cast<uint8_t>(index)}, "test save", error) && distinct_accepted;
        }
        const bool overflow_accepted = worker.write_async(root / "bounded-overflow.srm", {1}, "test save", error);
        check(coalesced_accepted, "same-path motion snapshots coalesce while the writer is busy");
        check(callbacks_accepted, "same-path asynchronous completions stay bounded at sixteen");
        check(!callback_overflow_accepted && callback_overflow_error.find("completion queue is full") != std::string::npos,
              "the seventeenth coalesced completion is rejected before replacing the latest bytes");
        check(distinct_accepted, "the worker accepts its bounded set of distinct pending paths");
        check(!overflow_accepted && error.find("queue is full") != std::string::npos,
              "the seventeenth pending path is rejected");

        release_writer(gate);
        check(worker.flush(error), "the bounded pending queue drains successfully");
        unsigned coalesced_writes = 0;
        std::vector<uint8_t> persisted_latest;
        {
            std::lock_guard<std::mutex> lock(gate->mutex);
            for (const auto& write : gate->writes) {
                if (write.path == coalesced_path) {
                    ++coalesced_writes;
                    persisted_latest = write.bytes;
                }
            }
            check(gate->writes.size() == 17, "one active write plus at most sixteen pending paths ran");
        }
        check(coalesced_writes == 1 && persisted_latest == newest,
              "the coalesced path writes only its newest snapshot");
    }

    {
        const auto gate = std::make_shared<WriterGate>();
        an3::SavePersistenceWorker worker(gated_writer(gate));
        std::atomic<bool> returned = false;
        bool save_succeeded = false;
        std::string save_error;
        std::thread final_save([&] {
            save_succeeded = worker.write_and_wait(root / "final-save.state", {9, 8, 7}, "test state", save_error);
            returned.store(true);
        });
        const bool entered = wait_for_writer(gate);
        check(entered && !returned.load(), "final save waits while the persistence worker is active");
        release_writer(gate);
        final_save.join();
        check(save_succeeded && returned.load(), "final save completes after the worker finishes");
    }

    {
        const auto shutdown_path = root / "shutdown-drain.state";
        const std::vector<uint8_t> final_snapshot{4, 2, 4, 2};
        std::string error;
        bool accepted = false;
        {
            an3::SavePersistenceWorker worker;
            accepted = worker.write_async(shutdown_path, {1}, "test state", error);
            accepted = worker.write_async(shutdown_path, final_snapshot, "test state", error) && accepted;
        }
        std::vector<uint8_t> persisted;
        check(accepted && read_bytes(shutdown_path, persisted) && persisted == final_snapshot,
              "worker shutdown drains the final queued snapshot before returning");
    }

    std::error_code ignored;
    std::filesystem::remove_all(root, ignored);
    if (failures) {
        std::cout << "SAVE_PERSISTENCE_WORKER=FAIL (" << failures << ")\n";
        return 1;
    }
    std::cout << "SAVE_PERSISTENCE_WORKER=PASS\n";
    return 0;
}
