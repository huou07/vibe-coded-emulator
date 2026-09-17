/*
 * SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Hosted macOS presentation surface for the Eden bridge.
 *
 * RG-115: a bare CAMetalLayer that is not attached to an NSView/NSWindow has
 * zero bounds, so MoltenVK creates 0x0 swapchain images; vkAcquireNextImageKHR
 * then fails with kIOGPUCommandBufferCallbackErrorInvalidInput, the device is
 * lost, and Eden's GPU thread throws where the C ABI cannot contain it.
 * Hosting the layer on a hidden window/view gives it a real size and lets
 * Core Animation recycle drawables, which is what sustains rendering.
 */
#include "cocoa_surface.h"

#if defined(__APPLE__)

#import <AppKit/AppKit.h>
#import <Metal/Metal.h>
#import <QuartzCore/CAMetalLayer.h>
#import <objc/runtime.h>

namespace {

/* Keeps the window/view alive for as long as the layer exists. */
const void* kAn3EdenCocoaHostKey = &kAn3EdenCocoaHostKey;

}  // namespace

@interface An3EdenCocoaHost : NSObject
@property(nonatomic, strong) NSWindow* window;
@property(nonatomic, strong) NSView* view;
@end

@implementation An3EdenCocoaHost
@end

extern "C" void* an3_eden_cocoa_create_layer(uint32_t width, uint32_t height) {
    @autoreleasepool {
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        if (device == nil) {
            return nullptr;
        }
        const CGFloat w = width > 0 ? static_cast<CGFloat>(width) : 1280.0;
        const CGFloat h = height > 0 ? static_cast<CGFloat>(height) : 720.0;

        CAMetalLayer* layer = [CAMetalLayer layer];
        layer.device = device;
        layer.pixelFormat = MTLPixelFormatBGRA8Unorm;
        layer.framebufferOnly = YES;
        layer.contentsScale = 1.0;
        layer.frame = CGRectMake(0.0, 0.0, w, h);
        layer.drawableSize = CGSizeMake(w, h);

        /* AppKit requires the main thread and a window-server session. When
         * either is unavailable, return the sized bare layer so the caller can
         * still make an honest decision (and never a fake success). */
        if ([NSThread isMainThread]) {
            @try {
                [NSApplication sharedApplication];
                NSView* view = [[NSView alloc] initWithFrame:NSMakeRect(0.0, 0.0, w, h)];
                view.wantsLayer = YES;
                view.layer = layer;

                NSWindow* window = [[NSWindow alloc]
                    initWithContentRect:NSMakeRect(0.0, 0.0, w, h)
                              styleMask:NSWindowStyleMaskBorderless
                                backing:NSBackingStoreBuffered
                                  defer:NO];
                window.contentView = view;
                window.releasedWhenClosed = NO;
                window.opaque = NO;
                window.backgroundColor = [NSColor clearColor];
                window.ignoresMouseEvents = YES;
                window.hasShadow = NO;
                window.animationBehavior = NSWindowAnimationBehaviorNone;
                /* Off every display but still a real, backed window: Core
                 * Animation keeps compositing and recycling drawables. */
                [window setFrameOrigin:NSMakePoint(-32000.0, -32000.0)];
                [window orderFrontRegardless];

                An3EdenCocoaHost* host = [[An3EdenCocoaHost alloc] init];
                host.window = window;
                host.view = view;
                objc_setAssociatedObject(layer, kAn3EdenCocoaHostKey, host,
                                         OBJC_ASSOCIATION_RETAIN_NONATOMIC);
            } @catch (NSException* exception) {
                (void)exception;
            }
        }

        /* Hand a +1 reference to the C caller. */
        return (__bridge_retained void*)layer;
    }
}

extern "C" void an3_eden_cocoa_destroy_layer(void* layer) {
    if (layer == nullptr) {
        return;
    }
    @autoreleasepool {
        CAMetalLayer* metal_layer = (__bridge_transfer CAMetalLayer*)layer;
        An3EdenCocoaHost* host =
            objc_getAssociatedObject(metal_layer, kAn3EdenCocoaHostKey);
        if (host != nil) {
            [host.window orderOut:nil];
            host.window = nil;
            host.view = nil;
            objc_setAssociatedObject(metal_layer, kAn3EdenCocoaHostKey, nil,
                                     OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        }
    }
}

#endif /* __APPLE__ */
