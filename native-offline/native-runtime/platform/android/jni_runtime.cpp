// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#include "window_surface.h"
#include "aaudio_backend.h"
#include "../../core/auto_save_mode.h"
#include "../../core/libretro_host.h"
#include "../../video/vulkan/software_backend.h"
#include "../../video/vulkan/hardware_backend.h"
#include "../../video/opengl/gles3_backend.h"
#include <android/native_window_jni.h>
#include <jni.h>
#include <atomic>
#include <array>
#include <algorithm>
#include <chrono>
#include <deque>
#include <filesystem>
#include <cmath>
#include <mutex>
#include <sstream>
#include <thread>

namespace {
using namespace an3;
using Clock = std::chrono::steady_clock;
struct Session {
    std::atomic<bool> stop{false};
    std::atomic<bool> suspend{false};
    std::atomic<bool> finished{false};
    std::thread worker;
    std::mutex mutex;
    NativeCoreHost host;
    std::deque<std::pair<std::string,std::string>> commands;
    std::string diagnostics = "Initializing native runtime";
};
std::shared_ptr<Session> session;
std::mutex runtime_serial;
// Accessed only while runtime_serial is held; never trust an old on-disk snapshot.
std::string resumable_save_path;
std::mutex lifecycle;
jweak activity_owner=nullptr;
bool owns(JNIEnv* e,jobject activity) { return activity_owner && e->IsSameObject(activity_owner,activity); }
std::string string(JNIEnv* env,jstring value) {
    if (!value) return {};
    const char* raw=env->GetStringUTFChars(value,nullptr);
    if (!raw) return {};
    std::string result(raw);env->ReleaseStringUTFChars(value,raw);return result;
}
void stop_session() {
    if (!session) return;
    auto retiring=std::move(session);
    retiring->stop=true;
    // Give the worker a bounded chance to leave the render loop before the
    // Android surface is destroyed. Touching a destroyed ANativeWindow from
    // the worker is a known Azahar/Vulkan crash class. If the worker is stuck
    // inside a driver call the join is detached so the UI thread cannot ANR.
    const auto deadline=Clock::now()+std::chrono::milliseconds(1500);
    while(!retiring->finished.load(std::memory_order_acquire) && Clock::now()<deadline) {
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    std::thread([retiring] { if (retiring->worker.joinable()) retiring->worker.join(); }).detach();
}
struct FinishGuard {
    std::atomic<bool>& flag;
    ~FinishGuard() { flag.store(true,std::memory_order_release); }
};
void run(Session& s,ANativeWindow* window,std::string core,std::string rom,std::string saves,std::string requested,std::string layout,std::string system,std::string auto_save_mode,bool resume) {
    FinishGuard finish_guard{s.finished};
    std::lock_guard runtime_lock(runtime_serial);
    // Resume from the in-process snapshot when this process performed the
    // suspend; otherwise fall back to a successful on-disk snapshot left by a
    // previous process (process-death recovery). A failed export deletes the
    // file, so a present `<saves>/.suspend.state` is always a successful
    // snapshot and never a stale half-written one.
    const bool can_resume=resume && (resumable_save_path==saves || std::filesystem::exists(saves+"/.suspend.state"));
    resumable_save_path.clear();
    AndroidWindowSurface surface(window);
    ANativeWindow_release(window);
    std::unique_ptr<NativeVideoBackend> video;
    AAudioBackend audio;
    std::string error, fallback, message;
    auto report=[&](std::string value) { std::lock_guard lock(s.mutex); s.diagnostics=std::move(value); };
    if (s.stop) return;
    const bool is_three_ds = system == "3ds";
    const bool three_ds_vulkan = is_three_ds && requested == "vulkan";
    std::string graphics_api = "Vulkan";
    // Android GPU drivers (for example Adreno 6xx) can return an out-of-spec
    // VK_ERROR_UNKNOWN from Azahar's Vulkan pipeline creation, which the core
    // turns into a fatal uncaught exception. The core's OpenGL ES renderer is
    // the stable path there; an explicit "Vulkan" choice still forces it.
    if (is_three_ds && !three_ds_vulkan) {
        auto gl=std::make_unique<AndroidGles3Backend>();
        if (gl->initialize(surface,error)) { video=std::move(gl); graphics_api="OpenGL"; }
        else { fallback=error; error.clear(); gl->shutdown(); }
    }
    if (!video && (requested=="auto" || requested=="vulkan")) {
        if (is_three_ds) video=std::make_unique<VulkanHardwareBackend>();
        else video=std::make_unique<VulkanSoftwareBackend>();
        if (!video->initialize(surface,error)) { fallback=error;video->shutdown();video.reset(); }
    }
    if (!video && !is_three_ds && (requested=="auto" || requested=="opengl")) {
        video=std::make_unique<AndroidGles3Backend>();
        if (!video->initialize(surface,error)) { video->shutdown();video.reset(); }
    }
    if (!video) {
        if (is_three_ds && error.empty()) error="Native 3DS could not initialize an OpenGL ES or Vulkan renderer.";
        report("Native renderer failed: "+error+"\nVulkan: "+fallback);return;
    }
    if (!s.host.initialize(core,rom,saves,*video,audio,error,layout,graphics_api)) {
        report("Native core failed: "+error);s.host.shutdown();video->shutdown();return;
    }
    if (resume) {
        if (!can_resume) message="Resume state unavailable; game restarted";
        else if (!s.host.import_state(saves+"/.suspend.state",error)) message="Resume state unavailable: "+error;
        else message="Native session resumed";
    }
    uint64_t core_frames=0;
    std::array<int64_t,240> frame_intervals{};
    size_t interval_count=0, interval_cursor=0;
    Clock::time_point previous_frame{};
    auto deadline=Clock::now(), started=deadline, last_report=deadline, last_auto=deadline;
    bool paused=false;
    bool audio_failed=false;
    double speed=1.0;
    AutoSaveSettings auto_save=parse_auto_save_mode(auto_save_mode).value_or(AutoSaveSettings{});
    const auto parse_number=[](const std::string& value,int maximum) {
        if(value.empty() || value.size()>3)return -1;int number=0;
        for(char c:value){if(c<'0' || c>'9')return -1;number=number*10+c-'0';}
        return number<=maximum?number:-1;
    };
    while (!s.stop) {
        std::deque<std::pair<std::string,std::string>> commands;
        { std::lock_guard lock(s.mutex);commands.swap(s.commands); }
        for (const auto& [cmd,value]:commands) {
            bool ok=true;error.clear();
            if (cmd=="pause") { paused=value=="1";s.host.input().clear();deadline=Clock::now(); }
            else if (cmd=="clear-input") s.host.input().clear();
            else if (cmd=="autosave-mode") {
                auto parsed=parse_auto_save_mode(value);
                if (parsed) auto_save=*parsed; else {ok=false;error="Unsupported Auto Save mode";}
            }
            else if (cmd=="speed") {
                if(value=="0.5" || value=="1" || value=="2" || value=="4" || value=="8") {
                    speed=value=="0.5"?.5:double(value[0]-'0');ok=audio.set_emulation_speed(speed);deadline=Clock::now();
                } else {ok=false;error="Unsupported emulation speed";}
            }
            else if(cmd=="volume") { const int v=parse_number(value,100);ok=v>=0 && audio.set_volume(v/100.0f); }
            else if(cmd=="mute") audio.set_muted(value=="1");
            else if(cmd=="latency") {const int v=parse_number(value,128);ok=v>=0 && audio.set_latency_ms(static_cast<unsigned>(v));}
            else if(cmd=="quality") {
                if(value=="low" || value=="medium" || value=="high")ok=audio.set_resampler_quality(value=="low"?AAudioResamplerQuality::Low:value=="high"?AAudioResamplerQuality::High:AAudioResamplerQuality::Medium);
                else ok=false;
            }
            else if(cmd=="option") {
                const auto split=value.find('\t');
                if(split==std::string::npos){ok=false;error="Invalid core option";}
                else ok=s.host.set_core_option(value.substr(0,split),value.substr(split+1),error);
            }
            else if (cmd=="layout") ok=s.host.set_screen_layout(value,error);
            else if (cmd=="save") ok=value=="auto"?s.host.save_auto(error):s.host.save_state((value=="10"?10u:(value.size()==1 && value[0]>='1' && value[0]<='9'?unsigned(value[0]-'0'):0u)),error);
            else if (cmd=="load") ok=value=="auto"?s.host.load_auto(error):s.host.load_state((value=="10"?10u:(value.size()==1 && value[0]>='1' && value[0]<='9'?unsigned(value[0]-'0'):0u)),error);
            else if (cmd=="export") ok=s.host.export_state(value,error);
            else if (cmd=="import") {
                ok=s.host.import_state(value,error);
                std::error_code ignored;std::filesystem::remove(value,ignored);
            }
            else { ok=false;error="Unknown native command"; }
            message=ok?cmd+" completed":cmd+" failed: "+error;
        }
        if (!paused) {
            const auto frame_start=Clock::now();
            if (previous_frame!=Clock::time_point{}) {
                frame_intervals[interval_cursor]=std::chrono::duration_cast<std::chrono::microseconds>(frame_start-previous_frame).count();
                interval_cursor=(interval_cursor+1)%frame_intervals.size();
                interval_count=std::min(interval_count+1,frame_intervals.size());
            }
            previous_frame=frame_start;
            const unsigned present_stride=speed>1?static_cast<unsigned>(speed):1u;
            if (!s.host.run_one(error,core_frames%present_stride==0)) { report("Native runtime stopped: "+error);break; }
            ++core_frames;
            deadline+=std::chrono::nanoseconds(static_cast<int64_t>(std::llround(s.host.frame_duration().count()/speed)));
            // Never add runs to catch up to display FPS or telemetry. Drop old
            // scheduling debt after a slow core so work stays bounded at 1x.
            if (Clock::now()-deadline>s.host.frame_duration()*2) deadline=Clock::now();
        } else { deadline=Clock::now()+std::chrono::milliseconds(20);previous_frame={}; }
        auto now=Clock::now();
        if (auto_save.enabled && now-last_auto>=std::chrono::seconds(auto_save.interval)) {
            message=s.host.save_auto(error)?"Auto Save completed":"Auto Save failed: "+error;
            last_auto=now;
        }
        if (now-last_report>=std::chrono::seconds(1)) {
            auto v=video->metrics();auto a=audio.metrics();
            if (!audio_failed && a.last_error!=AAUDIO_OK) {
                // A device audio disconnect (route change, driver hiccup, or an
                // unsupported rate negotiated by the HAL) must not end the
                // game. Stop the stream once and keep rendering silently so
                // gameplay and input continue.
                audio_failed=true;
                audio.shutdown();
                message="Native audio device stopped (error "+std::to_string(a.last_error)+"); continuing without sound.";
            }
            const double seconds=std::chrono::duration<double>(now-started).count();
            auto sorted_intervals=frame_intervals;
            std::sort(sorted_intervals.begin(),sorted_intervals.begin()+interval_count);
            const auto interval_percentile=[&](size_t percent) {return interval_count?sorted_intervals[(interval_count-1)*percent/100]:0;};
            std::ostringstream text;
            text<<"requested="<<requested<<" effective="<<v.effective<<" core="<<core_frames<<" presented="<<v.frames.presented_frames<<" drops="<<v.frames.dropped_frames
                <<"\nFPS core="<<int(core_frames/seconds)<<" present="<<int(v.frames.presented_frames/seconds)<<" ring="<<v.frames_in_flight
                <<" direct="<<v.frames.direct_software_uploads<<" copied="<<v.frames.copied_software_uploads<<" converted="<<v.frames.converted_software_uploads
                <<"\nupload p95/p99="<<v.frames.upload_p95_us<<"/"<<v.frames.upload_p99_us<<"us present="<<v.frames.present_p95_us<<"/"<<v.frames.present_p99_us
                <<"us speed="<<speed<<" audio="<<a.rendered_frames<<" nonzero="<<a.rendered_nonzero_samples<<" underrun="<<a.underrun_frames
                <<"\nFrame interval p95/p99="<<interval_percentile(95)<<"/"<<interval_percentile(99)<<"us samples="<<interval_count
                <<"\nAudio rate="<<a.core_sample_rate<<"→"<<a.sample_rate<<" volume="<<a.volume<<" mute="<<a.muted<<" latency="<<a.latency_ms<<"ms quality="<<int(a.resampler_quality)
                <<"\n"<<v.device_details<<"\n"<<message;
            if (!fallback.empty()) text<<" Vulkan initialization: "<<fallback;
            report(text.str());last_report=now;
        }
        std::this_thread::sleep_until(deadline);
    }
    if (s.suspend && s.host.export_state(saves+"/.suspend.state",error)) {
        resumable_save_path=saves;
    } else if (s.suspend) {
        // A failed new snapshot must never resume an older session position.
        std::error_code ignored;
        std::filesystem::remove(saves+"/.suspend.state",ignored);
        report("Native resume snapshot failed: "+error);
    }
    // A save-on-exit mode writes one final atomic snapshot as the session
    // stops. Periodic modes already saved on their own timer.
    if (auto_save.on_exit) s.host.save_auto(error);
    s.host.shutdown();audio.shutdown();video->shutdown();
}
}

extern "C" JNIEXPORT void JNICALL Java_space_an3tocom_offline_NativeGameActivity_nativeStart(JNIEnv* e,jobject activity,jobject surface,jstring core,jstring rom,jstring saves,jstring backend,jstring layout,jstring system,jstring autoSaveMode,jboolean resume) {
    std::lock_guard lock(lifecycle);stop_session();
    if (activity_owner) e->DeleteWeakGlobalRef(activity_owner);
    activity_owner=e->NewWeakGlobalRef(activity);
    ANativeWindow* window=ANativeWindow_fromSurface(e,surface);
    session=std::make_shared<Session>();
    if (!window) { session->diagnostics="Native surface unavailable";return; }
    session->worker=std::thread(run,std::ref(*session),window,string(e,core),string(e,rom),string(e,saves),string(e,backend),string(e,layout),string(e,system),string(e,autoSaveMode),bool(resume));
}
extern "C" JNIEXPORT void JNICALL Java_space_an3tocom_offline_NativeGameActivity_nativeStop(JNIEnv* e,jobject activity,jboolean suspend) { std::lock_guard lock(lifecycle);if(owns(e,activity)) {if(session) session->suspend=bool(suspend);stop_session();e->DeleteWeakGlobalRef(activity_owner);activity_owner=nullptr;} }
extern "C" JNIEXPORT void JNICALL Java_space_an3tocom_offline_NativeGameActivity_nativeButton(JNIEnv* e,jobject activity,jint button,jboolean pressed) {
    std::lock_guard lock(lifecycle);if (owns(e,activity) && session && button>=0 && button<16) session->host.input().set_button(button,pressed);
}
extern "C" JNIEXPORT void JNICALL Java_space_an3tocom_offline_NativeGameActivity_nativePointer(JNIEnv* e,jobject activity,jint x,jint y,jboolean pressed) {
    std::lock_guard lock(lifecycle);if (owns(e,activity) && session) session->host.input().set_pointer(static_cast<int16_t>(x),static_cast<int16_t>(y),pressed);
}
extern "C" JNIEXPORT void JNICALL Java_space_an3tocom_offline_NativeGameActivity_nativeAnalog(JNIEnv* e,jobject activity,jint x,jint y) {
    std::lock_guard lock(lifecycle);
    if(owns(e,activity) && session)session->host.input().set_analog(static_cast<int16_t>(std::clamp(x,-32767,32767)),static_cast<int16_t>(std::clamp(y,-32767,32767)));
}
extern "C" JNIEXPORT void JNICALL Java_space_an3tocom_offline_NativeGameActivity_nativeCommand(JNIEnv* e,jobject activity,jstring cmd,jstring value) {
    std::lock_guard lock(lifecycle);if (!owns(e,activity) || !session) return;
    std::lock_guard data_lock(session->mutex);
    if (session->commands.size()<128) session->commands.emplace_back(string(e,cmd),string(e,value));
}
extern "C" JNIEXPORT jstring JNICALL Java_space_an3tocom_offline_NativeGameActivity_nativeDiagnostics(JNIEnv* e,jobject activity) {
    std::lock_guard lock(lifecycle);if (!owns(e,activity) || !session) return e->NewStringUTF("Native runtime stopped");
    std::lock_guard data_lock(session->mutex);return e->NewStringUTF(session->diagnostics.c_str());
}

extern "C" JNIEXPORT jstring JNICALL Java_space_an3tocom_offline_NativeGameActivity_nativeOptions(JNIEnv* e,jobject activity) {
    std::lock_guard lock(lifecycle);
    if(!owns(e,activity) || !session)return e->NewStringUTF("[]");
    return e->NewStringUTF(session->host.core_options_json().c_str());
}

extern "C" JNIEXPORT void JNICALL Java_space_an3tocom_offline_NativeGameActivity_nativeCancelPointer(JNIEnv* e,jobject activity) {
    std::lock_guard lock(lifecycle);if(owns(e,activity) && session)session->host.input().cancel_pointer();
}
