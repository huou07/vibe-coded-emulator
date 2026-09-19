#import <AppKit/AppKit.h>

#include "../src-tauri/src/azahar_host.h"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <unistd.h>

// Hardware smoke/benchmark harness for the in-process macOS renderer. It
// accepts paths as arguments but intentionally reports only system and timing
// data, never local ROM names or paths.
int main(int argc, const char* argv[]) {
    if (argc != 8) {
        std::fprintf(stderr, "usage: native_smoke <system> <core> <moltenvk> <rom> <save-dir> <system-dir> <seconds>\n");
        return 64;
    }
    const double seconds = std::strtod(argv[7], nullptr);
    if (seconds <= 0.0) return 64;

    @autoreleasepool {
        NSApplication* application = [NSApplication sharedApplication];
        [application setActivationPolicy:NSApplicationActivationPolicyAccessory];
        NSWindow* window = [[NSWindow alloc]
            initWithContentRect:NSMakeRect(0.0, 0.0, 960.0, 640.0)
                      styleMask:NSWindowStyleMaskTitled
                        backing:NSBackingStoreBuffered
                          defer:NO];
        [window orderFrontRegardless];

        char details[512]{};
        // Third-party cores can emit local-content diagnostics on stderr.
        // Keep the benchmark output privacy-safe and restore stderr before
        // reporting our own result.
        const int original_stderr = dup(STDERR_FILENO);
        FILE* null_stderr = std::fopen("/dev/null", "w");
        if (null_stderr) dup2(fileno(null_stderr), STDERR_FILENO);
        const int started = an3_native_start((__bridge void*)window.contentView,
                                             argv[2], argv[3], argv[4], argv[1], argv[5], argv[6], argv[1],
                                             "default", details, sizeof(details));
        if (!started) {
            if (null_stderr) {
                std::fflush(stderr);
                dup2(original_stderr, STDERR_FILENO);
                std::fclose(null_stderr);
            }
            if (original_stderr >= 0) close(original_stderr);
            std::fprintf(stderr, "native_start_failed system=%s\n", argv[1]);
            [window close];
            return 1;
        }

        const auto began = std::chrono::steady_clock::now();
        const auto deadline = began + std::chrono::duration<double>(seconds);
        while (std::chrono::steady_clock::now() < deadline) {
            @autoreleasepool {
                NSEvent* event = [application nextEventMatchingMask:NSEventMaskAny
                                                            untilDate:[NSDate dateWithTimeIntervalSinceNow:0.005]
                                                               inMode:NSDefaultRunLoopMode
                                                              dequeue:YES];
                if (event) [application sendEvent:event];
                [application updateWindows];
            }
        }
        const auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - began).count();
        const bool verify_state = std::getenv("AN3_NATIVE_TEST_STATE") != nullptr;
        char state_details[256]{};
        const int state_save = verify_state ? an3_native_save_state(1, state_details, sizeof(state_details)) : -1;
        const int state_load = state_save == 1 ? an3_native_load_state(1, state_details, sizeof(state_details)) : -1;
        an3_native_renderer_metrics metrics{};
        const int have_metrics = an3_native_get_renderer_metrics(&metrics);
        const int running = an3_native_is_running();
        const uint64_t frames = an3_native_presented_frames();
        an3_native_stop();
        if (null_stderr) {
            std::fflush(stderr);
            dup2(original_stderr, STDERR_FILENO);
            std::fclose(null_stderr);
        }
        if (original_stderr >= 0) close(original_stderr);
        [window close];

        std::printf(
            "system=%s frames=%llu elapsed_s=%.3f fps=%.2f running=%d metrics=%d state_save=%d state_load=%d dropped=%llu uploads=%llu direct=%llu copied=%llu converted=%llu emulate_p95_us=%u emulate_p99_us=%u upload_p95_us=%u upload_p99_us=%u present_p95_us=%u present_p99_us=%u audio_queue=%u audio_queue_max=%u audio_underruns=%llu audio_overruns=%llu rss_bytes=%llu cpu_user_us=%llu cpu_system_us=%llu\n",
            argv[1], static_cast<unsigned long long>(frames), elapsed, frames / elapsed, running, have_metrics,
            state_save, state_load,
            static_cast<unsigned long long>(metrics.dropped_frames),
            static_cast<unsigned long long>(metrics.software_uploads),
            static_cast<unsigned long long>(metrics.direct_software_uploads),
            static_cast<unsigned long long>(metrics.copied_software_uploads),
            static_cast<unsigned long long>(metrics.converted_software_uploads), metrics.emulate_p95_us,
            metrics.emulate_p99_us, metrics.upload_p95_us, metrics.upload_p99_us, metrics.present_p95_us,
            metrics.present_p99_us, metrics.audio_queue_depth_frames, metrics.audio_queue_max_frames,
            static_cast<unsigned long long>(metrics.audio_underruns), static_cast<unsigned long long>(metrics.audio_overruns),
            static_cast<unsigned long long>(metrics.resident_memory_bytes), static_cast<unsigned long long>(metrics.cpu_user_time_us),
            static_cast<unsigned long long>(metrics.cpu_system_time_us));
        return running && frames ? 0 : 1;
    }
}
