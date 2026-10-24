# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Packaged macOS app: the Switch companion is bundled, self-contained and
launchable from the installed layout.

These run against a real `VibeCodedEmulator.app`, not a binary from the source
tree, and skip when the bundle has not been built.
"""

from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "native-offline/src-tauri/target/release/bundle/macos/VibeCodedEmulator.app"
HOMEBREW_CANDIDATES = [os.environ.get("AN3_SWITCH_HOMEBREW", ""), "/tmp/an3-switch/hbmenu.nro", "/tmp/hbmenu.nro"]


def _homebrew():
    for raw in HOMEBREW_CANDIDATES:
        if raw and Path(raw).exists():
            return Path(raw)
    return None


class SwitchPackagedTests(unittest.TestCase):
    def setUp(self):
        if not APP.exists():
            self.skipTest("the macOS app bundle has not been built")
        self.resources = APP / "Contents/Resources"
        self.companion = self.resources / "switch/macos-arm64/an3_switch_companion"
        self.moltenvk = self.resources / "azahar/macos-arm64/libMoltenVK.dylib"

    def test_50_companion_is_bundled_and_self_contained(self):
        self.assertTrue(self.companion.is_file(), "the companion is not in the bundle")
        self.assertTrue(os.access(self.companion, os.X_OK), "the companion is not executable")
        libs = list((self.resources / "switch/macos-arm64/lib").glob("*.dylib"))
        self.assertGreaterEqual(len(libs), 20, "the bundled library set is incomplete")
        self.assertTrue((self.resources / "switch/macos-arm64/EDEN-GPL-3.0-or-later.txt").is_file())
        manifest = json.loads((self.resources / "switch/macos-arm64/manifest.json").read_text())
        self.assertEqual(manifest["eden"]["commit"], "7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c")
        self.assertEqual(len(manifest["bundledLibraries"]), len(libs))
        # No development-machine paths may remain in the shipped binary.
        out = subprocess.run(["otool", "-L", str(self.companion)], capture_output=True, text=True).stdout
        self.assertNotIn("/opt/homebrew", out)
        self.assertNotIn("/usr/local", out)
        for lib in libs:
            deps = subprocess.run(["otool", "-L", str(lib)], capture_output=True, text=True).stdout
            self.assertNotIn("/opt/homebrew", deps, f"homebrew path remains in {lib.name}")

    def test_51_bundled_companion_runs_with_the_bundled_moltenvk(self):
        homebrew = _homebrew()
        if homebrew is None:
            self.skipTest("no legal homebrew fixture")
        self.assertTrue(self.moltenvk.is_file(), "the bundled MoltenVK is missing")
        with tempfile.TemporaryDirectory(prefix="an3-switch-pkg-") as tmp:
            env = dict(os.environ)
            env["HOME"] = tmp
            env["LIBVULKAN_PATH"] = str(self.moltenvk)
            process = subprocess.Popen(
                [str(self.companion), str(homebrew)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                env=env,
            )
            commands = "status\nstatus\naudio\nbutton A down\nbutton A up\nanalog L 0.5 -0.25\nfocus\nquit\n"
            stdout, _ = process.communicate(commands, timeout=90)
        self.assertEqual(process.returncode, 0, "the bundled companion did not exit cleanly")
        self.assertIn("AN3CTL_STATUS", stdout)
        self.assertIn('"result":"PASS"', stdout)
        self.assertIn("AN3CTL_ACK", stdout)
        self.assertIn('"available":true', stdout)


if __name__ == "__main__":
    unittest.main()
