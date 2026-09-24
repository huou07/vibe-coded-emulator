# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Packaged macOS app + DMG runtime QA.

This is the packaged-runtime guard for the macOS desktop product. It verifies
the built ``VibeCodedEmulator.app`` is the canonical desktop version and passes
code-signature verification, that the distribution DMG mounts and contains that
same signed app, and that launching the packaged app with an isolated ``HOME``
stays alive without a fatal error.

The DMG binary is gitignored and never shipped in the repo, so the DMG test
skips explicitly when the artifact has not been built. The tests never touch the
owner's real library, saves or settings.
"""

from __future__ import annotations

import json
import os
import platform
import plistlib
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAURI_CONF = ROOT / "native-offline/src-tauri/tauri.conf.json"
APP = ROOT / "native-offline/src-tauri/target/release/bundle/macos/VibeCodedEmulator.app"
RELEASES = ROOT / "native-offline/releases"
APP_BINARY = APP / "Contents/MacOS/an3-offline-native"

# Give the packaged WebView/AppKit shell time to initialize before the liveness
# assertion; the 2.2.0 release QA used the same "launch and stays alive" check.
LIVENESS_SECONDS = 10


def desktop_version() -> str:
    return json.loads(TAURI_CONF.read_text(encoding="utf-8"))["version"]


def dmg_path() -> Path:
    return RELEASES / f"vibecodedemulator-{desktop_version()}-macos-aarch64.dmg"


def _require_macos(testcase: unittest.TestCase) -> None:
    if platform.system() != "Darwin":
        testcase.skipTest("packaged macOS runtime QA requires Darwin")


def _codesign_ok(testcase: unittest.TestCase, bundle: Path) -> None:
    result = subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(bundle)],
        capture_output=True,
        text=True,
    )
    testcase.assertEqual(
        result.returncode,
        0,
        f"code-signature verification failed for {bundle}: {result.stderr.strip()}",
    )


def _attach(dmg: Path):
    """Mount the DMG read-only and return (dev_entry, mount_point)."""
    result = subprocess.run(
        ["hdiutil", "attach", "-nobrowse", "-readonly", "-plist", str(dmg)],
        capture_output=True,
    )
    if result.returncode != 0:
        raise AssertionError(f"hdiutil attach failed: {result.stderr.decode(errors='replace')}")
    info = plistlib.loads(result.stdout)
    for entity in info.get("system-entities", []):
        mount_point = entity.get("mount-point")
        if mount_point:
            return entity.get("dev-entry"), Path(mount_point)
    raise AssertionError("the DMG attached but exposed no mount point")


class MacosPackagedRuntimeTests(unittest.TestCase):
    def setUp(self):
        _require_macos(self)

    def test_10_built_app_is_the_canonical_version_and_signed(self):
        if not APP.is_dir():
            self.skipTest("the macOS app bundle has not been built")
        info = plistlib.loads((APP / "Contents/Info.plist").read_bytes())
        version = desktop_version()
        self.assertEqual(info["CFBundleShortVersionString"], version)
        self.assertEqual(info["CFBundleVersion"], version)
        self.assertEqual(info["CFBundleIdentifier"], "space.an3tocom.offline")
        for asset in ("LICENSE", "THIRD_PARTY_NOTICES.md", "azahar", "libretro", "switch"):
            self.assertTrue((APP / "Contents/Resources" / asset).exists(), f"missing bundled resource: {asset}")
        _codesign_ok(self, APP)

    def test_20_dmg_mounts_and_contains_the_signed_app(self):
        dmg = dmg_path()
        if not dmg.is_file():
            self.skipTest(f"the macOS DMG has not been built: {dmg}")
        dev_entry, mount_point = _attach(dmg)
        try:
            mounted_app = mount_point / "VibeCodedEmulator.app"
            self.assertTrue(mounted_app.is_dir(), "the DMG does not contain VibeCodedEmulator.app")
            info = plistlib.loads((mounted_app / "Contents/Info.plist").read_bytes())
            version = desktop_version()
            self.assertEqual(info["CFBundleShortVersionString"], version)
            self.assertEqual(info["CFBundleVersion"], version)
            _codesign_ok(self, mounted_app)
        finally:
            subprocess.run(["hdiutil", "detach", dev_entry], capture_output=True)

    def test_21_dmg_offers_the_applications_install_target(self):
        # The drag-to-install UX requires the mounted volume to contain an
        # Applications target that resolves to /Applications. A DMG built with
        # `hdiutil create -srcfolder <app>` alone silently omits it, so this
        # guard fails a release whose installer has no install destination.
        dmg = dmg_path()
        if not dmg.is_file():
            self.skipTest(f"the macOS DMG has not been built: {dmg}")
        dev_entry, mount_point = _attach(dmg)
        try:
            self.assertTrue(
                (mount_point / "VibeCodedEmulator.app").is_dir(),
                "the DMG does not contain VibeCodedEmulator.app",
            )
            applications = mount_point / "Applications"
            self.assertTrue(
                applications.is_symlink(),
                "the DMG must contain an Applications symlink for drag-to-install",
            )
            self.assertEqual(
                os.readlink(applications),
                "/Applications",
                "the Applications target must resolve to /Applications",
            )
        finally:
            subprocess.run(["hdiutil", "detach", dev_entry], capture_output=True)

    def test_30_packaged_app_launches_and_stays_alive(self):
        if not APP_BINARY.is_file():
            self.skipTest("the macOS app bundle has not been built")
        if not os.access(APP_BINARY, os.X_OK):
            self.skipTest("the packaged app binary is not executable")
        tmp = Path(tempfile.mkdtemp(prefix="an3-macos-runtime-"))
        home = tmp / "home"
        home.mkdir()
        process = None
        try:
            env = dict(os.environ)
            # Isolate the packaged app from the owner's real library/saves.
            env["HOME"] = str(home)
            process = subprocess.Popen(
                [str(APP_BINARY)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            deadline = time.time() + LIVENESS_SECONDS
            while time.time() < deadline:
                if process.poll() is not None:
                    break
                time.sleep(0.5)
            exit_code = process.poll()
            if exit_code is not None:
                stderr = process.stderr.read() if process.stderr else ""
                self.fail(f"the packaged app exited during startup (code {exit_code}); stderr:\n{stderr}")
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            for stream in (process.stdout, process.stderr) if process is not None else ():
                if stream is not None:
                    stream.close()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
