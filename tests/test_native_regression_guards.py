# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Permanent source contracts for user-observed native regression fixes.

These checks intentionally complement, rather than replace, packaged-app
verification. They make the invariant explicit before shared host changes can
silently reintroduce a prior defect.
"""

from pathlib import Path
import plistlib
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOST = (ROOT / "native-offline/src-tauri/src/azahar_host.mm").read_text(encoding="utf-8")
PERSISTENCE = (ROOT / "native-offline/src-tauri/src/save_persistence_worker.h").read_text(encoding="utf-8")
OPTIONS = (ROOT / "native-offline/native-runtime/core/core_options.h").read_text(encoding="utf-8")
VULKAN = (ROOT / "native-offline/src-tauri/src/vulkan_frontend.mm").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "native-offline/web/native-bootstrap.js").read_text(encoding="utf-8")
OFFLINE = (ROOT / "static/offline.js").read_text(encoding="utf-8")
PLAYER = (ROOT / "static/player.js").read_text(encoding="utf-8")
RUNTIME = (ROOT / "static/player-runtime.js").read_text(encoding="utf-8")
NATIVE_WEB_INDEX = (ROOT / "native-offline/web/index.html").read_text(encoding="utf-8")
TAURI = (ROOT / "native-offline/src-tauri/tauri.conf.json").read_text(encoding="utf-8")
MAIN_ACTIVITY = (ROOT / "native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/MainActivity.kt").read_text(encoding="utf-8")
CONTROLLER_CLIENT = (ROOT / "native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/ControllerClient.kt").read_text(encoding="utf-8")
CONTROLLER_SEND_QUEUE = (ROOT / "native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/ControllerSendQueue.kt").read_text(encoding="utf-8")
CONTROLLER_UTILITY_QUEUE = (ROOT / "native-offline/src-tauri/src/controller_utility_queue.rs").read_text(encoding="utf-8")
CONTROLLER_SENDER = (ROOT / "native-offline/web/controller-sender.js").read_text(encoding="utf-8")
LAN_PEER = (ROOT / "native-offline/src-tauri/src/lan_peer.rs").read_text(encoding="utf-8")
SYNC_PEER = (ROOT / "native-offline/src-tauri/src/sync_peer.rs").read_text(encoding="utf-8")
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
        self.assertIn("core_.run();", draw)

    def test_single_sample_audio_callbacks_are_not_dropped(self):
        self.assertIn("append_audio_sample(left, right)", HOST)
        self.assertIn("flush_pending_audio_samples();", HOST)
        self.assertIn("g_audio_player.isPlaying", HOST)

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

    def test_phone_controller_navigates_appkit_menu_without_leaking_core_input(self):
        draw = HOST[HOST.index("- (void)drawInMTKView:"):HOST.index("- (void)mtkView:")]
        self.assertLess(draw.index("handleControllerMenuButtons"), draw.index("host->draw()"))
        self.assertIn("host->controller_buttons()", draw)

        menu = HOST.split("- (void)handleControllerMenuButtons:(uint32_t)buttons {", 1)[1].split("\n}", 1)[0]
        self.assertIn("buttons & ~_controller_menu_buttons", menu)
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
        self.assertIn("_controller_menu_buttons != 0", close)
        self.assertIn("set_menu_navigation_active(_menu_input_suppressed_until_release)", close)

    def test_direct_lan_android_navigation_keeps_the_tauri_origin(self):
        # A raw WebView reload bypasses Tauri's dispatcher and leaves the
        # page at about:blank, so every native command is rejected by ACL.
        self.assertIn("super.onWebViewCreate(webView)", MAIN_ACTIVITY)
        self.assertNotIn("webView.loadUrl", MAIN_ACTIVITY)
        self.assertIn("WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)", MAIN_ACTIVITY)

    def test_direct_lan_discovery_uses_one_reusable_bound_socket(self):
        self.assertIn("pub fn discovery_socket", LAN_PEER)
        self.assertIn("socket.set_reuse_address(true)", LAN_PEER)
        self.assertIn("socket.set_reuse_port(true)", LAN_PEER)
        self.assertIn("discovery_socket(DISCOVERY_PORT)", SYNC_PEER)

    def test_native_sync_discovery_runs_off_the_event_loop_thread(self):
        start = TAURI_LIB.index("fn native_sync_discover()")
        command_start = TAURI_LIB.rfind("#[tauri::command]", 0, start)
        command_end = TAURI_LIB.index("\n}\n", start) + 2
        command = TAURI_LIB[command_start:command_end]
        self.assertIn("async fn native_sync_discover()", command)
        self.assertIn("spawn_blocking(sync_peer::discover_peers)", command)
        self.assertNotIn("sync_peer::discover_peers()", command)

    def test_direct_lan_sync_start_does_not_reenter_the_runtime_lock(self):
        existing = SYNC_PEER[SYNC_PEER.index("if let Some(existing) = slot.as_ref()") : SYNC_PEER.index("fs::create_dir_all", SYNC_PEER.index("if let Some(existing) = slot.as_ref()"))]
        self.assertIn("drop(slot);", existing)
        self.assertIn("return Ok(status());", existing)

    def test_direct_lan_reconnect_respects_the_foreground_opt_in(self):
        self.assertIn("if (status.running && window.AN3NativeSync.backgroundEnabled())", NATIVE_APP)

    def test_direct_lan_sync_accepts_blocking_handshake_sockets(self):
        listener = SYNC_PEER[SYNC_PEER.index("fn listener_loop") : SYNC_PEER.index("fn handshake_status")]
        self.assertIn("listener.set_nonblocking(true)", listener)
        self.assertIn("stream.set_nonblocking(false)", listener)
        self.assertLess(listener.index("stream.set_nonblocking(false)"), listener.index("handle_client"))

    def test_sync_loopback_tests_use_an_ephemeral_local_listener(self):
        self.assertIn("start_with_listener(app_dir, mode, SYNC_PORT, true)", SYNC_PEER)
        self.assertIn("start_with_listener(app_dir, mode, 0, false)", SYNC_PEER)
        listener = SYNC_PEER[SYNC_PEER.index("fn listener_loop") : SYNC_PEER.index("fn discover(")]
        self.assertIn("Ipv4Addr::LOCALHOST", listener)
        self.assertIn("runtime.bind_port", SYNC_PEER[SYNC_PEER.index("fn discovery_loop") : SYNC_PEER.index("fn listener_loop")])

    def test_macos_local_network_discovery_declares_privacy_usage(self):
        info = plistlib.loads((ROOT / "native-offline/src-tauri/Info.plist").read_bytes())
        description = info.get("NSLocalNetworkUsageDescription", "")
        self.assertIn("discover", description.lower())
        self.assertIn("save synchronization", description.lower())
        self.assertIn("phone-controller", description.lower())

    def test_core_save_snapshots_stay_at_the_frame_boundary_without_frame_path_file_io(self):
        start = HOST.index("void draw()")
        draw = HOST[start : HOST.index("\n  private:", start)]
        self.assertIn("std::lock_guard<std::mutex> lock(state_mutex_)", draw)
        self.assertIn("save_auto_state_locked(save_error, false)", draw)
        self.assertIn("flush_save_ram_locked(save_error, false)", draw)
        for operation in (
            "write_bytes_atomically",
            "write_and_wait",
            "persistence_writer_.flush",
            "std::ofstream",
            "::open",
            "::fsync",
            "::rename",
        ):
            self.assertNotIn(operation, draw)
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
        self.assertLess(writer.index("output.flush()"), writer.index("::fsync"))
        self.assertLess(writer.index("::fsync"), writer.index("::rename"))

    def test_controller_native_actions_run_on_ui_queue_and_stop_off_thread(self):
        utility = HOST[HOST.index('extern "C" int an3_native_apply_utility_at_slot') : HOST.index('extern "C" int an3_native_apply_utility(')]
        self.assertIn("[NSThread isMainThread]", utility)
        self.assertIn("dispatch_async(dispatch_get_main_queue()", utility)
        self.assertIn("result->completed.wait(lock, [&] { return result->done; })", utility)
        self.assertIn("async fn native_controller_lan_stop()", TAURI_LIB)
        self.assertIn("spawn_blocking(lan_host::stop)", TAURI_LIB)
        self.assertIn("spawn_blocking(controller_host::stop)", TAURI_LIB)
        self.assertIn("spawn_blocking(|| {\n                    lan_host::stop();", TAURI_LIB)

    def test_controller_readiness_and_system_metadata_do_not_read_core_state_under_render_lock(self):
        ready = HOST[HOST.index("bool controller_input_ready()") : HOST.index("bool is_nds()", HOST.index("bool controller_input_ready()"))]
        self.assertIn("input_ready_.load(std::memory_order_acquire)", ready)
        ffi = HOST[HOST.index('extern "C" int an3_native_is_running') : HOST.index('extern "C" uint64_t an3_native_presented_frames')]
        self.assertIn("controller_input_ready()", ffi)
        self.assertNotIn("running()", ffi)
        system = HOST[HOST.index('extern "C" int an3_native_active_system') : HOST.index('extern "C" uint64_t an3_native_presented_frames')]
        self.assertIn("active_system_code()", system)
        self.assertIn('(system_ == "gba" || system_ == "gb" || system_ == "gbc")', HOST)
        stop = HOST[HOST.index("    void stop()") : HOST.index("    bool running() const")]
        self.assertLess(stop.index("input_ready_.store(false"), stop.index("std::lock_guard<std::mutex> lock(state_mutex_)"))
        self.assertLess(stop.index("an3_native_controller_utilities_accepting(0)"), stop.index("std::lock_guard<std::mutex> lock(state_mutex_)"))
        self.assertIn("drain_controller_utilities_locked()", stop)
        draw = HOST[HOST.index("void draw()") : HOST.index("\n  private:", HOST.index("void draw()"))]
        self.assertIn("process_controller_utility_locked()", draw)
        self.assertIn("input_ready_.store(true", HOST)
        set_input_start = HOST.index("void set_input(uint32_t buttons,")
        set_input = HOST[set_input_start : HOST.index("void move_nds_cursor", set_input_start)]
        self.assertIn("buttons_.store(buttons", set_input)
        self.assertIn("touch_pressed_.store(touch_pressed", set_input)
        self.assertNotIn("state_mutex_", set_input)
        self.assertNotIn("lock_guard", set_input)
        input_ffi_start = HOST.index('extern "C" void an3_native_set_input')
        input_ffi = HOST[input_ffi_start:]
        self.assertIn("g_host->set_input(", input_ffi)
        self.assertNotIn("state_mutex_", input_ffi)

    def test_controller_utility_commands_use_a_bounded_ordered_frame_boundary_queue(self):
        self.assertIn("MAX_PENDING_CONTROLLER_UTILITIES: usize = 16", CONTROLLER_UTILITY_QUEUE)
        self.assertIn("VecDeque<ControllerUtility>", CONTROLLER_UTILITY_QUEUE)
        self.assertIn(".wait(queue)", CONTROLLER_UTILITY_QUEUE)
        self.assertIn("available.notify_one()", CONTROLLER_UTILITY_QUEUE)
        self.assertIn("crate::controller_utility_queue::enqueue", (ROOT / "native-offline/src-tauri/src/controller_host.rs").read_text())
        process_start = HOST.index("bool process_controller_utility_locked()")
        process = HOST[process_start : HOST.index("void drain_controller_utilities_locked()", process_start)]
        for action in ("QUICK_SAVE", "QUICK_LOAD", "SPEED_UP", "SPEED_DOWN", "OPEN_MENU"):
            self.assertIn(action, process)
        self.assertEqual(process.count("an3_native_take_controller_utility("), 1)
        self.assertIn("applied = save_state_locked(slot, error, false, completion)", process)
        self.assertIn("completion_deferred = applied", process)
        self.assertIn("persistence_writer_.flush(error) && load_state_locked(slot, error)", process)

    def test_sync_socket_requests_run_off_the_tauri_main_thread(self):
        start = TAURI_LIB.index("async fn native_sync_request(")
        command = TAURI_LIB[start : TAURI_LIB.index("\n}", start)]
        self.assertIn("spawn_blocking(move || sync_peer::request(method, payload))", command)
        self.assertIn(".await", command)

    def test_controller_motion_has_one_writer_and_separate_bounded_event_storage(self):
        self.assertIn("MAX_PENDING_EVENTS = 64", CONTROLLER_SENDER)
        self.assertIn("let motion = null", CONTROLLER_SENDER)
        self.assertIn("requestAnimationFrame", CONTROLLER_SENDER)
        self.assertIn('controllerSender.scheduleMotion(() => snapshot())', NATIVE_APP)
        self.assertIn('update(event, "motion")', NATIVE_APP)
        self.assertIn('sendMotionSnapshot()', NATIVE_APP)
        self.assertIn("MAX_PENDING_CONTROLLER_EVENTS = 64", CONTROLLER_CLIENT)
        self.assertIn("private class ClientWriterSession", CONTROLLER_CLIENT)
        self.assertIn("val outbound = ControllerSendQueue<JSONObject>", CONTROLLER_CLIENT)
        write_loop = CONTROLLER_CLIENT[CONTROLLER_CLIENT.index("private fun clientWriteLoop") : CONTROLLER_CLIENT.index("private fun failClientWriter")]
        self.assertIn("writeFrame(output, seal(writer.key, DIR_PHONE_TO_HOST, writer.sendCounter, next))", write_loop)
        self.assertIn("if (clientWriter === writer && clientSocket === connection) writer.outbound.poll()", write_loop)
        read_loop = CONTROLLER_CLIENT[CONTROLLER_CLIENT.index("private fun clientReadLoop") : CONTROLLER_CLIENT.index("private fun clientWriteLoop")]
        self.assertIn("if (clientWriter !== writer || clientSocket !== connection) false", read_loop)
        send_state = CONTROLLER_CLIENT[CONTROLLER_CLIENT.index("fun sendState(state: JSONObject)") : CONTROLLER_CLIENT.index("fun status()", CONTROLLER_CLIENT.index("fun sendState(state: JSONObject)"))]
        self.assertIn("outbound.offer(queued, motion)", send_state)
        self.assertNotIn("writeFrame(", send_state)
        self.assertIn("if (latestMotion?.let { sequenceOf(it) < newestEventSequence } == true) latestMotion = null", CONTROLLER_SEND_QUEUE)

    def test_android_controller_clears_paired_state_after_remote_disconnect(self):
        self.assertIn("if (!stopping.get()) {\n                    paired = false", CONTROLLER_CLIENT)
        self.assertIn("release()", CONTROLLER_CLIENT)


if __name__ == "__main__":
    unittest.main()
