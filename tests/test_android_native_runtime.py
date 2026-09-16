# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Behavioral and source guards for the portable Android native runtime.

The native host can be exercised on the development machine without an Android
device: the test builds a tiny libretro fixture and supplies fake video/audio
backends.  The remaining checks protect platform boundaries that cannot be
meaningfully exercised without Android's NDK or a real Surface.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "native-offline/native-runtime/core/libretro_host.cpp"
VULKAN = ROOT / "native-offline/native-runtime/video/vulkan/vulkan_backend.cpp"
GLES = ROOT / "native-offline/native-runtime/video/opengl/gles3_backend.cpp"
VULKAN_SOFTWARE = ROOT / "native-offline/native-runtime/video/vulkan/software_backend.h"
VULKAN_HARDWARE = ROOT / "native-offline/native-runtime/video/vulkan/hardware_backend.h"
JNI = ROOT / "native-offline/native-runtime/platform/android/jni_runtime.cpp"
ANDROID_SURFACE = ROOT / "native-offline/native-runtime/platform/android/window_surface.h"
GAME_ACTIVITY = ROOT / "native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeGameActivity.kt"
ANDROID_ACTIVITY = ROOT / "native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/MainActivity.kt"
ANDROID_MANIFEST = ROOT / "native-offline/src-tauri/gen/android/app/src/main/AndroidManifest.xml"
ANDROID_BUILD = ROOT / "native-offline/src-tauri/gen/android/app/build.gradle.kts"
ANDROID_BOOTSTRAP = ROOT / "native-offline/web/native-bootstrap.js"
OFFLINE_LIBRARY = ROOT / "static/offline.js"
HARNESS = ROOT / "tests/native/android_host_harness.cpp"
FAKE_SYMBOLS = ROOT / "tests/native/fake_libretro_symbols.cpp"
DIRECT_CORE = ROOT / "native-offline/tests/mock_direct_frame_core.cpp"
VULKAN_HEADERS = ROOT / "native-offline/vendor/moltenvk/macos-arm64/include"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def between(text: str, start: str, end: str) -> str:
    try:
        return text[text.index(start) : text.index(end, text.index(start))]
    except ValueError as exc:
        raise AssertionError(f"native source no longer has expected boundary: {start!r} -> {end!r}") from exc


class AndroidNativeRuntimeTests(unittest.TestCase):
    def test_fake_libretro_host_survives_renderer_drops_and_keeps_state_paths_separate(self):
        """A lost presentation target must not stop or deadlock the core loop."""

        compiler = os.environ.get("CXX") or shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            self.skipTest("no C++ compiler available for the portable host fixture")
        if os.name == "nt":
            self.skipTest("the local fixture build currently targets Unix-like native hosts")

        with tempfile.TemporaryDirectory(prefix="an3-native-host-") as temporary:
            temporary_path = Path(temporary)
            core_library = temporary_path / ("fake.dylib" if os.uname().sysname == "Darwin" else "fake.so")
            harness_binary = temporary_path / "native-host-harness"
            workdir = temporary_path / "work"
            workdir.mkdir()

            # Keep the fixture source in the repository unchanged while making
            # this harness exercise the same early GET_VARIABLE call that
            # melonDS performs during retro_init.  The load-game callback is
            # intentionally silent so a later callback cannot mask a stale
            # value from before core initialization.
            fixture_source = source(DIRECT_CORE)
            self.assertIn("void retro_init() {}", fixture_source)
            fixture_source = fixture_source.replace(
                "void retro_init() {}",
                """void retro_init() {
    RetroVariable variable{"melonds_screen_layout1", nullptr};
    if (environment && environment(kEnvironmentGetVariable, &variable)) {
        remember_layout(variable.value);
    } else {
        remember_layout(nullptr);
    }
}""",
                1,
            )
            fixture_source, load_replacements = re.subn(
                r"bool retro_load_game\(const retro_game_info\*\) \{.*?\n\}",
                "bool retro_load_game(const retro_game_info*) { return true; }",
                fixture_source,
                count=1,
                flags=re.DOTALL,
            )
            self.assertEqual(load_replacements, 1)
            layout_fixture = temporary_path / "layout-at-init-core.cpp"
            layout_fixture.write_text(fixture_source, encoding="utf-8")

            shared_flags = ["-dynamiclib"] if os.uname().sysname == "Darwin" else ["-shared"]
            compile_core = [
                compiler,
                "-std=c++20",
                "-fPIC",
                *shared_flags,
                "-I",
                str(ROOT / "native-offline/native-runtime/core/vendor"),
                str(layout_fixture),
                str(FAKE_SYMBOLS),
                "-o",
                str(core_library),
            ]
            compile_harness = [
                compiler,
                "-std=c++20",
                "-O0",
                "-g",
                "-I",
                str(VULKAN_HEADERS),
                "-I",
                str(ROOT / "native-offline/native-runtime/core"),
                "-I",
                str(ROOT / "native-offline/native-runtime/core/vendor"),
                "-I",
                str(ROOT / "native-offline/src-tauri/src"),
                str(HOST),
                str(HARNESS),
                "-pthread",
                "-o",
                str(harness_binary),
            ]
            if os.uname().sysname != "Darwin":
                compile_harness.append("-ldl")

            for command in (compile_core, compile_harness):
                result = subprocess.run(
                    command,
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    timeout=30,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"native fixture build failed:\n$ {' '.join(command)}\n{result.stdout}{result.stderr}",
                )

            result = subprocess.run(
                [str(harness_binary), str(core_library), str(workdir)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertRegex(result.stdout, r"frames=5\s+begin=5\s+presented=5\s+states=3")

    def test_android_gameplay_uses_a_surface_view_and_native_window(self):
        activity = source(GAME_ACTIVITY)
        surface = source(ANDROID_SURFACE)

        self.assertIn("SurfaceHolder.Callback", activity)
        self.assertIn("SurfaceView(this)", activity)
        self.assertIn("surface.holder.addCallback(this)", activity)
        self.assertIn("private external fun nativeStart(surface: Surface", activity)
        self.assertNotIn("TextureView", activity)
        self.assertNotIn("android.webkit", activity)
        self.assertIn("ANativeWindow_fromSurface", JNI.read_text(encoding="utf-8"))
        self.assertIn("class AndroidWindowSurface final : public NativeWindowSurface", surface)
        self.assertIn("VK_KHR_ANDROID_SURFACE_EXTENSION_NAME", surface)
        self.assertIn("vkCreateAndroidSurfaceKHR", surface)

    def test_auto_renderer_is_vulkan_then_android_gles_and_has_no_web_fallback(self):
        jni = source(JNI)
        activity = source(GAME_ACTIVITY) + source(GAME_ACTIVITY.with_name("NativeGameOverlay.kt"))
        selection = between(jni, 'const bool three_ds_vulkan', "if (!s.host.initialize")

        # Android 3DS defaults to the core's OpenGL ES renderer because some
        # Adreno Vulkan drivers return VK_ERROR_UNKNOWN from the core's pipeline
        # creation and the core aborts. An explicit Vulkan choice still forces
        # Vulkan, and other systems keep the Vulkan-first path with a GLES
        # fallback.
        self.assertIn('const bool three_ds_vulkan = is_three_ds && requested == "vulkan";', selection)
        self.assertIn('graphics_api="OpenGL"', selection)
        self.assertIn("std::make_unique<AndroidGles3Backend>()", selection)
        self.assertIn("std::make_unique<VulkanHardwareBackend>()", selection)
        self.assertIn("std::make_unique<VulkanSoftwareBackend>()", selection)
        self.assertIn('requested=="auto" || requested=="opengl"', selection)
        self.assertIn('requested=="auto" || requested=="vulkan"', selection)
        self.assertIn("s.host.initialize(core,rom,saves,*video,audio,error,layout,graphics_api)", jni)
        self.assertIn('report("Native renderer failed: "+error', selection)
        for forbidden in ("WebGPU", "WebGL", "EmulatorJS", "OffscreenCanvas", "ImageBitmap", "HTML canvas"):
            self.assertNotIn(forbidden, selection)

        # The Android setting vocabulary must stay distinct from the browser's
        # WebGPU/WebGL2 choices.
        for value in ("Auto", "Vulkan", "OpenGL ES", '"auto", "vulkan", "opengl"'):
            self.assertIn(value, activity)
        self.assertNotIn("WebGPU", activity)
        self.assertNotIn("WebGL2", activity)
        self.assertIn('status_.requested="vulkan"', source(VULKAN_SOFTWARE))
        self.assertIn('status_.effective="vulkan"', source(VULKAN_SOFTWARE))
        self.assertIn("VulkanHardwareBackend", source(VULKAN_HARDWARE))
        self.assertIn("core-provided images directly", source(VULKAN_HARDWARE))
        self.assertIn('impl_->status.effective = "opengl-es-3"', source(GLES))

    def test_android_menu_retains_dmg_controls_tabs_and_explicit_save_settings(self):
        overlay = source(GAME_ACTIVITY.with_name("NativeGameOverlay.kt"))
        shared = source(GAME_ACTIVITY.with_name("NativePlayerUi.kt"))
        for constant in ("MENU_LABEL", "PAD_LABEL", "LAYOUT_LABEL", "SAVE_LABEL", "CURSOR_LOCK_LABEL"):
            self.assertIn(f"NativePlayerUi.{constant}", overlay)
        self.assertIn("NativePlayerUi.speedLabels[0]", overlay)
        self.assertIn("for(tab in NativePlayerUi.tabs)", overlay)
        # The user-facing labels live in the one shared player model and are
        # generated into NativePlayerUi.kt; the overlay must consume them
        # instead of hard-coded duplicates.
        for label in ("Menu", "Pad", "0.5x", "1x", "x2", "Lock cursor", "General", "Graphics", "Audio", "Keyboard", "Controller", "Emulation", "Save States", "Diagnostics", "About"):
            self.assertIn('"'+label+'"', shared)
        self.assertIn('"Save Settings"', overlay)
        self.assertIn("for(slot in 1..10)", overlay)
        self.assertIn('"autosave-mode"', overlay)
        self.assertIn("NativePlayerUi.autoSaveTitles", overlay)
        self.assertIn("NativePlayerUi.autoSaveTokens", overlay)
        self.assertNotIn("autosave-interval", overlay)
        self.assertIn("val draft = mutableMapOf", overlay)
        self.assertIn("val flags = mutableMapOf", overlay)
        self.assertIn('button("Save Settings")', overlay)
        self.assertIn('send("option",', overlay)
        self.assertIn('private val previewLayout: (String) -> Unit', overlay)
        self.assertIn('Screen layout · applies immediately', overlay)
        self.assertIn('previewLayout(draft.getValue("nds-layout"))', overlay)
        self.assertIn('previewLayout(NativeLayoutModel.normalize(activity, system,', overlay)
        self.assertNotIn("WebView", overlay)

    def test_android_overlay_keeps_display_only_and_menu_precedence(self):
        overlay = source(GAME_ACTIVITY.with_name("NativeGameOverlay.kt"))
        activity = source(GAME_ACTIVITY)
        # The FPS badge is display-only and must not intercept taps.
        self.assertIn("fps.isClickable = false", overlay)
        self.assertIn("fps.isFocusable = false", overlay)
        self.assertIn("fps.setOnTouchListener { _, _ -> false }", overlay)
        # The toolbar Save control exposes all ten quick slots.
        self.assertIn("private fun chooseQuickSlot(", overlay)
        self.assertIn('(1..10).map { "Slot $it" }', overlay)
        # An open menu owns pointer input; the NDS/3DS touchscreen must not react.
        self.assertIn("fun isMenuOpen()", overlay)
        self.assertIn("if (overlay.isMenuOpen()) { releasePointer(); return true }", activity)

    def test_android_advertises_the_bundled_native_3ds_launch_path(self):
        bootstrap = source(ANDROID_BOOTSTRAP)
        activity = source(ANDROID_ACTIVITY)
        manifest = source(ANDROID_MANIFEST)
        library = source(OFFLINE_LIBRARY)

        self.assertIn('? ["gba", "nds", "3ds"] :', bootstrap)
        self.assertNotIn("AN3AndroidLaunchThreeDs", bootstrap)
        self.assertNotIn("launchThreeDs", activity)
        self.assertIn('system !in listOf("gba", "nds", "3ds")', activity)
        self.assertIn('"libazahar_libretro_android.so"', source(GAME_ACTIVITY))
        self.assertNotIn("org.azahar_emu.azahar", manifest)
        self.assertNotIn("An3RomContentProvider", manifest)
        self.assertFalse((ANDROID_ACTIVITY.parent / "An3RomContentProvider.kt").exists())
        self.assertIn('const androidThreeDsUnavailable = system =>', library)
        self.assertIn('nativeIntegratedSystem(game.system)', library)
        # No browser-only lock exists; the Android capability declaration is the
        # only gate and the play control stays bound to it.
        self.assertNotIn('browserThreeDsUnavailable', library)
        self.assertIn('play.disabled=game.system==="html5"||androidThreeDsUnavailable(game.system);', library)

    def test_android_library_capability_guard_behavior(self):
        subprocess.run(
            ["node", "--test", str(ROOT / "tests/native_android_library.test.js")],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )

    def test_android_native_rom_storage_preserves_supported_container_suffixes(self):
        activity = source(ANDROID_ACTIVITY)
        gameplay = source(GAME_ACTIVITY)

        self.assertIn('private fun nativeRomFile(romId: String, system: String, expectedSize: Long = -1L): File?', activity)
        self.assertIn('extensionSystem(safeExtension(file.name)) == system', activity)
        # A stale record id recovers its ROM by exact byte size instead of
        # failing closed with a re-import prompt.
        self.assertIn('file.length() == expectedSize', activity)
        self.assertIn('if (sized.size == 1) return sized.first()', activity)
        self.assertIn('storageExtension(selected.entryName, selected.system)', activity)
        self.assertIn('storageExtension(name, system)', activity)
        self.assertIn('putExtra("romFilename", rom.name)', activity)
        self.assertIn('getStringExtra("romFilename")', gameplay)
        self.assertIn('"^$romId\\\\.[a-z0-9]{1,12}$"', gameplay)

    def test_old_android_activity_cannot_stop_or_drive_a_new_native_session(self):
        jni = source(JNI)
        self.assertIn("jweak activity_owner", jni)
        self.assertRegex(jni, r"bool owns\(JNIEnv\* e,jobject activity\)")
        self.assertIn("e->NewWeakGlobalRef(activity)", jni)
        self.assertIn("e->DeleteWeakGlobalRef(activity_owner)", jni)

        stop = between(jni, "Java_space_an3tocom_offline_NativeGameActivity_nativeStop", "Java_space_an3tocom_offline_NativeGameActivity_nativeButton")
        self.assertRegex(stop, r"if\s*\(owns\(e,activity\)\)")
        for method in ("nativeButton", "nativePointer", "nativeCommand", "nativeDiagnostics"):
            body = jni[jni.index(f"Java_space_an3tocom_offline_NativeGameActivity_{method}") :]
            body = body[: body.find("\nextern \"C\"", 1)] if "\nextern \"C\"" in body else body
            self.assertIn("owns(e,activity)", body, method)

    def test_android_native_autosave_uses_the_single_shared_mode(self):
        jni = source(JNI)
        activity = source(GAME_ACTIVITY)
        overlay = source(GAME_ACTIVITY.with_name("NativeGameOverlay.kt"))
        resolver = source(GAME_ACTIVITY.with_name("NativeAutoSave.kt"))
        self.assertIn('#include "../../core/auto_save_mode.h"', jni)
        self.assertIn('cmd=="autosave-mode"', jni)
        self.assertIn("auto_save.enabled", jni)
        self.assertIn("auto_save.on_exit", jni)
        self.assertNotIn('cmd=="autosave-interval"', jni)
        self.assertNotIn("if (autosave) s.host.save_auto(error)", jni)
        self.assertIn("autoSaveMode: String", activity)
        self.assertIn("NativeAutoSave.resolve(preferences)", activity)
        self.assertIn('commandWhenReady("autosave-mode"', activity)
        self.assertIn('choice(NativePlayerUi.AUTO_SAVE_LABEL, "autosave-mode"', overlay)
        # One mode token drives the menu, the persisted setting and the host.
        for token in ('"off"', '"exit"', '"30"', '"10"', '"5"'):
            self.assertIn(token, source(ROOT / "native-offline/shared/generated/player_ui.h"))
        self.assertIn('getBoolean("autosave", true)', resolver)

    def test_failed_suspend_export_removes_stale_resume_snapshot(self):
        jni = source(JNI)
        failed_export = between(
            jni,
            'if (s.suspend && s.host.export_state(saves+"/.suspend.state",error))',
            'if (auto_save.on_exit) s.host.save_auto(error)',
        )

        self.assertIn('} else if (s.suspend) {', failed_export)
        failed_export = failed_export[failed_export.index('} else if (s.suspend) {') :]
        self.assertIn('std::filesystem::remove(saves+"/.suspend.state",ignored);', failed_export)
        self.assertIn('report("Native resume snapshot failed: "+error);', failed_export)

    def test_native_state_picker_catches_cache_temp_creation_failure(self):
        activity = source(GAME_ACTIVITY)

        self.assertRegex(
            activity,
            r'''val file = try \{\s*File\.createTempFile\("native-state-", "\.state", cacheDir\)\s*\}\s*catch \(_:\s*Exception\) \{\s*Toast\.makeText\(this, "Native state storage unavailable", Toast\.LENGTH_LONG\)\.show\(\)\s*return\s*\}''',
        )

    def test_nds_layout_is_available_to_get_variable_before_core_init(self):
        host = source(HOST)
        self.assertLess(host.index("nds_layout_=nds_layout =="), host.index("core_.retro_init();"))
        get_variable = between(host, "case RETRO_ENVIRONMENT_GET_VARIABLE:", "case RETRO_ENVIRONMENT_SET_VARIABLES:")
        self.assertIn('else if (!std::strcmp(variable->key,"melonds_screen_layout1")) variable->value=nds_layout_.c_str();', get_variable)

    def test_portable_vulkan_requires_identity_surface_transform_for_software_blit(self):
        vulkan = source(VULKAN)
        swapchain = between(vulkan, "bool create_swapchain_resources(std::string& error)", "bool recreate_swapchain_if_needed")

        reject = "if (!(capabilities.supportedTransforms & VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR))"
        identity = "info.preTransform = VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR;"
        self.assertIn(reject, swapchain)
        self.assertIn('error = "Native Vulkan surface requires unsupported pre-rotation.";', swapchain)
        self.assertIn(identity, swapchain)
        self.assertLess(swapchain.index(reject), swapchain.index(identity))
        self.assertNotIn("info.preTransform = capabilities.currentTransform;", swapchain)

    def test_native_upload_paths_are_bounded_and_have_no_gpu_readback_or_idle_hot_path(self):
        vulkan = source(VULKAN)
        gles = source(GLES)

        self.assertRegex(vulkan, r"static_assert\(AN3_FRAME_RING_SIZE >= 2 && AN3_FRAME_RING_SIZE <= 3")
        self.assertIn("std::array<PresentationFrame, kFrameRingSize>", vulkan)
        self.assertIn("std::array<SoftwareFrameSlot, kFrameRingSize>", vulkan)
        self.assertIn("staging_mapping", vulkan)
        self.assertIn("flush_mapped_memory_ranges", vulkan)

        upload = between(vulkan, "bool upload_software_frame", "void recover_unconsumed_software_upload")
        present = between(vulkan, "bool present_image", "NativeRendererMetrics renderer_metrics")
        for hot_path in (upload, present):
            for forbidden in ("vkQueueWaitIdle", "vkDeviceWaitIdle", "queue_wait_idle(", "device_wait_idle("):
                self.assertNotIn(forbidden, hot_path)

        self.assertNotIn("glReadPixels", gles)
        self.assertNotIn("glFinish", gles)
        self.assertIn("constexpr size_t kRingSize = 2", gles)
        self.assertIn("std::array<Slot, kRingSize>", gles)
        self.assertIn("glClientWaitSync(slot.fence, 0, 0)", gles)
        self.assertIn("eglSwapBuffers", gles)

    def test_android_frame_interval_telemetry_uses_a_bounded_ring(self):
        jni = source(JNI)
        self.assertIn("std::array<int64_t,240> frame_intervals{}", jni)
        self.assertIn("interval_cursor=(interval_cursor+1)%frame_intervals.size()", jni)
        self.assertIn("interval_count=std::min(interval_count+1,frame_intervals.size())", jni)
        self.assertIn("std::sort(sorted_intervals.begin(),sorted_intervals.begin()+interval_count)", jni)

    def test_android_gles_fallback_rejects_unnegotiated_native_hardware_frames(self):
        gles = source(GLES)
        self.assertIn("hardware-frame: OpenGL ES fallback unsupported without a negotiated libretro GLES context", gles)
        self.assertRegex(gles, re.compile(r"receive_native_gpu_frame\([^)]*\).*?return false", re.DOTALL))

    def test_3ds_vulkan_negotiation_stays_in_the_shared_portable_contract(self):
        host = source(HOST)
        hardware = source(VULKAN_HARDWARE)
        self.assertIn("RETRO_ENVIRONMENT_SET_HW_RENDER", host)
        self.assertIn("RETRO_ENVIRONMENT_SET_HW_RENDER_CONTEXT_NEGOTIATION_INTERFACE", host)
        self.assertIn("RETRO_ENVIRONMENT_GET_HW_RENDER_INTERFACE", host)
        self.assertIn("Azahar did not provide a Vulkan context-reset callback.", host)
        self.assertIn("present_native_gpu_frame(width,height)", host)
        self.assertIn("renderer_.present(width, height)", hardware)
        self.assertNotIn("glReadPixels", hardware)
        # The hardware implementation must satisfy the common backend
        # interface, but it must never forward a software framebuffer into
        # the GPU path.
        self.assertIn("void present_software(const void*, unsigned, unsigned, std::size_t, int) override {}", hardware)
        self.assertIn("renderer_.present(width, height)", hardware)

    def test_android_layout_and_virtual_controls_share_one_model_and_one_next_action(self):
        overlay = source(GAME_ACTIVITY.with_name("NativeGameOverlay.kt"))
        activity = source(GAME_ACTIVITY)
        schema = (ROOT / "native-offline/shared/native-layout-schema.json").read_text(encoding="utf-8")
        self.assertIn('button(NativePlayerUi.LAYOUT_LABEL)', overlay)
        self.assertIn('button(NativePlayerUi.SAVE_LABEL)', overlay)
        self.assertIn("showLayoutChooser", overlay)
        self.assertIn("showSaveMenu", overlay)
        self.assertIn("NativeLayoutModel.layouts", overlay)
        self.assertIn("NativeLayoutModel.normalize", activity)
        self.assertIn('commandWhenReady("layout", layout)', activity)
        self.assertIn('"Directional control"', overlay)
        self.assertIn('"Analog Joystick"', overlay)
        self.assertIn("releaseVirtualDirections", overlay)
        self.assertIn("virtual-control-position-x-$system", overlay)
        self.assertIn('"3ds"', schema)
        self.assertIn('"left-right"', schema)

    def test_android_archive_import_is_header_aware_bounded_and_never_extracts_unsafe_paths(self):
        activity = source(ANDROID_ACTIVITY)
        self.assertIn("ZipInputStream", activity)
        self.assertIn("isSafeArchivePath", activity)
        self.assertIn("systemFromHeader", activity)
        self.assertIn("AmbiguousArchiveException", activity)
        self.assertIn("Choose a ROM from archive", activity)
        self.assertIn("MAX_NATIVE_ROM_BYTES", activity)
        self.assertIn("SevenZFile", activity)
        self.assertIn("inspectSevenZip", activity)
        self.assertIn("copySevenZipEntry", activity)
        self.assertIn("MAX_ARCHIVE_BYTES", activity)
        self.assertIn('implementation("org.apache.commons:commons-compress:1.21")', source(ANDROID_BUILD))
        self.assertIn('implementation("org.tukaani:xz:1.9")', source(ANDROID_BUILD))
        self.assertLess(
            activity.index('if (header.size >= 0x30) {', activity.index('private fun systemFromHeader')),
            activity.index('if (header.size > 0xb2', activity.index('private fun systemFromHeader')),
        )


if __name__ == "__main__":
    unittest.main()
