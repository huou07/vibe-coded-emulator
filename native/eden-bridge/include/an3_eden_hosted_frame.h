// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Hosted-frame metadata protocol shared by the Eden companion (producer) and
// the AN3 host (consumer). This header is pure C and contains no GPU code: it
// defines the bounded ring contract, validation, and newest-frame-wins
// semantics so both sides agree on a versioned wire format.
//
// It carries only opaque surface identifiers and metadata. It never carries a
// process-private pointer, and it never carries pixel data.
#ifndef AN3_EDEN_HOSTED_FRAME_H
#define AN3_EDEN_HOSTED_FRAME_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Bump when the struct layout or semantics change. Consumers must reject a
 * descriptor whose version does not match exactly. */
#define AN3_EDEN_HOSTED_PROTOCOL_VERSION 1u

/* Bounded producer ring: 2-3 surfaces, never one allocation per frame. */
#define AN3_EDEN_HOSTED_RING_SLOTS 3u

/* Pixel formats. Only formats actually produced by the pinned MoltenVK path
 * may be added; BGRA8 UNORM is what the CAMetalLayer advertises. */
enum {
    AN3_EDEN_PIXEL_FORMAT_UNKNOWN = 0,
    AN3_EDEN_PIXEL_FORMAT_BGRA8_UNORM = 1,
};

/* Status codes (negative = failure, 0 = ok). */
enum {
    AN3_EDEN_HOSTED_OK = 0,
    AN3_EDEN_HOSTED_ERR_VERSION = -1,
    AN3_EDEN_HOSTED_ERR_ARGUMENT = -2,
    AN3_EDEN_HOSTED_ERR_SLOT = -3,
    AN3_EDEN_HOSTED_ERR_STALE = -4,
    AN3_EDEN_HOSTED_ERR_BUSY = -5,
    AN3_EDEN_HOSTED_ERR_EMPTY = -6,
};

typedef struct {
    uint32_t protocol_version;
    uint32_t sequence;     /* monotonic per producer_epoch */
    uint32_t slot;         /* 0 .. AN3_EDEN_HOSTED_RING_SLOTS-1 */
    uint32_t width;
    uint32_t height;
    uint32_t pixel_format;
    uint64_t producer_epoch; /* changes when the companion restarts */
    uint64_t surface_id;     /* opaque IOSurface id / shareable token; 0 = invalid */
} an3_eden_frame_desc;

/* Shared ring bookkeeping. The producer publishes descriptors; the consumer
 * marks slots it still owns and releases them when the GPU is done reading.
 * `slot_consumer_busy` is the only field the consumer writes. */
typedef struct {
    uint32_t protocol_version;
    uint32_t slots;
    uint32_t next_slot;
    uint32_t published_sequence; /* newest published, 0 = none yet */
    uint32_t consumed_sequence;  /* newest consumed by the host */
    uint8_t slot_consumer_busy[AN3_EDEN_HOSTED_RING_SLOTS];
    an3_eden_frame_desc latest;  /* descriptor of published_sequence */
} an3_eden_hosted_ring;

/* Reset the ring to an empty state for the given protocol version. */
int an3_eden_hosted_ring_init(an3_eden_hosted_ring* ring, uint32_t protocol_version);

/* Validate a descriptor against the ring contract without mutating state. */
int an3_eden_hosted_ring_validate(const an3_eden_hosted_ring* ring,
                                  const an3_eden_frame_desc* frame);

/* Producer selects the next slot it may write without publishing. The producer
 * calls this *before* it renders/copies the frame so it knows which slot to
 * write. Returns ERR_BUSY when every slot is consumer-owned. */
int an3_eden_hosted_ring_pick_slot(const an3_eden_hosted_ring* ring, uint32_t* out_slot);

/* Producer publishes a completed frame into a slot it already picked and wrote.
 * Fails with ERR_BUSY if the consumer owns that slot (the producer must not
 * overwrite a frame the consumer is still reading) and with ERR_SLOT if the
 * slot is out of range. Updates `frame->slot` and `frame->sequence` on success.
 * This is the slot-explicit form used by the real producer; `publish` remains
 * the convenience form (pick + publish_into). */
int an3_eden_hosted_ring_publish_into(an3_eden_hosted_ring* ring, an3_eden_frame_desc* frame,
                                      uint32_t slot);

/* Producer publishes a completed frame. Picks the next slot that the consumer
 * does not own. If every slot is consumer-owned the frame is dropped (BUSY) so
 * the producer never overwrites a frame the consumer is still reading.
 * Returns AN3_EDEN_HOSTED_OK and updates `frame->slot` on success. */
int an3_eden_hosted_ring_publish(an3_eden_hosted_ring* ring, an3_eden_frame_desc* frame);

/* Consumer takes the newest published frame that is not older than what it has
 * already consumed. Returns ERR_EMPTY when nothing newer exists, ERR_STALE for
 * a regressing sequence. */
int an3_eden_hosted_ring_consume(an3_eden_hosted_ring* ring, an3_eden_frame_desc* out);

/* Consumer releases a slot after it has finished reading it. */
int an3_eden_hosted_ring_release(an3_eden_hosted_ring* ring, uint32_t slot);

/* True when the sequence has advanced past what the consumer has consumed. */
int an3_eden_hosted_ring_has_newer(const an3_eden_hosted_ring* ring);

#ifdef __cplusplus
}
#endif

#endif /* AN3_EDEN_HOSTED_FRAME_H */
