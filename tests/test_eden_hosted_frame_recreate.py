# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Producer slot-recreation contracts and runtime guard.

The hosted-frame producer must rebuild its IOSurface-backed slots when the
swapchain extent/format changes instead of rejecting frames forever. The
runtime guard uses the bounded diagnostic trigger
(`AN3_HOSTED_FORCE_RECREATE_AFTER`) to exercise the real teardown/create path
without a GUI window resize. Skipped when the companion/fixture is unavailable.
"""
import os
import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRODUCER = (
    ROOT / "native" / "eden-bridge" / "src" / "hosted_frame_producer.cpp"
).read_text(encoding="utf-8")

COMPANION_CANDIDATES = [
    os.environ.get("AN3_SWITCH_COMPANION", ""),
    "/tmp/eden-build/bin/an3_switch_companion",
]
MOLTENVK_CANDIDATES = [
    os.environ.get("LIBVULKAN_PATH", ""),
    "/tmp/eden/.cache/cpm/moltenvk/v1.4.1-ryujinx/MoltenVK/dynamic/dylib/macOS/libMoltenVK.dylib",
]


def _first_existing(candidates):
    for raw in candidates:
        if raw and pathlib.Path(raw).exists():
            return pathlib.Path(raw)
    return None


def _homebrew():
    explicit = os.environ.get("AN3_SWITCH_HOMEBREW")
    if explicit and pathlib.Path(explicit).exists():
        return pathlib.Path(explicit)
    for candidate in (
        pathlib.Path("/tmp/an3-hbmenu/hbmenu.nro"),
        pathlib.Path("/tmp/hbmenu.nro"),
        pathlib.Path("/tmp/an3-switch/hbmenu.nro"),
    ):
        if candidate.exists():
            return candidate
    return None


class HostedFrameRecreateContractTests(unittest.TestCase):
    def test_01_producer_rebuilds_slots_on_change(self):
        for symbol in ("rebuild_slots", "teardown_slots", "destroy_slot"):
            self.assertIn(symbol, PRODUCER)
        # A changed device is refused, not mixed with images from another device.
        self.assertIn("e.device != device", PRODUCER)

    def test_02_teardown_releases_every_vulkan_object(self):
        for symbol in (
            "vk.destroy_fence",
            "vk.destroy_image",
            "vk.free_memory",
            "vk.destroy_command_pool",
            "vk.device_wait_idle",
            "CFRelease(slot.surface)",
        ):
            self.assertIn(symbol, PRODUCER)

    def test_03_epoch_is_bumped_on_recreation(self):
        # Consumers use the epoch to discard descriptors that named old slots.
        self.assertIn("g_epoch = (static_cast<uint64_t>(arc4random())", PRODUCER)
        self.assertIn("recreated", PRODUCER)

    def test_04_trigger_is_env_gated_and_defaults_off(self):
        self.assertIn("AN3_HOSTED_FORCE_RECREATE_AFTER", PRODUCER)
        self.assertIn(": 0u;", PRODUCER)

    def test_05_extent_change_rebuilds_and_copies_overlap(self):
        self.assertIn("AN3_HOSTED_FORCE_RESIZE", PRODUCER)
        # A rebuild at a different extent must copy only the overlapping region.
        self.assertIn("std::min(e.width, source_width)", PRODUCER)
        self.assertIn("std::min(e.height, source_height)", PRODUCER)


class HostedFrameRecreateRuntimeTests(unittest.TestCase):
    def test_20_forced_recreation_keeps_frames_flowing(self):
        companion = _first_existing(COMPANION_CANDIDATES)
        homebrew = _homebrew()
        if companion is None:
            self.skipTest("Eden companion is not built in this environment")
        if homebrew is None:
            self.skipTest("No legal homebrew fixture (set AN3_SWITCH_HOMEBREW to an .nro)")

        env = dict(os.environ)
        moltenvk = _first_existing(MOLTENVK_CANDIDATES)
        if moltenvk is not None:
            env["LIBVULKAN_PATH"] = str(moltenvk)
        env["AN3_HOSTED_FORCE_RECREATE_AFTER"] = "20"

        result = subprocess.run(
            [str(companion), "--frames", "60", str(homebrew)],
            capture_output=True,
            text=True,
            env=env,
            timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stdout[-800:] + result.stderr[-800:])
        self.assertIn('"recreated":1', result.stdout)
        self.assertNotIn("VK_TIMEOUT", result.stdout)
        self.assertNotIn("copy_failed", result.stdout)
        self.assertNotIn("recreate_failed", result.stdout)
        statuses = re.findall(r"AN3CTL_STATUS \{.*\}", result.stdout)
        self.assertTrue(statuses, result.stdout[-400:])
        self.assertIn('"result":"PASS"', statuses[-1])
        frames = re.search(r'"frames":(\d+)', statuses[-1])
        self.assertIsNotNone(frames)
        self.assertGreater(int(frames.group(1)), 0)

    def test_21_extent_change_rebuilds_to_a_different_size(self):
        companion = _first_existing(COMPANION_CANDIDATES)
        homebrew = _homebrew()
        if companion is None:
            self.skipTest("Eden companion is not built in this environment")
        if homebrew is None:
            self.skipTest("No legal homebrew fixture (set AN3_SWITCH_HOMEBREW to an .nro)")

        env = dict(os.environ)
        moltenvk = _first_existing(MOLTENVK_CANDIDATES)
        if moltenvk is not None:
            env["LIBVULKAN_PATH"] = str(moltenvk)
        env["AN3_HOSTED_FORCE_RECREATE_AFTER"] = "20"
        env["AN3_HOSTED_FORCE_RESIZE"] = "640x360"

        result = subprocess.run(
            [str(companion), "--no-stdin", "--frames", "60", str(homebrew)],
            capture_output=True,
            text=True,
            env=env,
            timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stdout[-800:] + result.stderr[-800:])
        # The forced rebuild allocates at the new extent; the next present then
        # drives a real mismatch rebuild back to the presented extent.
        self.assertIn('"w":640,"h":360', result.stdout)
        self.assertNotIn("copy_failed", result.stdout)
        self.assertNotIn("recreate_failed", result.stdout)
        self.assertNotIn("VK_TIMEOUT", result.stdout)
        statuses = re.findall(r"AN3CTL_STATUS \{.*\}", result.stdout)
        self.assertTrue(statuses, result.stdout[-400:])
        self.assertIn('"result":"PASS"', statuses[-1])


if __name__ == "__main__":
    unittest.main()
