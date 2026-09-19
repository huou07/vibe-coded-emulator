# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Switch save persistence, service level, fully isolated.

Eden owns save data and writes it under its own data directory. These tests run
the separate companion with an isolated ``HOME`` so the owner's real saves and
configuration are never touched, then verify that the save store survives a
clean restart and an abrupt termination.

This is *service-level* persistence (Eden's save store and our export path). A
game-level save round-trip needs a homebrew title that actually writes a save;
nx-hbmenu does not, so that remains UNVERIFIED and is not claimed here.
"""

from hashlib import sha256
from pathlib import Path
import os
import shutil
import subprocess
import sys
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
HOMEBREW_CANDIDATES = [
    os.environ.get("AN3_SWITCH_HOMEBREW", ""),
    "/tmp/an3-switch/hbmenu.nro",
    "/tmp/hbmenu.nro",
]


def _first(candidates):
    for raw in candidates:
        if raw and Path(raw).exists():
            return Path(raw)
    return None


def _manifest(root):
    """path -> sha256 for every file under root (empty when root is absent)."""
    entries = {}
    if not root.exists():
        return entries
    for path in sorted(root.rglob("*")):
        if path.is_file():
            entries[str(path.relative_to(root))] = sha256(path.read_bytes()).hexdigest()
    return entries


class SwitchSavePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.companion = _first(COMPANION_CANDIDATES)
        self.moltenvk = _first(MOLTENVK_CANDIDATES)
        self.homebrew = _first(HOMEBREW_CANDIDATES)
        if self.companion is None or self.homebrew is None:
            self.skipTest("companion or legal homebrew fixture is unavailable")
        self.tmp = Path(tempfile.mkdtemp(prefix="an3-switch-saves-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    @property
    def save_root(self):
        return self.tmp / ".local/share/eden/nand"

    def run_companion(self, seconds=8, kill_after=None):
        env = dict(os.environ)
        env["HOME"] = str(self.tmp)
        if self.moltenvk is not None:
            env["LIBVULKAN_PATH"] = str(self.moltenvk)
        process = subprocess.Popen(
            [str(self.companion), str(self.homebrew), "--seconds", str(seconds)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        try:
            process.wait(timeout=kill_after or (seconds + 60))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        return process.returncode

    def test_40_save_store_is_created_and_survives_a_restart(self):
        self.run_companion(seconds=8)
        self.assertTrue(self.save_root.exists(), "Eden did not create its save store")
        first = _manifest(self.save_root)
        self.assertTrue(first, "the save store is empty")

        self.run_companion(seconds=8)
        second = _manifest(self.save_root)
        # Every previously written file is still there after a clean restart.
        missing = [name for name in first if name not in second]
        self.assertEqual(missing, [], f"save files disappeared across a restart: {missing}")

    def test_41_save_store_survives_an_abrupt_termination(self):
        self.run_companion(seconds=30, kill_after=4)  # SIGKILL mid-run
        self.assertTrue(self.save_root.exists(), "Eden did not create its save store")
        # A crash must not make the store unreadable: a fresh run still works.
        code = self.run_companion(seconds=8)
        self.assertEqual(code, 0, "the companion could not restart after an abrupt kill")

    def test_42_owner_home_is_never_used(self):
        real_home_save = Path.home() / ".local/share/eden/nand"
        before = _manifest(real_home_save).keys() if real_home_save.exists() else set()
        self.run_companion(seconds=6)
        after = _manifest(real_home_save).keys() if real_home_save.exists() else set()
        self.assertEqual(set(before), set(after), "the isolated run modified the owner's save store")


if __name__ == "__main__":
    unittest.main()
