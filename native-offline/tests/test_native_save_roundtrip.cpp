// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Deterministic host-level verification of native save round-trips, using the
// real mGBA libretro core and the lawful homebrew fixture. It does not need a
// window, audio device, or emulator device, so it runs the same on a developer
// host as in CI.
//
// It proves three things with byte-level evidence:
//   1. save-state RESTORATION: state -> mutate -> load -> state reproduces the
//      original bytes exactly (a load that did nothing cannot pass);
//   2. SRAM persistence: stopping writes a 32 KiB .srm carrying the fixture's
//      "AN3B" signature;
//   3. SRAM RESTORATION: a second run reads the persisted save back (the
//      fixture's boot counter advances only if the load happened).
//
// Build/run: tests/run-native-save-test.sh  (macOS arm64)

#include "../native-runtime/core/libretro_host.h"
#include "../native-runtime/core/vendor/libretro.h"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

namespace {

class StubVideo final : public an3::NativeVideoBackend {
public:
    enum class Primary { Red, Green, Blue };

    bool initialize(an3::NativeWindowSurface&, std::string&) override { return true; }
    void resize() override {}
    bool begin_frame() override { return true; }
    bool acquire_software_framebuffer(unsigned, unsigned, int, void*& data, std::size_t& size) override {
        data = nullptr; size = 0; return false;
    }
    void present_software(const void* data, unsigned width, unsigned height,
                         std::size_t pitch, int format) override {
        if (!data || !width || !height || !pitch) return;
        last_width = width;
        last_height = height;
        last_pitch = pitch;
        last_format = format;
        const auto* bytes = static_cast<const std::uint8_t*>(data);
        last_pixels.assign(bytes, bytes + pitch * height);
        ++presented_frames;
    }
    bool receive_native_gpu_frame(const void*, std::string&) override { return false; }
    void present_native_gpu_frame(unsigned, unsigned) override {}
    an3::NativeVideoStatus metrics() const override { return {}; }
    void shutdown() override {}

    bool captured_gba_frame() const {
        return presented_frames > 0 && last_width == 240 && last_height == 160 &&
               last_pixels.size() >= last_pitch * last_height;
    }

    bool first_pixel_is_dominant(Primary primary) const {
        if (!captured_gba_frame()) return false;
        unsigned r = 0, g = 0, b = 0, threshold = 24;
        if (last_format == RETRO_PIXEL_FORMAT_0RGB1555 && last_pitch >= 2) {
            const unsigned pixel = last_pixels[0] | (static_cast<unsigned>(last_pixels[1]) << 8);
            r = (pixel >> 10) & 0x1f;
            g = (pixel >> 5) & 0x1f;
            b = pixel & 0x1f;
        } else if (last_format == RETRO_PIXEL_FORMAT_RGB565 && last_pitch >= 2) {
            const unsigned pixel = last_pixels[0] | (static_cast<unsigned>(last_pixels[1]) << 8);
            r = (pixel >> 11) & 0x1f;
            g = (pixel >> 5) & 0x3f;
            b = pixel & 0x1f;
        } else if (last_format == RETRO_PIXEL_FORMAT_XRGB8888 && last_pitch >= 4) {
            const unsigned pixel = last_pixels[0] | (static_cast<unsigned>(last_pixels[1]) << 8) |
                                   (static_cast<unsigned>(last_pixels[2]) << 16) |
                                   (static_cast<unsigned>(last_pixels[3]) << 24);
            r = (pixel >> 16) & 0xff;
            g = (pixel >> 8) & 0xff;
            b = pixel & 0xff;
            threshold = 192;
        } else {
            return false;
        }
        switch (primary) {
        case Primary::Red: return r >= threshold && r > g * 2 && r > b * 2;
        case Primary::Green: return g >= threshold && g > r * 2 && g > b * 2;
        case Primary::Blue: return b >= threshold && b > r * 2 && b > g * 2;
        }
        return false;
    }

    void report_first_pixel(const char* label) const {
        std::fprintf(stderr, "%s: format=%d size=%ux%u pitch=%zu pixel0=%02x %02x %02x %02x\n",
                     label, last_format, last_width, last_height, last_pitch,
                     last_pixels.size() > 0 ? last_pixels[0] : 0,
                     last_pixels.size() > 1 ? last_pixels[1] : 0,
                     last_pixels.size() > 2 ? last_pixels[2] : 0,
                     last_pixels.size() > 3 ? last_pixels[3] : 0);
    }

private:
    unsigned presented_frames = 0;
    unsigned last_width = 0, last_height = 0;
    std::size_t last_pitch = 0;
    int last_format = -1;
    std::vector<std::uint8_t> last_pixels;
};

class StubAudio final : public an3::NativeAudioBackend {
public:
    bool initialize(double, std::string&) override { return true; }
    std::size_t submit(const int16_t*, std::size_t frames) override { return frames; }
    void shutdown() override {}
};

std::string read_file(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    return std::string(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
}

std::string find_file(const std::string& root, const std::string& needle) {
    if (!std::filesystem::is_directory(root)) return {};
    for (const auto& entry : std::filesystem::recursive_directory_iterator(root)) {
        if (entry.is_regular_file() && entry.path().filename().string().find(needle) != std::string::npos)
            return entry.path().string();
    }
    return {};
}

bool run_frames(an3::NativeCoreHost& host, int count, const char* label, bool present = false) {
    std::string error;
    for (int i = 0; i < count; ++i) {
        if (!host.run_one(error, present)) {
            std::fprintf(stderr, "FAIL: %s: run_one failed at frame %d: %s\n", label, i, error.c_str());
            return false;
        }
    }
    return true;
}

} // namespace

int main(int argc, char** argv) {
    if (argc < 4) {
        std::fprintf(stderr, "usage: %s <mgba-core> <gba-fixture> <save-dir>\n", argv[0]);
        return 2;
    }
    const std::string core = argv[1], rom = argv[2], savedir = argv[3];
    int failures = 0;
    auto check = [&](bool ok, const char* what) {
        std::printf("%s %s\n", ok ? "PASS" : "FAIL", what);
        if (!ok) ++failures;
    };

    // ---- run 1: create state files and the battery save ----
    {
        an3::NativeCoreHost host; StubVideo video; StubAudio audio; std::string error;
        if (!host.initialize(core, rom, savedir, video, audio, error)) {
            std::fprintf(stderr, "FAIL: initialize (run 1): %s\n", error.c_str());
            return 1;
        }
        check(run_frames(host, 5, "run1 visible frames", true), "run 1 emitted presented frames");
        check(video.captured_gba_frame(), "the GBA core emitted a 240x160 software frame");
        const bool fresh_frame_is_blue = video.first_pixel_is_dominant(StubVideo::Primary::Blue);
        if (!fresh_frame_is_blue) video.report_first_pixel("fresh boot frame");
        check(fresh_frame_is_blue, "fresh boot rendered the fixture's blue frame");
        host.input().set_button(RETRO_DEVICE_ID_JOYPAD_A, true);
        check(run_frames(host, 5, "run1 A-button frames", true), "run 1 accepted presented A-button frames");
        const bool a_frame_is_red = video.first_pixel_is_dominant(StubVideo::Primary::Red);
        if (!a_frame_is_red) video.report_first_pixel("A-button frame");
        check(a_frame_is_red, "holding A changed the fixture frame to red");
        host.input().set_button(RETRO_DEVICE_ID_JOYPAD_A, false);
        check(run_frames(host, 110, "run1"), "run 1 executed 120 frames");
        check(host.save_state(1, error), "save state slot 1");
        check(run_frames(host, 60, "run1b"), "run 1 advanced 60 frames");
        check(host.save_state(2, error), "save state slot 2");

        const std::string s1 = find_file(savedir, "slot1.state");
        const std::string s2 = find_file(savedir, "slot2.state");
        check(!s1.empty() && !s2.empty(), "slot 1 and slot 2 state files exist");
        check(!s1.empty() && !s2.empty() && read_file(s1) != read_file(s2),
              "state changed between slot 1 and slot 2 (mutation is real)");

        check(host.load_state(1, error), "load state slot 1");
        check(host.save_state(3, error), "save state slot 3");
        const std::string s3 = find_file(savedir, "slot3.state");
        check(!s1.empty() && !s3.empty() && read_file(s3) == read_file(s1),
              "loading slot 1 then saving reproduces slot 1 exactly (restoration)");

        check(host.flush_save_ram(error), "flush battery save");
        const std::string srm = find_file(savedir, ".srm");
        const std::string bytes = read_file(srm);
        check(bytes.size() == 32768, "SRAM save is 32 KiB");
        check(bytes.size() >= 5 && bytes.compare(0, 4, "AN3B") == 0, "SRAM save carries the AN3B signature");
        check(bytes.size() >= 5 && static_cast<unsigned char>(bytes[4]) == 0x00,
              "fresh boot counter is 0x00");
        host.shutdown();
    }

    // ---- run 2: a new host must read the persisted save back ----
    {
        an3::NativeCoreHost host; StubVideo video; StubAudio audio; std::string error;
        if (!host.initialize(core, rom, savedir, video, audio, error)) {
            std::fprintf(stderr, "FAIL: initialize (run 2): %s\n", error.c_str());
            return 1;
        }
        check(run_frames(host, 5, "run2 restored visible frames", true), "run 2 emitted presented frames after loading SRAM");
        host.input().set_button(RETRO_DEVICE_ID_JOYPAD_A, true);
        check(run_frames(host, 5, "run2 restored A-button frames", true), "run 2 accepted presented A-button frames after loading SRAM");
        const bool restored_frame_is_green = video.first_pixel_is_dominant(StubVideo::Primary::Green);
        if (!restored_frame_is_green) video.report_first_pixel("restored boot frame");
        check(restored_frame_is_green, "restored SRAM changed the fixture frame to green");
        host.input().set_button(RETRO_DEVICE_ID_JOYPAD_A, false);
        check(run_frames(host, 50, "run2"), "run 2 executed 60 frames");
        check(host.flush_save_ram(error), "flush battery save after reload");
        const std::string bytes = read_file(find_file(savedir, ".srm"));
        check(bytes.size() >= 5 && static_cast<unsigned char>(bytes[4]) == 0x01,
              "reloaded boot counter advanced to 0x01 (SRAM restoration)");
        host.shutdown();
    }

    if (failures) { std::printf("RESULT: FAIL (%d)\n", failures); return 1; }
    std::printf("RESULT: PASS\n");
    return 0;
}
