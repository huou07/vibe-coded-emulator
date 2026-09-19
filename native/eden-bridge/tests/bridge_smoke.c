/*
 * SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Standalone smoke test for the Eden bridge C ABI. Runs with or without an Eden
 * backend: it validates the ABI, lifecycle, argument handling, error reporting
 * and idempotency. A pass here does NOT mean game emulation works.
 *
 * Agent/CI usage:
 *   bridge_smoke [--json] [--frames N] [content.nro]
 *     --json      emit one machine-readable summary line (AN3CTL_STATUS {...})
 *     --frames N  run exactly N emulated frames after start (deterministic)
 */
#include "an3_eden_bridge.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static int failures = 0;
static int checks = 0;
static int json_mode = 0;
static int frames_requested = 1;
static int seconds_requested = 0;
static int loaded_ok = 0;
static int input_supported = 0;
static int frame_callbacks = 0;
static int frames_run = 0;
static long elapsed_ms = 0;
static const char* result_mode = "error-path";

static long now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long)ts.tv_sec * 1000L + (long)(ts.tv_nsec / 1000000L);
}

#define CHECK(cond, message)                                    \
    do {                                                        \
        checks++;                                               \
        if (!(cond)) {                                          \
            failures++;                                         \
            fprintf(stderr, "FAIL: %s (%s:%d)\n", message, __FILE__, __LINE__); \
        }                                                       \
    } while (0)

/* One line, stable key order, no spaces inside values. */
static void emit_summary(void) {
    if (json_mode) {
        printf("AN3CTL_STATUS {\"target\":\"switch\",\"backend\":\"%s\",\"mode\":\"%s\","
               "\"loaded\":%s,\"framesRequested\":%d,\"framesRun\":%d,\"frameCallbacks\":%d,"
               "\"inputSupported\":%s,\"elapsedMs\":%ld,\"checks\":%d,\"failures\":%d,\"result\":\"%s\"}\n",
               an3_eden_backend_name(), result_mode, loaded_ok ? "true" : "false",
               frames_requested, frames_run, frame_callbacks, input_supported ? "true" : "false", elapsed_ms, checks, failures,
               failures == 0 ? "PASS" : "FAIL");
    }
}

static void frames_seen(const an3_eden_frame* frame, void* user_data) {
    (void)frame;
    int* count = (int*)user_data;
    if (count != NULL) {
        (*count)++;
    }
}

int main(int argc, char** argv) {
    /* Optional flags: --json, --frames N. The first non-flag argument is a
     * legal homebrew NRO (for example nx-hbmenu) to drive the happy path;
     * without it the test uses a path that cannot load. */
    const char* content_path = "/nonexistent/an3-smoke.nro";
    for (int index = 1; index < argc; index++) {
        if (strcmp(argv[index], "--json") == 0) { json_mode = 1; continue; }
        if (strcmp(argv[index], "--frames") == 0 && index + 1 < argc) {
            frames_requested = atoi(argv[++index]);
            if (frames_requested < 1) frames_requested = 1;
            continue;
        }
        if (strcmp(argv[index], "--seconds") == 0 && index + 1 < argc) {
            seconds_requested = atoi(argv[++index]);
            if (seconds_requested < 1) seconds_requested = 1;
            continue;
        }
        content_path = argv[index];
    }

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
    CHECK(an3_eden_submit_analog(NULL, 0, 0, 0, 0) == AN3_EDEN_ERR_INVALID_HANDLE, "submit_analog(NULL) is rejected");
    CHECK(an3_eden_get_button(NULL, 0, 0, NULL) == AN3_EDEN_ERR_INVALID_HANDLE, "get_button(NULL) is rejected");
    CHECK(an3_eden_get_analog(NULL, 0, 0, NULL, NULL) == AN3_EDEN_ERR_INVALID_HANDLE, "get_analog(NULL) is rejected");
    CHECK(an3_eden_save_data(NULL, "x") == AN3_EDEN_ERR_INVALID_HANDLE, "save_data(NULL) is rejected");
    char scratch[8] = {0};
    CHECK(an3_eden_get_save_dir(NULL, scratch, sizeof(scratch)) == AN3_EDEN_ERR_INVALID_HANDLE,
          "get_save_dir(NULL) is rejected");
    an3_eden_audio_info audio_probe;
    CHECK(an3_eden_get_audio_info(NULL, &audio_probe) == AN3_EDEN_ERR_INVALID_HANDLE,
          "get_audio_info(NULL) is rejected");
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
        result_mode = "unavailable";
        emit_summary();
        printf("an3-eden-bridge smoke: %d checks, %d failures (backend unavailable; lifecycle verified)\n",
               checks, failures);
        return failures == 0 ? 0 : 1;
    }

    /* Eden backend is present: exercise the full happy path with a path that
     * may or may not exist. An IO error here is acceptable and must surface. */
    CHECK(an3_eden_initialize(core, NULL, NULL) == AN3_EDEN_ERR_ALREADY_INITIALIZED,
          "second initialize is rejected");
    an3_eden_status load = an3_eden_load(core, content_path);
    if (load != AN3_EDEN_OK) {
        printf("an3-eden-bridge load(%s) -> %s (%s)\n", content_path,
               an3_eden_status_message(load), an3_eden_last_error(core));
    }
    CHECK(load == AN3_EDEN_OK || load == AN3_EDEN_ERR_IO || load == AN3_EDEN_ERR_UNSUPPORTED ||
              load == AN3_EDEN_ERR_KEYS_REQUIRED || load == AN3_EDEN_ERR_UNAVAILABLE,
          "load reports a defined status");
    if (load == AN3_EDEN_OK) {
        loaded_ok = 1;
        result_mode = "loaded";
        printf("an3-eden-bridge loaded %s\n", content_path);
        CHECK(an3_eden_start(core) == AN3_EDEN_OK, "start succeeds after load");
        CHECK(an3_eden_pause(core, 1) == AN3_EDEN_OK, "pause succeeds while started");
        CHECK(an3_eden_pause(core, 0) == AN3_EDEN_OK, "resume succeeds while started");
        /* Deterministic frame stepping: run exactly N frames and count callback
         * deliveries. The callback count stays 0 until frame readback lands, so
         * the assertion is on the run_frame status, not the pixel path. */
        int seen = 0;
        int frame_errors = 0;
        const long start_ms = now_ms();
        if (seconds_requested > 0) {
            /* Sustained-duration mode: keep emulating until the deadline. */
            const long deadline = start_ms + (long)seconds_requested * 1000L;
            while (now_ms() < deadline) {
                if (an3_eden_run_frame(core, frames_seen, &seen) != AN3_EDEN_OK) frame_errors++;
                frames_run++;
            }
        } else {
            for (int frame = 0; frame < frames_requested; frame++) {
                if (an3_eden_run_frame(core, frames_seen, &seen) != AN3_EDEN_OK) frame_errors++;
                frames_run++;
            }
        }
        elapsed_ms = now_ms() - start_ms;
        frame_callbacks = seen;
        CHECK(frame_errors == 0, "every run_frame in the bounded loop returns OK");
        printf("an3-eden-bridge run_frame: requested=%d seconds=%d framesRun=%d frameCallbacks=%d elapsed=%ldms\n",
               frames_requested, seconds_requested, frames_run, seen, elapsed_ms);
        /* Input and save bridges: the ABI must report a defined status and
         * never fake success. When input is supported, prove the emulated
         * controller state actually changed (not just that the call returned). */
        an3_eden_status button = an3_eden_submit_button(core, 0, AN3_EDEN_BUTTON_A, 1);
        CHECK(button == AN3_EDEN_OK || button == AN3_EDEN_ERR_UNSUPPORTED ||
                  button == AN3_EDEN_ERR_UNAVAILABLE,
              "submit_button succeeds or reports UNSUPPORTED");
        if (button == AN3_EDEN_OK) {
            input_supported = 1;
            int pressed = -1;
            CHECK(an3_eden_get_button(core, 0, AN3_EDEN_BUTTON_A, &pressed) == AN3_EDEN_OK,
                  "get_button succeeds when input is supported");
            CHECK(pressed == 1, "Eden's controller sees button A pressed");
            CHECK(an3_eden_submit_button(core, 0, AN3_EDEN_BUTTON_A, 0) == AN3_EDEN_OK,
                  "release succeeds");
            CHECK(an3_eden_get_button(core, 0, AN3_EDEN_BUTTON_A, &pressed) == AN3_EDEN_OK,
                  "get_button succeeds after release");
            CHECK(pressed == 0, "Eden's controller sees button A released");

            int16_t ax = 0;
            int16_t ay = 0;
            CHECK(an3_eden_submit_analog(core, 0, AN3_EDEN_STICK_LEFT, 16384, -16384) == AN3_EDEN_OK,
                  "left stick move succeeds");
            CHECK(an3_eden_get_analog(core, 0, AN3_EDEN_STICK_LEFT, &ax, &ay) == AN3_EDEN_OK,
                  "get_analog succeeds");
            CHECK(ax > 15000 && ax < 18000, "Eden sees left stick x");
            CHECK(ay < -15000 && ay > -18000, "Eden sees left stick y");
            CHECK(an3_eden_submit_analog(core, 0, AN3_EDEN_STICK_LEFT, 0, 0) == AN3_EDEN_OK,
                  "left stick reset succeeds");
            CHECK(an3_eden_get_analog(core, 0, AN3_EDEN_STICK_LEFT, &ax, &ay) == AN3_EDEN_OK,
                  "get_analog succeeds after reset");
            CHECK(ax == 0 && ay == 0, "Eden sees left stick neutral after reset");

            CHECK(an3_eden_submit_analog(core, 0, AN3_EDEN_STICK_RIGHT, -32768, 32767) == AN3_EDEN_OK,
                  "right stick move succeeds");
            CHECK(an3_eden_get_analog(core, 0, AN3_EDEN_STICK_RIGHT, &ax, &ay) == AN3_EDEN_OK,
                  "get_analog right succeeds");
            if (!json_mode) {
                printf("an3-eden-bridge input: right stick read back %d,%d\n", (int)ax, (int)ay);
            }
            /* A full-scale diagonal is normalized by Eden's circular gate, so
             * the magnitude stays 1.0 while each axis is ~0.7071 (-23169). */
            CHECK(ax < -20000 && ax >= -32768, "Eden sees right stick clamped x");
            CHECK(ay > 20000 && ay <= 32767, "Eden sees right stick clamped y");
            CHECK(an3_eden_submit_analog(core, 0, AN3_EDEN_STICK_RIGHT, 0, 0) == AN3_EDEN_OK,
                  "right stick reset succeeds");
        }
        CHECK(an3_eden_submit_analog(core, 0, 99, 0, 0) == AN3_EDEN_ERR_INVALID_ARGUMENT,
              "invalid stick id is rejected");
        CHECK(an3_eden_get_analog(core, 0, AN3_EDEN_STICK_LEFT, NULL, NULL) ==
                  AN3_EDEN_ERR_INVALID_ARGUMENT,
              "get_analog with NULL outputs is rejected");
        CHECK(an3_eden_submit_button(core, 99, AN3_EDEN_BUTTON_A, 1) == AN3_EDEN_ERR_INVALID_ARGUMENT,
              "invalid port is rejected");
        CHECK(an3_eden_submit_button(core, 0, 99, 1) == AN3_EDEN_ERR_INVALID_ARGUMENT,
              "invalid button is rejected");

        /* Saves: query the save location and export the user save tree. */
        char save_dir[1024] = {0};
        an3_eden_status save_location =
            an3_eden_get_save_dir(core, save_dir, (uint32_t)sizeof(save_dir));
        CHECK(save_location == AN3_EDEN_OK || save_location == AN3_EDEN_ERR_UNSUPPORTED,
              "get_save_dir reports a defined status");
        if (save_location == AN3_EDEN_OK) {
            CHECK(save_dir[0] != '\0', "save directory is not empty");
            if (!json_mode) {
                printf("an3-eden-bridge save dir: %s\n", save_dir);
            }
            an3_eden_status export_status = an3_eden_save_data(
                core, "/tmp/an3-eden-save-export");
            CHECK(export_status == AN3_EDEN_OK, "save export succeeds");
        }
        CHECK(an3_eden_get_save_dir(core, NULL, 16) == AN3_EDEN_ERR_INVALID_ARGUMENT,
              "get_save_dir with a NULL buffer is rejected");
        CHECK(an3_eden_save_data(core, NULL) == AN3_EDEN_ERR_INVALID_ARGUMENT,
              "save_data with a NULL path is rejected");

        /* Audio: Eden owns output directly; report the sink it selected. */
        an3_eden_audio_info audio;
        an3_eden_status audio_status = an3_eden_get_audio_info(core, &audio);
        CHECK(audio_status == AN3_EDEN_OK || audio_status == AN3_EDEN_ERR_UNSUPPORTED,
              "get_audio_info reports a defined status");
        if (audio_status == AN3_EDEN_OK) {
            CHECK(audio.backend[0] != '\0', "audio backend is reported");
            CHECK(audio.channels > 0, "audio device reports channels");
            if (!json_mode) {
                printf("an3-eden-bridge audio: backend=%s device=%s channels=%u volume=%.3f\n",
                       audio.backend, audio.device, audio.channels, (double)audio.volume);
            }
        }
        CHECK(an3_eden_get_audio_info(core, NULL) == AN3_EDEN_ERR_INVALID_ARGUMENT,
              "get_audio_info with a NULL output is rejected");
        CHECK(an3_eden_stop(core) == AN3_EDEN_OK, "stop succeeds");
        CHECK(an3_eden_stop(core) == AN3_EDEN_OK, "stop is idempotent");
    }

    /* Repeated shutdown and destroy must not crash. */
    CHECK(an3_eden_shutdown(core) == AN3_EDEN_OK, "shutdown succeeds");
    CHECK(an3_eden_shutdown(core) == AN3_EDEN_OK, "repeated shutdown is idempotent");
    an3_eden_destroy(core);

    emit_summary();
    printf("an3-eden-bridge smoke: %d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
