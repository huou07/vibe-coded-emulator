// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Development probe: loads a libretro core, captures the core-option metadata it
// announces (retro_init for mGBA/Azahar; no-game load for melonDS DS), and
// prints JSON. It never constructs a renderer or audio backend, so generating
// the committed core-option registry requires no game session.
//
// Build and run through scripts/generate-core-option-registry.mjs; the output is
// reviewed and committed as shared/core-option-registry.json.
#include "core_options.h"
#include "vendor/libretro.h"

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#if defined(_WIN32)
#include <windows.h>
#else
#include <dlfcn.h>
#endif

using namespace an3;

namespace {
CoreOptionsRegistry* g_registry = nullptr;
std::string g_save = ".";
std::string g_system = ".";
std::string g_content = ".";
std::string g_core = "";

std::string quote(const std::string& text) {
    std::string out = "\"";
    for (unsigned char c : text) {
        switch (c) {
        case '"': out += "\\\""; break;
        case '\\': out += "\\\\"; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        case '\t': out += "\\t"; break;
        default:
            if (c < 0x20) {
                char buffer[8];
                std::snprintf(buffer, sizeof(buffer), "\\u%04x", c);
                out += buffer;
            } else {
                out += static_cast<char>(c);
            }
        }
    }
    return out + "\"";
}

bool environment(unsigned command, void* data) {
    switch (command) {
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY: if (!data) return false; *static_cast<const char**>(data) = g_system.c_str(); return true;
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY: if (!data) return false; *static_cast<const char**>(data) = g_save.c_str(); return true;
    case RETRO_ENVIRONMENT_GET_CONTENT_DIRECTORY: if (!data) return false; *static_cast<const char**>(data) = g_content.c_str(); return true;
    case RETRO_ENVIRONMENT_GET_LIBRETRO_PATH: if (!data) return false; *static_cast<const char**>(data) = g_core.c_str(); return true;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT: return true;
    case RETRO_ENVIRONMENT_GET_VARIABLE: {
        auto* variable = static_cast<retro_variable*>(data);
        if (!variable || !variable->key) return false;
        return g_registry->get(variable->key, variable->value);
    }
    case RETRO_ENVIRONMENT_SET_VARIABLES: {
        auto* vars = static_cast<retro_variable*>(data);
        if (!vars) return false;
        std::vector<const char*> pairs;
        for (; vars->key; ++vars) { pairs.push_back(vars->key); pairs.push_back(vars->value); }
        pairs.push_back(nullptr);
        g_registry->capture_legacy_variables(pairs.data());
        return true;
    }
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS:
        g_registry->capture_legacy(reinterpret_cast<const RetroCoreOptionDefinition*>(data));
        return true;
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_INTL: {
        auto* intl = reinterpret_cast<const retro_core_options_intl*>(data);
        if (intl) g_registry->capture_legacy(reinterpret_cast<const RetroCoreOptionDefinition*>(intl->us ? intl->us : intl->local));
        return true;
    }
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2:
        g_registry->capture_v2(reinterpret_cast<const RetroCoreOptionsV2*>(data));
        return true;
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2_INTL: {
        auto* intl = reinterpret_cast<const RetroCoreOptionsIntl*>(data);
        if (intl) g_registry->capture_v2(intl->us ? intl->us : intl->local);
        return true;
    }
    case RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION: *static_cast<unsigned*>(data) = 2; return true;
    case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE: *static_cast<bool*>(data) = false; return true;
    case RETRO_ENVIRONMENT_GET_CAN_DUPE: if (!data) return false; *static_cast<bool*>(data) = true; return true;
    case RETRO_ENVIRONMENT_GET_INPUT_BITMASKS: return true;
    case RETRO_ENVIRONMENT_GET_LOG_INTERFACE: return true;
    case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
    case RETRO_ENVIRONMENT_SET_CONTROLLER_INFO:
    case RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME:
    case RETRO_ENVIRONMENT_SET_SERIALIZATION_QUIRKS: return true;
    default: return false;
    }
}

std::string dump() {
    std::string json = "[";
    bool first = true;
    for (const auto& option : g_registry->options()) {
        if (!first) json += ",";
        first = false;
        json += "{\"key\":" + quote(option.key) + ",\"label\":" + quote(option.display_label) +
                ",\"description\":" + quote(option.description) + ",\"category\":" + quote(option.category) +
                ",\"default\":" + quote(option.default_value) + ",\"values\":[";
        bool firstValue = true;
        for (const auto& value : option.values) {
            if (!firstValue) json += ",";
            firstValue = false;
            json += "{\"value\":" + quote(value.value) + ",\"label\":" + quote(value.label) + "}";
        }
        json += "]}";
    }
    return json + "]";
}

void* symbol(void* handle, const char* name) {
#if defined(_WIN32)
    return reinterpret_cast<void*>(GetProcAddress(static_cast<HMODULE>(handle), name));
#else
    return dlsym(handle, name);
#endif
}
} // namespace

int main(int argc, char** argv) {
    const bool no_game = argc >= 4 && std::strcmp(argv[3], "--nogame") == 0;
    if (argc < 3) { std::fprintf(stderr, "usage: core_option_probe <core> <workspace> [--nogame]\n"); return 2; }
    g_save = std::string(argv[2]) + "/save";
    g_system = std::string(argv[2]) + "/system";
    g_content = std::string(argv[2]);
    g_core = argv[1];
    CoreOptionsRegistry registry{std::string(argv[1])};
    g_registry = &registry;
#if defined(_WIN32)
    void* handle = LoadLibraryW(std::wstring(argv[1], argv[1] + std::strlen(argv[1])).c_str());
#else
    void* handle = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
#endif
    if (!handle) { std::fprintf(stderr, "could not load core\n"); return 3; }
    auto set_environment = reinterpret_cast<void (*)(retro_environment_t)>(symbol(handle, "retro_set_environment"));
    auto init = reinterpret_cast<void (*)()>(symbol(handle, "retro_init"));
    auto deinit = reinterpret_cast<void (*)()>(symbol(handle, "retro_deinit"));
    auto get_info = reinterpret_cast<void (*)(retro_system_info*)>(symbol(handle, "retro_get_system_info"));
    if (!set_environment || !init || !deinit) { std::fprintf(stderr, "missing libretro entry points\n"); return 4; }
    set_environment(&environment);
    init();
    retro_system_info info{};
    if (get_info) get_info(&info);
    if (no_game) {
        auto load_game = reinterpret_cast<bool (*)(const retro_game_info*)>(symbol(handle, "retro_load_game"));
        if (load_game) (void)load_game(nullptr);
    }
    std::printf("{\"engine\":%s,\"version\":%s,\"need_fullpath\":%s,\"options\":%s}\n",
                quote(info.library_name ? info.library_name : "").c_str(),
                quote(info.library_version ? info.library_version : "").c_str(),
                info.need_fullpath ? "true" : "false", dump().c_str());
    deinit();
#if defined(_WIN32)
    FreeLibrary(static_cast<HMODULE>(handle));
#else
    dlclose(handle);
#endif
    return 0;
}
