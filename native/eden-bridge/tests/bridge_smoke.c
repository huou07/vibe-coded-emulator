/*
 * SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Standalone smoke test for the Eden bridge C ABI. Runs with or without an Eden
 * backend: it validates the ABI, lifecycle, argument handling, error reporting
 * and idempotency. A pass here does NOT mean game emulation works.
 */
#include "an3_eden_bridge.h"

#include <stdio.h>
#include <string.h>

static int failures = 0;
static int checks = 0;

#define CHECK(cond, message)                                    \
    do {                                                        \
        checks++;                                               \
        if (!(cond)) {                                          \
            failures++;                                         \
            fprintf(stderr, "FAIL: %s (%s:%d)\n", message, __FILE__, __LINE__); \
        }                                                       \
    } while (0)

static void frames_seen(const an3_eden_frame* frame, void* user_data) {
    (void)frame;
    int* count = (int*)user_data;
    if (count != NULL) {
        (*count)++;
    }
}

int main(void) {
    /* ABI identity */
    CHECK(an3_eden_bridge_abi_version() == AN3_EDEN_BRIDGE_ABI_VERSION, "abi version matches the header");
    CHECK(an3_eden_backend_name() != NULL, "backend name is never NULL");
    printf("an3-eden-bridge abi=%u backend=%s\n", an3_eden_bridge_abi_version(), an3_eden_backend_name());

    /* Every status has a message. */
    for (int status = 0; status <= AN3_EDEN_ERR_KEYS_REQUIRED; status++) {
        const char* message = an3_eden_status_message((an3_eden_status)status);
        CHECK(message != NULL && message[0] != '\0', "status has a message");
    }

    /* Argument and handle validation. */
    CHECK(an3_eden_create(NULL) == AN3_EDEN_ERR_INVALID_ARGUMENT, "create(NULL) is rejected");
    CHECK(an3_eden_initialize(NULL, NULL, NULL) == AN3_EDEN_ERR_INVALID_HANDLE, "initialize(NULL) is rejected");
    CHECK(an3_eden_load(NULL, "x") == AN3_EDEN_ERR_INVALID_HANDLE, "load(NULL) is rejected");
    CHECK(an3_eden_start(NULL) == AN3_EDEN_ERR_INVALID_HANDLE, "start(NULL) is rejected");
    CHECK(an3_eden_pause(NULL, 1) == AN3_EDEN_ERR_INVALID_HANDLE, "pause(NULL) is rejected");
    CHECK(an3_eden_run_frame(NULL, NULL, NULL) == AN3_EDEN_ERR_INVALID_HANDLE, "run_frame(NULL) is rejected");
    CHECK(an3_eden_submit_button(NULL, 0, 0, 1) == AN3_EDEN_ERR_INVALID_HANDLE, "submit_button(NULL) is rejected");
    CHECK(an3_eden_submit_analog(NULL, 0, 0, 0) == AN3_EDEN_ERR_INVALID_HANDLE, "submit_analog(NULL) is rejected");
    CHECK(an3_eden_save_data(NULL, "x") == AN3_EDEN_ERR_INVALID_HANDLE, "save_data(NULL) is rejected");
    CHECK(an3_eden_stop(NULL) == AN3_EDEN_ERR_INVALID_HANDLE, "stop(NULL) is rejected");
    CHECK(an3_eden_shutdown(NULL) == AN3_EDEN_ERR_INVALID_HANDLE, "shutdown(NULL) is rejected");
    CHECK(strcmp(an3_eden_last_error(NULL), "") == 0, "last_error(NULL) is empty, not a crash");
    an3_eden_destroy(NULL); /* must be a no-op */

    /* Create, then use-before-initialise is rejected. */
    an3_eden_core* core = NULL;
    CHECK(an3_eden_create(&core) == AN3_EDEN_OK, "create succeeds");
    CHECK(core != NULL, "handle is returned");
    CHECK(an3_eden_load(core, NULL) == AN3_EDEN_ERR_INVALID_ARGUMENT, "load(core, NULL) is rejected");
    CHECK(an3_eden_start(core) == AN3_EDEN_ERR_NOT_INITIALIZED, "start before initialize is rejected");
    CHECK(an3_eden_pause(core, 1) == AN3_EDEN_ERR_NOT_INITIALIZED, "pause before initialize is rejected");
    CHECK(an3_eden_run_frame(core, frames_seen, NULL) == AN3_EDEN_ERR_NOT_INITIALIZED,
          "run_frame before initialize is rejected");
    CHECK(an3_eden_submit_button(core, 0, AN3_EDEN_BUTTON_A, 1) == AN3_EDEN_ERR_NOT_INITIALIZED,
          "submit_button before initialize is rejected");
    CHECK(an3_eden_stop(core) == AN3_EDEN_OK, "stop before start is idempotent");
    CHECK(an3_eden_shutdown(core) == AN3_EDEN_OK, "shutdown before initialize is idempotent");

    /* Initialise. With the null backend this is UNAVAILABLE; with Eden it may
     * also be UNAVAILABLE when the host has no usable Vulkan device. Both are
     * handled the same way so the smoke test passes in either build. */
    an3_eden_status init = an3_eden_initialize(core, NULL, NULL);
    CHECK(init == AN3_EDEN_OK || init == AN3_EDEN_ERR_UNAVAILABLE,
          "initialize either succeeds or reports UNAVAILABLE");
    if (init == AN3_EDEN_ERR_UNAVAILABLE) {
        CHECK(an3_eden_last_error(core)[0] != '\0', "UNAVAILABLE carries a diagnostic");
        CHECK(an3_eden_initialize(core, NULL, NULL) == AN3_EDEN_ERR_UNAVAILABLE,
              "re-initialise after failure is still UNAVAILABLE");
        CHECK(an3_eden_shutdown(core) == AN3_EDEN_OK, "shutdown after a failed initialise succeeds");
        an3_eden_destroy(core);
        printf("an3-eden-bridge smoke: %d checks, %d failures (backend unavailable; lifecycle verified)\n",
               checks, failures);
        return failures == 0 ? 0 : 1;
    }

    /* Eden backend is present: exercise the full happy path with a path that
     * may or may not exist. An IO error here is acceptable and must surface. */
    CHECK(an3_eden_initialize(core, NULL, NULL) == AN3_EDEN_ERR_ALREADY_INITIALIZED,
          "second initialize is rejected");
    an3_eden_status load = an3_eden_load(core, "/nonexistent/an3-smoke.nro");
    CHECK(load == AN3_EDEN_OK || load == AN3_EDEN_ERR_IO || load == AN3_EDEN_ERR_UNSUPPORTED ||
              load == AN3_EDEN_ERR_KEYS_REQUIRED || load == AN3_EDEN_ERR_UNAVAILABLE,
          "load reports a defined status");
    if (load == AN3_EDEN_OK) {
        CHECK(an3_eden_start(core) == AN3_EDEN_OK, "start succeeds after load");
        CHECK(an3_eden_pause(core, 1) == AN3_EDEN_OK, "pause succeeds while started");
        CHECK(an3_eden_pause(core, 0) == AN3_EDEN_OK, "resume succeeds while started");
        int seen = 0;
        CHECK(an3_eden_run_frame(core, frames_seen, &seen) == AN3_EDEN_OK, "run_frame succeeds");
        CHECK(an3_eden_submit_button(core, 0, AN3_EDEN_BUTTON_A, 1) == AN3_EDEN_OK, "submit_button succeeds");
        CHECK(an3_eden_submit_button(core, 0, AN3_EDEN_BUTTON_A, 0) == AN3_EDEN_OK, "release succeeds");
        CHECK(an3_eden_submit_analog(core, 0, 0, 0) == AN3_EDEN_OK, "submit_analog succeeds");
        CHECK(an3_eden_submit_button(core, 99, AN3_EDEN_BUTTON_A, 1) == AN3_EDEN_ERR_INVALID_ARGUMENT,
              "invalid port is rejected");
        CHECK(an3_eden_submit_button(core, 0, 99, 1) == AN3_EDEN_ERR_INVALID_ARGUMENT,
              "invalid button is rejected");
        CHECK(an3_eden_stop(core) == AN3_EDEN_OK, "stop succeeds");
        CHECK(an3_eden_stop(core) == AN3_EDEN_OK, "stop is idempotent");
    }

    /* Repeated shutdown and destroy must not crash. */
    CHECK(an3_eden_shutdown(core) == AN3_EDEN_OK, "shutdown succeeds");
    CHECK(an3_eden_shutdown(core) == AN3_EDEN_OK, "repeated shutdown is idempotent");
    an3_eden_destroy(core);

    printf("an3-eden-bridge smoke: %d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
