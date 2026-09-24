# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""AN3 app wiring for the Eden hosted frame (M2).

Source contracts that the AN3 macOS app captures the companion's
`AN3CTL_HOSTED {shm,...}` line, drives a native consumer that imports the
IOSurface as an MTLTexture, and never links Eden. Runtime proof lives in the
Rust tests:
  - `switch_companion::tests::e2e_hosted_frame_ring_is_captured`
  - `hosted_frame::tests::e2e_consumer_imports_frames_over_shm`
Both are ignored by default and require AN3_SWITCH_COMPANION/AN3_SWITCH_HOMEBREW.
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TAURI = ROOT / "native-offline" / "src-tauri"
SWITCH = (TAURI / "src" / "switch_companion.rs").read_text(encoding="utf-8")
HOSTED = (TAURI / "src" / "hosted_frame.rs").read_text(encoding="utf-8")
CONSUMER_H = (TAURI / "src" / "hosted_frame_consumer.h").read_text(encoding="utf-8")
CONSUMER_MM = (TAURI / "src" / "hosted_frame_consumer.mm").read_text(encoding="utf-8")
LIB = (TAURI / "src" / "lib.rs").read_text(encoding="utf-8")
BUILD = (TAURI / "build.rs").read_text(encoding="utf-8")
CAPABILITIES = (TAURI / "capabilities" / "default.json").read_text(encoding="utf-8")
PRODUCER = (ROOT / "native/eden-bridge/src/hosted_frame_producer.cpp").read_text(
    encoding="utf-8"
)


class HostedFrameAppWiringTests(unittest.TestCase):
    def test_01_companion_module_parses_and_exposes_the_ring(self):
        self.assertIn("AN3CTL_HOSTED", SWITCH)
        self.assertIn("fn hosted_from_line", SWITCH)
        self.assertIn("pub struct HostedFrameInfo", SWITCH)
        self.assertIn("pub fn hosted_frame", SWITCH)
        # The handle is cleared with the session so a stale ring never leaks.
        self.assertIn("*hosted_lock() = None;", SWITCH)

    def test_02_capture_command_is_registered_everywhere(self):
        self.assertIn("fn switch_companion_hosted_frame", LIB)
        self.assertIn("switch_companion_hosted_frame,", LIB)
        self.assertIn('"switch_companion_hosted_frame",', BUILD)
        self.assertIn("allow-switch-companion-hosted-frame", CAPABILITIES)

    def test_03_app_never_links_eden(self):
        # The app consumes a ring name and iOSurface ids; it must not include
        # Eden sources or Vulkan headers.
        for text in (SWITCH, HOSTED, CONSUMER_MM):
            self.assertNotIn("backend_eden", text)
            self.assertNotIn("vk_swapchain", text)
            self.assertNotIn("vulkan.h", text)

    def test_04_the_name_matches_the_producer(self):
        self.assertIn('"/an3hf_%d_%08x"', PRODUCER)
        self.assertIn("AN3CTL_HOSTED", PRODUCER)

    def test_05_transport_is_local_shared_memory(self):
        self.assertIn("an3_eden_hosted_shm_create", PRODUCER)
        self.assertNotIn("socket(", PRODUCER)
        self.assertNotIn("connect(", PRODUCER)

    def test_06_native_consumer_imports_the_iosurface(self):
        for symbol in (
            "IOSurfaceLookup",
            "newTextureWithDescriptor",
            "iosurface:",
            "MTLPixelFormatBGRA8Unorm",
            "an3_eden_hosted_consumer_attach",
        ):
            self.assertIn(symbol, CONSUMER_MM)
        self.assertIn("an3_eden_hosted_frame_shm.h", CONSUMER_MM)
        self.assertIn("an3_eden_hosted_consumer_attach", CONSUMER_H)

    def test_07_overlay_is_pointer_inert(self):
        # The player's input precedence must be preserved: the overlay never
        # receives a pointer and never becomes first responder.
        self.assertIn("hitTest:(NSPoint)point", CONSUMER_MM)
        self.assertIn("return nil;", CONSUMER_MM)
        self.assertIn("acceptsFirstResponder", CONSUMER_MM)
        self.assertIn("return NO;", CONSUMER_MM)
        self.assertIn("addSubview", CONSUMER_MM)
        self.assertIn("MTKView", CONSUMER_MM)

    def test_08_consumer_is_built_and_frameworks_linked(self):
        self.assertIn("src/hosted_frame_consumer.mm", BUILD)
        self.assertIn("native/eden-bridge/src/an3_eden_hosted_frame.c", BUILD)
        self.assertIn("native/eden-bridge/src/an3_eden_hosted_frame_shm.c", BUILD)
        self.assertIn("framework=IOSurface", BUILD)
        self.assertIn("framework=MetalKit", BUILD)
        self.assertIn("framework=CoreImage", BUILD)

    def test_09_consumer_commands_are_registered_everywhere(self):
        for command in (
            "switch_companion_hosted_frame_start",
            "switch_companion_hosted_frame_stop",
            "switch_companion_hosted_frame_stats",
            "switch_companion_hosted_frame_verify",
        ):
            self.assertIn(f"fn {command}", LIB)
            self.assertIn(f'"{command}",', BUILD)
            self.assertIn(command.replace("_", "-"), CAPABILITIES)
        # The Rust driver declares the C ABI it calls.
        for symbol in (
            "an3_eden_hosted_consumer_get_stats",
            "an3_eden_hosted_consumer_present_start",
            "an3_eden_hosted_consumer_present_stop",
        ):
            self.assertIn(symbol, HOSTED)

    def test_10_companion_lifecycle_drives_the_overlay(self):
        # A hosted companion is presented by AN3's overlay; the launch commands
        # start it once the ring appears, and stop tears it down.
        self.assertIn("pub fn start_when_ready", HOSTED)
        self.assertIn("hosted_frame::start_when_ready(&app)", LIB)
        self.assertIn("hosted_frame::stop()", LIB)
        self.assertIn("if hosted {", LIB)
        for command in ("fn switch_companion_launch(", "fn switch_companion_launch_rom("):
            self.assertIn(command, LIB)

    def test_11_hosted_presentation_is_explicit_and_probed(self):
        # The launch commands take an explicit `hosted` option and only start the
        # overlay for it; a support probe lets the bridge pick it on macOS only.
        self.assertIn("hosted: Option<bool>", LIB)
        self.assertIn("let hosted = hosted.unwrap_or(false);", LIB)
        self.assertIn("fn switch_companion_hosted_frame_supported", LIB)
        self.assertIn('"switch_companion_hosted_frame_supported",', BUILD)
        self.assertIn("allow-switch-companion-hosted-frame-supported", CAPABILITIES)
        bootstrap = (
            ROOT / "native-offline" / "web" / "native-bootstrap.js"
        ).read_text(encoding="utf-8")
        self.assertIn("switch_companion_hosted_frame_supported", bootstrap)
        self.assertIn("launchSwitch(", bootstrap)
        self.assertIn("hosted: !!hosted", bootstrap)
        self.assertIn("visible: !hosted", bootstrap)


if __name__ == "__main__":
    unittest.main()
