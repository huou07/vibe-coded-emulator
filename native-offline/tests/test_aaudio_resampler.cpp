#include <aaudio/AAudio.h>

#include <cassert>
#include <cmath>
#include <cstdint>
#include <string>

// The backend's render method is private because production code reaches it
// only through AAudio. This focused test drives the same callback directly
// against a deterministic AAudio stub.
#define private public
#include "../native-runtime/platform/android/aaudio_backend.h"
#undef private

struct AAudioStreamStruct {
    int32_t sample_rate = 1000;
    int32_t channels = 2;
    aaudio_format_t format = AAUDIO_FORMAT_PCM_I16;
};

struct AAudioStreamBuilderStruct {
    int32_t requested_rate = 0;
    AAudioStream_dataCallback data_callback = nullptr;
    void* data_user = nullptr;
    AAudioStream_errorCallback error_callback = nullptr;
    void* error_user = nullptr;
};

extern "C" {

const char* AAudio_convertResultToText(aaudio_result_t) { return "stub"; }

aaudio_result_t AAudio_createStreamBuilder(AAudioStreamBuilder** builder) {
    *builder = new AAudioStreamBuilderStruct;
    return AAUDIO_OK;
}

void AAudioStreamBuilder_setDirection(AAudioStreamBuilder*, aaudio_direction_t) {}
void AAudioStreamBuilder_setFormat(AAudioStreamBuilder* builder, aaudio_format_t format) {
    (void)format;
    (void)builder;
}
void AAudioStreamBuilder_setChannelCount(AAudioStreamBuilder*, int32_t) {}
void AAudioStreamBuilder_setSampleRate(AAudioStreamBuilder* builder, int32_t rate) {
    builder->requested_rate = rate;
}
void AAudioStreamBuilder_setSharingMode(AAudioStreamBuilder*, aaudio_sharing_mode_t) {}
void AAudioStreamBuilder_setPerformanceMode(AAudioStreamBuilder*, aaudio_performance_mode_t) {}
void AAudioStreamBuilder_setDataCallback(AAudioStreamBuilder* builder,
                                          AAudioStream_dataCallback callback, void* user) {
    builder->data_callback = callback;
    builder->data_user = user;
}
void AAudioStreamBuilder_setErrorCallback(AAudioStreamBuilder* builder,
                                           AAudioStream_errorCallback callback, void* user) {
    builder->error_callback = callback;
    builder->error_user = user;
}

aaudio_result_t AAudioStreamBuilder_openStream(AAudioStreamBuilder* builder,
                                               AAudioStream** stream) {
    (void)builder;
    *stream = new AAudioStreamStruct;
    return AAUDIO_OK;
}

aaudio_result_t AAudioStreamBuilder_delete(AAudioStreamBuilder* builder) {
    delete builder;
    return AAUDIO_OK;
}

aaudio_result_t AAudioStream_close(AAudioStream* stream) {
    delete stream;
    return AAUDIO_OK;
}
aaudio_result_t AAudioStream_requestStart(AAudioStream*) { return AAUDIO_OK; }
aaudio_result_t AAudioStream_requestStop(AAudioStream*) { return AAUDIO_OK; }
int32_t AAudioStream_getSampleRate(AAudioStream* stream) { return stream->sample_rate; }
int32_t AAudioStream_getChannelCount(AAudioStream* stream) { return stream->channels; }
aaudio_format_t AAudioStream_getFormat(AAudioStream* stream) { return stream->format; }

} // extern "C"

namespace {

struct Output {
    int16_t left[32]{};
    int16_t right[32]{};
};

Output run_quality(an3::AAudioResamplerQuality quality) {
    an3::AAudioBackend backend;
    std::string error;
    assert(backend.initialize(1500.0, error));
    assert(backend.set_latency_ms(128));
    assert(backend.set_resampler_quality(quality));

    const int16_t input[] = {
        0, 0, 1000, 1000, 3000, 3000, 9000, 9000,
        16000, 16000, 12000, 12000, 4000, 4000, -4000, -4000,
    };
    assert(backend.submit(input, 8) == 8);

    Output output;
    int16_t interleaved[64]{};
    backend.render(interleaved, 32);
    for (unsigned frame = 0; frame < 32; ++frame) {
        output.left[frame] = interleaved[frame * 2];
        output.right[frame] = interleaved[frame * 2 + 1];
    }
    backend.shutdown();
    return output;
}

} // namespace

int main() {
    const Output low = run_quality(an3::AAudioResamplerQuality::Low);
    const Output medium = run_quality(an3::AAudioResamplerQuality::Medium);
    const Output high = run_quality(an3::AAudioResamplerQuality::High);

    // The first two source positions are 0 and 1.5. Nearest, linear, and
    // cubic interpolation therefore produce distinct second samples.
    assert(low.left[1] != medium.left[1]);
    assert(medium.left[1] != high.left[1]);

    an3::AAudioBackend backend;
    std::string error;
    assert(backend.initialize(1500.0, error));
    auto metrics = backend.metrics();
    assert(metrics.requested_sample_rate == 1500);
    assert(metrics.sample_rate == 1000);
    assert(std::fabs(metrics.input_frames_per_output_frame - 1.5) < 1e-12);
    assert(metrics.latency_ms == 64);
    assert(metrics.capacity_frames == 64);
    assert(backend.set_emulation_speed(2.0));
    metrics = backend.metrics();
    assert(std::fabs(metrics.input_frames_per_output_frame - 3.0) < 1e-12);
    assert(!backend.set_emulation_speed(3.0));
    assert(backend.set_volume(0.5f));
    assert(!backend.set_volume(1.1f));
    backend.set_muted(true);
    metrics = backend.metrics();
    assert(metrics.muted);
    assert(metrics.volume == 0.5f);
    assert(backend.set_latency_ms(32));
    assert(backend.metrics().capacity_frames == 32);
    assert(!backend.set_latency_ms(33));
    backend.shutdown();
    return 0;
}
