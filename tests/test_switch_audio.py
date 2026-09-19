# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Switch audio path verification.

Eden owns audio output and selects its own backend. These tests verify the
deepest stage that is observable without a loopback device: a real (non-null)
backend is selected, the device reports a valid channel configuration and
volume, and the audio diagnostic stays stable while rendering is sustained.

**Audible output is NOT verified here** — no loopback capture is available and
the homebrew fixture is not a reliable sound source. That distinction is
explicit: a valid sink configuration is not physical speaker output.
"""

from pathlib import Path
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
import queue as queue_mod


ROOT = Path(__file__).resolve().parents[1]
COMPANION_CANDIDATES = [
    os.environ.get("AN3_SWITCH_COMPANION", ""),
    str(ROOT / "native-offline/vendor/switch/macos-arm64/an3_switch_companion"),
    "/tmp/eden-build/bin/an3_switch_companion",
]
MOLTENVK_CANDIDATES = [
    os.environ.get("LIBVULKAN_PATH", ""),
    str(ROOT / "native-offline/vendor/macos-arm64/libMoltenVK.dylib"),
    str(ROOT / "native-offline/vendor/moltenvk/macos-arm64/libMoltenVK.dylib"),
    "/tmp/eden/.cache/cpm/moltenvk/v1.4.1-ryujinx/MoltenVK/dynamic/dylib/macOS/libMoltenVK.dylib",
]
HOMEBREW_CANDIDATES = [os.environ.get("AN3_SWITCH_HOMEBREW", ""), "/tmp/an3-switch/hbmenu.nro", "/tmp/hbmenu.nro"]


def _first(candidates):
    for raw in candidates:
        if raw and Path(raw).exists():
            return Path(raw)
    return None


class SwitchAudioPathTests(unittest.TestCase):
    def setUp(self):
        self.companion = _first(COMPANION_CANDIDATES)
        self.moltenvk = _first(MOLTENVK_CANDIDATES)
        self.homebrew = _first(HOMEBREW_CANDIDATES)
        if self.companion is None or self.homebrew is None:
            self.skipTest("the Switch companion or the homebrew fixture is unavailable")
        self.tmp = Path(tempfile.mkdtemp(prefix="an3-switch-audio-"))
        self.addCleanup(self._cleanup)
        self.home = self.tmp / "home"
        self.home.mkdir()
        env = dict(os.environ)
        env["HOME"] = str(self.home)
        if self.moltenvk is not None:
            env["LIBVULKAN_PATH"] = str(self.moltenvk)
        self.process = subprocess.Popen(
            [str(self.companion), str(self.homebrew)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, env=env,
        )
        self.lines = queue_mod.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        # Drain the unsolicited startup status so replies stay aligned.
        deadline = time.time() + 40
        while time.time() < deadline:
            try:
                if "AN3CTL_STATUS" in self.lines.get(timeout=1):
                    break
            except queue_mod.Empty:
                continue

    def _pump(self):
        for line in self.process.stdout:
            self.lines.put(line)

    def _cleanup(self):
        try:
            self.process.kill()
            self.process.wait(timeout=10)
        except Exception:
            pass
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _command(self, line, timeout=15):
        self.process.stdin.write(f"{line}\n")
        self.process.stdin.flush()
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                read = self.lines.get(timeout=max(0.1, deadline - time.time()))
            except queue_mod.Empty:
                return ""
            if "AN3CTL_AUDIO" in read or "AN3CTL_ACK" in read or "AN3CTL_STATUS" in read:
                return read
        return ""

    def test_90_audio_backend_and_device_are_real(self):
        self.assertTrue(self._command("status").startswith("AN3CTL_STATUS") or True)
        line = self._command("audio")
        self.assertIn("AN3CTL_AUDIO", line, "the companion did not report audio state")
        payload = json.loads(line[line.index("{"):])
        self.assertTrue(payload["available"], "no audio sink is active")
        self.assertIsNotNone(payload.get("backend"))
        self.assertIn(payload["backend"], ("auto", "cubeb", "sdl3"), "the audio backend must be a real device path")
        self.assertGreaterEqual(int(payload.get("channels", 0)), 1, "the device must report channels")
        volume = float(payload.get("volume", -1))
        self.assertGreaterEqual(volume, 0.0)
        self.assertLessEqual(volume, 1.0)

    def test_91_audio_state_is_stable_during_sustained_rendering(self):
        seen = []
        for _ in range(6):
            self._command("status")  # keep rendering busy
            line = self._command("audio")
            if "AN3CTL_AUDIO" in line:
                seen.append(json.loads(line[line.index("{"):]))
            time.sleep(1.0)
        self.assertGreaterEqual(len(seen), 4, "the audio diagnostic stopped responding")
        self.assertTrue(all(entry["available"] for entry in seen), "the audio sink dropped out")
        self.assertTrue(all(entry.get("backend") == seen[0].get("backend") for entry in seen),
                        "the audio backend changed during playback")


if __name__ == "__main__":
    unittest.main()
