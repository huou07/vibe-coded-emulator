#pragma once
#include "../../core/renderer_contract.h"
#include "../../core/window_surface.h"

#include <memory>

namespace an3 {
class PortableVulkanBackend {
  public:
    PortableVulkanBackend();
    ~PortableVulkanBackend();
    PortableVulkanBackend(const PortableVulkanBackend&) = delete;
    PortableVulkanBackend& operator=(const PortableVulkanBackend&) = delete;

    bool initialize(NativeWindowSurface* native_surface,
                    const char* runtime_path,
                    const RetroHwRenderCallback& hardware_callbacks,
                    const void* negotiation_interface,
                    std::string& error);
    // Software libretro cores still benefit from the same native Vulkan /
    // MoltenVK / Metal presentation path. Their CPU framebuffer is converted
    // to BGRA8 in a host-visible staging buffer, uploaded into a Vulkan image,
    // then blitted through the existing swapchain presenter.
    bool initialize_software(NativeWindowSurface* native_surface, const char* runtime_path, std::string& error);
    void shutdown();
    bool ready() const;

    void receive_image(const void* image,
                       uint32_t semaphore_count,
                       const void* semaphores,
                       uint32_t source_queue_family);
    void present(unsigned width, unsigned height);
    // `pixel_format` uses libretro's stable enum values:
    // 0 = 0RGB1555, 1 = XRGB8888, 2 = RGB565.
    // A null framebuffer duplicates the most recently uploaded image.
    void present_software(const void* framebuffer,
                          unsigned width,
                          unsigned height,
                          std::size_t pitch,
                          int pixel_format);
    // Libretro software cores may ask the frontend for a writable framebuffer
    // during retro_run. When the source pixel format can be uploaded directly,
    // expose a persistently mapped ring slot so the core writes into the Vulkan
    // upload buffer instead of first rendering into an intermediate allocation.
    bool acquire_software_framebuffer(unsigned width,
                                      unsigned height,
                                      int pixel_format,
                                      void*& data,
                                      std::size_t& pitch);
    // Discard a pending hardware frame before its libretro context is
    // destroyed. This is an error/shutdown path: it consumes any one-shot
    // source semaphores and releases image ownership back to the core.
    bool discard_pending_core_frame();

    void* hardware_interface();
    uint32_t sync_index() const;
    uint32_t sync_index_mask() const;
    void wait_sync_index();
    void lock_queue();
    void unlock_queue();
    void set_signal_semaphore(const void* semaphore);
    void set_command_buffers(uint32_t count, const void* command_buffers);
    uint64_t presented_frames() const;
    NativeRendererMetrics renderer_metrics() const;
    std::string device_details() const;

  private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace an3
