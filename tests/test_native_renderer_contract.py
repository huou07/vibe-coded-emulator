# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
VULKAN = (ROOT / "native-offline" / "src-tauri" / "src" / "vulkan_frontend.mm").read_text(encoding="utf-8")
HOST = (ROOT / "native-offline" / "src-tauri" / "src" / "azahar_host.mm").read_text(encoding="utf-8")
PERSISTENCE = (ROOT / "native-offline" / "native-runtime" / "core" / "save_persistence_worker.h").read_text(encoding="utf-8")
HEADER = (ROOT / "native-offline" / "src-tauri" / "src" / "vulkan_frontend.h").read_text(encoding="utf-8")
SMOKE = (ROOT / "native-offline" / "tests" / "native_smoke.mm").read_text(encoding="utf-8")
DIRECT_CORE = (ROOT / "native-offline" / "tests" / "mock_direct_frame_core.cpp").read_text(encoding="utf-8")
TAURI = (ROOT / "native-offline" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")


class NativeRendererContractTests(unittest.TestCase):
    def test_software_frames_use_a_bounded_mapped_ring_and_preserve_native_gpu_frames(self):
        self.assertIn("constexpr uint32_t kFrameRingSize = AN3_FRAME_RING_SIZE", VULKAN)
        self.assertIn("AN3_FRAME_RING_SIZE >= 2 && AN3_FRAME_RING_SIZE <= 3", VULKAN)
        self.assertIn("std::array<PresentationFrame, kFrameRingSize> presentation_frames", VULKAN)
        self.assertIn("std::array<SoftwareFrameSlot, kFrameRingSize> software_slots", VULKAN)
        self.assertIn("persistently mapped staging allocation", VULKAN)
        self.assertIn("VkCommandBuffer upload_command", VULKAN)
        self.assertIn("VkSemaphore upload_finished", VULKAN)
        self.assertIn("const VkSemaphore* source_semaphores", VULKAN)
        self.assertIn("pending_semaphore_count", VULKAN)
        self.assertIn("receive_image", VULKAN)
        self.assertIn("VulkanFrontend::present(unsigned width, unsigned height)", VULKAN)

    def test_direct_write_abi_is_experimental_and_falls_back_without_changing_state_bytes(self):
        self.assertIn("RETRO_ENVIRONMENT_GET_CURRENT_SOFTWARE_FRAMEBUFFER = 40 | RETRO_ENVIRONMENT_EXPERIMENTAL", HOST)
        self.assertIn("struct retro_framebuffer", HOST)
        self.assertIn("vulkan_.acquire_software_framebuffer", HOST)
        self.assertIn("bool acquire_software_framebuffer", HEADER)
        self.assertIn("GET_CURRENT_SOFTWARE_FRAMEBUFFER", DIRECT_CORE)
        self.assertIn("direct=", SMOKE)

    def test_native_quick_saves_keep_raw_core_state_bytes_in_ten_stable_slots(self):
        self.assertIn("retro_serialize_size", HOST)
        self.assertIn("retro_serialize", HOST)
        self.assertIn("retro_unserialize", HOST)
        self.assertIn("rom_id_ + \".slot\"", HOST)
        self.assertIn("slot < 1 || slot > kMaxQuickStateSlot", HOST)
        self.assertIn("constexpr unsigned kMaxQuickStateSlot = 10", HOST)
        self.assertIn("an3_native_save_state", HOST)
        self.assertIn("an3_native_load_state", HOST)
        self.assertIn("an3_native_export_state", HOST)
        self.assertIn("an3_native_import_state", HOST)
        self.assertIn("write_and_wait", HOST)
        self.assertIn("write_bytes_atomically", PERSISTENCE)
        self.assertIn("kMaxQuickStateBytes", HOST)
        self.assertIn("retro_serialize", DIRECT_CORE)
        self.assertIn("AN3_NATIVE_TEST_STATE", SMOKE)

    def test_native_keyboard_mapping_is_persisted_without_touching_input_or_state_logic(self):
        self.assertIn("kNativeKeyMappingsDefaultsKey", HOST)
        self.assertIn("set_button_key_mapping", HOST)
        self.assertIn("reset_button_key_mappings", HOST)
        self.assertIn("beginKeyMapping", HOST)
        self.assertIn("Map selected key", HOST)

    def test_native_identity_changes_without_changing_bundle_or_persistence_namespaces(self):
        self.assertIn('"productName": "VibeCodedEmulator"', TAURI)
        self.assertIn('"title": "VibeCodedEmulator"', TAURI)
        self.assertIn('"identifier": "space.an3tocom.offline"', TAURI)
        self.assertIn('kNativeKeyMappingsDefaultsKey', HOST)
        self.assertIn('an3-arcade-save-slots', (ROOT / "static" / "player-runtime.js").read_text(encoding="utf-8"))

    def test_native_settings_state_dialogs_and_fps_overlay_are_real_backend_controls(self):
        for group in ("General", "Graphics", "Audio", "Input", "Emulation", "Save States", "About"):
            self.assertIn(group, HOST)
        self.assertIn('kNativeShowFpsDefaultsKey', HOST)
        self.assertIn('an3_native_presented_frames()', HOST)
        self.assertIn('now - _fps_last_update < 0.333', HOST)
        self.assertIn('NSSavePanel', HOST)
        self.assertIn('NSOpenPanel', HOST)
        self.assertIn('write_and_wait', HOST)
        self.assertIn('write_bytes_atomically', PERSISTENCE)
        self.assertIn('UTType typeWithFilenameExtension', HOST)

    def test_macos_top_controls_respect_the_unobscured_window_content(self):
        layout_start = HOST.index("- (void)layout {")
        layout_end = HOST.index("- (void)closeMenuDiscardingDraft", layout_start)
        layout = HOST[layout_start:layout_end]
        self.assertIn("self.window.contentLayoutRect", layout)
        self.assertIn("convertRect:", layout)
        self.assertIn("height - 44.0 - top_safe_inset", layout)
        self.assertIn("height - 42.0 - top_safe_inset", layout)

    def test_wait_idle_is_outside_per_frame_upload_and_present_hot_paths(self):
        upload = VULKAN[VULKAN.index("bool upload_software_frame"):VULKAN.index("void recover_unconsumed_software_upload")]
        present = VULKAN[VULKAN.index("bool present_image"):VULKAN.index("NativeRendererMetrics renderer_metrics")]
        self.assertNotIn("device_wait_idle", upload)
        self.assertNotIn("device_wait_idle", present)
        self.assertIn("if (slot.image && device_wait_idle)", VULKAN)
        self.assertIn("NativeRendererMetrics", HEADER)
        self.assertIn("an3_native_get_renderer_metrics", HOST)

    def test_unconsumed_binary_upload_semaphore_has_an_error_only_recovery_path(self):
        self.assertIn("recover_unconsumed_software_upload", VULKAN)
        self.assertIn("if (uploaded && !submitted) recover_unconsumed_software_upload(slot)", VULKAN)
        self.assertIn("A binary semaphore signalled by the upload submit must be consumed", VULKAN)

    def test_core_vulkan_failure_drains_pending_one_shot_waits_before_replacement(self):
        receive = VULKAN[VULKAN.index("void receive_image"):VULKAN.index("bool prepare_presentation_frame")]
        discard = VULKAN[VULKAN.index("bool discard_pending_core_frame"):VULKAN.index("static uint8_t expand_5_bit")]
        present = VULKAN[VULKAN.index("void present(unsigned width, unsigned height)"):VULKAN.index("bool discard_pending_core_frame")]
        self.assertLess(receive.index("discard_pending_core_frame"), receive.index("pending_image = *image"))
        self.assertIn("core_drain_command_pool", VULKAN)
        self.assertIn("core_drain_fence", discard)
        self.assertIn("submit.waitSemaphoreCount = wait_count", discard)
        self.assertIn("queue_submit(queue, 1, &submit, core_drain_fence)", discard)
        self.assertIn("acquire_barrier.srcQueueFamilyIndex", discard)
        self.assertIn("release_barrier.dstQueueFamilyIndex", discard)
        self.assertIn("last_submitted_fence = core_drain_fence", discard)
        self.assertIn("!discard_pending_core_frame()", present)
        self.assertIn("vulkan_.discard_pending_core_frame();", HOST)

    def test_software_core_and_presenter_are_bounded_and_fifo_when_cadence_is_close(self):
        self.assertIn("constexpr size_t kSoftwareFrameQueueCapacity = 3", HOST)
        self.assertIn("start_core_thread();", HOST)
        self.assertIn("std::thread software_core_thread_", HOST)
        self.assertIn("void core_thread_loop()", HOST)
        self.assertIn("void present_pending_software_frame()", HOST)
        presenter = HOST[HOST.index("void present_pending_software_frame()"):HOST.index("bool begin_software_frame", HOST.index("void present_pending_software_frame()"))]
        self.assertIn("slot.trace_sample.frame_id < oldest_frame", presenter)
        video = HOST[HOST.index("void on_video("):HOST.index("int16_t input_state", HOST.index("void on_video("))]
        self.assertIn("begin_software_frame(data", video)
        self.assertNotIn("vulkan_.present_software(data", video)
        draw = HOST[HOST.index("void draw()"):HOST.index("  private:", HOST.index("void draw()"))]
        self.assertIn("present_pending_software_frame();", draw)
        async_draw = draw[:draw.index("std::lock_guard<std::mutex> lock(state_mutex_)")]
        self.assertNotIn("run_one_core_frame_locked", async_draw)
        mtk_draw = HOST[HOST.index("- (void)drawInMTKView"):HOST.index("- (void)mtkView", HOST.index("- (void)drawInMTKView"))]
        self.assertNotIn("[self syncSpeedControls];", mtk_draw)


if __name__ == "__main__":
    unittest.main()
