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
 *
 * Setting AN3_EDEN_WINDOW_VISIBLE=1 makes the window an on-screen, focusable
 * companion window that forwards keyboard input to a registered handler; this
 * is the playable path used by the separate-process companion.
 */
#include "cocoa_surface.h"

#if defined(__APPLE__)

#import <AppKit/AppKit.h>
#import <Metal/Metal.h>
#import <QuartzCore/CAMetalLayer.h>
#import <objc/runtime.h>

#include <cstdlib>

namespace {

/* Keeps the window/view alive for as long as the layer exists. */
const void* kAn3EdenCocoaHostKey = &kAn3EdenCocoaHostKey;

an3_eden_key_handler g_key_handler = nullptr;

bool window_visible_requested() {
    const char* value = std::getenv("AN3_EDEN_WINDOW_VISIBLE");
    return value != nullptr && value[0] != '\0' && value[0] != '0';
}

}  // namespace

/* Forwards key events to the registered handler. A plain NSView does not
 * receive key events, so the surface owns this subclass. */
@interface An3EdenKeyView : NSView
@end

@implementation An3EdenKeyView
- (BOOL)acceptsFirstResponder {
    return YES;
}
- (BOOL)becomeFirstResponder {
    return YES;
}
- (void)keyDown:(NSEvent*)event {
    if (g_key_handler != nullptr) {
        g_key_handler(static_cast<int>(event.keyCode), 1);
    }
}
- (void)keyUp:(NSEvent*)event {
    if (g_key_handler != nullptr) {
        g_key_handler(static_cast<int>(event.keyCode), 0);
    }
}
@end

@interface An3EdenCocoaHost : NSObject
@property(nonatomic, strong) NSWindow* window;
@property(nonatomic, strong) An3EdenKeyView* view;
@end

@implementation An3EdenCocoaHost
@end

/* The companion owns a single window; keep it reachable for focus requests. */
static An3EdenCocoaHost* g_host = nil;

extern "C" void an3_eden_cocoa_set_key_handler(an3_eden_key_handler handler) {
    g_key_handler = handler;
}

extern "C" void an3_eden_cocoa_focus(void) {
    const auto activate = ^{
        [NSApp activateIgnoringOtherApps:YES];
        if (g_host != nil && g_host.window != nil) {
            [g_host.window makeKeyAndOrderFront:nil];
        }
    };
    if ([NSThread isMainThread]) {
        @autoreleasepool {
            activate();
        }
        return;
    }
    dispatch_async(dispatch_get_main_queue(), ^{
        @autoreleasepool {
            activate();
        }
    });
}

extern "C" void an3_eden_cocoa_run(int (*should_stop)(void)) {
    @autoreleasepool {
        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
        [NSApp finishLaunching];
        [NSTimer scheduledTimerWithTimeInterval:0.1
                                        repeats:YES
                                          block:^(NSTimer* timer) {
                                              (void)timer;
                                              if (should_stop != nullptr && should_stop()) {
                                                  [NSApp stop:nil];
                                                  /* Wake the loop so stop takes effect. */
                                                  NSEvent* wake = [NSEvent
                                                      otherEventWithType:NSEventTypeApplicationDefined
                                                                location:NSZeroPoint
                                                           modifierFlags:0
                                                               timestamp:0
                                                            windowNumber:0
                                                                 context:nil
                                                                 subtype:0
                                                                   data1:0
                                                                   data2:0];
                                                  [NSApp postEvent:wake atStart:NO];
                                              }
                                          }];
        [NSApp run];
    }
}

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
                An3EdenKeyView* view = [[An3EdenKeyView alloc] initWithFrame:NSMakeRect(0.0, 0.0, w, h)];
                view.wantsLayer = YES;
                view.layer = layer;

                const BOOL visible = window_visible_requested() ? YES : NO;
                NSWindow* window = [[NSWindow alloc]
                    initWithContentRect:NSMakeRect(0.0, 0.0, w, h)
                              styleMask:(visible ? (NSWindowStyleMaskTitled |
                                                    NSWindowStyleMaskClosable |
                                                    NSWindowStyleMaskMiniaturizable)
                                                 : NSWindowStyleMaskBorderless)
                                backing:NSBackingStoreBuffered
                                  defer:NO];
                window.contentView = view;
                window.releasedWhenClosed = NO;
                window.ignoresMouseEvents = visible ? NO : YES;
                window.hasShadow = visible ? YES : NO;
                window.animationBehavior = NSWindowAnimationBehaviorNone;
                if (visible) {
                    window.title = @"Vibe Coded Emulator — Switch";
                    window.backgroundColor = [NSColor blackColor];
                    [window center];
                    [window makeKeyAndOrderFront:nil];
                    [window makeFirstResponder:view];
                } else {
                    window.opaque = NO;
                    window.backgroundColor = [NSColor clearColor];
                    /* Off every display but still a real, backed window: Core
                     * Animation keeps compositing and recycling drawables. */
                    [window setFrameOrigin:NSMakePoint(-32000.0, -32000.0)];
                    [window orderFrontRegardless];
                }

                An3EdenCocoaHost* host = [[An3EdenCocoaHost alloc] init];
                host.window = window;
                host.view = view;
                objc_setAssociatedObject(layer, kAn3EdenCocoaHostKey, host,
                                         OBJC_ASSOCIATION_RETAIN_NONATOMIC);
                g_host = host;
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
            if (g_host == host) {
                g_host = nil;
            }
        }
    }
}

#endif /* __APPLE__ */
