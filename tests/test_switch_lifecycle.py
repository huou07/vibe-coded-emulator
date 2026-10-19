# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Switch companion lifecycle stress: repeated cycles, rapid start/stop and
orphan checks. Uses isolated data and never touches the owner's saves.
"""

from pathlib import Path
import os
import shutil
import subprocess
import tempfile
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


def _first(candidates):
    for raw in candidates:
        if raw and Path(raw).exists():
            return Path(raw)
    return None


def _running_companions(path):
    """Return only this checkout's companion processes."""

    command_path = str(path)
    resolved_path = str(path.resolve())
    result = subprocess.run(["pgrep", "-af", "an3_switch_companion"], capture_output=True, text=True)
    return [
        line for line in result.stdout.splitlines()
        if command_path in line or resolved_path in line
    ]


class SwitchLifecycleStressTests(unittest.TestCase):
    def setUp(self):
        self.companion = _first(COMPANION_CANDIDATES)
        self.moltenvk = _first(MOLTENVK_CANDIDATES)
        self.homebrew = _first(HOMEBREW_CANDIDATES)
        if self.companion is None or self.homebrew is None:
            self.skipTest("companion or legal homebrew fixture is unavailable")
        self.tmp = Path(tempfile.mkdtemp(prefix="an3-switch-life-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _session(self, commands="quit\n", timeout=60):
        env = dict(os.environ)
        env["HOME"] = str(self.tmp)
        if self.moltenvk is not None:
            env["LIBVULKAN_PATH"] = str(self.moltenvk)
        process = subprocess.Popen(
            [str(self.companion), str(self.homebrew)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=env,
        )
        try:
            stdout, _ = process.communicate(commands, timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            self.fail("a companion cycle did not exit within the timeout")
        return process.returncode, stdout

    def test_60_repeated_cycles_exit_cleanly_and_leave_no_orphans(self):
        before = len(_running_companions(self.companion))
        for index in range(5):
            code, stdout = self._session("status\nquit\n")
            self.assertEqual(code, 0, f"cycle {index} exited {code}")
            self.assertIn('"result":"PASS"', stdout)
        self.assertEqual(len(_running_companions(self.companion)), before, "a companion process was orphaned")

    def test_61_rapid_start_stop_is_safe(self):
        # Quitting immediately exercises the Eden early-shutdown race.
        before = len(_running_companions(self.companion))
        for _ in range(3):
            code, _ = self._session("quit\n")
            self.assertEqual(code, 0, "an immediate quit aborted or hung")
        self.assertEqual(len(_running_companions(self.companion)), before, "a companion process was orphaned")

    def test_62_companion_crash_then_restart(self):
        env = dict(os.environ)
        env["HOME"] = str(self.tmp)
        if self.moltenvk is not None:
            env["LIBVULKAN_PATH"] = str(self.moltenvk)
        crashed = subprocess.Popen(
            [str(self.companion), str(self.homebrew)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        import time as _time
        _time.sleep(4)
        crashed.kill()  # simulate an unexpected crash
        crashed.wait()
        # A fresh companion must still start and exit cleanly afterwards.
        code, stdout = self._session("status\nquit\n")
        self.assertEqual(code, 0)
        self.assertIn('"result":"PASS"', stdout)


if __name__ == "__main__":
    unittest.main()
