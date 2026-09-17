/*
 * SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include "cocoa_surface.h"

#if defined(__APPLE__)

#import <Metal/Metal.h>
#import <QuartzCore/CAMetalLayer.h>

extern "C" void* an3_eden_cocoa_create_layer(uint32_t width, uint32_t height) {
    @autoreleasepool {
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        if (device == nil) {
            return nullptr;
        }
        CAMetalLayer* layer = [CAMetalLayer layer];
        layer.device = device;
        layer.pixelFormat = MTLPixelFormatBGRA8Unorm;
        layer.framebufferOnly = YES;
        layer.contentsScale = 1.0;
        layer.drawableSize = CGSizeMake(width, height);
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
        (void)metal_layer;
    }
}

#endif /* __APPLE__ */
