// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#include "sdl_audio_backend.h"
#include "linux_controls.h"
#include "sdl_gl_backend.h"
#include "sdl_window_surface.h"

#include "../../core/auto_save_mode.h"
#include "../../../shared/generated/native_layouts.h"
#include "../../core/libretro_host.h"
#include "../../core/png_writer.h"
#include "../../video/capture/capture_backend.h"
#include "../../video/vulkan/hardware_backend.h"
#include "../../video/vulkan/software_backend.h"

#include <SDL2/SDL.h>
#include <gtk/gtk.h>

#include <algorithm>
#include <array>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstring>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <optional>
#if !defined(_WIN32)
#include <pwd.h>
#include <unistd.h>
#endif
#include <atomic>
#include <mutex>
#include <thread>
#include <sstream>
#include <string>
#include <string_view>

namespace an3 {
namespace {

struct Options {
    std::filesystem::path rom;
    std::string system;
    std::string renderer = "auto";
    std::string layout = "preserve";
    std::filesystem::path storage;
    bool control_stdin = false;
    bool pick = false;
    bool no_controls = false;
    // Structured, agent-native test control plane (see docs/agent-control-plane.md).
    bool headless = false;
    bool no_audio = false;
    bool status_json = false;
    long frames = -1;                    // <0 = run until quit; >=0 = bounded run
    std::filesystem::path capture;       // PNG written from the last headless frame
    std::filesystem::path capture_raw;   // raw RGBA written from the last headless frame
    std::filesystem::path load_state;    // import a save state before running
    std::filesystem::path save_state;    // export a save state after running
    std::string input_seq;               // e.g. "A@0-30;Start@40-45"
};

void usage() {
    std::cout << "VibeCodedEmulator native player\n"
              << "Usage: an3-offline-native --rom PATH [--system gba|nds|3ds] [--renderer auto|vulkan|opengl] [--layout left-right|top-bottom]\n"
              << "       an3-offline-native --pick [--no-controls]\n"
              << "       an3-offline-native --rom PATH --system gba --headless --frames N [--capture out.png] [--capture-raw out.rgba] [--status-json]\n"
              << "           [--load-state PATH] [--save-state PATH] [--input-seq \"A@0-30;Start@40-45\"] [--no-audio]\n"
              << "F1: Cycle layout · F2: Menu · F3: Pad · F4: fullscreen · Esc: close Menu/quit · F5/F9: save/load slot 1\n";
}

// Map a libretro joypad button name to its id (matches NativeInput /
// keyboard_button ids used elsewhere in this file).
int joypad_button_id(const std::string& name) {
    static const char* names[] = {"B", "Y", "Select", "Start", "Up", "Down", "Left", "Right",
                                  "A", "X", "L", "R", "L2", "R2", "L3", "R3"};
    for (int index = 0; index < 16; ++index) if (name == names[index]) return index;
    return -1;
}

struct InputWindow {
    int button = -1;
    long start = 0;
    long end = 0;
};

// Parses "A@0-30;Start@40-45". Invalid clauses are ignored so a malformed
// sequence degrades to no input rather than an unbounded hold.
std::vector<InputWindow> parse_input_seq(const std::string& spec) {
    std::vector<InputWindow> windows;
    std::istringstream clauses(spec);
    std::string clause;
    while (std::getline(clauses, clause, ';')) {
        if (clause.empty()) continue;
        const auto at = clause.find('@');
        const auto dash = clause.find('-', at == std::string::npos ? 0 : at);
        if (at == std::string::npos || dash == std::string::npos) continue;
        const int button = joypad_button_id(clause.substr(0, at));
        if (button < 0) continue;
        try {
            const long start = std::stol(clause.substr(at + 1, dash - at - 1));
            const long end = std::stol(clause.substr(dash + 1));
            if (end < start) continue;
            windows.push_back(InputWindow{button, start, end});
        } catch (...) {
            continue;
        }
    }
    return windows;
}

void apply_input_window(NativeInput& input, const std::vector<InputWindow>& windows, long frame) {
    for (const auto& window : windows) {
        if (frame >= window.start && frame <= window.end) input.set_button(static_cast<unsigned>(window.button), true);
    }
}

std::string json_escape(const std::string& value) {
    std::string out;
    out.reserve(value.size() + 8);
    for (char item : value) {
        switch (item) {
        case '"': out += "\\\""; break;
        case '\\': out += "\\\\"; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        case '\t': out += "\\t"; break;
        default:
            if (static_cast<unsigned char>(item) < 0x20) out += ' ';
            else out += item;
        }
    }
    return out;
}

std::optional<std::string> choose_rom() {
    // GTK uses the XDG desktop portal when Flatpak sets GTK_USE_PORTAL, while
    // remaining a native file picker for the DEB. The path never enters a
    // shell command and is validated as a regular file before core loading.
    int gtk_argc = 0;
    char** gtk_argv = nullptr;
    if (!gtk_init_check(&gtk_argc, &gtk_argv)) return std::nullopt;
    GtkWidget* dialog = gtk_file_chooser_dialog_new(
        "Choose a local ROM", nullptr, GTK_FILE_CHOOSER_ACTION_OPEN,
        "_Cancel", GTK_RESPONSE_CANCEL, "_Open", GTK_RESPONSE_ACCEPT, nullptr);
    GtkFileFilter* filter = gtk_file_filter_new();
    gtk_file_filter_set_name(filter, "Supported ROMs");
    gtk_file_filter_add_pattern(filter, "*.gba");
    gtk_file_filter_add_pattern(filter, "*.nds");
    gtk_file_filter_add_pattern(filter, "*.dsi");
    gtk_file_filter_add_pattern(filter, "*.3ds");
    gtk_file_filter_add_pattern(filter, "*.3dsx");
    gtk_file_filter_add_pattern(filter, "*.cci");
    gtk_file_filter_add_pattern(filter, "*.cxi");
    gtk_file_chooser_add_filter(GTK_FILE_CHOOSER(dialog), filter);
    std::optional<std::string> selected;
    if (gtk_dialog_run(GTK_DIALOG(dialog)) == GTK_RESPONSE_ACCEPT) {
        gchar* filename = gtk_file_chooser_get_filename(GTK_FILE_CHOOSER(dialog));
        if (filename) { selected = filename; g_free(filename); }
    }
    gtk_widget_destroy(dialog);
    while (g_main_context_iteration(nullptr, false)) {}
    return selected;
}

std::optional<Options> parse_options(int argc, char** argv) {
    Options options;
    for (int index = 1; index < argc; ++index) {
        const std::string_view argument(argv[index]);
        const auto value = [&]() -> std::optional<std::string> {
            if (index + 1 >= argc) return std::nullopt;
            return std::string(argv[++index]);
        };
        if (argument == "--help" || argument == "-h") { usage(); return std::nullopt; }
        if (argument == "--pick") { options.pick = true; continue; }
        if (argument == "--no-controls") { options.no_controls = true; continue; }
        if (argument == "--control-stdin") { options.control_stdin = true; continue; }
        if (argument == "--headless") { options.headless = true; continue; }
        if (argument == "--no-audio") { options.no_audio = true; continue; }
        if (argument == "--status-json") { options.status_json = true; continue; }
        if (argument == "--frames") {
            if (auto item = value()) { try { options.frames = std::stol(*item); } catch (...) { return std::nullopt; } } else return std::nullopt;
            if (options.frames < 0) return std::nullopt;
            continue;
        }
        if (argument == "--capture") { if (auto item = value()) options.capture = std::filesystem::u8path(*item); else return std::nullopt; continue; }
        if (argument == "--capture-raw") { if (auto item = value()) options.capture_raw = std::filesystem::u8path(*item); else return std::nullopt; continue; }
        if (argument == "--load-state") { if (auto item = value()) options.load_state = std::filesystem::u8path(*item); else return std::nullopt; continue; }
        if (argument == "--save-state") { if (auto item = value()) options.save_state = std::filesystem::u8path(*item); else return std::nullopt; continue; }
        if (argument == "--input-seq") { if (auto item = value()) options.input_seq = *item; else return std::nullopt; continue; }
        if (argument == "--storage") { if (auto item = value()) options.storage = std::filesystem::u8path(*item); else return std::nullopt; continue; }
        if (argument == "--rom") { if (auto item = value()) options.rom = std::filesystem::u8path(*item); else return std::nullopt; continue; }
        if (argument == "--system") { if (auto item = value()) options.system = *item; else return std::nullopt; continue; }
        if (argument == "--renderer") { if (auto item = value()) options.renderer = *item; else return std::nullopt; continue; }
        if (argument == "--layout") { if (auto item = value()) options.layout = *item; else return std::nullopt; continue; }
        std::cerr << "Unknown option: " << argument << "\n";
        return std::nullopt;
    }
    if (options.pick) {
        const auto selected = choose_rom();
        if (!selected) { std::cerr << "No ROM selected (or the desktop picker is unavailable).\n"; return std::nullopt; }
        options.rom = *selected;
    }
    if (options.rom.empty()) { usage(); return std::nullopt; }
    return options;
}

std::string infer_system(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    std::array<uint8_t, 0x200> header{};
    input.read(reinterpret_cast<char*>(header.data()), static_cast<std::streamsize>(header.size()));
    const auto size = static_cast<size_t>(input.gcount());
    if (size >= 0x104 && (!std::memcmp(header.data() + 0x100, "NCSD", 4) || !std::memcmp(header.data() + 0x100, "NCCH", 4))) return "3ds";
    if (size > 0xb2 && header[0xb2] == 0x96) return "gba";
    if (size >= 0x30) {
        const auto read_u32 = [&](size_t offset) { return static_cast<uint64_t>(header[offset]) | (static_cast<uint64_t>(header[offset+1]) << 8) | (static_cast<uint64_t>(header[offset+2]) << 16) | (static_cast<uint64_t>(header[offset+3]) << 24); };
        const uint64_t arm9_offset = read_u32(0x20), arm9_size = read_u32(0x2c);
        if (arm9_offset >= 0x200 && arm9_size) return "nds";
    }
    std::string extension = path.extension().string();
    std::transform(extension.begin(), extension.end(), extension.begin(), [](unsigned char item) { return static_cast<char>(std::tolower(item)); });
    if (extension == ".gba" || extension == ".raw") return "gba";
    if (extension == ".nds" || extension == ".dsi") return "nds";
    if (extension == ".3ds" || extension == ".3dsx" || extension == ".cci" || extension == ".cxi" || extension == ".app") return "3ds";
    return {};
}

std::filesystem::path user_data_root() {
#if defined(_WIN32)
    if (const char* configured = std::getenv("LOCALAPPDATA"); configured && *configured) return std::filesystem::path(configured) / "VibeCodedEmulator";
    throw std::runtime_error("Windows local application data directory is unavailable.");
#else
    if (const char* configured = std::getenv("XDG_DATA_HOME"); configured && *configured) return std::filesystem::path(configured) / "VibeCodedEmulator";
    const passwd* entry = getpwuid(getuid());
    return std::filesystem::path(entry && entry->pw_dir ? entry->pw_dir : ".") / ".local" / "share" / "VibeCodedEmulator";
#endif
}

std::string stable_rom_id(const std::filesystem::path& path) {
    const std::string text = path.string();
    uint64_t hash = 1469598103934665603ull;
    for (unsigned char item : text) { hash ^= item; hash *= 1099511628211ull; }
    std::ostringstream result; result << std::hex << std::setw(16) << std::setfill('0') << hash;
    return result.str();
}

std::filesystem::path bundled_core(const std::string& system) {
#if defined(_WIN32)
    const char* filename = system == "gba" ? "mgba_libretro.dll" : system == "nds" ? "melondsds_libretro.dll" : "azahar_libretro.dll";
    char* base = SDL_GetBasePath();
    const auto directory = std::filesystem::u8path(base ? base : ".");
    SDL_free(base);
    return directory / "libretro" / filename;
#else
    const char* filename = system == "gba" ? "mgba_libretro.so" : system == "nds" ? "melondsds_libretro.so" : "azahar_libretro.so";
    if (const char* configured = std::getenv("AN3_OFFLINE_LIBDIR"); configured && *configured) return std::filesystem::path(configured) / "libretro" / filename;
    const std::filesystem::path flatpak = "/app/lib/an3-offline-native/libretro";
    if (std::filesystem::is_regular_file(flatpak / filename)) return flatpak / filename;
    return std::filesystem::path("/usr/lib/an3-offline-native/libretro") / filename;
#endif
}

uint32_t keyboard_button(SDL_Keycode key) {
    switch (key) {
    case SDLK_z: return 0; case SDLK_a: return 1; case SDLK_SPACE: return 2; case SDLK_RETURN: return 3;
    case SDLK_UP: return 4; case SDLK_DOWN: return 5; case SDLK_LEFT: return 6; case SDLK_RIGHT: return 7;
    case SDLK_x: return 8; case SDLK_s: return 9; case SDLK_l: return 10; case SDLK_j: return 11;
    default: return 32;
    }
}

uint32_t controller_button(Uint8 button) {
    switch (button) {
    case SDL_CONTROLLER_BUTTON_B: return 0; case SDL_CONTROLLER_BUTTON_Y: return 1;
    case SDL_CONTROLLER_BUTTON_BACK: return 2; case SDL_CONTROLLER_BUTTON_START: return 3;
    case SDL_CONTROLLER_BUTTON_DPAD_UP: return 4; case SDL_CONTROLLER_BUTTON_DPAD_DOWN: return 5;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: return 6; case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: return 7;
    case SDL_CONTROLLER_BUTTON_A: return 8; case SDL_CONTROLLER_BUTTON_X: return 9;
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: return 10; case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: return 11;
    default: return 32;
    }
}

bool is_supported_layout(const std::string& system, const std::string& layout) {
    const auto contains = [&](const auto& layouts) {
        for (const auto& item : layouts) if (layout == item.id) return true;
        return false;
    };
    if (system == "nds") return contains(native_layouts::nds);
    if (system == "3ds") return contains(native_layouts::three_ds);
    return false;
}

// F1 cycles the same list the toolbar chooser exposes; the chooser itself is
// the full picker.
std::string next_supported_layout(const std::string& system, const std::string& current) {
    const auto advance = [&](const auto& layouts) -> std::string {
        if (layouts.empty()) return current;
        for (size_t index = 0; index < layouts.size(); ++index) {
            if (current == layouts[index].id) return std::string(layouts[(index + 1) % layouts.size()].id);
        }
        return std::string(layouts.front().id);
    };
    if (system == "nds") return advance(native_layouts::nds);
    if (system == "3ds") return advance(native_layouts::three_ds);
    return current;
}

void set_touch(NativeInput& input, const std::string& system, const std::string& layout,
               int mouse_x, int mouse_y, int width, int height, bool pressed) {
    if (!pressed || (system != "nds" && system != "3ds")) { input.cancel_pointer(); return; }
    const bool wide = layout == "left-right";
    const float frame_width = system == "3ds" ? (wide ? 720.f : 400.f) : (wide ? 512.f : 256.f);
    const float frame_height = system == "3ds" ? (wide ? 240.f : 480.f) : (wide ? 192.f : 384.f);
    const float scale = std::min(static_cast<float>(width) / frame_width, static_cast<float>(height) / frame_height);
    if (scale <= 0) { input.cancel_pointer(); return; }
    const float x = (mouse_x - (width - frame_width * scale) * .5f) / scale;
    const float y = (mouse_y - (height - frame_height * scale) * .5f) / scale;
    if (system == "nds") {
        const float local_x = x - (wide ? 256.f : 0.f), local_y = y - (wide ? 0.f : 192.f);
        if (local_x < 0 || local_x >= 256 || local_y < 0 || local_y >= 192) { input.cancel_pointer(); return; }
    } else {
        const float left = wide ? 400.f : 40.f, right = wide ? 720.f : 360.f;
        const float top = wide ? 0.f : 240.f, bottom = wide ? 240.f : 480.f;
        if (x < left || x >= right || y < top || y >= bottom) { input.cancel_pointer(); return; }
    }
    input.set_pointer(static_cast<int16_t>(std::clamp(x / frame_width * 65534.f - 32767.f, -32767.f, 32767.f)),
                      static_cast<int16_t>(std::clamp(y / frame_height * 65534.f - 32767.f, -32767.f, 32767.f)), true);
}

} // namespace
} // namespace an3

int main(int argc, char** argv) {
    using namespace an3;
    SDL_SetMainReady();
    if (argc == 2 && (std::string_view(argv[1]) == "--help" || std::string_view(argv[1]) == "-h")) {
        usage();
        return 0;
    }
    const auto parsed = parse_options(argc, argv);
    if (!parsed) return 2;
    Options options = *parsed;
    std::error_code filesystem_error;
    options.rom = std::filesystem::weakly_canonical(options.rom, filesystem_error);
    if (filesystem_error || !std::filesystem::is_regular_file(options.rom)) { std::cerr << "ROM is not a readable regular file.\n"; return 2; }
    if (options.system.empty()) options.system = infer_system(options.rom);
    if (options.system != "gba" && options.system != "nds" && options.system != "3ds") { std::cerr << "Could not identify GBA, NDS, or decrypted 3DS ROM content.\n"; return 2; }
    if (options.renderer != "auto" && options.renderer != "vulkan" && options.renderer != "opengl") { std::cerr << "Renderer must be auto, vulkan, or opengl.\n"; return 2; }
    if (options.system == "3ds" && options.renderer == "opengl") { std::cerr << "3DS requires the portable Vulkan hardware renderer; OpenGL would require a prohibited GPU readback.\n"; return 2; }
    const auto core = bundled_core(options.system);
    if (!std::filesystem::is_regular_file(core)) { std::cerr << "Bundled " << options.system << " libretro core is missing: " << core << "\n"; return 2; }

    const auto root = options.storage.empty() ? user_data_root() / options.system / stable_rom_id(options.rom) : options.storage;
    std::filesystem::create_directories(root / "saves", filesystem_error);
    if (filesystem_error) { std::cerr << "Could not create native save storage.\n"; return 2; }
    const auto layout_file = root / "screen-layout.txt";
    if (options.layout == "preserve" && (options.system == "nds" || options.system == "3ds")) {
        std::ifstream stored(layout_file); std::getline(stored, options.layout);
    }
    if ((options.system == "nds" || options.system == "3ds") && !is_supported_layout(options.system, options.layout)) options.layout = "left-right";

    // Agent-native deterministic test path: no window, no GPU, no human.
    // Capturing a frame implies headless because a GPU-backed window cannot
    // produce CPU pixels without a readback this build deliberately avoids.
    if (options.headless || !options.capture.empty() || !options.capture_raw.empty()) {
        if (options.system == "3ds") {
            std::cerr << "Headless capture is unavailable for hardware-rendered 3DS content.\n";
            return 2;
        }
        HeadlessSurface capture_surface;
        CaptureBackend capture_video;
        NullAudioBackend capture_audio;
        std::string error;
        if (!capture_video.initialize(capture_surface, error)) { std::cerr << error << "\n"; return 1; }
        NativeCoreHost host;
        if (!host.initialize(core.string(), options.rom.string(), (root / "saves").string(), capture_video, capture_audio, error, options.layout)) {
            std::cerr << "Native core initialization failed: " << error << "\n";
            return 1;
        }
        const bool requested_state_load = !options.load_state.empty();
        bool state_loaded = true;
        if (requested_state_load && !host.import_state(options.load_state.string(), error)) {
            std::cerr << "Could not load save state: " << error << "\n";
            host.shutdown();
            return 6;
        }
        const auto windows = parse_input_seq(options.input_seq);
        const long frames = options.frames >= 0 ? options.frames : 1;
        bool state_ok = true;
        long ran_frames = 0;
        for (long frame = 0; frame < frames; ++frame) {
            apply_input_window(host.input(), windows, frame);
            if (!host.run_one(error, true)) { state_ok = false; break; }
            host.input().clear();
            ++ran_frames;
        }
        bool state_saved = false;
        if (state_ok && !options.save_state.empty()) {
            state_saved = host.export_state(options.save_state.string(), error);
            if (!state_saved) std::cerr << "Could not save state: " << error << "\n";
        }
        const auto status = host.status();
        std::string capture_error;
        bool captured = false;
        if (state_ok && !options.capture.empty() && capture_video.has_frame()) {
            captured = write_png_rgba(options.capture.string(), capture_video.width(), capture_video.height(), capture_video.rgba(), capture_error);
        }
        if (state_ok && !options.capture_raw.empty() && capture_video.has_frame()) {
            write_raw_rgba(options.capture_raw.string(), capture_video.rgba(), capture_error);
        }
        if (options.status_json) {
            std::cout << "AN3CTL_STATUS {"
                      << "\"system\":\"" << json_escape(options.system) << "\","
                      << "\"rom\":\"" << json_escape(options.rom.filename().string()) << "\","
                      << "\"renderer\":\"headless\","
                      << "\"core\":\"" << json_escape(status.core_name) << "\","
                      << "\"coreVersion\":\"" << json_escape(status.core_version) << "\","
                      << "\"running\":" << (state_ok ? "true" : "false") << ","
                      << "\"frames\":" << ran_frames << ","
                      << "\"coreFrames\":" << status.core_frames << ","
                      << "\"requestedFrames\":" << frames << ","
                      << "\"fps\":" << status.core_fps << ","
                      << "\"width\":" << capture_video.width() << ","
                      << "\"height\":" << capture_video.height() << ","
                      << "\"capture\":\"" << json_escape(options.capture.string()) << "\","
                      << "\"captureRaw\":\"" << json_escape(options.capture_raw.string()) << "\","
                      << "\"captured\":" << (captured ? "true" : "false") << ","
                      << "\"stateLoaded\":" << (requested_state_load && state_loaded ? "true" : "false") << ","
                      << "\"stateSaved\":" << (state_saved ? "true" : "false") << ","
                      << "\"message\":\"" << json_escape(status.last_message) << "\""
                      << "}" << std::endl;
        }
        host.shutdown();
        if (!capture_error.empty()) { std::cerr << capture_error << "\n"; return 6; }
        return state_ok ? 0 : 1;
    }

    std::string error;
    LinuxSdlWindowSurface surface;
    if (!surface.initialize("VibeCodedEmulator", 1280, 720, error)) { std::cerr << error << "\n"; return 1; }
    std::unique_ptr<NativeVideoBackend> video;
    if (options.system == "3ds") video = std::make_unique<VulkanHardwareBackend>();
    else video = std::make_unique<VulkanSoftwareBackend>();
    bool ready = options.renderer != "opengl" && video->initialize(surface, error);
    if (!ready && options.system != "3ds" && (options.renderer == "auto" || options.renderer == "opengl")) {
        if (options.renderer == "auto") {
            std::cerr << "Vulkan unavailable; using native desktop OpenGL fallback: " << error << "\n";
        }
        video = std::make_unique<LinuxSdlGlBackend>();
        ready = video->initialize(surface, error);
    }
    if (!ready) { std::cerr << error << "\n"; SDL_Quit(); return 1; }
    LinuxSdlAudioBackend audio;
    NativeCoreHost host;
    if (!host.initialize(core.string(), options.rom.string(), (root / "saves").string(), *video, audio, error, options.layout)) {
        std::cerr << "Native core initialization failed: " << error << "\n";
        video->shutdown(); SDL_Quit(); return 1;
    }
    if (!options.load_state.empty() && !host.import_state(options.load_state.string(), error)) {
        std::cerr << "Could not load save state: " << error << "\n";
        video->shutdown(); SDL_Quit(); return 6;
    }

    SDL_GameController* controller = nullptr;
    for (int index = 0; index < SDL_NumJoysticks(); ++index) if (SDL_IsGameController(index)) { controller = SDL_GameControllerOpen(index); if (controller) break; }
    std::array<bool, 4> physical_dpad{}, analog_dpad{};
    auto apply_dpad = [&] { for (unsigned offset = 0; offset < 4; ++offset) host.input().set_button(4 + offset, physical_dpad[offset] || analog_dpad[offset]); };
    int mouse_x = 0, mouse_y = 0;
    bool mouse_pressed = false, running = true, paused = false;
    double speed = 1.0;
    std::string auto_save_mode = "off";
    AutoSaveSettings auto_save = parse_auto_save_mode(auto_save_mode).value_or(AutoSaveSettings{});
    uint64_t scheduled_frames = 0;
    std::string runtime_message;
    auto deadline = std::chrono::steady_clock::now();
    auto last_auto = deadline;
    auto set_layout = [&](const std::string& value, std::string& detail) {
        if (!host.set_screen_layout(value, detail)) return false;
        options.layout = value;
        std::ofstream output(layout_file, std::ios::trunc);
        output << options.layout;
        if (!output) { detail = "Could not persist the native screen layout."; return false; }
        runtime_message = "Screen layout changed to " + options.layout + ".";
        return true;
    };
    auto toggle_fullscreen = [&] {
        SDL_Window* window = surface.window();
        if (!window) { runtime_message = "Fullscreen is unavailable because the SDL window closed."; return; }
        const bool fullscreen = (SDL_GetWindowFlags(window) & SDL_WINDOW_FULLSCREEN_DESKTOP) != 0;
        if (SDL_SetWindowFullscreen(window, fullscreen ? 0 : SDL_WINDOW_FULLSCREEN_DESKTOP) != 0) {
            runtime_message = std::string("Fullscreen change failed: ") + SDL_GetError();
            return;
        }
        video->resize();
        runtime_message = fullscreen ? "Exited fullscreen." : "Entered fullscreen.";
    };

    LinuxControlCallbacks control_callbacks;
    control_callbacks.snapshot = [&] {
        LinuxControlSnapshot value;
        value.core = host.status();
        value.video = video->metrics();
        value.audio = audio.metrics();
        value.paused = paused;
        value.auto_save_mode = auto_save_mode;
        value.speed = speed;
        value.layout = options.layout;
        value.last_message = runtime_message.empty() ? value.core.last_message : runtime_message;
        return value;
    };
    control_callbacks.set_paused = [&](bool value) { paused = value; host.input().clear(); deadline = std::chrono::steady_clock::now(); };
    control_callbacks.set_speed = [&](double value) {
        if (value == .5 || value == 1.0 || value == 2.0 || value == 4.0 || value == 8.0) {
            speed = value;
            deadline = std::chrono::steady_clock::now();
        }
    };
    control_callbacks.set_auto_save_mode = [&](const std::string& value) {
        const auto parsed = parse_auto_save_mode(value);
        if (!parsed) return;
        auto_save_mode = value;
        auto_save = *parsed;
        last_auto = std::chrono::steady_clock::now();
    };
    control_callbacks.toggle_fullscreen = toggle_fullscreen;
    control_callbacks.return_to_library = [&] { running = false; };
    control_callbacks.set_layout = set_layout;

    // Step the emulation speed by one schema step for the Phone Controller.
    // Reuses the same speed values the companion panel exposes.
    const auto step_speed = [&](int direction) {
        static constexpr double kSpeeds[] = {0.5, 1.0, 2.0, 4.0, 8.0};
        int index = 1;
        for (int step = 0; step < 5; ++step) {
            if (std::abs(kSpeeds[step] - speed) < 0.001) index = step;
        }
        index = std::clamp(index + direction, 0, 4);
        speed = kSpeeds[index];
        deadline = std::chrono::steady_clock::now();
    };

    // Only a private parent-owned pipe enables this channel. It has no TCP
    // listener, arbitrary paths or commands; SDL/GTK remain input owners.
    struct ParentControl {
        std::atomic<bool> quit{false};
        std::mutex mutex;
        bool pending = false;
        uint32_t buttons = 0;
        int16_t x = 0, y = 0, tx = 0, ty = 0;
        bool touched = false;
        std::string utility;
    };
    auto parent = std::make_shared<ParentControl>();
    if (options.control_stdin) {
        std::thread([parent] {
            std::string line;
            while (std::getline(std::cin, line)) {
                if (line == "QUIT") break;
                if (line.size() > 160) continue;
                // Phone Controller one-shot utilities. Only the canonical action
                // names are accepted; anything else falls through to the INPUT
                // parser and is ignored.
                if (line == "QUICK_SAVE" || line == "SPEED_UP" || line == "SPEED_DOWN" || line == "OPEN_MENU") {
                    std::lock_guard lock(parent->mutex);
                    parent->utility = line;
                    continue;
                }
                std::istringstream message(line);
                std::string command;
                uint32_t buttons; int x, y, tx, ty, touched;
                if (!(message >> command >> buttons >> x >> y >> tx >> ty >> touched) || command != "INPUT") continue;
                if (x < -32767 || x > 32767 || y < -32767 || y > 32767 || tx < -32767 || tx > 32767 || ty < -32767 || ty > 32767 || (touched != 0 && touched != 1)) continue;
                std::lock_guard lock(parent->mutex);
                parent->buttons = buttons; parent->x = x; parent->y = y;
                parent->tx = tx; parent->ty = ty; parent->touched = touched; parent->pending = true;
            }
            parent->quit = true; // Parent exit also closes the native session.
        }).detach();
    }

    {
        std::unique_ptr<LinuxControlPanel> controls;
        if (!options.no_controls) {
            controls = std::make_unique<LinuxControlPanel>(host, audio, options.system, std::move(control_callbacks));
            std::string controls_error;
            if (!controls->initialize(controls_error)) {
                std::cerr << controls_error << " Continuing without the companion controls window.\n";
                controls.reset();
            } else {
                controls->show();
            }
        }
        if (options.control_stdin) {
            const auto video_status = video->metrics();
            std::cout << "AN3_NATIVE_READY " << video_status.effective << std::endl;
            std::cout << "AN3_NATIVE_DEVICE " << video_status.device_details << std::endl;
        }
        while (running && host.running() && !parent->quit) {
            std::string utility;
            if (options.control_stdin) {
                std::lock_guard lock(parent->mutex);
                if (parent->pending) {
                    for (unsigned bit = 0; bit < 16; ++bit) host.input().set_button(bit, (parent->buttons & (1u << bit)) != 0);
                    host.input().set_analog(parent->x, parent->y);
                    if (parent->touched) host.input().set_pointer(parent->tx, parent->ty, true);
                    else host.input().cancel_pointer();
                    parent->pending = false;
                }
                utility.swap(parent->utility);
            }
            if (!utility.empty()) {
                if (utility == "QUICK_SAVE") {
                    runtime_message = host.save_state(1, error) ? "Quick save 1 completed." : "Quick save 1 failed: " + error;
                } else if (utility == "SPEED_UP" || utility == "SPEED_DOWN") {
                    step_speed(utility == "SPEED_UP" ? 1 : -1);
                } else if (utility == "OPEN_MENU") {
                    if (controls && !controls->visible()) controls->show();
                }
            }
            if (controls) controls->pump();
            SDL_Event event{};
            while (SDL_PollEvent(&event)) {
                if (event.type == SDL_QUIT) { running = false; break; }
                if (event.type == SDL_WINDOWEVENT && event.window.event == SDL_WINDOWEVENT_FOCUS_LOST) {
                    host.input().clear(); mouse_pressed = false;
                    physical_dpad.fill(false); analog_dpad.fill(false);
                }
                if (event.type == SDL_KEYDOWN || event.type == SDL_KEYUP) {
                    const bool pressed = event.type == SDL_KEYDOWN;
                    if (pressed && event.key.repeat) continue;
                    if (pressed && event.key.keysym.sym == SDLK_ESCAPE) {
                        if (controls && controls->visible()) { controls->hide(); host.input().clear(); continue; }
                        running = false;
                        break;
                    }
                    if (pressed && event.key.keysym.sym == SDLK_F1 && (options.system == "nds" || options.system == "3ds")) {
                        const std::string next_layout = next_supported_layout(options.system, options.layout);
                        if (!set_layout(next_layout, error)) runtime_message = "Layout change failed: " + error;
                        continue;
                    }
                    if (pressed && event.key.keysym.sym == SDLK_F2 && controls) { controls->toggle(); continue; }
                    if (pressed && event.key.keysym.sym == SDLK_F3 && controls) { controls->show_pad(); continue; }
                    if (pressed && event.key.keysym.sym == SDLK_F4) { toggle_fullscreen(); continue; }
                    if (pressed && event.key.keysym.sym == SDLK_p) { paused = !paused; host.input().clear(); deadline = std::chrono::steady_clock::now(); continue; }
                    if (pressed && event.key.keysym.sym == SDLK_F5) {
                        runtime_message = host.save_state(1, error) ? "Quick save 1 completed." : "Quick save 1 failed: " + error;
                        continue;
                    }
                    if (pressed && event.key.keysym.sym == SDLK_F9) {
                        runtime_message = host.load_state(1, error) ? "Quick load 1 completed." : "Quick load 1 failed: " + error;
                        continue;
                    }
                    const uint32_t button = keyboard_button(event.key.keysym.sym);
                    if (button < 32) host.input().set_button(button, pressed);
                }
                if (event.type == SDL_CONTROLLERBUTTONDOWN || event.type == SDL_CONTROLLERBUTTONUP) {
                    const uint32_t button = controller_button(event.cbutton.button); const bool pressed = event.type == SDL_CONTROLLERBUTTONDOWN;
                    if (button >= 4 && button <= 7) physical_dpad[button - 4] = pressed; else if (button < 32) host.input().set_button(button, pressed);
                    apply_dpad();
                }
                if (event.type == SDL_CONTROLLERAXISMOTION) {
                    const int16_t value = event.caxis.value;
                    static int16_t axis_x = 0, axis_y = 0;
                    if (event.caxis.axis == SDL_CONTROLLER_AXIS_LEFTX) axis_x = value;
                    if (event.caxis.axis == SDL_CONTROLLER_AXIS_LEFTY) axis_y = value;
                    host.input().set_analog(axis_x, axis_y);
                    if (options.system != "3ds") {
                        constexpr int16_t dead_zone = 11'469;
                        analog_dpad = {axis_y < -dead_zone, axis_y > dead_zone, axis_x < -dead_zone, axis_x > dead_zone};
                        apply_dpad();
                    }
                }
                if (event.type == SDL_MOUSEBUTTONDOWN || event.type == SDL_MOUSEBUTTONUP) {
                    if (event.button.button == SDL_BUTTON_LEFT) mouse_pressed = event.type == SDL_MOUSEBUTTONDOWN;
                    mouse_x = event.button.x; mouse_y = event.button.y;
                }
                if (event.type == SDL_MOUSEMOTION) { mouse_x = event.motion.x; mouse_y = event.motion.y; }
                if (event.type == SDL_MOUSEBUTTONDOWN || event.type == SDL_MOUSEBUTTONUP || event.type == SDL_MOUSEMOTION) {
                    // An open controls panel owns pointer input; a tap on a menu
                    // row must never also drive the emulated touchscreen.
                    if (controls && controls->visible()) {
                        if (mouse_pressed) host.input().cancel_pointer();
                        mouse_pressed = false;
                    } else {
                        int width = 1, height = 1; SDL_GetWindowSize(surface.window(), &width, &height);
                        set_touch(host.input(), options.system, options.layout, mouse_x, mouse_y, width, height, mouse_pressed);
                    }
                }
            }
            const auto now = std::chrono::steady_clock::now();
            if (!paused && now >= deadline) {
                const unsigned present_stride = speed > 1.0 ? static_cast<unsigned>(speed) : 1u;
                if (!host.run_one(error, scheduled_frames % present_stride == 0)) { std::cerr << "Native core stopped: " << error << "\n"; break; }
                ++scheduled_frames;
                // A bounded run (`--frames N`) exits after N emulated frames so a
                // test can drive the player deterministically from the CLI.
                if (options.frames >= 0 && scheduled_frames >= static_cast<uint64_t>(options.frames)) running = false;
                // The owned parent pipe has no network listener. Emit a
                // bounded, path-free heartbeat for package/runtime testing
                // and for the Windows shell to distinguish an initialized
                // game window from a merely spawned process.
                if (options.control_stdin && scheduled_frames % 120 == 0) {
                    const auto core_status = host.status();
                    const auto video_status = video->metrics();
                    std::cout << "AN3_NATIVE_STATUS core=" << core_status.core_frames
                              << " present=" << video_status.frames.presented_frames
                              << " drops=" << video_status.frames.dropped_frames
                              << " renderer=" << video_status.effective << std::endl;
                }
                const auto scaled_duration = std::chrono::nanoseconds(static_cast<int64_t>(std::llround(host.frame_duration().count() / speed)));
                deadline += scaled_duration;
                if (deadline < now - std::chrono::milliseconds(100)) deadline = now;
            } else if (paused) {
                deadline = now + std::chrono::milliseconds(20);
            }
            if (auto_save.enabled && now - last_auto >= std::chrono::seconds(auto_save.interval)) {
                runtime_message = host.save_auto(error) ? "Auto Save completed." : "Auto Save failed: " + error;
                last_auto = now;
            }
            if (controls) controls->pump();
            if (now < deadline) SDL_Delay(1);
        }
    }
    // A save-on-exit mode writes one final atomic snapshot as the session
    // stops. Periodic modes already saved on their own timer.
    if (auto_save.on_exit) host.save_auto(error);
    if (!options.save_state.empty()) host.export_state(options.save_state.string(), error);
    host.shutdown(); video->shutdown(); if (controller) SDL_GameControllerClose(controller); SDL_Quit();
    return 0;
}
