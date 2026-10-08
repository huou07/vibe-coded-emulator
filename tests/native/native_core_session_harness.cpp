#include "../../native-offline/native-runtime/core/native_core_session.h"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace {

class RecordingVideo final : public an3::NativeVideoBackend {
  public:
    bool initialize(an3::NativeWindowSurface&, std::string&) override { return true; }
    void resize() override {}
    bool begin_frame() override {
        std::lock_guard<std::mutex> lock(mutex_);
        owner_thread = std::this_thread::get_id();
        ++begin_calls;
        return false;
    }
    bool acquire_software_framebuffer(unsigned, unsigned, int, void*& data,
                                      std::size_t& pitch) override {
        data = nullptr;
        pitch = 0;
        return false;
    }
    void present_software(const void*, unsigned, unsigned, std::size_t, int) override {}
    bool receive_native_gpu_frame(const void*, std::string& error) override {
        error = "fixture does not accept hardware frames";
        return false;
    }
    void present_native_gpu_frame(unsigned, unsigned) override {}
    an3::NativeVideoStatus metrics() const override {
        an3::NativeVideoStatus status;
        status.requested = "fixture";
        status.effective = "fixture";
        return status;
    }
    void shutdown() override {}

    std::thread::id owner_thread{};
    unsigned begin_calls = 0;

  private:
    std::mutex mutex_;
};

class RecordingAudio final : public an3::NativeAudioBackend {
  public:
    bool initialize(double, std::string&) override { return true; }
    std::size_t submit(const std::int16_t*, std::size_t frames) override { return frames; }
    void shutdown() override {}
};

int fail(const std::string& message) {
    std::cerr << message << "\n";
    return 1;
}

std::filesystem::path find_slot(const std::filesystem::path& saves) {
    const auto states = saves / "native-libretro" / "states";
    std::error_code error;
    if (!std::filesystem::is_directory(states, error)) return {};
    for (const auto& entry : std::filesystem::directory_iterator(states, error)) {
        if (entry.is_regular_file() && entry.path().filename().string().find(".slot1.state") != std::string::npos) {
            return entry.path();
        }
    }
    return {};
}

} // namespace

int main(int argc, char** argv) {
    if (argc != 3) return fail("usage: native_core_session_harness <core> <workdir>");
    const std::filesystem::path core = argv[1];
    const std::filesystem::path workdir = argv[2];
    const std::filesystem::path rom = workdir / "fixture.gba";
    const std::filesystem::path saves = workdir / "saves";
    std::filesystem::create_directories(workdir);
    std::ofstream(rom, std::ios::binary) << "AN3 session fixture";

    RecordingVideo video;
    RecordingAudio audio;
    an3::NativeCoreHost host;
    std::string error;
    if (!host.initialize(core.string(), rom.string(), saves.string(), video, audio, error)) {
        return fail("fixture host initialization failed: " + error);
    }

    an3::NativeCoreSession session(host);
    const std::thread::id main_thread = std::this_thread::get_id();
    if (!session.start(error, 6)) return fail("session startup failed: " + error);

    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    while (session.status().core_frames < 6 && std::chrono::steady_clock::now() < deadline) {
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    if (session.status().core_frames < 6) {
        session.stop();
        return fail("bounded session did not reach its frame limit");
    }
    if (!session.running() || !session.paused()) {
        session.stop();
        return fail("bounded session did not remain commandable at its frame limit");
    }
    if (video.owner_thread == main_thread || video.begin_calls < 6) {
        session.stop();
        return fail("core frames were not driven by the dedicated owner thread");
    }

    if (!session.save_state(1, error)) {
        session.stop();
        return fail("owner-thread save command failed: " + error);
    }
    if (find_slot(saves).empty()) {
        session.stop();
        return fail("owner-thread save command did not produce a state file");
    }
    session.set_speed(2.0);
    session.set_paused(false);
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
    session.set_paused(true);
    session.stop();
    if (host.running()) return fail("session stop left the native core running");

    std::cout << "NATIVE_CORE_SESSION=PASS frames=" << video.begin_calls << "\n";
    return 0;
}
