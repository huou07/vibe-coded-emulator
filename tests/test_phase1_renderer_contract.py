# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
RUNTIME = (ROOT / "static" / "player-runtime.js").read_text(encoding="utf-8")
WORKER = (ROOT / "static" / "renderer-worker.js").read_text(encoding="utf-8")
PLAYER = (ROOT / "static" / "player.js").read_text(encoding="utf-8")
OFFLINE = (ROOT / "static" / "offline.js").read_text(encoding="utf-8")
SERVICE_WORKER = (ROOT / "static" / "service-worker.js").read_text(encoding="utf-8")
NATIVE_HEADER = (ROOT / "native-offline" / "src-tauri" / "src" / "vulkan_frontend.h").read_text(encoding="utf-8")
NATIVE_CONTRACT = (ROOT / "native-offline" / "native-runtime" / "core" / "renderer_contract.h").read_text(encoding="utf-8")
NATIVE_HOST_HEADER = (ROOT / "native-offline" / "src-tauri" / "src" / "azahar_host.h").read_text(encoding="utf-8")
NATIVE_HOST = (ROOT / "native-offline" / "src-tauri" / "src" / "azahar_host.mm").read_text(encoding="utf-8")
NATIVE_SMOKE = (ROOT / "native-offline" / "tests" / "native_smoke.mm").read_text(encoding="utf-8")


class Phase1RendererContractTests(unittest.TestCase):
    def test_real_web_presenter_has_worker_webgpu_primary_and_webgl2_fallback(self):
        self.assertIn("transferControlToOffscreen", WORKER)
        self.assertIn("new Worker(this.workerUrl)", WORKER)
        self.assertIn("requestAdapter", WORKER)
        self.assertIn('getContext("webgpu")', WORKER)
        self.assertIn("copyExternalImageToTexture", WORKER)
        self.assertIn('getContext("webgl2"', WORKER)
        self.assertIn("texStorage2D", WORKER)
        self.assertIn("texSubImage2D", WORKER)
        self.assertIn('const FRAME_RING_SIZE = 2', WORKER)
        self.assertIn('transport: "bounded-latest-frame-wins"', WORKER)

    def test_renderer_reports_requested_and_effective_separately(self):
        self.assertIn("requested: this.requested", RUNTIME)
        self.assertIn("effective: this.effective", RUNTIME)
        self.assertIn("rendererRequested", PLAYER)
        self.assertIn("rendererEffective", PLAYER)
        self.assertIn("AN3RendererStatus", PLAYER)

    def test_emulatorjs_boundary_is_explicit_and_sab_is_not_faked(self):
        self.assertIn('rawFramebuffer: false', RUNTIME)
        self.assertIn('rawFramebufferProvider: null', RUNTIME)
        self.assertIn("ImageBitmap", WORKER)
        self.assertIn("EmulatorJS canvas remains the source of truth", WORKER)
        self.assertIn("SharedArrayBuffer", RUNTIME)

    def test_ten_slots_keep_the_v1_format_and_restore_historical_slot_five(self):
        self.assertIn("Array.from({length: 10}", RUNTIME)
        self.assertIn("Quick-save slots range from 1 to 10.", RUNTIME)
        self.assertIn("range(1, 11)", APP)
        self.assertIn("length:10", OFFLINE)
        self.assertIn("slot < 1 || slot > kMaxQuickStateSlot", NATIVE_HOST)
        self.assertIn("constexpr unsigned kMaxQuickStateSlot = 10", NATIVE_HOST)
        self.assertIn("indexedDB.open(this.databaseName, 1)", RUNTIME)
        self.assertNotIn("delete(this.id(5))", RUNTIME)
        self.assertNotIn("delete(this.id(5))", RUNTIME)

    def test_native_telemetry_extends_diagnostics_without_touching_vulkan_contract(self):
        for field in (
            "emulate_p95_us", "emulate_p99_us", "audio_queue_depth_frames",
            "audio_underruns", "audio_overruns", "resident_memory_bytes",
            "cpu_user_time_us", "cpu_system_time_us",
        ):
            self.assertIn(field, NATIVE_CONTRACT)
            self.assertIn(field, NATIVE_HOST_HEADER)
            self.assertIn(field, NATIVE_HOST)
            self.assertIn(field, NATIVE_SMOKE)
        self.assertIn("HostTimingSeries", NATIVE_HOST)
        self.assertIn("std::chrono::steady_clock::now()", NATIVE_HOST)


if __name__ == "__main__":
    unittest.main()
