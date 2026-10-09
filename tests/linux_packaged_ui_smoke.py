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
            [str(AN3CTL), *args, "--target", "linux", "--control-file", str(self.control), "--json"],
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
        last_error = None
        while time.monotonic() < deadline:
            if self.app.poll() is not None:
                self.fail(f"VCE shell exited with {self.app.returncode}; see {self.evidence / 'app.log'}")
            if self.control.exists():
                try:
                    last = self.an3ctl("ui", "query", "--testid", testid).get("node")
                    if predicate(last):
                        return last
                except (AssertionError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
                    last_error = str(error)
            time.sleep(0.4)
        details = {"testid": testid, "last_node": last, "last_error": last_error}
        try:
            details["tree"] = self.an3ctl("ui", "tree").get("nodes")
        except (AssertionError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
            details["tree_error"] = str(error)
        details["control_file_present"] = self.control.is_file()
        (self.evidence / "ui-timeout.json").write_text(
            json.dumps(details, indent=2) + "\n", encoding="utf-8"
        )
        self.fail(f"timed out waiting for {testid}; diagnostic details: {details}")

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

    @staticmethod
    def game_window(executable):
        player_pid = None
        for cmdline in Path("/proc").glob("[0-9]*/cmdline"):
            try:
                if str(executable) in cmdline.read_bytes().replace(b"\0", b" ").decode(errors="ignore"):
                    player_pid = int(cmdline.parent.name)
                    break
            except (OSError, ValueError):
                continue
        if player_pid is None:
            return None
        result = subprocess.run(
            ["xdotool", "search", "--onlyvisible", "--pid", str(player_pid)],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            return None
        for window in result.stdout.split():
            title = subprocess.run(
                ["xdotool", "getwindowname", window],
                text=True,
                capture_output=True,
                check=False,
            )
            if title.returncode == 0 and title.stdout.strip() == "VibeCodedEmulator":
                return window
        return None

    def capture_game_window(self, window, name):
        from PIL import Image

        path = self.evidence / name
        subprocess.run(["xdotool", "windowactivate", "--sync", window], check=True, timeout=10)
        time.sleep(0.4)
        subprocess.run(["scrot", "-u", "-o", str(path)], check=True, timeout=10)
        with Image.open(path) as image:
            width, height = image.size
            rgb = image.convert("RGB")
            crop = rgb.crop((width // 4, height // 4, width * 3 // 4, height * 3 // 4))
            pixels = list(crop.getdata())
        red = sum(r > 150 and r > b * 1.5 for r, g, b in pixels)
        blue = sum(b > 150 and b > r * 1.5 for r, g, b in pixels)
        return {"path": str(path), "width": width, "height": height,
                "redPixels": red, "bluePixels": blue, "samplePixels": len(pixels)}

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
            lambda item: bool(item and item.get("state") == "running"),
        )
        self.assertEqual(status.get("state"), "running")

        # Capture the actual SDL game window. The fixture fills the frame blue
        # without input and red/green while A is held, so X11 pixels prove both
        # presentation and the native keyboard path.
        player = self.package_root / "usr/lib/VibeCodedEmulator/runtime/linux-x86_64/an3-offline-native"
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not self.process_running(player):
            time.sleep(0.25)
        self.assertTrue(self.process_running(player), f"packaged Linux player did not start: {player}")

        deadline = time.monotonic() + 20
        game_window = None
        while time.monotonic() < deadline and game_window is None:
            game_window = self.game_window(player)
            time.sleep(0.25)
        self.assertIsNotNone(game_window, "packaged Linux game window was not visible under Xvfb")
        idle_frame = self.capture_game_window(game_window, "game-window-idle.png")
        self.assertGreater(idle_frame["bluePixels"], idle_frame["samplePixels"] * 0.75,
                           f"idle game window did not show the fixture's blue frame: {idle_frame}")
        subprocess.run(["xdotool", "keydown", "z"], check=True, timeout=10)
        try:
            time.sleep(0.4)
            input_frame = self.capture_game_window(game_window, "game-window-a-pressed.png")
        finally:
            subprocess.run(["xdotool", "keyup", "z"], check=False, timeout=10)
        self.assertGreater(input_frame["redPixels"], input_frame["samplePixels"] * 0.75,
                           f"visible game window did not show the A-pressed fixture frame: {input_frame}")

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
            "visible_frame_verified": True,
            "idle_frame": idle_frame,
            "a_pressed_frame": input_frame,
        }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main(verbosity=2)
