/*
 * SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Small Android JNI adapter for the stable AN3 Eden C ABI. The upstream Eden
 * core remains the emulator implementation; this file only owns Android
 * Surface -> ANativeWindow lifetime and marshals the existing ABI.
 */
#include <jni.h>
#include <android/native_window_jni.h>

#include <cstdint>
#include <mutex>

#include "an3_eden_bridge.h"

namespace {

std::mutex g_window_mutex;
ANativeWindow* g_window = nullptr;

an3_eden_core* handle(jlong value) {
    return reinterpret_cast<an3_eden_core*>(static_cast<uintptr_t>(value));
}

const char* text(JNIEnv* env, jstring value) {
    return value == nullptr ? nullptr : env->GetStringUTFChars(value, nullptr);
}

void release_text(JNIEnv* env, jstring value, const char* chars) {
    if (value != nullptr && chars != nullptr) {
        env->ReleaseStringUTFChars(value, chars);
    }
}

jint status(an3_eden_core* core, an3_eden_status result) {
    return static_cast<jint>(result);
}

void release_window() {
    std::lock_guard lock(g_window_mutex);
    if (g_window != nullptr) {
        ANativeWindow_release(g_window);
        g_window = nullptr;
    }
}

}  // namespace

extern "C" JNIEXPORT jlong JNICALL
Java_space_an3tocom_offline_NativeGameActivity_nativeEdenCreate(JNIEnv*, jobject) {
    an3_eden_core* core = nullptr;
    if (an3_eden_create(&core) != AN3_EDEN_OK) {
        return 0;
    }
    return static_cast<jlong>(reinterpret_cast<uintptr_t>(core));
}

extern "C" JNIEXPORT jint JNICALL
Java_space_an3tocom_offline_NativeGameActivity_nativeEdenStart(
    JNIEnv* env, jobject, jlong value, jobject surface, jstring keys_dir,
    jstring firmware_dir, jstring content_path) {
    an3_eden_core* core = handle(value);
    if (core == nullptr || surface == nullptr || content_path == nullptr) {
        return static_cast<jint>(AN3_EDEN_ERR_INVALID_ARGUMENT);
    }
    ANativeWindow* native_window = ANativeWindow_fromSurface(env, surface);
    if (native_window == nullptr) {
        return static_cast<jint>(AN3_EDEN_ERR_UNAVAILABLE);
    }
    an3_eden_status result = an3_eden_set_android_surface(core, native_window);
    if (result == AN3_EDEN_OK) {
        release_window();
        {
            std::lock_guard lock(g_window_mutex);
            g_window = native_window;
        }
        const char* keys = text(env, keys_dir);
        const char* firmware = text(env, firmware_dir);
        const char* content = text(env, content_path);
        result = an3_eden_initialize(core, keys, firmware);
        if (result == AN3_EDEN_OK) {
            result = an3_eden_load(core, content);
        }
        if (result == AN3_EDEN_OK) {
            result = an3_eden_start(core);
        }
        release_text(env, keys_dir, keys);
        release_text(env, firmware_dir, firmware);
        release_text(env, content_path, content);
    }
    if (result != AN3_EDEN_OK) {
        (void)an3_eden_shutdown(core);
        release_window();
    }
    return static_cast<jint>(result);
}

extern "C" JNIEXPORT jint JNICALL
Java_space_an3tocom_offline_NativeGameActivity_nativeEdenStop(JNIEnv*, jobject, jlong value) {
    an3_eden_core* core = handle(value);
    if (core == nullptr) {
        return static_cast<jint>(AN3_EDEN_ERR_INVALID_HANDLE);
    }
    const an3_eden_status result = an3_eden_shutdown(core);
    release_window();
    return static_cast<jint>(result);
}

extern "C" JNIEXPORT jint JNICALL
Java_space_an3tocom_offline_NativeGameActivity_nativeEdenPause(JNIEnv*, jobject, jlong value,
                                                               jboolean paused) {
    an3_eden_core* core = handle(value);
    if (core == nullptr) {
        return static_cast<jint>(AN3_EDEN_ERR_INVALID_HANDLE);
    }
    return static_cast<jint>(an3_eden_pause(core, paused == JNI_TRUE ? 1 : 0));
}

extern "C" JNIEXPORT void JNICALL
Java_space_an3tocom_offline_NativeGameActivity_nativeEdenDestroy(JNIEnv*, jobject, jlong value) {
    release_window();
    an3_eden_destroy(handle(value));
}

extern "C" JNIEXPORT jint JNICALL
Java_space_an3tocom_offline_NativeGameActivity_nativeEdenButton(
    JNIEnv*, jobject, jlong value, jint button, jboolean pressed) {
    return status(handle(value), an3_eden_submit_button(handle(value), 0,
                                                       static_cast<uint32_t>(button),
                                                       pressed == JNI_TRUE));
}

extern "C" JNIEXPORT jint JNICALL
Java_space_an3tocom_offline_NativeGameActivity_nativeEdenAnalog(
    JNIEnv*, jobject, jlong value, jint x, jint y) {
    return status(handle(value), an3_eden_submit_analog(
                                  handle(value), 0, AN3_EDEN_STICK_LEFT,
                                  static_cast<int16_t>(x), static_cast<int16_t>(y)));
}

extern "C" JNIEXPORT jint JNICALL
Java_space_an3tocom_offline_NativeGameActivity_nativeEdenRunFrame(
    JNIEnv*, jobject, jlong value) {
    return status(handle(value), an3_eden_run_frame(handle(value), nullptr, nullptr));
}

extern "C" JNIEXPORT jstring JNICALL
Java_space_an3tocom_offline_NativeGameActivity_nativeEdenError(
    JNIEnv* env, jobject, jlong value) {
    const char* error = an3_eden_last_error(handle(value));
    return env->NewStringUTF(error == nullptr ? "" : error);
}
