// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#include "../native-runtime/core/vendor/libretro.h"

#include <cassert>
#include <cstdio>
#include <dlfcn.h>

namespace {
retro_netpacket_callback captured{};

bool RETRO_CALLCONV environment(unsigned command, void* data) {
    if (command != RETRO_ENVIRONMENT_SET_NETPACKET_INTERFACE) return false;
    if (!data) return false;
    captured = *static_cast<const retro_netpacket_callback*>(data);
    return true;
}
}

int main(int argc, char** argv) {
    assert(argc == 2);
    void* library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    assert(library);
    using set_environment_t = void (*)(retro_environment_t);
    using lifecycle_t = void (*)();
    auto set_environment = reinterpret_cast<set_environment_t>(dlsym(library, "retro_set_environment"));
    auto init = reinterpret_cast<lifecycle_t>(dlsym(library, "retro_init"));
    auto deinit = reinterpret_cast<lifecycle_t>(dlsym(library, "retro_deinit"));
    assert(set_environment && init && deinit);
    set_environment(environment);
    init();
    assert(captured.start && captured.receive);
    std::printf("melonDS netpacket callback exposed protocol=%s\n", captured.protocol_version ? captured.protocol_version : "core-version");
    deinit();
    dlclose(library);
    return 0;
}
