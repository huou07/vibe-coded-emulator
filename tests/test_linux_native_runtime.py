# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression contracts for the real portable Linux native package.

The Debian release job compiles and runs these adapters.  These lightweight
checks ensure a later UI-only change cannot silently restore the former
"blocked" browser-package placeholder or put a GPU-frame core on a readback
path.
"""

from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/native-build.yml").read_text(encoding="utf-8")
LINUX = ROOT / "native-offline/native-runtime/platform/linux"
BUILD = (ROOT / "native-offline/scripts/build-linux-staging.sh").read_text(encoding="utf-8")
FLATPAK_INSTALL_VERIFY = (ROOT / "native-offline/scripts/verify-flatpak-install.sh").read_text(encoding="utf-8")
RUNTIME = (LINUX / "linux_runtime.cpp").read_text(encoding="utf-8")
CONTROLS = (LINUX / "linux_controls.cpp").read_text(encoding="utf-8")
LINUX_TAURI = (ROOT / "native-offline/src-tauri/src/linux_runtime.rs").read_text(encoding="utf-8")
WINDOWS_TAURI = (ROOT / "native-offline/src-tauri/src/windows_runtime.rs").read_text(encoding="utf-8")
AZAHAR = (ROOT / "native-offline/src-tauri/src/azahar.rs").read_text(encoding="utf-8")
TAURI_LIB = (ROOT / "native-offline/src-tauri/src/lib.rs").read_text(encoding="utf-8")
NATIVE_BOOTSTRAP = (ROOT / "native-offline/web/native-bootstrap.js").read_text(encoding="utf-8")
NATIVE_APP = (ROOT / "native-offline/web/native-app.js").read_text(encoding="utf-8")
NATIVE_HTML = (ROOT / "native-offline/web/index.html").read_text(encoding="utf-8")
NATIVE_CSS = (ROOT / "native-offline/web/native.css").read_text(encoding="utf-8")
SESSION_H = (ROOT / "native-offline/native-runtime/core/native_core_session.h").read_text(encoding="utf-8")
SESSION_CPP = (ROOT / "native-offline/native-runtime/core/native_core_session.cpp").read_text(encoding="utf-8")
FRAME_QUEUE_CPP = (ROOT / "native-offline/native-runtime/video/software_frame_queue.cpp").read_text(encoding="utf-8")
FRAME_QUEUE_H = (ROOT / "native-offline/native-runtime/video/software_frame_queue.h").read_text(encoding="utf-8")
GL = (LINUX / "sdl_gl_backend.cpp").read_text(encoding="utf-8")
AUDIO = (LINUX / "sdl_audio_backend.cpp").read_text(encoding="utf-8")
AUDIO_HEADER = (LINUX / "sdl_audio_backend.h").read_text(encoding="utf-8")
SURFACE = (LINUX / "sdl_window_surface.h").read_text(encoding="utf-8")
FLATPAK = (ROOT / "native-offline/flatpak/space.an3tocom.offline.yml").read_text(encoding="utf-8")
VULKAN = (ROOT / "native-offline/native-runtime/video/vulkan/vulkan_backend.cpp").read_text(encoding="utf-8")


class LinuxNativeRuntimeTests(unittest.TestCase):
    def test_linux_shell_owns_the_active_session_controls(self):
        self.assertIn('.args(["--control-stdin", "--no-controls"])', LINUX_TAURI)
        self.assertIn('native_session_control,', TAURI_LIB)
        self.assertIn('pub async fn native_session_control', AZAHAR)
        self.assertIn('tauri::async_runtime::spawn_blocking', AZAHAR)
        self.assertIn('AN3_NATIVE_CONTROL_RESULT', LINUX_TAURI)
        self.assertIn('AN3_NATIVE_CONTROL_RESULT', RUNTIME)
        self.assertIn('commands.size() >= 32', RUNTIME)
        self.assertIn('apply_parent_controls();', RUNTIME)
        self.assertIn('"Game window opened. Use the VCE Play page for session controls."', LINUX_TAURI)

        for testid in (
            "native-session", "native-session-return", "native-session-pause",
            "native-session-save", "native-session-load", "native-session-layout",
            "native-session-auto-save", "native-session-volume", "native-session-mute",
        ):
            self.assertIn(f'data-testid="{testid}"', NATIVE_HTML)
        self.assertIn('AN3NativeSessionControls', NATIVE_BOOTSTRAP)
        self.assertIn('an3-native-session-started', NATIVE_BOOTSTRAP)
        self.assertIn('data-native-button', NATIVE_APP)
        self.assertIn('pointercancel', NATIVE_APP)
        self.assertIn('lostpointercapture', NATIVE_APP)
        self.assertIn('window.addEventListener("blur", releaseButtons)', NATIVE_APP)
        self.assertIn('sessionControls.stop()', NATIVE_APP)
        self.assertIn('show("library")', NATIVE_APP)
        self.assertIn('aria-label="Directional controls"', NATIVE_HTML)
        self.assertIn('aria-label="Action buttons"', NATIVE_HTML)
        self.assertIn('.native-session-dpad [data-native-button="4"]{grid-area:1/2}', NATIVE_CSS)
        self.assertIn('.native-session-dpad [data-native-button="6"]{grid-area:2/1}', NATIVE_CSS)

        slots = [f'<option value="{slot}">{slot}</option>' for slot in range(1, 11)]
        self.assertTrue(all(option in NATIVE_HTML for option in slots))

    def test_windows_shell_owns_session_controls_without_a_second_controls_window(self):
        self.assertIn('.args(["--control-stdin", "--no-controls"])', WINDOWS_TAURI)
        self.assertIn('"AN3_NATIVE_CONTROL_RESULT "', WINDOWS_TAURI)
        self.assertIn('pub(super) fn control(action: &str, value: Option<&str>)', WINDOWS_TAURI)
        self.assertIn('pub async fn native_session_control', AZAHAR)
        self.assertIn('target_os = "windows"', AZAHAR[AZAHAR.index("pub async fn native_session_control"):])
        self.assertIn('windows_runtime::control(&action, value.as_deref())', AZAHAR)
        self.assertIn("desktopSessionControlShell", NATIVE_BOOTSTRAP)
        self.assertIn('window.dispatchEvent(new CustomEvent("an3-native-session-started"', NATIVE_BOOTSTRAP)
        self.assertIn('window.AN3NativeSessionControls = {', NATIVE_BOOTSTRAP)
        self.assertIn('data-testid="native-session"', NATIVE_HTML)
        self.assertIn('data-testid="native-session-pause"', NATIVE_HTML)

    def test_linux_parent_control_actions_are_whitelisted_and_acknowledged(self):
        for action in ('"pause"', '"speed"', '"save"', '"load"', '"layout"',
                       '"auto-save"', '"volume"', '"mute"', '"button"',
                       '"clear-input"', '"fullscreen"', '"load-auto"'):
            self.assertIn(action, LINUX_TAURI)
        self.assertIn('"Unsupported or invalid native control action."', LINUX_TAURI)
        self.assertIn('"QUIT"', LINUX_TAURI)
        self.assertIn('"quit"', RUNTIME)
        self.assertIn('parent->enqueue(std::move(command))', RUNTIME)
        self.assertIn('write_parent_control_result(command->id, ok, message)', RUNTIME)

    def test_build_entrypoint_creates_real_deb_and_flatpak(self):
        self.assertNotIn("LINUX_NATIVE_RUNTIME=BLOCKED", BUILD)
        for required in ("libretro_host.cpp", "vulkan_backend.cpp", "linux_runtime.cpp",
                         "linux_controls.cpp", "sdl_audio_backend.cpp", "sdl_gl_backend.cpp",
                         "native_core_session.cpp", "software_frame_queue.cpp",
                         "bundle-linux-runtime.mjs", "npm run tauri -- build --bundles deb",
                         "flatpak-builder", "fetch-linux-gba-nds-libretro.mjs"):
            self.assertIn(required, BUILD)

        self.assertIn('cp -a deb-extract/usr/lib/. /app/lib/', FLATPAK)
        self.assertNotIn('cp -a deb-extract/usr/lib/. /app/lib/an3-offline-native/', FLATPAK)
        self.assertIn('strip: false', FLATPAK)
        self.assertIn('flatpak_companion=', BUILD)
        self.assertIn('flatpak build-export', BUILD)
        self.assertIn('--runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo', BUILD)
        self.assertIn('flatpak_deb_path="$root/releases/$deb_name"', BUILD)
        self.assertIn('The Flatpak source DEB does not match the fresh staged DEB.', BUILD)

    def test_flatpak_bundle_is_clean_installable_without_a_builder_runtime_cache(self):
        self.assertIn('flatpak --user install --noninteractive "$bundle"', FLATPAK_INSTALL_VERIFY)
        self.assertIn('flatpak --user info "$app_id"', FLATPAK_INSTALL_VERIFY)
        self.assertIn('flatpak run --command=an3-native-player "$app_id" --help', FLATPAK_INSTALL_VERIFY)
        self.assertIn('AN3_FLATPAK_SMOKE_ROM', FLATPAK_INSTALL_VERIFY)
        self.assertIn('FLATPAK_RUNTIME_SMOKE=PASS', FLATPAK_INSTALL_VERIFY)

    def test_hosted_flatpak_job_clean_installs_and_runs_generated_gba_fixture(self):
        flatpak_job = WORKFLOW[WORKFLOW.index("  linux-flatpak:"):WORKFLOW.index("  windows-exe:")]
        build_step = flatpak_job.index("Build Flatpak from the same DEB artifact")
        install_step = flatpak_job.index("Clean-install and launch Flatpak gameplay")
        artifact_step = flatpak_job.index("Label and hash artifact")
        self.assertLess(build_step, install_step)
        self.assertLess(install_step, artifact_step)
        self.assertIn("python3 tools/testrom/gba_homebrew_test.py", flatpak_job)
        self.assertIn('"$fixture" AN3FLATPAK', flatpak_job)
        self.assertIn('AN3_FLATPAK_SMOKE_ROM="$fixture"', flatpak_job)
        self.assertIn("bash native-offline/scripts/verify-flatpak-install.sh", flatpak_job)
        self.assertIn("xvfb xauth", flatpak_job)

    def test_linux_surface_audio_and_file_picker_are_native(self):
        self.assertIn("SDL_Vulkan_CreateSurface", SURFACE)
        self.assertIn("SDL_WINDOW_VULKAN", SURFACE)
        self.assertIn("SDL_WINDOW_OPENGL", SURFACE)
        self.assertIn("SDL_OpenAudioDevice", AUDIO)
        self.assertIn("queue_limit_frames_", AUDIO)
        self.assertIn("GTK_FILE_CHOOSER_ACTION_OPEN", RUNTIME)
        self.assertIn("org.freedesktop.portal.Desktop", FLATPAK)
        self.assertNotIn("WebView", RUNTIME)
        self.assertNotIn("OffscreenCanvas", RUNTIME)
        self.assertIn('std::strcmp(path, "libvulkan.so")', VULKAN)
        self.assertIn('dlopen("libvulkan.so.1", RTLD_NOW | RTLD_LOCAL)', VULKAN)

    def test_linux_player_finds_cores_beside_the_packaged_executable(self):
        self.assertIn("SDL_GetBasePath()", RUNTIME)
        self.assertIn('directory / "libretro" / filename', RUNTIME)
        self.assertNotIn("/usr/lib/an3-offline-native/libretro", RUNTIME)

    def test_3ds_is_vulkan_only_and_software_cores_can_select_gl(self):
        self.assertIn('system == "3ds" && options.renderer == "opengl"', RUNTIME)
        self.assertIn('options.renderer == "auto" || options.renderer == "opengl"', RUNTIME)
        self.assertIn("VulkanHardwareBackend", RUNTIME)
        self.assertIn("LinuxSdlGlBackend", RUNTIME)
        self.assertIn("prohibited GPU readback", RUNTIME)
        self.assertIn("hardware-frame: desktop OpenGL fallback cannot consume Vulkan images", GL)

    def test_gl_reuses_resources_and_has_no_finish_or_readback_hot_path(self):
        self.assertIn("std::array<std::vector<uint8_t>, 2> staging", GL)
        self.assertIn("std::array<std::vector<uint8_t>, 2> converted", GL)
        self.assertIn("if (impl_->texture_width != allocation_width || impl_->texture_height != allocation_height)", GL)
        self.assertIn('gl_version_at_least(1, 2) ||', GL)
        self.assertIn('gl_has_extension(extensions, "GL_EXT_texture_edge_clamp")', GL)
        self.assertIn("impl_->supports_edge_clamp ? GL_CLAMP_TO_EDGE : GL_CLAMP", GL)
        self.assertIn("gl_version_at_least(1, 2) ? GL_RGBA : 4", GL)
        self.assertIn("glTexImage2D(GL_TEXTURE_2D, 0, internal_format", GL)
        self.assertIn("GL_MAX_TEXTURE_SIZE", GL)
        self.assertIn('record_present_error("texture preflight", preallocation_error, context_details)', GL)
        self.assertIn("max texture size ", GL)
        self.assertIn("allocation_details", GL)
        self.assertIn("unsigned next_power_of_two(unsigned value)", GL)
        self.assertIn('gl_version_at_least(2, 0) || gl_has_extension(extensions, "GL_ARB_texture_non_power_of_two")', GL)
        self.assertIn("impl_->supports_npot ? width : next_power_of_two(width)", GL)
        self.assertIn("texture_max_u", GL)
        self.assertIn("texture_max_v", GL)
        self.assertIn('gl_version_at_least(1, 2) || gl_has_extension(extensions, "GL_EXT_bgra")', GL)
        self.assertIn('gl_version_at_least(1, 2) || gl_has_extension(extensions, "GL_EXT_packed_pixels")', GL)
        self.assertIn("convert_software_frame_to_rgba", GL)
        self.assertIn("supports_packed_pixels);", GL)
        self.assertIn("glTexSubImage2D", GL)
        self.assertIn('record_present_error("texture allocation", allocation_error, allocation_details)', GL)
        self.assertIn('record_present_error("frame upload", upload_error)', GL)
        self.assertIn('record_present_error("frame draw", draw_error)', GL)
        self.assertIn("current.video.failure_reason", CONTROLS)
        self.assertNotIn("glFinish", GL)
        self.assertNotIn("glReadPixels", GL)
        self.assertLess(GL.index("SDL_GL_SetAttribute"), GL.index("surface->recreate_for_opengl"))

    def test_f1_uses_the_shared_layout_state_and_persists_the_live_choice(self):
        self.assertIn("session.set_screen_layout(value, detail)", RUNTIME)
        self.assertIn("std::ofstream output(layout_file, std::ios::trunc)", RUNTIME)
        self.assertIn("output << options.layout", RUNTIME)
        self.assertIn("next_supported_layout(options.system, options.layout)", RUNTIME)
        self.assertIn("is_supported_layout(options.system, options.layout)", RUNTIME)
        self.assertIn("set_touch(session.input(), options.system, options.layout", RUNTIME)

    def test_linux_toolbar_save_exposes_ten_slots_and_menu_owns_pointer(self):
        self.assertIn("void show_save_menu()", CONTROLS)
        self.assertIn("add_slots(std::string(player_ui::toolbar_quick_save), true)", CONTROLS)
        self.assertIn("slot <= 10", CONTROLS)
        # An open controls panel owns pointer input; a menu tap must not also
        # drive the emulated touchscreen.
        self.assertIn("controls && controls->visible()", RUNTIME)
        self.assertIn("cancel_pointer()", RUNTIME)

    def test_linux_control_panel_reuses_native_state_and_matches_the_desktop_menu_surface(self):
        model = json.loads((ROOT / "native-offline/shared/player-ui.json").read_text())
        self.assertEqual(model["tabs"], ["General", "Graphics", "Audio", "Keyboard", "Controller", "Emulation", "Save States", "Diagnostics", "About"])
        self.assertIn("append_page(player_ui::tabs[i]", CONTROLS)
        for action in ("Toggle fullscreen", "Return to library", "x4", "x8",
                       "Export Save State…", "Import Save State…", "Release held native input"):
            self.assertIn(action, CONTROLS)
        self.assertIn("player_ui::auto_save_label", CONTROLS)
        self.assertIn("player_ui::auto_save_titles", CONTROLS)
        self.assertIn("player_ui::auto_save_tokens", CONTROLS)
        self.assertNotIn("Auto Save (state snapshot)", CONTROLS)
        for speed in ("player_ui::toolbar_speed[0]", "player_ui::toolbar_speed[1]", "player_ui::toolbar_speed[2]"):
            self.assertIn(speed, CONTROLS)
        self.assertIn("session_.core_options()", CONTROLS)
        self.assertIn("session_.set_core_option", CONTROLS)
        self.assertIn("session_.save_state", CONTROLS)
        self.assertIn("session_.load_state", CONTROLS)
        self.assertIn("callbacks_.set_layout", CONTROLS)
        for forbidden in ("WebView", "OffscreenCanvas", "glReadPixels", "glFinish"):
            self.assertNotIn(forbidden, CONTROLS)

    def test_linux_native_autosave_uses_the_single_shared_mode(self):
        self.assertIn('#include "../../core/auto_save_mode.h"', RUNTIME)
        self.assertIn("set_auto_save_mode", RUNTIME)
        self.assertIn("parse_auto_save_mode", RUNTIME)
        self.assertIn("auto_save.enabled", RUNTIME)
        self.assertIn("auto_save.on_exit", RUNTIME)
        self.assertNotIn("set_autosave_interval", RUNTIME)
        self.assertNotIn("autosave_interval", RUNTIME)
        # The shared model is the single source for the offered mode tokens.
        native = (ROOT / "native-offline/shared/generated/player_ui.h").read_text(encoding="utf-8")
        for token in ('"off"', '"exit"', '"30"', '"10"', '"5"'):
            self.assertIn(token, native)

    def test_portable_runtime_has_one_bounded_core_owner(self):
        self.assertIn("class NativeCoreSession", SESSION_H)
        self.assertIn("kMaxPendingCommands = 128", SESSION_H)
        self.assertIn("std::thread worker_", SESSION_H)
        self.assertIn("std::deque<Command> commands_", SESSION_H)
        self.assertIn("host_.run_one(error", SESSION_CPP)
        self.assertIn("host_.shutdown();", SESSION_CPP)
        self.assertIn("commands_.size() >= kMaxPendingCommands", SESSION_CPP)
        self.assertIn("session.start(error, options.frames)", RUNTIME)
        self.assertIn("session.stop();", RUNTIME)
        self.assertIn("LinuxControlPanel>(session, audio", RUNTIME)
        interactive = RUNTIME[RUNTIME.index("NativeCoreSession session(host);"):]
        self.assertNotIn("host.run_one(", interactive)

    def test_presenter_and_audio_metrics_are_safe_with_the_owner_thread(self):
        self.assertIn("mutable std::mutex status_mutex", GL)
        self.assertIn("std::lock_guard<std::mutex> lock(impl_->status_mutex)", GL)
        self.assertIn("mutable std::mutex mutex_", AUDIO_HEADER)
        self.assertIn("std::lock_guard<std::mutex> lock(mutex_)", AUDIO)

    def test_sdl_audio_keeps_conversion_and_queue_work_bounded(self):
        self.assertIn("conversion_buffer_.resize(static_cast<std::size_t>(queue_limit_frames_) * bytes_per_frame)", AUDIO)
        self.assertIn("const int available_bytes = SDL_AudioStreamAvailable(stream_)", AUDIO)
        self.assertIn("if (input_bytes > conversion_buffer_.size())", AUDIO)
        self.assertIn("int remaining_bytes = available_bytes", AUDIO)
        self.assertIn("dropped_frames_ += static_cast<std::size_t>(received) / bytes_per_frame", AUDIO)
        self.assertIn("queue_limit_frames", AUDIO_HEADER)
        self.assertIn("queue_max_frames", AUDIO_HEADER)
        self.assertIn("dropped_frames_ += available_frames - accepted_frames", AUDIO)
        self.assertIn("current.audio.queue_limit_frames", CONTROLS)
        self.assertIn("current.audio.dropped_frames", CONTROLS)

    def test_portable_software_frames_use_a_bounded_fifo_handoff(self):
        self.assertIn("kCapacity = 3", FRAME_QUEUE_H)
        self.assertIn("SlotState::Ready", FRAME_QUEUE_CPP)
        self.assertIn("choose_oldest_ready_slot_locked", FRAME_QUEUE_CPP)
        self.assertIn("finish_frame()", FRAME_QUEUE_CPP)
        self.assertIn("runtime_video = frame_queue.get()", RUNTIME)
        self.assertIn("frame_queue->present_pending()", RUNTIME)
        self.assertIn("software_frame_queue.cpp", BUILD)

    def test_portable_software_frame_queue_fixture(self):
        compiler = shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            self.skipTest("no C++ compiler available for the frame queue fixture")
        with tempfile.TemporaryDirectory(prefix="an3-frame-queue-test-") as temporary:
            binary = Path(temporary) / "frame-queue"
            command = [
                compiler, "-std=c++20", "-Wall", "-Wextra", "-Wpedantic",
                "-I", "~/<REDACTED_PATH>",
                "-I", str(ROOT / "native-offline/native-runtime"),
                "-I", str(ROOT / "native-offline/native-runtime/core"),
                str(ROOT / "native-offline/native-runtime/video/software_frame_queue.cpp"),
                str(ROOT / "tests/native/software_frame_queue_harness.cpp"),
                "-pthread", "-o", str(binary),
            ]
            result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=30)
            if result.returncode != 0 and "vulkan/vulkan.h" in result.stderr:
                self.skipTest("the checkout lacks the external MoltenVK Vulkan header dependency")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], cwd=ROOT, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("SOFTWARE_FRAME_QUEUE=PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
