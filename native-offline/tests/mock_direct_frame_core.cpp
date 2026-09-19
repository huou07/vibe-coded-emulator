#include <array>
#include <cstddef>
#include <cstdint>

// Minimal libretro test core that exercises GET_CURRENT_SOFTWARE_FRAMEBUFFER.
// It is not packaged and has no game logic; its sole purpose is proving that
// the host can hand a core a persistently mapped direct-write upload slot.
namespace {

constexpr unsigned kEnvironmentSetPixelFormat = 10;
constexpr unsigned kEnvironmentGetVariable = 15;
constexpr unsigned kEnvironmentSetVariables = 16;
constexpr unsigned kEnvironmentGetCurrentSoftwareFramebuffer = 40 | 0x10000;
constexpr int kPixelFormatXrgb8888 = 1;
constexpr unsigned kMemoryAccessWrite = 1u << 0;
constexpr unsigned kDeviceJoypad = 1;
constexpr unsigned kDevicePointer = 6;
constexpr unsigned kJoypadMask = 256;
constexpr unsigned kPointerX = 0;
constexpr unsigned kPointerY = 1;
constexpr unsigned kPointerPressed = 2;
constexpr unsigned kWidth = 240;
constexpr unsigned kHeight = 160;
constexpr unsigned kMaxInputObservations = 64;

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
    std::size_t size;
    const char* meta;
};
struct retro_game_geometry {
    unsigned base_width;
    unsigned base_height;
    unsigned max_width;
    unsigned max_height;
    float aspect_ratio;
};
struct retro_system_timing {
    double fps;
    double sample_rate;
};
struct retro_system_av_info {
    retro_game_geometry geometry;
    retro_system_timing timing;
};
struct retro_framebuffer {
    void* data;
    unsigned width;
    unsigned height;
    std::size_t pitch;
    int format;
    unsigned access_flags;
    unsigned memory_flags;
};

using Environment = bool (*)(unsigned, void*);
using VideoRefresh = void (*)(const void*, unsigned, unsigned, std::size_t);
using AudioSample = void (*)(std::int16_t, std::int16_t);
using AudioBatch = std::size_t (*)(const std::int16_t*, std::size_t);
using InputPoll = void (*)();
using InputState = std::int16_t (*)(unsigned, unsigned, unsigned, unsigned);

struct RetroVariable {
    const char* key;
    const char* value;
};

Environment environment = nullptr;
VideoRefresh video_refresh = nullptr;
InputState input_state = nullptr;
std::array<std::uint32_t, kWidth * kHeight> fallback{};
std::uint32_t frame = 0;

struct InputObservation {
    std::uint32_t buttons = 0;
    std::int16_t pointer_x = 0;
    std::int16_t pointer_y = 0;
    std::int16_t pointer_pressed = 0;
};

std::array<InputObservation, kMaxInputObservations> input_observations{};
unsigned input_observation_count = 0;
std::array<char, 32> layout_seen_at_load{};

void remember_layout(const char* value) {
    unsigned index = 0;
    if (value) {
        for (; value[index] && index + 1 < layout_seen_at_load.size(); ++index) {
            layout_seen_at_load[index] = value[index];
        }
    }
    layout_seen_at_load[index] = '\0';
}

} // namespace

extern "C" {

unsigned retro_api_version() { return 1; }
void retro_init() {}
void retro_deinit() {}
void retro_get_system_info(retro_system_info* info) {
    if (info) *info = {"AN3 direct-frame test core", "1", "gba", true, false};
}
void retro_get_system_av_info(retro_system_av_info* info) {
    if (info) *info = {{kWidth, kHeight, kWidth, kHeight, 3.0f / 2.0f}, {60.0, 48'000.0}};
}
void retro_set_environment(Environment callback) {
    environment = callback;
    if (environment) {
        int format = kPixelFormatXrgb8888;
        environment(kEnvironmentSetPixelFormat, &format);
        RetroVariable variables[] = {
            {"melonds_screen_layout1", "top-bottom|left-right"},
            {nullptr, nullptr},
        };
        environment(kEnvironmentSetVariables, variables);
    }
}
void retro_set_video_refresh(VideoRefresh callback) { video_refresh = callback; }
void retro_set_audio_sample(AudioSample) {}
void retro_set_audio_sample_batch(AudioBatch) {}
void retro_set_input_poll(InputPoll) {}
void retro_set_input_state(InputState callback) { input_state = callback; }
void retro_set_controller_port_device(unsigned, unsigned) {}
bool retro_load_game(const retro_game_info*) {
    RetroVariable variable{"melonds_screen_layout1", nullptr};
    if (environment && environment(kEnvironmentGetVariable, &variable)) {
        remember_layout(variable.value);
    } else {
        remember_layout(nullptr);
    }
    return true;
}
void retro_unload_game() {}
std::size_t retro_serialize_size() { return sizeof(frame); }
bool retro_serialize(void* data, std::size_t size) {
    if (!data || size != sizeof(frame)) return false;
    *static_cast<std::uint32_t*>(data) = frame;
    return true;
}
bool retro_unserialize(const void* data, std::size_t size) {
    if (!data || size != sizeof(frame)) return false;
    frame = *static_cast<const std::uint32_t*>(data);
    return true;
}
void retro_run() {
    InputObservation observation{};
    if (input_state) {
        observation.buttons = static_cast<std::uint32_t>(input_state(0, kDeviceJoypad, 0, kJoypadMask));
        observation.pointer_x = input_state(0, kDevicePointer, 0, kPointerX);
        observation.pointer_y = input_state(0, kDevicePointer, 0, kPointerY);
        observation.pointer_pressed = input_state(0, kDevicePointer, 0, kPointerPressed);
    }
    if (input_observation_count < input_observations.size()) {
        input_observations[input_observation_count] = observation;
    }
    ++input_observation_count;

    retro_framebuffer framebuffer{nullptr, kWidth, kHeight, 0, kPixelFormatXrgb8888, kMemoryAccessWrite, 0};
    const bool direct = environment && environment(kEnvironmentGetCurrentSoftwareFramebuffer, &framebuffer) &&
                        framebuffer.data && framebuffer.pitch >= kWidth * sizeof(std::uint32_t);
    auto* pixels = direct ? static_cast<std::uint32_t*>(framebuffer.data) : fallback.data();
    const std::size_t pitch = direct ? framebuffer.pitch : kWidth * sizeof(std::uint32_t);
    for (unsigned y = 0; y < kHeight; ++y) {
        auto* row = reinterpret_cast<std::uint32_t*>(reinterpret_cast<std::uint8_t*>(pixels) + y * pitch);
        for (unsigned x = 0; x < kWidth; ++x) row[x] = 0xff000000u | ((x + frame) & 0xffu) | ((y & 0xffu) << 8);
    }
    ++frame;
    if (video_refresh) video_refresh(pixels, kWidth, kHeight, pitch);
}

unsigned an3_test_input_observation_count() {
    return input_observation_count;
}

int an3_test_read_input_observation(unsigned index, std::uint32_t* buttons,
                                    std::int16_t* pointer_x, std::int16_t* pointer_y,
                                    std::int16_t* pointer_pressed) {
    if (index >= input_observation_count || index >= input_observations.size() ||
        !buttons || !pointer_x || !pointer_y || !pointer_pressed) {
        return 0;
    }
    const InputObservation& observation = input_observations[index];
    *buttons = observation.buttons;
    *pointer_x = observation.pointer_x;
    *pointer_y = observation.pointer_y;
    *pointer_pressed = observation.pointer_pressed;
    return 1;
}

const char* an3_test_layout_seen_at_load() {
    return layout_seen_at_load.data();
}

} // extern "C"
