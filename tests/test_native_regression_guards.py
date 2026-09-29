# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Permanent source contracts for user-observed native regression fixes.

These checks intentionally complement, rather than replace, packaged-app
verification. They make the invariant explicit before shared host changes can
silently reintroduce a prior defect.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOST = (ROOT / "native-offline/src-tauri/src/azahar_host.mm").read_text(encoding="utf-8")
PERSISTENCE = (ROOT / "native-offline/native-runtime/core/save_persistence_worker.h").read_text(encoding="utf-8")
OPTIONS = (ROOT / "native-offline/native-runtime/core/core_options.h").read_text(encoding="utf-8")
VULKAN = (ROOT / "native-offline/src-tauri/src/vulkan_frontend.mm").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "native-offline/web/native-bootstrap.js").read_text(encoding="utf-8")
OFFLINE = (ROOT / "static/offline.js").read_text(encoding="utf-8")
PLAYER = (ROOT / "static/player.js").read_text(encoding="utf-8")
RUNTIME = (ROOT / "static/player-runtime.js").read_text(encoding="utf-8")
NATIVE_WEB_INDEX = (ROOT / "native-offline/web/index.html").read_text(encoding="utf-8")
TAURI = (ROOT / "native-offline/src-tauri/tauri.conf.json").read_text(encoding="utf-8")
MAIN_ACTIVITY = (ROOT / "native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/MainActivity.kt").read_text(encoding="utf-8")
NATIVE_APP = (ROOT / "native-offline/web/native-app.js").read_text(encoding="utf-8")
TAURI_LIB = (ROOT / "native-offline/src-tauri/src/lib.rs").read_text(encoding="utf-8")


class NativeRegressionGuardTests(unittest.TestCase):
    def test_01_quick_slots_remain_exactly_one_through_ten(self):
        self.assertIn("constexpr unsigned kMaxQuickStateSlot = 10", HOST)
        self.assertIn("Array.from({length:10}", OFFLINE)

    def test_02_autosave_never_aliases_a_quick_slot(self):
        self.assertIn('rom_id_ + ".autosave.state"', HOST)
        self.assertIn('rom_id_ + ".slot"', HOST)

    def test_03_nds_relative_direction_has_one_positive_screen_facing_transform(self):
        transform = (ROOT / "native-offline/src-tauri/src/native_input_transform.h").read_text(encoding="utf-8")
        self.assertIn("right/down are", transform)
        self.assertIn("host->move_nds_cursor(event.deltaX, event.deltaY)", HOST)
        self.assertNotIn("move_nds_cursor(event.deltaX, -event.deltaY)", HOST)

    def test_04_nds_input_is_not_driven_by_ui_or_fps_timers(self):
        cursor_path = HOST[HOST.index("void move_nds_cursor"):HOST.index("void set_nds_touch_pressed")]
        self.assertIn("mouse_delta_x_", cursor_path)
        self.assertNotIn("NSTimer", cursor_path)
        self.assertNotIn("0.333", cursor_path)

    def test_05_escape_keeps_menu_first_precedence(self):
        capture = HOST.index("if (_capturing_key_map)")
        menu = HOST.index("if (!_menu_panel.hidden)", capture)
        cursor = HOST.index("if ([self isNds] && _cursor_locked)", menu)
        library = HOST.index("[self returnToLibrary:nil]", cursor)
        self.assertLess(capture, menu)
        self.assertLess(menu, cursor)
        self.assertLess(cursor, library)

    def test_06_new_session_starts_at_one_x(self):
        self.assertIn("speed_ = 1.0;", HOST)
        self.assertIn("set_audio_speed(1.0);", HOST)

    def test_07_speed_controls_remain_bounded_at_eight_x(self):
        self.assertIn("constexpr double kSpeeds[] = {0.5, 1.0, 2.0, 4.0, 8.0}", HOST)
        self.assertIn("std::min(runs, 8u)", HOST)

    def test_08_core_options_are_keyed_by_actual_core_identity(self):
        for core in ('return "mgba"', 'return "melondsds"', 'return "azahar"'):
            self.assertIn(core, HOST)
        self.assertIn("core_options_.core_namespace()", HOST)

    def test_09_core_options_do_not_write_layout_preferences(self):
        self.assertIn("Reading a preference is deliberately side-effect free", HOST)
        implementation = HOST.index("- (void)refreshCoreOptions", HOST.index("@implementation"))
        refresh = HOST[implementation:HOST.index("- (void)changeCoreOption", implementation)]
        self.assertNotIn("persist_native_layout_preference", refresh)

    def test_10_nds_landscape_is_preserved_at_launch(self):
        self.assertIn('"melonds_screen_layout1"', HOST)
        self.assertIn('native_layout_core_value(system_, layout_)', HOST)
        # The layout list is generated from the one schema, not a private copy.
        self.assertIn('shared/generated/native_layouts.h', HOST)
        self.assertIn('native_layouts::nds', HOST)
        self.assertIn('core_options_.set("melonds_screen_layout1"', HOST)
        self.assertIn('launch(romId,game.system,"preserve",game.size)', OFFLINE)

    def test_11_3ds_landscape_is_preserved_at_launch(self):
        self.assertIn('"citra_layout_option"', HOST)
        self.assertIn('variable->value = native_layout_core_value(system_, layout_)', HOST)
        self.assertIn('core_options_.set("citra_layout_option", native_layout_core_value(system_, layout_))', HOST)
        self.assertIn('launch(romId,title,"preserve",game.size)', OFFLINE)

    def test_12_normal_speed_audio_keeps_a_valid_resampled_output_path(self):
        self.assertIn("initStandardFormatWithSampleRate", HOST)
        self.assertIn("input.floatChannelData", HOST)
        self.assertIn("buffer.floatChannelData", HOST)
        self.assertIn("record_input_pcm(data, frames)", HOST)
        self.assertIn("record_output_pcm(output)", HOST)
        self.assertIn("g_audio_effective_input_rate = g_audio_core_sample_rate * multiplier", HOST)
        self.assertIn("AVAudioConverterInputStatus_NoDataNow", HOST)

    def test_13_gba_core_options_are_not_placed_on_azahar_only_paths(self):
        hardware = HOST[HOST.index("case RETRO_ENVIRONMENT_SET_HW_RENDER:"):HOST.index("case RETRO_ENVIRONMENT_GET_CURRENT_SOFTWARE_FRAMEBUFFER")]
        self.assertIn('if (system_ != "3ds") return false;', hardware)
        self.assertIn('if (system_ == "3ds")', HOST)

    def test_14_volume_slider_has_bilateral_containment_constraints(self):
        self.assertIn("volume_row.leadingAnchor constraintEqualToAnchor:stack.leadingAnchor", HOST)
        self.assertIn("volume_row.trailingAnchor constraintEqualToAnchor:stack.trailingAnchor", HOST)
        self.assertIn("minimum_slider_width", HOST)
        self.assertIn("_volume_value", HOST)

    def test_15_vulkan_has_no_wait_idle_in_steady_upload_or_present(self):
        upload = VULKAN[VULKAN.index("bool upload_software_frame"):VULKAN.index("void recover_unconsumed_software_upload")]
        present = VULKAN[VULKAN.index("bool present_image"):VULKAN.index("NativeRendererMetrics renderer_metrics")]
        self.assertNotIn("device_wait_idle", upload)
        self.assertNotIn("device_wait_idle", present)

    def test_16_native_3ds_retains_its_gpu_image_path(self):
        self.assertIn("RETRO_HW_FRAME_BUFFER_VALID", HOST)
        self.assertIn("vulkan_.present(width, height)", HOST)
        self.assertIn("receive_image", VULKAN)

    def test_17_product_identity_is_vibecodedemulator(self):
        self.assertIn('"productName": "VibeCodedEmulator"', TAURI)
        self.assertIn('"identifier": "space.an3tocom.offline"', TAURI)

    def test_18_quick_save_paths_keep_the_existing_names(self):
        self.assertIn('rom_id_ + ".slot" + std::to_string(slot) + ".state"', HOST)

    def test_19_state_file_import_export_remains_independent(self):
        self.assertIn("an3_native_export_state", HOST)
        self.assertIn("an3_native_import_state", HOST)
        self.assertIn("NSSavePanel", HOST)
        self.assertIn("NSOpenPanel", HOST)

    def test_20_web_renderer_worker_contract_remains_present(self):
        self.assertIn("renderer-worker.js", NATIVE_WEB_INDEX)
        self.assertIn("EmulatorJS core", RUNTIME)

    def test_runtime_layout_launcher_never_uses_window_geometry_as_a_preference(self):
        self.assertNotIn('innerWidth>innerHeight?"side_by_side":"default"', OFFLINE)
        self.assertIn('layout || "preserve"', BOOTSTRAP)

    def test_one_x_scheduler_runs_exactly_one_core_frame_per_draw(self):
        draw = HOST[HOST.index("void draw()") : HOST.index("bool validate_state_slot")]
        self.assertIn("unsigned runs = 1;", draw)
        self.assertIn("if (std::abs(speed_ - 1.0) >= 0.001)", draw)
        self.assertIn("run_one_core_frame_locked();", draw)
        core_frame = HOST[HOST.index("void run_one_core_frame_locked()") : HOST.index("void core_thread_loop()")]
        self.assertIn("core_.run();", core_frame)

    def test_single_sample_audio_callbacks_are_not_dropped(self):
        self.assertIn("append_audio_sample(left, right)", HOST)
        self.assertIn("flush_pending_audio_samples();", HOST)
        self.assertIn("g_audio_player.isPlaying", HOST)

    def test_audio_node_restart_clears_stale_queue_after_route_stop(self):
        self.assertIn("if (g_audio_playing && !g_audio_player.isPlaying)", HOST)
        self.assertIn("g_audio_frames_queued.store(0, std::memory_order_relaxed)", HOST)
        self.assertIn("[g_audio_player play]", HOST)

    def test_escape_and_menu_share_non_save_close(self):
        close = HOST.split("- (void)closeMenuDiscardingDraft {", 1)[1].split("\n}", 1)[0]
        toggle = HOST.split("- (void)toggleMenu:(id)sender {", 1)[1].split("\n}", 1)[0]
        key = HOST.split("- (void)keyDown:(NSEvent*)event {", 1)[1].split("\n}", 1)[0]
        self.assertIn("[self discardSettingsDraft]", close)
        self.assertNotIn("saveSettings", close)
        self.assertIn("[self closeMenuDiscardingDraft]", toggle)
        self.assertIn("[self closeMenuDiscardingDraft]", key)
        self.assertNotIn("_menu_panel.hidden = YES", key)
        self.assertLess(key.index("_capturing_key_map"), key.index("closeMenuDiscardingDraft"))
        self.assertLess(key.index("closeMenuDiscardingDraft"), key.index("releaseCursorLock"))
        self.assertLess(key.index("releaseCursorLock"), key.index("returnToLibrary"))

    def test_settings_are_real_tabs_with_an_explicit_save_boundary(self):
        self.assertIn("NSTabView", HOST)
        for tab in ("General", "Graphics", "Audio", "Keyboard", "Controller", "Emulation", "Save States", "Diagnostics", "About"):
            self.assertIn(f'@"{tab}"', HOST)
        self.assertIn('buttonWithTitle:@"Save Settings"', HOST)
        self.assertIn("- (void)saveSettings", HOST)
        self.assertIn("- (void)discardSettingsDraft", HOST)
        self.assertIn("_settings_dirty", HOST)


    def test_fps_overlay_is_pointer_inert(self):
        # The FPS badge sits over the game surface and must never swallow a
        # click meant for the emulator or a control beneath it.
        self.assertIn("@interface AN3InertLabel : NSTextField", HOST)
        self.assertIn("- (NSView*)hitTest:(NSPoint)point { return nil; }", HOST)
        self.assertIn("_fps_overlay = [AN3InertLabel labelWithString", HOST)

    def test_toolbar_save_exposes_all_ten_quick_slots(self):
        self.assertIn("- (NSMenu*)quickSlotSubmenu:", HOST)
        save_menu = HOST[HOST.index("- (void)showSaveMenu:"):HOST.index("- (void)saveAutoNow:")]
        self.assertIn("@selector(saveQuickSlot:)", save_menu)
        self.assertIn("@selector(loadQuickSlot:)", save_menu)
        submenu = HOST[HOST.index("- (NSMenu*)quickSlotSubmenu:"):HOST.index("- (void)showSaveMenu:")]
        self.assertIn("slot <= 10", submenu)

    def test_open_menu_owns_pointer_input(self):
        # Menu-first precedence: mouse input must not also drive NDS/3DS touch.
        for handler in ("- (void)mouseMoved:", "- (void)mouseDown:", "- (void)mouseDragged:", "- (void)mouseUp:"):
            body = HOST[HOST.index(handler):]
            body = body[:body.index("\n}\n", body.index("{"))] if "\n}\n" in body else body
            self.assertIn("_menu_panel.hidden", body, handler)
        toggle = HOST.split("- (void)toggleMenu:(id)sender {", 1)[1].split("\n}", 1)[0]
        self.assertIn("set_nds_touch_pressed(false)", toggle)

    def test_local_gamepad_navigates_appkit_menu_without_leaking_core_input(self):
        draw = HOST[HOST.index("- (void)drawInMTKView:"):HOST.index("- (void)mtkView:")]
        self.assertLess(draw.index("handleLocalMenuButtons"), draw.index("host->draw()"))
        self.assertIn("host->local_input_buttons()", draw)

        menu = HOST.split("- (void)handleLocalMenuButtons:(uint32_t)buttons {", 1)[1].split("\n}", 1)[0]
        self.assertIn("buttons & ~_local_menu_buttons", menu)
        self.assertIn("Button bit positions match the libretro joypad IDs used by local keys", menu)
        for name, bit in (("Up", 4), ("Down", 5), ("Left", 6), ("Right", 7),
                          ("A", 8), ("B", 0), ("Start", 3)):
            self.assertIn(f"kMenu{name} = 1u << {bit}", menu)
        self.assertIn("closeMenuDiscardingDraft", menu)
        self.assertIn("moveMenuFocusBy", menu)
        self.assertIn("adjustMenuFocusBy", menu)
        self.assertIn("activateMenuFocus", menu)
        self.assertIn("_menu_input_suppressed_until_release", menu)

        input_state = HOST.split("int16_t input_state(unsigned device", 1)[1].split("\n    }", 1)[0]
        self.assertIn("menu_navigation_active_.load", input_state)
        self.assertIn("return 0", input_state)
        close = HOST.split("- (void)closeMenuDiscardingDraft {", 1)[1].split("\n}", 1)[0]
        self.assertIn("_local_menu_buttons != 0", close)
        self.assertIn("set_menu_navigation_active(_menu_input_suppressed_until_release)", close)

    def test_android_main_activity_keeps_the_tauri_origin(self):
        # A raw WebView reload bypasses Tauri's dispatcher and leaves the
        # page at about:blank, so every native command is rejected by ACL.
        self.assertIn("super.onWebViewCreate(webView)", MAIN_ACTIVITY)
        self.assertNotIn("webView.loadUrl", MAIN_ACTIVITY)
        self.assertIn("WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)", MAIN_ACTIVITY)

    def test_local_rom_catalog_survives_without_sync_runtime(self):
        build = (ROOT / "native-offline/src-tauri/build.rs").read_text(encoding="utf-8")
        native_roms = (ROOT / "native-offline/src-tauri/src/native_rom_library.rs").read_text(encoding="utf-8")
        self.assertIn("native_rom_library_manifest", TAURI_LIB)
        self.assertIn('"native_rom_library_manifest"', build)
        self.assertIn("native_rom_library::manifest", TAURI_LIB)
        self.assertIn('invoke("native_rom_library_manifest",{})', OFFLINE)
        self.assertIn("pub fn manifest(app_dir", native_roms)
        self.assertNotIn("sync_peer", TAURI_LIB)
        self.assertNotIn("native_sync_", TAURI_LIB)

    def test_core_save_snapshots_stay_at_the_frame_boundary_without_frame_path_file_io(self):
        start = HOST.index("void draw()")
        draw = HOST[start : HOST.index("\n  private:", start)]
        self.assertIn("std::lock_guard<std::mutex> lock(state_mutex_)", draw)
        core_frame = HOST[HOST.index("void run_one_core_frame_locked()") : HOST.index("void core_thread_loop()")]
        self.assertIn("save_auto_state_locked(save_error, false)", core_frame)
        self.assertIn("flush_save_ram_locked(save_error, false)", core_frame)
        for operation in (
            "write_bytes_atomically",
            "write_and_wait",
            "persistence_writer_.flush",
            "std::ofstream",
            "::open",
            "::fsync",
            "::rename",
        ):
            self.assertNotIn(operation, draw + core_frame)
        stop = HOST[HOST.index("    void stop()") : HOST.index("    bool running() const")]
        self.assertIn("std::lock_guard<std::mutex> lock(state_mutex_)", stop)
        self.assertIn("save_auto_state_locked(save_error, true)", stop)
        self.assertIn("flush_save_ram_locked(save_error, true)", stop)
        self.assertIn("persistence_writer_.flush(persistence_error)", stop)
        self.assertLess(stop.index("save_auto_state_locked(save_error, true)"), stop.index("running_ = false"))
        self.assertLess(stop.index("flush_save_ram_locked(save_error, true)"), stop.index("persistence_writer_.flush(persistence_error)"))
        self.assertLess(stop.index("persistence_writer_.flush(persistence_error)"), stop.index("core_.unload_game()"))

    def test_native_save_file_operations_run_on_the_bounded_persistence_worker(self):
        self.assertIn('#include "save_persistence_worker.h"', HOST)
        self.assertIn("SavePersistenceWorker persistence_writer_", HOST)
        self.assertIn("persistence_writer_.write_async(path", HOST)
        self.assertIn("persistence_writer_.write_and_wait(path", HOST)
        self.assertIn("std::thread worker_", PERSISTENCE)
        self.assertIn("constexpr size_t kMaxPendingPaths = 16", PERSISTENCE)
        self.assertIn("static bool write_bytes_atomically", PERSISTENCE)
        self.assertIn("write_bytes_atomically(job.path", PERSISTENCE)
        writer_start = PERSISTENCE.index("static bool write_bytes_atomically")
        writer_end = PERSISTENCE.index("    void complete(", writer_start)
        writer = PERSISTENCE[writer_start:writer_end]
        self.assertIn('path.string() + ".tmp"', writer)
        for operation in ("create_directories", "std::ofstream", "output.flush()", "::open", "::fsync", "::rename"):
            self.assertIn(operation, writer)
        posix_start = writer.index("#else", writer.index("#if defined(_WIN32)"))
        posix_end = writer.index("#endif", posix_start)
        posix = writer[posix_start:posix_end]
        self.assertLess(writer.index("output.flush()"), writer.index("::fsync"))
        self.assertLess(posix.index("::fsync"), posix.index("::rename"))

    def test_portable_runtime_queues_periodic_saves_and_waits_outside_core_lock(self):
        portable = (ROOT / "native-offline/native-runtime/core/libretro_host.cpp").read_text(encoding="utf-8")
        header = (ROOT / "native-offline/native-runtime/core/libretro_host.h").read_text(encoding="utf-8")
        android = (ROOT / "native-offline/native-runtime/platform/android/jni_runtime.cpp").read_text(encoding="utf-8")
        linux = (ROOT / "native-offline/native-runtime/platform/linux/linux_runtime.cpp").read_text(encoding="utf-8")
        self.assertIn('#include "save_persistence_worker.h"', portable)
        self.assertIn("SavePersistenceWorker persistence_writer_", portable)
        self.assertIn("bool queue_save_auto", header)
        self.assertIn("bool queue_save_ram", header)
        self.assertIn("queue_save_auto", android)
        self.assertIn("queue_save_ram", android)
        self.assertIn("queue_save_auto", linux)
        self.assertIn("take_background_error", portable)
        self.assertNotIn("write_atomic(", portable)
        state = portable[portable.index("bool NativeCoreHost::Impl::state"):portable.index("std::string NativeCoreHost::Impl::save_ram_path")]
        self.assertIn("std::lock_guard<std::mutex> lock(mutex_)", state)
        self.assertIn("persist_snapshot(std::move(snapshot), true", state)
        self.assertLess(state.index("snapshot.ready = true"), state.index("persist_snapshot(std::move(snapshot), true"))
        self.assertIn("// Manual/final durability waits must not hold the core ownership lock.", portable)

if __name__ == "__main__":
    unittest.main()
