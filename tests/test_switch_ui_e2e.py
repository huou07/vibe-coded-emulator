# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Packaged-app Switch UI E2E (macOS).

Drives the **real packaged application** through `an3ctl ui --target macos`,
which dispatches DOM events on the app's own controls. It checks that the
library starts empty and requires visible, enabled Open ROM and Switch
launch/focus/stop controls — this test never calls a Tauri command directly.

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

        # Check the isolated library before using any import action.
        empty_library = self.ui_query("switch-game-card")["data"]["node"]
        self.assertIsNone(empty_library, "the isolated test HOME must not expose a Switch entry")

        # Open ROM is the visible Play-page action and routes into Library.
        self.ui_click_visible("open-rom")
        grid = self.ui_query("game-grid")["data"]["node"]
        self.assertIsNotNone(grid, "the Library game grid is missing")
        self.assertTrue(grid["visible"], f"the Library game grid is hidden: {grid}")

        # The test-only picker answer still exercises the normal import path.
        card_wait = self.wait_ui("switch-game-card")
        self.assertTrue(card_wait["ok"], "the Switch card did not appear")

        card = self.ui_query("switch-game-card")
        self.assertTrue(card["data"]["node"]["visible"], "the Switch card is hidden")
        self.assertIn("Nintendo Switch".casefold(), card["data"]["node"]["text"].casefold())

        # Launch through the card's own control (not a direct command).
        self.ui_click_visible("switch-launch")
        running = self.wait_ui("switch-status", state="running", timeout=120)
        self.assertTrue(running["ok"], "the UI never reported the companion as running")
        status = self.ui_query("switch-status")["data"]["node"]
        self.assertTrue(status["visible"], "the Switch status is hidden")
        self.assertTrue(self.companions(), "no companion process was started")

        # Focus and stop through the UI.
        self.ui_click_visible("switch-focus")
        self.ui_click_visible("switch-stop")
        stopped = self.wait_ui("switch-status", state="stopped", timeout=30)
        self.assertTrue(stopped["ok"])
        status = self.ui_query("switch-status")["data"]["node"]
        self.assertTrue(status["visible"], "the stopped Switch status is hidden")
        for _ in range(20):
            if not self.companions():
                break
            time.sleep(0.5)
        self.assertFalse(self.companions(), "the companion did not stop through the UI")

        # Relaunch creates a valid new companion and is stoppable again.
        self.ui_click_visible("switch-launch")
        self.assertTrue(self.wait_ui("switch-status", state="running", timeout=120)["ok"])
        self.ui_click_visible("switch-stop")

        # Closing the app must not leave an orphan companion.
        self.app_stop()
        deadline = time.time() + 15
        while time.time() < deadline and self.companions():
            time.sleep(0.5)
        self.assertFalse(self.companions(), "closing the app left an orphan companion")


if __name__ == "__main__":
    unittest.main()
