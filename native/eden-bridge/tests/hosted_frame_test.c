// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Behavioral tests for the hosted-frame ring contract. Pure CPU: no GPU or
// MoltenVK required. Exits non-zero on the first failure.
#include "an3_eden_hosted_frame.h"

#include <stdio.h>
#include <string.h>

static int g_checks = 0;
static int g_failures = 0;

#define CHECK(expr)                                                     \
    do {                                                                \
        ++g_checks;                                                     \
        if (!(expr)) {                                                  \
            ++g_failures;                                               \
            fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #expr); \
        }                                                               \
    } while (0)

static an3_eden_frame_desc make_frame(uint32_t w, uint32_t h) {
    an3_eden_frame_desc frame;
    memset(&frame, 0, sizeof(frame));
    frame.protocol_version = AN3_EDEN_HOSTED_PROTOCOL_VERSION;
    frame.width = w;
    frame.height = h;
    frame.pixel_format = AN3_EDEN_PIXEL_FORMAT_BGRA8_UNORM;
    frame.producer_epoch = 7;
    frame.surface_id = 0x1234u;
    return frame;
}

static void test_init_and_empty(void) {
    an3_eden_hosted_ring ring;
    CHECK(an3_eden_hosted_ring_init(&ring, AN3_EDEN_HOSTED_PROTOCOL_VERSION) == AN3_EDEN_HOSTED_OK);
    CHECK(an3_eden_hosted_ring_has_newer(&ring) == 0);
    an3_eden_frame_desc out = make_frame(1280, 720);
    CHECK(an3_eden_hosted_ring_consume(&ring, &out) == AN3_EDEN_HOSTED_ERR_EMPTY);
}

static void test_version_and_argument_rejection(void) {
    an3_eden_hosted_ring ring;
    an3_eden_hosted_ring_init(&ring, AN3_EDEN_HOSTED_PROTOCOL_VERSION);

    an3_eden_frame_desc frame = make_frame(1280, 720);
    frame.protocol_version = AN3_EDEN_HOSTED_PROTOCOL_VERSION + 1;
    CHECK(an3_eden_hosted_ring_publish(&ring, &frame) == AN3_EDEN_HOSTED_ERR_VERSION);

    frame = make_frame(1280, 720);
    frame.surface_id = 0;
    CHECK(an3_eden_hosted_ring_publish(&ring, &frame) == AN3_EDEN_HOSTED_ERR_ARGUMENT);

    frame = make_frame(0, 720);
    CHECK(an3_eden_hosted_ring_validate(&ring, &frame) == AN3_EDEN_HOSTED_ERR_ARGUMENT);

    frame = make_frame(1280, 720);
    frame.pixel_format = AN3_EDEN_PIXEL_FORMAT_UNKNOWN;
    CHECK(an3_eden_hosted_ring_publish(&ring, &frame) == AN3_EDEN_HOSTED_ERR_ARGUMENT);

    frame = make_frame(1280, 720);
    frame.slot = 99;
    CHECK(an3_eden_hosted_ring_validate(&ring, &frame) == AN3_EDEN_HOSTED_ERR_SLOT);
    CHECK(an3_eden_hosted_ring_release(&ring, 99) == AN3_EDEN_HOSTED_ERR_SLOT);

    CHECK(an3_eden_hosted_ring_init(&ring, 999) == AN3_EDEN_HOSTED_ERR_VERSION);
    CHECK(an3_eden_hosted_ring_publish(0, &frame) == AN3_EDEN_HOSTED_ERR_ARGUMENT);
    CHECK(an3_eden_hosted_ring_consume(&ring, 0) == AN3_EDEN_HOSTED_ERR_ARGUMENT);
}

static void test_publish_consume_release(void) {
    an3_eden_hosted_ring ring;
    an3_eden_hosted_ring_init(&ring, AN3_EDEN_HOSTED_PROTOCOL_VERSION);
    an3_eden_frame_desc frame = make_frame(1280, 720);
    CHECK(an3_eden_hosted_ring_publish(&ring, &frame) == AN3_EDEN_HOSTED_OK);
    CHECK(frame.sequence == 1);
    CHECK(frame.slot < AN3_EDEN_HOSTED_RING_SLOTS);
    CHECK(an3_eden_hosted_ring_has_newer(&ring) == 1);

    an3_eden_frame_desc out;
    memset(&out, 0, sizeof(out));
    CHECK(an3_eden_hosted_ring_consume(&ring, &out) == AN3_EDEN_HOSTED_OK);
    CHECK(out.sequence == 1);
    CHECK(out.slot == frame.slot);
    CHECK(out.width == 1280 && out.height == 720);
    CHECK(out.surface_id == frame.surface_id);
    CHECK(an3_eden_hosted_ring_has_newer(&ring) == 0);
    CHECK(an3_eden_hosted_ring_consume(&ring, &out) == AN3_EDEN_HOSTED_ERR_EMPTY);
    CHECK(an3_eden_hosted_ring_release(&ring, out.slot) == AN3_EDEN_HOSTED_OK);
}

static void test_newest_frame_wins_and_drops_older(void) {
    an3_eden_hosted_ring ring;
    an3_eden_hosted_ring_init(&ring, AN3_EDEN_HOSTED_PROTOCOL_VERSION);
    for (uint32_t i = 0; i < 3; ++i) {
        an3_eden_frame_desc frame = make_frame(1280, 720);
        CHECK(an3_eden_hosted_ring_publish(&ring, &frame) == AN3_EDEN_HOSTED_OK);
    }
    an3_eden_frame_desc out;
    memset(&out, 0, sizeof(out));
    CHECK(an3_eden_hosted_ring_consume(&ring, &out) == AN3_EDEN_HOSTED_OK);
    CHECK(out.sequence == 3); /* only the newest is delivered */
}

static void test_producer_never_overwrites_a_owned_slot(void) {
    an3_eden_hosted_ring ring;
    an3_eden_hosted_ring_init(&ring, AN3_EDEN_HOSTED_PROTOCOL_VERSION);
    for (uint32_t i = 0; i < AN3_EDEN_HOSTED_RING_SLOTS; ++i) {
        an3_eden_frame_desc frame = make_frame(1280, 720);
        CHECK(an3_eden_hosted_ring_publish(&ring, &frame) == AN3_EDEN_HOSTED_OK);
        an3_eden_frame_desc out;
        memset(&out, 0, sizeof(out));
        CHECK(an3_eden_hosted_ring_consume(&ring, &out) == AN3_EDEN_HOSTED_OK);
        /* intentionally not released: the host still owns every slot */
    }
    an3_eden_frame_desc blocked = make_frame(1280, 720);
    CHECK(an3_eden_hosted_ring_publish(&ring, &blocked) == AN3_EDEN_HOSTED_ERR_BUSY);
    CHECK(an3_eden_hosted_ring_release(&ring, 0) == AN3_EDEN_HOSTED_OK);
    CHECK(an3_eden_hosted_ring_publish(&ring, &blocked) == AN3_EDEN_HOSTED_OK);
}

static void test_stale_sequence_is_rejected(void) {
    an3_eden_hosted_ring ring;
    an3_eden_hosted_ring_init(&ring, AN3_EDEN_HOSTED_PROTOCOL_VERSION);
    ring.published_sequence = 5;
    ring.consumed_sequence = 6;
    an3_eden_frame_desc out;
    memset(&out, 0, sizeof(out));
    CHECK(an3_eden_hosted_ring_consume(&ring, &out) == AN3_EDEN_HOSTED_ERR_STALE);
}

static void test_pick_slot_then_publish_into(void) {
    an3_eden_hosted_ring ring;
    an3_eden_hosted_ring_init(&ring, AN3_EDEN_HOSTED_PROTOCOL_VERSION);

    uint32_t slot = 99;
    CHECK(an3_eden_hosted_ring_pick_slot(&ring, &slot) == AN3_EDEN_HOSTED_OK);
    CHECK(slot == 0);

    an3_eden_frame_desc frame = make_frame(1280, 720);
    CHECK(an3_eden_hosted_ring_publish_into(&ring, &frame, slot) == AN3_EDEN_HOSTED_OK);
    CHECK(frame.slot == 0);
    CHECK(frame.sequence == 1);

    /* The pick cursor advances with the published slot. */
    uint32_t next = 99;
    CHECK(an3_eden_hosted_ring_pick_slot(&ring, &next) == AN3_EDEN_HOSTED_OK);
    CHECK(next == 1);

    /* A consumer-owned slot must never be overwritten. */
    ring.slot_consumer_busy[2] = 1;
    an3_eden_frame_desc blocked = make_frame(1280, 720);
    CHECK(an3_eden_hosted_ring_publish_into(&ring, &blocked, 2) == AN3_EDEN_HOSTED_ERR_BUSY);
    CHECK(an3_eden_hosted_ring_publish_into(&ring, &blocked, 9) == AN3_EDEN_HOSTED_ERR_SLOT);

    /* publish() is pick + publish_into and stays consistent. */
    ring.next_slot = 0;
    an3_eden_frame_desc via_publish = make_frame(1280, 720);
    CHECK(an3_eden_hosted_ring_publish(&ring, &via_publish) == AN3_EDEN_HOSTED_OK);
    CHECK(via_publish.slot == 0);

    /* Every slot owned -> pick reports BUSY rather than overwriting. */
    ring.next_slot = 0;
    ring.slot_consumer_busy[0] = 1;
    ring.slot_consumer_busy[1] = 1;
    ring.slot_consumer_busy[2] = 1;
    CHECK(an3_eden_hosted_ring_pick_slot(&ring, &slot) == AN3_EDEN_HOSTED_ERR_BUSY);
    CHECK(an3_eden_hosted_ring_pick_slot(0, &slot) == AN3_EDEN_HOSTED_ERR_ARGUMENT);
    CHECK(an3_eden_hosted_ring_publish_into(0, &frame, 0) == AN3_EDEN_HOSTED_ERR_ARGUMENT);
}

int main(void) {
    test_init_and_empty();
    test_version_and_argument_rejection();
    test_publish_consume_release();
    test_newest_frame_wins_and_drops_older();
    test_producer_never_overwrites_a_owned_slot();
    test_stale_sequence_is_rejected();
    test_pick_slot_then_publish_into();
    printf("hosted_frame: %d checks, %d failures\n", g_checks, g_failures);
    return g_failures == 0 ? 0 : 1;
}
