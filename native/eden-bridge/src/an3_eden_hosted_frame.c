// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Pure-C hosted-frame ring implementation. No GPU access: it only enforces the
// versioned, bounded, newest-frame-wins contract shared by the Eden companion
// and the AN3 host.
#include "an3_eden_hosted_frame.h"

#include <string.h>

int an3_eden_hosted_ring_init(an3_eden_hosted_ring* ring, uint32_t protocol_version) {
    if (ring == 0) {
        return AN3_EDEN_HOSTED_ERR_ARGUMENT;
    }
    memset(ring, 0, sizeof(*ring));
    ring->protocol_version = protocol_version;
    ring->slots = AN3_EDEN_HOSTED_RING_SLOTS;
    return protocol_version == AN3_EDEN_HOSTED_PROTOCOL_VERSION ? AN3_EDEN_HOSTED_OK
                                                                 : AN3_EDEN_HOSTED_ERR_VERSION;
}

int an3_eden_hosted_ring_validate(const an3_eden_hosted_ring* ring,
                                  const an3_eden_frame_desc* frame) {
    if (ring == 0 || frame == 0) {
        return AN3_EDEN_HOSTED_ERR_ARGUMENT;
    }
    if (ring->protocol_version != AN3_EDEN_HOSTED_PROTOCOL_VERSION ||
        frame->protocol_version != AN3_EDEN_HOSTED_PROTOCOL_VERSION) {
        return AN3_EDEN_HOSTED_ERR_VERSION;
    }
    if (frame->surface_id == 0 || frame->width == 0 || frame->height == 0 ||
        frame->pixel_format == AN3_EDEN_PIXEL_FORMAT_UNKNOWN) {
        return AN3_EDEN_HOSTED_ERR_ARGUMENT;
    }
    if (frame->slot >= ring->slots) {
        return AN3_EDEN_HOSTED_ERR_SLOT;
    }
    return AN3_EDEN_HOSTED_OK;
}

int an3_eden_hosted_ring_pick_slot(const an3_eden_hosted_ring* ring, uint32_t* out_slot) {
    if (ring == 0 || out_slot == 0) {
        return AN3_EDEN_HOSTED_ERR_ARGUMENT;
    }
    if (ring->protocol_version != AN3_EDEN_HOSTED_PROTOCOL_VERSION) {
        return AN3_EDEN_HOSTED_ERR_VERSION;
    }
    for (uint32_t attempt = 0; attempt < AN3_EDEN_HOSTED_RING_SLOTS; ++attempt) {
        const uint32_t slot = (ring->next_slot + attempt) % AN3_EDEN_HOSTED_RING_SLOTS;
        if (slot >= ring->slots) {
            continue;
        }
        if (!ring->slot_consumer_busy[slot]) {
            *out_slot = slot;
            return AN3_EDEN_HOSTED_OK;
        }
    }
    return AN3_EDEN_HOSTED_ERR_BUSY;
}

int an3_eden_hosted_ring_publish_into(an3_eden_hosted_ring* ring, an3_eden_frame_desc* frame,
                                      uint32_t slot) {
    if (ring == 0 || frame == 0) {
        return AN3_EDEN_HOSTED_ERR_ARGUMENT;
    }
    if (ring->protocol_version != AN3_EDEN_HOSTED_PROTOCOL_VERSION ||
        frame->protocol_version != AN3_EDEN_HOSTED_PROTOCOL_VERSION) {
        return AN3_EDEN_HOSTED_ERR_VERSION;
    }
    if (frame->surface_id == 0 || frame->width == 0 || frame->height == 0 ||
        frame->pixel_format == AN3_EDEN_PIXEL_FORMAT_UNKNOWN) {
        return AN3_EDEN_HOSTED_ERR_ARGUMENT;
    }
    if (slot >= ring->slots) {
        return AN3_EDEN_HOSTED_ERR_SLOT;
    }
    if (ring->slot_consumer_busy[slot]) {
        return AN3_EDEN_HOSTED_ERR_BUSY;
    }
    frame->slot = slot;
    frame->sequence = ring->published_sequence + 1u;
    ring->latest = *frame;
    ring->published_sequence = frame->sequence;
    ring->next_slot = (slot + 1u) % AN3_EDEN_HOSTED_RING_SLOTS;
    return AN3_EDEN_HOSTED_OK;
}

int an3_eden_hosted_ring_publish(an3_eden_hosted_ring* ring, an3_eden_frame_desc* frame) {
    if (ring == 0 || frame == 0) {
        return AN3_EDEN_HOSTED_ERR_ARGUMENT;
    }
    uint32_t slot = 0;
    const int picked = an3_eden_hosted_ring_pick_slot(ring, &slot);
    if (picked != AN3_EDEN_HOSTED_OK) {
        return picked;
    }
    return an3_eden_hosted_ring_publish_into(ring, frame, slot);
}

int an3_eden_hosted_ring_has_newer(const an3_eden_hosted_ring* ring) {
    if (ring == 0 || ring->protocol_version != AN3_EDEN_HOSTED_PROTOCOL_VERSION) {
        return 0;
    }
    return ring->published_sequence != 0 && ring->published_sequence > ring->consumed_sequence;
}

int an3_eden_hosted_ring_consume(an3_eden_hosted_ring* ring, an3_eden_frame_desc* out) {
    if (ring == 0 || out == 0) {
        return AN3_EDEN_HOSTED_ERR_ARGUMENT;
    }
    if (ring->protocol_version != AN3_EDEN_HOSTED_PROTOCOL_VERSION) {
        return AN3_EDEN_HOSTED_ERR_VERSION;
    }
    if (ring->published_sequence == 0) {
        return AN3_EDEN_HOSTED_ERR_EMPTY;
    }
    if (ring->published_sequence < ring->consumed_sequence) {
        return AN3_EDEN_HOSTED_ERR_STALE;
    }
    if (ring->published_sequence == ring->consumed_sequence) {
        return AN3_EDEN_HOSTED_ERR_EMPTY;
    }
    /* Newest-frame-wins: the host takes exactly the latest published frame and
     * marks its slot consumer-owned until released. Older unconsumed frames are
     * dropped by design. */
    *out = ring->latest;
    ring->consumed_sequence = ring->latest.sequence;
    ring->slot_consumer_busy[ring->latest.slot] = 1u;
    return AN3_EDEN_HOSTED_OK;
}

int an3_eden_hosted_ring_release(an3_eden_hosted_ring* ring, uint32_t slot) {
    if (ring == 0) {
        return AN3_EDEN_HOSTED_ERR_ARGUMENT;
    }
    if (ring->protocol_version != AN3_EDEN_HOSTED_PROTOCOL_VERSION) {
        return AN3_EDEN_HOSTED_ERR_VERSION;
    }
    if (slot >= ring->slots) {
        return AN3_EDEN_HOSTED_ERR_SLOT;
    }
    ring->slot_consumer_busy[slot] = 0u;
    return AN3_EDEN_HOSTED_OK;
}
