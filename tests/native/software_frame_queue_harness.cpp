#include "../../native-offline/native-runtime/video/software_frame_queue.h"
#include "../../native-offline/native-runtime/core/vendor/libretro.h"

#include <cstdint>
#include <chrono>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

namespace {

class RecordingPresenter final : public an3::NativeVideoBackend {
  public:
    bool initialize(an3::NativeWindowSurface&, std::string&) override { return true; }
    void resize() override {}
    bool begin_frame() override { return true; }
    bool acquire_software_framebuffer(unsigned, unsigned, int, void*& data,
                                      std::size_t& pitch) override {
        data = nullptr;
        pitch = 0;
        return false;
    }
    void present_software(const void* data, unsigned width, unsigned height,
                          std::size_t pitch, int) override {
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
        if (!data || width != 2 || height != 1 || pitch != 8) return;
        const auto* bytes = static_cast<const std::uint8_t*>(data);
        frames.push_back(bytes[0]);
    }
    void finish_frame() override {}
    bool receive_native_gpu_frame(const void*, std::string& error) override {
        error = "fixture presenter does not accept hardware frames";
        return false;
    }
    void present_native_gpu_frame(unsigned, unsigned) override {}
    an3::NativeVideoStatus metrics() const override {
        an3::NativeVideoStatus result;
        result.requested = "fixture";
        result.effective = "fixture";
        result.frames_in_flight = 2;
        return result;
    }
    void shutdown() override {}

    std::vector<std::uint8_t> frames;
};

int fail(const char* message) {
    std::cerr << message << "\n";
    return 1;
}

} // namespace

int main() {
    RecordingPresenter presenter;
    an3::NativeSoftwareFrameQueue queue(presenter);
    std::string error;
    for (std::uint8_t value = 1; value <= 3; ++value) {
        void* data = nullptr;
        std::size_t pitch = 0;
        if (!queue.acquire_software_framebuffer(2, 1, RETRO_PIXEL_FORMAT_XRGB8888, data, pitch)) {
            return fail("bounded queue rejected a writable slot");
        }
        static_cast<std::uint8_t*>(data)[0] = value;
        queue.present_software(data, 2, 1, pitch, RETRO_PIXEL_FORMAT_XRGB8888);
    }
    if (queue.pending_frames() != 3) return fail("queue depth exceeded or lost a ready frame");
    if (queue.metrics().frames.queue_depth_max != 3) return fail("queue depth maximum was not recorded");
    while (queue.present_pending()) {}
    if (presenter.frames != std::vector<std::uint8_t>({1, 2, 3})) return fail("FIFO presentation order changed");
    const auto present_metrics = queue.metrics().frames;
    if (present_metrics.present_p50_us == 0 || present_metrics.present_p95_us == 0 ||
        present_metrics.present_p99_us == 0) return fail("presentation latency percentiles were not recorded");

    presenter.frames.clear();
    for (std::uint8_t value = 4; value <= 7; ++value) {
        void* data = nullptr;
        std::size_t pitch = 0;
        if (!queue.acquire_software_framebuffer(2, 1, RETRO_PIXEL_FORMAT_XRGB8888, data, pitch)) {
            return fail("bounded queue rejected a replacement slot");
        }
        static_cast<std::uint8_t*>(data)[0] = value;
        queue.present_software(data, 2, 1, pitch, RETRO_PIXEL_FORMAT_XRGB8888);
    }
    const auto metrics = queue.metrics();
    if (metrics.frames.dropped_frames != 1) return fail("full queue did not drop exactly its oldest ready frame");
    while (queue.present_pending()) {}
    if (presenter.frames != std::vector<std::uint8_t>({5, 6, 7})) return fail("full queue did not preserve newest FIFO frames");

    queue.present_software(nullptr, 2, 1, 0, RETRO_PIXEL_FORMAT_XRGB8888);
    if (queue.metrics().frames.duplicated_frames != 1) return fail("duplicate frame opportunity was not recorded");
    if (!queue.present_pending()) return fail("duplicate frame opportunity was not drainable");

    void* incomplete = nullptr;
    std::size_t incomplete_pitch = 0;
    if (!queue.acquire_software_framebuffer(2, 1, RETRO_PIXEL_FORMAT_XRGB8888,
                                            incomplete, incomplete_pitch)) {
        return fail("queue rejected an incomplete-frame slot");
    }
    queue.finish_frame();
    if (queue.pending_frames() != 0) return fail("incomplete direct frame remained queued");

    queue.shutdown();
    if (queue.present_pending()) return fail("shutdown queue still presented a frame");
    std::cout << "SOFTWARE_FRAME_QUEUE=PASS\n";
    return 0;
}
