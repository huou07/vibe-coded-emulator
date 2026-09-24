# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Packaged-app Switch UI E2E (macOS).

Drives the **real packaged application** through `an3ctl ui --target macos`,
which dispatches real DOM events on the app's own controls. The import button,
the Switch game card and its launch/focus/stop controls are the actual frontend
handlers a user clicks — this test never calls a Tauri command directly.

The distribution ``VibeCodedEmulator.app`` deliberately does not compile the
test-only ``ui-control`` bridge, so this E2E drives the separate automation
bundle produced by ``native-offline/scripts/build-macos-automation.sh``
(``npm run build:macos-automation``). It requires that bundle plus a legal
homebrew fixture; skips otherwise. The throwaway-copy/isolated-HOME bootstrap is
shared with the GBA/NDS E2E in ``tests/macos_ui_e2e_harness.py``.
"""

from pathlib import Path
import os
import subprocess
import sys
import time
import unittest


sys.path.append(str(Path(__file__).resolve().parent))
from macos_ui_e2e_harness import AUTOMATION_APP, MacosPackagedUiHarness


HOMEBREW_CANDIDATES = [os.environ.get("AN3_SWITCH_HOMEBREW", ""), "/tmp/an3-switch/hbmenu.nro", "/tmp/hbmenu.nro"]


def _homebrew():
    for raw in HOMEBREW_CANDIDATES:
        if raw and Path(raw).exists():
            return Path(raw)
    return None


class SwitchPackagedUiE2ETests(MacosPackagedUiHarness):
    bundle_app_name = "AN3SwitchUITest.app"

    def preflight(self):
        companion = AUTOMATION_APP / "Contents/Resources/switch/macos-arm64/an3_switch_companion"
        if not companion.exists():
            self.skipTest("the app bundle does not contain the Switch companion")
        self.homebrew = _homebrew()
        if self.homebrew is None:
            self.skipTest("no legal homebrew fixture (set AN3_SWITCH_HOMEBREW)")

    def companions(self):
        # The packaged app resolves its companion from its own resource dir, so
        # the throwaway bundle path identifies *this* instance's processes and
        # ignores companions other worktrees are running concurrently.
        result = subprocess.run(["pgrep", "-fl", "an3_switch_companion"], capture_output=True, text=True)
        marker = str(self.app)
        return [line for line in result.stdout.splitlines() if line.strip() and marker in line]

    def test_70_packaged_switch_ui_full_workflow(self):
        started = self.app_start(self.homebrew)
        self.assertTrue(started["data"]["port"] > 0)

        # The library UI is present and the switch capability was detected.
        self.assertTrue(self.wait_ui("game-grid")["ok"])

        # Import through the real picker control.
        self.ui_click("choose-rom")
        self.assertTrue(self.wait_ui("switch-game-card")["ok"], "the Switch card did not appear")

        card = self.ui_query("switch-game-card")
        self.assertIn("Nintendo Switch", card["data"]["node"]["text"])

        # Launch through the card's own control (not a direct command).
        self.ui_click("switch-launch")
        running = self.wait_ui("switch-status", state="running", timeout=120)
        self.assertTrue(running["ok"], "the UI never reported the companion as running")
        self.assertTrue(self.companions(), "no companion process was started")

        # Focus and stop through the UI.
        self.ui_click("switch-focus")
        self.ui_click("switch-stop")
        self.assertTrue(self.wait_ui("switch-status", state="stopped", timeout=30)["ok"])
        for _ in range(20):
            if not self.companions():
                break
            time.sleep(0.5)
        self.assertFalse(self.companions(), "the companion did not stop through the UI")

        # Relaunch creates a valid new companion and is stoppable again.
        self.ui_click("switch-launch")
        self.assertTrue(self.wait_ui("switch-status", state="running", timeout=120)["ok"])
        self.ui_click("switch-stop")

        # Closing the app must not leave an orphan companion.
        self.app_stop()
        deadline = time.time() + 15
        while time.time() < deadline and self.companions():
            time.sleep(0.5)
        self.assertFalse(self.companions(), "closing the app left an orphan companion")


if __name__ == "__main__":
    unittest.main()
