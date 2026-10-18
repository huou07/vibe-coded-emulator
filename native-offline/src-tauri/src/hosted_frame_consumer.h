// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// AN3-side hosted-frame consumer. Attaches to the Eden companion's
// shared-memory ring, imports each published IOSurface id as an MTLTexture on a
// background thread, and (optionally) draws the newest texture into a
// pointer-inert MTKView overlay added to the player's content view.
//
// It never links Eden. The only cross-process data is the ring metadata and the
// global IOSurface ids it names.
#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct an3_eden_hosted_consumer_stats {
    uint64_t imported_frames;   /* frames imported into an MTLTexture */
    uint64_t readback_frames;   /* frames CPU-verified (diagnostic) */
    uint32_t last_sequence;
    uint32_t last_slot;
    uint32_t width;
    uint32_t height;
    uint64_t last_surface_id;
    uint64_t last_nonzero;
    uint64_t last_hash;
} an3_eden_hosted_consumer_stats;

/* Attach to the ring and start importing on a background thread. Returns
 * non-zero on success. Re-attaching replaces any previous attachment. */
int an3_eden_hosted_consumer_attach(const char* shm_name);
void an3_eden_hosted_consumer_detach(void);
int an3_eden_hosted_consumer_is_attached(void);

/* Copies the current counters. Returns non-zero when attached or when a frame
 * has ever been imported. */
int an3_eden_hosted_consumer_get_stats(an3_eden_hosted_consumer_stats* out);

/* Diagnostic only: reads the latest imported texture back on the CPU and fills
 * `out` with non-zero byte count and hash. Returns non-zero on success. */
int an3_eden_hosted_consumer_verify_latest(an3_eden_hosted_consumer_stats* out);

/* Presentation: create/destroy a pointer-inert MTKView overlay under
 * `content_view` (an NSView*). Must be called on the main thread. */
int an3_eden_hosted_consumer_present_start(void* content_view);
void an3_eden_hosted_consumer_present_stop(void);
int an3_eden_hosted_consumer_present_is_running(void);
/* Renders the latest imported frame into the overlay drawable exactly once.
 * Must be called on the main thread. Returns non-zero when a drawable was
 * available and the frame was submitted (used for deterministic tests). */
int an3_eden_hosted_consumer_present_draw(void);
uint64_t an3_eden_hosted_consumer_presented_frames(void);

#ifdef __cplusplus
}
#endif
