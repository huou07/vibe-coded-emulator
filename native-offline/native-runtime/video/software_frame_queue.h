// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "../core/video_backend.h"
#include "../core/perf_telemetry.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <mutex>
#include <vector>

namespace an3 {

// Keeps software-core callbacks off the platform presenter thread. The core
// writes one of three reusable slots; the SDL/GL/Vulkan presenter consumes the
// oldest ready slot from its own thread. A full ring replaces only the oldest
// ready frame, never a frame currently being presented.
class NativeSoftwareFrameQueue final : public NativeVideoBackend {
  public:
    static constexpr std::size_t kCapacity = 3;

    explicit NativeSoftwareFrameQueue(NativeVideoBackend& presenter);

    bool initialize(NativeWindowSurface&, std::string&) override;
    void resize() override;
    bool begin_frame() override;
    bool acquire_software_framebuffer(unsigned, unsigned, int, void*&, std::size_t&) override;
    void present_software(const void*, unsigned, unsigned, std::size_t, int) override;
    void finish_frame() override;
    bool receive_native_gpu_frame(const void*, std::string&) override;
    void present_native_gpu_frame(unsigned, unsigned) override;
    NativeVideoStatus metrics() const override;
    void shutdown() override;

    // Called by the platform presentation/event thread only.
    bool present_pending();
    std::size_t pending_frames() const;

  private:
    enum class SlotState : uint8_t { Free, Writing, Ready, Presenting };
    static constexpr std::size_t kNoSlot = std::numeric_limits<std::size_t>::max();

    struct Slot {
        std::vector<uint8_t> pixels;
        unsigned width = 0;
        unsigned height = 0;
        std::size_t pitch = 0;
        int pixel_format = 1;
        uint64_t frame_id = 0;
        bool duplicate = false;
        SlotState state = SlotState::Free;
    };

    static bool frame_shape(unsigned width, unsigned height, int pixel_format,
                            std::size_t pitch, std::size_t& bytes_per_pixel,
                            std::size_t& bytes);
    std::size_t choose_writable_slot_locked();
    std::size_t choose_oldest_ready_slot_locked() const;

    NativeVideoBackend& presenter_;
    mutable std::mutex mutex_;
    std::array<Slot, kCapacity> slots_{};
    std::size_t writing_slot_ = kNoSlot;
    uint64_t next_frame_id_ = 0;
    uint64_t published_frames_ = 0;
    uint64_t presented_frames_ = 0;
    uint64_t dropped_frames_ = 0;
    uint64_t duplicated_frames_ = 0;
    uint32_t queue_depth_max_ = 0;
    perf::TimingSeries present_timings_{};
    perf::TimingSeries queue_depth_timings_{};
    bool active_ = true;
};

} // namespace an3
