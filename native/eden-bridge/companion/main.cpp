/*
 * SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * an3_switch_companion — the separate-process Nintendo Switch companion.
 *
 * It embeds the Eden bridge (the companion is the GPL component; AN3 launches
 * it rather than linking Eden) and owns its own presentation window, input and
 * lifecycle. AN3 controls it by launching it with a content path and reading
 * its AN3CTL_STATUS lines.
 *
 * Usage:
 *   an3_switch_companion <content.nro> [--visible] [--seconds N] [--frames N]
 *                        [--no-stdin] [--status-every N]
 *
 * Keyboard (--visible): A/S→Y/X, Z/X→B/A, Q/W→L/R, E/R→ZL/ZR,
 *   Return→Plus, Delete→Minus, arrows→d-pad, Space→A.
 * Stdin (automation): `button <name> <down|up>`, `analog <L|R> <x> <y>`,
 *   `status`, `quit`.
 */
#include "an3_eden_bridge.h"

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>

#if defined(__APPLE__)
#include "cocoa_surface.h"
#elif !defined(__ANDROID__)
#include "desktop_surface.h"
#include <SDL3/SDL_scancode.h>
#endif

namespace {

std::atomic<bool> g_quit{false};
std::atomic<bool> g_running{false};
std::atomic<bool> g_ready{false};
std::atomic<unsigned long long> g_frames{0};
an3_eden_core* g_core = nullptr;
int g_status_every = 0;

/* Eden's pinned revision can deadlock in ShutdownMainProcess() when the
 * process is torn down before its GPU has settled (~1s after start). Lifecycle
 * commands therefore wait briefly for readiness first; AN3 additionally kills
 * the companion on timeout, so a stuck init can never hang the app. */
constexpr int kReadySettleMs = 1200;

void request_quit(void) {
    for (int waited = 0; waited < kReadySettleMs && !g_ready.load(); waited += 50) {
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
    g_quit.store(true);
}

void on_signal(int) {
    g_quit.store(true);
}

void request_visible_window(void) {
#if defined(_WIN32)
    (void)_putenv_s("AN3_EDEN_WINDOW_VISIBLE", "1");
#else
    (void)setenv("AN3_EDEN_WINDOW_VISIBLE", "1", 1);
#endif
}

int should_stop(void) {
    return g_quit.load() ? 1 : 0;
}

/* Platform key codes -> AN3 button ids (or -1). */
int key_to_button(int key_code) {
#if defined(__APPLE__)
    switch (key_code) {
        case 0: return AN3_EDEN_BUTTON_Y;      /* A */
        case 1: return AN3_EDEN_BUTTON_X;      /* S */
        case 6: return AN3_EDEN_BUTTON_B;      /* Z */
        case 7: return AN3_EDEN_BUTTON_A;      /* X */
        case 12: return AN3_EDEN_BUTTON_L;     /* Q */
        case 13: return AN3_EDEN_BUTTON_R;     /* W */
        case 14: return AN3_EDEN_BUTTON_L2;    /* E -> ZL */
        case 15: return AN3_EDEN_BUTTON_R2;    /* R -> ZR */
        case 36: return AN3_EDEN_BUTTON_START; /* Return -> Plus */
        case 49: return AN3_EDEN_BUTTON_A;     /* Space */
        case 51: return AN3_EDEN_BUTTON_SELECT;/* Delete -> Minus */
        case 123: return AN3_EDEN_BUTTON_LEFT;
        case 124: return AN3_EDEN_BUTTON_RIGHT;
        case 125: return AN3_EDEN_BUTTON_DOWN;
        case 126: return AN3_EDEN_BUTTON_UP;
        default: return -1;
    }
#else
    switch (key_code) {
        case SDL_SCANCODE_A: return AN3_EDEN_BUTTON_Y;
        case SDL_SCANCODE_S: return AN3_EDEN_BUTTON_X;
        case SDL_SCANCODE_Z: return AN3_EDEN_BUTTON_B;
        case SDL_SCANCODE_X: return AN3_EDEN_BUTTON_A;
        case SDL_SCANCODE_Q: return AN3_EDEN_BUTTON_L;
        case SDL_SCANCODE_W: return AN3_EDEN_BUTTON_R;
        case SDL_SCANCODE_E: return AN3_EDEN_BUTTON_L2;
        case SDL_SCANCODE_R: return AN3_EDEN_BUTTON_R2;
        case SDL_SCANCODE_RETURN: return AN3_EDEN_BUTTON_START;
        case SDL_SCANCODE_SPACE: return AN3_EDEN_BUTTON_A;
        case SDL_SCANCODE_DELETE: return AN3_EDEN_BUTTON_SELECT;
        case SDL_SCANCODE_LEFT: return AN3_EDEN_BUTTON_LEFT;
        case SDL_SCANCODE_RIGHT: return AN3_EDEN_BUTTON_RIGHT;
        case SDL_SCANCODE_DOWN: return AN3_EDEN_BUTTON_DOWN;
        case SDL_SCANCODE_UP: return AN3_EDEN_BUTTON_UP;
        default: return -1;
    }
#endif
}

void key_handler(int key_code, int is_down) {
    const int button = key_to_button(key_code);
    if (button >= 0 && g_core != nullptr) {
        an3_eden_submit_button(g_core, 0, static_cast<uint32_t>(button), is_down);
    }
}

void emit_status(const char* mode, const char* result) {
    std::printf(
        "\nAN3CTL_STATUS {\"target\":\"switch\",\"backend\":\"%s\",\"mode\":\"%s\","
        "\"frames\":%llu,\"result\":\"%s\"}\n",
        an3_eden_backend_name(), mode, g_frames.load(), result);
    std::fflush(stdout);
}

/* Eden owns audio output directly; report the sink it selected. This is
 * introspection, not a claim that audible sound was produced. */
void emit_audio(void) {
    an3_eden_audio_info info;
    if (g_core == nullptr || an3_eden_get_audio_info(g_core, &info) != AN3_EDEN_OK) {
        std::printf("\nAN3CTL_AUDIO {\"available\":false}\n");
    } else {
        std::printf(
            "\nAN3CTL_AUDIO {\"available\":true,\"backend\":\"%s\",\"device\":\"%s\","
            "\"channels\":%u,\"volume\":%.3f}\n",
            info.backend, info.device, info.channels, static_cast<double>(info.volume));
    }
    std::fflush(stdout);
}

int button_from_name(const std::string& name) {
    if (name == "A") return AN3_EDEN_BUTTON_A;
    if (name == "B") return AN3_EDEN_BUTTON_B;
    if (name == "X") return AN3_EDEN_BUTTON_X;
    if (name == "Y") return AN3_EDEN_BUTTON_Y;
    if (name == "L") return AN3_EDEN_BUTTON_L;
    if (name == "R") return AN3_EDEN_BUTTON_R;
    if (name == "ZL") return AN3_EDEN_BUTTON_L2;
    if (name == "ZR") return AN3_EDEN_BUTTON_R2;
    if (name == "PLUS" || name == "START") return AN3_EDEN_BUTTON_START;
    if (name == "MINUS" || name == "SELECT") return AN3_EDEN_BUTTON_SELECT;
    if (name == "UP") return AN3_EDEN_BUTTON_UP;
    if (name == "DOWN") return AN3_EDEN_BUTTON_DOWN;
    if (name == "LEFT") return AN3_EDEN_BUTTON_LEFT;
    if (name == "RIGHT") return AN3_EDEN_BUTTON_RIGHT;
    if (name == "LS") return AN3_EDEN_BUTTON_L3;
    if (name == "RS") return AN3_EDEN_BUTTON_R3;
    return -1;
}

void frame_loop(void) {
    const auto started = std::chrono::steady_clock::now();
    while (!g_quit.load()) {
        if (an3_eden_run_frame(g_core, nullptr, nullptr) != AN3_EDEN_OK) {
            break;
        }
        const unsigned long long frames = g_frames.fetch_add(1) + 1;
        if (std::chrono::steady_clock::now() - started >=
            std::chrono::milliseconds(kReadySettleMs)) {
            g_ready.store(true);
        }
        if (g_status_every > 0 && frames % static_cast<unsigned long long>(g_status_every) == 0) {
            emit_status("running", "PASS");
        }
    }
    g_running.store(false);
}

/* Automation channel: one command per line. */
void command_loop(void) {
    char line[256];
    while (!g_quit.load() && std::fgets(line, sizeof(line), stdin) != nullptr) {
        char verb[32] = {0};
        char arg1[32] = {0};
        char arg2[32] = {0};
        const int fields = std::sscanf(line, "%31s %31s %31s", verb, arg1, arg2);
        if (fields < 1) {
            continue;
        }
        if (std::strcmp(verb, "quit") == 0 || std::strcmp(verb, "stop") == 0) {
            request_quit();
            break;
        }
        if (std::strcmp(verb, "status") == 0) {
            /* Exactly one terminal line per command keeps the app's
             * request/reply control channel aligned. */
            emit_status("running", "PASS");
            continue;
        }
        if (std::strcmp(verb, "audio") == 0) {
            emit_audio();
            continue;
        }
        if (std::strcmp(verb, "focus") == 0) {
#if defined(__APPLE__)
            an3_eden_cocoa_focus();
#elif !defined(__ANDROID__)
            an3_eden_desktop_focus();
#endif
            std::printf("\nAN3CTL_ACK {\"focus\":true}\n");
            std::fflush(stdout);
            continue;
        }
        if (std::strcmp(verb, "button") == 0 && fields >= 3) {
            const int button = button_from_name(arg1);
            if (button < 0) {
                std::printf("AN3CTL_ERROR {\"code\":\"E_BUTTON\",\"message\":\"unknown button\"}\n");
            } else {
                const int down = std::strcmp(arg2, "down") == 0 ? 1 : 0;
                an3_eden_submit_button(g_core, 0, static_cast<uint32_t>(button), down);
                std::printf("\nAN3CTL_ACK {\"button\":\"%s\",\"state\":\"%s\"}\n", arg1, down ? "down" : "up");
            }
            std::fflush(stdout);
            continue;
        }
        if (std::strcmp(verb, "analog") == 0 && fields >= 3) {
            const uint32_t stick = (arg1[0] == 'R' || arg1[0] == 'r') ? AN3_EDEN_STICK_RIGHT
                                                                      : AN3_EDEN_STICK_LEFT;
            float x = 0.0f;
            float y = 0.0f;
            if (std::sscanf(line + (std::strstr(line, arg1) - line) + std::strlen(arg1), "%f %f", &x,
                            &y) == 2) {
                const auto to_i16 = [](float value) {
                    const float clamped = value < -1.0f ? -1.0f : (value > 1.0f ? 1.0f : value);
                    return static_cast<int16_t>(clamped * 32767.0f);
                };
                an3_eden_submit_analog(g_core, 0, stick, to_i16(x), to_i16(y));
                std::printf("\nAN3CTL_ACK {\"analog\":\"%s\",\"x\":%.3f,\"y\":%.3f}\n", arg1, x, y);
            } else {
                std::printf("AN3CTL_ERROR {\"code\":\"E_ANALOG\",\"message\":\"analog needs x y\"}\n");
            }
            std::fflush(stdout);
            continue;
        }
        std::printf("AN3CTL_ERROR {\"code\":\"E_USAGE\",\"message\":\"unknown command\"}\n");
        std::fflush(stdout);
    }
}

}  // namespace

int main(int argc, char** argv) {
    const char* content = nullptr;
    int seconds = 0;
    int frames = 0;
    int visible = 0;
    int use_stdin = 1;
    for (int index = 1; index < argc; index++) {
        if (std::strcmp(argv[index], "--visible") == 0) { visible = 1; continue; }
        if (std::strcmp(argv[index], "--hidden") == 0) { visible = 0; continue; }
        if (std::strcmp(argv[index], "--no-stdin") == 0) { use_stdin = 0; continue; }
        if (std::strcmp(argv[index], "--seconds") == 0 && index + 1 < argc) { seconds = std::atoi(argv[++index]); continue; }
        if (std::strcmp(argv[index], "--frames") == 0 && index + 1 < argc) { frames = std::atoi(argv[++index]); continue; }
        if (std::strcmp(argv[index], "--status-every") == 0 && index + 1 < argc) { g_status_every = std::atoi(argv[++index]); continue; }
        content = argv[index];
    }
    if (content == nullptr) {
        std::fprintf(stderr, "usage: an3_switch_companion <content.nro> [--visible] [--seconds N] [--frames N] [--no-stdin] [--status-every N]\n");
        return 2;
    }
    if (visible) {
        request_visible_window();
    }

    an3_eden_core* core = nullptr;
    if (an3_eden_create(&core) != AN3_EDEN_OK) {
        emit_status("create-failed", "FAIL");
        return 1;
    }
    g_core = core;

    if (an3_eden_initialize(core, nullptr, nullptr) != AN3_EDEN_OK) {
        std::fprintf(stderr, "an3_switch_companion: initialize failed: %s\n", an3_eden_last_error(core));
        emit_status("unavailable", "FAIL");
        an3_eden_destroy(core);
        return 1;
    }
    if (an3_eden_load(core, content) != AN3_EDEN_OK) {
        std::fprintf(stderr, "an3_switch_companion: load failed: %s\n", an3_eden_last_error(core));
        emit_status("load-failed", "FAIL");
        an3_eden_shutdown(core);
        an3_eden_destroy(core);
        return 1;
    }
    if (an3_eden_start(core) != AN3_EDEN_OK) {
        std::fprintf(stderr, "an3_switch_companion: start failed: %s\n", an3_eden_last_error(core));
        emit_status("start-failed", "FAIL");
        an3_eden_shutdown(core);
        an3_eden_destroy(core);
        return 1;
    }

    std::signal(SIGINT, on_signal);
    std::signal(SIGTERM, on_signal);

#if defined(__APPLE__)
    an3_eden_cocoa_set_key_handler(key_handler);
#elif !defined(__ANDROID__)
    an3_eden_desktop_set_key_handler(key_handler);
#endif

    g_running.store(true);
    std::thread frames_thread(frame_loop);
    std::thread commands_thread;
    if (use_stdin) {
        commands_thread = std::thread(command_loop);
    }

    emit_status("running", "PASS");

    if (frames > 0) {
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(0);
        (void)deadline;
        while (g_frames.load() < static_cast<unsigned long long>(frames) && !g_quit.load()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(2));
        }
        request_quit();
    } else if (seconds > 0) {
        std::thread watchdog([seconds] {
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(seconds);
            while (!g_quit.load() && std::chrono::steady_clock::now() < deadline) {
                std::this_thread::sleep_for(std::chrono::milliseconds(50));
            }
            request_quit();
        });
        watchdog.detach();
    }

    if (visible) {
#if defined(__APPLE__)
        an3_eden_cocoa_run(should_stop);
#elif !defined(__ANDROID__)
        an3_eden_desktop_run(should_stop);
        g_quit.store(true);
#else
        while (!g_quit.load()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }
#endif
    } else {
        while (!g_quit.load()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
        }
    }

    g_quit.store(true);
    if (commands_thread.joinable()) {
        commands_thread.join();
    }
    if (frames_thread.joinable()) {
        frames_thread.join();
    }

    an3_eden_stop(core);
    emit_status("stopped", "PASS");
    an3_eden_shutdown(core);
    an3_eden_destroy(core);
    g_core = nullptr;
    return 0;
}
