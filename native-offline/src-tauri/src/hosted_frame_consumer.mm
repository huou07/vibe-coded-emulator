// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// AN3-side hosted-frame consumer implementation. See hosted_frame_consumer.h.
#import <AppKit/AppKit.h>
#import <CoreImage/CoreImage.h>
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <MetalKit/MetalKit.h>

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <thread>

#include "hosted_frame_consumer.h"
#include "an3_eden_hosted_frame.h"
#include "an3_eden_hosted_frame_shm.h"

namespace {

std::mutex g_frame_mutex;
id<MTLTexture> g_latest_texture = nil;
an3_eden_hosted_consumer_stats g_stats{};
std::atomic<uint64_t> g_presented_frames{0};

an3_eden_hosted_shm* g_shm = nullptr;
std::atomic<bool> g_attached{false};
std::atomic<bool> g_stop{false};
std::thread g_thread;

id<MTLDevice> g_device = nil;
id<MTLCommandQueue> g_command_queue = nil;
CIContext* g_ci_context = nil;
CGColorSpaceRef g_color_space = nullptr;
MTKView* g_view = nil;

void record_frame(const an3_eden_frame_desc& frame, bool imported) {
    std::lock_guard<std::mutex> lock(g_frame_mutex);
    g_stats.last_sequence = frame.sequence;
    g_stats.last_slot = frame.slot;
    g_stats.width = frame.width;
    g_stats.height = frame.height;
    g_stats.last_surface_id = frame.surface_id;
    if (imported) {
        ++g_stats.imported_frames;
    }
}

void consume_loop() {
    while (!g_stop.load(std::memory_order_relaxed)) {
        an3_eden_frame_desc frame;
        std::memset(&frame, 0, sizeof(frame));
        int rc = AN3_EDEN_HOSTED_ERR_EMPTY;
        if (an3_eden_hosted_shm_trylock(g_shm) == AN3_EDEN_HOSTED_OK) {
            rc = an3_eden_hosted_ring_consume(&g_shm->ring, &frame);
            an3_eden_hosted_shm_unlock(g_shm);
        }
        if (rc != AN3_EDEN_HOSTED_OK || frame.pixel_format != AN3_EDEN_PIXEL_FORMAT_BGRA8_UNORM ||
            frame.width == 0 || frame.height == 0) {
            std::this_thread::sleep_for(std::chrono::milliseconds(2));
            continue;
        }

        IOSurfaceRef surface = IOSurfaceLookup(static_cast<IOSurfaceID>(frame.surface_id));
        bool imported = false;
        if (surface != nullptr && g_device != nil) {
            MTLTextureDescriptor* descriptor = [[MTLTextureDescriptor alloc] init];
            descriptor.textureType = MTLTextureType2D;
            descriptor.pixelFormat = MTLPixelFormatBGRA8Unorm;
            descriptor.width = frame.width;
            descriptor.height = frame.height;
            descriptor.mipmapLevelCount = 1;
            descriptor.storageMode = MTLStorageModeShared;
            descriptor.usage = MTLTextureUsageShaderRead;
            id<MTLTexture> texture = [g_device newTextureWithDescriptor:descriptor
                                                             iosurface:surface
                                                                 plane:0];
            if (texture != nil) {
                std::lock_guard<std::mutex> lock(g_frame_mutex);
                g_latest_texture = texture;
                imported = true;
            }
            CFRelease(surface);
        }
        record_frame(frame, imported);

        if (an3_eden_hosted_shm_trylock(g_shm) == AN3_EDEN_HOSTED_OK) {
            an3_eden_hosted_ring_release(&g_shm->ring, frame.slot);
            an3_eden_hosted_shm_unlock(g_shm);
        }
    }
}

an3_eden_hosted_consumer_stats snapshot() {
    std::lock_guard<std::mutex> lock(g_frame_mutex);
    return g_stats;
}

// Draws the newest imported texture into the view's drawable, aspect-fit
// (letterboxed) over a black clear. Returns true when a frame was submitted.
bool render_latest(MTKView* view) {
    id<MTLTexture> texture = nil;
    {
        std::lock_guard<std::mutex> lock(g_frame_mutex);
        texture = g_latest_texture;
    }
    if (texture == nil || view == nil || g_command_queue == nil || g_ci_context == nil ||
        g_color_space == nullptr || view.currentDrawable == nil) {
        return false;
    }
    CIImage* image = [CIImage imageWithMTLTexture:texture options:nil];
    if (image == nil) {
        return false;
    }
    const CGSize drawable_size = view.drawableSize;
    if (drawable_size.width < 1.0 || drawable_size.height < 1.0) {
        return false;
    }
    const CGRect bounds = CGRectMake(0, 0, drawable_size.width, drawable_size.height);
    const CGFloat image_width = MAX(image.extent.size.width, 1.0);
    const CGFloat image_height = MAX(image.extent.size.height, 1.0);
    // Aspect-fit inside the drawable, centered: black bars on the unused axis.
    const CGFloat scale = MIN(drawable_size.width / image_width, drawable_size.height / image_height);
    const CGFloat offset_x = (drawable_size.width - image_width * scale) * 0.5;
    const CGFloat offset_y = (drawable_size.height - image_height * scale) * 0.5;
    CIImage* scaled = [image
        imageByApplyingTransform:CGAffineTransformMake(scale, 0, 0, scale, offset_x, offset_y)];

    id<MTLCommandBuffer> buffer = [g_command_queue commandBuffer];
    MTLRenderPassDescriptor* pass = [MTLRenderPassDescriptor renderPassDescriptor];
    pass.colorAttachments[0].texture = view.currentDrawable.texture;
    pass.colorAttachments[0].loadAction = MTLLoadActionClear;
    pass.colorAttachments[0].storeAction = MTLStoreActionStore;
    pass.colorAttachments[0].clearColor = MTLClearColorMake(0.0, 0.0, 0.0, 1.0);
    id<MTLRenderCommandEncoder> encoder = [buffer renderCommandEncoderWithDescriptor:pass];
    [encoder endEncoding];
    [g_ci_context render:scaled
             toMTLTexture:view.currentDrawable.texture
            commandBuffer:buffer
                   bounds:bounds
               colorSpace:g_color_space];
    [buffer presentDrawable:view.currentDrawable];
    [buffer commit];
    return true;
}

} // namespace

// A pointer-inert Metal view: it draws the newest hosted frame but never
// receives a pointer, so the player's own controls keep their input precedence.
@interface AN3HostedFrameView : MTKView <MTKViewDelegate>
@end

@implementation AN3HostedFrameView

- (NSView*)hitTest:(NSPoint)point {
    (void)point;
    return nil;
}

- (BOOL)acceptsFirstResponder {
    return NO;
}

- (void)mtkView:(MTKView*)view drawableSizeWillChange:(CGSize)size {
    (void)view;
    (void)size;
}

- (void)drawInMTKView:(MTKView*)view {
    if (render_latest(view)) {
        g_presented_frames.fetch_add(1, std::memory_order_relaxed);
    }
}

@end

extern "C" int an3_eden_hosted_consumer_attach(const char* shm_name) {
    if (shm_name == nullptr || shm_name[0] == '\0') {
        return 0;
    }
    an3_eden_hosted_consumer_detach();
    an3_eden_hosted_shm* shm = nullptr;
    if (an3_eden_hosted_shm_attach(shm_name, &shm) != AN3_EDEN_HOSTED_OK || shm == nullptr) {
        return 0;
    }
    if (g_device == nil) {
        g_device = MTLCreateSystemDefaultDevice();
    }
    if (g_device == nil) {
        an3_eden_hosted_shm_detach(shm);
        return 0;
    }
    g_shm = shm;
    g_stop.store(false, std::memory_order_relaxed);
    g_attached.store(true, std::memory_order_relaxed);
    g_thread = std::thread(consume_loop);
    return 1;
}

extern "C" void an3_eden_hosted_consumer_detach(void) {
    g_stop.store(true, std::memory_order_relaxed);
    if (g_thread.joinable()) {
        g_thread.join();
    }
    g_attached.store(false, std::memory_order_relaxed);
    if (g_shm != nullptr) {
        an3_eden_hosted_shm_detach(g_shm);
        g_shm = nullptr;
    }
    std::lock_guard<std::mutex> lock(g_frame_mutex);
    g_latest_texture = nil;
}

extern "C" int an3_eden_hosted_consumer_is_attached(void) {
    return g_attached.load(std::memory_order_relaxed) ? 1 : 0;
}

extern "C" int an3_eden_hosted_consumer_get_stats(an3_eden_hosted_consumer_stats* out) {
    if (out == nullptr) {
        return 0;
    }
    *out = snapshot();
    return (g_attached.load(std::memory_order_relaxed) || out->imported_frames > 0) ? 1 : 0;
}

extern "C" int an3_eden_hosted_consumer_verify_latest(an3_eden_hosted_consumer_stats* out) {
    if (out == nullptr) {
        return 0;
    }
    id<MTLTexture> texture = nil;
    an3_eden_hosted_consumer_stats stats;
    {
        std::lock_guard<std::mutex> lock(g_frame_mutex);
        texture = g_latest_texture;
        stats = g_stats;
    }
    if (texture == nil || texture.storageMode != MTLStorageModeShared) {
        return 0;
    }
    const NSUInteger bytes_per_row = texture.width * 4u;
    const NSUInteger total = bytes_per_row * texture.height;
    NSMutableData* data = [NSMutableData dataWithLength:total];
    if (data == nil) {
        return 0;
    }
    [texture getBytes:[data mutableBytes]
          bytesPerRow:bytes_per_row
           fromRegion:MTLRegionMake2D(0, 0, texture.width, texture.height)
          mipmapLevel:0];
    const uint8_t* base = static_cast<const uint8_t*>([data bytes]);
    uint64_t hash = 1469598103934665603ULL;
    uint64_t nonzero = 0;
    for (NSUInteger i = 0; i < total; ++i) {
        const uint8_t byte = base[i];
        hash ^= byte;
        hash *= 1099511628211ULL;
        nonzero += byte != 0 ? 1u : 0u;
    }
    {
        std::lock_guard<std::mutex> lock(g_frame_mutex);
        ++g_stats.readback_frames;
        g_stats.last_nonzero = nonzero;
        g_stats.last_hash = hash;
        stats = g_stats;
    }
    *out = stats;
    return 1;
}

extern "C" int an3_eden_hosted_consumer_present_start(void* content_view) {
    if (content_view == nullptr) {
        return 0;
    }
    if (g_view != nil) {
        return 1;
    }
    if (g_device == nil) {
        g_device = MTLCreateSystemDefaultDevice();
    }
    if (g_device == nil) {
        return 0;
    }
    NSView* content = (__bridge NSView*)content_view;
    if (g_command_queue == nil) {
        g_command_queue = [g_device newCommandQueue];
    }
    if (g_ci_context == nil) {
        g_ci_context = [CIContext contextWithMTLDevice:g_device];
    }
    if (g_color_space == nullptr) {
        g_color_space = CGColorSpaceCreateDeviceRGB();
    }
    AN3HostedFrameView* view = [[AN3HostedFrameView alloc] initWithFrame:content.bounds
                                                                  device:g_device];
    view.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    view.colorPixelFormat = MTLPixelFormatBGRA8Unorm;
    view.preferredFramesPerSecond = 60;
    view.paused = NO;
    view.delegate = view;
    [content addSubview:view positioned:NSWindowAbove relativeTo:nil];
    g_view = view;
    return 1;
}

extern "C" void an3_eden_hosted_consumer_present_stop(void) {
    if (g_view != nil) {
        [g_view removeFromSuperview];
        g_view = nil;
    }
}

extern "C" int an3_eden_hosted_consumer_present_is_running(void) {
    return g_view != nil ? 1 : 0;
}

extern "C" int an3_eden_hosted_consumer_present_draw(void) {
    if (g_view == nil) {
        return 0;
    }
    if (render_latest(g_view)) {
        g_presented_frames.fetch_add(1, std::memory_order_relaxed);
        return 1;
    }
    return 0;
}

extern "C" uint64_t an3_eden_hosted_consumer_presented_frames(void) {
    return g_presented_frames.load(std::memory_order_relaxed);
}
