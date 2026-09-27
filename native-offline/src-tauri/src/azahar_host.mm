// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#import <AppKit/AppKit.h>
#import <AVFoundation/AVFoundation.h>
#import <dispatch/dispatch.h>
#import <MetalKit/MetalKit.h>
#import <QuartzCore/QuartzCore.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#include "../../shared/generated/player_ui.h"
#include "../../shared/generated/native_layouts.h"
#include "../../native-runtime/core/auto_save_mode.h"

#include <array>
#include <atomic>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <condition_variable>
#include <dlfcn.h>
#include <filesystem>
#include <fstream>
#include <fcntl.h>
#include <limits>
#include <mach/mach.h>
#include <memory>
#include <mutex>
#include <string>
#include <unistd.h>
#include <utility>
#include <vector>

#include "azahar_host.h"
#include "core_options.h"
#include "native_input_transform.h"
#include "save_persistence_worker.h"
#include "vulkan_frontend.h"

// The public libretro ABI is deliberately reproduced in this small host rather
// than pulling in a whole RetroArch frontend. Azahar exposes this ABI as its
// supported native integration seam on macOS.
namespace an3 {

constexpr unsigned RETRO_DEVICE_JOYPAD = 1;
constexpr unsigned RETRO_DEVICE_MOUSE = 2;
constexpr unsigned RETRO_DEVICE_ANALOG = 5;
constexpr unsigned RETRO_DEVICE_POINTER = 6;
constexpr unsigned RETRO_DEVICE_INDEX_ANALOG_LEFT = 0;
constexpr unsigned RETRO_DEVICE_INDEX_ANALOG_RIGHT = 1;
constexpr unsigned RETRO_DEVICE_ID_ANALOG_X = 0;
constexpr unsigned RETRO_DEVICE_ID_ANALOG_Y = 1;
constexpr unsigned RETRO_DEVICE_ID_JOYPAD_MASK = 256;
constexpr unsigned RETRO_DEVICE_ID_POINTER_X = 0;
constexpr unsigned RETRO_DEVICE_ID_POINTER_Y = 1;
constexpr unsigned RETRO_DEVICE_ID_POINTER_PRESSED = 2;
constexpr unsigned RETRO_DEVICE_ID_MOUSE_X = 0;
constexpr unsigned RETRO_DEVICE_ID_MOUSE_Y = 1;
constexpr unsigned RETRO_DEVICE_ID_MOUSE_LEFT = 2;
constexpr unsigned RETRO_MEMORY_SAVE_RAM = 0;

constexpr int RETRO_PIXEL_FORMAT_0RGB1555 = 0;
constexpr int RETRO_PIXEL_FORMAT_XRGB8888 = 1;
constexpr int RETRO_PIXEL_FORMAT_RGB565 = 2;

constexpr unsigned RETRO_ENVIRONMENT_SET_MESSAGE = 6;
constexpr unsigned RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY = 9;
constexpr unsigned RETRO_ENVIRONMENT_SET_PIXEL_FORMAT = 10;
constexpr unsigned RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS = 11;
constexpr unsigned RETRO_ENVIRONMENT_SET_HW_RENDER = 14;
constexpr unsigned RETRO_ENVIRONMENT_GET_VARIABLE = 15;
constexpr unsigned RETRO_ENVIRONMENT_SET_VARIABLES = 16;
constexpr unsigned RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE = 17;
constexpr unsigned RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME = 18;
constexpr unsigned RETRO_ENVIRONMENT_GET_LIBRETRO_PATH = 19;
constexpr unsigned RETRO_ENVIRONMENT_GET_LOG_INTERFACE = 27;
constexpr unsigned RETRO_ENVIRONMENT_GET_CONTENT_DIRECTORY = 30;
constexpr unsigned RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY = 31;
constexpr unsigned RETRO_ENVIRONMENT_SET_CONTROLLER_INFO = 35;
constexpr unsigned RETRO_ENVIRONMENT_SET_GEOMETRY = 37;
constexpr unsigned RETRO_ENVIRONMENT_EXPERIMENTAL = 0x10000;
constexpr unsigned RETRO_ENVIRONMENT_GET_CURRENT_SOFTWARE_FRAMEBUFFER = 40 | RETRO_ENVIRONMENT_EXPERIMENTAL;
constexpr unsigned RETRO_ENVIRONMENT_SET_SERIALIZATION_QUIRKS = 44;
constexpr unsigned RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION = 52;
constexpr unsigned RETRO_ENVIRONMENT_GET_PREFERRED_HW_RENDER = 56;
constexpr unsigned RETRO_ENVIRONMENT_SET_MESSAGE_EXT = 60;
constexpr unsigned RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2 = 67;
constexpr unsigned RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2_INTL = 68;
constexpr unsigned RETRO_ENVIRONMENT_GET_HW_RENDER_INTERFACE = 41 | RETRO_ENVIRONMENT_EXPERIMENTAL;
constexpr unsigned RETRO_ENVIRONMENT_SET_HW_RENDER_CONTEXT_NEGOTIATION_INTERFACE = 43 | RETRO_ENVIRONMENT_EXPERIMENTAL;
constexpr unsigned RETRO_ENVIRONMENT_GET_HW_RENDER_CONTEXT_NEGOTIATION_INTERFACE_SUPPORT = 73 | RETRO_ENVIRONMENT_EXPERIMENTAL;

constexpr uintptr_t RETRO_HW_FRAME_BUFFER_VALID = static_cast<uintptr_t>(-1);
constexpr unsigned RETRO_MEMORY_ACCESS_WRITE = 1u << 0;
constexpr unsigned RETRO_MEMORY_TYPE_CACHED = 1u << 0;
constexpr size_t kMaxQuickStateBytes = 512u * 1024u * 1024u;
constexpr size_t kMaxSaveRamBytes = 16u * 1024u * 1024u;
constexpr unsigned kMaxQuickStateSlot = 10;
constexpr size_t kHostTimingSamples = 256;
constexpr double kNominalCoreFps = 60.0;

// Host telemetry is a fixed atomic ring. It is intentionally independent of
// VulkanFrontend's mapped staging/ring implementation: collecting a timestamp
// and one bounded sample must not introduce logging, allocation, or a queue
// wait into the renderer hot path.
struct HostTimingSeries {
    std::array<std::atomic<uint32_t>, kHostTimingSamples> values{};
    std::atomic<size_t> count{0};
    std::atomic<size_t> next{0};

    void reset() {
        count.store(0, std::memory_order_relaxed);
        next.store(0, std::memory_order_relaxed);
    }

    void add(std::chrono::steady_clock::duration elapsed) {
        const auto micros = std::chrono::duration_cast<std::chrono::microseconds>(elapsed).count();
        const auto bounded = static_cast<uint32_t>(std::clamp<int64_t>(micros, 0, std::numeric_limits<uint32_t>::max()));
        const size_t index = next.fetch_add(1, std::memory_order_relaxed) % kHostTimingSamples;
        values[index].store(bounded, std::memory_order_relaxed);
        size_t observed = count.load(std::memory_order_relaxed);
        while (observed < kHostTimingSamples &&
               !count.compare_exchange_weak(observed, observed + 1, std::memory_order_relaxed)) {}
    }

    uint32_t percentile(unsigned percent) const {
        const size_t sample_count = std::min(count.load(std::memory_order_relaxed), kHostTimingSamples);
        if (!sample_count) return 0;
        std::array<uint32_t, kHostTimingSamples> ordered{};
        for (size_t index = 0; index < sample_count; ++index) ordered[index] = values[index].load(std::memory_order_relaxed);
        std::sort(ordered.begin(), ordered.begin() + static_cast<std::ptrdiff_t>(sample_count));
        const size_t rank = std::max<size_t>(1, (sample_count * percent + 99) / 100) - 1;
        return ordered[std::min(rank, sample_count - 1)];
    }
};

struct retro_system_info {
    const char* library_name;
    const char* library_version;
    const char* valid_extensions;
    bool need_fullpath;
    bool block_extract;
};

struct retro_game_info {
    const char* path;
    const void* data;
    size_t size;
    const char* meta;
};

struct retro_variable {
    const char* key;
    const char* value;
};

struct retro_message {
    const char* msg;
    unsigned frames;
};

// ABI layout from libretro.h. A core can request this experimental writable
// buffer during retro_run and then pass the same pointer to video_refresh.
struct retro_framebuffer {
    void* data;
    unsigned width;
    unsigned height;
    size_t pitch;
    int format;
    unsigned access_flags;
    unsigned memory_flags;
};

using retro_log_printf_t = void (*)(int level, const char* format, ...);

struct retro_log_callback {
    retro_log_printf_t log;
};

struct retro_system_timing {
    double fps;
    double sample_rate;
};

struct retro_game_geometry {
    unsigned base_width;
    unsigned base_height;
    unsigned max_width;
    unsigned max_height;
    float aspect_ratio;
};

struct retro_system_av_info {
    retro_game_geometry geometry;
    retro_system_timing timing;
};

using retro_environment_t = bool (*)(unsigned, void*);
using retro_video_refresh_t = void (*)(const void*, unsigned, unsigned, size_t);
using retro_audio_sample_t = void (*)(int16_t, int16_t);
using retro_audio_sample_batch_t = size_t (*)(const int16_t*, size_t);
using retro_input_poll_t = void (*)();
using retro_input_state_t = int16_t (*)(unsigned, unsigned, unsigned, unsigned);

class AzaharHost;
// libretro starts consulting the environment callback during retro_init and
// retro_load_game. Publish the host before either call so its paths and core
// options are available from the very first callback.
static AzaharHost* g_host = nullptr;
AzaharHost* active_host();

} // namespace an3

@class AN3AzaharView;
@class AN3InputButton;
@class AN3CirclePadView;

@interface AN3AzaharView : MTKView <MTKViewDelegate>
{
    NSString* _system;
    NSButton* _menu_button;
    NSButton* _pad_button;
    NSButton* _cursor_lock_button;
    NSView* _menu_panel;
    NSScrollView* _settings_scroll;
    NSView* _settings_document;
    NSStackView* _settings_stack;
    NSTabView* _settings_tabs;
    NSMutableDictionary<NSString*, NSStackView*>* _settings_tab_stacks;
    NSControl* _menu_focus_control;
    uint32_t _controller_menu_buttons;
    BOOL _menu_input_suppressed_until_release;
    NSButton* _save_settings_button;
    NSTextField* _settings_save_status;
    BOOL _settings_dirty;
    BOOL _draft_start_fullscreen;
    BOOL _draft_show_fps;
    BOOL _draft_muted;
    double _draft_volume;
    unsigned _draft_latency;
    unsigned _draft_resampler_quality;
    NSMutableDictionary<NSString*, NSString*>* _draft_core_options;
    NSTextField* _quick_state_status;
    NSTextField* _fps_overlay;
    NSButton* _start_fullscreen_toggle;
    NSButton* _show_fps_toggle;
    NSButton* _mute_audio_toggle;
    NSStackView* _volume_row;
    NSSlider* _volume_slider;
    NSTextField* _volume_value;
    NSPopUpButton* _audio_latency_popup;
    NSPopUpButton* _resampler_quality_popup;
    NSTextField* _audio_diagnostics;
    NSStackView* _core_options_stack;
    NSPopUpButton* _auto_save_mode_popup;
    NSButton* _load_auto_save_button;
    NSTextField* _auto_save_status;
    NSButton* _slow_speed_button;
    NSButton* _normal_speed_button;
    NSButton* _fast_speed_button;
    NSButton* _layout_button;
    NSButton* _save_button;
    NSPopUpButton* _screen_layout_popup;
    NSPopUpButton* _key_map_action;
    NSTextField* _key_map_status;
    NSArray<NSView*>* _pad_controls;
    AN3CirclePadView* _circle_pad;
    uint8_t _circle_key_directions;
    AN3InputButton* _dpad_up;
    AN3InputButton* _dpad_down;
    AN3InputButton* _dpad_left;
    AN3InputButton* _dpad_right;
    AN3InputButton* _button_a;
    AN3InputButton* _button_b;
    AN3InputButton* _button_x;
    AN3InputButton* _button_y;
    AN3InputButton* _button_l;
    AN3InputButton* _button_r;
    AN3InputButton* _button_start;
    AN3InputButton* _button_select;
    NSTrackingArea* _tracking_area;
    BOOL _cursor_locked;
    BOOL _capturing_key_map;
    unsigned _capturing_key_button;
    NSUInteger _ignore_key_up;
    BOOL _show_fps;
    uint64_t _fps_last_presented;
    NSTimeInterval _fps_last_update;
    NSTimeInterval _last_audio_diag_update;
    BOOL _applied_initial_fullscreen;
}
- (instancetype)initWithFrame:(NSRect)frameRect device:(nullable id<MTLDevice>)device system:(const char*)system;
- (void)releaseCursorLock;
- (void)refreshCoreOptions;
- (void)refreshSaveStateAvailability;
- (void)syncSpeedControls;
- (void)updateAudioDiagnostics;
- (void)saveSettings:(id)sender;
- (void)discardSettingsDraft;
- (void)closeMenuDiscardingDraft;
- (void)openMenu;
- (void)focusMenuControl:(NSControl*)control;
- (NSArray<NSControl*>*)menuFocusableControls;
- (void)moveMenuFocusBy:(NSInteger)delta;
- (void)adjustMenuFocusBy:(NSInteger)delta;
- (void)activateMenuFocus;
- (void)handleControllerMenuButtons:(uint32_t)buttons;
@end

@interface AN3InputButton : NSButton
@property(nonatomic, assign) unsigned input_button;
@end

@interface AN3CirclePadView : NSView {
    CGFloat _stick_x;
    CGFloat _stick_y;
}
- (void)releaseCircle;
@end

@interface AN3CoreOptionPopup : NSPopUpButton
@property(nonatomic, copy) NSString* optionKey;
@end

// Display-only labels must never take part in hit-testing. The FPS badge sits
// over the game surface, so without this a click on it would be swallowed
// instead of reaching the emulator or a control underneath.
@interface AN3InertLabel : NSTextField
@end

namespace an3 {
static AN3AzaharView* g_view = nil;
}

namespace an3 {

struct CoreApi {
    void* handle = nullptr;
    unsigned (*api_version)() = nullptr;
    void (*init)() = nullptr;
    void (*deinit)() = nullptr;
    void (*get_system_info)(retro_system_info*) = nullptr;
    void (*get_system_av_info)(retro_system_av_info*) = nullptr;
    void (*set_environment)(retro_environment_t) = nullptr;
    void (*set_video_refresh)(retro_video_refresh_t) = nullptr;
    void (*set_audio_sample)(retro_audio_sample_t) = nullptr;
    void (*set_audio_sample_batch)(retro_audio_sample_batch_t) = nullptr;
    void (*set_input_poll)(retro_input_poll_t) = nullptr;
    void (*set_input_state)(retro_input_state_t) = nullptr;
    void (*set_controller_port_device)(unsigned, unsigned) = nullptr;
    bool (*load_game)(const retro_game_info*) = nullptr;
    void (*unload_game)() = nullptr;
    void (*run)() = nullptr;
    size_t (*serialize_size)() = nullptr;
    bool (*serialize)(void*, size_t) = nullptr;
    bool (*unserialize)(const void*, size_t) = nullptr;
    void* (*get_memory_data)(unsigned) = nullptr;
    size_t (*get_memory_size)(unsigned) = nullptr;

    template <typename T>
    bool load_symbol(const char* name, T& target, std::string& error) {
        target = reinterpret_cast<T>(dlsym(handle, name));
        if (target) return true;
        error = std::string("Bundled libretro core is missing required symbol ") + name;
        return false;
    }

    template <typename T>
    void load_optional_symbol(const char* name, T& target) {
        target = reinterpret_cast<T>(dlsym(handle, name));
    }

    bool open(const char* path, std::string& error) {
        handle = dlopen(path, RTLD_NOW | RTLD_LOCAL);
        if (!handle) {
            error = std::string("Cannot load bundled native core: ") + (dlerror() ?: "unknown loader error");
            return false;
        }
        const bool required = load_symbol("retro_api_version", api_version, error) &&
                              load_symbol("retro_init", init, error) &&
                              load_symbol("retro_deinit", deinit, error) &&
                              load_symbol("retro_get_system_info", get_system_info, error) &&
                              load_symbol("retro_get_system_av_info", get_system_av_info, error) &&
                              load_symbol("retro_set_environment", set_environment, error) &&
                              load_symbol("retro_set_video_refresh", set_video_refresh, error) &&
                              load_symbol("retro_set_audio_sample", set_audio_sample, error) &&
                              load_symbol("retro_set_audio_sample_batch", set_audio_sample_batch, error) &&
                              load_symbol("retro_set_input_poll", set_input_poll, error) &&
                              load_symbol("retro_set_input_state", set_input_state, error) &&
                              load_symbol("retro_set_controller_port_device", set_controller_port_device, error) &&
                              load_symbol("retro_load_game", load_game, error) &&
                              load_symbol("retro_unload_game", unload_game, error) &&
                              load_symbol("retro_run", run, error);
        if (!required) return false;
        // State functions are optional in the libretro ABI. Their bytes stay
        // untouched when available; a core that omits them simply exposes no
        // quick-state controls instead of receiving a frontend-specific
        // wrapper or conversion.
        load_optional_symbol("retro_serialize_size", serialize_size);
        load_optional_symbol("retro_serialize", serialize);
        load_optional_symbol("retro_unserialize", unserialize);
        load_optional_symbol("retro_get_memory_data", get_memory_data);
        load_optional_symbol("retro_get_memory_size", get_memory_size);
        if (!get_memory_data || !get_memory_size) {
            get_memory_data = nullptr;
            get_memory_size = nullptr;
        }
        return true;
    }

    void close() {
        if (handle) dlclose(handle);
        *this = {};
    }

    bool supports_states() const {
        return serialize_size && serialize && unserialize;
    }
};

static bool start_audio(double sample_rate);
static void stop_audio();
static void submit_audio(const int16_t* data, size_t frames);
static void append_audio_sample(int16_t left, int16_t right);
static void flush_pending_audio_samples();
static void note_audio_batch_callback(size_t frames);
static void note_audio_underrun();
static void set_audio_speed(double multiplier);
static void set_audio_latency_ms(unsigned latency_ms);
static void set_audio_resampler_quality(unsigned quality);

struct NativeScreenLayout {
    const char* id;
    const char* label;
    // The exact token the libretro core accepts for this layout.
    const char* coreValue;
};

// Built from shared/generated/native_layouts.h, which is generated from the one
// layout schema (Android reads that JSON directly). `id` is the persisted
// preference; `coreValue` is the token the core option expects.
template <typename Source>
static std::vector<NativeScreenLayout> build_native_layouts(const Source& source) {
    std::vector<NativeScreenLayout> layouts;
    layouts.reserve(source.size());
    for (const auto& item : source) {
        layouts.push_back({item.id.data(), item.label.data(), item.core_value.data()});
    }
    return layouts;
}

static const std::vector<NativeScreenLayout>& native_screen_layouts(const std::string& system) {
    static const std::vector<NativeScreenLayout> kNoLayouts;
    static const std::vector<NativeScreenLayout> kNdsLayouts = build_native_layouts(an3::native_layouts::nds);
    static const std::vector<NativeScreenLayout> kThreeDsLayouts = build_native_layouts(an3::native_layouts::three_ds);
    if (system == "nds") return kNdsLayouts;
    if (system == "3ds") return kThreeDsLayouts;
    return kNoLayouts;
}

static const NativeScreenLayout* find_native_layout(const std::string& system, const std::string& layout) {
    for (const auto& candidate : native_screen_layouts(system)) {
        if (layout == candidate.id) return &candidate;
    }
    return nullptr;
}

// Legacy canonical spellings map onto the schema ids so a preference stored by
// an earlier build keeps working after the layout list grew.
static std::string canonical_native_layout(const std::string& system, const std::string& layout) {
    if (layout == "side_by_side") return find_native_layout(system, "left-right") ? "left-right" : std::string();
    if (layout == "top_bottom") return find_native_layout(system, "top-bottom") ? "top-bottom" : std::string();
    return find_native_layout(system, layout) ? layout : std::string();
}

static const char* native_layout_core_value(const std::string& system, const std::string& layout) {
    if (const NativeScreenLayout* found = find_native_layout(system, layout)) return found->coreValue;
    const auto& layouts = native_screen_layouts(system);
    return layouts.empty() ? "" : layouts.front().coreValue;
}

static std::string native_layout_preference(const std::string& system, const char* requested_layout) {
    if (system != "nds" && system != "3ds") return "default";
    const std::string requested = requested_layout ? requested_layout : "preserve";
    if (const std::string canonical = canonical_native_layout(system, requested); !canonical.empty()) return canonical;
    // Reading a preference is deliberately side-effect free. In particular,
    // opening Settings or receiving an unspecified layout from the web shell
    // must never replace a valid landscape choice with a portrait default.
    NSString* key = [NSString stringWithFormat:@"an3.native-screen-layout.v1.%s", system.c_str()];
    NSString* stored = [[NSUserDefaults standardUserDefaults] stringForKey:key];
    if (stored) {
        if (const std::string canonical = canonical_native_layout(system, stored.UTF8String ?: ""); !canonical.empty()) return canonical;
    }
    // The pre-regression native landscape default was side-by-side. Do not
    // infer the layout from transient window dimensions.
    return native_screen_layouts(system).front().id;
}

static void persist_native_layout_preference(NSString* system, NSString* layout) {
    if (!([system isEqualToString:@"nds"] || [system isEqualToString:@"3ds"])) return;
    const std::string canonical = canonical_native_layout(system.UTF8String ?: "", layout.UTF8String ?: "");
    if (canonical.empty()) return;
    NSString* key = [NSString stringWithFormat:@"an3.native-screen-layout.v1.%@", system];
    [[NSUserDefaults standardUserDefaults] setObject:[NSString stringWithUTF8String:canonical.c_str()] forKey:key];
}

static std::string core_option_namespace_for_system(const std::string& system) {
    if (system == "gba") return "mgba";
    if (system == "nds") return "melondsds";
    if (system == "3ds") return "azahar";
    return system;
}

// Resolve the persisted Auto Save token from the shared model/parser below.
static NSString* native_stored_auto_save_mode();

class AzaharHost {
  public:
    bool start(const char* core_path,
               const char* moltenvk_path,
               const char* rom_path,
               const char* rom_id,
               const char* save_path,
               const char* system_path,
               const char* system,
               const char* layout_path,
               CAMetalLayer* metal_layer,
               std::string& error) {
        input_ready_.store(false, std::memory_order_release);
        active_system_code_.store(0, std::memory_order_release);
        an3_native_controller_utilities_accepting(0);
        core_path_ = core_path ?: "";
        moltenvk_path_ = moltenvk_path ?: "";
        rom_path_ = rom_path ?: "";
        rom_id_ = rom_id ?: "";
        save_path_ = save_path ?: "";
        system_path_ = system_path ?: "";
        system_ = system ?: "";
        layout_ = layout_path ?: "preserve";
        if (core_path_.empty() || moltenvk_path_.empty() || rom_path_.empty() || rom_id_.empty() || save_path_.empty() ||
            system_path_.empty() || system_.empty() || !metal_layer) {
            error = "The native player did not receive a valid core, Vulkan runtime, ROM identity, save path, system path, and native view.";
            return false;
        }
        if (!std::all_of(rom_id_.begin(), rom_id_.end(), [](unsigned char value) {
                return (value >= 'a' && value <= 'z') || (value >= 'A' && value <= 'Z') ||
                       (value >= '0' && value <= '9') || value == '-' || value == '_';
            })) {
            error = "The native player received an invalid local ROM identity.";
            return false;
        }
        if (system_ != "gba" && system_ != "nds" && system_ != "3ds") {
            error = "Unsupported native system requested.";
            return false;
        }
        layout_ = native_layout_preference(system_, layout_path);
        emulate_timings_.reset();
        if (!core_.open(core_path_.c_str(), error)) return false;

        core_options_.reset(core_option_namespace_for_system(system_));
        speed_ = 1.0;
        speed_budget_ = 0.0;
        active_game_seconds_ = 0.0;
        last_save_ram_game_seconds_ = 0.0;
        save_ram_writable_ = true;
        pending_save_ram_restore_size_ = 0;
        last_autosave_game_seconds_ = 0.0;
        // One shared Auto Save token, resolved through the same
        // native-runtime/core/auto_save_mode.h parser Android and Linux use.
        {
            NSString* stored_mode = native_stored_auto_save_mode();
            auto parsed = an3::parse_auto_save_mode(std::string(stored_mode.UTF8String ?: "off"));
            if (!parsed) parsed = an3::parse_auto_save_mode("off");
            auto_save_enabled_ = parsed->enabled;
            auto_save_on_exit_ = parsed->on_exit;
            auto_save_interval_seconds_ = parsed->enabled ? std::max(1u, parsed->interval) : 60u;
        }
        set_audio_speed(1.0);

        core_.set_environment(environment_callback);
        core_.set_video_refresh(video_callback);
        core_.set_audio_sample(audio_callback);
        core_.set_audio_sample_batch(audio_batch_callback);
        core_.set_input_poll(input_poll_callback);
        core_.set_input_state(input_state_callback);
        core_.init();
        initialized_ = true;

        // Core options are discovered from the core before load_game. Restore
        // only values announced by this core and namespace them by system so
        // unrelated cores never inherit one another's settings.
        for (const auto& option : core_options_.options()) {
            NSString* defaults_key = [NSString stringWithFormat:@"an3.native-core-option.%@.%s",
                                      [NSString stringWithUTF8String:core_options_.core_namespace().c_str()], option.key.c_str()];
            NSString* stored = [[NSUserDefaults standardUserDefaults] stringForKey:defaults_key];
            // The generic UI originally used the system label as its key.
            // Read that bounded legacy value once, but all future writes use
            // the actual core namespace so similarly named options cannot
            // cross-contaminate cores.
            if (!stored) {
                NSString* legacy_key = [NSString stringWithFormat:@"an3.native-core-option.%@.%s",
                                        [NSString stringWithUTF8String:system_.c_str()], option.key.c_str()];
                stored = [[NSUserDefaults standardUserDefaults] stringForKey:legacy_key];
            }
            if (stored) {
                core_options_.set_initial(option.key, stored.UTF8String ?: "");
            }
        }
        if (system_ == "nds") {
            // Keep the core's own option snapshot consistent with the
            // protected per-system layout. Some melonDS versions retain that
            // snapshot through content load before asking GET_VARIABLE again.
            // This is an in-memory launch value only: it never persists or
            // overwrites an unrelated generic Core Options preference. Mark
            // it updated so the core cannot keep the top/bottom snapshot it
            // announced before content was loaded.
            (void)core_options_.set("melonds_number_of_screen_layouts", "1");
            (void)core_options_.set("melonds_screen_layout1",
                                    native_layout_core_value(system_, layout_));
        } else if (system_ == "3ds") {
            // Keep the displayed Azahar option and the protected host launch
            // preference in agreement. The renderer still receives the
            // native GPU image; this only updates the core's layout value.
            (void)core_options_.set("citra_layout_option", native_layout_core_value(system_, layout_));
        }

        retro_system_info info{};
        core_.get_system_info(&info);
        retro_game_info game{rom_path_.c_str(), nullptr, 0, nullptr};
        if (!info.need_fullpath) {
            std::ifstream input(rom_path_, std::ios::binary | std::ios::ate);
            const std::streamoff size = input ? static_cast<std::streamoff>(input.tellg()) : -1;
            if (size <= 0 || static_cast<uintmax_t>(size) > std::numeric_limits<size_t>::max()) {
                error = "The native core needs readable local ROM data, but the selected file could not be loaded.";
                stop();
                return false;
            }
            input.seekg(0, std::ios::beg);
            rom_data_.resize(static_cast<size_t>(size));
            if (!input.read(reinterpret_cast<char*>(rom_data_.data()), static_cast<std::streamsize>(size))) {
                error = "The native core could not read the selected local ROM data.";
                stop();
                return false;
            }
            game.data = rom_data_.data();
            game.size = rom_data_.size();
        }
        if (!core_.load_game(&game)) {
            error = message_.empty()
                ? "The bundled native core rejected this local ROM. It may be encrypted, unsupported, or missing required system files."
                : message_;
            stop();
            return false;
        }
        game_loaded_ = true;
        restore_save_ram();

        retro_system_av_info av_info{};
        core_.get_system_av_info(&av_info);
        if (!start_audio(av_info.timing.sample_rate)) {
            error = "The native core reported an invalid audio sample rate or the output audio graph could not start.";
            stop();
            return false;
        }

        if (system_ == "3ds") {
            if (!has_hardware_callbacks_ || !negotiation_interface_) {
                error = "The bundled Azahar core did not negotiate its required Vulkan renderer.";
                stop();
                return false;
            }
            if (!vulkan_.initialize((__bridge void*)metal_layer, moltenvk_path_.c_str(), hardware_callbacks_,
                                     negotiation_interface_, error)) {
                stop();
                return false;
            }
            if (!hardware_callbacks_.context_reset) {
                error = "Azahar did not provide a Vulkan context-reset callback.";
                stop();
                return false;
            }
            hardware_callbacks_.context_reset();
        } else if (!vulkan_.initialize_software((__bridge void*)metal_layer, moltenvk_path_.c_str(), error)) {
            stop();
            return false;
        }
        renderer_initialized_ = true;
        {
            std::lock_guard<std::mutex> lock(state_mutex_);
            running_ = true;
            const int system_code = (system_ == "gba" || system_ == "gb" || system_ == "gbc")
                                        ? 1
                                        : system_ == "nds" ? 2 : system_ == "3ds" ? 3 : 0;
            active_system_code_.store(system_code, std::memory_order_release);
            an3_native_controller_utilities_accepting(1);
            input_ready_.store(true, std::memory_order_release);
        }
        return true;
    }

    void stop() {
        menu_navigation_active_.store(false, std::memory_order_relaxed);
        input_ready_.store(false, std::memory_order_release);
        active_system_code_.store(0, std::memory_order_release);
        an3_native_controller_utilities_accepting(0);
        std::lock_guard<std::mutex> lock(state_mutex_);
        drain_controller_utilities_locked();
        if (running_ && auto_save_enabled_) {
            std::string save_error;
            if (!save_auto_state_locked(save_error, true) && !save_error.empty()) message_ = save_error;
        }
        running_ = false;
        // The libretro Vulkan contract keeps image/semaphore ownership with
        // the frontend until it consumes the frame. Drain it while the core
        // context is still valid, before context_destroy invalidates handles.
        if (renderer_initialized_) vulkan_.discard_pending_core_frame();
        if (renderer_initialized_ && hardware_callbacks_.context_destroy) {
            hardware_callbacks_.context_destroy();
        }
        renderer_initialized_ = false;
        const bool unload_game = game_loaded_ && static_cast<bool>(core_.unload_game);
        if (unload_game) {
            std::string save_error;
            if (!flush_save_ram_locked(save_error, true) && !save_error.empty()) message_ = save_error;
        }
        std::string persistence_error;
        if (!persistence_writer_.flush(persistence_error) && !persistence_error.empty()) message_ = persistence_error;
        if (unload_game) core_.unload_game();
        const std::string background_error = persistence_writer_.take_background_error();
        if (!background_error.empty()) message_ = background_error;
        game_loaded_ = false;
        if (initialized_ && core_.deinit) core_.deinit();
        initialized_ = false;
        stop_audio();
        vulkan_.shutdown();
        core_.close();
        hardware_callbacks_ = {};
        has_hardware_callbacks_ = false;
        negotiation_interface_ = nullptr;
        rom_data_.clear();
        rom_id_.clear();
        system_.clear();
        last_video_width_ = 0;
        last_video_height_ = 0;
        last_draw_time_ = {};
        speed_budget_ = 0.0;
        pixel_format_ = RETRO_PIXEL_FORMAT_RGB565;
        mouse_delta_x_.store(0, std::memory_order_relaxed);
        mouse_delta_y_.store(0, std::memory_order_relaxed);
    }

    bool running() const {
        std::lock_guard<std::mutex> lock(state_mutex_);
        return running_;
    }
    bool controller_input_ready() const { return input_ready_.load(std::memory_order_acquire); }
    int active_system_code() const { return active_system_code_.load(std::memory_order_acquire); }
    bool is_nds() const { return system_ == "nds"; }
    const std::string& system_name() const { return system_; }
    const std::string& layout() const { return layout_; }
    bool set_screen_layout(const std::string& requested, std::string& error) {
        std::lock_guard<std::mutex> lock(state_mutex_);
        if (!running_ || (system_ != "nds" && system_ != "3ds")) {
            error = "Screen layout is available only while an NDS or 3DS game is running.";
            return false;
        }
        const std::string layout = canonical_native_layout(system_, requested);
        if (layout.empty()) {
            error = "Unknown screen layout.";
            return false;
        }
        layout_ = layout;
        const char* key = system_ == "nds" ? "melonds_screen_layout1" : "citra_layout_option";
        // A few older cores do not include the layout item in their editable
        // list, so GET_VARIABLE remains authoritative. Always signal the
        // update, letting the current retro_run recompute frame and touch
        // geometry immediately rather than waiting for relaunch.
        (void)core_options_.set(key, native_layout_core_value(system_, layout_));
        core_options_.mark_updated();
        return true;
    }
    uint64_t presented_frames() const { return vulkan_.presented_frames(); }
    NativeRendererMetrics renderer_metrics() const;
    bool supports_quick_states() const {
        std::lock_guard<std::mutex> lock(state_mutex_);
        return running_ && core_.supports_states();
    }
    const std::vector<CoreOption>& core_options() const { return core_options_.options(); }
    bool set_core_option(const std::string& key, const std::string& value, std::string& error);
    double speed() const {
        std::lock_guard<std::mutex> lock(state_mutex_);
        return speed_;
    }
    void set_speed(double multiplier);
    bool auto_save_enabled() const {
        std::lock_guard<std::mutex> lock(state_mutex_);
        return auto_save_enabled_;
    }
    bool auto_save_on_exit() const {
        std::lock_guard<std::mutex> lock(state_mutex_);
        return auto_save_on_exit_;
    }
    unsigned auto_save_interval_seconds() const {
        std::lock_guard<std::mutex> lock(state_mutex_);
        return auto_save_interval_seconds_;
    }
    bool flush_save_ram(std::string& error) {
        std::lock_guard<std::mutex> lock(state_mutex_);
        return flush_save_ram_locked(error, true);
    }
    void set_auto_save_enabled(bool enabled) {
        std::lock_guard<std::mutex> lock(state_mutex_);
        auto_save_enabled_ = enabled;
    }
    void set_auto_save_on_exit(bool enabled) {
        std::lock_guard<std::mutex> lock(state_mutex_);
        auto_save_on_exit_ = enabled;
    }
    void set_auto_save_interval_seconds(unsigned seconds) {
        std::lock_guard<std::mutex> lock(state_mutex_);
        auto_save_interval_seconds_ = std::clamp(seconds, 1u, 3600u);
    }
    std::filesystem::path auto_save_file_path() const {
        std::lock_guard<std::mutex> lock(state_mutex_);
        return std::filesystem::path(save_path_) / "states" / (rom_id_ + ".autosave.state");
    }
    bool save_auto_state(std::string& error);
    bool load_auto_state(std::string& error);

    bool export_state(const std::filesystem::path& path, std::string& error) {
        std::lock_guard<std::mutex> lock(state_mutex_);
        std::vector<uint8_t> bytes;
        if (!serialize_state(bytes, error)) return false;
        if (path.empty() || path.filename().empty()) {
            error = "Choose a valid .state export filename.";
            return false;
        }
        return persistence_writer_.write_and_wait(path, std::move(bytes), "save state", error);
    }

    bool import_state(const std::filesystem::path& path, std::string& error) {
        std::lock_guard<std::mutex> lock(state_mutex_);
        if (!running_ || !core_.supports_states()) {
            error = "This native core does not provide save states.";
            return false;
        }
        std::error_code filesystem_error;
        if (!std::filesystem::is_regular_file(path, filesystem_error) || filesystem_error) {
            error = "Choose a readable .state file.";
            return false;
        }
        const auto size = std::filesystem::file_size(path, filesystem_error);
        if (filesystem_error || size == 0 || size > kMaxQuickStateBytes) {
            error = "This save state is empty or exceeds the 512 MiB safety limit.";
            return false;
        }
        std::ifstream input(path, std::ios::binary);
        if (!input) {
            error = "VibeCodedEmulator could not read this save state.";
            return false;
        }
        std::vector<uint8_t> bytes(static_cast<size_t>(size));
        if (!input.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()))) {
            error = "VibeCodedEmulator could not read this save state completely.";
            return false;
        }
        if (!core_.unserialize(bytes.data(), bytes.size())) {
            error = "The current native core rejected this save state as incompatible.";
            return false;
        }
        return true;
    }

    bool save_state(unsigned slot, std::string& error) {
        std::lock_guard<std::mutex> lock(state_mutex_);
        return save_state_locked(slot, error, true);
    }

    bool save_state_locked(unsigned slot,
                           std::string& error,
                           bool wait_for_write,
                           SavePersistenceWorker::AsyncCompletion async_completion = {}) {
        if (!validate_state_slot(slot, error)) return false;
        std::vector<uint8_t> bytes;
        if (!serialize_state(bytes, error)) return false;
        const std::filesystem::path path = quick_state_path(slot);
        return persist_bytes_locked(path, std::move(bytes), "save state", wait_for_write, error,
                                    std::move(async_completion));
    }

    bool load_state(unsigned slot, std::string& error) {
        std::lock_guard<std::mutex> lock(state_mutex_);
        return load_state_locked(slot, error);
    }

    bool load_state_locked(unsigned slot, std::string& error) {
        if (!validate_state_slot(slot, error)) return false;
        const std::filesystem::path path = quick_state_path(slot);
        std::ifstream input(path, std::ios::binary | std::ios::ate);
        const std::streamoff size = input ? static_cast<std::streamoff>(input.tellg()) : -1;
        if (size <= 0 || static_cast<uintmax_t>(size) > kMaxQuickStateBytes) {
            error = "This quick-save slot is empty or invalid.";
            return false;
        }
        input.seekg(0, std::ios::beg);
        std::vector<uint8_t> bytes(static_cast<size_t>(size));
        if (!input.read(reinterpret_cast<char*>(bytes.data()), size)) {
            error = "VibeCodedEmulator could not read this quick save.";
            return false;
        }
        if (!core_.unserialize(bytes.data(), bytes.size())) {
            error = "The native core rejected this quick save.";
            return false;
        }
        return true;
    }

    void set_input(uint32_t buttons,
                   int16_t circle_x,
                   int16_t circle_y,
                   int16_t cstick_x,
                   int16_t cstick_y,
                   int16_t touch_x,
                   int16_t touch_y,
                   bool touch_pressed) {
        buttons_.store(buttons, std::memory_order_relaxed);
        circle_x_.store(circle_x, std::memory_order_relaxed);
        circle_y_.store(circle_y, std::memory_order_relaxed);
        cstick_x_.store(cstick_x, std::memory_order_relaxed);
        cstick_y_.store(cstick_y, std::memory_order_relaxed);
        touch_x_.store(touch_x, std::memory_order_relaxed);
        touch_y_.store(touch_y, std::memory_order_relaxed);
        touch_pressed_.store(touch_pressed, std::memory_order_relaxed);
    }

    uint32_t controller_buttons() const {
        return buttons_.load(std::memory_order_relaxed);
    }

    void set_menu_navigation_active(bool active) {
        menu_navigation_active_.store(active, std::memory_order_relaxed);
    }

    void move_nds_cursor(float delta_x, float delta_y) {
        if (!is_nds()) return;
        // The Pointer device receives absolute values in [-32767, 32767]. A
        // 400-point-wide display maps naturally across the 256-pixel touch
        // screen while still allowing precise relative mouse movement.
        constexpr float normalized_per_point = 163.835f;
        const auto update_axis = [](std::atomic<int16_t>& axis, int16_t delta) {
            const int current = axis.load(std::memory_order_relaxed);
            const int next = std::clamp(current + static_cast<int>(delta), -32767, 32767);
            axis.store(static_cast<int16_t>(next), std::memory_order_relaxed);
        };
        update_axis(touch_x_, input_contract::relative_axis(delta_x, normalized_per_point));
        update_axis(touch_y_, input_contract::relative_axis(delta_y, normalized_per_point));
        const auto update_mouse_delta = [](std::atomic<int16_t>& axis, int16_t delta) {
            const int current = axis.load(std::memory_order_relaxed);
            const int next = std::clamp(current + static_cast<int>(delta), -32767, 32767);
            axis.store(static_cast<int16_t>(next), std::memory_order_relaxed);
        };
        // The maintained melonDS DS core uses Pointer mode. Also publish a
        // relative Mouse delta for libretro builds that select Mouse mode;
        // this makes the lock semantics forward-compatible without relying on
        // a separately launched frontend.
        update_mouse_delta(mouse_delta_x_, input_contract::relative_axis(delta_x));
        update_mouse_delta(mouse_delta_y_, input_contract::relative_axis(delta_y));
    }

    void set_nds_touch_pressed(bool pressed) {
        if (!is_nds()) return;
        touch_pressed_.store(pressed, std::memory_order_relaxed);
    }

    void set_button(unsigned button, bool pressed) {
        if (button >= 32) return;
        const uint32_t mask = 1u << button;
        if (pressed) buttons_.fetch_or(mask, std::memory_order_relaxed);
        else buttons_.fetch_and(~mask, std::memory_order_relaxed);
    }

    void set_circle(int16_t x, int16_t y) {
        circle_x_.store(x, std::memory_order_relaxed);
        circle_y_.store(y, std::memory_order_relaxed);
    }

    void clear_input() {
        buttons_.store(0, std::memory_order_relaxed);
        circle_x_.store(0, std::memory_order_relaxed);
        circle_y_.store(0, std::memory_order_relaxed);
        cstick_x_.store(0, std::memory_order_relaxed);
        cstick_y_.store(0, std::memory_order_relaxed);
        touch_x_.store(0, std::memory_order_relaxed);
        touch_y_.store(0, std::memory_order_relaxed);
        touch_pressed_.store(false, std::memory_order_relaxed);
        mouse_delta_x_.store(0, std::memory_order_relaxed);
        mouse_delta_y_.store(0, std::memory_order_relaxed);
    }

    void set_touch_from_view(NSPoint point, NSSize size, bool pressed) {
        const auto clear_touch = [this] {
            touch_x_.store(0, std::memory_order_relaxed);
            touch_y_.store(0, std::memory_order_relaxed);
            touch_pressed_.store(false, std::memory_order_relaxed);
        };
        const float view_width = std::max<CGFloat>(size.width, 1.0);
        const float view_height = std::max<CGFloat>(size.height, 1.0);
        const float frame_width = std::max(1u, last_video_width_);
        const float frame_height = std::max(1u, last_video_height_);
        if (!last_video_width_ || !last_video_height_) {
            clear_touch();
            return;
        }
        const float scale = std::min(view_width / frame_width, view_height / frame_height);
        const float displayed_width = frame_width * scale;
        const float displayed_height = frame_height * scale;
        const float left = (view_width - displayed_width) * 0.5f;
        const float top = (view_height - displayed_height) * 0.5f;
        const float cursor_x = static_cast<float>(point.x);
        const float cursor_y = view_height - static_cast<float>(point.y);
        if (cursor_x < left || cursor_x > left + displayed_width || cursor_y < top ||
            cursor_y > top + displayed_height) {
            clear_touch();
            return;
        }
        const float framebuffer_x = (cursor_x - left) / scale;
        const float framebuffer_y = (cursor_y - top) / scale;
        // The core is fixed to resolution factor 1 and a zero screen gap. Its
        // lower touchscreen lives in these composite-frame rectangles:
        // default: [40,360) x [240,480); side by side: [400,720) x [0,240).
        // Keep pointer coordinates normalized against the entire composite,
        // because Azahar's mouse tracker performs the lower-screen-local
        // conversion after this hit test.
        const bool side_by_side = layout_ == "left-right";
        const float base_width = side_by_side ? 720.0f : 400.0f;
        const float base_height = side_by_side ? 240.0f : 480.0f;
        const float scale_x = frame_width / base_width;
        const float scale_y = frame_height / base_height;
        const float touch_left = (side_by_side ? 400.0f : 40.0f) * scale_x;
        const float touch_right = (side_by_side ? 720.0f : 360.0f) * scale_x;
        const float touch_top = (side_by_side ? 0.0f : 240.0f) * scale_y;
        const float touch_bottom = (side_by_side ? 240.0f : 480.0f) * scale_y;
        if (framebuffer_x < touch_left || framebuffer_x >= touch_right || framebuffer_y < touch_top ||
            framebuffer_y >= touch_bottom) {
            clear_touch();
            return;
        }
        touch_x_.store(input_contract::absolute_axis(framebuffer_x, frame_width), std::memory_order_relaxed);
        touch_y_.store(input_contract::absolute_axis(framebuffer_y, frame_height), std::memory_order_relaxed);
        touch_pressed_.store(pressed, std::memory_order_relaxed);
    }

    void draw() {
        std::lock_guard<std::mutex> lock(state_mutex_);
        if (!running_ || !core_.run || !vulkan_.ready()) return;
        process_controller_utility_locked();
        // At normal speed preserve the historical scheduler: one core frame
        // per MTKView callback. Fractional wall-clock budgeting at 1x causes
        // ordinary timer jitter to alternate 0/2 runs, delaying NDS input
        // polls and making cursor movement visibly step.
        unsigned runs = 1;
        if (std::abs(speed_ - 1.0) >= 0.001) {
            const auto now = std::chrono::steady_clock::now();
            if (last_draw_time_.time_since_epoch().count() == 0) last_draw_time_ = now;
            const double elapsed = std::clamp(std::chrono::duration<double>(now - last_draw_time_).count(), 0.0, 0.25);
            last_draw_time_ = now;
            speed_budget_ = std::min(8.0, speed_budget_ + elapsed * kNominalCoreFps * speed_);
            runs = static_cast<unsigned>(std::floor(speed_budget_));
            speed_budget_ -= static_cast<double>(runs);
        } else {
            last_draw_time_ = std::chrono::steady_clock::now();
            speed_budget_ = 0.0;
        }
        for (unsigned index = 0; index < std::min(runs, 8u); ++index) {
            const auto began = std::chrono::steady_clock::now();
            core_.run();
            resolve_pending_save_ram_restore();
            flush_pending_audio_samples();
            emulate_timings_.add(std::chrono::steady_clock::now() - began);
            active_game_seconds_ += 1.0 / kNominalCoreFps;
            if (auto_save_enabled_ && active_game_seconds_ - last_autosave_game_seconds_ >= auto_save_interval_seconds_) {
                std::string save_error;
                if (save_auto_state_locked(save_error, false)) last_autosave_game_seconds_ = active_game_seconds_;
                else if (!save_error.empty()) message_ = save_error;
            }
            if (active_game_seconds_ - last_save_ram_game_seconds_ >= 5.0) {
                std::string save_error;
                if (!flush_save_ram_locked(save_error, false) && !save_error.empty()) message_ = save_error;
                const std::string background_error = persistence_writer_.take_background_error();
                if (!background_error.empty()) message_ = background_error;
                last_save_ram_game_seconds_ = active_game_seconds_;
            }
        }
        note_audio_underrun();
    }

  private:
    void set_speed_locked(double multiplier) {
        constexpr double kSpeeds[] = {0.5, 1.0, 2.0, 4.0, 8.0};
        double selected = 1.0;
        for (const double candidate : kSpeeds) {
            if (std::abs(candidate - multiplier) < 0.001) selected = candidate;
        }
        if (std::abs(selected - speed_) < 0.001) return;
        speed_ = selected;
        speed_budget_ = 0.0;
        set_audio_speed(speed_);
    }

    bool process_controller_utility_locked() {
        uint32_t action = 0;
        uint32_t slot = 1;
        char command_id_buffer[129] = {};
        if (an3_native_take_controller_utility(&action, &slot, command_id_buffer,
                                               sizeof(command_id_buffer)) <= 0) return false;
        const std::string command_id(command_id_buffer);
        std::string error;
        bool applied = false;
        bool completion_deferred = false;
        switch (action) {
            case 1: { // QUICK_SAVE
                const auto completion = [command_id, slot](bool success, const std::string& detail) {
                    const std::string message = success
                        ? "Quick save complete."
                        : (detail.empty() ? "Quick save failed." : detail);
                    an3_native_controller_utility_completed(command_id.c_str(), 1, slot,
                                                            success ? 1 : 0, message.c_str());
                };
                applied = save_state_locked(slot, error, false, completion);
                completion_deferred = applied;
                if (applied) message_ = "Quick save pending.";
                break;
            }
            case 2: // QUICK_LOAD
                applied = persistence_writer_.flush(error) && load_state_locked(slot, error);
                if (applied) error = "Quick load complete.";
                break;
            case 3: // SPEED_UP
            case 4: { // SPEED_DOWN
                constexpr double kSpeeds[] = {0.5, 1.0, 2.0, 4.0, 8.0};
                int index = 1;
                for (int step = 0; step < 5; ++step) {
                    if (std::abs(kSpeeds[step] - speed_) < 0.001) index = step;
                }
                index = std::clamp(index + (action == 3 ? 1 : -1), 0, 4);
                set_speed_locked(kSpeeds[index]);
                if (an3::g_view) {
                    dispatch_async(dispatch_get_main_queue(), ^{
                        if (an3::g_view) [an3::g_view syncSpeedControls];
                    });
                }
                applied = true;
                error = "Speed changed.";
                break;
            }
            case 5: // OPEN_MENU
                if (!an3::g_view) {
                    error = "The native player menu is unavailable.";
                } else {
                    const auto result_id = std::make_shared<std::string>(command_id);
                    const uint32_t result_slot = slot;
                    dispatch_async(dispatch_get_main_queue(), ^{
                        const bool opened = an3::g_view != nil;
                        if (opened) [an3::g_view openMenu];
                        const char* message = opened ? "Menu opened." : "The native player menu is unavailable.";
                        an3_native_controller_utility_completed(result_id->c_str(), 5, result_slot,
                                                                opened ? 1 : 0, message);
                    });
                    completion_deferred = true;
                }
                break;
            default:
                error = "The controller utility queue contained an unknown action.";
                break;
        }
        if (!completion_deferred) {
            if (!applied && error.empty()) error = "The controller utility could not be applied.";
            if (!applied) message_ = error;
            an3_native_controller_utility_completed(command_id.c_str(), action, slot,
                                                    applied ? 1 : 0, error.c_str());
        }
        return true;
    }

    void drain_controller_utilities_locked() {
        while (process_controller_utility_locked()) {
            // Stop has already disabled queue acceptance, so the shutdown
            // drain is finite and preserves every accepted discrete action.
        }
    }

    bool persist_bytes_locked(const std::filesystem::path& path,
                              std::vector<uint8_t> bytes,
                              const std::string& description,
                              bool wait_for_write,
                              std::string& error,
                              SavePersistenceWorker::AsyncCompletion async_completion = {}) {
        if (wait_for_write) {
            return persistence_writer_.write_and_wait(path, std::move(bytes), description, error);
        }
        if (async_completion) {
            return persistence_writer_.write_async_with_completion(
                path, std::move(bytes), description, std::move(async_completion), error);
        }
        return persistence_writer_.write_async(path, std::move(bytes), description, error);
    }

    bool flush_save_ram_locked(std::string& error, bool wait_for_write) {
        if (!game_loaded_ || !core_.get_memory_data || !core_.get_memory_size) return true;
        if (pending_save_ram_restore_size_ != 0) {
            error = "The existing cartridge save is waiting for the core to identify its memory size; it was preserved.";
            return false;
        }
        if (!save_ram_writable_) {
            error = "An existing battery save was invalid and has been preserved; saving is disabled for this session.";
            return false;
        }
        const auto size = core_.get_memory_size(RETRO_MEMORY_SAVE_RAM);
        void* data = core_.get_memory_data(RETRO_MEMORY_SAVE_RAM);
        if (!data || size == 0) return true;
        if (size > kMaxSaveRamBytes) {
            error = "The core reported an invalid battery-save size.";
            return false;
        }
        const auto* begin = static_cast<const uint8_t*>(data);
        std::vector<uint8_t> bytes(begin, begin + size);
        return persist_bytes_locked(std::filesystem::path(save_path_) / (rom_id_ + ".srm"),
                                    std::move(bytes), "cartridge save", wait_for_write, error);
    }

    bool save_auto_state_locked(std::string& error, bool wait_for_write);
    bool load_auto_state_locked(std::string& error);

    void restore_save_ram() {
        if (!core_.get_memory_data || !core_.get_memory_size) return;
        void* data = core_.get_memory_data(RETRO_MEMORY_SAVE_RAM);
        const auto size = core_.get_memory_size(RETRO_MEMORY_SAVE_RAM);
        if (!data || size == 0 || size > kMaxSaveRamBytes) return;
        const auto path = std::filesystem::path(save_path_) / (rom_id_ + ".srm");
        std::error_code filesystem_error;
        const auto file_status = std::filesystem::symlink_status(path, filesystem_error);
        if (filesystem_error == std::errc::no_such_file_or_directory) {
            return;
        }
        if (filesystem_error || !std::filesystem::is_regular_file(file_status)) {
            save_ram_writable_ = false;
            message_ = "The existing cartridge save is not a regular file; it was left untouched.";
            return;
        }
        const auto saved_size = std::filesystem::file_size(path, filesystem_error);
        if (filesystem_error || saved_size == 0 || saved_size > kMaxSaveRamBytes) {
            save_ram_writable_ = false;
            message_ = "The existing cartridge save has an invalid size; it was left untouched.";
            return;
        }
        const bool provisional_gba_buffer = saved_size != size && system_ == "gba" && saved_size < size;
        if (saved_size != size && !provisional_gba_buffer) {
            save_ram_writable_ = false;
            message_ = "The existing cartridge save does not match this core's save memory size; it was left untouched.";
            return;
        }
        std::ifstream input(path, std::ios::binary);
        std::vector<uint8_t> bytes(static_cast<size_t>(saved_size));
        if (!input || !input.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()))) {
            save_ram_writable_ = false;
            message_ = "The existing cartridge save could not be read and was left untouched.";
            return;
        }
        std::copy(bytes.begin(), bytes.end(), static_cast<uint8_t*>(data));
        if (provisional_gba_buffer) {
            pending_save_ram_restore_size_ = bytes.size();
            return;
        }
    }

    void resolve_pending_save_ram_restore() {
        if (pending_save_ram_restore_size_ == 0) return;
        void* data = core_.get_memory_data ? core_.get_memory_data(RETRO_MEMORY_SAVE_RAM) : nullptr;
        const auto size = core_.get_memory_size ? core_.get_memory_size(RETRO_MEMORY_SAVE_RAM) : 0;
        const auto expected_size = pending_save_ram_restore_size_;
        if (data && size == expected_size) {
            pending_save_ram_restore_size_ = 0;
            save_ram_writable_ = true;
            return;
        }
        pending_save_ram_restore_size_ = 0;
        save_ram_writable_ = false;
        message_ = "The core's detected cartridge-save size did not match the existing save; it was left untouched.";
    }

    bool validate_state_slot(unsigned slot, std::string& error) const {
        if (!running_ || !core_.supports_states()) {
            error = "This native core does not provide save states.";
            return false;
        }
        if (slot < 1 || slot > kMaxQuickStateSlot) {
            error = "Quick-save slots range from 1 to 10.";
            return false;
        }
        return true;
    }

    bool serialize_state(std::vector<uint8_t>& bytes, std::string& error) const {
        if (!running_ || !core_.supports_states()) {
            error = "This native core does not provide save states.";
            return false;
        }
        const size_t size = core_.serialize_size();
        if (!size || size > kMaxQuickStateBytes) {
            error = "This core reported an invalid save-state size.";
            return false;
        }
        bytes.resize(size);
        if (!core_.serialize(bytes.data(), bytes.size())) {
            error = "The native core could not create a save state.";
            bytes.clear();
            return false;
        }
        return true;
    }

    std::filesystem::path quick_state_path(unsigned slot) const {
        // The payload is exactly the core's serialized byte stream. Only its
        // file name is frontend-owned, keyed by the stable imported ROM id.
        return std::filesystem::path(save_path_) / "states" /
               (rom_id_ + ".slot" + std::to_string(slot) + ".state");
    }

    static bool environment_callback(unsigned command, void* data) {
        auto* host = active_host();
        return host ? host->environment(command, data) : false;
    }

    static void video_callback(const void* data, unsigned width, unsigned height, size_t pitch) {
        auto* host = active_host();
        if (host) host->on_video(data, width, height, pitch);
    }

    static void audio_callback(int16_t left, int16_t right) {
        append_audio_sample(left, right);
    }

    static size_t audio_batch_callback(const int16_t* data, size_t frames) {
        // A core may use either libretro audio callback style. Keep their
        // ordering intact if it switches from single samples to a batch.
        flush_pending_audio_samples();
        note_audio_batch_callback(frames);
        submit_audio(data, frames);
        return frames;
    }

    static void input_poll_callback() {}

    static int16_t input_state_callback(unsigned, unsigned device, unsigned index, unsigned id) {
        auto* host = active_host();
        return host ? host->input_state(device, index, id) : 0;
    }

    static void quiet_log(int, const char*, ...) {}

    bool environment(unsigned command, void* data) {
        switch (command) {
        case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
            *static_cast<const char**>(data) = system_path_.c_str();
            return true;
        case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
            *static_cast<const char**>(data) = save_path_.c_str();
            return true;
        case RETRO_ENVIRONMENT_GET_CONTENT_DIRECTORY:
            *static_cast<const char**>(data) = system_path_.c_str();
            return true;
        case RETRO_ENVIRONMENT_GET_LIBRETRO_PATH:
            *static_cast<const char**>(data) = core_path_.c_str();
            return true;
        case RETRO_ENVIRONMENT_GET_VARIABLE: {
            auto* variable = static_cast<retro_variable*>(data);
            if (!variable || !variable->key) return false;
            if (system_ == "3ds") {
                if (std::strcmp(variable->key, "citra_graphics_api") == 0) variable->value = "Vulkan";
                else if (std::strcmp(variable->key, "citra_layout_option") == 0) variable->value = native_layout_core_value(system_, layout_);
                else if (std::strcmp(variable->key, "citra_resolution_factor") == 0) variable->value = "1";
                else if (core_options_.get(variable->key, variable->value)) return true;
                else return false;
            }
            if (system_ == "nds") {
                // Native NDS emulation uses the core's efficient software
                // renderer; its frames are presented by Vulkan -> MoltenVK -> Metal.
                if (std::strcmp(variable->key, "melonds_render_mode") == 0) variable->value = "software";
                else if (std::strcmp(variable->key, "melonds_threaded_renderer") == 0) variable->value = "enabled";
                else if (std::strcmp(variable->key, "melonds_touch_mode") == 0) variable->value = "touch";
                else if (std::strcmp(variable->key, "melonds_show_cursor") == 0) variable->value = "always";
                else if (std::strcmp(variable->key, "melonds_number_of_screen_layouts") == 0) variable->value = "1";
                else if (std::strcmp(variable->key, "melonds_screen_layout1") == 0) {
                    variable->value = native_layout_core_value(system_, layout_);
                } else if (core_options_.get(variable->key, variable->value)) return true;
                else return false;
            }
            return core_options_.get(variable->key, variable->value);
        }
        case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT: {
            if (!data) return false;
            const int requested = *static_cast<const int*>(data);
            if (requested != RETRO_PIXEL_FORMAT_0RGB1555 && requested != RETRO_PIXEL_FORMAT_XRGB8888 &&
                requested != RETRO_PIXEL_FORMAT_RGB565) return false;
            pixel_format_ = requested;
            return true;
        }
        case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
        case RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME:
        case RETRO_ENVIRONMENT_SET_CONTROLLER_INFO:
        case RETRO_ENVIRONMENT_SET_GEOMETRY:
        case RETRO_ENVIRONMENT_SET_SERIALIZATION_QUIRKS:
            return true;
        case RETRO_ENVIRONMENT_SET_VARIABLES: {
            auto* variables = static_cast<retro_variable*>(data);
            if (!variables) return false;
            std::vector<const char*> entries;
            for (auto* variable = variables; variable->key; ++variable) {
                entries.push_back(variable->key);
                entries.push_back(variable->value);
            }
            entries.push_back(nullptr);
            core_options_.capture_legacy_variables(entries.data());
            return true;
        }
        case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2: {
            core_options_.capture_v2(static_cast<const RetroCoreOptionsV2*>(data));
            return true;
        }
        case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2_INTL: {
            auto* intl = static_cast<const RetroCoreOptionsIntl*>(data);
            // The international payload contains v2 containers. Parsing it
            // with the v1 layout shifts the values array into text pointers
            // and makes the AppKit Core Options popup crash at launch.
            if (intl) core_options_.capture_v2(intl->us ? intl->us : intl->local);
            return true;
        }
        case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:
            if (!data) return false;
            *static_cast<bool*>(data) = core_options_.consume_update();
            return true;
        case RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION:
            if (!data) return false;
            *static_cast<unsigned*>(data) = 2;
            return true;
        case RETRO_ENVIRONMENT_SET_HW_RENDER:
            if (system_ != "3ds") return false;
            if (!data) return false;
            hardware_callbacks_ = *static_cast<RetroHwRenderCallback*>(data);
            has_hardware_callbacks_ = hardware_callbacks_.context_type == 6;
            return has_hardware_callbacks_;
        case RETRO_ENVIRONMENT_SET_HW_RENDER_CONTEXT_NEGOTIATION_INTERFACE:
            if (system_ != "3ds") return false;
            if (!data) return false;
            // Azahar 2126.0 follows the libretro convention used by
            // RetroArch here: `data` is the negotiation-interface struct
            // itself (the core's wrapper casts that address to void**).
            // Dereferencing it would instead interpret the enum/version
            // prefix as a pointer and discard the real create-device hook.
            negotiation_interface_ = data;
            return negotiation_interface_ != nullptr;
        case RETRO_ENVIRONMENT_GET_HW_RENDER_INTERFACE:
            if (system_ != "3ds") return false;
            if (!data) return false;
            *static_cast<void**>(data) = vulkan_.hardware_interface();
            return vulkan_.hardware_interface() != nullptr;
        case RETRO_ENVIRONMENT_GET_HW_RENDER_CONTEXT_NEGOTIATION_INTERFACE_SUPPORT:
            // Azahar 2126.0 exposes the v1 create-device callbacks even
            // though it advertises v2; return false so it uses that stable
            // subset rather than probing a partially implemented v2 path.
            return false;
        case RETRO_ENVIRONMENT_GET_CURRENT_SOFTWARE_FRAMEBUFFER: {
            if (system_ == "3ds" || !data) return false;
            auto* framebuffer = static_cast<retro_framebuffer*>(data);
            if (!framebuffer->width || !framebuffer->height ||
                !(framebuffer->access_flags & RETRO_MEMORY_ACCESS_WRITE)) {
                return false;
            }
            void* mapped_framebuffer = nullptr;
            size_t mapped_pitch = 0;
            if (!vulkan_.acquire_software_framebuffer(framebuffer->width, framebuffer->height,
                                                       pixel_format_, mapped_framebuffer, mapped_pitch)) {
                return false;
            }
            framebuffer->data = mapped_framebuffer;
            framebuffer->pitch = mapped_pitch;
            framebuffer->format = pixel_format_;
            framebuffer->memory_flags = RETRO_MEMORY_TYPE_CACHED;
            return true;
        }
        case RETRO_ENVIRONMENT_GET_PREFERRED_HW_RENDER:
            return false;
        case RETRO_ENVIRONMENT_SET_MESSAGE:
        case RETRO_ENVIRONMENT_SET_MESSAGE_EXT: {
            auto* message = static_cast<retro_message*>(data);
            if (message && message->msg) message_ = message->msg;
            return true;
        }
        case RETRO_ENVIRONMENT_GET_LOG_INTERFACE:
            if (!data) return false;
            static_cast<retro_log_callback*>(data)->log = quiet_log;
            return true;
        default:
            return false;
        }
    }

    void on_video(const void* data, unsigned width, unsigned height, size_t pitch) {
        if (!vulkan_.ready()) return;
        if (system_ == "3ds" && width && height && reinterpret_cast<uintptr_t>(data) == RETRO_HW_FRAME_BUFFER_VALID) {
            last_video_width_ = width;
            last_video_height_ = height;
            vulkan_.present(width, height);
        } else if (system_ != "3ds" && data && width && height) {
            last_video_width_ = width;
            last_video_height_ = height;
            vulkan_.present_software(data, width, height, pitch, pixel_format_);
        } else if (!data && last_video_width_ && last_video_height_) {
            // Libretro permits a null frame to duplicate the last image.
            if (system_ == "3ds") vulkan_.present(last_video_width_, last_video_height_);
            else vulkan_.present_software(nullptr, last_video_width_, last_video_height_, 0, pixel_format_);
        }
    }

    int16_t input_state(unsigned device, unsigned index, unsigned id) {
        if (menu_navigation_active_.load(std::memory_order_relaxed)) return 0;
        if (device == RETRO_DEVICE_JOYPAD) {
            const uint32_t buttons = buttons_.load(std::memory_order_relaxed);
            if (id == RETRO_DEVICE_ID_JOYPAD_MASK) return static_cast<int16_t>(buttons & 0xffffu);
            return id < 32 && (buttons & (1u << id)) ? 1 : 0;
        }
        if (device == RETRO_DEVICE_ANALOG) {
            if (index == RETRO_DEVICE_INDEX_ANALOG_LEFT) {
                if (id == RETRO_DEVICE_ID_ANALOG_X) return circle_x_.load(std::memory_order_relaxed);
                if (id == RETRO_DEVICE_ID_ANALOG_Y) return circle_y_.load(std::memory_order_relaxed);
            }
            if (index == RETRO_DEVICE_INDEX_ANALOG_RIGHT) {
                if (id == RETRO_DEVICE_ID_ANALOG_X) return cstick_x_.load(std::memory_order_relaxed);
                if (id == RETRO_DEVICE_ID_ANALOG_Y) return cstick_y_.load(std::memory_order_relaxed);
            }
            return 0;
        }
        if (device == RETRO_DEVICE_POINTER) {
            if (id == RETRO_DEVICE_ID_POINTER_X) return touch_x_.load(std::memory_order_relaxed);
            if (id == RETRO_DEVICE_ID_POINTER_Y) return touch_y_.load(std::memory_order_relaxed);
            if (id == RETRO_DEVICE_ID_POINTER_PRESSED) return touch_pressed_.load(std::memory_order_relaxed) ? 1 : 0;
        }
        if (device == RETRO_DEVICE_MOUSE) {
            if (id == RETRO_DEVICE_ID_MOUSE_X) return mouse_delta_x_.exchange(0, std::memory_order_relaxed);
            if (id == RETRO_DEVICE_ID_MOUSE_Y) return mouse_delta_y_.exchange(0, std::memory_order_relaxed);
            if (id == RETRO_DEVICE_ID_MOUSE_LEFT) return touch_pressed_.load(std::memory_order_relaxed) ? 1 : 0;
        }
        return 0;
    }

    CoreApi core_;
    CoreOptionsRegistry core_options_{""};
    std::string core_path_;
    std::string moltenvk_path_;
    std::string rom_path_;
    std::string rom_id_;
    std::string save_path_;
    std::string system_path_;
    std::string system_;
    std::string layout_;
    std::string message_;
    std::vector<uint8_t> rom_data_;
    VulkanFrontend vulkan_;
    RetroHwRenderCallback hardware_callbacks_{};
    const void* negotiation_interface_ = nullptr;
    unsigned last_video_width_ = 0;
    unsigned last_video_height_ = 0;
    std::atomic<uint32_t> buttons_{0};
    std::atomic<bool> menu_navigation_active_{false};
    std::atomic<int16_t> circle_x_{0};
    std::atomic<int16_t> circle_y_{0};
    std::atomic<int16_t> cstick_x_{0};
    std::atomic<int16_t> cstick_y_{0};
    std::atomic<int16_t> touch_x_{0};
    std::atomic<int16_t> touch_y_{0};
    std::atomic<bool> touch_pressed_{false};
    std::atomic<int16_t> mouse_delta_x_{0};
    std::atomic<int16_t> mouse_delta_y_{0};
    HostTimingSeries emulate_timings_;
    std::chrono::steady_clock::time_point last_draw_time_{};
    double speed_ = 1.0;
    double speed_budget_ = 0.0;
    double active_game_seconds_ = 0.0;
    double last_save_ram_game_seconds_ = 0.0;
    bool save_ram_writable_ = true;
    size_t pending_save_ram_restore_size_ = 0;
    double last_autosave_game_seconds_ = 0.0;
    bool auto_save_enabled_ = false;
    bool auto_save_on_exit_ = false;
    unsigned auto_save_interval_seconds_ = 60;
    mutable std::mutex state_mutex_;
    SavePersistenceWorker persistence_writer_;
    int pixel_format_ = RETRO_PIXEL_FORMAT_RGB565;
    bool initialized_ = false;
    bool game_loaded_ = false;
    bool has_hardware_callbacks_ = false;
    bool renderer_initialized_ = false;
    bool running_ = false;
    std::atomic<bool> input_ready_{false};
    std::atomic<int> active_system_code_{0};
};

void AzaharHost::set_speed(double multiplier) {
    std::lock_guard<std::mutex> lock(state_mutex_);
    set_speed_locked(multiplier);
}

bool AzaharHost::set_core_option(const std::string& key, const std::string& value, std::string& error) {
    std::lock_guard<std::mutex> lock(state_mutex_);
    if (!core_options_.set(key, value)) {
        error = "The selected value is not announced by the running core.";
        return false;
    }
    NSString* defaults_key = [NSString stringWithFormat:@"an3.native-core-option.%@.%s",
                              [NSString stringWithUTF8String:core_options_.core_namespace().c_str()], key.c_str()];
    [[NSUserDefaults standardUserDefaults] setObject:[NSString stringWithUTF8String:value.c_str()]
                                               forKey:defaults_key];
    error.clear();
    return true;
}

bool AzaharHost::save_auto_state(std::string& error) {
    std::lock_guard<std::mutex> lock(state_mutex_);
    return save_auto_state_locked(error, true);
}

bool AzaharHost::save_auto_state_locked(std::string& error, bool wait_for_write) {
    if (!running_ || !core_.supports_states()) {
        error = "This native core does not provide automatic save states.";
        return false;
    }
    std::vector<uint8_t> bytes;
    if (!serialize_state(bytes, error)) return false;
    return persist_bytes_locked(std::filesystem::path(save_path_) / "states" /
                                    (rom_id_ + ".autosave.state"),
                                std::move(bytes), "save state", wait_for_write, error);
}

bool AzaharHost::load_auto_state(std::string& error) {
    std::lock_guard<std::mutex> lock(state_mutex_);
    return load_auto_state_locked(error);
}

bool AzaharHost::load_auto_state_locked(std::string& error) {
    if (!running_ || !core_.supports_states()) {
        error = "This native core does not provide automatic save states.";
        return false;
    }
    const auto path = std::filesystem::path(save_path_) / "states" / (rom_id_ + ".autosave.state");
    std::ifstream input(path, std::ios::binary | std::ios::ate);
    const std::streamoff size = input ? static_cast<std::streamoff>(input.tellg()) : -1;
    if (size <= 0 || static_cast<uintmax_t>(size) > kMaxQuickStateBytes) {
        error = "No valid Auto Save snapshot exists for this ROM.";
        return false;
    }
    input.seekg(0, std::ios::beg);
    std::vector<uint8_t> bytes(static_cast<size_t>(size));
    if (!input.read(reinterpret_cast<char*>(bytes.data()), size) || !core_.unserialize(bytes.data(), bytes.size())) {
        error = "The current native core rejected the Auto Save snapshot.";
        return false;
    }
    return true;
}

static AVAudioEngine* g_audio_engine = nil;
static AVAudioPlayerNode* g_audio_player = nil;
static AVAudioFormat* g_audio_format = nil; // output/mixer format
static AVAudioFormat* g_audio_core_format = nil; // true core PCM rate
static AVAudioConverter* g_audio_converter = nil;
static std::mutex g_audio_mutex;
static double g_audio_core_sample_rate = 0.0;
static double g_audio_effective_input_rate = 0.0;
static double g_audio_output_sample_rate = 0.0;
static double g_audio_hardware_sample_rate = 0.0;
static unsigned g_audio_latency_ms = 64;
static unsigned g_audio_resampler_quality = 2;
static bool g_audio_playing = false;
static std::atomic<size_t> g_audio_frames_queued{0};
static std::atomic<size_t> g_audio_frames_max{0};
static std::atomic<uint64_t> g_audio_underruns{0};
static std::atomic<uint64_t> g_audio_overruns{0};
static std::atomic<uint64_t> g_audio_last_submit_ns{0};
static std::atomic<bool> g_audio_underrun_latched{false};
// A bounded PCM snapshot distinguishes a silent core/converter from a
// healthy graph that simply has no queued buffers. It deliberately records
// only the first second-ish of stereo samples, never logs individual calls,
// and does not retain user audio.
constexpr size_t kAudioPcmSnapshotSamples = 65'536;
static std::atomic<uint64_t> g_audio_sample_callbacks{0};
static std::atomic<uint64_t> g_audio_batch_callbacks{0};
static std::atomic<uint64_t> g_audio_input_frames{0};
static std::atomic<uint64_t> g_audio_output_frames{0};
static std::atomic<size_t> g_audio_input_snapshot_samples{0};
static std::atomic<size_t> g_audio_output_snapshot_samples{0};
static std::atomic<uint64_t> g_audio_input_nonzero_samples{0};
static std::atomic<uint64_t> g_audio_output_nonzero_samples{0};
static std::atomic<uint64_t> g_audio_input_energy{0};
static std::atomic<uint64_t> g_audio_output_energy{0};
static std::atomic<uint32_t> g_audio_input_peak{0};
static std::atomic<uint32_t> g_audio_output_peak{0};
static std::atomic<uint64_t> g_audio_converter_failures{0};
static std::atomic<int32_t> g_audio_converter_last_status{0};
static std::atomic<int32_t> g_audio_converter_last_error{0};
static std::atomic<uint64_t> g_audio_scheduled_buffers{0};
static std::mutex g_audio_sample_mutex;
static std::array<int16_t, 2048> g_pending_audio_samples{};
static size_t g_pending_audio_frames = 0;

AzaharHost* active_host() { return g_host; }

static NSString* const kNativeKeyMappingsDefaultsKey = @"an3.native-key-mappings.v1";
static NSString* const kNativeStartFullscreenDefaultsKey = @"an3.native-start-fullscreen.v1";
static NSString* const kNativeShowFpsDefaultsKey = @"an3.native-show-fps.v1";
static NSString* const kNativeAudioVolumeDefaultsKey = @"an3.native-audio-volume.v1";
static NSString* const kNativeAudioMutedDefaultsKey = @"an3.native-audio-muted.v1";
static NSString* const kNativeAudioLatencyDefaultsKey = @"an3.native-audio-latency.v1";
static NSString* const kNativeResamplerQualityDefaultsKey = @"an3.native-resampler-quality.v1";
static NSString* const kNativeAutoSaveDefaultsKey = @"an3.native-auto-save.v1";
static NSString* const kNativeAutoSaveIntervalDefaultsKey = @"an3.native-auto-save-interval.v1";
static NSString* const kNativeAutoSaveModeDefaultsKey = @"an3.native-auto-save-mode.v1";

// Auto Save mode is a single, unambiguous choice from the shared model
// (native-offline/shared/player-ui.json) and is parsed by the same
// native-runtime/core/auto_save_mode.h header Android and Linux use, so the
// three native shells cannot drift apart.
static NSArray<NSString*>* native_auto_save_titles() {
    NSMutableArray<NSString*>* titles = [NSMutableArray arrayWithCapacity:an3::player_ui::auto_save_titles.size()];
    for (std::string_view title : an3::player_ui::auto_save_titles) {
        [titles addObject:[NSString stringWithUTF8String:std::string(title).c_str()]];
    }
    return titles;
}

static NSArray<NSString*>* native_auto_save_tokens() {
    NSMutableArray<NSString*>* tokens = [NSMutableArray arrayWithCapacity:an3::player_ui::auto_save_tokens.size()];
    for (std::string_view token : an3::player_ui::auto_save_tokens) {
        [tokens addObject:[NSString stringWithUTF8String:std::string(token).c_str()]];
    }
    return tokens;
}

static NSString* native_stored_auto_save_mode() {
    NSString* stored = [[NSUserDefaults standardUserDefaults] stringForKey:kNativeAutoSaveModeDefaultsKey];
    // An empty or unrecognised value falls through to the earlier boolean +
    // interval keys so an existing install keeps its configured interval.
    if (stored.length && an3::parse_auto_save_mode(std::string(stored.UTF8String))) return stored;
    const bool legacy_enabled = [[NSUserDefaults standardUserDefaults] boolForKey:kNativeAutoSaveDefaultsKey];
    if (!legacy_enabled) return @"off";
    const NSInteger legacy_interval = [[NSUserDefaults standardUserDefaults] integerForKey:kNativeAutoSaveIntervalDefaultsKey];
    return [NSString stringWithFormat:@"%ld", (long)(legacy_interval > 0 ? legacy_interval : 60)];
}

static void native_apply_auto_save_mode(NSString* mode) {
    std::string token = mode.length ? std::string(mode.UTF8String) : std::string("off");
    auto parsed = an3::parse_auto_save_mode(token);
    if (!parsed) {
        token = "off";
        parsed = an3::parse_auto_save_mode(token);
    }
    if (auto* host = active_host()) {
        host->set_auto_save_enabled(parsed->enabled);
        host->set_auto_save_on_exit(parsed->on_exit);
        if (parsed->enabled) host->set_auto_save_interval_seconds(std::max(1u, parsed->interval));
    }
    [[NSUserDefaults standardUserDefaults] setObject:[NSString stringWithUTF8String:token.c_str()]
                                              forKey:kNativeAutoSaveModeDefaultsKey];
}

static float native_audio_volume() {
    NSUserDefaults* defaults = [NSUserDefaults standardUserDefaults];
    const double value = [defaults objectForKey:kNativeAudioVolumeDefaultsKey]
        ? [defaults doubleForKey:kNativeAudioVolumeDefaultsKey] : 1.0;
    return static_cast<float>(std::clamp(value, 0.0, 1.0));
}

static bool native_audio_muted() {
    return [[NSUserDefaults standardUserDefaults] boolForKey:kNativeAudioMutedDefaultsKey];
}

static void reset_audio_pcm_snapshot() {
    g_audio_sample_callbacks.store(0, std::memory_order_relaxed);
    g_audio_batch_callbacks.store(0, std::memory_order_relaxed);
    g_audio_input_frames.store(0, std::memory_order_relaxed);
    g_audio_output_frames.store(0, std::memory_order_relaxed);
    g_audio_input_snapshot_samples.store(0, std::memory_order_relaxed);
    g_audio_output_snapshot_samples.store(0, std::memory_order_relaxed);
    g_audio_input_nonzero_samples.store(0, std::memory_order_relaxed);
    g_audio_output_nonzero_samples.store(0, std::memory_order_relaxed);
    g_audio_input_energy.store(0, std::memory_order_relaxed);
    g_audio_output_energy.store(0, std::memory_order_relaxed);
    g_audio_input_peak.store(0, std::memory_order_relaxed);
    g_audio_output_peak.store(0, std::memory_order_relaxed);
    g_audio_converter_failures.store(0, std::memory_order_relaxed);
    g_audio_converter_last_status.store(0, std::memory_order_relaxed);
    g_audio_converter_last_error.store(0, std::memory_order_relaxed);
    g_audio_scheduled_buffers.store(0, std::memory_order_relaxed);
    std::lock_guard<std::mutex> lock(g_audio_sample_mutex);
    g_pending_audio_frames = 0;
}

static void update_audio_peak(std::atomic<uint32_t>& peak, uint32_t value) {
    uint32_t current = peak.load(std::memory_order_relaxed);
    while (value > current && !peak.compare_exchange_weak(current, value, std::memory_order_relaxed)) {}
}

static size_t reserve_audio_snapshot_samples(std::atomic<size_t>& recorded, size_t requested) {
    size_t current = recorded.load(std::memory_order_relaxed);
    while (current < kAudioPcmSnapshotSamples) {
        const size_t accepted = std::min(requested, kAudioPcmSnapshotSamples - current);
        if (recorded.compare_exchange_weak(current, current + accepted, std::memory_order_relaxed)) return accepted;
    }
    return 0;
}

static void record_input_pcm(const int16_t* data, size_t frames) {
    if (!data || !frames) return;
    g_audio_input_frames.fetch_add(frames, std::memory_order_relaxed);
    const size_t samples = reserve_audio_snapshot_samples(g_audio_input_snapshot_samples,
                                                           std::min(frames, std::numeric_limits<size_t>::max() / 2u) * 2u);
    uint64_t nonzero = 0;
    uint64_t energy = 0;
    uint32_t peak = 0;
    for (size_t index = 0; index < samples; ++index) {
        const int amplitude = std::abs(static_cast<int>(data[index]));
        peak = std::max(peak, static_cast<uint32_t>(amplitude));
        if (amplitude) ++nonzero;
        energy += static_cast<uint64_t>(amplitude) * static_cast<uint64_t>(amplitude);
    }
    if (nonzero) g_audio_input_nonzero_samples.fetch_add(nonzero, std::memory_order_relaxed);
    if (energy) g_audio_input_energy.fetch_add(energy, std::memory_order_relaxed);
    update_audio_peak(g_audio_input_peak, peak);
}

static void record_output_pcm(AVAudioPCMBuffer* buffer) {
    if (!buffer || !buffer.frameLength) return;
    const size_t frames = buffer.frameLength;
    g_audio_output_frames.fetch_add(frames, std::memory_order_relaxed);
    const size_t samples = reserve_audio_snapshot_samples(g_audio_output_snapshot_samples,
                                                           std::min(frames, std::numeric_limits<size_t>::max() / 2u) * 2u);
    float* const* channels = buffer.floatChannelData;
    if (!channels || !channels[0] || !channels[1]) return;
    const size_t measured_frames = samples / 2u;
    uint64_t nonzero = 0;
    uint64_t energy = 0;
    uint32_t peak = 0;
    for (size_t index = 0; index < measured_frames; ++index) {
        for (float sample : {channels[0][index], channels[1][index]}) {
            const uint32_t amplitude = static_cast<uint32_t>(std::min(32767.0f, std::abs(sample) * 32767.0f));
            peak = std::max(peak, amplitude);
            if (amplitude) ++nonzero;
            energy += static_cast<uint64_t>(amplitude) * static_cast<uint64_t>(amplitude);
        }
    }
    if (nonzero) g_audio_output_nonzero_samples.fetch_add(nonzero, std::memory_order_relaxed);
    if (energy) g_audio_output_energy.fetch_add(energy, std::memory_order_relaxed);
    update_audio_peak(g_audio_output_peak, peak);
}

static void append_audio_sample(int16_t left, int16_t right) {
    g_audio_sample_callbacks.fetch_add(1, std::memory_order_relaxed);
    std::array<int16_t, 2048> ready{};
    size_t ready_frames = 0;
    {
        std::lock_guard<std::mutex> lock(g_audio_sample_mutex);
        const size_t offset = g_pending_audio_frames * 2u;
        g_pending_audio_samples[offset] = left;
        g_pending_audio_samples[offset + 1u] = right;
        if (++g_pending_audio_frames == g_pending_audio_samples.size() / 2u) {
            ready = g_pending_audio_samples;
            ready_frames = g_pending_audio_frames;
            g_pending_audio_frames = 0;
        }
    }
    if (ready_frames) submit_audio(ready.data(), ready_frames);
}

static void flush_pending_audio_samples() {
    std::array<int16_t, 2048> ready{};
    size_t ready_frames = 0;
    {
        std::lock_guard<std::mutex> lock(g_audio_sample_mutex);
        if (!g_pending_audio_frames) return;
        ready_frames = g_pending_audio_frames;
        std::copy_n(g_pending_audio_samples.begin(), ready_frames * 2u, ready.begin());
        g_pending_audio_frames = 0;
    }
    submit_audio(ready.data(), ready_frames);
}

static void note_audio_batch_callback(size_t frames) {
    if (!frames) return;
    g_audio_batch_callbacks.fetch_add(1, std::memory_order_relaxed);
}

static unsigned native_audio_latency_ms() {
    const NSInteger value = [[NSUserDefaults standardUserDefaults] integerForKey:kNativeAudioLatencyDefaultsKey];
    return value == 32 || value == 64 || value == 96 || value == 128 ? static_cast<unsigned>(value) : 64u;
}

static unsigned native_resampler_quality() {
    const NSInteger value = [[NSUserDefaults standardUserDefaults] integerForKey:kNativeResamplerQualityDefaultsKey];
    return value >= 0 && value <= 2 ? static_cast<unsigned>(value) : 2u;
}

static void apply_native_audio_preferences() {
    if (g_audio_player) g_audio_player.volume = native_audio_muted() ? 0.0f : native_audio_volume();
}

static unsigned button_for_key(unsigned short key_code) {
    NSString* key = [NSString stringWithFormat:@"%hu", key_code];
    NSDictionary* mappings = [[NSUserDefaults standardUserDefaults] dictionaryForKey:kNativeKeyMappingsDefaultsKey];
    const id mapped_value = [mappings objectForKey:key];
    if ([mapped_value isKindOfClass:NSNumber.class]) {
        const unsigned mapped_button = [mapped_value unsignedIntValue];
        if (mapped_button < 32) return mapped_button;
    }
    switch (key_code) {
    case 123: return 6;  // left
    case 124: return 7;  // right
    case 125: return 5;  // down
    case 126: return 4;  // up
    case 6: return 8;    // Z / A
    case 7: return 0;    // X / B
    case 0: return 9;    // A / X
    case 1: return 1;    // S / Y
    case 37: return 10;  // L
    case 38: return 11;  // J / R
    case 36: return 3;   // Return / Start
    case 49: return 2;   // Space / Select
    default: return 32;
    }
}

static void set_button_key_mapping(unsigned short key_code, unsigned button) {
    if (button >= 32) return;
    NSUserDefaults* defaults = [NSUserDefaults standardUserDefaults];
    NSMutableDictionary* mappings = [[defaults dictionaryForKey:kNativeKeyMappingsDefaultsKey] mutableCopy];
    if (!mappings) mappings = [NSMutableDictionary dictionary];
    mappings[[NSString stringWithFormat:@"%hu", key_code]] = @(button);
    [defaults setObject:mappings forKey:kNativeKeyMappingsDefaultsKey];
}

static void reset_button_key_mappings() {
    [[NSUserDefaults standardUserDefaults] removeObjectForKey:kNativeKeyMappingsDefaultsKey];
}

static AVAudioQuality audio_converter_quality(unsigned quality) {
    switch (quality) {
    case 0: return AVAudioQualityLow;
    case 1: return AVAudioQualityMedium;
    default: return AVAudioQualityHigh;
    }
}

static bool rebuild_audio_converter_locked() {
    if (!g_audio_core_format || !g_audio_format || !g_audio_output_sample_rate) return false;
    g_audio_converter = [[AVAudioConverter alloc] initFromFormat:g_audio_core_format toFormat:g_audio_format];
    if (!g_audio_converter) return false;
    g_audio_converter.sampleRateConverterQuality = audio_converter_quality(g_audio_resampler_quality);
    g_audio_converter.primeMethod = AVAudioConverterPrimeMethod_None;
    return true;
}

static void stop_audio_unlocked() {
    if (g_audio_player) [g_audio_player stop];
    if (g_audio_engine) [g_audio_engine stop];
    g_audio_player = nil;
    g_audio_engine = nil;
    g_audio_format = nil;
    g_audio_core_format = nil;
    g_audio_converter = nil;
    g_audio_core_sample_rate = 0.0;
    g_audio_effective_input_rate = 0.0;
    g_audio_output_sample_rate = 0.0;
    g_audio_hardware_sample_rate = 0.0;
    g_audio_playing = false;
    g_audio_frames_queued.store(0, std::memory_order_relaxed);
}

static void stop_audio() {
    std::lock_guard<std::mutex> lock(g_audio_mutex);
    stop_audio_unlocked();
}

static bool start_audio(double sample_rate) {
    std::lock_guard<std::mutex> lock(g_audio_mutex);
    stop_audio_unlocked();
    reset_audio_pcm_snapshot();
    g_audio_frames_max.store(0, std::memory_order_relaxed);
    g_audio_underruns.store(0, std::memory_order_relaxed);
    g_audio_overruns.store(0, std::memory_order_relaxed);
    g_audio_last_submit_ns.store(0, std::memory_order_relaxed);
    g_audio_underrun_latched.store(false, std::memory_order_relaxed);
    g_audio_latency_ms = native_audio_latency_ms();
    g_audio_resampler_quality = native_resampler_quality();
    if (sample_rate < 8'000.0 || sample_rate > 192'000.0) return false;

    g_audio_engine = [[AVAudioEngine alloc] init];
    g_audio_player = [[AVAudioPlayerNode alloc] init];
    [g_audio_engine attachNode:g_audio_player];
    AVAudioFormat* hardware = [g_audio_engine.outputNode outputFormatForBus:0];
    g_audio_hardware_sample_rate = hardware.sampleRate;
    const double output_rate = hardware.sampleRate >= 8'000.0 && hardware.sampleRate <= 192'000.0
        ? hardware.sampleRate : sample_rate;
    g_audio_output_sample_rate = output_rate;
    g_audio_core_sample_rate = sample_rate;
    g_audio_effective_input_rate = sample_rate;
    // Libretro callbacks are interleaved S16; AVAudioEngine's mixer/player
    // path is Float32 planar. Convert the sample representation explicitly
    // before resampling. Passing S16 bytes through planar float buffers (or
    // scheduling them as though they matched the mixer) caused an apparently
    // healthy-but-silent native pipeline.
    g_audio_format = [[AVAudioFormat alloc] initStandardFormatWithSampleRate:output_rate channels:2];
    g_audio_core_format = [[AVAudioFormat alloc] initStandardFormatWithSampleRate:sample_rate channels:2];
    if (!g_audio_format || !g_audio_core_format || !rebuild_audio_converter_locked()) {
        stop_audio_unlocked();
        return false;
    }
    [g_audio_engine connect:g_audio_player to:g_audio_engine.mainMixerNode format:g_audio_format];
    NSError* error = nil;
    if (![g_audio_engine startAndReturnError:&error]) {
        stop_audio_unlocked();
        return false;
    }
    // Record the post-start mixer/hardware rates as well; these are the values
    // used by the output graph and are exposed through native diagnostics.
    AVAudioFormat* mixer = [g_audio_engine.mainMixerNode outputFormatForBus:0];
    if (mixer.sampleRate >= 8'000.0 && mixer.sampleRate <= 192'000.0) g_audio_output_sample_rate = mixer.sampleRate;
    AVAudioFormat* started_hardware = [g_audio_engine.outputNode outputFormatForBus:0];
    if (started_hardware.sampleRate >= 8'000.0 && started_hardware.sampleRate <= 192'000.0) g_audio_hardware_sample_rate = started_hardware.sampleRate;
    apply_native_audio_preferences();
    // Queue a bounded priming period before starting the player node. Starting
    // immediately on the first tiny libretro batch is a common source of
    // audible crackle even when the renderer is at a stable frame rate.
    g_audio_playing = false;
    return true;
}

static void note_audio_underrun() {
    if (!g_audio_player || !g_audio_format || g_audio_frames_queued.load(std::memory_order_relaxed) != 0) return;
    const uint64_t last_submit = g_audio_last_submit_ns.load(std::memory_order_relaxed);
    if (!last_submit) return;
    const uint64_t now = static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
    // AVAudioEngine does not expose a reliable per-buffer underrun callback.
    // Count only a queue drain that persists for 50 ms while the core keeps
    // running; this is a clearly labelled frontend queue-drain estimate.
    if (now <= last_submit || now - last_submit < 50'000'000) return;
    bool expected = false;
    if (g_audio_underrun_latched.compare_exchange_strong(expected, true, std::memory_order_relaxed)) {
        g_audio_underruns.fetch_add(1, std::memory_order_relaxed);
    }
}

static void submit_audio(const int16_t* data, size_t frames) {
    std::lock_guard<std::mutex> lock(g_audio_mutex);
    if (!data || !frames || !g_audio_player || !g_audio_format || !g_audio_core_format || !g_audio_converter) return;
    record_input_pcm(data, frames);
    const size_t queued = g_audio_frames_queued.load(std::memory_order_relaxed);
    const size_t output_capacity = static_cast<size_t>(std::ceil(frames * g_audio_output_sample_rate /
                                                                  g_audio_effective_input_rate)) + 8u;
    const size_t ceiling = std::max<size_t>(output_capacity,
                                            static_cast<size_t>(g_audio_output_sample_rate * g_audio_latency_ms / 1000.0));
    if (output_capacity > ceiling || queued > ceiling - output_capacity) {
        g_audio_overruns.fetch_add(1, std::memory_order_relaxed);
        return;
    }
    AVAudioPCMBuffer* input = [[AVAudioPCMBuffer alloc] initWithPCMFormat:g_audio_core_format
                                                              frameCapacity:static_cast<AVAudioFrameCount>(frames)];
    AVAudioPCMBuffer* output = [[AVAudioPCMBuffer alloc] initWithPCMFormat:g_audio_format
                                                               frameCapacity:static_cast<AVAudioFrameCount>(output_capacity)];
    if (!input || !output) return;
    input.frameLength = static_cast<AVAudioFrameCount>(frames);
    float* const* input_channels = input.floatChannelData;
    if (!input_channels || !input_channels[0] || !input_channels[1]) return;
    constexpr float kS16Scale = 1.0f / 32768.0f;
    for (size_t index = 0; index < frames; ++index) {
        input_channels[0][index] = static_cast<float>(data[index * 2u]) * kS16Scale;
        input_channels[1][index] = static_cast<float>(data[index * 2u + 1u]) * kS16Scale;
    }
    __block bool provided = false;
    NSError* conversion_error = nil;
    const AVAudioConverterOutputStatus status = [g_audio_converter convertToBuffer:output error:&conversion_error
                                                               withInputFromBlock:^AVAudioBuffer*(AVAudioPacketCount, AVAudioConverterInputStatus* input_status) {
        if (provided) {
            // This converter is reused for the continuous realtime stream.
            // EndOfStream is terminal: after the first callback it made every
            // later conversion return with zero frames. Signal a temporary
            // dry input instead and supply the next libretro batch normally.
            *input_status = AVAudioConverterInputStatus_NoDataNow;
            return nil;
        }
        provided = true;
        *input_status = AVAudioConverterInputStatus_HaveData;
        return input;
    }];
    g_audio_converter_last_status.store(static_cast<int32_t>(status), std::memory_order_relaxed);
    g_audio_converter_last_error.store(static_cast<int32_t>(conversion_error.code), std::memory_order_relaxed);
    if (status == AVAudioConverterOutputStatus_Error || !output.frameLength) {
        g_audio_converter_failures.fetch_add(1, std::memory_order_relaxed);
        return;
    }
    record_output_pcm(output);
    const size_t output_frames = output.frameLength;
    const size_t next = g_audio_frames_queued.fetch_add(output_frames, std::memory_order_relaxed) + output_frames;
    size_t maximum = g_audio_frames_max.load(std::memory_order_relaxed);
    while (next > maximum && !g_audio_frames_max.compare_exchange_weak(maximum, next, std::memory_order_relaxed)) {}
    g_audio_last_submit_ns.store(static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count()), std::memory_order_relaxed);
    g_audio_underrun_latched.store(false, std::memory_order_relaxed);
    [g_audio_player scheduleBuffer:output completionHandler:^{
        const size_t current = g_audio_frames_queued.load(std::memory_order_relaxed);
        const size_t consumed = std::min(current, output_frames);
        g_audio_frames_queued.fetch_sub(consumed, std::memory_order_relaxed);
    }];
    g_audio_scheduled_buffers.fetch_add(1, std::memory_order_relaxed);
    const size_t target = static_cast<size_t>(g_audio_output_sample_rate * g_audio_latency_ms / 2000.0);
    // A drained AVAudioPlayerNode may report stopped while our completion
    // bookkeeping still says it was started. Restarting only when the node is
    // genuinely inactive restores sound after a short bounded underrun; it
    // does not rebuild the engine or converter on the steady 1x path.
    const bool node_is_playing = g_audio_player.isPlaying;
    if ((!g_audio_playing && next >= std::max<size_t>(1, target)) ||
        (g_audio_playing && !node_is_playing)) {
        [g_audio_player play];
    }
    g_audio_playing = g_audio_player.isPlaying;
}

static void set_audio_speed(double multiplier) {
    std::lock_guard<std::mutex> lock(g_audio_mutex);
    if (!g_audio_player || !g_audio_core_sample_rate || !g_audio_format) return;
    g_audio_effective_input_rate = g_audio_core_sample_rate * multiplier;
    if (g_audio_effective_input_rate < 4'000.0 || g_audio_effective_input_rate > 384'000.0) return;
    [g_audio_player stop];
    g_audio_frames_queued.store(0, std::memory_order_relaxed);
    g_audio_playing = false;
    {
        std::lock_guard<std::mutex> pending_lock(g_audio_sample_mutex);
        g_pending_audio_frames = 0;
    }
    g_audio_core_format = [[AVAudioFormat alloc] initStandardFormatWithSampleRate:g_audio_effective_input_rate channels:2];
    (void)rebuild_audio_converter_locked();
}

static void set_audio_latency_ms(unsigned latency_ms) {
    std::lock_guard<std::mutex> lock(g_audio_mutex);
    g_audio_latency_ms = latency_ms == 32 || latency_ms == 64 || latency_ms == 96 || latency_ms == 128 ? latency_ms : 64;
}

static void set_audio_resampler_quality(unsigned quality) {
    std::lock_guard<std::mutex> lock(g_audio_mutex);
    g_audio_resampler_quality = std::min(quality, 2u);
    if (g_audio_converter) g_audio_converter.sampleRateConverterQuality = audio_converter_quality(g_audio_resampler_quality);
}

static uint64_t timeval_microseconds(const time_value_t& value) {
    return static_cast<uint64_t>(value.seconds) * 1'000'000ull + static_cast<uint64_t>(value.microseconds);
}

static void populate_process_metrics(NativeRendererMetrics& snapshot) {
    mach_task_basic_info task{};
    mach_msg_type_number_t count = MACH_TASK_BASIC_INFO_COUNT;
    if (task_info(mach_task_self(), MACH_TASK_BASIC_INFO, reinterpret_cast<task_info_t>(&task), &count) != KERN_SUCCESS) return;
    snapshot.resident_memory_bytes = static_cast<uint64_t>(task.resident_size);
    snapshot.cpu_user_time_us = timeval_microseconds(task.user_time);
    snapshot.cpu_system_time_us = timeval_microseconds(task.system_time);
}

NativeRendererMetrics AzaharHost::renderer_metrics() const {
    NativeRendererMetrics snapshot = vulkan_.renderer_metrics();
    snapshot.emulate_p95_us = emulate_timings_.percentile(95);
    snapshot.emulate_p99_us = emulate_timings_.percentile(99);
    snapshot.audio_queue_depth_frames = static_cast<uint32_t>(std::min<size_t>(
        g_audio_frames_queued.load(std::memory_order_relaxed), std::numeric_limits<uint32_t>::max()));
    snapshot.audio_queue_max_frames = static_cast<uint32_t>(std::min<size_t>(
        g_audio_frames_max.load(std::memory_order_relaxed), std::numeric_limits<uint32_t>::max()));
    snapshot.audio_underruns = g_audio_underruns.load(std::memory_order_relaxed);
    snapshot.audio_overruns = g_audio_overruns.load(std::memory_order_relaxed);
    snapshot.audio_core_sample_rate = g_audio_core_sample_rate;
    snapshot.audio_output_sample_rate = g_audio_output_sample_rate;
    snapshot.audio_hardware_sample_rate = g_audio_hardware_sample_rate;
    snapshot.audio_effective_input_rate = g_audio_effective_input_rate;
    snapshot.audio_core_channels = 2;
    snapshot.audio_output_channels = g_audio_format ? g_audio_format.channelCount : 2;
    snapshot.audio_sample_callbacks = g_audio_sample_callbacks.load(std::memory_order_relaxed);
    snapshot.audio_batch_callbacks = g_audio_batch_callbacks.load(std::memory_order_relaxed);
    snapshot.audio_input_frames = g_audio_input_frames.load(std::memory_order_relaxed);
    snapshot.audio_output_frames = g_audio_output_frames.load(std::memory_order_relaxed);
    snapshot.audio_input_nonzero_samples = g_audio_input_nonzero_samples.load(std::memory_order_relaxed);
    snapshot.audio_output_nonzero_samples = g_audio_output_nonzero_samples.load(std::memory_order_relaxed);
    snapshot.audio_input_energy = g_audio_input_energy.load(std::memory_order_relaxed);
    snapshot.audio_output_energy = g_audio_output_energy.load(std::memory_order_relaxed);
    snapshot.audio_input_peak = g_audio_input_peak.load(std::memory_order_relaxed);
    snapshot.audio_output_peak = g_audio_output_peak.load(std::memory_order_relaxed);
    snapshot.audio_converter_failures = g_audio_converter_failures.load(std::memory_order_relaxed);
    snapshot.audio_converter_last_status = g_audio_converter_last_status.load(std::memory_order_relaxed);
    snapshot.audio_converter_last_error = g_audio_converter_last_error.load(std::memory_order_relaxed);
    snapshot.audio_scheduled_buffers = g_audio_scheduled_buffers.load(std::memory_order_relaxed);
    snapshot.audio_player_playing = g_audio_player && g_audio_player.isPlaying;
    snapshot.audio_engine_running = g_audio_engine && g_audio_engine.isRunning;
    snapshot.audio_muted = native_audio_muted();
    snapshot.audio_volume = native_audio_volume();
    populate_process_metrics(snapshot);
    return snapshot;
}

} // namespace an3

static NSTextField* native_settings_header(NSString* title) {
    NSTextField* header = [NSTextField labelWithString:title];
    header.font = [NSFont boldSystemFontOfSize:12.0];
    header.textColor = NSColor.controlAccentColor;
    return header;
}

// Toolbar text belongs to the shared player contract. AppKit retains the
// native visual treatment while Android, Linux and web consume the same words.
static NSString* native_player_ui_text(std::string_view value) {
    // Generated labels originate from string literals, so their data is NUL-terminated.
    return [NSString stringWithUTF8String:value.data()];
}

static void collect_menu_focusable_controls(NSView* view, NSMutableArray<NSControl*>* controls) {
    if (view.hidden) return;
    if ([view isKindOfClass:NSButton.class] || [view isKindOfClass:NSPopUpButton.class] ||
        [view isKindOfClass:NSSlider.class]) {
        NSControl* control = (NSControl*)view;
        if (control.enabled) [controls addObject:control];
        return;
    }
    for (NSView* child in view.subviews) collect_menu_focusable_controls(child, controls);
}

@implementation AN3AzaharView

- (instancetype)initWithFrame:(NSRect)frameRect device:(nullable id<MTLDevice>)device system:(const char*)system {
    self = [super initWithFrame:frameRect device:device];
    if (self) {
        _system = [NSString stringWithUTF8String:system ?: ""] ?: @"";
        _draft_start_fullscreen = [[NSUserDefaults standardUserDefaults] boolForKey:an3::kNativeStartFullscreenDefaultsKey];
        _draft_show_fps = [[NSUserDefaults standardUserDefaults] boolForKey:an3::kNativeShowFpsDefaultsKey];
        _draft_muted = an3::native_audio_muted();
        _draft_volume = an3::native_audio_volume();
        _draft_latency = an3::native_audio_latency_ms();
        _draft_resampler_quality = an3::native_resampler_quality();
        _draft_core_options = [NSMutableDictionary dictionary];
        [self buildControls];
    }
    return self;
}

- (AN3InputButton*)inputButton:(NSString*)title bit:(unsigned)bit {
    AN3InputButton* button = [AN3InputButton buttonWithTitle:title target:nil action:nil];
    button.input_button = bit;
    button.font = [NSFont boldSystemFontOfSize:15.0];
    button.bezelStyle = NSBezelStyleCircular;
    button.wantsLayer = YES;
    button.layer.cornerRadius = 24.0;
    [self addSubview:button];
    return button;
}

- (void)buildControls {
    const BOOL is_three_ds = [_system isEqualToString:@"3ds"];
    const BOOL is_nds = [_system isEqualToString:@"nds"];
    _menu_button = [NSButton buttonWithTitle:native_player_ui_text(an3::player_ui::toolbar_menu) target:self action:@selector(toggleMenu:)];
    _pad_button = [NSButton buttonWithTitle:native_player_ui_text(an3::player_ui::toolbar_pad) target:self action:@selector(togglePad:)];
    _menu_button.font = [NSFont boldSystemFontOfSize:13.0];
    _pad_button.font = [NSFont boldSystemFontOfSize:13.0];
    [self addSubview:_menu_button];
    [self addSubview:_pad_button];
    if (is_nds || is_three_ds) {
        _layout_button = [NSButton buttonWithTitle:native_player_ui_text(an3::player_ui::toolbar_layout) target:self action:@selector(showLayoutChooser:)];
        _layout_button.font = [NSFont boldSystemFontOfSize:13.0];
        _layout_button.toolTip = @"Choose any screen layout this core supports.";
        [self addSubview:_layout_button];
    }
    _save_button = [NSButton buttonWithTitle:native_player_ui_text(an3::player_ui::toolbar_save) target:self action:@selector(showSaveMenu:)];
    _save_button.font = [NSFont boldSystemFontOfSize:13.0];
    _save_button.toolTip = @"Quick save, quick load, or Auto Save without opening the menu.";
    [self addSubview:_save_button];
    _slow_speed_button = [NSButton buttonWithTitle:native_player_ui_text(an3::player_ui::toolbar_speed[0]) target:self action:@selector(setSlowSpeed:)];
    _normal_speed_button = [NSButton buttonWithTitle:native_player_ui_text(an3::player_ui::toolbar_speed[1]) target:self action:@selector(setNormalSpeed:)];
    _fast_speed_button = [NSButton buttonWithTitle:native_player_ui_text(an3::player_ui::toolbar_speed[2]) target:self action:@selector(cycleFastSpeed:)];
    for (NSButton* button in @[_slow_speed_button, _normal_speed_button, _fast_speed_button]) {
        button.bezelStyle = NSBezelStyleRounded;
        button.font = [NSFont monospacedDigitSystemFontOfSize:11.0 weight:NSFontWeightSemibold];
        button.imagePosition = NSImageLeft;
        button.imageScaling = NSImageScaleProportionallyDown;
        button.wantsLayer = YES;
        button.layer.cornerRadius = 8.0;
        [self addSubview:button];
    }
    _slow_speed_button.image = [NSImage imageWithSystemSymbolName:@"tortoise" accessibilityDescription:@"Slow speed"];
    _normal_speed_button.image = [NSImage imageWithSystemSymbolName:@"hare" accessibilityDescription:@"Normal speed"];
    _fast_speed_button.image = [NSImage imageWithSystemSymbolName:@"hare.fill" accessibilityDescription:@"Fast speed"];
    _slow_speed_button.accessibilityLabel = @"Slow speed";
    _normal_speed_button.accessibilityLabel = @"Normal speed";
    _fast_speed_button.accessibilityLabel = @"Fast speed";
    [self syncSpeedControls];
    if (is_nds) {
        _cursor_lock_button = [NSButton buttonWithTitle:native_player_ui_text(an3::player_ui::toolbar_cursor_lock) target:self action:@selector(lockCursor:)];
        _cursor_lock_button.font = [NSFont boldSystemFontOfSize:13.0];
        _cursor_lock_button.toolTip = @"Lock mouse movement to the NDS touchscreen. Press Esc to release it.";
        [self addSubview:_cursor_lock_button];
    }

    _dpad_up = [self inputButton:@"▲" bit:4];
    _dpad_down = [self inputButton:@"▼" bit:5];
    _dpad_left = [self inputButton:@"◀" bit:6];
    _dpad_right = [self inputButton:@"▶" bit:7];
    _button_a = [self inputButton:@"A" bit:8];
    _button_b = [self inputButton:@"B" bit:0];
    _button_x = [self inputButton:@"X" bit:9];
    _button_y = [self inputButton:@"Y" bit:1];
    _button_l = [self inputButton:@"L" bit:10];
    _button_r = [self inputButton:@"R" bit:11];
    _button_start = [self inputButton:@"Start" bit:3];
    _button_select = [self inputButton:@"Select" bit:2];
    NSMutableArray<NSView*>* pad_controls = [@[_dpad_up, _dpad_down, _dpad_left, _dpad_right, _button_a, _button_b,
                                                _button_x, _button_y, _button_l, _button_r, _button_start, _button_select] mutableCopy];
    if (is_three_ds) {
        _circle_pad = [[AN3CirclePadView alloc] initWithFrame:NSZeroRect];
        _circle_pad.toolTip = @"Circle Pad: drag to move";
        [self addSubview:_circle_pad];
        [pad_controls addObject:_circle_pad];
    }
    _pad_controls = pad_controls;

    NSVisualEffectView* panel = [[NSVisualEffectView alloc] initWithFrame:NSZeroRect];
    panel.material = NSVisualEffectMaterialHUDWindow;
    panel.blendingMode = NSVisualEffectBlendingModeWithinWindow;
    panel.state = NSVisualEffectStateActive;
    panel.wantsLayer = YES;
    panel.layer.cornerRadius = 14.0;
    NSString* engine = is_three_ds ? @"Azahar native" : (is_nds ? @"melonDS DS native" : @"mGBA native");
    NSTextField* title = [NSTextField labelWithString:[@"Vibe Coded Emulator · " stringByAppendingString:engine]];
    title.font = [NSFont boldSystemFontOfSize:16.0];
    NSString* help_text = is_three_ds
        ? @"Keyboard: arrows, Z/X, A/S, L/J, Return and Space.\nOption + arrows: Circle Pad. Click the lower display for 3DS touch input.\nThe menu keeps ten raw core quick-save slots."
        : (is_nds
            ? @"Keyboard: arrows, Z/X, A/S, L/J, Return and Space.\nClick the game display or Lock cursor to control the NDS touchscreen. Esc releases the cursor; Esc again returns to the library.\nThe menu keeps ten raw core quick-save slots."
            : @"Keyboard: arrows, Z/X, A/S, L/J, Return and Space.\nUse Menu and Pad for the native GBA virtual controls. The menu keeps ten raw core quick-save slots.");
    NSTextField* help = [NSTextField labelWithString:help_text];
    help.font = [NSFont systemFontOfSize:12.0];
    help.maximumNumberOfLines = 5;
    help.lineBreakMode = NSLineBreakByWordWrapping;
    NSMutableArray<NSView*>* general_rows = [NSMutableArray arrayWithObjects:title, help, nil];
    NSMutableArray<NSView*>* graphics_rows = [NSMutableArray array];
    NSMutableArray<NSView*>* audio_rows = [NSMutableArray array];
    NSMutableArray<NSView*>* keyboard_rows = [NSMutableArray array];
    NSMutableArray<NSView*>* controller_rows = [NSMutableArray array];
    NSMutableArray<NSView*>* emulation_rows = [NSMutableArray array];
    NSMutableArray<NSView*>* save_rows = [NSMutableArray array];
    NSMutableArray<NSView*>* diagnostics_rows = [NSMutableArray array];
    NSMutableArray<NSView*>* about_rows = [NSMutableArray array];
    NSMutableArray<NSView*>* menu_rows = general_rows;
    _start_fullscreen_toggle = [NSButton checkboxWithTitle:@"Start fullscreen on launch"
                                                     target:self action:@selector(toggleStartFullscreen:)];
    _start_fullscreen_toggle.state = [[NSUserDefaults standardUserDefaults] boolForKey:an3::kNativeStartFullscreenDefaultsKey]
        ? NSControlStateValueOn : NSControlStateValueOff;
    [menu_rows addObject:_start_fullscreen_toggle];
    NSButton* fullscreen_now = [NSButton buttonWithTitle:@"Enter fullscreen now" target:self action:@selector(toggleFullscreen:)];
    [menu_rows addObject:fullscreen_now];

    menu_rows = graphics_rows;
    NSTextField* renderer_info = [NSTextField labelWithString:@"Renderer: Vulkan 1.1 via bundled MoltenVK → Metal"];
    renderer_info.font = [NSFont systemFontOfSize:11.0];
    [menu_rows addObject:renderer_info];
    _show_fps = [[NSUserDefaults standardUserDefaults] boolForKey:an3::kNativeShowFpsDefaultsKey];
    _show_fps_toggle = [NSButton checkboxWithTitle:@"Show FPS" target:self action:@selector(toggleShowFps:)];
    _show_fps_toggle.state = _show_fps ? NSControlStateValueOn : NSControlStateValueOff;
    [menu_rows addObject:_show_fps_toggle];
    if (is_nds || is_three_ds) {
        NSTextField* layout_label = [NSTextField labelWithString:@"Screen layout"];
        _screen_layout_popup = [[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO];
        for (const auto& layout : an3::native_screen_layouts(_system.UTF8String ?: "")) {
            [_screen_layout_popup addItemWithTitle:[NSString stringWithUTF8String:layout.label]];
            _screen_layout_popup.lastItem.representedObject = [NSString stringWithUTF8String:layout.id];
        }
        const std::string preferred = an3::native_layout_preference(_system.UTF8String ?: "", "preserve");
        for (NSMenuItem* item in _screen_layout_popup.itemArray) {
            if ([item.representedObject isEqualToString:[NSString stringWithUTF8String:preferred.c_str()]]) {
                [_screen_layout_popup selectItem:item];
                break;
            }
        }
        _screen_layout_popup.target = self;
        _screen_layout_popup.action = @selector(changeScreenLayout:);
        NSStackView* layout_row = [NSStackView stackViewWithViews:@[layout_label, _screen_layout_popup]];
        layout_row.orientation = NSUserInterfaceLayoutOrientationHorizontal;
        layout_row.spacing = 10.0;
        [menu_rows addObject:layout_row];
        NSTextField* layout_hint = [NSTextField labelWithString:@"Saved per system and applied immediately."];
        layout_hint.font = [NSFont systemFontOfSize:11.0];
        layout_hint.textColor = NSColor.secondaryLabelColor;
        [menu_rows addObject:layout_hint];
    }

    menu_rows = audio_rows;
    NSTextField* volume_label = [NSTextField labelWithString:@"Volume"];
    [volume_label setContentHuggingPriority:NSLayoutPriorityRequired forOrientation:NSLayoutConstraintOrientationHorizontal];
    [volume_label setContentCompressionResistancePriority:NSLayoutPriorityRequired forOrientation:NSLayoutConstraintOrientationHorizontal];
    _volume_slider = [NSSlider sliderWithValue:an3::native_audio_volume() * 100.0
                                       minValue:0.0 maxValue:100.0 target:self action:@selector(changeVolume:)];
    _volume_slider.translatesAutoresizingMaskIntoConstraints = NO;
    [_volume_slider setContentHuggingPriority:NSLayoutPriorityDefaultLow forOrientation:NSLayoutConstraintOrientationHorizontal];
    [_volume_slider setContentCompressionResistancePriority:NSLayoutPriorityDefaultLow forOrientation:NSLayoutConstraintOrientationHorizontal];
    _volume_value = [NSTextField labelWithString:[NSString stringWithFormat:@"%d%%", (int)std::lround(an3::native_audio_volume() * 100.0)]];
    _volume_value.alignment = NSTextAlignmentRight;
    [_volume_value setContentHuggingPriority:NSLayoutPriorityRequired forOrientation:NSLayoutConstraintOrientationHorizontal];
    [_volume_value setContentCompressionResistancePriority:NSLayoutPriorityRequired forOrientation:NSLayoutConstraintOrientationHorizontal];
    NSStackView* volume_row = [NSStackView stackViewWithViews:@[volume_label, _volume_slider, _volume_value]];
    _volume_slider.continuous = YES;
    volume_row.orientation = NSUserInterfaceLayoutOrientationHorizontal;
    volume_row.distribution = NSStackViewDistributionFill;
    volume_row.spacing = 8.0;
    volume_row.alignment = NSLayoutAttributeCenterY;
    _volume_row = volume_row;
    [menu_rows addObject:volume_row];
    _mute_audio_toggle = [NSButton checkboxWithTitle:@"Mute" target:self action:@selector(toggleMute:)];
    _mute_audio_toggle.state = an3::native_audio_muted() ? NSControlStateValueOn : NSControlStateValueOff;
    [menu_rows addObject:_mute_audio_toggle];
    NSStackView* latency_row = [NSStackView stackViewWithViews:@[[NSTextField labelWithString:@"Audio latency"],
        (_audio_latency_popup = [[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO])]];
    [_audio_latency_popup addItemsWithTitles:@[@"32 ms", @"64 ms", @"96 ms", @"128 ms"]];
    [_audio_latency_popup selectItemWithTitle:[NSString stringWithFormat:@"%u ms", an3::native_audio_latency_ms()]];
    [_audio_latency_popup setTarget:self];
    [_audio_latency_popup setAction:@selector(changeAudioLatency:)];
    latency_row.orientation = NSUserInterfaceLayoutOrientationHorizontal;
    latency_row.spacing = 10.0;
    [menu_rows addObject:latency_row];
    NSStackView* resampler_row = [NSStackView stackViewWithViews:@[[NSTextField labelWithString:@"Resampler quality"],
        (_resampler_quality_popup = [[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO])]];
    [_resampler_quality_popup addItemsWithTitles:@[@"Low", @"Medium", @"High"]];
    [_resampler_quality_popup selectItemAtIndex:an3::native_resampler_quality()];
    [_resampler_quality_popup setTarget:self];
    [_resampler_quality_popup setAction:@selector(changeResamplerQuality:)];
    resampler_row.orientation = NSUserInterfaceLayoutOrientationHorizontal;
    resampler_row.spacing = 10.0;
    [menu_rows addObject:resampler_row];
    _audio_diagnostics = [NSTextField labelWithString:@"Core sample rate: — · Output: — · Hardware: —"];
    _audio_diagnostics.font = [NSFont systemFontOfSize:11.0];
    _audio_diagnostics.textColor = NSColor.secondaryLabelColor;
    _audio_diagnostics.maximumNumberOfLines = 4;
    // Live audio counters belong in Diagnostics; the Audio tab only contains controls.

    menu_rows = emulation_rows;
    [menu_rows addObject:native_settings_header(@"Core Options announced by the active libretro core")];
    _core_options_stack = [NSStackView stackViewWithViews:@[[NSTextField labelWithString:@"The core has not announced any options."]]];
    _core_options_stack.orientation = NSUserInterfaceLayoutOrientationVertical;
    _core_options_stack.alignment = NSLayoutAttributeLeading;
    _core_options_stack.spacing = 5.0;
    [menu_rows addObject:_core_options_stack];

    menu_rows = save_rows;
    NSStackView* auto_save_mode_row = [NSStackView stackViewWithViews:@[[NSTextField labelWithString:@"Auto Save"],
        (_auto_save_mode_popup = [[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO])]];
    [_auto_save_mode_popup addItemsWithTitles:an3::native_auto_save_titles()];
    const NSUInteger auto_save_index = [an3::native_auto_save_tokens() indexOfObject:an3::native_stored_auto_save_mode()];
    [_auto_save_mode_popup selectItemAtIndex:(auto_save_index == NSNotFound ? 0 : auto_save_index)];
    [_auto_save_mode_popup setTarget:self];
    [_auto_save_mode_popup setAction:@selector(changeAutoSaveMode:)];
    auto_save_mode_row.orientation = NSUserInterfaceLayoutOrientationHorizontal;
    auto_save_mode_row.spacing = 10.0;
    [menu_rows addObject:auto_save_mode_row];
    _auto_save_status = [NSTextField labelWithString:@"Last Auto Save: —"];
    _auto_save_status.font = [NSFont systemFontOfSize:11.0];
    _auto_save_status.textColor = NSColor.secondaryLabelColor;
    [menu_rows addObject:_auto_save_status];
    _load_auto_save_button = [NSButton buttonWithTitle:@"Load Auto Save" target:self action:@selector(loadAutoSave:)];
    [menu_rows addObject:_load_auto_save_button];
    NSButton* exit_game = [NSButton buttonWithTitle:@"Exit Game" target:self action:@selector(exitGame:)];
    [menu_rows addObject:exit_game];
    for (NSInteger slot = 1; slot <= 10; ++slot) {
        NSButton* save = [NSButton buttonWithTitle:[NSString stringWithFormat:@"Quick save %ld", (long)slot]
                                             target:self action:@selector(saveQuickSlot:)];
        save.tag = slot;
        save.bezelStyle = NSBezelStyleRounded;
        NSButton* load = [NSButton buttonWithTitle:[NSString stringWithFormat:@"Quick load %ld", (long)slot]
                                             target:self action:@selector(loadQuickSlot:)];
        load.tag = slot;
        load.bezelStyle = NSBezelStyleRounded;
        NSStackView* row = [NSStackView stackViewWithViews:@[save, load]];
        row.orientation = NSUserInterfaceLayoutOrientationHorizontal;
        row.spacing = 8.0;
        [menu_rows addObject:row];
    }
    _quick_state_status = [NSTextField labelWithString:@"Quick saves use native core state bytes."];
    _quick_state_status.font = [NSFont systemFontOfSize:11.0];
    _quick_state_status.textColor = NSColor.secondaryLabelColor;
    [menu_rows addObject:_quick_state_status];
    NSStackView* state_file_row = [NSStackView stackViewWithViews:@[
        [NSButton buttonWithTitle:@"Export Save State…" target:self action:@selector(exportState:)],
        [NSButton buttonWithTitle:@"Import Save State…" target:self action:@selector(importState:)]
    ]];
    state_file_row.orientation = NSUserInterfaceLayoutOrientationHorizontal;
    state_file_row.spacing = 10.0;
    [menu_rows addObject:state_file_row];

    menu_rows = keyboard_rows;
    _key_map_action = [[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO];
    const NSArray<NSString*>* map_actions = @[@"B", @"Y", @"Select", @"Start", @"Up", @"Down", @"Left", @"Right",
                                               @"A", @"X", @"L", @"R"];
    const unsigned map_buttons[] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11};
    for (NSUInteger index = 0; index < map_actions.count; ++index) {
        [_key_map_action addItemWithTitle:map_actions[index]];
        _key_map_action.lastItem.tag = map_buttons[index];
    }
    NSButton* map_key = [NSButton buttonWithTitle:@"Map selected key" target:self action:@selector(beginKeyMapping:)];
    NSStackView* map_row = [NSStackView stackViewWithViews:@[_key_map_action, map_key]];
    map_row.orientation = NSUserInterfaceLayoutOrientationHorizontal;
    map_row.spacing = 10.0;
    [menu_rows addObject:map_row];
    NSButton* reset_keys = [NSButton buttonWithTitle:@"Reset custom keyboard map" target:self action:@selector(resetKeyMappings:)];
    [menu_rows addObject:reset_keys];
    _key_map_status = [NSTextField labelWithString:@"Choose an action, then capture one physical key."];
    _key_map_status.font = [NSFont systemFontOfSize:11.0];
    _key_map_status.textColor = NSColor.secondaryLabelColor;
    [menu_rows addObject:_key_map_status];
    // Controller input is owned by the core/native responder; no HID remapping backend exists.
    [controller_rows addObject:[NSTextField labelWithString:@"Controller support: native responder/core-owned. Controller remapping is not implemented."]];
    menu_rows = diagnostics_rows;
    _audio_diagnostics = [NSTextField labelWithString:@"Renderer and audio diagnostics refresh at a bounded 2 Hz."];
    _audio_diagnostics.font = [NSFont systemFontOfSize:11.0];
    _audio_diagnostics.textColor = NSColor.secondaryLabelColor;
    _audio_diagnostics.maximumNumberOfLines = 6;
    [menu_rows addObject:_audio_diagnostics];
    [menu_rows addObject:[NSTextField labelWithString:@"Renderer: Vulkan 1.1 → bundled MoltenVK → Metal. Backend selection is fixed and read-only."]];
    menu_rows = about_rows;
    NSTextField* about_info = [NSTextField labelWithString:@"Vibe Coded Emulator 1.1.0\nGBA · NDS · 3DS native cores\nVulkan → MoltenVK → Metal"];
    about_info.font = [NSFont systemFontOfSize:11.0];
    about_info.maximumNumberOfLines = 3;
    [menu_rows addObject:about_info];
    [menu_rows addObject:[NSButton buttonWithTitle:@"About VibeCodedEmulator…" target:self action:@selector(showAbout:)]];
    [about_rows addObject:[NSButton buttonWithTitle:@"Resume" target:self action:@selector(toggleMenu:)]];
    [about_rows addObject:[NSButton buttonWithTitle:@"Return to library" target:self action:@selector(returnToLibrary:)]];
    _settings_tab_stacks = [NSMutableDictionary dictionary];
    _settings_tabs = [[NSTabView alloc] initWithFrame:NSZeroRect];
    _settings_tabs.translatesAutoresizingMaskIntoConstraints = NO;
    _settings_tabs.tabViewType = NSTopTabsBezelBorder;
    _settings_tabs.controlSize = NSControlSizeSmall;
    const NSArray<NSArray*>* tab_specs = @[
        @[@"General", general_rows], @[@"Graphics", graphics_rows], @[@"Audio", audio_rows],
        @[@"Keyboard", keyboard_rows], @[@"Controller", controller_rows], @[@"Emulation", emulation_rows],
        @[@"Save States", save_rows], @[@"Diagnostics", diagnostics_rows], @[@"About", about_rows]
    ];
    for (NSArray* spec in tab_specs) {
        NSString* tab_name = spec[0];
        NSArray<NSView*>* rows = spec[1];
        NSStackView* stack = [NSStackView stackViewWithViews:rows];
        stack.orientation = NSUserInterfaceLayoutOrientationVertical;
        stack.alignment = NSLayoutAttributeLeading;
        stack.spacing = 8.0;
        stack.edgeInsets = NSEdgeInsetsMake(4.0, 4.0, 10.0, 4.0);
        stack.translatesAutoresizingMaskIntoConstraints = YES;
        stack.autoresizingMask = NSViewWidthSizable;
        NSScrollView* tab_scroll = [[NSScrollView alloc] initWithFrame:NSZeroRect];
        tab_scroll.drawsBackground = NO;
        tab_scroll.hasVerticalScroller = YES;
        tab_scroll.hasHorizontalScroller = NO;
        tab_scroll.autohidesScrollers = YES;
        tab_scroll.documentView = stack;
        NSTabViewItem* item = [[NSTabViewItem alloc] initWithIdentifier:tab_name];
        item.label = tab_name;
        item.view = tab_scroll;
        [_settings_tabs addTabViewItem:item];
        _settings_tab_stacks[tab_name] = stack;
    }
    // The audio row is constrained to the document content on both sides,
    // rather than relying on NSStackView's fitting width. The text labels
    // keep their intrinsic width and the slider is the only flexible element.
    NSStackView* stack = _settings_tab_stacks[@"Audio"];
    volume_row.translatesAutoresizingMaskIntoConstraints = NO;
    NSLayoutConstraint* minimum_slider_width = [_volume_slider.widthAnchor constraintGreaterThanOrEqualToConstant:72.0];
    minimum_slider_width.priority = NSLayoutPriorityDefaultHigh;
    [NSLayoutConstraint activateConstraints:@[
        [volume_row.leadingAnchor constraintEqualToAnchor:stack.leadingAnchor],
        [volume_row.trailingAnchor constraintEqualToAnchor:stack.trailingAnchor],
        minimum_slider_width,
    ]];
    _save_settings_button = [NSButton buttonWithTitle:@"Save Settings" target:self action:@selector(saveSettings:)];
    _save_settings_button.translatesAutoresizingMaskIntoConstraints = NO;
    _settings_save_status = [NSTextField labelWithString:@"Changes are saved only when you choose Save Settings."];
    _settings_save_status.translatesAutoresizingMaskIntoConstraints = NO;
    _settings_save_status.textColor = NSColor.secondaryLabelColor;
    _settings_save_status.lineBreakMode = NSLineBreakByTruncatingTail;
    NSTextField* settings_title = [NSTextField labelWithString:@"In-game settings"];
    settings_title.font = [NSFont boldSystemFontOfSize:14.0];
    NSTextField* settings_context = [NSTextField labelWithString:@"Nine sections · changes are kept as a draft until you save."];
    settings_context.font = [NSFont systemFontOfSize:11.0];
    settings_context.textColor = NSColor.secondaryLabelColor;
    NSStackView* settings_header = [NSStackView stackViewWithViews:@[settings_title, settings_context]];
    settings_header.orientation = NSUserInterfaceLayoutOrientationVertical;
    settings_header.spacing = 1.0;
    settings_header.translatesAutoresizingMaskIntoConstraints = NO;
    [panel addSubview:_settings_tabs];
    [panel addSubview:_save_settings_button];
    [panel addSubview:_settings_save_status];
    [panel addSubview:settings_header];
    [NSLayoutConstraint activateConstraints:@[
        [settings_header.leadingAnchor constraintEqualToAnchor:panel.leadingAnchor constant:14.0],
        [settings_header.trailingAnchor constraintEqualToAnchor:panel.trailingAnchor constant:-14.0],
        [settings_header.topAnchor constraintEqualToAnchor:panel.topAnchor constant:12.0],
        [_settings_tabs.leadingAnchor constraintEqualToAnchor:panel.leadingAnchor constant:14.0],
        [_settings_tabs.trailingAnchor constraintEqualToAnchor:panel.trailingAnchor constant:-14.0],
        [_settings_tabs.topAnchor constraintEqualToAnchor:settings_header.bottomAnchor constant:6.0],
        [_settings_tabs.bottomAnchor constraintEqualToAnchor:_save_settings_button.topAnchor constant:-8.0],
        [_save_settings_button.trailingAnchor constraintEqualToAnchor:panel.trailingAnchor constant:-14.0],
        [_save_settings_button.bottomAnchor constraintEqualToAnchor:panel.bottomAnchor constant:-12.0],
        [_settings_save_status.leadingAnchor constraintEqualToAnchor:panel.leadingAnchor constant:14.0],
        [_settings_save_status.trailingAnchor constraintLessThanOrEqualToAnchor:_save_settings_button.leadingAnchor constant:-12.0],
        [_settings_save_status.centerYAnchor constraintEqualToAnchor:_save_settings_button.centerYAnchor],
    ]];
    _settings_stack = _settings_tab_stacks[@"General"];
    _fps_overlay = [AN3InertLabel labelWithString:@""];
    _fps_overlay.font = [NSFont monospacedDigitSystemFontOfSize:11.0 weight:NSFontWeightSemibold];
    _fps_overlay.textColor = NSColor.whiteColor;
    _fps_overlay.alignment = NSTextAlignmentCenter;
    _fps_overlay.drawsBackground = YES;
    _fps_overlay.backgroundColor = [NSColor colorWithWhite:0.0 alpha:0.72];
    _fps_overlay.wantsLayer = YES;
    _fps_overlay.layer.cornerRadius = 5.0;
    _fps_overlay.hidden = !_show_fps;
    [self addSubview:_fps_overlay];
    panel.hidden = YES;
    [self addSubview:panel];
    _menu_panel = panel;
}

- (void)layout {
    [super layout];
    const CGFloat width = self.bounds.size.width;
    const CGFloat height = self.bounds.size.height;
    const CGFloat key = 52.0;
    _menu_button.frame = NSMakeRect(18.0, height - 44.0, 64.0, 28.0);
    _cursor_lock_button.frame = NSMakeRect(90.0, height - 44.0, 102.0, 28.0);
    _pad_button.frame = NSMakeRect(width - 82.0, height - 44.0, 64.0, 28.0);
    if (_layout_button) _layout_button.frame = NSMakeRect(std::max<CGFloat>(92.0, width - 254.0), height - 44.0, 60.0, 28.0);
    _save_button.frame = NSMakeRect(std::max<CGFloat>(92.0, width - 190.0), height - 44.0, 60.0, 28.0);
    const CGFloat speed_gap = 5.0;
    // At narrow widths the menu, cursor, and pad buttons must keep their
    // touch targets. Put the compact speed row above them instead of letting
    // it overlap either edge control or escape the window bounds.
    const bool compact_controls = width < 600.0;
    const CGFloat speed_width = compact_controls ? 48.0 : std::clamp((width - 72.0) / 3.0, 54.0, 74.0);
    const CGFloat speed_total = speed_width * 3.0 + speed_gap * 2.0;
    const CGFloat speed_start = compact_controls
        ? std::max<CGFloat>(8.0, (width - speed_total) * 0.5)
        : std::max<CGFloat>(210.0, width * 0.5 - (speed_width * 1.5 + speed_gap));
    const CGFloat speed_y = compact_controls ? height - 78.0 : height - 44.0;
    _slow_speed_button.frame = NSMakeRect(speed_start, speed_y, speed_width, 28.0);
    _normal_speed_button.frame = NSMakeRect(speed_start + speed_width + speed_gap, speed_y, speed_width, 28.0);
    _fast_speed_button.frame = NSMakeRect(speed_start + (speed_width + speed_gap) * 2.0, speed_y, speed_width, 28.0);
    _button_l.frame = NSMakeRect(18.0, height - 92.0, 58.0, 34.0);
    _button_r.frame = NSMakeRect(width - 76.0, height - 92.0, 58.0, 34.0);
    _dpad_up.frame = NSMakeRect(42.0 + key, 42.0 + key * 2.0, key, key);
    _dpad_down.frame = NSMakeRect(42.0 + key, 42.0, key, key);
    _dpad_left.frame = NSMakeRect(42.0, 42.0 + key, key, key);
    _dpad_right.frame = NSMakeRect(42.0 + key * 2.0, 42.0 + key, key, key);
    _button_a.frame = NSMakeRect(width - 42.0 - key, 42.0 + key, key, key);
    _button_b.frame = NSMakeRect(width - 42.0 - key * 2.0, 42.0, key, key);
    _button_x.frame = NSMakeRect(width - 42.0 - key * 2.0, 42.0 + key * 2.0, key, key);
    _button_y.frame = NSMakeRect(width - 42.0 - key * 3.0, 42.0 + key, key, key);
    _button_select.frame = NSMakeRect(width * 0.5 - 106.0, 28.0, 86.0, 30.0);
    _button_start.frame = NSMakeRect(width * 0.5 + 20.0, 28.0, 86.0, 30.0);
    _circle_pad.frame = NSMakeRect(20.0, 214.0, 108.0, 108.0);
    // Desktop preferences use a comfortable 700–820px target when the host
    // permits it, and clamp inside the current drawable at narrow sizes.
    const CGFloat panel_width = std::min<CGFloat>(an3::player_ui::panel_width, std::max<CGFloat>(300.0, width - an3::player_ui::panel_edge * 2.0));
    const CGFloat panel_height = std::min<CGFloat>(an3::player_ui::panel_height, std::max<CGFloat>(260.0, height - an3::player_ui::panel_edge * 2.0));
    _menu_panel.frame = NSMakeRect((width - panel_width) * 0.5, (height - panel_height) * 0.5, panel_width, panel_height);
    for (NSStackView* stack in _settings_tab_stacks.allValues) {
        stack.frame = NSMakeRect(8.0, 0.0, panel_width - 44.0, std::max<CGFloat>(120.0, stack.fittingSize.height));
    }
    _fps_overlay.frame = NSMakeRect(std::max<CGFloat>(8.0, width - 186.0), height - 42.0, 144.0, 24.0);
}

- (void)closeMenuDiscardingDraft {
    if (_settings_dirty) [self discardSettingsDraft];
    _menu_focus_control.focusRingType = NSFocusRingTypeDefault;
    _menu_focus_control = nil;
    _menu_panel.hidden = YES;
    _controller_menu_buttons = an3::active_host() ? an3::active_host()->controller_buttons() : _controller_menu_buttons;
    _menu_input_suppressed_until_release = _controller_menu_buttons != 0;
    if (auto* host = an3::active_host()) {
        host->set_menu_navigation_active(_menu_input_suppressed_until_release);
    }
    [self.window makeFirstResponder:self];
}

- (void)toggleMenu:(id)sender {
    if (!_menu_panel.hidden) {
        [self closeMenuDiscardingDraft];
        return;
    }
    _menu_panel.hidden = NO;
    _menu_input_suppressed_until_release = NO;
    if (auto* host = an3::active_host()) {
        _controller_menu_buttons = host->controller_buttons();
        host->set_menu_navigation_active(true);
    }
    // Opening the menu releases any held NDS/3DS touch so a tap on a menu row
    // can never leak into the emulated touchscreen.
    if (auto* host = an3::active_host()) host->set_nds_touch_pressed(false);
    [self.window makeFirstResponder:self];
    [self moveMenuFocusBy:1];
}

// Phone Controller OPEN_MENU has open semantics: a repeated press must not
// toggle an already-open menu closed.
- (void)openMenu {
    if (_menu_panel.hidden) [self toggleMenu:nil];
}

- (NSArray<NSControl*>*)menuFocusableControls {
    NSMutableArray<NSControl*>* controls = [NSMutableArray array];
    if (_settings_tabs.selectedTabViewItem.view) {
        collect_menu_focusable_controls(_settings_tabs.selectedTabViewItem.view, controls);
    }
    if (_save_settings_button.enabled) [controls addObject:_save_settings_button];
    return controls;
}

- (void)focusMenuControl:(NSControl*)control {
    if (_menu_focus_control != control) _menu_focus_control.focusRingType = NSFocusRingTypeDefault;
    _menu_focus_control = control;
    if (!_menu_focus_control) return;
    _menu_focus_control.focusRingType = NSFocusRingTypeExterior;
    [self.window makeFirstResponder:_menu_focus_control];
    [_menu_focus_control setNeedsDisplay:YES];
}

- (void)moveMenuFocusBy:(NSInteger)delta {
    NSArray<NSControl*>* controls = [self menuFocusableControls];
    if (!controls.count) return;
    const NSUInteger current = [controls indexOfObjectIdenticalTo:_menu_focus_control];
    const NSUInteger next = current == NSNotFound
        ? (delta < 0 ? controls.count - 1 : 0)
        : (delta < 0 ? (current + controls.count - 1) % controls.count
                     : (current + 1) % controls.count);
    [self focusMenuControl:controls[next]];
}

- (void)adjustMenuFocusBy:(NSInteger)delta {
    if ([_menu_focus_control isKindOfClass:NSPopUpButton.class]) {
        NSPopUpButton* popup = (NSPopUpButton*)_menu_focus_control;
        const NSInteger count = static_cast<NSInteger>(popup.numberOfItems);
        if (count < 1) return;
        const NSInteger current = std::max<NSInteger>(0, popup.indexOfSelectedItem);
        [popup selectItemAtIndex:std::clamp(current + delta, NSInteger{0}, count - 1)];
        [popup sendAction:popup.action to:popup.target];
        return;
    }
    if ([_menu_focus_control isKindOfClass:NSSlider.class]) {
        NSSlider* slider = (NSSlider*)_menu_focus_control;
        const double step = std::max(0.01, (slider.maxValue - slider.minValue) / 20.0);
        slider.doubleValue = std::clamp(slider.doubleValue + step * delta, slider.minValue, slider.maxValue);
        [slider sendAction:slider.action to:slider.target];
        return;
    }
    const NSInteger count = static_cast<NSInteger>(_settings_tabs.numberOfTabViewItems);
    if (count < 1) return;
    const NSInteger current = std::max<NSInteger>(0, [_settings_tabs indexOfTabViewItem:_settings_tabs.selectedTabViewItem]);
    const NSInteger next = (current + delta + count) % count;
    _menu_focus_control.focusRingType = NSFocusRingTypeDefault;
    _menu_focus_control = nil;
    [_settings_tabs selectTabViewItemAtIndex:next];
    [self moveMenuFocusBy:1];
}

- (void)activateMenuFocus {
    if ([_menu_focus_control isKindOfClass:NSButton.class]) {
        [(NSButton*)_menu_focus_control performClick:self];
    } else if ([_menu_focus_control isKindOfClass:NSPopUpButton.class] ||
               [_menu_focus_control isKindOfClass:NSSlider.class]) {
        [self adjustMenuFocusBy:1];
    } else {
        [self moveMenuFocusBy:1];
    }
}

- (void)handleControllerMenuButtons:(uint32_t)buttons {
    if (_menu_panel.hidden) {
        _controller_menu_buttons = buttons;
        if (_menu_input_suppressed_until_release && buttons == 0) {
            _menu_input_suppressed_until_release = NO;
            if (auto* host = an3::active_host()) host->set_menu_navigation_active(false);
        }
        return;
    }
    const uint32_t rising = buttons & ~_controller_menu_buttons;
    _controller_menu_buttons = buttons;
    // Button bit positions are the libretro joypad IDs already sent by the phone.
    static constexpr uint32_t kMenuUp = 1u << 4;
    static constexpr uint32_t kMenuDown = 1u << 5;
    static constexpr uint32_t kMenuLeft = 1u << 6;
    static constexpr uint32_t kMenuRight = 1u << 7;
    static constexpr uint32_t kMenuA = 1u << 8;
    static constexpr uint32_t kMenuB = 1u << 0;
    static constexpr uint32_t kMenuStart = 1u << 3;
    if (rising & kMenuB) {
        [self closeMenuDiscardingDraft];
    } else if (rising & kMenuUp) {
        [self moveMenuFocusBy:-1];
    } else if (rising & kMenuDown) {
        [self moveMenuFocusBy:1];
    } else if (rising & kMenuLeft) {
        [self adjustMenuFocusBy:-1];
    } else if (rising & kMenuRight) {
        [self adjustMenuFocusBy:1];
    } else if (rising & (kMenuA | kMenuStart)) {
        [self activateMenuFocus];
    }
}

- (void)applyNativeSpeed:(double)speed {
    if (auto* host = an3::active_host()) host->set_speed(speed);
    [self syncSpeedControls];
}

- (void)setSlowSpeed:(id)sender { [self applyNativeSpeed:0.5]; }
- (void)setNormalSpeed:(id)sender { [self applyNativeSpeed:1.0]; }
- (void)cycleFastSpeed:(id)sender {
    const double current = an3::active_host() ? an3::active_host()->speed() : 1.0;
    const double next = current <= 1.0 ? 2.0 : current < 4.0 ? 4.0 : current < 8.0 ? 8.0 : 8.0;
    [self applyNativeSpeed:next];
}

- (void)syncSpeedControls {
    const double speed = an3::active_host() ? an3::active_host()->speed() : 1.0;
    _slow_speed_button.state = std::abs(speed - 0.5) < 0.001 ? NSControlStateValueOn : NSControlStateValueOff;
    _normal_speed_button.state = std::abs(speed - 1.0) < 0.001 ? NSControlStateValueOn : NSControlStateValueOff;
    _fast_speed_button.state = speed >= 2.0 ? NSControlStateValueOn : NSControlStateValueOff;
    _fast_speed_button.title = speed >= 8.0 ? @"x8" : speed >= 4.0 ? @"x4" : @"x2";
    for (NSButton* button in @[_slow_speed_button, _normal_speed_button, _fast_speed_button]) {
        button.contentTintColor = button.state == NSControlStateValueOn ? NSColor.controlAccentColor : NSColor.labelColor;
    }
}

- (void)toggleStartFullscreen:(NSButton*)sender {
    _draft_start_fullscreen = sender.state == NSControlStateValueOn;
    _settings_dirty = YES;
}

- (void)toggleFullscreen:(id)sender {
    if (self.window) [self.window toggleFullScreen:nil];
}

- (void)toggleShowFps:(NSButton*)sender {
    _draft_show_fps = sender.state == NSControlStateValueOn;
    _show_fps = _draft_show_fps; // safe live preview; discard restores it.
    _fps_overlay.hidden = !_show_fps;
    _fps_last_presented = an3_native_presented_frames();
    _fps_last_update = CACurrentMediaTime();
    if (_show_fps) _fps_overlay.stringValue = @"— FPS · Vulkan";
    _settings_dirty = YES;
}

- (void)changeScreenLayout:(NSPopUpButton*)sender {
    NSString* selected = sender.selectedItem.representedObject ?: @"left-right";
    std::string error;
    auto* host = an3::active_host();
    const bool changed = host && host->set_screen_layout(selected.UTF8String ?: "", error);
    if (!changed) {
        [self updateQuickStateStatus:error.empty() ? "Screen layout could not be applied." : error.c_str() success:NO];
        return;
    }
    an3::persist_native_layout_preference(_system, selected);
    [self updateQuickStateStatus:"Screen layout applied and saved for this system." success:YES];
}

- (void)syncScreenLayoutPopup:(const std::string&)layout {
    if (!_screen_layout_popup) return;
    NSString* selected = [NSString stringWithUTF8String:layout.c_str()];
    for (NSMenuItem* item in _screen_layout_popup.itemArray) {
        if ([item.representedObject isEqualToString:selected]) {
            [_screen_layout_popup selectItem:item];
            break;
        }
    }
}

// The toolbar Layout control exposes every layout the active core supports
// instead of only cycling between two.
- (void)showLayoutChooser:(NSButton*)sender {
    auto* host = an3::active_host();
    if (!host) return;
    const std::string current = host->layout();
    NSMenu* menu = [[NSMenu alloc] initWithTitle:@""];
    for (const auto& layout : an3::native_screen_layouts(_system.UTF8String ?: "")) {
        NSMenuItem* item = [[NSMenuItem alloc] initWithTitle:[NSString stringWithUTF8String:layout.label]
                                                      action:@selector(selectScreenLayout:)
                                               keyEquivalent:@""];
        item.representedObject = [NSString stringWithUTF8String:layout.id];
        item.state = (current == layout.id) ? NSControlStateValueOn : NSControlStateValueOff;
        item.target = self;
        [menu addItem:item];
    }
    [menu popUpMenuPositioningItem:nil atLocation:NSMakePoint(0.0, sender.bounds.size.height + 4.0) inView:sender];
}

- (void)selectScreenLayout:(NSMenuItem*)sender {
    NSString* selected = sender.representedObject;
    if (!selected.length) return;
    std::string error;
    auto* host = an3::active_host();
    const bool changed = host && host->set_screen_layout(selected.UTF8String ?: "", error);
    if (!changed) {
        [self updateQuickStateStatus:error.empty() ? "Screen layout could not be applied." : error.c_str() success:NO];
        return;
    }
    an3::persist_native_layout_preference(_system, selected);
    [self syncScreenLayoutPopup:selected.UTF8String ?: ""];
    [self updateQuickStateStatus:"Screen layout applied and saved for this system." success:YES];
}

// The toolbar Save control mirrors the Save States tab's quick actions so a
// save/load does not require opening the menu.
- (NSMenu*)quickSlotSubmenu:(SEL)action title:(NSString*)title {
    NSMenu* submenu = [[NSMenu alloc] initWithTitle:title];
    for (unsigned slot = 1; slot <= 10; ++slot) {
        NSMenuItem* item = [[NSMenuItem alloc] initWithTitle:[NSString stringWithFormat:@"Slot %u", slot]
                                                      action:action keyEquivalent:@""];
        item.tag = static_cast<NSInteger>(slot);
        item.target = self;
        [submenu addItem:item];
    }
    return submenu;
}

- (void)showSaveMenu:(NSButton*)sender {
    NSMenu* menu = [[NSMenu alloc] initWithTitle:@""];
    // Quick Save / Quick Load expose all ten quick slots, matching the Save
    // States tab, so a save or load never needs the full menu.
    NSMenuItem* saveRoot = [[NSMenuItem alloc] initWithTitle:native_player_ui_text(an3::player_ui::toolbar_quick_save)
                                                      action:nil keyEquivalent:@""];
    saveRoot.submenu = [self quickSlotSubmenu:@selector(saveQuickSlot:)
                                        title:native_player_ui_text(an3::player_ui::toolbar_quick_save)];
    [menu addItem:saveRoot];
    NSMenuItem* loadRoot = [[NSMenuItem alloc] initWithTitle:native_player_ui_text(an3::player_ui::toolbar_quick_load)
                                                      action:nil keyEquivalent:@""];
    loadRoot.submenu = [self quickSlotSubmenu:@selector(loadQuickSlot:)
                                        title:native_player_ui_text(an3::player_ui::toolbar_quick_load)];
    [menu addItem:loadRoot];
    [menu addItem:[NSMenuItem separatorItem]];
    NSMenuItem* saveAuto = [[NSMenuItem alloc] initWithTitle:@"Auto Save now" action:@selector(saveAutoNow:) keyEquivalent:@""];
    saveAuto.target = self;
    [menu addItem:saveAuto];
    NSMenuItem* loadAuto = [[NSMenuItem alloc] initWithTitle:@"Load Auto Save" action:@selector(loadAutoSave:) keyEquivalent:@""];
    loadAuto.target = self;
    [menu addItem:loadAuto];
    [menu popUpMenuPositioningItem:nil atLocation:NSMakePoint(0.0, sender.bounds.size.height + 4.0) inView:sender];
}

- (void)saveAutoNow:(id)sender {
    std::string error;
    auto* host = an3::active_host();
    const bool saved = host && host->save_auto_state(error);
    if (!saved && error.empty()) error = "The native player is not running.";
    [self updateQuickStateStatus:saved ? "Auto Save saved." : error.c_str() success:saved];
}

- (void)changeVolume:(NSSlider*)sender {
    const double value = std::clamp(sender.doubleValue / 100.0, 0.0, 1.0);
    _draft_volume = value;
    _volume_value.stringValue = [NSString stringWithFormat:@"%d%%", (int)std::lround(value * 100.0)];
    an3::apply_native_audio_preferences();
    _settings_dirty = YES;
}

- (void)toggleMute:(NSButton*)sender {
    _draft_muted = sender.state == NSControlStateValueOn;
    _settings_dirty = YES;
}

- (void)changeAudioLatency:(NSPopUpButton*)sender {
    const unsigned latency = static_cast<unsigned>(sender.selectedItem.title.integerValue);
    _draft_latency = latency;
    _settings_dirty = YES;
}

- (void)changeResamplerQuality:(NSPopUpButton*)sender {
    const unsigned quality = static_cast<unsigned>(sender.indexOfSelectedItem);
    _draft_resampler_quality = quality;
    _settings_dirty = YES;
}

- (void)saveSettings:(id)sender {
    NSUserDefaults* defaults = [NSUserDefaults standardUserDefaults];
    [defaults setBool:_draft_start_fullscreen forKey:an3::kNativeStartFullscreenDefaultsKey];
    [defaults setBool:_draft_show_fps forKey:an3::kNativeShowFpsDefaultsKey];
    [defaults setDouble:_draft_volume forKey:an3::kNativeAudioVolumeDefaultsKey];
    [defaults setBool:_draft_muted forKey:an3::kNativeAudioMutedDefaultsKey];
    [defaults setInteger:_draft_latency forKey:an3::kNativeAudioLatencyDefaultsKey];
    [defaults setInteger:_draft_resampler_quality forKey:an3::kNativeResamplerQualityDefaultsKey];
    an3::apply_native_audio_preferences();
    an3::set_audio_latency_ms(_draft_latency);
    an3::set_audio_resampler_quality(_draft_resampler_quality);
    for (NSString* key in _draft_core_options) {
        std::string ignored;
        (void)(an3::active_host() && an3::active_host()->set_core_option(key.UTF8String ?: "",
            _draft_core_options[key].UTF8String ?: "", ignored));
    }
    const BOOL core_needs_restart = _draft_core_options.count > 0;
    [_draft_core_options removeAllObjects];
    _settings_dirty = NO;
    _settings_save_status.stringValue = core_needs_restart ? @"Settings saved · restart required for marked core options" : @"Settings saved";
    _settings_save_status.textColor = NSColor.systemGreenColor;
}

- (void)discardSettingsDraft {
    NSUserDefaults* defaults = [NSUserDefaults standardUserDefaults];
    _draft_start_fullscreen = [defaults boolForKey:an3::kNativeStartFullscreenDefaultsKey];
    _draft_show_fps = [defaults boolForKey:an3::kNativeShowFpsDefaultsKey];
    _draft_volume = an3::native_audio_volume();
    _draft_muted = an3::native_audio_muted();
    _draft_latency = an3::native_audio_latency_ms();
    _draft_resampler_quality = an3::native_resampler_quality();
    _start_fullscreen_toggle.state = _draft_start_fullscreen ? NSControlStateValueOn : NSControlStateValueOff;
    _show_fps_toggle.state = _draft_show_fps ? NSControlStateValueOn : NSControlStateValueOff;
    _show_fps = _draft_show_fps;
    _fps_overlay.hidden = !_show_fps;
    _volume_slider.doubleValue = _draft_volume * 100.0;
    _volume_value.stringValue = [NSString stringWithFormat:@"%d%%", (int)std::lround(_draft_volume * 100.0)];
    _mute_audio_toggle.state = _draft_muted ? NSControlStateValueOn : NSControlStateValueOff;
    [_audio_latency_popup selectItemWithTitle:[NSString stringWithFormat:@"%u ms", _draft_latency]];
    [_resampler_quality_popup selectItemAtIndex:_draft_resampler_quality];
    an3::apply_native_audio_preferences();
    _settings_dirty = NO;
    [_draft_core_options removeAllObjects];
    _settings_save_status.stringValue = @"Unsaved settings discarded.";
    _settings_save_status.textColor = NSColor.secondaryLabelColor;
}

- (void)changeAutoSaveMode:(NSPopUpButton*)sender {
    const NSArray<NSString*>* tokens = an3::native_auto_save_tokens();
    const NSInteger index = sender.indexOfSelectedItem;
    NSString* mode = (index >= 0 && index < (NSInteger)tokens.count) ? tokens[index] : @"off";
    an3::native_apply_auto_save_mode(mode);
    if ([mode isEqualToString:@"off"]) {
        [self updateQuickStateStatus:"Auto Save disabled." success:YES];
    } else if ([mode isEqualToString:@"exit"]) {
        [self updateQuickStateStatus:"Auto Save runs when you exit the game." success:YES];
    } else {
        [self updateQuickStateStatus:"Auto Save will run every configured interval." success:YES];
    }
}

// Exit Game stops this emulation session and returns to the library. When
// save-on-exit is enabled it writes one final autosave first; the write is
// atomic, and an unchanged state is still cheap because the host serializes
// under its state mutex.
- (void)exitGame:(id)sender {
    if (auto* host = an3::active_host()) {
        if (host->auto_save_on_exit()) {
            std::string ignored;
            host->save_auto_state(ignored);
        }
    }
    [self returnToLibrary:sender];
}

- (void)loadAutoSave:(id)sender {
    std::string error;
    const bool loaded = an3::active_host() && an3::active_host()->load_auto_state(error);
    [self updateQuickStateStatus:loaded ? "Auto Save loaded." : error.c_str() success:loaded];
}

- (void)exportState:(id)sender {
    NSSavePanel* panel = [NSSavePanel savePanel];
    panel.title = @"Export Save State";
    UTType* state_type = [UTType typeWithFilenameExtension:@"state"];
    if (state_type) panel.allowedContentTypes = @[state_type];
    panel.allowsOtherFileTypes = NO;
    panel.canCreateDirectories = YES;
    panel.nameFieldStringValue = @"VibeCodedEmulator.state";
    if ([panel runModal] != NSModalResponseOK || !panel.URL.path.length) return;
    NSString* path = panel.URL.path;
    if ([[path pathExtension] caseInsensitiveCompare:@"state"] != NSOrderedSame) {
        path = [path stringByAppendingPathExtension:@"state"];
    }
    char details[256]{};
    const int exported = an3_native_export_state(path.fileSystemRepresentation, details, sizeof(details));
    [self updateQuickStateStatus:details success:exported != 0];
}

- (void)importState:(id)sender {
    NSOpenPanel* panel = [NSOpenPanel openPanel];
    panel.title = @"Import Save State";
    UTType* state_type = [UTType typeWithFilenameExtension:@"state"];
    UTType* savestate_type = [UTType typeWithFilenameExtension:@"savestate"];
    NSMutableArray<UTType*>* allowed_types = [NSMutableArray array];
    if (state_type) [allowed_types addObject:state_type];
    if (savestate_type) [allowed_types addObject:savestate_type];
    panel.allowedContentTypes = allowed_types;
    panel.allowsOtherFileTypes = NO;
    panel.canChooseFiles = YES;
    panel.canChooseDirectories = NO;
    if ([panel runModal] != NSModalResponseOK || !panel.URL.path.length) return;
    char details[256]{};
    const int imported = an3_native_import_state(panel.URL.path.fileSystemRepresentation, details, sizeof(details));
    [self updateQuickStateStatus:details success:imported != 0];
}

- (void)showAbout:(id)sender {
    NSAlert* alert = [[NSAlert alloc] init];
    alert.messageText = @"VibeCodedEmulator";
    alert.informativeText = @"Version 1.1.0\nNative GBA · NDS · 3DS\nVulkan → MoltenVK → Metal\nRaw libretro save states are kept compatible with existing app data.";
    alert.alertStyle = NSAlertStyleInformational;
    [alert addButtonWithTitle:@"OK"];
    [alert runModal];
}

- (void)updateFpsOverlay {
    if (!_show_fps || _fps_overlay.hidden) return;
    const NSTimeInterval now = CACurrentMediaTime();
    if (_fps_last_update > 0.0 && now - _fps_last_update < 0.333) return;
    const uint64_t presented = an3_native_presented_frames();
    if (_fps_last_update > 0.0 && now > _fps_last_update) {
        const double fps = static_cast<double>(presented - _fps_last_presented) / (now - _fps_last_update);
        _fps_overlay.stringValue = [NSString stringWithFormat:@"%.1f FPS · Vulkan", std::max(0.0, fps)];
    }
    _fps_last_presented = presented;
    _fps_last_update = now;
}

- (void)updateAudioDiagnostics {
    const NSTimeInterval now = CACurrentMediaTime();
    if (_last_audio_diag_update > 0.0 && now - _last_audio_diag_update < 0.5) return;
    _last_audio_diag_update = now;
    an3_native_renderer_metrics metrics{};
    if (!an3_native_get_renderer_metrics(&metrics)) return;
    _audio_diagnostics.stringValue = [NSString stringWithFormat:
        @"Core %.0f Hz · Effective %.0f Hz · Output %.0f Hz · Hardware %.0f Hz\n"
         "PCM in p%u nz%llu · out p%u nz%llu · callbacks s%llu b%llu · converter failures %llu (status %d, error %d)\n"
         "Player %@ · engine %@ · volume %.0f%%%@ · Queue %u/%u · underrun %llu · overrun %llu",
        metrics.audio_core_sample_rate, metrics.audio_effective_input_rate,
        metrics.audio_output_sample_rate, metrics.audio_hardware_sample_rate,
        metrics.audio_input_peak, metrics.audio_input_nonzero_samples,
        metrics.audio_output_peak, metrics.audio_output_nonzero_samples,
        metrics.audio_sample_callbacks, metrics.audio_batch_callbacks, metrics.audio_converter_failures,
        metrics.audio_converter_last_status, metrics.audio_converter_last_error,
        metrics.audio_player_playing ? @"playing" : @"stopped",
        metrics.audio_engine_running ? @"running" : @"stopped",
        metrics.audio_volume * 100.0f, metrics.audio_muted ? @" muted" : @"",
        metrics.audio_queue_depth_frames, metrics.audio_queue_max_frames,
        metrics.audio_underruns, metrics.audio_overruns];
    if (an3::active_host()) {
        const auto path = an3::active_host()->auto_save_file_path();
        NSDictionary* attributes = [[NSFileManager defaultManager]
            attributesOfItemAtPath:[NSString stringWithUTF8String:path.string().c_str()] error:nil];
        NSDate* date = attributes[NSFileModificationDate];
        if (date) {
            _auto_save_status.stringValue = [NSString stringWithFormat:@"Last Auto Save: %@",
                [NSDateFormatter localizedStringFromDate:date dateStyle:NSDateFormatterShortStyle timeStyle:NSDateFormatterShortStyle]];
        }
    }
}

- (void)updateQuickStateStatus:(const char*)details success:(BOOL)success {
    NSString* text = details ? [NSString stringWithUTF8String:details] : @"Quick-state action failed.";
    _quick_state_status.stringValue = text ?: @"Quick-state action failed.";
    _quick_state_status.textColor = success ? NSColor.secondaryLabelColor : NSColor.systemRedColor;
}

- (void)saveQuickSlot:(NSButton*)sender {
    char details[256]{};
    const int saved = an3_native_save_state(static_cast<unsigned>(sender.tag), details, sizeof(details));
    [self updateQuickStateStatus:details success:saved != 0];
}

- (void)loadQuickSlot:(NSButton*)sender {
    char details[256]{};
    const int loaded = an3_native_load_state(static_cast<unsigned>(sender.tag), details, sizeof(details));
    [self updateQuickStateStatus:details success:loaded != 0];
}

- (void)beginKeyMapping:(id)sender {
    NSMenuItem* selected = _key_map_action.selectedItem;
    if (!selected) return;
    _capturing_key_map = YES;
    _capturing_key_button = static_cast<unsigned>(selected.tag);
    _key_map_status.stringValue = [NSString stringWithFormat:@"Press a physical key for %@. Esc cancels.", selected.title];
    _key_map_status.textColor = NSColor.secondaryLabelColor;
    [self.window makeFirstResponder:self];
}

- (void)resetKeyMappings:(id)sender {
    an3::reset_button_key_mappings();
    _capturing_key_map = NO;
    _key_map_status.stringValue = @"Custom keyboard mapping reset to defaults.";
    _key_map_status.textColor = NSColor.secondaryLabelColor;
}

- (void)refreshCoreOptions {
    if (!_core_options_stack) return;
    for (NSView* view in [_core_options_stack.arrangedSubviews copy]) {
        [_core_options_stack removeArrangedSubview:view];
        [view removeFromSuperview];
    }
    auto* host = an3::active_host();
    if (!host || host->core_options().empty()) {
        [_core_options_stack addArrangedSubview:[NSTextField labelWithString:@"The core announced no configurable options."]];
        return;
    }
    std::string last_category;
    for (const auto& option : host->core_options()) {
        if (option.category != last_category && !option.category.empty()) {
            [_core_options_stack addArrangedSubview:native_settings_header([NSString stringWithUTF8String:option.category.c_str()])];
            last_category = option.category;
        }
        AN3CoreOptionPopup* popup = [[AN3CoreOptionPopup alloc] initWithFrame:NSZeroRect pullsDown:NO];
        popup.optionKey = [NSString stringWithUTF8String:option.key.c_str()];
        for (const auto& value : option.values) {
            [popup addItemWithTitle:[NSString stringWithUTF8String:value.label.c_str()]];
            popup.lastItem.representedObject = [NSString stringWithUTF8String:value.value.c_str()];
        }
        for (NSUInteger index = 0; index < option.values.size(); ++index) {
            if (option.values[index].value == option.current_value) {
                [popup selectItemAtIndex:index];
                break;
            }
        }
        popup.target = self;
        popup.action = @selector(changeCoreOption:);
        NSString* label = [NSString stringWithUTF8String:option.display_label.c_str()];
        if (option.restart_required) label = [label stringByAppendingString:@" · restart to apply"];
        NSStackView* row = [NSStackView stackViewWithViews:@[[NSTextField labelWithString:label], popup]];
        row.orientation = NSUserInterfaceLayoutOrientationHorizontal;
        row.spacing = 8.0;
        [_core_options_stack addArrangedSubview:row];
        if (!option.description.empty()) {
            NSTextField* description = [NSTextField labelWithString:[NSString stringWithUTF8String:option.description.c_str()]];
            description.font = [NSFont systemFontOfSize:10.0];
            description.textColor = NSColor.secondaryLabelColor;
            description.maximumNumberOfLines = 2;
            [_core_options_stack addArrangedSubview:description];
        }
    }
}

- (void)changeCoreOption:(AN3CoreOptionPopup*)sender {
    NSString* value = sender.selectedItem.representedObject ?: sender.selectedItem.title;
    if (!sender.optionKey.length || !value.length) return;
    _draft_core_options[sender.optionKey] = value;
    _settings_dirty = YES;
    _settings_save_status.stringValue = @"Core option staged · Save Settings to persist";
    _settings_save_status.textColor = NSColor.secondaryLabelColor;
}

- (void)refreshSaveStateAvailability {
    const BOOL available = an3::active_host() && an3::active_host()->supports_quick_states();
    _auto_save_mode_popup.enabled = available;
    _load_auto_save_button.enabled = available;
    if (!available) _auto_save_status.stringValue = @"Auto Save unavailable: this core does not support save states.";
}

- (void)togglePad:(id)sender {
    const BOOL hidden = !_dpad_up.hidden;
    for (NSView* control in _pad_controls) control.hidden = hidden;
    if (hidden) {
        _circle_key_directions = 0;
        if (auto* host = an3::active_host()) host->set_circle(0, 0);
    }
}

- (BOOL)isNds {
    return [_system isEqualToString:@"nds"];
}

- (BOOL)isThreeDs {
    return [_system isEqualToString:@"3ds"];
}

- (void)lockCursor:(id)sender {
    if (![self isNds]) return;
    auto* host = an3::active_host();
    if (!host || !host->running() || !host->is_nds()) return;
    if (!_cursor_locked) {
        if (CGAssociateMouseAndMouseCursorPosition(false) != kCGErrorSuccess) return;
        [NSCursor hide];
        _cursor_locked = YES;
        _cursor_lock_button.title = @"Cursor locked · Esc";
    }
    self.window.acceptsMouseMovedEvents = YES;
    [self.window makeFirstResponder:self];
}

- (void)releaseCursorLock {
    if (!_cursor_locked) return;
    if (auto* host = an3::active_host()) host->set_nds_touch_pressed(false);
    CGAssociateMouseAndMouseCursorPosition(true);
    [NSCursor unhide];
    _cursor_locked = NO;
    _cursor_lock_button.title = @"Lock cursor";
}

- (void)releaseCursorLockForNotification:(NSNotification*)notification {
    [self releaseCursorLock];
}

- (void)viewDidMoveToWindow {
    [super viewDidMoveToWindow];
    NSNotificationCenter* center = [NSNotificationCenter defaultCenter];
    [center removeObserver:self name:NSWindowDidResignKeyNotification object:nil];
    [center removeObserver:self name:NSApplicationDidResignActiveNotification object:nil];
    if (self.window) {
        [center addObserver:self selector:@selector(releaseCursorLockForNotification:)
                   name:NSWindowDidResignKeyNotification object:self.window];
        [center addObserver:self selector:@selector(releaseCursorLockForNotification:)
                   name:NSApplicationDidResignActiveNotification object:nil];
        if (!_applied_initial_fullscreen && [[NSUserDefaults standardUserDefaults] boolForKey:an3::kNativeStartFullscreenDefaultsKey]) {
            _applied_initial_fullscreen = YES;
            dispatch_async(dispatch_get_main_queue(), ^{
                if (self.window && !(self.window.styleMask & NSWindowStyleMaskFullScreen)) {
                    [self.window toggleFullScreen:nil];
                }
            });
        }
    }
}

- (void)viewWillMoveToWindow:(NSWindow*)newWindow {
    if (!newWindow) [self releaseCursorLock];
    [super viewWillMoveToWindow:newWindow];
}

- (void)updateTrackingAreas {
    if (_tracking_area) [self removeTrackingArea:_tracking_area];
    _tracking_area = [[NSTrackingArea alloc] initWithRect:NSZeroRect
                                                   options:NSTrackingMouseMoved | NSTrackingMouseEnteredAndExited |
                                                           NSTrackingActiveInKeyWindow | NSTrackingInVisibleRect
                                                     owner:self
                                                  userInfo:nil];
    [self addTrackingArea:_tracking_area];
    [super updateTrackingAreas];
}

- (void)dealloc {
    [self releaseCursorLock];
    [[NSNotificationCenter defaultCenter] removeObserver:self];
}

- (void)returnToLibrary:(id)sender {
    [self releaseCursorLock];
    dispatch_async(dispatch_get_main_queue(), ^{
        an3_native_stop();
    });
}

- (BOOL)acceptsFirstResponder {
    return YES;
}

- (BOOL)resignFirstResponder {
    [self releaseCursorLock];
    _circle_key_directions = 0;
    if (auto* host = an3::active_host()) host->clear_input();
    return [super resignFirstResponder];
}

- (void)drawInMTKView:(MTKView*)view {
    if (auto* host = an3::active_host()) {
        [self handleControllerMenuButtons:host->controller_buttons()];
        host->draw();
    }
    [self updateFpsOverlay];
    [self updateAudioDiagnostics];
    [self syncSpeedControls];
}

- (void)mtkView:(MTKView*)view drawableSizeWillChange:(CGSize)size {
}

- (void)syncCirclePadKeys {
    const int horizontal = ((_circle_key_directions & 0x2) ? 1 : 0) - ((_circle_key_directions & 0x1) ? 1 : 0);
    const int vertical = ((_circle_key_directions & 0x8) ? 1 : 0) - ((_circle_key_directions & 0x4) ? 1 : 0);
    constexpr int16_t cardinal = 32767;
    constexpr int16_t diagonal = 23170;
    const int16_t magnitude = horizontal && vertical ? diagonal : cardinal;
    if (auto* host = an3::active_host()) {
        host->set_circle(static_cast<int16_t>(horizontal * magnitude), static_cast<int16_t>(vertical * magnitude));
    }
}

- (BOOL)updateCirclePadKey:(NSEvent*)event pressed:(BOOL)pressed {
    if (![self isThreeDs]) return NO;
    uint8_t direction = 0;
    switch (event.keyCode) {
    case 123: direction = 0x1; break; // left
    case 124: direction = 0x2; break; // right
    case 126: direction = 0x4; break; // up: raw libretro Y is negative
    case 125: direction = 0x8; break; // down
    default: return NO;
    }
    if (pressed) {
        if (!(event.modifierFlags & NSEventModifierFlagOption)) return NO;
        _circle_key_directions |= direction;
    } else {
        if (!(_circle_key_directions & direction)) return NO;
        _circle_key_directions &= ~direction;
    }
    [self syncCirclePadKeys];
    return YES;
}

- (void)keyDown:(NSEvent*)event {
    if (_capturing_key_map) {
        if (event.keyCode == 53) {
            _capturing_key_map = NO;
            _key_map_status.stringValue = @"Keyboard mapping cancelled.";
            _key_map_status.textColor = NSColor.secondaryLabelColor;
            return;
        }
        an3::set_button_key_mapping(event.keyCode, _capturing_key_button);
        _ignore_key_up = static_cast<NSUInteger>(event.keyCode) + 1u;
        _capturing_key_map = NO;
        _key_map_status.stringValue = @"Custom keyboard mapping saved.";
        _key_map_status.textColor = NSColor.secondaryLabelColor;
        return;
    }
    if (event.keyCode == 53) {
        if (!_menu_panel.hidden) {
            [self closeMenuDiscardingDraft];
            return;
        }
        if ([self isNds] && _cursor_locked) {
            [self releaseCursorLock];
            return;
        }
        [self returnToLibrary:nil];
        return;
    }
    if ([self updateCirclePadKey:event pressed:YES]) return;
    if (auto* host = an3::active_host()) host->set_button(an3::button_for_key(event.keyCode), true);
}

- (void)keyUp:(NSEvent*)event {
    if (_ignore_key_up == static_cast<NSUInteger>(event.keyCode) + 1u) {
        _ignore_key_up = 0;
        return;
    }
    if (event.keyCode == 53) return;
    if ([self updateCirclePadKey:event pressed:NO]) return;
    if (auto* host = an3::active_host()) host->set_button(an3::button_for_key(event.keyCode), false);
}

- (void)updateTouch:(NSEvent*)event pressed:(BOOL)pressed {
    if (auto* host = an3::active_host()) {
        const NSPoint point = [self convertPoint:event.locationInWindow fromView:nil];
        host->set_touch_from_view(point, self.bounds.size, pressed);
    }
}

- (void)mouseMoved:(NSEvent*)event {
    // An open menu owns pointer input; the game surface must not also react.
    if (!_menu_panel.hidden) return;
    if ([self isNds] && _cursor_locked) {
        // AppKit's locked-event deltas enter the single platform transform
        // boundary here. The core receives physical right/down as positive.
        if (auto* host = an3::active_host()) host->move_nds_cursor(event.deltaX, event.deltaY);
    }
}

- (void)mouseDown:(NSEvent*)event {
    if (!_menu_panel.hidden) return;
    if ([self isNds]) {
        [self lockCursor:nil];
        if (auto* host = an3::active_host()) host->set_nds_touch_pressed(_cursor_locked);
        return;
    }
    if ([self isThreeDs]) [self updateTouch:event pressed:YES];
}

- (void)mouseDragged:(NSEvent*)event {
    if (!_menu_panel.hidden) return;
    if ([self isNds] && _cursor_locked) {
        if (auto* host = an3::active_host()) {
            host->move_nds_cursor(event.deltaX, event.deltaY);
            host->set_nds_touch_pressed(true);
        }
        return;
    }
    if ([self isThreeDs]) [self updateTouch:event pressed:YES];
}

- (void)mouseUp:(NSEvent*)event {
    if ([self isNds]) {
        // Always clear a held touch, even if the menu opened mid-drag.
        if (auto* host = an3::active_host()) host->set_nds_touch_pressed(false);
        if (!_menu_panel.hidden) return;
        return;
    }
    if (!_menu_panel.hidden) return;
    if ([self isThreeDs]) [self updateTouch:event pressed:NO];
}

@end

@implementation AN3CoreOptionPopup
@end

@implementation AN3InertLabel
- (NSView*)hitTest:(NSPoint)point { return nil; }
@end

@implementation AN3InputButton

- (BOOL)acceptsFirstResponder {
    return NO;
}

- (void)mouseDown:(NSEvent*)event {
    if (auto* host = an3::active_host()) host->set_button(self.input_button, true);
    [super mouseDown:event];
    if (auto* host = an3::active_host()) host->set_button(self.input_button, false);
    if (NSView* view = self.superview) [self.window makeFirstResponder:view];
}

@end

@implementation AN3CirclePadView

- (instancetype)initWithFrame:(NSRect)frameRect {
    self = [super initWithFrame:frameRect];
    if (self) {
        self.wantsLayer = YES;
        self.layer.backgroundColor = [[NSColor colorWithWhite:0.08 alpha:0.72] CGColor];
        self.layer.borderColor = [[NSColor colorWithWhite:1.0 alpha:0.5] CGColor];
        self.layer.borderWidth = 1.5;
        self.layer.cornerRadius = 54.0;
    }
    return self;
}

- (BOOL)acceptsFirstResponder {
    return NO;
}

- (void)drawRect:(NSRect)dirtyRect {
    const CGFloat radius = std::min(self.bounds.size.width, self.bounds.size.height) * 0.5;
    self.layer.cornerRadius = radius;
    const CGFloat thumb = radius * an3::player_ui::thumb_radius_ratio;
    const CGFloat travel = radius * an3::player_ui::travel_ratio;
    [[NSColor colorWithWhite:1.0 alpha:0.85] setFill];
    [[NSBezierPath bezierPathWithOvalInRect:NSMakeRect(NSMidX(self.bounds) + _stick_x * travel - thumb,
        NSMidY(self.bounds) + _stick_y * travel - thumb, thumb * 2.0, thumb * 2.0)] fill];
}

- (void)updateCircle:(NSEvent*)event {
    const NSPoint point = [self convertPoint:event.locationInWindow fromView:nil];
    const CGFloat travel = std::max<CGFloat>(1.0, std::min(self.bounds.size.width, self.bounds.size.height) * 0.5 * an3::player_ui::travel_ratio);
    const auto axis = an3::player_ui::normalize((point.x - NSMidX(self.bounds)) / travel,
                                               (point.y - NSMidY(self.bounds)) / travel);
    _stick_x = axis.x; _stick_y = axis.y;
    [self setNeedsDisplay:YES];
    if (auto* host = an3::active_host()) {
        host->set_circle(static_cast<int16_t>(std::lround(axis.x * 32767.0)),
                         static_cast<int16_t>(std::lround(-axis.y * 32767.0)));
    }
}

- (void)mouseDown:(NSEvent*)event { [self updateCircle:event]; }
- (void)mouseDragged:(NSEvent*)event { [self updateCircle:event]; }
- (void)mouseUp:(NSEvent*)event {
    [self releaseCircle];
    if (NSView* view = self.superview) [self.window makeFirstResponder:view];
}

- (void)releaseCircle {
    _stick_x = 0.0; _stick_y = 0.0;
    if (auto* host = an3::active_host()) host->set_circle(0, 0);
    [self setNeedsDisplay:YES];
}

- (void)viewDidMoveToWindow {
    [[NSNotificationCenter defaultCenter] removeObserver:self name:NSWindowDidResignKeyNotification object:nil];
    if (self.window) [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(circleWindowResigned:)
        name:NSWindowDidResignKeyNotification object:self.window];
    [self releaseCircle];
}
- (void)circleWindowResigned:(NSNotification*)notification { [self releaseCircle]; }
- (void)setHidden:(BOOL)hidden { [super setHidden:hidden]; if (hidden) [self releaseCircle]; }

@end

extern "C" int an3_native_probe(const char* core_path, char* details, size_t details_length) {
    std::string error;
    an3::CoreApi core;
    if (!core_path || !core.open(core_path, error)) {
        if (details && details_length) std::snprintf(details, details_length, "%s", error.c_str());
        return 0;
    }
    an3::retro_system_info info{};
    core.get_system_info(&info);
    const unsigned api = core.api_version();
    if (details && details_length) {
        std::snprintf(details, details_length, "%s %s · %s",
                      info.library_name ? info.library_name : "native libretro core",
                      info.library_version ? info.library_version : "unknown version",
                      info.valid_extensions ? info.valid_extensions : "no formats advertised");
    }
    core.close();
    return static_cast<int>(api);
}

extern "C" int an3_native_start(void* content_view,
                                  const char* core_path,
                                  const char* moltenvk_path,
                                  const char* rom_path,
                                  const char* rom_id,
                                  const char* save_directory,
                                  const char* system_directory,
                                  const char* system,
                                  const char* layout,
                                  char* details,
                                  size_t details_length) {
    an3_native_stop();
    if (!content_view) {
        if (details && details_length) std::snprintf(details, details_length, "VibeCodedEmulator native window is unavailable.");
        return 0;
    }
    const std::string requested_system = system ?: "";
    if (requested_system != "gba" && requested_system != "nds" && requested_system != "3ds") {
        if (details && details_length) std::snprintf(details, details_length, "Unsupported native system requested.");
        return 0;
    }
    auto host = std::make_unique<an3::AzaharHost>();
    // The core invokes our environment callback from retro_init/load_game.
    // Keeping this assignment after host->start made those calls observe a
    // null active host, causing an otherwise valid local ROM to be rejected.
    an3::g_host = host.release();
    NSView* content = (__bridge NSView*)content_view;
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    an3::g_view = [[AN3AzaharView alloc] initWithFrame:content.bounds device:device system:system];
    an3::g_view.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    an3::g_view.colorPixelFormat = MTLPixelFormatBGRA8Unorm;
    an3::g_view.framebufferOnly = NO;
    an3::g_view.clearColor = MTLClearColorMake(0.0, 0.0, 0.0, 1.0);
    an3::g_view.preferredFramesPerSecond = 60;
    an3::g_view.paused = YES;
    [content addSubview:an3::g_view positioned:NSWindowAbove relativeTo:nil];
    [content.window makeFirstResponder:an3::g_view];
    CAMetalLayer* metal_layer = [an3::g_view.layer isKindOfClass:CAMetalLayer.class]
                                      ? (CAMetalLayer*)an3::g_view.layer
                                      : nil;
    std::string error;
    if (!an3::g_host->start(core_path, moltenvk_path, rom_path, rom_id, save_directory, system_directory, system, layout,
                             metal_layer, error)) {
        an3_native_stop();
        if (details && details_length) std::snprintf(details, details_length, "%s", error.c_str());
        return 0;
    }
    an3::g_view.delegate = an3::g_view;
    an3::g_view.paused = NO;
    [an3::g_view refreshCoreOptions];
    [an3::g_view refreshSaveStateAvailability];
    [an3::g_view syncSpeedControls];
    if (details && details_length) std::snprintf(details, details_length, "%s native core is running inside VibeCodedEmulator.", requested_system.c_str());
    return 1;
}

extern "C" void an3_native_stop(void) {
    if (an3::g_view) [an3::g_view releaseCursorLock];
    if (an3::g_host) {
        an3::g_host->stop();
        delete an3::g_host;
        an3::g_host = nullptr;
    }
    if (an3::g_view) {
        an3::g_view.paused = YES;
        an3::g_view.delegate = nil;
        [an3::g_view removeFromSuperview];
        an3::g_view = nil;
    }
}

extern "C" int an3_native_is_running(void) {
    // Phone Controller hot-path readiness must never wait on the mutex held
    // across draw/core execution. Lifecycle code publishes this after init and
    // clears it before entering stop().
    return an3::g_host && an3::g_host->controller_input_ready() ? 1 : 0;
}

// 0 = none, 1 = gba, 2 = nds, 3 = 3ds. Used only so the phone controller can
// tell the phone which pad layout to show.
extern "C" int an3_native_active_system(void) {
    return an3::g_host ? an3::g_host->active_system_code() : 0;
}

extern "C" uint64_t an3_native_presented_frames(void) {
    return an3::g_host ? an3::g_host->presented_frames() : 0;
}

extern "C" int an3_native_get_renderer_metrics(an3_native_renderer_metrics* metrics) {
    if (!metrics || !an3::g_host || !an3::g_host->running()) return 0;
    const an3::NativeRendererMetrics snapshot = an3::g_host->renderer_metrics();
    metrics->presented_frames = snapshot.presented_frames;
    metrics->dropped_frames = snapshot.dropped_frames;
    metrics->software_uploads = snapshot.software_uploads;
    metrics->direct_software_uploads = snapshot.direct_software_uploads;
    metrics->copied_software_uploads = snapshot.copied_software_uploads;
    metrics->converted_software_uploads = snapshot.converted_software_uploads;
    metrics->upload_p95_us = snapshot.upload_p95_us;
    metrics->upload_p99_us = snapshot.upload_p99_us;
    metrics->present_p95_us = snapshot.present_p95_us;
    metrics->present_p99_us = snapshot.present_p99_us;
    metrics->emulate_p95_us = snapshot.emulate_p95_us;
    metrics->emulate_p99_us = snapshot.emulate_p99_us;
    metrics->audio_queue_depth_frames = snapshot.audio_queue_depth_frames;
    metrics->audio_queue_max_frames = snapshot.audio_queue_max_frames;
    metrics->audio_underruns = snapshot.audio_underruns;
    metrics->audio_overruns = snapshot.audio_overruns;
    metrics->audio_core_sample_rate = snapshot.audio_core_sample_rate;
    metrics->audio_output_sample_rate = snapshot.audio_output_sample_rate;
    metrics->audio_hardware_sample_rate = snapshot.audio_hardware_sample_rate;
    metrics->audio_effective_input_rate = snapshot.audio_effective_input_rate;
    metrics->audio_core_channels = snapshot.audio_core_channels;
    metrics->audio_output_channels = snapshot.audio_output_channels;
    metrics->audio_sample_callbacks = snapshot.audio_sample_callbacks;
    metrics->audio_batch_callbacks = snapshot.audio_batch_callbacks;
    metrics->audio_input_frames = snapshot.audio_input_frames;
    metrics->audio_output_frames = snapshot.audio_output_frames;
    metrics->audio_input_nonzero_samples = snapshot.audio_input_nonzero_samples;
    metrics->audio_output_nonzero_samples = snapshot.audio_output_nonzero_samples;
    metrics->audio_input_energy = snapshot.audio_input_energy;
    metrics->audio_output_energy = snapshot.audio_output_energy;
    metrics->audio_input_peak = snapshot.audio_input_peak;
    metrics->audio_output_peak = snapshot.audio_output_peak;
    metrics->audio_converter_failures = snapshot.audio_converter_failures;
    metrics->audio_converter_last_status = snapshot.audio_converter_last_status;
    metrics->audio_converter_last_error = snapshot.audio_converter_last_error;
    metrics->audio_scheduled_buffers = snapshot.audio_scheduled_buffers;
    metrics->audio_player_playing = snapshot.audio_player_playing ? 1 : 0;
    metrics->audio_engine_running = snapshot.audio_engine_running ? 1 : 0;
    metrics->audio_muted = snapshot.audio_muted ? 1 : 0;
    metrics->audio_volume = snapshot.audio_volume;
    metrics->resident_memory_bytes = snapshot.resident_memory_bytes;
    metrics->cpu_user_time_us = snapshot.cpu_user_time_us;
    metrics->cpu_system_time_us = snapshot.cpu_system_time_us;
    return 1;
}

extern "C" int an3_native_save_state(unsigned slot, char* details, size_t details_length) {
    std::string error;
    const bool saved = an3::g_host ? an3::g_host->save_state(slot, error) : false;
    if (!saved && error.empty()) error = "The native player is not running.";
    if (details && details_length) {
        std::snprintf(details, details_length, "%s", saved ? "Quick save complete." : error.c_str());
    }
    return saved ? 1 : 0;
}

extern "C" int an3_native_load_state(unsigned slot, char* details, size_t details_length) {
    std::string error;
    const bool loaded = an3::g_host ? an3::g_host->load_state(slot, error) : false;
    if (!loaded && error.empty()) error = "The native player is not running.";
    if (details && details_length) {
        std::snprintf(details, details_length, "%s", loaded ? "Quick save loaded." : error.c_str());
    }
    return loaded ? 1 : 0;
}

extern "C" int an3_native_export_state(const char* path, char* details, size_t details_length) {
    std::string error;
    const bool exported = an3::g_host && path && an3::g_host->export_state(std::filesystem::path(path), error);
    if (!exported && error.empty()) error = "The native player is not running.";
    if (details && details_length) {
        std::snprintf(details, details_length, "%s", exported ? "Save state exported." : error.c_str());
    }
    return exported ? 1 : 0;
}

extern "C" int an3_native_import_state(const char* path, char* details, size_t details_length) {
    std::string error;
    const bool imported = an3::g_host && path && an3::g_host->import_state(std::filesystem::path(path), error);
    if (!imported && error.empty()) error = "The native player is not running.";
    if (details && details_length) {
        std::snprintf(details, details_length, "%s", imported ? "Save state imported." : error.c_str());
    }
    return imported ? 1 : 0;
}

// Routes the Phone Controller's one-shot utility actions to the same host
// operations the toolbar and keyboard shortcuts already use. No second
// save-state or speed implementation is introduced.
extern "C" int an3_native_apply_utility_at_slot(const char* action,
                                                   unsigned slot,
                                                   char* details,
                                                   size_t details_length) {
    // The host's supported speed steps, matching the toolbar and schema.
    static constexpr double kSpeeds[] = {0.5, 1.0, 2.0, 4.0, 8.0};
    const auto finish = [&](bool applied, const std::string& message) {
        if (details && details_length) std::snprintf(details, details_length, "%s", message.c_str());
        return applied ? 1 : 0;
    };
    if (!action || !*action) return finish(false, "Missing utility action.");
    const std::string name(action);
    if ((name == "QUICK_SAVE" || name == "QUICK_LOAD") && (slot < 1 || slot > 10)) {
        return finish(false, "Save-state slot must be between 1 and 10.");
    }
    const auto apply_on_main = [name, slot]() -> std::pair<bool, std::string> {
        if (!an3::g_host || !an3::g_host->running()) {
            return {false, "The native player is not running."};
        }
        if (name == "QUICK_SAVE") {
            std::string error;
            const bool saved = an3::g_host->save_state(slot, error);
            return {saved, saved ? "Quick save complete." : (error.empty() ? "Quick save failed." : error)};
        }
        if (name == "QUICK_LOAD") {
            std::string error;
            const bool loaded = an3::g_host->load_state(slot, error);
            return {loaded, loaded ? "Quick load complete." : (error.empty() ? "Quick load failed." : error)};
        }
        if (name == "SPEED_UP" || name == "SPEED_DOWN") {
            const double current = an3::g_host->speed();
            int index = 1;
            for (int step = 0; step < 5; ++step) {
                if (std::abs(kSpeeds[step] - current) < 0.001) index = step;
            }
            index = std::clamp(index + (name == "SPEED_UP" ? 1 : -1), 0, 4);
            an3::g_host->set_speed(kSpeeds[index]);
            if (an3::g_view) [an3::g_view syncSpeedControls];
            return {true, "Speed changed."};
        }
        if (name == "OPEN_MENU") {
            if (!an3::g_view) return {false, "The native player menu is unavailable."};
            [an3::g_view openMenu];
            return {true, "Menu opened."};
        }
        return {false, "Unsupported utility action '" + name + "'."};
    };

    // Controller frames arrive on a transport worker, but the menu and speed
    // controls are AppKit objects and the core frame callback may be active on
    // another thread. Serialize the actual operation on the UI queue; callers
    // wait for its real result rather than acknowledging queued work.
    if ([NSThread isMainThread]) {
        const auto [applied, message] = apply_on_main();
        return finish(applied, message);
    }
    struct PendingUtilityResult {
        std::mutex mutex;
        std::condition_variable completed;
        bool done = false;
        bool applied = false;
        std::string message;
    };
    const auto result = std::make_shared<PendingUtilityResult>();
    dispatch_async(dispatch_get_main_queue(), ^{
        const auto [applied, message] = apply_on_main();
        {
            std::lock_guard<std::mutex> lock(result->mutex);
            result->applied = applied;
            result->message = message;
            result->done = true;
        }
        result->completed.notify_one();
    });
    std::unique_lock<std::mutex> lock(result->mutex);
    result->completed.wait(lock, [&] { return result->done; });
    return finish(result->applied, result->message);
}

extern "C" int an3_native_apply_utility(const char* action, char* details, size_t details_length) {
    return an3_native_apply_utility_at_slot(action, 1, details, details_length);
}

extern "C" void an3_native_set_input(uint32_t buttons,
                                       int16_t circle_x,
                                       int16_t circle_y,
                                       int16_t cstick_x,
                                       int16_t cstick_y,
                                       int16_t touch_x,
                                       int16_t touch_y,
                                       int touch_pressed) {
    if (an3::g_host) {
        an3::g_host->set_input(buttons, circle_x, circle_y, cstick_x, cstick_y, touch_x, touch_y, touch_pressed != 0);
    }
}
