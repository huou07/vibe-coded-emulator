# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hosted Linux smoke for the shell and resources from one exact DEB."""

from pathlib import Path
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
AN3CTL = ROOT / "tools/an3ctl/bin/an3ctl"
PORT = 38471


class LinuxPackagedUiSmoke(unittest.TestCase):
    def setUp(self):
        package_root = os.environ.get("AN3_LINUX_PACKAGE_ROOT")
        automation_binary = os.environ.get("AN3_LINUX_AUTOMATION_BINARY")
        fixture = os.environ.get("AN3_LINUX_GBA_FIXTURE")
        evidence = os.environ.get("AN3_LINUX_UI_EVIDENCE_DIR")
        if not all((package_root, automation_binary, fixture, evidence)):
            self.skipTest("hosted Linux package smoke inputs are not configured")

        self.package_root = Path(package_root).resolve()
        self.fixture = Path(fixture).resolve()
        self.evidence = Path(evidence).resolve()
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.home = Path(tempfile.mkdtemp(prefix="an3-linux-ui-home-"))
        self.control = self.home / "linux-ui-control.json"
        self.binary = Path(automation_binary).resolve()
        candidates = sorted({
            path.resolve() for path in (self.package_root / "usr").rglob("an3-offline-native")
            if path.is_file() and "runtime/linux-" not in path.as_posix()
        })
        if len(candidates) != 1:
            self.fail(f"expected one packaged VCE shell executable, found: {candidates}")
        self.shell_binary = candidates[0]
        shutil.copy2(self.binary, self.shell_binary)

        probe = socket.socket()
        try:
            probe.bind(("127.0.0.1", PORT))
        except OSError as error:
            self.fail(f"Linux UI-control port {PORT} is unavailable: {error}")
        finally:
            probe.close()

        env = os.environ.copy()
        env.update({
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_DATA_HOME": str(self.home / ".local/share"),
            "XDG_CACHE_HOME": str(self.home / ".cache"),
            "AN3_UI_CONTROL_FILE": str(self.control),
            "AN3_UI_TEST_ROM": str(self.fixture),
            "SDL_AUDIODRIVER": "dummy",
            "LIBGL_ALWAYS_SOFTWARE": "1",
            "GDK_BACKEND": "x11",
        })
        self.app_log = (self.evidence / "app.log").open("w", encoding="utf-8")
        self.app = subprocess.Popen(
            [str(self.shell_binary)],
            cwd=self.shell_binary.parent,
            env=env,
            stdout=self.app_log,
            stderr=subprocess.STDOUT,
        )
        self.env = env
        self.addCleanup(self.stop_app)

    def stop_app(self):
        app = getattr(self, "app", None)
        if app is not None and app.poll() is None:
            app.terminate()
            try:
                app.wait(timeout=8)
            except subprocess.TimeoutExpired:
                app.kill()
                app.wait(timeout=5)
        log = getattr(self, "app_log", None)
        if log is not None and not log.closed:
            log.close()

    def an3ctl(self, *args):
        result = subprocess.run(
            [str(AN3CTL), *args, "--target", "linux", "--control-file", str(self.control)],
            env={**self.env, "AN3_LINUX_UI_CONTROL_FILE": str(self.control)},
            text=True,
            capture_output=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, f"an3ctl failed: {result.stdout}\n{result.stderr}")
        payload = json.loads(result.stdout)
        self.assertTrue(payload.get("ok"), payload)
        return payload["data"]

    def wait_node(self, testid, predicate, timeout=60):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            if self.app.poll() is not None:
                self.fail(f"VCE shell exited with {self.app.returncode}; see {self.evidence / 'app.log'}")
            if self.control.exists():
                try:
                    last = self.an3ctl("ui", "query", "--testid", testid).get("node")
                    if predicate(last):
                        return last
                except (AssertionError, json.JSONDecodeError, subprocess.TimeoutExpired):
                    pass
            time.sleep(0.4)
        self.fail(f"timed out waiting for {testid}; last DOM node: {last}")

    def click_visible(self, testid):
        node = self.wait_node(testid, lambda item: bool(item and item.get("visible") and not item.get("disabled")))
        self.assertTrue(node["visible"])
        self.assertFalse(node["disabled"])
        return self.an3ctl("ui", "click", "--testid", testid)

    @staticmethod
    def process_running(executable):
        for cmdline in Path("/proc").glob("[0-9]*/cmdline"):
            try:
                if str(executable) in cmdline.read_bytes().replace(b"\0", b" ").decode(errors="ignore"):
                    return True
            except OSError:
                continue
        return False

    def test_import_launch_and_return_use_the_packaged_linux_shell(self):
        play = self.wait_node("open-rom", lambda item: bool(item and item.get("visible") and not item.get("disabled")))
        self.assertIsNotNone(play)
        self.click_visible("open-rom")

        grid = self.wait_node("game-grid", lambda item: bool(item and item.get("visible")))
        self.assertIsNotNone(grid)
        card = self.wait_node("game-card", lambda item: bool(item and item.get("visible")))
        self.assertIn("AN3TAPTEST", card.get("text", "").upper())

        self.click_visible("game-launch")
        status = self.wait_node(
            "native-status",
            lambda item: bool(item and item.get("visible") and item.get("state") == "running"),
        )
        self.assertEqual(status.get("state"), "running")

        # Confirm that the installed package's bundled Linux player process was
        # started; the UI bridge itself does not expose presented-frame data.
        player = self.package_root / "usr/lib/VibeCodedEmulator/runtime/linux-x86_64/an3-offline-native"
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not self.process_running(player):
            time.sleep(0.25)
        self.assertTrue(self.process_running(player), f"packaged Linux player did not start: {player}")

        self.click_visible("native-session-return")
        self.wait_node("open-rom", lambda item: bool(item and item.get("visible")), timeout=30)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and self.process_running(player):
            time.sleep(0.25)
        self.assertFalse(self.process_running(player), "Return to Library left the packaged Linux player running")
        (self.evidence / "result.json").write_text(json.dumps({
            "shell": str(self.shell_binary),
            "player": str(player),
            "fixture": str(self.fixture),
            "journey": ["Play visible", "fixture imported", "player launched", "returned to Library"],
            "presented_frame_verified": False,
        }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main(verbosity=2)
