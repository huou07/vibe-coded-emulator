// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Hosted-frame consumer harness (macOS). This is a *separate process* from the
// Eden companion. It attaches to the shared-memory ring the companion publishes,
// consumes frame descriptors, resolves each opaque IOSurface id with
// IOSurfaceLookup() and imports it as an MTLTexture with
// -[MTLDevice newTextureWithDescriptor:iosurface:plane:]. It then reads the
// texture back on the CPU purely to prove the imported surface holds real
// pixels. It never links Eden; it links only the pure-C ring/transport and the
// Apple frameworks.
//
// Usage:
//   an3_eden_hosted_consumer <shm-name> [--frames N] [--timeout-ms M]
//
// Exit 0 when at least one distinct frame was imported into a Metal texture.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>

#include <IOSurface/IOSurface.h>

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>
#include <unistd.h>

#include "an3_eden_hosted_frame.h"
#include "an3_eden_hosted_frame_shm.h"

namespace {

struct ImportStats {
    int imported{0};
    int texture_ok{0};
    int readback_ok{0};
    uint64_t last_nonzero{0};
    uint64_t last_hash{0};
    uint32_t last_sequence{0};
    uint32_t last_slot{0};
    uint64_t last_surface{0};
};

int ring_consume(an3_eden_hosted_shm* shm, an3_eden_frame_desc* out) {
    if (an3_eden_hosted_shm_trylock(shm) != AN3_EDEN_HOSTED_OK) {
        return AN3_EDEN_HOSTED_ERR_BUSY;
    }
    const int rc = an3_eden_hosted_ring_consume(&shm->ring, out);
    an3_eden_hosted_shm_unlock(shm);
    return rc;
}

void ring_release(an3_eden_hosted_shm* shm, uint32_t slot) {
    if (an3_eden_hosted_shm_trylock(shm) != AN3_EDEN_HOSTED_OK) {
        return;
    }
    an3_eden_hosted_ring_release(&shm->ring, slot);
    an3_eden_hosted_shm_unlock(shm);
}

// Import one descriptor as an MTLTexture and hash its pixels. Returns false when
// no Metal texture could be created for the id.
bool import_frame(id<MTLDevice> device, const an3_eden_frame_desc& frame, ImportStats& stats) {
    IOSurfaceRef surface = IOSurfaceLookup(static_cast<IOSurfaceID>(frame.surface_id));
    if (surface == nullptr) {
        return false;
    }

    MTLTextureDescriptor* descriptor = [[MTLTextureDescriptor alloc] init];
    descriptor.textureType = MTLTextureType2D;
    descriptor.pixelFormat = MTLPixelFormatBGRA8Unorm;
    descriptor.width = frame.width;
    descriptor.height = frame.height;
    descriptor.mipmapLevelCount = 1;
    descriptor.storageMode = MTLStorageModeShared;
    descriptor.usage = MTLTextureUsageShaderRead;

    id<MTLTexture> texture = [device newTextureWithDescriptor:descriptor
                                                    iosurface:surface
                                                        plane:0];
    const bool texture_created = texture != nil;
    uint64_t nonzero = 0;
    uint64_t hash = 0;
    bool readback = false;
    if (texture_created && texture.storageMode == MTLStorageModeShared) {
        const NSUInteger bytes_per_row = static_cast<NSUInteger>(frame.width) * 4u;
        const NSUInteger total = bytes_per_row * static_cast<NSUInteger>(frame.height);
        NSMutableData* data = [NSMutableData dataWithLength:total];
        if (data != nil) {
            [texture getBytes:[data mutableBytes]
                  bytesPerRow:bytes_per_row
                   fromRegion:MTLRegionMake2D(0, 0, frame.width, frame.height)
                  mipmapLevel:0];
            const uint8_t* base = static_cast<const uint8_t*>([data bytes]);
            hash = 1469598103934665603ULL;
            for (NSUInteger i = 0; i < total; ++i) {
                const uint8_t byte = base[i];
                hash ^= byte;
                hash *= 1099511628211ULL;
                nonzero += byte != 0 ? 1u : 0u;
            }
            readback = true;
        }
    }
    CFRelease(surface);

    if (!texture_created) {
        return false;
    }
    ++stats.texture_ok;
    if (readback) {
        ++stats.readback_ok;
    }
    stats.last_nonzero = nonzero;
    stats.last_hash = hash;
    stats.last_sequence = frame.sequence;
    stats.last_slot = frame.slot;
    stats.last_surface = frame.surface_id;

    std::printf("\nHF_IMPORT {\"consumer\":1,\"pid\":%d,\"seq\":%u,\"epoch\":%llu,\"slot\":%u,"
                "\"surface\":%llu,\"w\":%u,\"h\":%u,\"texture\":1,\"readback\":%d,"
                "\"nonzero\":%llu,\"hash\":%llu}\n",
                static_cast<int>(::getpid()), frame.sequence,
                static_cast<unsigned long long>(frame.producer_epoch), frame.slot,
                static_cast<unsigned long long>(frame.surface_id), frame.width, frame.height,
                readback ? 1 : 0, static_cast<unsigned long long>(nonzero),
                static_cast<unsigned long long>(hash));
    std::fflush(stdout);
    return true;
}

} // namespace

int main(int argc, char** argv) {
    const char* shm_name = nullptr;
    int frames = 5;
    int timeout_ms = 15000;
    for (int index = 1; index < argc; ++index) {
        if (std::strcmp(argv[index], "--frames") == 0 && index + 1 < argc) {
            frames = std::atoi(argv[++index]);
            continue;
        }
        if (std::strcmp(argv[index], "--timeout-ms") == 0 && index + 1 < argc) {
            timeout_ms = std::atoi(argv[++index]);
            continue;
        }
        shm_name = argv[index];
    }
    if (shm_name == nullptr || frames <= 0) {
        std::fprintf(stderr,
                     "usage: an3_eden_hosted_consumer <shm-name> [--frames N] [--timeout-ms M]\n");
        return 2;
    }

    an3_eden_hosted_shm* shm = nullptr;
    const auto attach_deadline =
        std::chrono::steady_clock::now() + std::chrono::milliseconds(3000);
    while (std::chrono::steady_clock::now() < attach_deadline) {
        if (an3_eden_hosted_shm_attach(shm_name, &shm) == AN3_EDEN_HOSTED_OK) {
            break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    if (shm == nullptr) {
        std::printf("\nAN3CTL_CONSUMER {\"shm\":\"%s\",\"pid\":%d,\"imported\":0,"
                    "\"result\":\"FAIL\",\"reason\":\"attach\"}\n",
                    shm_name, static_cast<int>(::getpid()));
        return 1;
    }

    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    if (device == nil) {
        std::printf("\nAN3CTL_CONSUMER {\"shm\":\"%s\",\"pid\":%d,\"imported\":0,"
                    "\"result\":\"FAIL\",\"reason\":\"no_metal_device\"}\n",
                    shm_name, static_cast<int>(::getpid()));
        an3_eden_hosted_shm_detach(shm);
        return 1;
    }

    ImportStats stats;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
    while (stats.imported < frames && std::chrono::steady_clock::now() < deadline) {
        an3_eden_frame_desc frame;
        std::memset(&frame, 0, sizeof(frame));
        const int rc = ring_consume(shm, &frame);
        if (rc != AN3_EDEN_HOSTED_OK) {
            std::this_thread::sleep_for(std::chrono::milliseconds(2));
            continue;
        }
        if (frame.pixel_format != AN3_EDEN_PIXEL_FORMAT_BGRA8_UNORM || frame.width == 0 ||
            frame.height == 0) {
            ring_release(shm, frame.slot);
            continue;
        }
        import_frame(device, frame, stats);
        ring_release(shm, frame.slot);
        ++stats.imported;
    }

    an3_eden_hosted_shm_detach(shm);

    const bool pass = stats.imported > 0 && stats.texture_ok == stats.imported &&
                      stats.readback_ok == stats.imported && stats.last_nonzero > 0;
    std::printf("\nAN3CTL_CONSUMER {\"shm\":\"%s\",\"pid\":%d,\"requested\":%d,\"imported\":%d,"
                "\"texture_ok\":%d,\"readback_ok\":%d,\"seq\":%u,\"slot\":%u,\"surface\":%llu,"
                "\"nonzero\":%llu,\"hash\":%llu,\"result\":\"%s\"}\n",
                shm_name, static_cast<int>(::getpid()), frames, stats.imported, stats.texture_ok,
                stats.readback_ok, stats.last_sequence, stats.last_slot,
                static_cast<unsigned long long>(stats.last_surface),
                static_cast<unsigned long long>(stats.last_nonzero),
                static_cast<unsigned long long>(stats.last_hash), pass ? "PASS" : "FAIL");
    std::fflush(stdout);
    return pass ? 0 : 1;
}
