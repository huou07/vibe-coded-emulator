# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Packaged-app Switch UI E2E (macOS).

Drives the **real packaged application** through `an3ctl ui --target macos`,
which dispatches real DOM events on the app's own controls. The import button,
the Switch game card and its launch/focus/stop controls are the actual frontend
handlers a user clicks — this test never calls a Tauri command directly.

Requires an app built with the test-only `ui-control` cargo feature and a legal
homebrew fixture; skips otherwise. Uses an isolated HOME and a throwaway install
copy so the owner's library, saves and settings are never touched.
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
AN3CTL = ROOT / "tools/an3ctl/bin/an3ctl"
APP = ROOT / "native-offline/src-tauri/target/release/bundle/macos/VibeCodedEmulator.app"
HOMEBREW_CANDIDATES = [os.environ.get("AN3_SWITCH_HOMEBREW", ""), "/tmp/an3-switch/hbmenu.nro", "/tmp/hbmenu.nro"]
TEST_BUNDLE_ID = "space.an3tocom.offline.uitest"


def _homebrew():
    for raw in HOMEBREW_CANDIDATES:
        if raw and Path(raw).exists():
            return Path(raw)
    return None


class SwitchPackagedUiE2ETests(unittest.TestCase):
    def setUp(self):
        if not APP.exists():
            self.skipTest("the macOS app bundle has not been built")
        companion = APP / "Contents/Resources/switch/macos-arm64/an3_switch_companion"
        if not companion.exists():
            self.skipTest("the app bundle does not contain the Switch companion")
        self.homebrew = _homebrew()
        if self.homebrew is None:
            self.skipTest("no legal homebrew fixture (set AN3_SWITCH_HOMEBREW)")
        binary = APP / "Contents/MacOS/an3-offline-native"
        if b"AN3_UI_CONTROL_FILE" not in binary.read_bytes():
            self.skipTest("the app was not built with --features ui-control")

        self.tmp = Path(tempfile.mkdtemp(prefix="an3-ui-e2e-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.control = self.tmp / "ui-control.json"
        self.install = self.tmp / "install"
        self.install.mkdir()
        self.app = self.install / "AN3SwitchUITest.app"
        shutil.copytree(APP, self.app, symlinks=True)
        subprocess.run(
            ["/usr/libexec/PlistBuddy", "-c", f"Set :CFBundleIdentifier {TEST_BUNDLE_ID}",
             str(self.app / "Contents/Info.plist")],
            check=True,
        )
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(self.app)],
                       check=True, capture_output=True)
        self.addCleanup(self._teardown)

    def _teardown(self):
        subprocess.run(["pkill", "-f", str(self.app)], capture_output=True)
        subprocess.run(["pkill", "-f", "an3_switch_companion"], capture_output=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def an3ctl(self, *args, check=True):
        result = subprocess.run(
            ["bash", str(AN3CTL), *args, "--json"],
            capture_output=True, text=True, cwd=ROOT,
        )
        try:
            payload = json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {"ok": False, "raw": result.stdout, "stderr": result.stderr}
        if check and not payload.get("ok"):
            self.fail(f"an3ctl {' '.join(args)} failed: {payload} (stderr: {result.stderr[-300:]})")
        return payload

    def wait_ui(self, testid, state=None, timeout=90):
        args = ["ui", "wait", "--target", "macos", "--testid", testid,
                "--control-file", str(self.control), "--timeout", str(timeout * 1000)]
        if state:
            args += ["--state", state]
        return self.an3ctl(*args, check=False)

    def companions(self):
        result = subprocess.run(["pgrep", "-f", "an3_switch_companion"], capture_output=True, text=True)
        return [line for line in result.stdout.split() if line.strip()]

    def test_70_packaged_switch_ui_full_workflow(self):
        started = self.an3ctl(
            "app", "start", "--target", "macos",
            "--app", str(self.app),
            "--rom", str(self.homebrew),
            "--home", str(self.home),
            "--control-file", str(self.control),
        )
        self.assertTrue(started["data"]["port"] > 0)

        # The library UI is present and the switch capability was detected.
        self.assertTrue(self.wait_ui("game-grid")["ok"])

        # Import through the real picker control.
        self.an3ctl("ui", "click", "--target", "macos", "--testid", "choose-rom",
                    "--control-file", str(self.control))
        self.assertTrue(self.wait_ui("switch-game-card")["ok"], "the Switch card did not appear")

        card = self.an3ctl("ui", "query", "--target", "macos", "--testid", "switch-game-card",
                           "--control-file", str(self.control))
        self.assertIn("Nintendo Switch", card["data"]["node"]["text"])

        # Launch through the card's own control (not a direct command).
        self.an3ctl("ui", "click", "--target", "macos", "--testid", "switch-launch",
                    "--control-file", str(self.control))
        running = self.wait_ui("switch-status", state="running", timeout=120)
        self.assertTrue(running["ok"], "the UI never reported the companion as running")
        self.assertTrue(self.companions(), "no companion process was started")

        # Focus and stop through the UI.
        self.an3ctl("ui", "click", "--target", "macos", "--testid", "switch-focus",
                    "--control-file", str(self.control))
        self.an3ctl("ui", "click", "--target", "macos", "--testid", "switch-stop",
                    "--control-file", str(self.control))
        self.assertTrue(self.wait_ui("switch-status", state="stopped", timeout=30)["ok"])
        for _ in range(20):
            if not self.companions():
                break
            time.sleep(0.5)
        self.assertFalse(self.companions(), "the companion did not stop through the UI")

        # Relaunch creates a valid new companion and is stoppable again.
        self.an3ctl("ui", "click", "--target", "macos", "--testid", "switch-launch",
                    "--control-file", str(self.control))
        self.assertTrue(self.wait_ui("switch-status", state="running", timeout=120)["ok"])
        self.an3ctl("ui", "click", "--target", "macos", "--testid", "switch-stop",
                    "--control-file", str(self.control))

        # Closing the app must not leave an orphan companion.
        self.an3ctl("app", "stop", "--target", "macos", "--app", str(self.app))
        time.sleep(3)
        self.assertFalse(self.companions(), "closing the app left an orphan companion")


if __name__ == "__main__":
    unittest.main()
