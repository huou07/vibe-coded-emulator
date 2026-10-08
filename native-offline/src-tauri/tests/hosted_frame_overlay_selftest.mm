// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Standalone overlay self-test. It drives the *real* app consumer
// (hosted_frame_consumer.mm) against a running companion's shared-memory ring,
// attaches the pointer-inert MTKView overlay to an off-screen (but real, backed)
// window, and renders the imported frame into the drawable once. This exercises
// the Metal/CIContext presentation path that a full app launch would.
//
// Usage: an3_hosted_frame_overlay_selftest <shm-name> [--wait-ms N]
// Emits a terminal `AN3CTL_OVERLAY {...}` line and exits non-zero on failure.
#import <AppKit/AppKit.h>
#import <CoreFoundation/CoreFoundation.h>
#import <Foundation/Foundation.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <unistd.h>

#include "hosted_frame_consumer.h"

int main(int argc, char** argv) {
    const char* shm_name = nullptr;
    int wait_ms = 10000;
    for (int index = 1; index < argc; ++index) {
        if (std::strcmp(argv[index], "--wait-ms") == 0 && index + 1 < argc) {
            wait_ms = std::atoi(argv[++index]);
            continue;
        }
        shm_name = argv[index];
    }
    if (shm_name == nullptr) {
        std::fprintf(stderr,
                     "usage: an3_hosted_frame_overlay_selftest <shm-name> [--wait-ms N]\n");
        return 2;
    }

    @autoreleasepool {
        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];

        NSWindow* window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 640, 360)
                                                       styleMask:NSWindowStyleMaskBorderless
                                                         backing:NSBackingStoreBuffered
                                                           defer:NO];
        window.releasedWhenClosed = NO;
        window.opaque = NO;
        window.backgroundColor = [NSColor clearColor];
        window.ignoresMouseEvents = YES;
        // Off every display but still a real, backed window: Core Animation
        // keeps compositing and recycling drawables (same fix as RG-115).
        [window setFrameOrigin:NSMakePoint(-32000.0, -32000.0)];
        [window orderFrontRegardless];
        NSView* content = window.contentView;

        if (an3_eden_hosted_consumer_attach(shm_name) != 1) {
            std::printf("\nAN3CTL_OVERLAY {\"result\":\"FAIL\",\"reason\":\"attach\"}\n");
            return 1;
        }
        if (an3_eden_hosted_consumer_present_start((__bridge void*)content) != 1) {
            std::printf("\nAN3CTL_OVERLAY {\"result\":\"FAIL\",\"reason\":\"present_start\"}\n");
            an3_eden_hosted_consumer_detach();
            return 1;
        }

        an3_eden_hosted_consumer_stats stats;
        std::memset(&stats, 0, sizeof(stats));
        for (int waited = 0; waited < wait_ms; waited += 20) {
            if (an3_eden_hosted_consumer_get_stats(&stats) == 1 && stats.imported_frames > 0) {
                break;
            }
            usleep(20 * 1000);
        }

        int drawn = 0;
        // AppKit only commits the layer and starts recycling drawables once the
        // main run loop is pumped, so drive it while we wait for the view's
        // display link to present a frame.
        for (int waited = 0; waited < 6000 && drawn == 0; waited += 50) {
            CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.05, true);
            if (an3_eden_hosted_consumer_presented_frames() > 0) {
                drawn = 1;
            }
        }
        for (int attempt = 0; attempt < 10 && drawn == 0; ++attempt) {
            CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.05, true);
            drawn = an3_eden_hosted_consumer_present_draw();
            if (drawn == 0) {
                usleep(50 * 1000);
            }
        }
        an3_eden_hosted_consumer_verify_latest(&stats);
        const uint64_t presented = an3_eden_hosted_consumer_presented_frames();
        const bool pass = drawn == 1 && stats.imported_frames > 0;
        std::printf("\nAN3CTL_OVERLAY {\"imported\":%llu,\"drawn\":%d,\"presented\":%llu,"
                    "\"width\":%u,\"height\":%u,\"nonzero\":%llu,\"result\":\"%s\"}\n",
                    static_cast<unsigned long long>(stats.imported_frames), drawn,
                    static_cast<unsigned long long>(presented), stats.width, stats.height,
                    static_cast<unsigned long long>(stats.last_nonzero), pass ? "PASS" : "FAIL");
        std::fflush(stdout);

        an3_eden_hosted_consumer_present_stop();
        an3_eden_hosted_consumer_detach();
        return pass ? 0 : 1;
    }
}
