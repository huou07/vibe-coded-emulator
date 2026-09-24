#include "../../native-offline/native-runtime/core/libretro_host.h"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#if !defined(_WIN32)
#include <dlfcn.h>
#endif

namespace {

class DroppingVideo final : public an3::NativeVideoBackend {
public:
    bool initialize(an3::NativeWindowSurface&, std::string&) override { return true; }
    void resize() override {}
    bool begin_frame() override {
        ++begin_calls;
        // A lost/temporarily unavailable Android surface must not stop the
        // libretro core. The host deliberately continues to run one core
        // frame even when presentation cannot begin.
        return false;
    }
    bool acquire_software_framebuffer(unsigned, unsigned, int, void*& data,
                                      std::size_t& pitch) override {
        ++acquire_calls;
        data = nullptr;
        pitch = 0;
        return false;
    }
    void present_software(const void* data, unsigned width, unsigned height,
                          std::size_t pitch, int format) override {
        ++present_calls;
        last_data = data;
        last_width = width;
        last_height = height;
        last_pitch = pitch;
        last_format = format;
    }
    bool receive_native_gpu_frame(const void*, std::string& error) override {
        error = "test backend does not accept hardware frames";
        return false;
    }
    void present_native_gpu_frame(unsigned, unsigned) override {}
    an3::NativeVideoStatus metrics() const override {
        an3::NativeVideoStatus result;
        result.requested = "test";
        result.effective = "test";
        result.frames.dropped_frames = static_cast<std::uint64_t>(begin_calls);
        return result;
    }
    void shutdown() override {}

    unsigned begin_calls = 0;
    unsigned acquire_calls = 0;
    unsigned present_calls = 0;
    const void* last_data = nullptr;
    unsigned last_width = 0;
    unsigned last_height = 0;
    std::size_t last_pitch = 0;
    int last_format = -1;
};

class RecordingAudio final : public an3::NativeAudioBackend {
public:
    bool initialize(double rate, std::string&) override {
        if (fail_initialize) return false;
        sample_rate = rate;
        initialized = true;
        return true;
    }
    std::size_t submit(const std::int16_t*, std::size_t frames) override {
        submitted_frames += frames;
        return frames;
    }
    void shutdown() override { initialized = false; }

    double sample_rate = 0.0;
    std::size_t submitted_frames = 0;
    bool initialized = false;
    bool fail_initialize = false;
};

struct InputObservation {
    std::uint32_t buttons = 0;
    std::int16_t pointer_x = 0;
    std::int16_t pointer_y = 0;
    std::int16_t pointer_pressed = 0;
};

class CoreInputObserver final {
public:
#if !defined(_WIN32)
    using ObservationCount = unsigned (*)();
    using ObservationRead = int (*)(unsigned, std::uint32_t*, std::int16_t*,
                                    std::int16_t*, std::int16_t*);
    using LayoutRead = const char* (*)();
#endif

    ~CoreInputObserver() {
#if !defined(_WIN32)
        if (handle_) dlclose(handle_);
#endif
    }

    bool open(const std::filesystem::path& core_path, std::string& error) {
#if defined(_WIN32)
        error = "the POSIX test-core observation bridge is unavailable on Windows";
        return false;
#else
        handle_ = dlopen(core_path.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!handle_) {
            const char* detail = dlerror();
            error = detail ? detail : "could not open the test core for input observations";
            return false;
        }
        count_ = reinterpret_cast<ObservationCount>(dlsym(handle_, "an3_test_input_observation_count"));
        read_ = reinterpret_cast<ObservationRead>(dlsym(handle_, "an3_test_read_input_observation"));
        layout_ = reinterpret_cast<LayoutRead>(dlsym(handle_, "an3_test_layout_seen_at_load"));
        if (!count_ || !read_ || !layout_) {
            error = "test core input observation symbols are missing";
            return false;
        }
        return true;
#endif
    }

    std::string layout_seen_at_load() const {
#if defined(_WIN32)
        return {};
#else
        const char* value = layout_();
        return value ? value : "";
#endif
    }

    unsigned count() const {
#if defined(_WIN32)
        return 0;
#else
        return count_();
#endif
    }

    bool read(unsigned index, InputObservation& observation) const {
#if defined(_WIN32)
        (void)index;
        (void)observation;
        return false;
#else
        return read_(index, &observation.buttons, &observation.pointer_x,
                     &observation.pointer_y, &observation.pointer_pressed) != 0;
#endif
    }

private:
#if !defined(_WIN32)
    void* handle_ = nullptr;
    ObservationCount count_ = nullptr;
    ObservationRead read_ = nullptr;
    LayoutRead layout_ = nullptr;
#endif
};

bool has_suffix(const std::string& value, const std::string& suffix) {
    return value.size() >= suffix.size() &&
           value.compare(value.size() - suffix.size(), suffix.size(), suffix) == 0;
}

// The host derives the state filename from the ROM identity, which the harness
// does not need to reproduce: locate the single file with the requested suffix.
std::filesystem::path find_state_file(const std::filesystem::path& saves,
                                      const std::string& suffix) {
    const std::filesystem::path states = saves / "native-libretro" / "states";
    std::error_code ec;
    if (!std::filesystem::is_directory(states, ec)) return {};
    for (const auto& entry : std::filesystem::directory_iterator(states, ec)) {
        if (entry.is_regular_file() && has_suffix(entry.path().filename().string(), suffix)) {
            return entry.path();
        }
    }
    return {};
}

int fail(const std::string& message) {
    std::cerr << message << "\n";
    return 1;
}

} // namespace

int main(int argc, char** argv) {
    if (argc != 3) return fail("usage: native_android_host_harness <core> <workdir>");

    const std::filesystem::path core_path = argv[1];
    const std::filesystem::path workdir = argv[2];
    const std::filesystem::path rom = workdir / "fixture.gba";
    const std::filesystem::path saves = workdir / "saves";
    std::filesystem::create_directories(workdir);
    {
        std::ofstream output(rom, std::ios::binary);
        output << "AN3 native host fixture";
    }

    DroppingVideo video;
    RecordingAudio audio;
    an3::NativeCoreHost host;
    std::string error;

    // A failed load must release the process-wide active-core guard so the
    // next real load cannot block behind stale host state.
    if (host.initialize((workdir / "missing-core.dylib").string(), rom.string(),
                        saves.string(), video, audio, error)) {
        return fail("missing core unexpectedly initialized");
    }
    if (error.empty()) return fail("missing core returned no diagnostic");

    // Failure after retro_init/retro_load_game occurs while the host mutex is
    // held. It must use the locked cleanup path instead of recursively
    // locking itself, and it must leave the active-core guard reusable.
    RecordingAudio failing_audio;
    failing_audio.fail_initialize = true;
    an3::NativeCoreHost failed_host;
    error.clear();
    if (failed_host.initialize(core_path.string(), rom.string(), saves.string(), video,
                               failing_audio, error)) {
        return fail("audio failure unexpectedly initialized");
    }
    failed_host.shutdown();

    CoreInputObserver input_observer;
    error.clear();
    if (!host.initialize(core_path.string(), rom.string(), saves.string(), video,
                         audio, error)) {
        return fail("fixture core failed to initialize with default layout: " + error);
    }
    error.clear();
    if (!input_observer.open(core_path, error)) return fail("layout observation setup failed: " + error);
    if (input_observer.layout_seen_at_load() != "top-bottom") {
        return fail("default NDS layout was not visible as top-bottom during retro_load_game");
    }
    host.shutdown();

    error.clear();
    if (!host.initialize(core_path.string(), rom.string(), saves.string(), video,
                         audio, error, "left-right")) {
        return fail("fixture core failed to initialize with left-right layout: " + error);
    }
    if (input_observer.layout_seen_at_load() != "left-right") {
        return fail("left-right NDS layout was not visible during retro_load_game");
    }

    for (unsigned index = 0; index < 5; ++index) {
        error.clear();
        if (!host.run_one(error)) return fail("core stopped after renderer drop: " + error);
    }
    const auto status = host.status();
    if (!host.running() || status.core_frames != 5 || video.begin_calls != 5 ||
        video.present_calls != 5 || video.acquire_calls != 5) {
        return fail("renderer drops did not preserve core progress");
    }

    // Fast-forward skips selected video callbacks without skipping core work.
    if (!host.run_one(error, false) || host.status().core_frames != 6 ||
        video.begin_calls != 5 || video.present_calls != 5 || video.acquire_calls != 5) {
        return fail("explicit presentation skip changed core progress or uploaded a frame");
    }

    if (input_observer.count() != 6) return fail("fixture did not observe each completed core frame");

    // A press/release completed between two core frames must still be sampled
    // as one pressed frame, then disappear on the next frame.
    const unsigned button_tap_frame = input_observer.count();
    host.input().set_button(3, true); // libretro Start
    host.input().set_button(3, false);
    if (!host.run_one(error, false)) return fail("core stopped while sampling a short button tap: " + error);
    InputObservation observation{};
    if (!input_observer.read(button_tap_frame, observation) ||
        observation.buttons != (1u << 3)) {
        return fail("short Start tap was not visible for exactly one core frame");
    }
    if (!host.run_one(error, false)) return fail("core stopped while releasing a short button tap: " + error);
    if (!input_observer.read(button_tap_frame + 1, observation) ||
        (observation.buttons & (1u << 3)) != 0) {
        return fail("short Start tap remained pressed after its sampled frame");
    }

    // A completed pointer tap keeps its coordinates and pressed state for the
    // sampled frame, then releases on the following frame.
    const unsigned pointer_tap_frame = input_observer.count();
    constexpr std::int16_t kTouchX = 1234;
    constexpr std::int16_t kTouchY = -2345;
    host.input().set_pointer(kTouchX, kTouchY, true);
    host.input().set_pointer(kTouchX, kTouchY, false);
    if (!host.run_one(error, false)) return fail("core stopped while sampling a short pointer tap: " + error);
    if (!input_observer.read(pointer_tap_frame, observation) ||
        observation.pointer_x != kTouchX || observation.pointer_y != kTouchY ||
        observation.pointer_pressed != 1) {
        return fail("short pointer tap did not preserve coordinates for one core frame");
    }
    if (!host.run_one(error, false)) return fail("core stopped while releasing a short pointer tap: " + error);
    if (!input_observer.read(pointer_tap_frame + 1, observation) ||
        observation.pointer_pressed != 0) {
        return fail("short pointer tap remained pressed after its sampled frame");
    }

    // A held pointer drag must preserve the press while forwarding movement
    // on each successive core frame, then release at the final coordinates.
    const unsigned pointer_drag_frame = input_observer.count();
    constexpr std::int16_t kDragStartX = -3000;
    constexpr std::int16_t kDragStartY = 2100;
    constexpr std::int16_t kDragNextX = 2800;
    constexpr std::int16_t kDragNextY = -1700;
    host.input().set_pointer(kDragStartX, kDragStartY, true);
    if (!host.run_one(error, false)) return fail("core stopped while sampling the start of a held pointer drag: " + error);
    if (!input_observer.read(pointer_drag_frame, observation) ||
        observation.pointer_x != kDragStartX || observation.pointer_y != kDragStartY ||
        observation.pointer_pressed != 1) {
        return fail("held pointer drag did not preserve its initial coordinates and press");
    }
    host.input().set_pointer(kDragNextX, kDragNextY, true);
    if (!host.run_one(error, false)) return fail("core stopped while sampling pointer drag movement: " + error);
    if (!input_observer.read(pointer_drag_frame + 1, observation) ||
        observation.pointer_x != kDragNextX || observation.pointer_y != kDragNextY ||
        observation.pointer_pressed != 1) {
        return fail("held pointer drag did not forward changed coordinates while pressed");
    }
    host.input().set_pointer(kDragNextX, kDragNextY, false);
    if (!host.run_one(error, false)) return fail("core stopped while sampling the end of a held pointer drag: " + error);
    if (!input_observer.read(pointer_drag_frame + 2, observation) ||
        observation.pointer_x != kDragNextX || observation.pointer_y != kDragNextY ||
        observation.pointer_pressed != 0) {
        return fail("held pointer drag did not release at its final coordinates");
    }

    // Cancellation before the next core frame must clear both the held and
    // pending pointer press, so an interrupted gesture cannot latch.
    const unsigned cancelled_pointer_frame = input_observer.count();
    host.input().set_pointer(-321, 654, true);
    host.input().cancel_pointer();
    if (!host.run_one(error, false)) return fail("core stopped while sampling a cancelled pointer tap: " + error);
    if (!input_observer.read(cancelled_pointer_frame, observation) ||
        observation.pointer_pressed != 0) {
        return fail("cancelled pointer tap latched into a core frame");
    }

    error.clear();
    if (host.save_state(0, error) || error.find("1 to 10") == std::string::npos) {
        return fail("slot zero was accepted without the range diagnostic");
    }
    error.clear();
    if (host.save_state(11, error) || error.find("1 to 10") == std::string::npos) {
        return fail("slot eleven was accepted without the range diagnostic");
    }

    error.clear();
    if (!host.save_state(1, error) || !error.empty()) return fail("slot 1 save failed: " + error);
    error.clear();
    if (!host.save_state(10, error) || !error.empty()) return fail("slot 10 save failed: " + error);
    error.clear();
    if (!host.save_auto(error) || !error.empty()) return fail("auto save failed: " + error);

    std::vector<std::string> state_files;
    for (const auto& entry : std::filesystem::recursive_directory_iterator(saves)) {
        if (entry.is_regular_file() && entry.path().extension() == ".state") {
            state_files.push_back(entry.path().filename().string());
        }
    }
    if (state_files.size() != 3) return fail("quick slots and auto save did not create three files");
    bool slot_one = false, slot_ten = false, autosave = false;
    for (const auto& name : state_files) {
        slot_one = slot_one || has_suffix(name, ".slot1.state");
        slot_ten = slot_ten || has_suffix(name, ".slot10.state");
        autosave = autosave || has_suffix(name, ".autosave.state");
    }
    if (!slot_one || !slot_ten || !autosave) {
        return fail("auto save aliases a numbered quick-save slot");
    }

    error.clear();
    if (!host.load_state(1, error) || !error.empty()) return fail("slot 1 load failed: " + error);
    error.clear();
    if (!host.load_auto(error) || !error.empty()) return fail("auto save load failed: " + error);

    // A truncated state must be rejected before it reaches the core, and the
    // host must stay running so the user can retry with a valid slot.
    const std::filesystem::path slot_one_path = find_state_file(saves, ".slot1.state");
    if (slot_one_path.empty()) return fail("slot 1 state file was not found for the corruption guard");
    {
        std::ofstream truncated(slot_one_path, std::ios::binary | std::ios::trunc);
        truncated << "x";
    }
    error.clear();
    if (host.load_state(1, error) || error.empty()) {
        return fail("a truncated save state was accepted without a diagnostic");
    }
    if (!host.running()) return fail("a rejected save state stopped the running core");

    // An empty state file is rejected the same way.
    {
        std::ofstream empty(slot_one_path, std::ios::binary | std::ios::trunc);
    }
    error.clear();
    if (host.load_state(1, error) || error.empty()) {
        return fail("an empty save state was accepted without a diagnostic");
    }

    // A failed atomic write must leave the previous valid bytes byte-identical
    // and must not leave a temporary artifact behind. Make the destination a
    // directory so the final rename cannot succeed.
    error.clear();
    if (!host.save_state(2, error) || !error.empty()) return fail("slot 2 save failed: " + error);
    const std::filesystem::path slot_two_path = find_state_file(saves, ".slot2.state");
    if (slot_two_path.empty()) return fail("slot 2 state file was not found for the atomic-write guard");
    std::vector<std::uint8_t> before;
    {
        std::ifstream input(slot_two_path, std::ios::binary);
        before.assign(std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>());
    }
    if (before.empty()) return fail("slot 2 did not produce readable bytes");
    std::error_code remove_ec;
    std::filesystem::remove(slot_two_path, remove_ec);
    std::filesystem::create_directory(slot_two_path, remove_ec);
    error.clear();
    if (host.save_state(2, error) || error.empty()) {
        return fail("a save whose atomic rename cannot complete reported success");
    }
    if (!std::filesystem::is_directory(slot_two_path)) {
        return fail("a failed atomic save replaced the destination");
    }
    if (std::filesystem::exists(slot_two_path.string() + ".tmp")) {
        return fail("a failed atomic save left a temporary artifact behind");
    }
    std::filesystem::remove(slot_two_path, remove_ec);

    // Concurrent save/load requests must serialise on the host mutex without
    // corrupting state or deadlocking. Each thread saves then loads the same
    // slot, so every load has a state to read.
    {
        std::vector<std::thread> workers;
        std::atomic<int> failures{0};
        for (int index = 0; index < 4; ++index) {
            workers.emplace_back([&host, &failures, index]() {
                std::string local_error;
                const unsigned slot = static_cast<unsigned>(1 + (index % 10));
                for (int round = 0; round < 8; ++round) {
                    if (!host.save_state(slot, local_error)) failures.fetch_add(1);
                    local_error.clear();
                    if (!host.load_state(slot, local_error)) failures.fetch_add(1);
                    local_error.clear();
                }
            });
        }
        for (auto& worker : workers) worker.join();
        if (failures.load() != 0) return fail("concurrent save/load requests failed");
        if (!host.running()) return fail("concurrent save/load requests stopped the core");
    }

    host.shutdown();
    if (host.running() || audio.initialized) return fail("host shutdown left runtime resources active");
    std::cout << "frames=" << status.core_frames << " begin=" << video.begin_calls
              << " presented=" << video.present_calls << " states=" << state_files.size()
              << "\n";
    return 0;
}
