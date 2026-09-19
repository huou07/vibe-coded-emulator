# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Switch companion failure paths and RG-111 coverage.

Every failure must be a structured result (a `load-failed` status and a normal
exit code), never a SIGABRT, and the companion must recover on the next launch.
Uses isolated data and a legal fixture only.
"""

from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPANION_CANDIDATES = [
    os.environ.get("AN3_SWITCH_COMPANION", ""),
    str(ROOT / "native-offline/vendor/switch/macos-arm64/an3_switch_companion"),
    "/tmp/eden-build/bin/an3_switch_companion",
]
MOLTENVK_CANDIDATES = [
    os.environ.get("LIBVULKAN_PATH", ""),
    str(ROOT / "native-offline/vendor/moltenvk/macos-arm64/libMoltenVK.dylib"),
    "/tmp/eden/.cache/cpm/moltenvk/v1.4.1-ryujinx/MoltenVK/dynamic/dylib/macOS/libMoltenVK.dylib",
]
HOMEBREW_CANDIDATES = [os.environ.get("AN3_SWITCH_HOMEBREW", ""), "/tmp/an3-switch/hbmenu.nro", "/tmp/hbmenu.nro"]
SIGABRT = {-6, 134}


def _first(candidates):
    for raw in candidates:
        if raw and Path(raw).exists():
            return Path(raw)
    return None


class SwitchFailurePathTests(unittest.TestCase):
    def setUp(self):
        self.companion = _first(COMPANION_CANDIDATES)
        self.moltenvk = _first(MOLTENVK_CANDIDATES)
        self.homebrew = _first(HOMEBREW_CANDIDATES)
        if self.companion is None:
            self.skipTest("the Switch companion is not built")
        self.tmp = Path(tempfile.mkdtemp(prefix="an3-switch-fail-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.home.mkdir()

    def _run(self, content, moltenvk=True, timeout=120, seconds=8):
        env = dict(os.environ)
        env["HOME"] = str(self.home)
        if moltenvk and self.moltenvk is not None:
            env["LIBVULKAN_PATH"] = str(self.moltenvk)
        elif not moltenvk:
            env.pop("LIBVULKAN_PATH", None)
        return subprocess.run(
            [str(self.companion), str(content), "--no-stdin", "--seconds", str(seconds)],
            capture_output=True, text=True, env=env, timeout=timeout,
        )

    @staticmethod
    def _status(stdout):
        for line in reversed(stdout.splitlines()):
            marker = "AN3CTL_STATUS "
            if marker in line:
                return json.loads(line[line.index(marker) + len(marker):])
        return None

    def test_80_invalid_homebrew_fails_structurally(self):
        bad = self.tmp / "bad.nro"
        bad.write_bytes(b"\x00" * 4096)
        result = self._run(bad)
        self.assertNotIn(result.returncode, SIGABRT, "an invalid title must not abort")
        status = self._status(result.stdout)
        self.assertIsNotNone(status, result.stderr[-300:])
        self.assertEqual(status["result"], "FAIL")
        self.assertIn(status["mode"], ("load-failed", "unavailable"))

    def test_81_missing_vulkan_fails_structurally(self):
        if self.homebrew is None:
            self.skipTest("no legal homebrew fixture")
        result = self._run(self.homebrew, moltenvk=False)
        self.assertNotIn(result.returncode, SIGABRT, "a missing Vulkan runtime must not abort")
        status = self._status(result.stdout)
        self.assertIsNotNone(status, result.stderr[-300:])
        self.assertEqual(status["result"], "FAIL")
        self.assertIn("Vulkan", result.stdout + result.stderr)

    def test_82_companion_recovers_after_failures(self):
        if self.homebrew is None:
            self.skipTest("no legal homebrew fixture")
        bad = self.tmp / "bad.nro"
        bad.write_bytes(b"\x00" * 4096)
        # Repeated failures then a good title must still work.
        for _ in range(3):
            self.assertNotIn(self._run(bad).returncode, SIGABRT)
        self.assertNotIn(self._run(self.homebrew, moltenvk=False).returncode, SIGABRT)
        good = self._run(self.homebrew)
        self.assertEqual(good.returncode, 0, good.stderr[-300:])
        self.assertEqual(self._status(good.stdout)["result"], "PASS")

    def test_83_no_stale_state_after_an_invalid_launch(self):
        bad = self.tmp / "bad.nro"
        bad.write_bytes(b"\x00" * 4096)
        self._run(bad)
        # No leftover companion process from the failed attempt.
        result = subprocess.run(["pgrep", "-f", "an3_switch_companion"], capture_output=True, text=True)
        self.assertEqual([line for line in result.stdout.split() if line.strip()], [])


if __name__ == "__main__":
    unittest.main()
