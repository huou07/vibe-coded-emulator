// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#include "software_frame_queue.h"

#include "../core/vendor/libretro.h"

#include <algorithm>
#include <cstring>

namespace an3 {
namespace {
constexpr std::size_t kMaxFrameBytes = 64u * 1024u * 1024u;
constexpr unsigned kMaxFrameDimension = 8192;
}

NativeSoftwareFrameQueue::NativeSoftwareFrameQueue(NativeVideoBackend& presenter)
    : presenter_(presenter) {}

bool NativeSoftwareFrameQueue::initialize(NativeWindowSurface&, std::string&) {
    std::lock_guard<std::mutex> lock(mutex_);
    active_ = true;
    writing_slot_ = kNoSlot;
    next_frame_id_ = 0;
    published_frames_ = 0;
    presented_frames_ = 0;
    dropped_frames_ = 0;
    duplicated_frames_ = 0;
    queue_depth_max_ = 0;
    for (auto& slot : slots_) {
        slot.state = SlotState::Free;
        slot.pixels.clear();
    }
    return true;
}

void NativeSoftwareFrameQueue::resize() {
    // The wrapped presenter owns the platform window and must be resized on
    // the platform thread, never from the core owner.
    presenter_.resize();
}

bool NativeSoftwareFrameQueue::begin_frame() {
    std::lock_guard<std::mutex> lock(mutex_);
    return active_;
}

bool NativeSoftwareFrameQueue::frame_shape(unsigned width, unsigned height, int pixel_format,
                                           std::size_t pitch, std::size_t& bytes_per_pixel,
                                           std::size_t& bytes) {
    if (!width || !height || width > kMaxFrameDimension || height > kMaxFrameDimension) return false;
    if (pixel_format == RETRO_PIXEL_FORMAT_XRGB8888) bytes_per_pixel = 4;
    else if (pixel_format == RETRO_PIXEL_FORMAT_0RGB1555 || pixel_format == RETRO_PIXEL_FORMAT_RGB565) bytes_per_pixel = 2;
    else return false;
    const std::size_t row = static_cast<std::size_t>(width) * bytes_per_pixel;
    if (row / bytes_per_pixel != width || (pitch && pitch < row) || height > kMaxFrameBytes / row) return false;
    bytes = row * height;
    return bytes <= kMaxFrameBytes;
}

std::size_t NativeSoftwareFrameQueue::choose_oldest_ready_slot_locked() const {
    std::size_t selected = kNoSlot;
    uint64_t oldest = std::numeric_limits<uint64_t>::max();
    for (std::size_t index = 0; index < slots_.size(); ++index) {
        const auto& slot = slots_[index];
        if (slot.state != SlotState::Ready) continue;
        if (selected == kNoSlot || slot.frame_id < oldest) {
            selected = index;
            oldest = slot.frame_id;
        }
    }
    return selected;
}

std::size_t NativeSoftwareFrameQueue::choose_writable_slot_locked() {
    for (std::size_t index = 0; index < slots_.size(); ++index) {
        if (slots_[index].state == SlotState::Free) return index;
    }
    const std::size_t selected = choose_oldest_ready_slot_locked();
    if (selected != kNoSlot) ++dropped_frames_;
    return selected;
}

bool NativeSoftwareFrameQueue::acquire_software_framebuffer(unsigned width, unsigned height, int pixel_format,
                                                            void*& data, std::size_t& pitch) {
    data = nullptr;
    pitch = 0;
    std::size_t bytes_per_pixel = 0, bytes = 0;
    if (!frame_shape(width, height, pixel_format, 0, bytes_per_pixel, bytes)) {
        return false;
    }
    std::lock_guard<std::mutex> lock(mutex_);
    if (!active_) return false;
    if (writing_slot_ == kNoSlot) writing_slot_ = choose_writable_slot_locked();
    if (writing_slot_ == kNoSlot) return false;
    auto& slot = slots_[writing_slot_];
    slot.state = SlotState::Writing;
    slot.width = width;
    slot.height = height;
    slot.pitch = static_cast<std::size_t>(width) * bytes_per_pixel;
    slot.pixel_format = pixel_format;
    slot.duplicate = false;
    slot.pixels.resize(bytes);
    data = slot.pixels.data();
    pitch = slot.pitch;
    return true;
}

void NativeSoftwareFrameQueue::present_software(const void* data, unsigned width, unsigned height,
                                                std::size_t pitch, int pixel_format) {
    std::size_t bytes_per_pixel = 0, bytes = 0;
    const bool duplicate = data == nullptr;
    if (!duplicate && !frame_shape(width, height, pixel_format, pitch, bytes_per_pixel, bytes)) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (writing_slot_ != kNoSlot) slots_[writing_slot_].state = SlotState::Free;
        writing_slot_ = kNoSlot;
        ++dropped_frames_;
        return;
    }
    std::lock_guard<std::mutex> lock(mutex_);
    if (!active_) return;
    if (writing_slot_ == kNoSlot) writing_slot_ = choose_writable_slot_locked();
    if (writing_slot_ == kNoSlot) {
        ++dropped_frames_;
        return;
    }
    auto& slot = slots_[writing_slot_];
    slot.width = width;
    slot.height = height;
    slot.pixel_format = pixel_format;
    slot.duplicate = duplicate;
    if (duplicate) {
        slot.pitch = 0;
        slot.pixels.clear();
    } else {
        slot.pitch = static_cast<std::size_t>(width) * bytes_per_pixel;
        if (data != slot.pixels.data() || pitch != slot.pitch || slot.pixels.size() != bytes) {
            slot.pixels.resize(bytes);
            const auto* source = static_cast<const uint8_t*>(data);
            for (unsigned row = 0; row < height; ++row) {
                std::memcpy(slot.pixels.data() + static_cast<std::size_t>(row) * slot.pitch,
                            source + static_cast<std::size_t>(row) * pitch, slot.pitch);
            }
        }
    }
    slot.frame_id = ++next_frame_id_;
    slot.state = SlotState::Ready;
    ++published_frames_;
    if (duplicate) ++duplicated_frames_;
    std::size_t ready = 0;
    for (const auto& candidate : slots_) {
        if (candidate.state == SlotState::Ready || candidate.state == SlotState::Presenting) ++ready;
    }
    queue_depth_max_ = std::max<uint32_t>(queue_depth_max_, static_cast<uint32_t>(ready));
    writing_slot_ = kNoSlot;
}

void NativeSoftwareFrameQueue::finish_frame() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (writing_slot_ == kNoSlot) return;
    slots_[writing_slot_].state = SlotState::Free;
    writing_slot_ = kNoSlot;
    ++dropped_frames_;
}

bool NativeSoftwareFrameQueue::receive_native_gpu_frame(const void*, std::string& error) {
    error = "hardware-frame: the software frame queue accepts only CPU frames";
    return false;
}

void NativeSoftwareFrameQueue::present_native_gpu_frame(unsigned, unsigned) {}

bool NativeSoftwareFrameQueue::present_pending() {
    std::size_t selected = kNoSlot;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (!active_) return false;
        selected = choose_oldest_ready_slot_locked();
        if (selected == kNoSlot) return false;
        slots_[selected].state = SlotState::Presenting;
    }

    Slot* slot = nullptr;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        slot = &slots_[selected];
    }
    if (!slot->duplicate) {
        presenter_.present_software(slot->pixels.data(), slot->width, slot->height,
                                    slot->pitch, slot->pixel_format);
    }
    {
        std::lock_guard<std::mutex> lock(mutex_);
        slots_[selected].state = SlotState::Free;
        ++presented_frames_;
    }
    return true;
}

std::size_t NativeSoftwareFrameQueue::pending_frames() const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::size_t count = 0;
    for (const auto& slot : slots_) {
        if (slot.state == SlotState::Ready || slot.state == SlotState::Presenting) ++count;
    }
    return count;
}

NativeVideoStatus NativeSoftwareFrameQueue::metrics() const {
    NativeVideoStatus result = presenter_.metrics();
    std::lock_guard<std::mutex> lock(mutex_);
    result.frames.dropped_frames += dropped_frames_;
    result.frames.duplicated_frames += duplicated_frames_;
    result.frames.queue_depth_max = std::max<uint32_t>(result.frames.queue_depth_max, queue_depth_max_);
    std::size_t pending = 0;
    for (const auto& slot : slots_) {
        if (slot.state == SlotState::Ready || slot.state == SlotState::Presenting) ++pending;
    }
    result.frames_in_flight = static_cast<uint32_t>(std::max<std::size_t>(result.frames_in_flight, pending));
    return result;
}

void NativeSoftwareFrameQueue::shutdown() {
    std::lock_guard<std::mutex> lock(mutex_);
    active_ = false;
    writing_slot_ = kNoSlot;
    for (auto& slot : slots_) {
        slot.state = SlotState::Free;
        slot.pixels.clear();
    }
}

} // namespace an3
