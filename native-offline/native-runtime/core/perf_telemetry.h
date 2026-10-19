// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <algorithm>
#include <array>
#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <limits>
#include <memory>
#include <string>

namespace an3::perf {

// The runtime keeps only a small recent window in memory.  Threshold counters
// are cumulative, so a long run does not need an ever-growing log or queue.
constexpr std::size_t kTimingSamples = 512;
// Keep enough bounded history for a warm-up plus a several-minute acceptance
// run without turning tracing into an unbounded log. At 60 Hz this covers more
// than 18 minutes of frame samples.
constexpr std::size_t kTraceSamples = 65536;

struct TimingSummary {
    uint64_t count = 0;
    uint64_t p50_ns = 0;
    uint64_t p95_ns = 0;
    uint64_t p99_ns = 0;
    uint64_t max_ns = 0;
    uint64_t deadline_misses = 0;
    uint64_t over_150x = 0;
    uint64_t over_2x = 0;
    uint64_t over_3x = 0;
};

class TimingSeries {
  public:
    void reset() {
        count_.store(0, std::memory_order_relaxed);
        next_.store(0, std::memory_order_relaxed);
        max_ns_.store(0, std::memory_order_relaxed);
        deadline_misses_.store(0, std::memory_order_relaxed);
        over_150x_.store(0, std::memory_order_relaxed);
        over_2x_.store(0, std::memory_order_relaxed);
        over_3x_.store(0, std::memory_order_relaxed);
    }

    // `budget_ns == 0` records the sample without deadline classification.
    // This keeps one implementation usable for emulation, presentation,
    // upload, acquire, fence, and save timings.
    void add(uint64_t elapsed_ns, uint64_t budget_ns = 0) {
        const std::size_t index = next_.fetch_add(1, std::memory_order_relaxed) % kTimingSamples;
        values_[index].store(elapsed_ns, std::memory_order_relaxed);
        std::size_t observed = count_.load(std::memory_order_relaxed);
        while (observed < kTimingSamples &&
               !count_.compare_exchange_weak(observed, observed + 1, std::memory_order_relaxed)) {}

        uint64_t observed_max = max_ns_.load(std::memory_order_relaxed);
        while (observed_max < elapsed_ns &&
               !max_ns_.compare_exchange_weak(observed_max, elapsed_ns, std::memory_order_relaxed)) {}
        if (!budget_ns) return;
        if (elapsed_ns > budget_ns) deadline_misses_.fetch_add(1, std::memory_order_relaxed);
        // Avoid overflow when a caller supplies an unusually large budget.
        const uint64_t one_and_a_half = budget_ns > (std::numeric_limits<uint64_t>::max() / 3u) * 2u
            ? std::numeric_limits<uint64_t>::max()
            : (budget_ns * 3u) / 2u;
        const uint64_t two = budget_ns > std::numeric_limits<uint64_t>::max() / 2u
            ? std::numeric_limits<uint64_t>::max()
            : budget_ns * 2u;
        const uint64_t three = budget_ns > std::numeric_limits<uint64_t>::max() / 3u
            ? std::numeric_limits<uint64_t>::max()
            : budget_ns * 3u;
        if (elapsed_ns > one_and_a_half) over_150x_.fetch_add(1, std::memory_order_relaxed);
        if (elapsed_ns > two) over_2x_.fetch_add(1, std::memory_order_relaxed);
        if (elapsed_ns > three) over_3x_.fetch_add(1, std::memory_order_relaxed);
    }

    TimingSummary summary() const {
        TimingSummary result{};
        result.count = std::min(count_.load(std::memory_order_relaxed), kTimingSamples);
        if (result.count) {
            std::array<uint64_t, kTimingSamples> ordered{};
            for (std::size_t index = 0; index < result.count; ++index) {
                ordered[index] = values_[index].load(std::memory_order_relaxed);
            }
            std::sort(ordered.begin(), ordered.begin() + static_cast<std::ptrdiff_t>(result.count));
            result.p50_ns = percentile(ordered, result.count, 50);
            result.p95_ns = percentile(ordered, result.count, 95);
            result.p99_ns = percentile(ordered, result.count, 99);
        }
        result.max_ns = max_ns_.load(std::memory_order_relaxed);
        result.deadline_misses = deadline_misses_.load(std::memory_order_relaxed);
        result.over_150x = over_150x_.load(std::memory_order_relaxed);
        result.over_2x = over_2x_.load(std::memory_order_relaxed);
        result.over_3x = over_3x_.load(std::memory_order_relaxed);
        return result;
    }

  private:
    static uint64_t percentile(const std::array<uint64_t, kTimingSamples>& ordered,
                               std::size_t count, unsigned percent) {
        const std::size_t rank = std::max<std::size_t>(1, (count * percent + 99u) / 100u) - 1u;
        return ordered[std::min(rank, count - 1u)];
    }

    std::array<std::atomic<uint64_t>, kTimingSamples> values_{};
    std::atomic<std::size_t> count_{0};
    std::atomic<std::size_t> next_{0};
    std::atomic<uint64_t> max_ns_{0};
    std::atomic<uint64_t> deadline_misses_{0};
    std::atomic<uint64_t> over_150x_{0};
    std::atomic<uint64_t> over_2x_{0};
    std::atomic<uint64_t> over_3x_{0};
};

struct FrameSample {
    uint64_t frame_id = 0;
    uint64_t core_deadline_ns = 0;
    uint64_t input_sample_ns = 0;
    uint64_t emu_begin_ns = 0;
    uint64_t emu_end_ns = 0;
    uint64_t video_ready_ns = 0;
    uint64_t gpu_submit_ns = 0;
    uint64_t present_call_ns = 0;
    uint64_t present_duration_ns = 0;
    uint64_t displayed_ns = 0;
    uint64_t frame_interval_ns = 0;
    uint64_t presentation_interval_ns = 0;
    uint32_t frame_queue_depth = 0;
    uint32_t audio_fill_frames = 0;
    uint64_t audio_xruns = 0;
    uint64_t acquire_wait_us = 0;
    uint64_t fence_wait_us = 0;
    uint64_t save_snapshot_us = 0;
    uint64_t save_io_ms = 0;
    uint64_t rss_bytes = 0;
    bool dropped = false;
    bool duplicated = false;
};

// Opt-in trace storage. Recording is a fixed-size in-memory write and never
// opens a file from the frame path. The file is emitted by the owner during
// shutdown, when no frame callback is running.
class TraceBuffer {
  public:
    void configure_from_env() {
        enabled_ = std::getenv("AN3_PERF_TRACE") && std::string(std::getenv("AN3_PERF_TRACE")) == "1";
        const char* requested_path = std::getenv("AN3_PERF_TRACE_PATH");
        if (!enabled_) {
            path_.clear();
            samples_.reset();
            reset();
            return;
        }
        std::error_code error;
        const auto temporary = std::filesystem::temp_directory_path(error);
        path_ = requested_path && *requested_path ? requested_path
            : (error ? std::string{} : (temporary / "an3-perf-trace.jsonl").string());
        try {
            samples_ = std::make_unique<std::array<FrameSample, kTraceSamples>>();
        } catch (...) {
            enabled_ = false;
            path_.clear();
            samples_.reset();
        }
        reset();
    }

    void reset() {
        next_.store(0, std::memory_order_relaxed);
        count_.store(0, std::memory_order_relaxed);
    }

    bool enabled() const { return enabled_; }
    std::size_t sample_count() const {
        return static_cast<std::size_t>(std::min(next_.load(std::memory_order_relaxed),
                                                 static_cast<uint64_t>(kTraceSamples)));
    }

    void add(const FrameSample& sample) {
        if (!enabled_ || !samples_) return;
        const uint64_t sequence = next_.fetch_add(1, std::memory_order_relaxed);
        (*samples_)[sequence % kTraceSamples] = sample;
        std::size_t observed = count_.load(std::memory_order_relaxed);
        while (observed < kTraceSamples &&
               !count_.compare_exchange_weak(observed, observed + 1, std::memory_order_relaxed)) {}
    }

    bool write_jsonl(const std::string& core_id, uint64_t budget_ns) const {
        if (!enabled_ || !samples_ || path_.empty()) return false;
        std::ofstream output(path_, std::ios::trunc);
        if (!output) return false;
        output << "{\"type\":\"meta\",\"schema\":1,\"core_id\":\"" << core_id
               << "\",\"budget_ns\":" << budget_ns << "}\n";
        const uint64_t total = next_.load(std::memory_order_relaxed);
        const std::size_t count = std::min(total, static_cast<uint64_t>(kTraceSamples));
        const uint64_t first = total > kTraceSamples ? total - kTraceSamples : 0;
        for (std::size_t offset = 0; offset < count; ++offset) {
            const FrameSample& sample = (*samples_)[(first + offset) % kTraceSamples];
            output << "{\"type\":\"frame\",\"frame_id\":" << sample.frame_id
                   << ",\"core_deadline_ns\":" << sample.core_deadline_ns
                   << ",\"input_sample_ns\":" << sample.input_sample_ns
                   << ",\"emu_begin_ns\":" << sample.emu_begin_ns
                   << ",\"emu_end_ns\":" << sample.emu_end_ns
                   << ",\"video_ready_ns\":" << sample.video_ready_ns
                   << ",\"gpu_submit_ns\":" << sample.gpu_submit_ns
                   << ",\"present_call_ns\":" << sample.present_call_ns
                   << ",\"present_duration_ns\":" << sample.present_duration_ns
                   << ",\"displayed_ns\":" << sample.displayed_ns
                   << ",\"frame_interval_ns\":" << sample.frame_interval_ns
                   << ",\"presentation_interval_ns\":" << sample.presentation_interval_ns
                   << ",\"frame_queue_depth\":" << sample.frame_queue_depth
                   << ",\"audio_fill_frames\":" << sample.audio_fill_frames
                   << ",\"audio_xruns\":" << sample.audio_xruns
                   << ",\"acquire_wait_us\":" << sample.acquire_wait_us
                   << ",\"fence_wait_us\":" << sample.fence_wait_us
                   << ",\"save_snapshot_us\":" << sample.save_snapshot_us
                   << ",\"save_io_ms\":" << sample.save_io_ms
                   << ",\"rss_bytes\":" << sample.rss_bytes
                   << ",\"dropped\":" << (sample.dropped ? "true" : "false")
                   << ",\"duplicated\":" << (sample.duplicated ? "true" : "false") << "}\n";
        }
        return static_cast<bool>(output);
    }

  private:
    std::unique_ptr<std::array<FrameSample, kTraceSamples>> samples_;
    std::atomic<uint64_t> next_{0};
    std::atomic<std::size_t> count_{0};
    bool enabled_ = false;
    std::string path_;
};

} // namespace an3::perf
