#include <vulkan/vulkan.h>

#include "vulkan_backend.h"

#include <array>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <cstring>
#if defined(_WIN32)
#include <windows.h>
#ifdef interface
#undef interface
#endif
#else
#include <dlfcn.h>
#endif
#include <limits>
#include <mutex>
#include <string>
#include <vector>

namespace an3 {

namespace {

constexpr int kRetroHwContextVulkan = 6;
constexpr int kRetroHwRenderInterfaceVulkan = 0;
constexpr int kRetroHwNegotiationVulkan = 0;
constexpr unsigned kRetroVulkanInterfaceVersion = 5;
constexpr int kRetroPixelFormat0RGB1555 = 0;
constexpr int kRetroPixelFormatXRGB8888 = 1;
constexpr int kRetroPixelFormatRGB565 = 2;
#ifndef AN3_FRAME_RING_SIZE
#define AN3_FRAME_RING_SIZE 2
#endif
static_assert(AN3_FRAME_RING_SIZE >= 2 && AN3_FRAME_RING_SIZE <= 3,
              "The native presenter intentionally bounds its upload ring to two or three slots.");
constexpr uint32_t kFrameRingSize = AN3_FRAME_RING_SIZE;
constexpr uint32_t kMaxSourceWaitSemaphores = 8;
constexpr uint32_t kNoFrameSlot = std::numeric_limits<uint32_t>::max();

struct RetroVulkanImage {
    VkImageView image_view;
    VkImageLayout image_layout;
    VkImageViewCreateInfo create_info;
};

using RetroVulkanSetImage = void (*)(void*, const RetroVulkanImage*, uint32_t, const VkSemaphore*, uint32_t);
using RetroVulkanGetSyncIndex = uint32_t (*)(void*);
using RetroVulkanGetSyncIndexMask = uint32_t (*)(void*);
using RetroVulkanSetCommandBuffers = void (*)(void*, uint32_t, const VkCommandBuffer*);
using RetroVulkanWaitSyncIndex = void (*)(void*);
using RetroVulkanLockQueue = void (*)(void*);
using RetroVulkanUnlockQueue = void (*)(void*);
using RetroVulkanSetSignalSemaphore = void (*)(void*, VkSemaphore);

struct RetroHwRenderInterfaceVulkan {
    int interface_type;
    unsigned interface_version;
    void* handle;
    VkInstance instance;
    VkPhysicalDevice gpu;
    VkDevice device;
    PFN_vkGetDeviceProcAddr get_device_proc_addr;
    PFN_vkGetInstanceProcAddr get_instance_proc_addr;
    VkQueue queue;
    unsigned queue_index;
    RetroVulkanSetImage set_image;
    RetroVulkanGetSyncIndex get_sync_index;
    RetroVulkanGetSyncIndexMask get_sync_index_mask;
    RetroVulkanSetCommandBuffers set_command_buffers;
    RetroVulkanWaitSyncIndex wait_sync_index;
    RetroVulkanLockQueue lock_queue;
    RetroVulkanUnlockQueue unlock_queue;
    RetroVulkanSetSignalSemaphore set_signal_semaphore;
};

struct RetroVulkanContext {
    VkPhysicalDevice gpu;
    VkDevice device;
    VkQueue queue;
    uint32_t queue_family_index;
    VkQueue presentation_queue;
    uint32_t presentation_queue_family_index;
};

using RetroVulkanGetApplicationInfo = const VkApplicationInfo* (*)();
using RetroVulkanCreateDevice = bool (*)(RetroVulkanContext*, VkInstance, VkPhysicalDevice, VkSurfaceKHR,
                                         PFN_vkGetInstanceProcAddr, const char**, unsigned,
                                         const char**, unsigned, const VkPhysicalDeviceFeatures*);
using RetroVulkanDestroyDevice = void (*)();

struct RetroHwRenderContextNegotiationInterfaceVulkan {
    int interface_type;
    unsigned interface_version;
    RetroVulkanGetApplicationInfo get_application_info;
    RetroVulkanCreateDevice create_device;
    RetroVulkanDestroyDevice destroy_device;
};

template <typename T>
T load_instance_function(PFN_vkGetInstanceProcAddr resolver, VkInstance instance, const char* name) {
    return reinterpret_cast<T>(resolver ? resolver(instance, name) : nullptr);
}

template <typename T>
T load_device_function(PFN_vkGetDeviceProcAddr resolver, VkDevice device, const char* name) {
    return reinterpret_cast<T>(resolver ? resolver(device, name) : nullptr);
}

VkExtent2D clamp_extent(const VkSurfaceCapabilitiesKHR& capabilities, VkExtent2D drawable_size) {
    if (capabilities.currentExtent.width != std::numeric_limits<uint32_t>::max()) {
        return capabilities.currentExtent;
    }
    const uint32_t width = std::max(1u, static_cast<uint32_t>(drawable_size.width));
    const uint32_t height = std::max(1u, static_cast<uint32_t>(drawable_size.height));
    return {
        std::clamp(width, capabilities.minImageExtent.width, capabilities.maxImageExtent.width),
        std::clamp(height, capabilities.minImageExtent.height, capabilities.maxImageExtent.height),
    };
}

VkCompositeAlphaFlagBitsKHR composite_alpha(const VkSurfaceCapabilitiesKHR& capabilities) {
    constexpr VkCompositeAlphaFlagBitsKHR values[] = {
        VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR,
        VK_COMPOSITE_ALPHA_PRE_MULTIPLIED_BIT_KHR,
        VK_COMPOSITE_ALPHA_POST_MULTIPLIED_BIT_KHR,
        VK_COMPOSITE_ALPHA_INHERIT_BIT_KHR,
    };
    for (const auto value : values) {
        if (capabilities.supportedCompositeAlpha & value) return value;
    }
    return VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;
}

} // namespace

struct PortableVulkanBackend::Impl {
    explicit Impl(PortableVulkanBackend* frontend) : owner(frontend) {}

    PortableVulkanBackend* owner = nullptr;
    void* runtime = nullptr;
    PFN_vkGetInstanceProcAddr get_instance_proc_addr = nullptr;
    PFN_vkGetDeviceProcAddr get_device_proc_addr = nullptr;
    PFN_vkCreateInstance create_instance = nullptr;
    PFN_vkDestroyInstance destroy_instance = nullptr;
    PFN_vkDestroySurfaceKHR destroy_surface = nullptr;
    PFN_vkEnumeratePhysicalDevices enumerate_physical_devices = nullptr;
    PFN_vkEnumerateDeviceExtensionProperties enumerate_device_extension_properties = nullptr;
    PFN_vkGetPhysicalDeviceQueueFamilyProperties get_queue_family_properties = nullptr;
    PFN_vkGetPhysicalDeviceMemoryProperties get_memory_properties = nullptr;
    PFN_vkGetPhysicalDeviceSurfaceSupportKHR get_surface_support = nullptr;
    PFN_vkGetPhysicalDeviceSurfaceCapabilitiesKHR get_surface_capabilities = nullptr;
    PFN_vkGetPhysicalDeviceSurfaceFormatsKHR get_surface_formats = nullptr;
    PFN_vkGetPhysicalDeviceSurfacePresentModesKHR get_surface_present_modes = nullptr;
    PFN_vkGetPhysicalDeviceFormatProperties get_format_properties = nullptr;
    PFN_vkCreateDevice create_device = nullptr;
    PFN_vkDestroyDevice destroy_device = nullptr;
    PFN_vkDeviceWaitIdle device_wait_idle = nullptr;
    PFN_vkCreateSwapchainKHR create_swapchain = nullptr;
    PFN_vkDestroySwapchainKHR destroy_swapchain = nullptr;
    PFN_vkGetSwapchainImagesKHR get_swapchain_images = nullptr;
    PFN_vkAcquireNextImageKHR acquire_next_image = nullptr;
    PFN_vkQueuePresentKHR queue_present = nullptr;
    PFN_vkCreateCommandPool create_command_pool = nullptr;
    PFN_vkDestroyCommandPool destroy_command_pool = nullptr;
    PFN_vkAllocateCommandBuffers allocate_command_buffers = nullptr;
    PFN_vkResetCommandBuffer reset_command_buffer = nullptr;
    PFN_vkBeginCommandBuffer begin_command_buffer = nullptr;
    PFN_vkEndCommandBuffer end_command_buffer = nullptr;
    PFN_vkCreateSemaphore create_semaphore = nullptr;
    PFN_vkDestroySemaphore destroy_semaphore = nullptr;
    PFN_vkCreateFence create_fence = nullptr;
    PFN_vkDestroyFence destroy_fence = nullptr;
    PFN_vkWaitForFences wait_for_fences = nullptr;
    PFN_vkResetFences reset_fences = nullptr;
    PFN_vkQueueSubmit queue_submit = nullptr;
    PFN_vkCmdPipelineBarrier cmd_pipeline_barrier = nullptr;
    PFN_vkCmdClearColorImage cmd_clear_color_image = nullptr;
    PFN_vkCmdBlitImage cmd_blit_image = nullptr;
    PFN_vkCreateBuffer create_buffer = nullptr;
    PFN_vkDestroyBuffer destroy_buffer = nullptr;
    PFN_vkGetBufferMemoryRequirements get_buffer_memory_requirements = nullptr;
    PFN_vkAllocateMemory allocate_memory = nullptr;
    PFN_vkFreeMemory free_memory = nullptr;
    PFN_vkBindBufferMemory bind_buffer_memory = nullptr;
    PFN_vkMapMemory map_memory = nullptr;
    PFN_vkUnmapMemory unmap_memory = nullptr;
    PFN_vkFlushMappedMemoryRanges flush_mapped_memory_ranges = nullptr;
    PFN_vkCreateImage create_image = nullptr;
    PFN_vkDestroyImage destroy_image = nullptr;
    PFN_vkGetImageMemoryRequirements get_image_memory_requirements = nullptr;
    PFN_vkBindImageMemory bind_image_memory = nullptr;
    PFN_vkCmdCopyBufferToImage cmd_copy_buffer_to_image = nullptr;

    NativeWindowSurface* window_surface = nullptr;
    VkInstance instance = VK_NULL_HANDLE;
    VkSurfaceKHR surface = VK_NULL_HANDLE;
    VkPhysicalDevice physical_device = VK_NULL_HANDLE;
    VkDevice device = VK_NULL_HANDLE;
    VkQueue queue = VK_NULL_HANDLE;
    VkQueue presentation_queue = VK_NULL_HANDLE;
    uint32_t queue_family_index = 0;
    uint32_t presentation_queue_family_index = 0;
    VkSwapchainKHR swapchain = VK_NULL_HANDLE;
    VkExtent2D extent{};
    VkFormat swapchain_format = VK_FORMAT_UNDEFINED;
    VkColorSpaceKHR swapchain_color_space = VK_COLOR_SPACE_SRGB_NONLINEAR_KHR;
    std::vector<VkImage> swapchain_images;
    std::vector<VkCommandBuffer> command_buffers;
    std::vector<bool> image_initialized;
    std::vector<VkFence> image_in_flight;
    VkCommandPool command_pool = VK_NULL_HANDLE;

    // A CoreVulkan frame can fail before the normal presentation submit gets
    // to wait its source semaphores. Keep an independent, reusable drain
    // command/fence so resize recovery never overwrites those one-shot waits.
    // This pool must not be tied to the swapchain pool: the latter is exactly
    // what an out-of-date path is allowed to rebuild first.
    VkCommandPool core_drain_command_pool = VK_NULL_HANDLE;
    VkCommandBuffer core_drain_command = VK_NULL_HANDLE;
    VkFence core_drain_fence = VK_NULL_HANDLE;

    // Two presentation contexts bound the renderer to two frames in flight.
    // The extra swapchain image, when one is available, is intentionally not
    // used to let the emulation core run farther ahead of input.
    struct PresentationFrame {
        VkSemaphore image_available = VK_NULL_HANDLE;
        VkSemaphore render_finished = VK_NULL_HANDLE;
        VkFence in_flight = VK_NULL_HANDLE;
        bool submitted = false;
    };
    std::array<PresentationFrame, kFrameRingSize> presentation_frames{};
    uint32_t next_presentation_frame = 0;
    uint32_t active_presentation_frame = kNoFrameSlot;
    VkFence last_submitted_fence = VK_NULL_HANDLE;

    // Each software slot owns its persistently mapped staging allocation,
    // upload command buffer and upload semaphore. It is reused only after its
    // matching presentation fence is complete.
    struct SoftwareFrameSlot {
        VkCommandBuffer upload_command = VK_NULL_HANDLE;
        VkSemaphore upload_finished = VK_NULL_HANDLE;
        VkBuffer staging_buffer = VK_NULL_HANDLE;
        VkDeviceMemory staging_memory = VK_NULL_HANDLE;
        void* staging_mapping = nullptr;
        VkDeviceSize staging_capacity = 0;
        VkDeviceSize allocation_size = 0;
        bool coherent = true;
        VkDeviceSize flush_atom = 1;
        VkImage image = VK_NULL_HANDLE;
        VkDeviceMemory image_memory = VK_NULL_HANDLE;
        VkFormat image_format = VK_FORMAT_UNDEFINED;
        uint32_t width = 0;
        uint32_t height = 0;
        std::size_t bytes_per_pixel = 0;
        int pixel_format = kRetroPixelFormatXRGB8888;
        bool image_initialized = false;
        bool direct_write_active = false;
    };
    VkCommandPool software_command_pool = VK_NULL_HANDLE;
    std::array<SoftwareFrameSlot, kFrameRingSize> software_slots{};
    uint32_t last_software_slot = kNoFrameSlot;
    RetroHwRenderInterfaceVulkan interface{};
    RetroVulkanDestroyDevice destroy_core_device = nullptr;
    RetroVulkanImage pending_image{};
    std::array<VkSemaphore, kMaxSourceWaitSemaphores> pending_semaphores{};
    uint32_t pending_semaphore_count = 0;
    uint32_t pending_source_queue = VK_QUEUE_FAMILY_IGNORED;
    bool has_pending_image = false;
    enum class Mode {
        None,
        CoreVulkan,
        SoftwareUpload,
    };
    Mode mode = Mode::None;
    bool active = false;
    std::atomic<uint32_t> current_sync_index{0};
    std::atomic<uint64_t> frame_count{0};

    static constexpr size_t kMetricSamples = 256;
    struct TimingSeries {
        std::array<uint32_t, kMetricSamples> values{};
        size_t count = 0;
        size_t next = 0;

        void add(uint64_t microseconds) {
            values[next] = static_cast<uint32_t>(std::min<uint64_t>(microseconds, std::numeric_limits<uint32_t>::max()));
            next = (next + 1u) % values.size();
            count = std::min(count + 1u, values.size());
        }

        uint32_t percentile(unsigned numerator, unsigned denominator) const {
            if (!count || !denominator) return 0;
            std::array<uint32_t, kMetricSamples> sorted{};
            std::copy_n(values.begin(), count, sorted.begin());
            std::sort(sorted.begin(), sorted.begin() + static_cast<std::ptrdiff_t>(count));
            const size_t rank = std::max<size_t>(1u, (count * numerator + denominator - 1u) / denominator);
            return sorted[std::min(count - 1u, rank - 1u)];
        }
    };
    struct Metrics {
        uint64_t dropped_frames = 0;
        uint64_t software_uploads = 0;
        uint64_t direct_software_uploads = 0;
        uint64_t copied_software_uploads = 0;
        uint64_t converted_software_uploads = 0;
        TimingSeries upload{};
        TimingSeries present{};
    } metrics;

    struct ScopedTiming {
        TimingSeries& series;
        std::chrono::steady_clock::time_point started = std::chrono::steady_clock::now();
        ~ScopedTiming() {
            const auto elapsed = std::chrono::steady_clock::now() - started;
            series.add(static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(elapsed).count()));
        }
    };
    mutable std::mutex mutex;

    ~Impl() { shutdown(); }

    VkExtent2D drawable_size() const { return window_surface ? window_surface->extent() : VkExtent2D{1,1}; }

    bool load_runtime(const char* path, std::string& error) {
        if (!path || !*path) {
            error = "The bundled Vulkan runtime runtime is unavailable.";
            return false;
        }
        // The core can log paths while probing a ROM. Keep the graphics runtime
        // quiet in the local-only app so its diagnostics never expose ROM paths.
#if defined(_WIN32)
        // Load the native Vulkan loader from the application or Windows
        // system directory, never from the current directory or PATH.
        runtime = LoadLibraryExW(L"vulkan-1.dll", nullptr,
            LOAD_LIBRARY_SEARCH_APPLICATION_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
        if (!runtime) {
            error = "Cannot load Windows Vulkan loader (error " + std::to_string(GetLastError()) + ").";
            return false;
        }
        get_instance_proc_addr = reinterpret_cast<PFN_vkGetInstanceProcAddr>(
            GetProcAddress(static_cast<HMODULE>(runtime), "vkGetInstanceProcAddr"));
#else
        runtime = dlopen(path, RTLD_NOW | RTLD_LOCAL);
#if defined(__linux__)
        // Development systems normally expose libvulkan.so, whereas a
        // Flatpak runtime intentionally ships only the ABI SONAME. Both are
        // the same native Vulkan loader; this is not a renderer fallback.
        if (!runtime && std::strcmp(path, "libvulkan.so") == 0) {
            runtime = dlopen("libvulkan.so.1", RTLD_NOW | RTLD_LOCAL);
        }
#endif
        if (!runtime) {
            const char* loader_error = dlerror();
            error = std::string("Cannot load bundled Vulkan runtime: ") + (loader_error ? loader_error : "unknown loader error");
            return false;
        }
        get_instance_proc_addr = reinterpret_cast<PFN_vkGetInstanceProcAddr>(dlsym(runtime, "vkGetInstanceProcAddr"));
#endif
        if (!get_instance_proc_addr) {
            error = "Vulkan runtime is missing vkGetInstanceProcAddr.";
            return false;
        }
        create_instance = load_instance_function<PFN_vkCreateInstance>(get_instance_proc_addr, VK_NULL_HANDLE, "vkCreateInstance");
        if (!create_instance) {
            error = "Vulkan runtime cannot create a Vulkan instance.";
            return false;
        }
        return true;
    }

    bool create_vulkan_instance(std::string& error) {
        const auto extensions = window_surface->instance_extensions();
        VkApplicationInfo application{};
        application.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
        application.pApplicationName = "VibeCodedEmulator";
        application.applicationVersion = VK_MAKE_VERSION(0, 2, 0);
        application.pEngineName = "Azahar libretro";
        application.engineVersion = VK_MAKE_VERSION(0, 2, 0);
        application.apiVersion = VK_API_VERSION_1_1;
        VkInstanceCreateInfo info{};
        info.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
        info.pApplicationInfo = &application;
        info.enabledExtensionCount = static_cast<uint32_t>(extensions.size());
        info.ppEnabledExtensionNames = extensions.data();
        if (create_instance(&info, nullptr, &instance) != VK_SUCCESS || !instance) {
            error = "Vulkan runtime could not create a Vulkan 1.1 instance.";
            return false;
        }
        destroy_instance = load_instance_function<PFN_vkDestroyInstance>(get_instance_proc_addr, instance, "vkDestroyInstance");
        destroy_surface = load_instance_function<PFN_vkDestroySurfaceKHR>(get_instance_proc_addr, instance, "vkDestroySurfaceKHR");
        enumerate_physical_devices = load_instance_function<PFN_vkEnumeratePhysicalDevices>(get_instance_proc_addr, instance, "vkEnumeratePhysicalDevices");
        enumerate_device_extension_properties = load_instance_function<PFN_vkEnumerateDeviceExtensionProperties>(get_instance_proc_addr, instance, "vkEnumerateDeviceExtensionProperties");
        get_queue_family_properties = load_instance_function<PFN_vkGetPhysicalDeviceQueueFamilyProperties>(get_instance_proc_addr, instance, "vkGetPhysicalDeviceQueueFamilyProperties");
        get_memory_properties = load_instance_function<PFN_vkGetPhysicalDeviceMemoryProperties>(get_instance_proc_addr, instance, "vkGetPhysicalDeviceMemoryProperties");
        get_surface_support = load_instance_function<PFN_vkGetPhysicalDeviceSurfaceSupportKHR>(get_instance_proc_addr, instance, "vkGetPhysicalDeviceSurfaceSupportKHR");
        get_surface_capabilities = load_instance_function<PFN_vkGetPhysicalDeviceSurfaceCapabilitiesKHR>(get_instance_proc_addr, instance, "vkGetPhysicalDeviceSurfaceCapabilitiesKHR");
        get_surface_formats = load_instance_function<PFN_vkGetPhysicalDeviceSurfaceFormatsKHR>(get_instance_proc_addr, instance, "vkGetPhysicalDeviceSurfaceFormatsKHR");
        get_surface_present_modes = load_instance_function<PFN_vkGetPhysicalDeviceSurfacePresentModesKHR>(get_instance_proc_addr, instance, "vkGetPhysicalDeviceSurfacePresentModesKHR");
        get_format_properties = load_instance_function<PFN_vkGetPhysicalDeviceFormatProperties>(get_instance_proc_addr, instance, "vkGetPhysicalDeviceFormatProperties");
        create_device = load_instance_function<PFN_vkCreateDevice>(get_instance_proc_addr, instance, "vkCreateDevice");
        get_device_proc_addr = load_instance_function<PFN_vkGetDeviceProcAddr>(get_instance_proc_addr, instance, "vkGetDeviceProcAddr");
        if (!destroy_instance || !destroy_surface || !enumerate_physical_devices ||
            !enumerate_device_extension_properties || !get_queue_family_properties || !get_memory_properties ||
            !get_surface_support || !get_surface_capabilities || !get_surface_formats ||
            !get_surface_present_modes || !get_format_properties || !create_device || !get_device_proc_addr) {
            error = "Vulkan runtime is missing a required Vulkan presentation entry point.";
            return false;
        }
        return true;
    }

    bool create_surface(std::string& error) {
        return window_surface && window_surface->create_surface(instance,get_instance_proc_addr,surface,error);
    }

    bool choose_physical_device(std::string& error) {
        uint32_t count = 0;
        if (enumerate_physical_devices(instance, &count, nullptr) != VK_SUCCESS || !count) {
            error = "Vulkan runtime did not expose a Vulkan-capable native GPU.";
            return false;
        }
        std::vector<VkPhysicalDevice> devices(count);
        if (enumerate_physical_devices(instance, &count, devices.data()) != VK_SUCCESS) {
            error = "Vulkan runtime could not enumerate the native GPU.";
            return false;
        }
        for (const auto candidate : devices) {
            uint32_t family_count = 0;
            get_queue_family_properties(candidate, &family_count, nullptr);
            std::vector<VkQueueFamilyProperties> families(family_count);
            get_queue_family_properties(candidate, &family_count, families.data());
            for (uint32_t index = 0; index < family_count; ++index) {
                VkBool32 supports_present = VK_FALSE;
                get_surface_support(candidate, index, surface, &supports_present);
                if ((families[index].queueFlags & VK_QUEUE_GRAPHICS_BIT) && supports_present) {
                    physical_device = candidate;
                    queue_family_index = index;
                    return true;
                }
            }
        }
        error = "No Vulkan graphics queue can present into this native window.";
        return false;
    }

    bool create_core_device(const void* raw_negotiation, std::string& error) {
        const auto* negotiation = static_cast<const RetroHwRenderContextNegotiationInterfaceVulkan*>(raw_negotiation);
        if (!negotiation || negotiation->interface_type != kRetroHwNegotiationVulkan || !negotiation->create_device) {
            error = "Azahar did not provide its Vulkan device-negotiation interface.";
            return false;
        }
        const char* frontend_extensions[] = { VK_KHR_SWAPCHAIN_EXTENSION_NAME };
        VkPhysicalDeviceFeatures required_features{};
        RetroVulkanContext context{};
        if (!negotiation->create_device(&context, instance, physical_device, surface, get_instance_proc_addr,
                                        frontend_extensions, 1, nullptr, 0, &required_features) ||
            !context.device || !context.queue) {
            error = "Azahar could not create a Vulkan device through Vulkan runtime.";
            return false;
        }
        physical_device = context.gpu;
        device = context.device;
        queue = context.queue;
        queue_family_index = context.queue_family_index;
        presentation_queue = context.presentation_queue ? context.presentation_queue : queue;
        presentation_queue_family_index = context.presentation_queue ? context.presentation_queue_family_index : queue_family_index;
        destroy_core_device = negotiation->destroy_device;
        return true;
    }

    bool create_software_device(std::string& error) {
        if (!create_device || !get_device_proc_addr || !enumerate_device_extension_properties) {
            error = "Vulkan runtime is missing the Vulkan device-creation entry points.";
            return false;
        }
        uint32_t extension_count = 0;
        if (enumerate_device_extension_properties(physical_device, nullptr, &extension_count, nullptr) != VK_SUCCESS) {
            error = "Vulkan runtime could not inspect the native GPU device extensions.";
            return false;
        }
        std::vector<VkExtensionProperties> available_extensions(extension_count);
        if (extension_count &&
            enumerate_device_extension_properties(physical_device, nullptr, &extension_count,
                                                  available_extensions.data()) != VK_SUCCESS) {
            error = "Vulkan runtime could not enumerate the native GPU device extensions.";
            return false;
        }
        std::vector<const char*> enabled_extensions = {VK_KHR_SWAPCHAIN_EXTENSION_NAME};
        const auto has_extension = [&available_extensions](const char* wanted) {
            return std::any_of(available_extensions.begin(), available_extensions.end(), [wanted](const VkExtensionProperties& item) {
                return std::strcmp(item.extensionName, wanted) == 0;
            });
        };
        if (!has_extension(VK_KHR_SWAPCHAIN_EXTENSION_NAME)) {
            error = "This native GPU does not expose the Vulkan swapchain extension.";
            return false;
        }
#ifdef VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME
        if (has_extension(VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME)) {
            enabled_extensions.push_back(VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME);
        }
#endif
        constexpr float priority = 1.0f;
        VkDeviceQueueCreateInfo queue_info{};
        queue_info.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
        queue_info.queueFamilyIndex = queue_family_index;
        queue_info.queueCount = 1;
        queue_info.pQueuePriorities = &priority;
        VkDeviceCreateInfo info{};
        info.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
        info.queueCreateInfoCount = 1;
        info.pQueueCreateInfos = &queue_info;
        info.enabledExtensionCount = static_cast<uint32_t>(enabled_extensions.size());
        info.ppEnabledExtensionNames = enabled_extensions.data();
        if (create_device(physical_device, &info, nullptr, &device) != VK_SUCCESS || !device) {
            error = "Vulkan runtime could not create a Vulkan device for software-frame presentation.";
            return false;
        }
        const auto get_queue = load_device_function<PFN_vkGetDeviceQueue>(get_device_proc_addr, device, "vkGetDeviceQueue");
        if (!get_queue) {
            error = "Vulkan runtime is missing vkGetDeviceQueue.";
            return false;
        }
        get_queue(device, queue_family_index, 0, &queue);
        if (!queue) {
            error = "Vulkan runtime did not provide a graphics queue for software-frame presentation.";
            return false;
        }
        presentation_queue = queue;
        presentation_queue_family_index = queue_family_index;
        return true;
    }

    uint32_t find_memory_type(uint32_t type_bits, VkMemoryPropertyFlags desired) const {
        if (!get_memory_properties || !physical_device) return std::numeric_limits<uint32_t>::max();
        VkPhysicalDeviceMemoryProperties properties{};
        get_memory_properties(physical_device, &properties);
        for (uint32_t index = 0; index < properties.memoryTypeCount; ++index) {
            if ((type_bits & (1u << index)) &&
                (properties.memoryTypes[index].propertyFlags & desired) == desired) {
                return index;
            }
        }
        return std::numeric_limits<uint32_t>::max();
    }

    bool load_device_functions(std::string& error) {
        destroy_device = load_device_function<PFN_vkDestroyDevice>(get_device_proc_addr, device, "vkDestroyDevice");
        device_wait_idle = load_device_function<PFN_vkDeviceWaitIdle>(get_device_proc_addr, device, "vkDeviceWaitIdle");
        create_swapchain = load_device_function<PFN_vkCreateSwapchainKHR>(get_device_proc_addr, device, "vkCreateSwapchainKHR");
        destroy_swapchain = load_device_function<PFN_vkDestroySwapchainKHR>(get_device_proc_addr, device, "vkDestroySwapchainKHR");
        get_swapchain_images = load_device_function<PFN_vkGetSwapchainImagesKHR>(get_device_proc_addr, device, "vkGetSwapchainImagesKHR");
        acquire_next_image = load_device_function<PFN_vkAcquireNextImageKHR>(get_device_proc_addr, device, "vkAcquireNextImageKHR");
        queue_present = load_device_function<PFN_vkQueuePresentKHR>(get_device_proc_addr, device, "vkQueuePresentKHR");
        create_command_pool = load_device_function<PFN_vkCreateCommandPool>(get_device_proc_addr, device, "vkCreateCommandPool");
        destroy_command_pool = load_device_function<PFN_vkDestroyCommandPool>(get_device_proc_addr, device, "vkDestroyCommandPool");
        allocate_command_buffers = load_device_function<PFN_vkAllocateCommandBuffers>(get_device_proc_addr, device, "vkAllocateCommandBuffers");
        reset_command_buffer = load_device_function<PFN_vkResetCommandBuffer>(get_device_proc_addr, device, "vkResetCommandBuffer");
        begin_command_buffer = load_device_function<PFN_vkBeginCommandBuffer>(get_device_proc_addr, device, "vkBeginCommandBuffer");
        end_command_buffer = load_device_function<PFN_vkEndCommandBuffer>(get_device_proc_addr, device, "vkEndCommandBuffer");
        create_semaphore = load_device_function<PFN_vkCreateSemaphore>(get_device_proc_addr, device, "vkCreateSemaphore");
        destroy_semaphore = load_device_function<PFN_vkDestroySemaphore>(get_device_proc_addr, device, "vkDestroySemaphore");
        create_fence = load_device_function<PFN_vkCreateFence>(get_device_proc_addr, device, "vkCreateFence");
        destroy_fence = load_device_function<PFN_vkDestroyFence>(get_device_proc_addr, device, "vkDestroyFence");
        wait_for_fences = load_device_function<PFN_vkWaitForFences>(get_device_proc_addr, device, "vkWaitForFences");
        reset_fences = load_device_function<PFN_vkResetFences>(get_device_proc_addr, device, "vkResetFences");
        queue_submit = load_device_function<PFN_vkQueueSubmit>(get_device_proc_addr, device, "vkQueueSubmit");
        cmd_pipeline_barrier = load_device_function<PFN_vkCmdPipelineBarrier>(get_device_proc_addr, device, "vkCmdPipelineBarrier");
        cmd_clear_color_image = load_device_function<PFN_vkCmdClearColorImage>(get_device_proc_addr, device, "vkCmdClearColorImage");
        cmd_blit_image = load_device_function<PFN_vkCmdBlitImage>(get_device_proc_addr, device, "vkCmdBlitImage");
        create_buffer = load_device_function<PFN_vkCreateBuffer>(get_device_proc_addr, device, "vkCreateBuffer");
        destroy_buffer = load_device_function<PFN_vkDestroyBuffer>(get_device_proc_addr, device, "vkDestroyBuffer");
        get_buffer_memory_requirements = load_device_function<PFN_vkGetBufferMemoryRequirements>(get_device_proc_addr, device, "vkGetBufferMemoryRequirements");
        allocate_memory = load_device_function<PFN_vkAllocateMemory>(get_device_proc_addr, device, "vkAllocateMemory");
        free_memory = load_device_function<PFN_vkFreeMemory>(get_device_proc_addr, device, "vkFreeMemory");
        bind_buffer_memory = load_device_function<PFN_vkBindBufferMemory>(get_device_proc_addr, device, "vkBindBufferMemory");
        map_memory = load_device_function<PFN_vkMapMemory>(get_device_proc_addr, device, "vkMapMemory");
        unmap_memory = load_device_function<PFN_vkUnmapMemory>(get_device_proc_addr, device, "vkUnmapMemory");
        create_image = load_device_function<PFN_vkCreateImage>(get_device_proc_addr, device, "vkCreateImage");
        destroy_image = load_device_function<PFN_vkDestroyImage>(get_device_proc_addr, device, "vkDestroyImage");
        get_image_memory_requirements = load_device_function<PFN_vkGetImageMemoryRequirements>(get_device_proc_addr, device, "vkGetImageMemoryRequirements");
        bind_image_memory = load_device_function<PFN_vkBindImageMemory>(get_device_proc_addr, device, "vkBindImageMemory");
        flush_mapped_memory_ranges = load_device_function<PFN_vkFlushMappedMemoryRanges>(get_device_proc_addr, device, "vkFlushMappedMemoryRanges");
        cmd_copy_buffer_to_image = load_device_function<PFN_vkCmdCopyBufferToImage>(get_device_proc_addr, device, "vkCmdCopyBufferToImage");
        if (!destroy_device || !device_wait_idle || !create_swapchain || !destroy_swapchain ||
            !get_swapchain_images || !acquire_next_image || !queue_present || !create_command_pool ||
            !destroy_command_pool || !allocate_command_buffers || !reset_command_buffer ||
            !begin_command_buffer || !end_command_buffer || !create_semaphore || !destroy_semaphore ||
            !create_fence || !destroy_fence || !wait_for_fences || !reset_fences || !queue_submit ||
            !cmd_pipeline_barrier || !cmd_clear_color_image || !cmd_blit_image || !create_buffer ||
            !destroy_buffer || !get_buffer_memory_requirements || !allocate_memory || !free_memory ||
            !bind_buffer_memory || !map_memory || !unmap_memory || !create_image || !destroy_image ||
            !get_image_memory_requirements || !bind_image_memory || !cmd_copy_buffer_to_image || !flush_mapped_memory_ranges) {
            error = "Vulkan runtime is missing a required Vulkan device entry point.";
            return false;
        }
        return true;
    }

    void destroy_swapchain_resources(bool wait_for_gpu) {
        if (device && wait_for_gpu && device_wait_idle) device_wait_idle(device);
        for (auto& frame : presentation_frames) {
            if (frame.in_flight && destroy_fence) destroy_fence(device, frame.in_flight, nullptr);
            if (frame.image_available && destroy_semaphore) destroy_semaphore(device, frame.image_available, nullptr);
            if (frame.render_finished && destroy_semaphore) destroy_semaphore(device, frame.render_finished, nullptr);
            frame = {};
        }
        next_presentation_frame = 0;
        active_presentation_frame = kNoFrameSlot;
        last_submitted_fence = VK_NULL_HANDLE;
        command_buffers.clear();
        if (command_pool && destroy_command_pool) destroy_command_pool(device, command_pool, nullptr);
        command_pool = VK_NULL_HANDLE;
        if (swapchain && destroy_swapchain) destroy_swapchain(device, swapchain, nullptr);
        swapchain = VK_NULL_HANDLE;
        swapchain_images.clear();
        image_initialized.clear();
        image_in_flight.clear();
        extent = {};
        swapchain_format = VK_FORMAT_UNDEFINED;
    }

    bool create_core_drain_resources(std::string& error) {
        if (core_drain_command_pool && core_drain_command && core_drain_fence) return true;
        VkCommandPoolCreateInfo pool_info{};
        pool_info.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
        pool_info.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
        pool_info.queueFamilyIndex = queue_family_index;
        if (create_command_pool(device, &pool_info, nullptr, &core_drain_command_pool) != VK_SUCCESS ||
            !core_drain_command_pool) {
            error = "Vulkan runtime could not create CoreVulkan recovery commands.";
            return false;
        }
        VkCommandBufferAllocateInfo command_info{};
        command_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
        command_info.commandPool = core_drain_command_pool;
        command_info.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        command_info.commandBufferCount = 1;
        if (allocate_command_buffers(device, &command_info, &core_drain_command) != VK_SUCCESS || !core_drain_command) {
            error = "Vulkan runtime could not allocate CoreVulkan recovery commands.";
            destroy_core_drain_resources();
            return false;
        }
        VkFenceCreateInfo fence_info{};
        fence_info.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
        fence_info.flags = VK_FENCE_CREATE_SIGNALED_BIT;
        if (create_fence(device, &fence_info, nullptr, &core_drain_fence) != VK_SUCCESS || !core_drain_fence) {
            error = "Vulkan runtime could not create CoreVulkan recovery synchronization.";
            destroy_core_drain_resources();
            return false;
        }
        return true;
    }

    void destroy_core_drain_resources() {
        if (core_drain_fence && destroy_fence) destroy_fence(device, core_drain_fence, nullptr);
        core_drain_fence = VK_NULL_HANDLE;
        core_drain_command = VK_NULL_HANDLE;
        if (core_drain_command_pool && destroy_command_pool) {
            destroy_command_pool(device, core_drain_command_pool, nullptr);
        }
        core_drain_command_pool = VK_NULL_HANDLE;
    }

    void destroy_software_slot_resources(SoftwareFrameSlot& slot) {
        if (slot.staging_mapping && slot.staging_memory && unmap_memory) {
            unmap_memory(device, slot.staging_memory);
        }
        if (slot.image && destroy_image) destroy_image(device, slot.image, nullptr);
        if (slot.image_memory && free_memory) free_memory(device, slot.image_memory, nullptr);
        if (slot.staging_buffer && destroy_buffer) destroy_buffer(device, slot.staging_buffer, nullptr);
        if (slot.staging_memory && free_memory) free_memory(device, slot.staging_memory, nullptr);
        slot.staging_buffer = VK_NULL_HANDLE;
        slot.staging_memory = VK_NULL_HANDLE;
        slot.staging_mapping = nullptr;
        slot.staging_capacity = 0;
        slot.image = VK_NULL_HANDLE;
        slot.image_memory = VK_NULL_HANDLE;
        slot.image_format = VK_FORMAT_UNDEFINED;
        slot.width = 0;
        slot.height = 0;
        slot.bytes_per_pixel = 0;
        slot.image_initialized = false;
        slot.direct_write_active = false;
    }

    void destroy_software_resources() {
        for (auto& slot : software_slots) {
            destroy_software_slot_resources(slot);
            if (slot.upload_finished && destroy_semaphore) destroy_semaphore(device, slot.upload_finished, nullptr);
            slot.upload_finished = VK_NULL_HANDLE;
            slot.upload_command = VK_NULL_HANDLE;
        }
        if (software_command_pool && destroy_command_pool) destroy_command_pool(device, software_command_pool, nullptr);
        software_command_pool = VK_NULL_HANDLE;
        last_software_slot = kNoFrameSlot;
    }

    static bool native_software_format(int pixel_format, VkFormat& image_format, std::size_t& bytes_per_pixel) {
        switch (pixel_format) {
        case kRetroPixelFormatXRGB8888:
            image_format = VK_FORMAT_B8G8R8A8_UNORM;
            bytes_per_pixel = 4;
            return true;
        case kRetroPixelFormatRGB565:
            image_format = VK_FORMAT_R5G6B5_UNORM_PACK16;
            bytes_per_pixel = 2;
            return true;
        case kRetroPixelFormat0RGB1555:
            image_format = VK_FORMAT_A1R5G5B5_UNORM_PACK16;
            bytes_per_pixel = 2;
            return true;
        default:
            image_format = VK_FORMAT_UNDEFINED;
            bytes_per_pixel = 0;
            return false;
        }
    }

    bool can_blit_from(VkFormat format) const {
        if (!get_format_properties || !physical_device || format == VK_FORMAT_UNDEFINED) return false;
        VkFormatProperties properties{};
        get_format_properties(physical_device, format, &properties);
        return (properties.optimalTilingFeatures & VK_FORMAT_FEATURE_BLIT_SRC_BIT) != 0;
    }

    bool create_software_command_resources(std::string& error) {
        if (software_command_pool) return true;
        VkCommandPoolCreateInfo pool_info{};
        pool_info.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
        pool_info.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
        pool_info.queueFamilyIndex = queue_family_index;
        if (create_command_pool(device, &pool_info, nullptr, &software_command_pool) != VK_SUCCESS || !software_command_pool) {
            error = "Vulkan runtime could not create a software-frame upload command pool.";
            return false;
        }
        std::array<VkCommandBuffer, kFrameRingSize> commands{};
        VkCommandBufferAllocateInfo command_info{};
        command_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
        command_info.commandPool = software_command_pool;
        command_info.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        command_info.commandBufferCount = kFrameRingSize;
        if (allocate_command_buffers(device, &command_info, commands.data()) != VK_SUCCESS) {
            error = "Vulkan runtime could not allocate software-frame upload command buffers.";
            destroy_software_resources();
            return false;
        }
        VkSemaphoreCreateInfo semaphore_info{};
        semaphore_info.sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO;
        for (uint32_t index = 0; index < kFrameRingSize; ++index) {
            software_slots[index].upload_command = commands[index];
            if (create_semaphore(device, &semaphore_info, nullptr, &software_slots[index].upload_finished) != VK_SUCCESS ||
                !software_slots[index].upload_finished) {
                error = "Vulkan runtime could not create software-frame upload synchronization.";
                destroy_software_resources();
                return false;
            }
        }
        return true;
    }

    bool create_software_resources(SoftwareFrameSlot& slot, uint32_t width, uint32_t height,
                                   int pixel_format, std::string& error) {
        if (!width || !height || !device || !create_buffer || !create_image) {
            error = "Invalid software-frame Vulkan image dimensions.";
            return false;
        }
        VkFormat native_format = VK_FORMAT_UNDEFINED;
        std::size_t native_bytes_per_pixel = 0;
        if (!native_software_format(pixel_format, native_format, native_bytes_per_pixel)) {
            error = "The software core requested an unsupported pixel format.";
            return false;
        }
        const bool upload_native_format = can_blit_from(native_format);
        const VkFormat image_format = upload_native_format ? native_format : VK_FORMAT_B8G8R8A8_UNORM;
        const std::size_t bytes_per_pixel = upload_native_format ? native_bytes_per_pixel : 4u;
        const VkDeviceSize pixel_count = static_cast<VkDeviceSize>(width) * static_cast<VkDeviceSize>(height);
        if (pixel_count > std::numeric_limits<VkDeviceSize>::max() / bytes_per_pixel) {
            error = "Software-frame dimensions are too large for Vulkan presentation.";
            return false;
        }
        const VkDeviceSize staging_size = pixel_count * bytes_per_pixel;
        if (slot.image && slot.width == width && slot.height == height && slot.image_format == image_format &&
            slot.staging_capacity >= staging_size && slot.staging_mapping && slot.upload_command && slot.upload_finished) {
            return true;
        }
        // A core changing its geometry or pixel format is a reconfiguration,
        // not a per-frame event. Drain only here before replacing a slot: a
        // null-frame duplicate may still reference this source image from the
        // other presentation context.
        if (slot.image && device_wait_idle) device_wait_idle(device);
        destroy_software_slot_resources(slot);

        VkBufferCreateInfo buffer_info{};
        buffer_info.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
        buffer_info.size = staging_size;
        buffer_info.usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT;
        buffer_info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        if (create_buffer(device, &buffer_info, nullptr, &slot.staging_buffer) != VK_SUCCESS || !slot.staging_buffer) {
            error = "Vulkan runtime could not create a software-frame staging buffer.";
            destroy_software_slot_resources(slot);
            return false;
        }
        VkMemoryRequirements staging_requirements{};
        get_buffer_memory_requirements(device, slot.staging_buffer, &staging_requirements);
        uint32_t staging_memory_type = find_memory_type(
            staging_requirements.memoryTypeBits,
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
        VkPhysicalDeviceProperties properties{};
        const auto get_properties = load_instance_function<PFN_vkGetPhysicalDeviceProperties>(get_instance_proc_addr, instance, "vkGetPhysicalDeviceProperties");
        if (!get_properties) { error="software-memory: physical device properties unavailable"; return false; }
        get_properties(physical_device, &properties);
        slot.flush_atom = std::max<VkDeviceSize>(1, properties.limits.nonCoherentAtomSize);
        slot.coherent = staging_memory_type != std::numeric_limits<uint32_t>::max();
        if (!slot.coherent) staging_memory_type = find_memory_type(staging_requirements.memoryTypeBits, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT);
        if (staging_memory_type == std::numeric_limits<uint32_t>::max()) {
            error = "software-memory: no host-visible upload memory";
            destroy_software_slot_resources(slot);
            return false;
        }
        VkMemoryAllocateInfo staging_allocation{};
        staging_allocation.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
        staging_allocation.allocationSize = staging_requirements.size;
        staging_allocation.memoryTypeIndex = staging_memory_type;
        if (allocate_memory(device, &staging_allocation, nullptr, &slot.staging_memory) != VK_SUCCESS ||
            bind_buffer_memory(device, slot.staging_buffer, slot.staging_memory, 0) != VK_SUCCESS ||
            map_memory(device, slot.staging_memory, 0, staging_requirements.size, 0, &slot.staging_mapping) != VK_SUCCESS ||
            !slot.staging_mapping) {
            error = "Vulkan runtime could not map a software-frame staging buffer.";
            destroy_software_slot_resources(slot);
            return false;
        }

        VkImageCreateInfo image_info{};
        image_info.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
        image_info.imageType = VK_IMAGE_TYPE_2D;
        image_info.format = image_format;
        image_info.extent = {width, height, 1};
        image_info.mipLevels = 1;
        image_info.arrayLayers = 1;
        image_info.samples = VK_SAMPLE_COUNT_1_BIT;
        image_info.tiling = VK_IMAGE_TILING_OPTIMAL;
        image_info.usage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT;
        image_info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        image_info.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        if (create_image(device, &image_info, nullptr, &slot.image) != VK_SUCCESS || !slot.image) {
            error = "Vulkan runtime could not create a software-frame Vulkan image.";
            destroy_software_slot_resources(slot);
            return false;
        }
        VkMemoryRequirements image_requirements{};
        get_image_memory_requirements(device, slot.image, &image_requirements);
        uint32_t image_memory_type = find_memory_type(image_requirements.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
        if (image_memory_type == std::numeric_limits<uint32_t>::max()) {
            image_memory_type = find_memory_type(image_requirements.memoryTypeBits, 0);
        }
        if (image_memory_type == std::numeric_limits<uint32_t>::max()) {
            error = "This native GPU does not expose memory for software-frame Vulkan images.";
            destroy_software_slot_resources(slot);
            return false;
        }
        VkMemoryAllocateInfo image_allocation{};
        image_allocation.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
        image_allocation.allocationSize = image_requirements.size;
        image_allocation.memoryTypeIndex = image_memory_type;
        if (allocate_memory(device, &image_allocation, nullptr, &slot.image_memory) != VK_SUCCESS ||
            bind_image_memory(device, slot.image, slot.image_memory, 0) != VK_SUCCESS) {
            error = "Vulkan runtime could not allocate a software-frame Vulkan image.";
            destroy_software_slot_resources(slot);
            return false;
        }
        slot.staging_capacity = staging_size;
        slot.allocation_size = staging_requirements.size;
        slot.image_format = image_format;
        slot.width = width;
        slot.height = height;
        slot.bytes_per_pixel = bytes_per_pixel;
        slot.pixel_format = pixel_format;
        slot.image_initialized = false;
        slot.direct_write_active = false;
        return true;
    }

    bool create_swapchain_resources(std::string& error) {
        VkSurfaceCapabilitiesKHR capabilities{};
        if (get_surface_capabilities(physical_device, surface, &capabilities) != VK_SUCCESS) {
            error = "Vulkan runtime could not inspect the native window surface.";
            return false;
        }
        if (!(capabilities.supportedUsageFlags & VK_IMAGE_USAGE_TRANSFER_DST_BIT)) {
            error = "This native surface cannot accept Vulkan frame transfers.";
            return false;
        }
        uint32_t format_count = 0;
        get_surface_formats(physical_device, surface, &format_count, nullptr);
        if (!format_count) {
            error = "Vulkan runtime did not provide a swapchain color format.";
            return false;
        }
        std::vector<VkSurfaceFormatKHR> formats(format_count);
        get_surface_formats(physical_device, surface, &format_count, formats.data());
        // The core presents display-referred UNORM frames, so the swapchain
        // must stay in the standard sRGB-nonlinear color space and use a UNORM
        // color format. An _SRGB surface makes the presentation blit apply a
        // second linear-to-sRGB encode, and a wide-gamut/HDR surface color
        // space makes Android's compositor reinterpret the channels; both wash
        // out or desaturate the 3DS framebuffer while the UI stays correct.
        // MoltenVK only advertises B8G8R8A8_UNORM with the standard space, so
        // macOS never reproduced this. Prefer R8G8B8A8_UNORM because it matches
        // the core's VK_FORMAT_R8G8B8A8_UNORM output, letting Android skip the
        // cross-format blit entirely. "VK_FORMAT_UNDEFINED" means the driver
        // lets us choose.
        const auto supports_blit_dst = [this](VkFormat format) {
            VkFormatProperties properties{};
            get_format_properties(physical_device, format, &properties);
            return (properties.optimalTilingFeatures & VK_FORMAT_FEATURE_BLIT_DST_BIT) != 0;
        };
        // A non-standard surface color space (for example the wide-gamut
        // DISPLAY_P3 that some Android compositors advertise first) makes the
        // compositor reinterpret the channels of the display-referred UNORM
        // frame, which drops/garbles color information while the app UI stays
        // correct. Only ever select a format that keeps the standard
        // sRGB-nonlinear space; the previous fallback to formats.front() could
        // silently pick such a surface. MoltenVK and desktop drivers always
        // advertise the standard space, which is why this only reproduced on
        // Android Vulkan.
        VkSurfaceFormatKHR selected = formats.front();
        bool have_selection = false;
        if (formats.size() == 1 && selected.format == VK_FORMAT_UNDEFINED) {
            selected.format = VK_FORMAT_R8G8B8A8_UNORM;
            selected.colorSpace = VK_COLOR_SPACE_SRGB_NONLINEAR_KHR;
            have_selection = true;
        } else {
            const VkFormat preferred_formats[] = {
                VK_FORMAT_R8G8B8A8_UNORM, VK_FORMAT_B8G8R8A8_UNORM,
                VK_FORMAT_B8G8R8A8_SRGB,  VK_FORMAT_R8G8B8A8_SRGB,
            };
            for (const VkFormat preferred : preferred_formats) {
                const auto candidate = std::find_if(formats.begin(), formats.end(), [preferred](const VkSurfaceFormatKHR& item) {
                    return item.format == preferred && item.colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR;
                });
                if (candidate != formats.end() && supports_blit_dst(candidate->format)) {
                    selected = *candidate;
                    have_selection = true;
                    break;
                }
            }
        }
        if (!have_selection) {
            // The driver advertised no preferred format with the standard
            // space; scan for any blit-capable format that still presents in
            // the standard space before accepting the (possibly wide-gamut)
            // first entry. This keeps channel interpretation stable instead of
            // letting the compositor reinterpret a P3/HDR surface.
            const auto candidate = std::find_if(formats.begin(), formats.end(), [&supports_blit_dst](const VkSurfaceFormatKHR& item) {
                return item.colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR && supports_blit_dst(item.format);
            });
            if (candidate != formats.end()) selected = *candidate;
        }
        VkFormatProperties selected_properties{};
        get_format_properties(physical_device, selected.format, &selected_properties);
        if (!(selected_properties.optimalTilingFeatures & VK_FORMAT_FEATURE_BLIT_DST_BIT)) {
            error = "This native surface does not provide a Vulkan blit-compatible color format.";
            return false;
        }
        uint32_t present_mode_count = 0;
        get_surface_present_modes(physical_device, surface, &present_mode_count, nullptr);
        std::vector<VkPresentModeKHR> present_modes(present_mode_count);
        if (present_mode_count) get_surface_present_modes(physical_device, surface, &present_mode_count, present_modes.data());
        VkPresentModeKHR present_mode = VK_PRESENT_MODE_FIFO_KHR;

        const VkExtent2D desired = clamp_extent(capabilities, drawable_size());
        uint32_t image_count = std::max(capabilities.minImageCount + 1, 2u);
        if (capabilities.maxImageCount && image_count > capabilities.maxImageCount) image_count = capabilities.maxImageCount;
        VkSwapchainCreateInfoKHR info{};
        info.sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR;
        info.surface = surface;
        info.minImageCount = image_count;
        info.imageFormat = selected.format;
        info.imageColorSpace = selected.colorSpace;
        info.imageExtent = desired;
        info.imageArrayLayers = 1;
        info.imageUsage = VK_IMAGE_USAGE_TRANSFER_DST_BIT;
        const uint32_t queue_families[] = {queue_family_index, presentation_queue_family_index};
        if (queue_family_index != presentation_queue_family_index) {
            info.imageSharingMode = VK_SHARING_MODE_CONCURRENT;
            info.queueFamilyIndexCount = 2;
            info.pQueueFamilyIndices = queue_families;
        } else {
            info.imageSharingMode = VK_SHARING_MODE_EXCLUSIVE;
        }
        // This software blit path renders in window coordinates and does not
        // pre-rotate its pixels. Let the compositor apply the surface rotation.
        // Claiming currentTransform here rotates/stretches Android landscape.
        if (!(capabilities.supportedTransforms & VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR)) {
            error = "Native Vulkan surface requires unsupported pre-rotation.";
            return false;
        }
        info.preTransform = VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR;
        info.compositeAlpha = composite_alpha(capabilities);
        info.presentMode = present_mode;
        info.clipped = VK_TRUE;
        if (create_swapchain(device, &info, nullptr, &swapchain) != VK_SUCCESS || !swapchain) {
            error = "Vulkan runtime could not create a native Vulkan swapchain.";
            return false;
        }
        uint32_t count = 0;
        if (get_swapchain_images(device, swapchain, &count, nullptr) != VK_SUCCESS || !count) {
            error = "Vulkan runtime did not return swapchain images.";
            return false;
        }
        swapchain_images.resize(count);
        if (get_swapchain_images(device, swapchain, &count, swapchain_images.data()) != VK_SUCCESS) {
            error = "Vulkan runtime could not read swapchain images.";
            return false;
        }
        VkCommandPoolCreateInfo pool_info{};
        pool_info.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
        pool_info.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
        pool_info.queueFamilyIndex = queue_family_index;
        if (create_command_pool(device, &pool_info, nullptr, &command_pool) != VK_SUCCESS) {
            error = "Vulkan runtime could not create a presentation command pool.";
            return false;
        }
        command_buffers.resize(count);
        VkCommandBufferAllocateInfo buffers{};
        buffers.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
        buffers.commandPool = command_pool;
        buffers.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        buffers.commandBufferCount = count;
        if (allocate_command_buffers(device, &buffers, command_buffers.data()) != VK_SUCCESS) {
            error = "Vulkan runtime could not allocate presentation command buffers.";
            return false;
        }
        VkSemaphoreCreateInfo semaphore_info{};
        semaphore_info.sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO;
        VkFenceCreateInfo fence_info{};
        fence_info.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
        fence_info.flags = VK_FENCE_CREATE_SIGNALED_BIT;
        for (auto& frame : presentation_frames) {
            if (create_semaphore(device, &semaphore_info, nullptr, &frame.image_available) != VK_SUCCESS ||
                create_semaphore(device, &semaphore_info, nullptr, &frame.render_finished) != VK_SUCCESS ||
                create_fence(device, &fence_info, nullptr, &frame.in_flight) != VK_SUCCESS) {
                error = "Vulkan runtime could not create presentation synchronization primitives.";
                return false;
            }
        }
        extent = desired;
        swapchain_format = selected.format;
        swapchain_color_space = selected.colorSpace;
        image_initialized.assign(count, false);
        image_in_flight.assign(count, VK_NULL_HANDLE);
        next_presentation_frame = 0;
        active_presentation_frame = kNoFrameSlot;
        last_submitted_fence = VK_NULL_HANDLE;
        return true;
    }

    bool recreate_swapchain_if_needed(std::string& error) {
        if (!swapchain) return create_swapchain_resources(error);
        const VkExtent2D size = drawable_size();
        if (static_cast<uint32_t>(size.width) == extent.width && static_cast<uint32_t>(size.height) == extent.height) return true;
        destroy_swapchain_resources(true);
        return create_swapchain_resources(error);
    }

    bool initialize(NativeWindowSurface* native_surface, const char* runtime_path,
                    const RetroHwRenderCallback& hardware_callbacks,
                    const void* negotiation_interface, std::string& error) {
        shutdown();
        current_sync_index.store(0, std::memory_order_relaxed);
        frame_count.store(0, std::memory_order_relaxed);
        metrics = {};
        window_surface = native_surface;
        if (!window_surface) { error = "native-surface: unavailable"; return false; }
        if (!load_runtime(runtime_path, error) || !create_vulkan_instance(error) || !create_surface(error) ||
            !choose_physical_device(error) || !create_core_device(negotiation_interface, error) ||
            !load_device_functions(error) || !create_core_drain_resources(error) || !create_swapchain_resources(error)) {
            shutdown();
            return false;
        }
        interface = {
            kRetroHwRenderInterfaceVulkan,
            kRetroVulkanInterfaceVersion,
            owner,
            instance,
            physical_device,
            device,
            get_device_proc_addr,
            get_instance_proc_addr,
            queue,
            queue_family_index,
            [](void* handle, const RetroVulkanImage* image, uint32_t semaphore_count,
               const VkSemaphore* semaphores, uint32_t source_queue_family) {
                static_cast<PortableVulkanBackend*>(handle)->receive_image(image, semaphore_count, semaphores, source_queue_family);
            },
            [](void* handle) { return static_cast<PortableVulkanBackend*>(handle)->sync_index(); },
            [](void* handle) { return static_cast<PortableVulkanBackend*>(handle)->sync_index_mask(); },
            nullptr,
            [](void* handle) { static_cast<PortableVulkanBackend*>(handle)->wait_sync_index(); },
            [](void* handle) { static_cast<PortableVulkanBackend*>(handle)->lock_queue(); },
            [](void* handle) { static_cast<PortableVulkanBackend*>(handle)->unlock_queue(); },
            nullptr,
        };
        active = hardware_callbacks.context_type == kRetroHwContextVulkan;
        if (!active) {
            error = "Azahar requested a non-Vulkan renderer.";
            shutdown();
            return false;
        }
        mode = Mode::CoreVulkan;
        return true;
    }

    bool initialize_software(NativeWindowSurface* native_surface, const char* runtime_path, std::string& error) {
        shutdown();
        current_sync_index.store(0, std::memory_order_relaxed);
        frame_count.store(0, std::memory_order_relaxed);
        metrics = {};
        window_surface = native_surface;
        if (!window_surface) { error = "native-surface: unavailable"; return false; }
        if (!load_runtime(runtime_path, error) || !create_vulkan_instance(error) || !create_surface(error) ||
            !choose_physical_device(error) || !create_software_device(error) ||
            !load_device_functions(error) || !create_swapchain_resources(error) ||
            !create_software_command_resources(error)) {
            shutdown();
            return false;
        }
        active = true;
        mode = Mode::SoftwareUpload;
        return true;
    }

    void shutdown() {
        std::scoped_lock lock{mutex};
        if (mode == Mode::CoreVulkan) discard_pending_core_frame();
        destroy_swapchain_resources(true);
        destroy_software_resources();
        destroy_core_drain_resources();
        if (destroy_core_device) destroy_core_device();
        destroy_core_device = nullptr;
        if (device && destroy_device) destroy_device(device, nullptr);
        device = VK_NULL_HANDLE;
        queue = VK_NULL_HANDLE;
        presentation_queue = VK_NULL_HANDLE;
        physical_device = VK_NULL_HANDLE;
        queue_family_index = 0;
        presentation_queue_family_index = 0;
        if (surface && destroy_surface) destroy_surface(instance, surface, nullptr);
        surface = VK_NULL_HANDLE;
        if (instance && destroy_instance) destroy_instance(instance, nullptr);
        instance = VK_NULL_HANDLE;
        if (runtime) {
#if defined(_WIN32)
            FreeLibrary(static_cast<HMODULE>(runtime));
#else
            dlclose(runtime);
#endif
        }
        runtime = nullptr;
        get_instance_proc_addr = nullptr;
        get_device_proc_addr = nullptr;
        interface = {};
        has_pending_image = false;
        pending_semaphores.fill(VK_NULL_HANDLE);
        pending_semaphore_count = 0;
        pending_source_queue = VK_QUEUE_FAMILY_IGNORED;
        mode = Mode::None;
        active = false;
        window_surface = nullptr;
    }

    void receive_image(const RetroVulkanImage* image, uint32_t semaphore_count,
                       const VkSemaphore* semaphores, uint32_t source_queue_family) {
        if (!image) return;
        std::scoped_lock lock{mutex};
        if (!active || mode != Mode::CoreVulkan) return;
        // The supported core currently supplies one semaphore. Keep a small
        // fixed-size boundary here so the native hot path never allocates
        // while accepting a frame from a GPU-heavy core.
        if (semaphore_count > kMaxSourceWaitSemaphores) return;
        // A previous failed presentation may still own a one-shot semaphore.
        // Never overwrite it: the core is entitled to reuse that semaphore as
        // soon as this callback returns. The recovery is deliberately absent
        // from the successful frame path.
        if (pending_semaphore_count && !discard_pending_core_frame()) {
            ++metrics.dropped_frames;
            active = false;
            return;
        }
        pending_image = *image;
        pending_semaphore_count = semaphores ? semaphore_count : 0;
        for (uint32_t index = 0; index < pending_semaphore_count; ++index) pending_semaphores[index] = semaphores[index];
        pending_source_queue = source_queue_family;
        has_pending_image = true;
    }

    bool prepare_presentation_frame(uint32_t& frame_index) {
        if (active_presentation_frame != kNoFrameSlot) {
            frame_index = active_presentation_frame;
            return true;
        }
        frame_index = next_presentation_frame;
        auto& frame = presentation_frames[frame_index];
        if (!frame.in_flight || !frame.image_available || !frame.render_finished) return false;
        if (frame.submitted &&
            wait_for_fences(device, 1, &frame.in_flight, VK_TRUE, UINT64_MAX) != VK_SUCCESS) {
            return false;
        }
        frame.submitted = false;
        active_presentation_frame = frame_index;
        return true;
    }

    void finish_presentation_frame(uint32_t frame_index, bool submitted) {
        if (active_presentation_frame != frame_index) return;
        if (submitted) {
            auto& frame = presentation_frames[frame_index];
            frame.submitted = true;
            last_submitted_fence = frame.in_flight;
            next_presentation_frame = (frame_index + 1u) % kFrameRingSize;
        }
        active_presentation_frame = kNoFrameSlot;
    }

    void present(unsigned width, unsigned height) {
        std::scoped_lock lock{mutex};
        if (!active || mode != Mode::CoreVulkan || !has_pending_image) return;
        VkImageSubresourceRange source_range = pending_image.create_info.subresourceRange;
        const bool submitted = present_image(pending_image.create_info.image, pending_image.image_layout,
                                             source_range, pending_image.create_info.format,
                                             pending_source_queue, pending_semaphores.data(),
                                             pending_semaphore_count, width, height);
        // A libretro semaphore can only be waited once. Keep the last image so
        // a null video callback can duplicate it, but discard waits after a
        // successful submission. If no submit happened, drain the original
        // wait before the core can hand us a replacement image.
        if (submitted) {
            pending_semaphores.fill(VK_NULL_HANDLE);
            pending_semaphore_count = 0;
        } else if (pending_semaphore_count && !discard_pending_core_frame()) {
            active = false;
        }
    }

    bool discard_pending_core_frame() {
        if (!has_pending_image) return true;
        const auto clear_pending = [this] {
            pending_image = {};
            pending_semaphores.fill(VK_NULL_HANDLE);
            pending_semaphore_count = 0;
            pending_source_queue = VK_QUEUE_FAMILY_IGNORED;
            has_pending_image = false;
        };
        if (!pending_semaphore_count) {
            clear_pending();
            return true;
        }
        if (!pending_image.create_info.image || !core_drain_command || !core_drain_fence ||
            !wait_for_fences || !reset_fences || !reset_command_buffer || !begin_command_buffer ||
            !end_command_buffer || !queue_submit) {
            return false;
        }
        if (wait_for_fences(device, 1, &core_drain_fence, VK_TRUE, UINT64_MAX) != VK_SUCCESS ||
            reset_fences(device, 1, &core_drain_fence) != VK_SUCCESS ||
            reset_command_buffer(core_drain_command, 0) != VK_SUCCESS) {
            return false;
        }
        VkCommandBufferBeginInfo begin{};
        begin.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        if (begin_command_buffer(core_drain_command, &begin) != VK_SUCCESS) return false;
        VkImageSubresourceRange source_range = pending_image.create_info.subresourceRange;
        if (!source_range.aspectMask) source_range.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        if (!source_range.levelCount) source_range.levelCount = 1;
        if (!source_range.layerCount) source_range.layerCount = 1;
        const bool transfer_source_ownership = pending_source_queue != VK_QUEUE_FAMILY_IGNORED &&
                                               pending_source_queue != queue_family_index;
        VkImageMemoryBarrier acquire_barrier{};
        acquire_barrier.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
        acquire_barrier.srcAccessMask = VK_ACCESS_MEMORY_WRITE_BIT;
        acquire_barrier.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
        acquire_barrier.oldLayout = pending_image.image_layout;
        acquire_barrier.newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
        acquire_barrier.srcQueueFamilyIndex = transfer_source_ownership ? pending_source_queue : VK_QUEUE_FAMILY_IGNORED;
        acquire_barrier.dstQueueFamilyIndex = transfer_source_ownership ? queue_family_index : VK_QUEUE_FAMILY_IGNORED;
        acquire_barrier.image = pending_image.create_info.image;
        acquire_barrier.subresourceRange = source_range;
        cmd_pipeline_barrier(core_drain_command, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
                             0, 0, nullptr, 0, nullptr, 1, &acquire_barrier);
        VkImageMemoryBarrier release_barrier{};
        release_barrier.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
        release_barrier.srcAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
        release_barrier.dstAccessMask = VK_ACCESS_MEMORY_READ_BIT;
        release_barrier.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
        release_barrier.newLayout = pending_image.image_layout;
        release_barrier.srcQueueFamilyIndex = transfer_source_ownership ? queue_family_index : VK_QUEUE_FAMILY_IGNORED;
        release_barrier.dstQueueFamilyIndex = transfer_source_ownership ? pending_source_queue : VK_QUEUE_FAMILY_IGNORED;
        release_barrier.image = pending_image.create_info.image;
        release_barrier.subresourceRange = source_range;
        cmd_pipeline_barrier(core_drain_command, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT,
                             0, 0, nullptr, 0, nullptr, 1, &release_barrier);
        if (end_command_buffer(core_drain_command) != VK_SUCCESS) return false;
        std::array<VkSemaphore, kMaxSourceWaitSemaphores> wait_semaphores{};
        std::array<VkPipelineStageFlags, kMaxSourceWaitSemaphores> wait_stages{};
        uint32_t wait_count = 0;
        for (uint32_t index = 0; index < pending_semaphore_count; ++index) {
            if (pending_semaphores[index]) {
                wait_semaphores[wait_count] = pending_semaphores[index];
                wait_stages[wait_count++] = VK_PIPELINE_STAGE_TRANSFER_BIT;
            }
        }
        if (!wait_count) {
            clear_pending();
            return true;
        }
        VkSubmitInfo submit{};
        submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
        submit.waitSemaphoreCount = wait_count;
        submit.pWaitSemaphores = wait_semaphores.data();
        submit.pWaitDstStageMask = wait_stages.data();
        submit.commandBufferCount = 1;
        submit.pCommandBuffers = &core_drain_command;
        if (queue_submit(queue, 1, &submit, core_drain_fence) != VK_SUCCESS ||
            wait_for_fences(device, 1, &core_drain_fence, VK_TRUE, UINT64_MAX) != VK_SUCCESS) {
            return false;
        }
        last_submitted_fence = core_drain_fence;
        clear_pending();
        return true;
    }

    static uint8_t expand_5_bit(uint16_t value) {
        return static_cast<uint8_t>((value << 3) | (value >> 2));
    }

    bool upload_software_frame(SoftwareFrameSlot& slot, const void* framebuffer,
                               unsigned width, unsigned height, std::size_t pitch, int pixel_format) {
        ScopedTiming timing{metrics.upload};
        if (!framebuffer || !width || !height) return false;
        std::string ignored_error;
        if (!create_software_resources(slot, width, height, pixel_format, ignored_error)) return false;
        if (!slot.staging_mapping || !slot.upload_finished || !slot.upload_command) return false;
        const std::size_t bytes_per_pixel = pixel_format == kRetroPixelFormatXRGB8888 ? 4u : 2u;
        if (pixel_format != kRetroPixelFormat0RGB1555 && pixel_format != kRetroPixelFormatXRGB8888 &&
            pixel_format != kRetroPixelFormatRGB565) return false;
        if (pitch < static_cast<std::size_t>(width) * bytes_per_pixel) return false;
        VkFormat native_format = VK_FORMAT_UNDEFINED;
        std::size_t native_bytes_per_pixel = 0;
        if (!native_software_format(pixel_format, native_format, native_bytes_per_pixel)) return false;
        const bool native_upload = slot.image_format == native_format && slot.bytes_per_pixel == native_bytes_per_pixel;
        const bool direct_write = slot.direct_write_active && framebuffer == slot.staging_mapping &&
                                  native_upload && pitch == static_cast<std::size_t>(width) * bytes_per_pixel;
        if (!direct_write) {
            const auto* source = static_cast<const uint8_t*>(framebuffer);
            auto* destination = static_cast<uint8_t*>(slot.staging_mapping);
            if (native_upload) {
                const std::size_t row_bytes = static_cast<std::size_t>(width) * bytes_per_pixel;
                for (unsigned y = 0; y < height; ++y) {
                    std::memcpy(destination + static_cast<std::size_t>(y) * row_bytes,
                                source + static_cast<std::size_t>(y) * pitch, row_bytes);
                }
            } else {
                for (unsigned y = 0; y < height; ++y) {
                    const auto* source_row = source + static_cast<std::size_t>(y) * pitch;
                    auto* destination_row = destination + static_cast<std::size_t>(y) * width * 4u;
                    for (unsigned x = 0; x < width; ++x) {
                        auto* output = destination_row + static_cast<std::size_t>(x) * 4u;
                        if (pixel_format == kRetroPixelFormatXRGB8888) {
                            uint32_t pixel{};
                            std::memcpy(&pixel, source_row + static_cast<std::size_t>(x) * 4u, sizeof(pixel));
                            output[0] = static_cast<uint8_t>(pixel & 0xffu);
                            output[1] = static_cast<uint8_t>((pixel >> 8) & 0xffu);
                            output[2] = static_cast<uint8_t>((pixel >> 16) & 0xffu);
                        } else {
                            uint16_t pixel{};
                            std::memcpy(&pixel, source_row + static_cast<std::size_t>(x) * 2u, sizeof(pixel));
                            output[0] = expand_5_bit(pixel & 0x1fu);
                            output[1] = pixel_format == kRetroPixelFormatRGB565
                                ? static_cast<uint8_t>(((pixel >> 5) & 0x3fu) * 255u / 63u)
                                : expand_5_bit((pixel >> 5) & 0x1fu);
                            output[2] = expand_5_bit((pixel >> (pixel_format == kRetroPixelFormatRGB565 ? 11 : 10)) & 0x1fu);
                        }
                        output[3] = 0xffu;
                    }
                }
            }
        }
        slot.direct_write_active = false;
        if (!slot.coherent) {
            const VkDeviceSize atom = slot.flush_atom;
            const VkDeviceSize written = VkDeviceSize(width) * height * slot.bytes_per_pixel;
            VkMappedMemoryRange range{};
            range.sType = VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE;
            range.memory = slot.staging_memory;
            range.size = std::min(slot.allocation_size, ((written + atom - 1) / atom) * atom);
            if (flush_mapped_memory_ranges(device, 1, &range) != VK_SUCCESS) return false;
        }
        if (reset_command_buffer(slot.upload_command, 0) != VK_SUCCESS) return false;
        VkCommandBufferBeginInfo begin{};
        begin.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        if (begin_command_buffer(slot.upload_command, &begin) != VK_SUCCESS) return false;
        VkImageSubresourceRange image_range{};
        image_range.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        image_range.levelCount = 1;
        image_range.layerCount = 1;
        VkImageMemoryBarrier begin_barrier{};
        begin_barrier.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
        begin_barrier.srcAccessMask = slot.image_initialized ? VK_ACCESS_MEMORY_READ_BIT : 0;
        begin_barrier.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
        begin_barrier.oldLayout = slot.image_initialized ? VK_IMAGE_LAYOUT_GENERAL : VK_IMAGE_LAYOUT_UNDEFINED;
        begin_barrier.newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
        begin_barrier.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        begin_barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        begin_barrier.image = slot.image;
        begin_barrier.subresourceRange = image_range;
        cmd_pipeline_barrier(slot.upload_command, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
                             0, 0, nullptr, 0, nullptr, 1, &begin_barrier);
        VkBufferImageCopy copy{};
        copy.imageSubresource.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        copy.imageSubresource.layerCount = 1;
        copy.imageExtent = {width, height, 1};
        cmd_copy_buffer_to_image(slot.upload_command, slot.staging_buffer, slot.image,
                                 VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &copy);
        VkImageMemoryBarrier finish_barrier{};
        finish_barrier.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
        finish_barrier.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
        finish_barrier.dstAccessMask = VK_ACCESS_MEMORY_READ_BIT;
        finish_barrier.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
        finish_barrier.newLayout = VK_IMAGE_LAYOUT_GENERAL;
        finish_barrier.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        finish_barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        finish_barrier.image = slot.image;
        finish_barrier.subresourceRange = image_range;
        cmd_pipeline_barrier(slot.upload_command, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT,
                             0, 0, nullptr, 0, nullptr, 1, &finish_barrier);
        if (end_command_buffer(slot.upload_command) != VK_SUCCESS) return false;
        VkSubmitInfo submit{};
        submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
        submit.commandBufferCount = 1;
        submit.pCommandBuffers = &slot.upload_command;
        submit.signalSemaphoreCount = 1;
        submit.pSignalSemaphores = &slot.upload_finished;
        if (queue_submit(queue, 1, &submit, VK_NULL_HANDLE) != VK_SUCCESS) return false;
        slot.image_initialized = true;
        ++metrics.software_uploads;
        if (direct_write) ++metrics.direct_software_uploads;
        else if (native_upload) ++metrics.copied_software_uploads;
        else ++metrics.converted_software_uploads;
        return true;
    }

    void recover_unconsumed_software_upload(SoftwareFrameSlot& slot) {
        // A binary semaphore signalled by the upload submit must be consumed
        // before it can be signalled again. The normal path consumes it in
        // present_image's queue submit. This deliberately slow recovery runs
        // only after a failed presentation before that submit (for example an
        // out-of-date drawable), never in the successful per-frame hot path.
        if (!slot.upload_finished || !device_wait_idle || !destroy_semaphore || !create_semaphore) return;
        if (device_wait_idle(device) != VK_SUCCESS) return;
        destroy_semaphore(device, slot.upload_finished, nullptr);
        slot.upload_finished = VK_NULL_HANDLE;
        VkSemaphoreCreateInfo semaphore_info{};
        semaphore_info.sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO;
        if (create_semaphore(device, &semaphore_info, nullptr, &slot.upload_finished) != VK_SUCCESS) {
            slot.upload_finished = VK_NULL_HANDLE;
        }
    }

    bool acquire_software_framebuffer(unsigned width, unsigned height, int pixel_format,
                                      void*& data, std::size_t& pitch) {
        data = nullptr;
        pitch = 0;
        std::scoped_lock lock{mutex};
        if (!active || mode != Mode::SoftwareUpload || !width || !height) return false;
        std::string ignored_error;
        if (!recreate_swapchain_if_needed(ignored_error)) return false;
        uint32_t frame_index = kNoFrameSlot;
        if (!prepare_presentation_frame(frame_index)) return false;
        auto& slot = software_slots[frame_index];
        if (!create_software_resources(slot, width, height, pixel_format, ignored_error)) {
            finish_presentation_frame(frame_index, false);
            return false;
        }
        VkFormat native_format = VK_FORMAT_UNDEFINED;
        std::size_t bytes_per_pixel = 0;
        if (!native_software_format(pixel_format, native_format, bytes_per_pixel) ||
            slot.image_format != native_format || slot.bytes_per_pixel != bytes_per_pixel ||
            !slot.staging_mapping) {
            // Do not hand a core a converted BGRA buffer: its declared pixel
            // format must continue to describe the memory it writes.
            finish_presentation_frame(frame_index, false);
            return false;
        }
        slot.direct_write_active = true;
        data = slot.staging_mapping;
        pitch = static_cast<std::size_t>(width) * bytes_per_pixel;
        return true;
    }

    void present_software(const void* framebuffer, unsigned width, unsigned height,
                          std::size_t pitch, int pixel_format) {
        std::scoped_lock lock{mutex};
        if (!active || mode != Mode::SoftwareUpload || !width || !height) return;
        std::string ignored_error;
        if (!recreate_swapchain_if_needed(ignored_error)) return;
        uint32_t frame_index = kNoFrameSlot;
        if (!prepare_presentation_frame(frame_index)) return;
        auto& slot = software_slots[frame_index];
        bool uploaded = false;
        if (framebuffer) {
            uploaded = upload_software_frame(slot, framebuffer, width, height, pitch, pixel_format);
            if (!uploaded) {
                ++metrics.dropped_frames;
                finish_presentation_frame(frame_index, false);
                return;
            }
            last_software_slot = frame_index;
        } else if (last_software_slot == kNoFrameSlot ||
                   !software_slots[last_software_slot].image_initialized ||
                   software_slots[last_software_slot].width != width ||
                   software_slots[last_software_slot].height != height) {
            ++metrics.dropped_frames;
            finish_presentation_frame(frame_index, false);
            return;
        }
        const auto& source = software_slots[framebuffer ? frame_index : last_software_slot];
        VkImageSubresourceRange source_range{};
        source_range.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        source_range.levelCount = 1;
        source_range.layerCount = 1;
        const VkSemaphore* upload_wait = uploaded ? &slot.upload_finished : nullptr;
        const bool submitted = present_image(source.image, VK_IMAGE_LAYOUT_GENERAL, source_range, source.image_format,
                                             queue_family_index, upload_wait, uploaded ? 1u : 0u, width, height);
        if (uploaded && !submitted) recover_unconsumed_software_upload(slot);
    }

    // Called with `mutex` held. Both the Azahar hardware image and the
    // software upload image share this swapchain blit/present path.
    // The return value means the source wait semaphores were consumed by a
    // successful queue submission (even if the subsequent present asks the
    // caller to recreate the swapchain).
    bool present_image(VkImage source_image, VkImageLayout source_layout,
                       VkImageSubresourceRange source_range, VkFormat source_format,
                       uint32_t source_queue_family,
                       const VkSemaphore* source_semaphores, uint32_t source_semaphore_count,
                       unsigned width, unsigned height) {
        if (!source_image || !width || !height ||
            width > static_cast<unsigned>(std::numeric_limits<int32_t>::max()) ||
            height > static_cast<unsigned>(std::numeric_limits<int32_t>::max()) ||
            source_semaphore_count > kMaxSourceWaitSemaphores) {
            ++metrics.dropped_frames;
            return false;
        }
        ScopedTiming timing{metrics.present};
        std::string ignored_error;
        if (!recreate_swapchain_if_needed(ignored_error)) {
            ++metrics.dropped_frames;
            return false;
        }
        uint32_t frame_index = kNoFrameSlot;
        if (!prepare_presentation_frame(frame_index)) {
            ++metrics.dropped_frames;
            return false;
        }
        auto& frame = presentation_frames[frame_index];
        const auto abandon = [this, frame_index]() {
            ++metrics.dropped_frames;
            finish_presentation_frame(frame_index, false);
        };
        VkFormatProperties source_properties{};
        get_format_properties(physical_device, source_format, &source_properties);
        if (!(source_properties.optimalTilingFeatures & VK_FORMAT_FEATURE_BLIT_SRC_BIT)) {
            abandon();
            return false;
        }
        const VkFilter blit_filter = (source_properties.optimalTilingFeatures &
                                      VK_FORMAT_FEATURE_SAMPLED_IMAGE_FILTER_LINEAR_BIT)
            ? VK_FILTER_LINEAR : VK_FILTER_NEAREST;
        uint32_t image_index = 0;
        const VkResult acquired = acquire_next_image(device, swapchain, UINT64_MAX, frame.image_available, VK_NULL_HANDLE, &image_index);
        if (acquired == VK_ERROR_OUT_OF_DATE_KHR) {
            abandon();
            destroy_swapchain_resources(true);
            create_swapchain_resources(ignored_error);
            return false;
        }
        if ((acquired != VK_SUCCESS && acquired != VK_SUBOPTIMAL_KHR) || image_index >= command_buffers.size()) {
            abandon();
            destroy_swapchain_resources(true);
            return false;
        }
        const VkFence image_fence = image_in_flight[image_index];
        if (image_fence && image_fence != frame.in_flight &&
            wait_for_fences(device, 1, &image_fence, VK_TRUE, UINT64_MAX) != VK_SUCCESS) {
            abandon();
            return false;
        }
        const VkCommandBuffer command = command_buffers[image_index];
        if (reset_command_buffer(command, 0) != VK_SUCCESS) {
            abandon();
            destroy_swapchain_resources(true);
            return false;
        }
        VkCommandBufferBeginInfo begin{};
        begin.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        if (begin_command_buffer(command, &begin) != VK_SUCCESS) {
            abandon();
            destroy_swapchain_resources(true);
            return false;
        }

        if (!source_range.aspectMask) source_range.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        if (!source_range.levelCount) source_range.levelCount = 1;
        if (!source_range.layerCount) source_range.layerCount = 1;
        const bool transfer_source_ownership = source_queue_family != VK_QUEUE_FAMILY_IGNORED &&
                                               source_queue_family != queue_family_index;
        VkImageMemoryBarrier begin_barriers[2]{};
        begin_barriers[0].sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
        begin_barriers[0].srcAccessMask = VK_ACCESS_MEMORY_WRITE_BIT;
        begin_barriers[0].dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
        begin_barriers[0].oldLayout = source_layout;
        begin_barriers[0].newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
        begin_barriers[0].srcQueueFamilyIndex = transfer_source_ownership ? source_queue_family : VK_QUEUE_FAMILY_IGNORED;
        begin_barriers[0].dstQueueFamilyIndex = transfer_source_ownership ? queue_family_index : VK_QUEUE_FAMILY_IGNORED;
        begin_barriers[0].image = source_image;
        begin_barriers[0].subresourceRange = source_range;
        begin_barriers[1].sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
        begin_barriers[1].srcAccessMask = image_initialized[image_index] ? VK_ACCESS_MEMORY_READ_BIT : 0;
        begin_barriers[1].dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
        begin_barriers[1].oldLayout = image_initialized[image_index] ? VK_IMAGE_LAYOUT_PRESENT_SRC_KHR : VK_IMAGE_LAYOUT_UNDEFINED;
        begin_barriers[1].newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
        begin_barriers[1].srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        begin_barriers[1].dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        begin_barriers[1].image = swapchain_images[image_index];
        begin_barriers[1].subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        begin_barriers[1].subresourceRange.levelCount = 1;
        begin_barriers[1].subresourceRange.layerCount = 1;
        cmd_pipeline_barrier(command, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0,
                             0, nullptr, 0, nullptr, 2, begin_barriers);

        VkImageSubresourceRange destination_range{};
        destination_range.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        destination_range.levelCount = 1;
        destination_range.layerCount = 1;
        VkClearColorValue clear_color{};
        clear_color.float32[3] = 1.0f;
        cmd_clear_color_image(command, swapchain_images[image_index], VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                              &clear_color, 1, &destination_range);

        const float scale = std::min(static_cast<float>(extent.width) / static_cast<float>(width),
                                     static_cast<float>(extent.height) / static_cast<float>(height));
        const int32_t target_width = std::max(1, static_cast<int32_t>(width * scale));
        const int32_t target_height = std::max(1, static_cast<int32_t>(height * scale));
        const int32_t target_x = (static_cast<int32_t>(extent.width) - target_width) / 2;
        const int32_t target_y = (static_cast<int32_t>(extent.height) - target_height) / 2;
        VkImageBlit blit{};
        blit.srcSubresource.aspectMask = source_range.aspectMask;
        blit.srcSubresource.mipLevel = source_range.baseMipLevel;
        blit.srcSubresource.baseArrayLayer = source_range.baseArrayLayer;
        blit.srcSubresource.layerCount = 1;
        blit.srcOffsets[1] = { static_cast<int32_t>(width), static_cast<int32_t>(height), 1 };
        blit.dstSubresource.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        blit.dstSubresource.layerCount = 1;
        blit.dstOffsets[0] = { target_x, target_y, 0 };
        blit.dstOffsets[1] = { target_x + target_width, target_y + target_height, 1 };
        cmd_blit_image(command, source_image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                       swapchain_images[image_index], VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &blit, blit_filter);

        VkImageMemoryBarrier finish_barriers[2]{};
        finish_barriers[0].sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
        finish_barriers[0].srcAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
        finish_barriers[0].dstAccessMask = VK_ACCESS_MEMORY_READ_BIT;
        finish_barriers[0].oldLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
        finish_barriers[0].newLayout = source_layout;
        finish_barriers[0].srcQueueFamilyIndex = transfer_source_ownership ? queue_family_index : VK_QUEUE_FAMILY_IGNORED;
        finish_barriers[0].dstQueueFamilyIndex = transfer_source_ownership ? source_queue_family : VK_QUEUE_FAMILY_IGNORED;
        finish_barriers[0].image = source_image;
        finish_barriers[0].subresourceRange = source_range;
        finish_barriers[1].sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
        finish_barriers[1].srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
        finish_barriers[1].dstAccessMask = VK_ACCESS_MEMORY_READ_BIT;
        finish_barriers[1].oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
        finish_barriers[1].newLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
        finish_barriers[1].srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        finish_barriers[1].dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        finish_barriers[1].image = swapchain_images[image_index];
        finish_barriers[1].subresourceRange = destination_range;
        cmd_pipeline_barrier(command, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, 0,
                             0, nullptr, 0, nullptr, 2, finish_barriers);
        if (end_command_buffer(command) != VK_SUCCESS) {
            abandon();
            destroy_swapchain_resources(true);
            return false;
        }
        std::array<VkSemaphore, kMaxSourceWaitSemaphores + 1> wait_semaphores{};
        std::array<VkPipelineStageFlags, kMaxSourceWaitSemaphores + 1> wait_stages{};
        uint32_t wait_count = 0;
        wait_semaphores[wait_count] = frame.image_available;
        wait_stages[wait_count++] = VK_PIPELINE_STAGE_TRANSFER_BIT;
        for (uint32_t source_index = 0; source_index < source_semaphore_count; ++source_index) {
            const VkSemaphore semaphore = source_semaphores ? source_semaphores[source_index] : VK_NULL_HANDLE;
            if (semaphore) {
                wait_semaphores[wait_count] = semaphore;
                wait_stages[wait_count++] = VK_PIPELINE_STAGE_TRANSFER_BIT;
            }
        }
        VkSubmitInfo submit{};
        submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
        submit.waitSemaphoreCount = wait_count;
        submit.pWaitSemaphores = wait_semaphores.data();
        submit.pWaitDstStageMask = wait_stages.data();
        submit.commandBufferCount = 1;
        submit.pCommandBuffers = &command;
        submit.signalSemaphoreCount = 1;
        submit.pSignalSemaphores = &frame.render_finished;
        if (reset_fences(device, 1, &frame.in_flight) != VK_SUCCESS ||
            queue_submit(queue, 1, &submit, frame.in_flight) != VK_SUCCESS) {
            abandon();
            destroy_swapchain_resources(true);
            return false;
        }
        image_in_flight[image_index] = frame.in_flight;
        finish_presentation_frame(frame_index, true);
        VkPresentInfoKHR present{};
        present.sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR;
        present.waitSemaphoreCount = 1;
        present.pWaitSemaphores = &frame.render_finished;
        present.swapchainCount = 1;
        present.pSwapchains = &swapchain;
        present.pImageIndices = &image_index;
        const VkResult presented = queue_present(presentation_queue, &present);
        if (presented == VK_SUCCESS || presented == VK_SUBOPTIMAL_KHR) {
            image_initialized[image_index] = true;
            current_sync_index.fetch_add(1, std::memory_order_relaxed);
            frame_count.fetch_add(1, std::memory_order_relaxed);
        } else {
            destroy_swapchain_resources(true);
        }
        return true;
    }

    NativeRendererMetrics renderer_metrics() const {
        NativeRendererMetrics snapshot{};
        snapshot.presented_frames = frame_count.load(std::memory_order_relaxed);
        snapshot.dropped_frames = metrics.dropped_frames;
        snapshot.software_uploads = metrics.software_uploads;
        snapshot.direct_software_uploads = metrics.direct_software_uploads;
        snapshot.copied_software_uploads = metrics.copied_software_uploads;
        snapshot.converted_software_uploads = metrics.converted_software_uploads;
        snapshot.upload_p95_us = metrics.upload.percentile(95, 100);
        snapshot.upload_p99_us = metrics.upload.percentile(99, 100);
        snapshot.present_p95_us = metrics.present.percentile(95, 100);
        snapshot.present_p99_us = metrics.present.percentile(99, 100);
        return snapshot;
    }
};

PortableVulkanBackend::PortableVulkanBackend() : impl_(std::make_unique<Impl>(this)) {}
PortableVulkanBackend::~PortableVulkanBackend() = default;

bool PortableVulkanBackend::initialize(NativeWindowSurface* native_surface, const char* runtime_path,
                                const RetroHwRenderCallback& hardware_callbacks,
                                const void* negotiation_interface, std::string& error) {
    return impl_->initialize(native_surface, runtime_path, hardware_callbacks, negotiation_interface, error);
}

bool PortableVulkanBackend::initialize_software(NativeWindowSurface* native_surface, const char* runtime_path, std::string& error) {
    return impl_->initialize_software(native_surface, runtime_path, error);
}

void PortableVulkanBackend::shutdown() { impl_->shutdown(); }
bool PortableVulkanBackend::ready() const { return impl_->active; }
void* PortableVulkanBackend::hardware_interface() { return impl_->active ? &impl_->interface : nullptr; }
uint32_t PortableVulkanBackend::sync_index() const { return impl_->current_sync_index.load(std::memory_order_relaxed); }
uint32_t PortableVulkanBackend::sync_index_mask() const { return 0x3u; }
uint64_t PortableVulkanBackend::presented_frames() const { return impl_->frame_count.load(std::memory_order_relaxed); }
NativeRendererMetrics PortableVulkanBackend::renderer_metrics() const {
    std::scoped_lock lock{impl_->mutex};
    return impl_->renderer_metrics();
}

std::string PortableVulkanBackend::device_details() const {
    std::scoped_lock lock{impl_->mutex};
    if (!impl_->physical_device) return {};
    VkPhysicalDeviceProperties properties{};
    auto get = load_instance_function<PFN_vkGetPhysicalDeviceProperties>(impl_->get_instance_proc_addr,impl_->instance,"vkGetPhysicalDeviceProperties");
    if (!get) return {};
    get(impl_->physical_device,&properties);
    return std::string(properties.deviceName)+" API="+std::to_string(VK_VERSION_MAJOR(properties.apiVersion))+"."+std::to_string(VK_VERSION_MINOR(properties.apiVersion))+
        " type="+std::to_string(properties.deviceType)+" driver="+std::to_string(properties.driverVersion)+" FIFO images="+std::to_string(impl_->swapchain_images.size())+
        " format="+std::to_string(impl_->swapchain_format)+" colorSpace="+std::to_string(impl_->swapchain_color_space)+
        (impl_->swapchain_color_space == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR ? "" : " (non-sRGB color space: expect washed-out colors)");
}

void PortableVulkanBackend::receive_image(const void* image, uint32_t semaphore_count,
                                   const void* semaphores, uint32_t source_queue_family) {
    impl_->receive_image(static_cast<const RetroVulkanImage*>(image), semaphore_count,
                         static_cast<const VkSemaphore*>(semaphores), source_queue_family);
}

void PortableVulkanBackend::present(unsigned width, unsigned height) { impl_->present(width, height); }

void PortableVulkanBackend::present_software(const void* framebuffer, unsigned width, unsigned height,
                                      std::size_t pitch, int pixel_format) {
    impl_->present_software(framebuffer, width, height, pitch, pixel_format);
}

bool PortableVulkanBackend::acquire_software_framebuffer(unsigned width, unsigned height, int pixel_format,
                                                   void*& data, std::size_t& pitch) {
    return impl_->acquire_software_framebuffer(width, height, pixel_format, data, pitch);
}

bool PortableVulkanBackend::discard_pending_core_frame() {
    std::scoped_lock lock{impl_->mutex};
    return impl_->discard_pending_core_frame();
}

void PortableVulkanBackend::wait_sync_index() {
    std::scoped_lock lock{impl_->mutex};
    if (impl_->active && impl_->last_submitted_fence && impl_->wait_for_fences) {
        impl_->wait_for_fences(impl_->device, 1, &impl_->last_submitted_fence, VK_TRUE, UINT64_MAX);
    }
}

void PortableVulkanBackend::lock_queue() { impl_->mutex.lock(); }
void PortableVulkanBackend::unlock_queue() { impl_->mutex.unlock(); }
void PortableVulkanBackend::set_signal_semaphore(const void*) {}
void PortableVulkanBackend::set_command_buffers(uint32_t, const void*) {}

} // namespace an3
