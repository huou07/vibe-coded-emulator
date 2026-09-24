# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Guard: the test-only macOS ``ui-control`` automation app.

The distribution ``VibeCodedEmulator.app`` deliberately does not compile the
structured UI bridge. An3ctl-driven packaged E2E instead uses a *separate*
automation bundle produced by
``native-offline/scripts/build-macos-automation.sh`` (``npm run
build:macos-automation``). This guard keeps that separation honest:

* the automation binary exposes the bridge and is validly code-signed;
* the distribution binary must NOT expose the bridge;
* launching the automation bundle in a throwaway copy with an isolated ``HOME``
  and a unique bundle identifier serves the library UI through an3ctl while the
  owner's real library stays invisible.

The runtime bridge requires the default loopback runtime port: the shipped
capability grants IPC only to ``http://127.0.0.1:38471/*``, so any other
``AN3_NATIVE_RUNTIME_PORT`` leaves the page without ``window.__TAURI__`` and the
bridge can never receive a DOM result. The test therefore skips (rather than
fails) when that port is already taken by another instance.

The test never imports or launches a ROM, and it never touches the owner's
library, saves or settings.
"""

from __future__ import annotations

import json
import os
import platform
import plistlib
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AN3CTL = ROOT / "tools/an3ctl/bin/an3ctl"
TAURI_CONF = ROOT / "native-offline/src-tauri/tauri.conf.json"
BUNDLE_DIR = ROOT / "native-offline/src-tauri/target/release/bundle/macos"
AUTOMATION_APP = Path(
    os.environ.get("AN3_MACOS_AUTOMATION_APP", str(BUNDLE_DIR / "VibeCodedEmulatorAutomation.app"))
)
DISTRIBUTION_APP = BUNDLE_DIR / "VibeCodedEmulator.app"
BRIDGE_MARKER = b"AN3_UI_CONTROL_FILE"
BRIDGE_TIMEOUT_SECONDS = 60
# The capability in native-offline/src-tauri/capabilities/default.json grants
# WebView IPC only to this loopback origin, so the bridge cannot work on another
# runtime port.
RUNTIME_PORT = 38471


def desktop_version() -> str:
    return json.loads(TAURI_CONF.read_text(encoding="utf-8"))["version"]


def _binary(bundle: Path) -> Path:
    return bundle / "Contents/MacOS/an3-offline-native"


def _require_macos(testcase: unittest.TestCase) -> None:
    if platform.system() != "Darwin":
        testcase.skipTest("macOS automation QA requires Darwin")


def _require_automation_app(testcase: unittest.TestCase) -> None:
    _require_macos(testcase)
    if not _binary(AUTOMATION_APP).is_file():
        testcase.skipTest(
            "the macOS automation app has not been built "
            "(npm run build:macos-automation)"
        )


def _runtime_port_free() -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind(("127.0.0.1", RUNTIME_PORT))
    except OSError:
        return False
    finally:
        probe.close()
    return True


class MacosAutomationAppTests(unittest.TestCase):
    def _stop(self, app: Path) -> None:
        subprocess.run(["pkill", "-f", str(app)], capture_output=True)
        for _ in range(20):
            probe = subprocess.run(["pgrep", "-f", str(app)], capture_output=True, text=True)
            if not probe.stdout.strip():
                return
            time.sleep(0.25)

    def _an3ctl(self, *args, check=True):
        result = subprocess.run(
            ["bash", str(AN3CTL), *args, "--json"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        try:
            payload = json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {"ok": False, "raw": result.stdout, "stderr": result.stderr}
        if check and not payload.get("ok"):
            self.fail(f"an3ctl {' '.join(args)} failed: {payload} (stderr: {result.stderr[-300:]})")
        return payload

    def test_10_automation_bundle_exposes_bridge_and_is_signed(self):
        _require_automation_app(self)
        binary = _binary(AUTOMATION_APP)
        self.assertIn(
            BRIDGE_MARKER,
            binary.read_bytes(),
            "the automation binary does not expose the ui-control bridge",
        )
        distribution = _binary(DISTRIBUTION_APP)
        if distribution.is_file():
            self.assertNotIn(
                BRIDGE_MARKER,
                distribution.read_bytes(),
                "the distribution app must never compile the test-only ui-control bridge",
            )
        signature = subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(AUTOMATION_APP)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(signature.returncode, 0, signature.stderr)
        info = plistlib.loads((AUTOMATION_APP / "Contents/Info.plist").read_bytes())
        self.assertEqual(info.get("CFBundleShortVersionString"), desktop_version())
        self.assertEqual(info.get("CFBundleVersion"), desktop_version())

    def test_20_automation_bridge_serves_isolated_library(self):
        _require_automation_app(self)
        if not AN3CTL.is_file():
            self.skipTest("an3ctl launcher is unavailable")
        if shutil.which("node") is None:
            self.skipTest("node is required to drive an3ctl")
        if not _runtime_port_free():
            self.skipTest(
                f"runtime port {RUNTIME_PORT} is already in use; "
                "close any running Vibe Coded Emulator instance first"
            )

        tmp = Path(tempfile.mkdtemp(prefix="an3-macos-automation-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        home = tmp / "home"
        home.mkdir()
        control = tmp / "ui-control.json"
        app = tmp / "An3AutomationUITest.app"
        shutil.copytree(AUTOMATION_APP, app, symlinks=True)
        self.addCleanup(self._stop, app)

        # A unique bundle id gives the copy its own WebKit data store, so the
        # owner's real library (keyed by the distribution bundle id) is invisible.
        subprocess.run(
            [
                "/usr/libexec/PlistBuddy",
                "-c",
                f"Set :CFBundleIdentifier space.an3tocom.offline.autotest{os.getpid()}",
                str(app / "Contents/Info.plist"),
            ],
            check=True,
        )
        subprocess.run(
            ["codesign", "--force", "--deep", "--sign", "-", str(app)],
            check=True,
            capture_output=True,
        )

        subprocess.run(
            [
                "open",
                "-n",
                str(app),
                "--stdout",
                str(tmp / "app.out"),
                "--stderr",
                str(tmp / "app.err"),
                "--env",
                f"HOME={home}",
                "--env",
                f"AN3_UI_CONTROL_FILE={control}",
            ],
            check=True,
        )

        deadline = time.time() + BRIDGE_TIMEOUT_SECONDS
        while time.time() < deadline and not control.is_file():
            time.sleep(0.5)
        self.assertTrue(control.is_file(), "the automation bridge never wrote its control file")

        # The WebView answers /tree as soon as it exists, but the library page may
        # still be loading; keep polling until the packaged UI has rendered.
        nodes = None
        deadline = time.time() + BRIDGE_TIMEOUT_SECONDS
        while time.time() < deadline:
            payload = self._an3ctl(
                "ui", "tree", "--target", "macos", "--control-file", str(control), "--limit", "40",
                check=False,
            )
            if payload.get("ok"):
                candidate = payload["data"]["nodes"]
                if any(node.get("testid") == "open-rom" for node in candidate):
                    nodes = candidate
                    break
            time.sleep(1.0)
        self.assertIsNotNone(nodes, "the packaged library UI never rendered through the bridge")

        testids = {node.get("testid") for node in nodes}
        self.assertIn("open-rom", testids, "the packaged library UI did not render through the bridge")
        self.assertIn("game-grid", testids)
        self.assertNotIn(
            "game-card",
            testids,
            "the isolated automation instance exposed a populated library",
        )
        serialized = json.dumps(nodes)
        for owner_title in ("Pokemon", "Emerald", "Metal Slug"):
            self.assertNotIn(
                owner_title,
                serialized,
                f"the automation instance leaked the owner's library ({owner_title})",
            )

        self._stop(app)
        remaining = subprocess.run(["pgrep", "-f", str(app)], capture_output=True, text=True)
        self.assertEqual(remaining.stdout.strip(), "", "closing the automation app left an orphan process")


if __name__ == "__main__":
    unittest.main()
