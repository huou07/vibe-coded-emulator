# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Switch / Eden bridge contracts and runtime guards.

The source contracts always run. The runtime guards run the deterministic Eden
bridge harness and are skipped when it (or the legal homebrew fixture) is not
available, so the suite stays green on machines without an Eden build. They
never substitute a one-frame load for sustained-rendering evidence: the
sustained guard is opt-in and explicit.
"""

from pathlib import Path
import json
import os
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "native/eden-bridge"
HEADER = (BRIDGE / "include/an3_eden_bridge.h").read_text(encoding="utf-8")
INTERNAL = (BRIDGE / "src/an3_eden_internal.h").read_text(encoding="utf-8")
BACKEND = (BRIDGE / "src/backend_eden.cpp").read_text(encoding="utf-8")
NULL_BACKEND = (BRIDGE / "src/backend_null.cpp").read_text(encoding="utf-8")
SURFACE = (BRIDGE / "src/cocoa_surface.mm").read_text(encoding="utf-8")
SMOKE = (BRIDGE / "tests/bridge_smoke.c").read_text(encoding="utf-8")

HARNESS_CANDIDATES = [
    os.environ.get("AN3_SWITCH_HARNESS", ""),
    "/tmp/eden-build/bin/an3_eden_bridge_smoke",
    str(BRIDGE / "build/an3_eden_bridge_smoke"),
]
MOLTENVK_CANDIDATES = [
    os.environ.get("LIBVULKAN_PATH", ""),
    "/tmp/eden/.cache/cpm/moltenvk/v1.4.1-ryujinx/MoltenVK/dynamic/dylib/macOS/libMoltenVK.dylib",
]


def _first_existing(candidates):
    for raw in candidates:
        if not raw:
            continue
        candidate = Path(raw)
        if candidate.exists():
            return candidate
    return None


def _homebrew():
    explicit = os.environ.get("AN3_SWITCH_HOMEBREW")
    if explicit and Path(explicit).exists():
        return Path(explicit)
    for candidate in (Path("/tmp/an3-switch/hbmenu.nro"), Path("/tmp/hbmenu.nro")):
        if candidate.exists():
            return candidate
    return None


def _run_harness(args, timeout=180):
    harness = _first_existing(HARNESS_CANDIDATES)
    if harness is None:
        raise unittest.SkipTest("Eden bridge harness is not built in this environment")
    env = dict(os.environ)
    moltenvk = _first_existing(MOLTENVK_CANDIDATES)
    if moltenvk is not None:
        env["LIBVULKAN_PATH"] = str(moltenvk)
    return subprocess.run(
        [str(harness), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )


def _status(result):
    for line in reversed(result.stdout.splitlines()):
        marker = "AN3CTL_STATUS "
        if marker in line:
            return json.loads(line[line.index(marker) + len(marker):])
    return None


class EdenBridgeContractTests(unittest.TestCase):
    """Source contracts that must hold without running Eden."""

    def test_01_abi_is_version_two(self):
        self.assertIn("#define AN3_EDEN_BRIDGE_ABI_VERSION 2u", HEADER)

    def test_02_analog_has_a_stick_selector(self):
        self.assertIn("AN3_EDEN_STICK_LEFT = 0", HEADER)
        self.assertIn("AN3_EDEN_STICK_RIGHT = 1", HEADER)
        self.assertIn("uint32_t stick, int16_t x, int16_t y", HEADER)

    def test_03_input_and_diagnostics_exist_in_both_backends(self):
        for symbol in ("an3_eden_submit_button", "an3_eden_submit_analog",
                       "an3_eden_get_button", "an3_eden_get_analog",
                       "an3_eden_get_save_dir"):
            self.assertIn(symbol, HEADER)
        for entry in ("(*submit_button)", "(*submit_analog)", "(*get_button)",
                      "(*get_analog)", "(*get_save_dir)"):
            self.assertIn(entry, INTERNAL)
        self.assertIn("eden_get_button", BACKEND)
        self.assertIn("eden_get_analog", BACKEND)
        self.assertIn("null_get_button", NULL_BACKEND)
        self.assertIn("null_get_analog", NULL_BACKEND)

    def test_04_input_drives_edens_virtual_gamepad(self):
        self.assertIn("GetVirtualGamepad", BACKEND)
        self.assertIn("SetButtonState", BACKEND)
        self.assertIn("SetStickPosition", BACKEND)
        # The engine must be registered before the system builds its devices.
        self.assertLess(
            BACKEND.index("state->input->Initialize()"),
            BACKEND.index("state->system = std::make_unique<Core::System>()"),
        )

    def test_05_sustained_rendering_fix_hosts_the_metal_layer(self):
        # RG-115: the layer must be attached to a window/view with a real size.
        self.assertIn("NSWindow", SURFACE)
        self.assertIn("NSView", SURFACE)
        self.assertIn("drawableSize", SURFACE)
        self.assertIn("orderFrontRegardless", SURFACE)

    def test_06_saves_are_exported_not_overwritten_in_place(self):
        self.assertIn("eden_get_save_dir", BACKEND)
        self.assertIn("EdenPath::SaveDir", BACKEND)
        # The export writes to the caller's destination only.
        self.assertIn("fs::create_directories(destination", BACKEND)

    def test_07_harness_can_prove_input_reaches_eden(self):
        self.assertIn("get_button", SMOKE)
        self.assertIn("inputSupported", SMOKE)
        self.assertIn("--seconds", SMOKE)

    def test_08_null_backend_never_fakes_success(self):
        self.assertIn("null_unavailable", NULL_BACKEND)
        self.assertNotIn("return AN3_EDEN_OK;", NULL_BACKEND.split("null_stop")[0])


class EdenBridgeRuntimeTests(unittest.TestCase):
    """Runtime guards. Skipped without a built harness."""

    def test_20_error_path_passes_without_content(self):
        result = _run_harness(["--json"])
        status = _status(result)
        self.assertIsNotNone(status, result.stderr[-400:])
        self.assertEqual(status["result"], "PASS")
        self.assertEqual(status["failures"], 0)

    def test_21_legal_homebrew_loads_and_input_reaches_eden(self):
        homebrew = _homebrew()
        if homebrew is None:
            self.skipTest("No legal homebrew fixture (set AN3_SWITCH_HOMEBREW to an .nro)")
        result = _run_harness(["--json", "--frames", "5", str(homebrew)])
        status = _status(result)
        self.assertIsNotNone(status, result.stderr[-400:])
        self.assertEqual(status["result"], "PASS")
        self.assertEqual(status["failures"], 0)
        self.assertTrue(status["loaded"])
        self.assertTrue(status["inputSupported"])

    def test_22_sustained_rendering_is_opt_in(self):
        seconds = os.environ.get("AN3_SWITCH_SUSTAINED_SECONDS")
        if not seconds:
            self.skipTest("Set AN3_SWITCH_SUSTAINED_SECONDS to run the sustained guard")
        homebrew = _homebrew()
        if homebrew is None:
            self.skipTest("No legal homebrew fixture (set AN3_SWITCH_HOMEBREW to an .nro)")
        result = _run_harness(
            ["--json", "--seconds", str(int(seconds)), str(homebrew)],
            timeout=int(seconds) + 180,
        )
        status = _status(result)
        self.assertIsNotNone(status, result.stderr[-400:])
        self.assertEqual(status["result"], "PASS")
        self.assertEqual(status["failures"], 0)
        self.assertGreater(status["framesRun"], 0)


class SwitchCompanionContractTests(unittest.TestCase):
    """The app must control Switch as a separate process and never advertise it
    as a libretro/NativeSystem core."""

    def setUp(self):
        self.companion = ROOT / "native-offline/src-tauri/src/switch_companion.rs"
        self.lib = (ROOT / "native-offline/src-tauri/src/lib.rs").read_text(encoding="utf-8")

    def test_30_companion_module_defines_the_lifecycle(self):
        source = self.companion.read_text(encoding="utf-8")
        for symbol in ("pub fn detect", "pub fn launch", "pub fn status", "pub fn stop"):
            self.assertIn(symbol, source)

    def test_31_app_registers_the_companion_commands(self):
        self.assertIn("mod switch_companion;", self.lib)
        for command in ("switch_companion_detect", "switch_companion_launch",
                        "switch_companion_status", "switch_companion_stop",
                        "switch_companion_focus", "switch_companion_input",
                        "switch_companion_analog", "switch_companion_audio"):
            self.assertIn(command, self.lib)

    def test_33_companion_resolves_from_the_installed_layout(self):
        source = self.companion.read_text(encoding="utf-8")
        # Bundled resource path first, development vendor path second; no
        # machine-specific absolute path.
        self.assertIn("switch/macos-arm64/an3_switch_companion", source)
        self.assertIn("resource_dir", source)
        self.assertIn("AN3_SWITCH_COMPANION", source)
        self.assertNotIn("/tmp/eden-build", source)
        self.assertNotIn("/Users/", source)

    def test_34_companion_control_channel_is_bounded(self):
        source = self.companion.read_text(encoding="utf-8")
        self.assertIn("recv_timeout", source)
        self.assertIn("IPC_TIMEOUT", source)
        self.assertIn("STOP_TIMEOUT", source)
        self.assertIn("try_wait", source)

    def test_32_switch_is_routed_to_the_companion_not_the_libretro_host(self):
        bootstrap = (ROOT / "native-offline/web/native-bootstrap.js").read_text(encoding="utf-8")
        offline = (ROOT / "static/offline.js").read_text(encoding="utf-8")
        # The library recognises .nro as Nintendo Switch.
        self.assertIn('switch:{label:"Nintendo Switch"', offline)
        self.assertIn('".nro":"switch"', offline)
        # Launch routes Switch to the companion, never start_native_game.
        self.assertIn('nativeSystem === "switch"', bootstrap)
        self.assertIn('switch_companion_launch_rom', bootstrap)
        # Capability is detected at runtime, not claimed statically.
        self.assertIn("AN3NativeSwitch.detect()", bootstrap)
        # The rom-id launcher enforces .nro only.
        self.assertIn("Only Nintendo Switch .nro homebrew", self.companion.read_text(encoding="utf-8"))
        self.assertIn("switch_companion_launch_rom", self.lib)
        self.assertIn("switch_companion::stop()", self.lib)

    def test_35_nro_detection_is_wired_in_the_importer(self):
        self.assertIn('eq_ignore_ascii_case("nro")', self.lib_source())

    def lib_source(self):
        return (ROOT / "native-offline/src-tauri/src/lib.rs").read_text(encoding="utf-8")

    def test_36_switch_ui_has_focus_and_stop_controls(self):
        offline = (ROOT / "static/offline.js").read_text(encoding="utf-8")
        self.assertIn('dataset.switchControl="focus"', offline)
        self.assertIn('dataset.switchControl="stop"', offline)
        self.assertIn("AN3NativeSwitch", offline)
        self.assertIn("AN3RerenderLibrary", offline)

    def test_37_companion_e2e_test_is_present_and_gated(self):
        source = self.companion.read_text(encoding="utf-8")
        self.assertIn("e2e_launch_input_stop_relaunch", source)
        self.assertIn("AN3_SWITCH_HOMEBREW", source)
        self.assertIn("AN3_SWITCH_COMPANION", source)


    def test_23_missing_vulkan_is_structured_not_a_crash(self):
        """RG-111: Eden's ErrorVideoCore path terminates in a noexcept destructor.
        The bridge pre-flights Vulkan, so a missing runtime must be a structured
        UNAVAILABLE with exit 0, never SIGABRT."""
        homebrew = _homebrew()
        if homebrew is None:
            self.skipTest("No legal homebrew fixture (set AN3_SWITCH_HOMEBREW to an .nro)")
        harness = _first_existing(HARNESS_CANDIDATES)
        if harness is None:
            self.skipTest("Eden bridge harness is not built in this environment")
        env = {key: value for key, value in os.environ.items() if key != "LIBVULKAN_PATH"}
        result = subprocess.run(
            [str(harness), "--json", "--frames", "1", str(homebrew)],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
        status = _status(result)
        self.assertIsNotNone(status, result.stderr[-400:])
        self.assertEqual(result.returncode, 0, "a missing Vulkan runtime must not abort the process")
        self.assertEqual(status["result"], "PASS")
        self.assertFalse(status["loaded"])


if __name__ == "__main__":
    unittest.main()
