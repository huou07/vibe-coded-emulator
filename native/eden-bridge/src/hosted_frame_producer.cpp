// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Hosted-frame producer (Route B). Eden calls the weak hook
// `an3_eden_hosted_frame_hook` from its Vulkan swapchain present path with the
// just-presented VkImage plus the Vulkan device context. This file is the
// strong definition: it GPU-copies the presented swapchain image into a
// bridge-owned, IOSurface-backed VkImage and publishes that IOSurface's global
// id through the versioned ring, so an out-of-process host can import it.
//
// Design notes (M1):
//   - The destination image is underlaid with an IOSurface via
//     vkUseIOSurfaceMVK() (MoltenVK). We create the IOSurface with the exact
//     properties MoltenVK validates: width, height, 4 bytes/element, 1x1
//     elements and the 'BGRA' pixel format.
//   - The destination image uses VK_IMAGE_TILING_LINEAR: MoltenVK only backs
//     linear, transfer-only images with the shared storage an IOSurface needs.
//   - A temporary full graphics-queue wait plus a per-slot fence is used for
//     M1. It is slow but provably orders our copy after Eden's render. The
//     bounded ring still gives newest-frame-wins and never-overwrite-consumer
//     semantics.
//   - It never logs a pointer and never copies pixel data across the ABI: only
//     the global IOSurface id and frame metadata.
#if defined(__APPLE__)

#include "an3_eden_hosted_frame.h"
#include "an3_eden_hosted_frame_shm.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <thread>

#include <CoreFoundation/CoreFoundation.h>
#include <IOSurface/IOSurface.h>
#include <dlfcn.h>
#include <unistd.h>
#include <vulkan/vulkan.h>

namespace {

using UseIOSurfaceFn = VkResult (*)(VkImage, IOSurfaceRef);
using GetIOSurfaceFn = void (*)(VkImage, IOSurfaceRef*);

// 'BGRA' four-character code used by kIOSurfacePixelFormat.
constexpr int32_t kIosurfacePixelFormatBgra = 0x42475241;

// Changes every companion start (and on every producer slot recreation) so the
// consumer can discard stale descriptors.
uint64_t g_epoch = (static_cast<uint64_t>(arc4random()) << 32) ^ arc4random();

// Test/diagnostic only: rebuild the slots after this many published frames to
// exercise the swapchain-recreation path without a real window resize. 0 (the
// default) disables it. Set via AN3_HOSTED_FORCE_RECREATE_AFTER.
const uint32_t g_force_recreate_after = [] {
    const char* value = std::getenv("AN3_HOSTED_FORCE_RECREATE_AFTER");
    return value != nullptr ? static_cast<uint32_t>(std::strtoul(value, nullptr, 10)) : 0u;
}();

// Test/diagnostic only: the extent a forced recreation rebuilds to ("WxH").
// Empty means "keep the current extent". Used with the trigger above to prove
// the slot rebuild actually allocates and copies at a different size.
struct ForceResize {
    uint32_t width{0};
    uint32_t height{0};
};

const ForceResize g_force_resize = [] {
    ForceResize result;
    const char* value = std::getenv("AN3_HOSTED_FORCE_RESIZE");
    if (value != nullptr) {
        unsigned width = 0;
        unsigned height = 0;
        if (std::sscanf(value, "%ux%u", &width, &height) == 2) {
            result.width = width;
            result.height = height;
        }
    }
    return result;
}();

// MoltenVK entry points resolved at runtime. Eden loads MoltenVK itself
// (RTLD_LOCAL), so the bridge must resolve the same library explicitly; it
// never links the loader.
struct MoltenVk {
    PFN_vkCreateImage create_image{};
    PFN_vkGetImageMemoryRequirements get_image_memory_requirements{};
    PFN_vkAllocateMemory allocate_memory{};
    PFN_vkBindImageMemory bind_image_memory{};
    PFN_vkGetDeviceQueue get_device_queue{};
    PFN_vkCreateCommandPool create_command_pool{};
    PFN_vkAllocateCommandBuffers allocate_command_buffers{};
    PFN_vkResetCommandBuffer reset_command_buffer{};
    PFN_vkBeginCommandBuffer begin_command_buffer{};
    PFN_vkCmdPipelineBarrier cmd_pipeline_barrier{};
    PFN_vkCmdCopyImage cmd_copy_image{};
    PFN_vkEndCommandBuffer end_command_buffer{};
    PFN_vkCreateFence create_fence{};
    PFN_vkResetFences reset_fences{};
    PFN_vkQueueSubmit queue_submit{};
    PFN_vkWaitForFences wait_for_fences{};
    PFN_vkDeviceWaitIdle device_wait_idle{};
    PFN_vkDestroyImage destroy_image{};
    PFN_vkFreeMemory free_memory{};
    PFN_vkDestroyFence destroy_fence{};
    PFN_vkDestroyCommandPool destroy_command_pool{};
    UseIOSurfaceFn use_iosurface{};
    GetIOSurfaceFn get_iosurface{};
};

void* library_handle() {
    static void* handle = nullptr;
    if (handle != nullptr) {
        return handle;
    }
    // Prefer the exact dylib Eden was told to load; the handle is deduplicated
    // by dyld, so this is the same MoltenVK instance Eden uses.
    const char* path = std::getenv("LIBVULKAN_PATH");
    if (path != nullptr && path[0] != '\0') {
        handle = dlopen(path, RTLD_NOW | RTLD_LOCAL);
        if (handle != nullptr) {
            return handle;
        }
    }
    static const char* const alternatives[] = {"libMoltenVK.dylib", "libvulkan.1.dylib",
                                               "libvulkan.dylib"};
    for (const char* alt : alternatives) {
        handle = dlopen(alt, RTLD_NOW | RTLD_LOCAL);
        if (handle != nullptr) {
            return handle;
        }
    }
    return nullptr;
}

template <typename T>
T load(const char* name) {
    void* handle = library_handle();
    return reinterpret_cast<T>(handle != nullptr ? dlsym(handle, name) : nullptr);
}

bool resolve_api(MoltenVk& vk) {
    vk.create_image = load<PFN_vkCreateImage>("vkCreateImage");
    vk.get_image_memory_requirements =
        load<PFN_vkGetImageMemoryRequirements>("vkGetImageMemoryRequirements");
    vk.allocate_memory = load<PFN_vkAllocateMemory>("vkAllocateMemory");
    vk.bind_image_memory = load<PFN_vkBindImageMemory>("vkBindImageMemory");
    vk.get_device_queue = load<PFN_vkGetDeviceQueue>("vkGetDeviceQueue");
    vk.create_command_pool = load<PFN_vkCreateCommandPool>("vkCreateCommandPool");
    vk.allocate_command_buffers =
        load<PFN_vkAllocateCommandBuffers>("vkAllocateCommandBuffers");
    vk.reset_command_buffer = load<PFN_vkResetCommandBuffer>("vkResetCommandBuffer");
    vk.begin_command_buffer = load<PFN_vkBeginCommandBuffer>("vkBeginCommandBuffer");
    vk.cmd_pipeline_barrier = load<PFN_vkCmdPipelineBarrier>("vkCmdPipelineBarrier");
    vk.cmd_copy_image = load<PFN_vkCmdCopyImage>("vkCmdCopyImage");
    vk.end_command_buffer = load<PFN_vkEndCommandBuffer>("vkEndCommandBuffer");
    vk.create_fence = load<PFN_vkCreateFence>("vkCreateFence");
    vk.reset_fences = load<PFN_vkResetFences>("vkResetFences");
    vk.queue_submit = load<PFN_vkQueueSubmit>("vkQueueSubmit");
    vk.wait_for_fences = load<PFN_vkWaitForFences>("vkWaitForFences");
    vk.device_wait_idle = load<PFN_vkDeviceWaitIdle>("vkDeviceWaitIdle");
    vk.destroy_image = load<PFN_vkDestroyImage>("vkDestroyImage");
    vk.free_memory = load<PFN_vkFreeMemory>("vkFreeMemory");
    vk.destroy_fence = load<PFN_vkDestroyFence>("vkDestroyFence");
    vk.destroy_command_pool = load<PFN_vkDestroyCommandPool>("vkDestroyCommandPool");
    vk.use_iosurface = load<UseIOSurfaceFn>("vkUseIOSurfaceMVK");
    vk.get_iosurface = load<GetIOSurfaceFn>("vkGetIOSurfaceMVK");
    return vk.create_image != nullptr && vk.get_image_memory_requirements != nullptr &&
           vk.allocate_memory != nullptr && vk.bind_image_memory != nullptr &&
           vk.get_device_queue != nullptr && vk.create_command_pool != nullptr &&
           vk.allocate_command_buffers != nullptr && vk.reset_command_buffer != nullptr &&
           vk.begin_command_buffer != nullptr && vk.cmd_pipeline_barrier != nullptr &&
           vk.cmd_copy_image != nullptr && vk.end_command_buffer != nullptr &&
           vk.create_fence != nullptr && vk.reset_fences != nullptr &&
           vk.queue_submit != nullptr && vk.wait_for_fences != nullptr &&
           vk.device_wait_idle != nullptr && vk.destroy_image != nullptr &&
           vk.free_memory != nullptr && vk.destroy_fence != nullptr &&
           vk.destroy_command_pool != nullptr && vk.use_iosurface != nullptr &&
           vk.get_iosurface != nullptr;
}

uint32_t map_pixel_format(unsigned vk_format) {
    switch (vk_format) {
    case VK_FORMAT_B8G8R8A8_UNORM:
    case VK_FORMAT_B8G8R8A8_SRGB:
        return AN3_EDEN_PIXEL_FORMAT_BGRA8_UNORM;
    default:
        return AN3_EDEN_PIXEL_FORMAT_UNKNOWN;
    }
}

// Cross-process ring in POSIX shared memory; null when creation failed, in
// which case the producer falls back to an in-process ring (M1 behaviour).
an3_eden_hosted_shm* g_shm = nullptr;
char g_shm_name[40] = {0};

an3_eden_hosted_ring& local_ring() {
    static an3_eden_hosted_ring instance;
    static const bool ready = [] {
        an3_eden_hosted_ring_init(&instance, AN3_EDEN_HOSTED_PROTOCOL_VERSION);
        return true;
    }();
    (void)ready;
    return instance;
}

an3_eden_hosted_ring* active_ring() {
    return g_shm != nullptr ? &g_shm->ring : &local_ring();
}

// Holds the process-shared lock across pick -> GPU copy -> publish so the
// producer never writes a slot the consumer still owns. The consumer releases
// the lock before it imports pixels, so neither side blocks the other on GPU
// work.
struct RingGuard {
    explicit RingGuard(an3_eden_hosted_shm* shm) : shm_(shm) {
        if (shm_ == nullptr) {
            return;
        }
        // Bounded acquisition: a consumer that died while holding the lock must
        // not hang the emulator, so give up and drop the frame instead.
        for (int attempt = 0; attempt < 250; ++attempt) {
            if (an3_eden_hosted_shm_trylock(shm_) == AN3_EDEN_HOSTED_OK) {
                locked_ = true;
                return;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    }
    ~RingGuard() {
        if (shm_ != nullptr && locked_) {
            an3_eden_hosted_shm_unlock(shm_);
        }
    }
    RingGuard(const RingGuard&) = delete;
    RingGuard& operator=(const RingGuard&) = delete;
    bool locked() const { return locked_; }

  private:
    an3_eden_hosted_shm* shm_;
    bool locked_{false};
};

uint32_t lowest_bit_index(VkMemoryRequirements requirements) {
    const uint32_t bits = requirements.memoryTypeBits;
    return bits == 0 ? 0u : static_cast<uint32_t>(__builtin_ctz(bits));
}

// IOSurfaceCreate with the properties MoltenVK's vkUseIOSurfaceMVK validates.
IOSurfaceRef create_iosurface(uint32_t width, uint32_t height) {
    CFMutableDictionaryRef properties = CFDictionaryCreateMutable(
        kCFAllocatorDefault, 0, &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    if (properties == nullptr) {
        return nullptr;
    }
    int32_t iw = static_cast<int32_t>(width);
    int32_t ih = static_cast<int32_t>(height);
    int32_t bytes_per_element = 4;
    int32_t element_width = 1;
    int32_t element_height = 1;
    int32_t pixel_format = kIosurfacePixelFormatBgra;
    const auto set_number = [&](CFStringRef key, int32_t value) {
        CFNumberRef number = CFNumberCreate(kCFAllocatorDefault, kCFNumberSInt32Type, &value);
        if (number != nullptr) {
            CFDictionarySetValue(properties, key, number);
            CFRelease(number);
        }
    };
    set_number(kIOSurfaceWidth, iw);
    set_number(kIOSurfaceHeight, ih);
    set_number(kIOSurfaceBytesPerElement, bytes_per_element);
    set_number(kIOSurfaceElementWidth, element_width);
    set_number(kIOSurfaceElementHeight, element_height);
    set_number(kIOSurfacePixelFormat, pixel_format);
    // Deprecated since 10.11 and ignored on modern macOS (all surfaces are
    // globally lookup-able by id), but harmless and matches MoltenVK's own
    // IOSurface creation for maximum compatibility.
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    CFDictionarySetValue(properties, kIOSurfaceIsGlobal, kCFBooleanTrue);
#pragma clang diagnostic pop
    IOSurfaceRef surface = IOSurfaceCreate(properties);
    CFRelease(properties);
    return surface;
}

struct Slot {
    IOSurfaceRef surface{nullptr};
    bool owns_surface_ref{false};
    uint64_t surface_id{0};
    VkImage image{VK_NULL_HANDLE};
    VkDeviceMemory memory{VK_NULL_HANDLE};
    VkCommandBuffer command_buffer{VK_NULL_HANDLE};
    VkFence fence{VK_NULL_HANDLE};
};

struct Engine {
    bool attempted{false};
    bool ready{false};
    bool failure_logged{false};
    // Test/diagnostic: tear down and rebuild the slots on the next present
    // without a real swapchain resize (AN3_HOSTED_FORCE_RECREATE_AFTER).
    bool force_recreate{false};
    MoltenVk vk;
    VkDevice device{VK_NULL_HANDLE};
    uint32_t family{0};
    VkQueue queue{VK_NULL_HANDLE};
    VkCommandPool pool{VK_NULL_HANDLE};
    uint32_t width{0};
    uint32_t height{0};
    unsigned vk_format{0};
    Slot slots[AN3_EDEN_HOSTED_RING_SLOTS];
};

Engine& engine() {
    static Engine instance;
    return instance;
}

bool create_slot(Engine& e, Slot& slot, uint32_t slot_index) {
    slot.surface = create_iosurface(e.width, e.height);
    if (slot.surface == nullptr) {
        return false;
    }
    slot.owns_surface_ref = true;

    VkImageCreateInfo image_ci{};
    image_ci.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
    image_ci.imageType = VK_IMAGE_TYPE_2D;
    image_ci.format = static_cast<VkFormat>(e.vk_format);
    image_ci.extent = {e.width, e.height, 1};
    image_ci.mipLevels = 1;
    image_ci.arrayLayers = 1;
    image_ci.samples = VK_SAMPLE_COUNT_1_BIT;
    image_ci.tiling = VK_IMAGE_TILING_LINEAR;
    image_ci.usage = VK_IMAGE_USAGE_TRANSFER_SRC_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT;
    image_ci.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    image_ci.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    if (e.vk.create_image(e.device, &image_ci, nullptr, &slot.image) != VK_SUCCESS ||
        slot.image == VK_NULL_HANDLE) {
        return false;
    }

    VkMemoryRequirements requirements{};
    e.vk.get_image_memory_requirements(e.device, slot.image, &requirements);
    if (requirements.size == 0 || requirements.memoryTypeBits == 0) {
        return false;
    }
    VkMemoryAllocateInfo allocate_info{};
    allocate_info.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
    allocate_info.allocationSize = requirements.size;
    allocate_info.memoryTypeIndex = lowest_bit_index(requirements);
    if (e.vk.allocate_memory(e.device, &allocate_info, nullptr, &slot.memory) != VK_SUCCESS ||
        e.vk.bind_image_memory(e.device, slot.image, slot.memory, 0) != VK_SUCCESS) {
        return false;
    }

    VkResult use_result = e.vk.use_iosurface(slot.image, slot.surface);
    if (use_result != VK_SUCCESS) {
        // Our IOSurface was rejected as incompatible. Fall back to letting
        // MoltenVK create the backing IOSurface, then adopt it (MoltenVK keeps
        // it alive as long as the VkImage lives).
        use_result = e.vk.use_iosurface(slot.image, nullptr);
        if (use_result != VK_SUCCESS) {
            std::printf("\nHF_HOOK {\"init_failed\":1,\"slot\":%u,\"stage\":\"use_iosurface\","
                        "\"result\":%d}\n",
                        slot_index, static_cast<int>(use_result));
            std::fflush(stdout);
            return false;
        }
        IOSurfaceRef adopted = nullptr;
        e.vk.get_iosurface(slot.image, &adopted);
        if (adopted == nullptr) {
            return false;
        }
        CFRelease(slot.surface);
        slot.surface = adopted;
        slot.owns_surface_ref = false;
    } else {
        // De-risk the binding contract: the underlaying IOSurface must be the
        // one we supplied. A mismatch means the copy would target the wrong
        // surface. Do not log the pointer, only the outcome.
        IOSurfaceRef observed = nullptr;
        e.vk.get_iosurface(slot.image, &observed);
        if (observed != slot.surface) {
            std::printf("\nHF_HOOK {\"init_failed\":1,\"slot\":%u,\"stage\":\"iosurface_mismatch\"}\n",
                        slot_index);
            std::fflush(stdout);
            return false;
        }
    }

    slot.surface_id = static_cast<uint64_t>(IOSurfaceGetID(slot.surface));

    VkCommandBufferAllocateInfo command_ai{};
    command_ai.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
    command_ai.commandPool = e.pool;
    command_ai.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    command_ai.commandBufferCount = 1;
    if (e.vk.allocate_command_buffers(e.device, &command_ai, &slot.command_buffer) != VK_SUCCESS) {
        return false;
    }
    VkFenceCreateInfo fence_ci{};
    fence_ci.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
    fence_ci.flags = VK_FENCE_CREATE_SIGNALED_BIT;
    if (e.vk.create_fence(e.device, &fence_ci, nullptr, &slot.fence) != VK_SUCCESS) {
        return false;
    }
    return true;
}

bool create_pool(Engine& e) {
    VkCommandPoolCreateInfo pool_ci{};
    pool_ci.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
    pool_ci.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
    pool_ci.queueFamilyIndex = e.family;
    return e.vk.create_command_pool(e.device, &pool_ci, nullptr, &e.pool) == VK_SUCCESS;
}

bool create_all_slots(Engine& e) {
    for (uint32_t i = 0; i < AN3_EDEN_HOSTED_RING_SLOTS; ++i) {
        if (!create_slot(e, e.slots[i], i)) {
            std::printf("\nHF_HOOK {\"init_failed\":1,\"slot\":%u,\"stage\":\"create_slot\"}\n", i);
            std::fflush(stdout);
            return false;
        }
    }
    return true;
}

void destroy_slot(Engine& e, Slot& slot) {
    // The command buffer belongs to the pool and is freed with it.
    if (slot.fence != VK_NULL_HANDLE) {
        e.vk.destroy_fence(e.device, slot.fence, nullptr);
    }
    if (slot.image != VK_NULL_HANDLE) {
        e.vk.destroy_image(e.device, slot.image, nullptr);
    }
    if (slot.memory != VK_NULL_HANDLE) {
        e.vk.free_memory(e.device, slot.memory, nullptr);
    }
    if (slot.surface != nullptr && slot.owns_surface_ref) {
        CFRelease(slot.surface);
    }
    slot = Slot{};
}

// Releases every slot and the command pool. Called when the swapchain extent or
// format changes so the new size can be allocated (today a mismatch used to be
// rejected forever). Waits for the device first so nothing is in flight.
void teardown_slots(Engine& e) {
    if (e.device != VK_NULL_HANDLE) {
        e.vk.device_wait_idle(e.device);
    }
    for (uint32_t i = 0; i < AN3_EDEN_HOSTED_RING_SLOTS; ++i) {
        destroy_slot(e, e.slots[i]);
    }
    if (e.pool != VK_NULL_HANDLE) {
        e.vk.destroy_command_pool(e.device, e.pool, nullptr);
    }
    e.pool = VK_NULL_HANDLE;
}

// Rebuilds every slot at `width`/`height`/`vk_format`. Used both by the real
// swapchain-recreation path and by the env-gated diagnostic trigger below.
// New IOSurface ids are produced, so the epoch is bumped for consumers.
bool rebuild_slots(Engine& e, unsigned width, unsigned height, unsigned vk_format) {
    teardown_slots(e);
    e.width = width;
    e.height = height;
    e.vk_format = vk_format;
    if (!create_pool(e) || !create_all_slots(e)) {
        e.ready = false;
        std::printf("\nHF_HOOK {\"recreate_failed\":1,\"w\":%u,\"h\":%u}\n", width, height);
        std::fflush(stdout);
        return false;
    }
    g_epoch = (static_cast<uint64_t>(arc4random()) << 32) ^ arc4random();
    std::printf("\nHF_HOOK {\"recreated\":1,\"w\":%u,\"h\":%u,\"epoch\":%llu,"
                "\"surface0\":%llu,\"surface1\":%llu,\"surface2\":%llu}\n",
                width, height, static_cast<unsigned long long>(g_epoch),
                static_cast<unsigned long long>(e.slots[0].surface_id),
                static_cast<unsigned long long>(e.slots[1].surface_id),
                static_cast<unsigned long long>(e.slots[2].surface_id));
    std::fflush(stdout);
    return true;
}

bool ensure_ready(Engine& e, VkDevice device, uint32_t family, unsigned width, unsigned height,
                  unsigned vk_format) {
    if (e.ready) {
        if (e.force_recreate) {
            e.force_recreate = false;
            const unsigned width =
                g_force_resize.width != 0 ? g_force_resize.width : e.width;
            const unsigned height =
                g_force_resize.height != 0 ? g_force_resize.height : e.height;
            return rebuild_slots(e, width, height, e.vk_format);
        }
        if (e.device == device && e.width == width && e.height == height &&
            e.vk_format == vk_format) {
            return true;
        }
        // The swapchain was recreated with a new extent/format. A different
        // device cannot be used with images created here, so refuse instead of
        // corrupting state.
        if (e.device != device) {
            return false;
        }
        return rebuild_slots(e, width, height, vk_format);
    }
    if (e.attempted) {
        return false;
    }
    e.attempted = true;
    if (!resolve_api(e.vk)) {
        std::printf("\nHF_HOOK {\"init_failed\":1,\"stage\":\"resolve_api\"}\n");
        std::fflush(stdout);
        return false;
    }
    e.device = device;
    e.family = family;
    e.width = width;
    e.height = height;
    e.vk_format = vk_format;

    e.vk.get_device_queue(device, family, 0, &e.queue);
    if (e.queue == VK_NULL_HANDLE) {
        std::printf("\nHF_HOOK {\"init_failed\":1,\"stage\":\"get_device_queue\"}\n");
        std::fflush(stdout);
        return false;
    }
    if (!create_pool(e)) {
        std::printf("\nHF_HOOK {\"init_failed\":1,\"stage\":\"create_command_pool\"}\n");
        std::fflush(stdout);
        return false;
    }
    if (!create_all_slots(e)) {
        return false;
    }

    // Publish the ring in POSIX shared memory so the out-of-process host can
    // attach by name. Fall back to the in-process ring if this fails: M1
    // delivery must not depend on the transport.
    char name[40];
    std::snprintf(name, sizeof(name), "/an3hf_%d_%08x", static_cast<int>(getpid()),
                  static_cast<unsigned>(arc4random()));
    if (an3_eden_hosted_shm_create(name, &g_shm) == AN3_EDEN_HOSTED_OK) {
        std::snprintf(g_shm_name, sizeof(g_shm_name), "%s", name);
        std::atexit([] { an3_eden_hosted_shm_unlink(g_shm_name); });
        std::printf("\nAN3CTL_HOSTED {\"shm\":\"%s\",\"slots\":%u,\"epoch\":%llu}\n", g_shm_name,
                    static_cast<unsigned>(AN3_EDEN_HOSTED_RING_SLOTS),
                    static_cast<unsigned long long>(g_epoch));
        std::fflush(stdout);
    } else {
        g_shm = nullptr;
        std::printf("\nHF_HOOK {\"shm\":0}\n");
        std::fflush(stdout);
    }

    e.ready = true;
    std::printf("\nHF_HOOK {\"slots\":%u,\"w\":%u,\"h\":%u,\"surface0\":%llu,\"surface1\":%llu,"
                "\"surface2\":%llu}\n",
                static_cast<unsigned>(AN3_EDEN_HOSTED_RING_SLOTS), width, height,
                static_cast<unsigned long long>(e.slots[0].surface_id),
                static_cast<unsigned long long>(e.slots[1].surface_id),
                static_cast<unsigned long long>(e.slots[2].surface_id));
    std::fflush(stdout);
    return true;
}

// Record and submit the GPU copy presented image -> slot image, then wait for
// it. Ordering comes from Eden's per-frame present fence: it signals once the
// copy-to-swapchain submission (which leaves the image in PRESENT_SRC_KHR) has
// completed, so waiting on it orders our read without draining the queue the
// way vkQueueWaitIdle did. The per-slot fence then only waits for our own copy.
bool copy_frame(Engine& e, const Slot& slot, VkImage presented, VkFence present_fence,
                unsigned source_width, unsigned source_height) {
    if (present_fence != VK_NULL_HANDLE &&
        e.vk.wait_for_fences(e.device, 1, &present_fence, VK_TRUE, UINT64_MAX) != VK_SUCCESS) {
        return false;
    }
    if (e.vk.reset_command_buffer(slot.command_buffer, 0) != VK_SUCCESS) {
        return false;
    }
    VkCommandBufferBeginInfo begin_info{};
    begin_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
    begin_info.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    if (e.vk.begin_command_buffer(slot.command_buffer, &begin_info) != VK_SUCCESS) {
        return false;
    }

    VkImageMemoryBarrier to_transfer_src{};
    to_transfer_src.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
    to_transfer_src.srcAccessMask = VK_ACCESS_MEMORY_READ_BIT;
    to_transfer_src.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
    to_transfer_src.oldLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
    to_transfer_src.newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
    to_transfer_src.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    to_transfer_src.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    to_transfer_src.image = presented;
    to_transfer_src.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};

    VkImageMemoryBarrier to_transfer_dst{};
    to_transfer_dst.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
    to_transfer_dst.srcAccessMask = 0;
    to_transfer_dst.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    to_transfer_dst.oldLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    to_transfer_dst.newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
    to_transfer_dst.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    to_transfer_dst.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    to_transfer_dst.image = slot.image;
    to_transfer_dst.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};

    const VkImageMemoryBarrier pre_barriers[2] = {to_transfer_src, to_transfer_dst};
    e.vk.cmd_pipeline_barrier(slot.command_buffer, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT,
                              VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, nullptr, 0, nullptr, 2,
                              pre_barriers);

    VkImageCopy region{};
    region.srcSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
    region.srcOffset = {0, 0, 0};
    region.dstSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
    region.dstOffset = {0, 0, 0};
    // On a real swapchain resize the source and destination extents match. When
    // they differ (diagnostic forced resize) copy the overlapping region so the
    // transfer remains valid.
    region.extent = {std::min(e.width, source_width), std::min(e.height, source_height), 1};
    e.vk.cmd_copy_image(slot.command_buffer, presented, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                        slot.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &region);

    VkImageMemoryBarrier restore_present{};
    restore_present.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
    restore_present.srcAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
    restore_present.dstAccessMask = VK_ACCESS_MEMORY_READ_BIT;
    restore_present.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
    restore_present.newLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
    restore_present.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    restore_present.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    restore_present.image = presented;
    restore_present.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};

    VkImageMemoryBarrier to_host{};
    to_host.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
    to_host.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    to_host.dstAccessMask = VK_ACCESS_HOST_READ_BIT;
    to_host.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
    to_host.newLayout = VK_IMAGE_LAYOUT_GENERAL;
    to_host.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    to_host.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    to_host.image = slot.image;
    to_host.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};

    const VkImageMemoryBarrier post_barriers[2] = {restore_present, to_host};
    e.vk.cmd_pipeline_barrier(slot.command_buffer, VK_PIPELINE_STAGE_TRANSFER_BIT,
                              VK_PIPELINE_STAGE_ALL_COMMANDS_BIT | VK_PIPELINE_STAGE_HOST_BIT, 0, 0,
                              nullptr, 0, nullptr, 2, post_barriers);

    if (e.vk.end_command_buffer(slot.command_buffer) != VK_SUCCESS) {
        return false;
    }

    VkFence fence = slot.fence;
    e.vk.reset_fences(e.device, 1, &fence);
    VkSubmitInfo submit_info{};
    submit_info.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    submit_info.commandBufferCount = 1;
    submit_info.pCommandBuffers = &slot.command_buffer;
    if (e.vk.queue_submit(e.queue, 1, &submit_info, fence) != VK_SUCCESS) {
        return false;
    }
    return e.vk.wait_for_fences(e.device, 1, &fence, VK_TRUE, UINT64_MAX) == VK_SUCCESS;
}

// Diagnostic only: import the published id the way a cross-process consumer
// would (IOSurfaceLookup), lock it and hash the pixels. This proves the id is a
// valid, readable, IOSurface-backed frame. It is not the transport.
void verify_import(const Slot& slot, const an3_eden_frame_desc& frame) {
    IOSurfaceRef looked_up = IOSurfaceLookup(static_cast<IOSurfaceID>(slot.surface_id));
    if (looked_up == nullptr) {
        std::printf("\nHF_IMPORT {\"seq\":%u,\"slot\":%u,\"surface\":%llu,\"lookup\":0}\n",
                    frame.sequence, frame.slot,
                    static_cast<unsigned long long>(frame.surface_id));
        std::fflush(stdout);
        return;
    }
    uint64_t nonzero = 0;
    uint64_t hash = 1469598103934665603ULL;
    size_t bytes_read = 0;
    int lock_result = -1;
    if (IOSurfaceLock(looked_up, kIOSurfaceLockReadOnly, nullptr) == 0) {
        lock_result = 0;
        const uint8_t* base = static_cast<const uint8_t*>(IOSurfaceGetBaseAddress(looked_up));
        const size_t bytes_per_row = IOSurfaceGetBytesPerRow(looked_up);
        const size_t rows = IOSurfaceGetHeight(looked_up);
        if (base != nullptr) {
            bytes_read = bytes_per_row * rows;
            for (size_t i = 0; i < bytes_read; ++i) {
                const uint8_t byte = base[i];
                hash ^= byte;
                hash *= 1099511628211ULL;
                nonzero += byte != 0 ? 1u : 0u;
            }
        }
        IOSurfaceUnlock(looked_up, kIOSurfaceLockReadOnly, nullptr);
    }
    CFRelease(looked_up);
    std::printf("\nHF_IMPORT {\"seq\":%u,\"slot\":%u,\"surface\":%llu,\"locked\":%d,"
                "\"bytes\":%llu,\"nonzero\":%llu,\"hash\":%llu,\"w\":%u,\"h\":%u}\n",
                frame.sequence, frame.slot, static_cast<unsigned long long>(frame.surface_id),
                lock_result, static_cast<unsigned long long>(bytes_read),
                static_cast<unsigned long long>(nonzero), static_cast<unsigned long long>(hash),
                frame.width, frame.height);
    std::fflush(stdout);
}

std::atomic<uint32_t> g_calls{0};
std::atomic<uint32_t> g_produced{0};
std::atomic<uint32_t> g_dropped{0};
std::atomic<uint32_t> g_rejected{0};
std::atomic<uint32_t> g_copy_errors{0};

} // namespace

extern "C" void an3_eden_hosted_frame_hook(void* device, unsigned graphics_family, void* image,
                                           unsigned width, unsigned height, unsigned vk_format,
                                           void* present_fence) {
    const uint32_t call = g_calls.fetch_add(1, std::memory_order_relaxed) + 1;
    if (call == 1) {
        std::printf("\nHF_HOOK {\"called\":1,\"device_null\":%d,\"family\":%u,\"image_null\":%d,"
                    "\"w\":%u,\"h\":%u,\"vk_format\":%u,\"fence\":%d}\n",
                    device == nullptr ? 1 : 0, graphics_family, image == nullptr ? 1 : 0, width,
                    height, vk_format, present_fence == nullptr ? 0 : 1);
        std::fflush(stdout);
    }
    if (device == nullptr || image == nullptr || width == 0 || height == 0) {
        g_rejected.fetch_add(1, std::memory_order_relaxed);
        return;
    }
    const uint32_t pixel_format = map_pixel_format(vk_format);
    if (pixel_format == AN3_EDEN_PIXEL_FORMAT_UNKNOWN) {
        g_rejected.fetch_add(1, std::memory_order_relaxed);
        if (call <= 2) {
            std::printf("\nHF_HOOK {\"rejected\":1,\"reason\":\"unsupported_format\",\"vk_format\":%u}\n",
                        vk_format);
            std::fflush(stdout);
        }
        return;
    }

    Engine& e = engine();
    if (!ensure_ready(e, reinterpret_cast<VkDevice>(device), graphics_family, width, height,
                      vk_format)) {
        g_rejected.fetch_add(1, std::memory_order_relaxed);
        return;
    }

    RingGuard guard(g_shm);
    if (g_shm != nullptr && !guard.locked()) {
        g_dropped.fetch_add(1, std::memory_order_relaxed);
        return;
    }

    uint32_t slot_index = 0;
    if (an3_eden_hosted_ring_pick_slot(active_ring(), &slot_index) != AN3_EDEN_HOSTED_OK) {
        g_dropped.fetch_add(1, std::memory_order_relaxed);
        return;
    }
    const Slot& slot = e.slots[slot_index];
    if (!copy_frame(e, slot, reinterpret_cast<VkImage>(image),
                    reinterpret_cast<VkFence>(present_fence), width, height)) {
        g_copy_errors.fetch_add(1, std::memory_order_relaxed);
        if (call <= 3 || g_copy_errors.load(std::memory_order_relaxed) % 60u == 0u) {
            std::printf("\nHF_HOOK {\"copy_failed\":1,\"call\":%u,\"copy_errors\":%u}\n", call,
                        g_copy_errors.load(std::memory_order_relaxed));
            std::fflush(stdout);
        }
        return;
    }

    an3_eden_frame_desc frame{};
    frame.protocol_version = AN3_EDEN_HOSTED_PROTOCOL_VERSION;
    frame.sequence = 0;
    frame.slot = slot_index;
    frame.width = width;
    frame.height = height;
    frame.pixel_format = pixel_format;
    frame.producer_epoch = g_epoch;
    frame.surface_id = slot.surface_id;

    const int rc = an3_eden_hosted_ring_publish_into(active_ring(), &frame, slot_index);
    if (rc == AN3_EDEN_HOSTED_ERR_BUSY) {
        g_dropped.fetch_add(1, std::memory_order_relaxed);
        return;
    }
    if (rc != AN3_EDEN_HOSTED_OK) {
        g_rejected.fetch_add(1, std::memory_order_relaxed);
        return;
    }

    const uint32_t produced = g_produced.fetch_add(1, std::memory_order_relaxed) + 1;
    if (g_force_recreate_after > 0 && produced == g_force_recreate_after) {
        e.force_recreate = true;
    }
    if (produced == 1 || produced % 30u == 0u) {
        std::printf("\nHF_PRODUCE {\"epoch\":%llu,\"seq\":%u,\"slot\":%u,\"surface\":%llu,\"w\":%u,"
                    "\"h\":%u,\"format\":%u,\"produced\":%u,\"dropped\":%u,\"rejected\":%u,"
                    "\"copy_errors\":%u}\n",
                    static_cast<unsigned long long>(frame.producer_epoch), frame.sequence, frame.slot,
                    static_cast<unsigned long long>(frame.surface_id), width, height, pixel_format,
                    produced, g_dropped.load(std::memory_order_relaxed),
                    g_rejected.load(std::memory_order_relaxed),
                    g_copy_errors.load(std::memory_order_relaxed));
        std::fflush(stdout);
    }
    // Prove the first published frame is real pixels, not an empty surface.
    if (produced == 1) {
        verify_import(slot, frame);
    }
}

#endif // __APPLE__
