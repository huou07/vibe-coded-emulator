# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Smoke-test the exact Windows package's Azahar core in its visible window."""

from pathlib import Path
import ctypes
import hashlib
import json
import os
import queue
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest

from PIL import Image, ImageChops, ImageGrab


FIXTURE_SHA256 = "a9fac712e9a6e937ec3d3d3228d8031d94030f3bec3462d9048897f3be638050"
FIXTURE_COMMIT = "e5b13872f0c1207cb9c86e18e710c8f1fa269fb8"
WINDOW_TITLE = "VibeCodedEmulator"


class Rect(ctypes.Structure):
    _fields_ = [(name, ctypes.c_long) for name in ("left", "top", "right", "bottom")]


class Point(ctypes.Structure):
    _fields_ = [(name, ctypes.c_long) for name in ("x", "y")]


def capture_client(hwnd, path):
    rect = Rect()
    if not ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("Could not read the native player client rectangle.")
    top_left, bottom_right = Point(rect.left, rect.top), Point(rect.right, rect.bottom)
    if not ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(top_left)):
        raise RuntimeError("Could not locate the native player client rectangle.")
    if not ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(bottom_right)):
        raise RuntimeError("Could not locate the native player client rectangle.")
    box = (top_left.x, top_left.y, bottom_right.x, bottom_right.y)
    if box[2] <= box[0] or box[3] <= box[1]:
        raise RuntimeError(f"Native player client area is empty: {box}")
    image = ImageGrab.grab(bbox=box).convert("RGB")
    image.save(path)
    return image


def game_area(image):
    # A maximized Windows runner can leave the taskbar over the window. Exclude
    # its bottom strip so desktop chrome cannot make a blank render look valid.
    return image.crop((0, 0, image.width, max(1, image.height - 48)))


def wait_for_output(lines, prefix, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            line = lines.get(timeout=min(0.25, deadline - time.monotonic()))
        except queue.Empty:
            continue
        if prefix in line:
            return line
    raise TimeoutError(f"Native player did not acknowledge {prefix}.")


class WindowsPackaged3DSSmoke(unittest.TestCase):
    def test_exact_windows_package_azahar_visible_frame_and_a_input(self):
        runner_temp = Path(os.environ["RUNNER_TEMP"])
        evidence = runner_temp / "vce-windows-3ds-smoke"
        install_dir = runner_temp / "vce-windows-3ds-installed"
        storage = runner_temp / "vce-windows-3ds-storage"
        fixture_root = Path(os.environ["FIXTURE_ROOT"])
        fixture = fixture_root / "3DS-TEST.3dsx"
        evidence.mkdir(parents=True, exist_ok=True)

        expected_sha = os.environ["EXPECTED_SOURCE_SHA"]
        self.assertRegex(expected_sha, r"^[0-9a-fA-F]{40}$")
        artifact_dir = Path("artifacts/windows")
        labels = (artifact_dir / "BUILD_LABELS.txt").read_text(encoding="utf-8")
        self.assertRegex(labels, rf"Source revision:\s*{expected_sha}\b")
        installer = next(artifact_dir.glob("*.exe"))
        sidecar = installer.with_suffix(installer.suffix + ".sha256").read_text(encoding="utf-8").strip()
        expected_installer_hash, sidecar_name = sidecar.split(maxsplit=1)
        self.assertEqual(Path(sidecar_name.lstrip("* ")).name, installer.name)
        installer_hash = hashlib.sha256(installer.read_bytes()).hexdigest()
        self.assertEqual(installer_hash, expected_installer_hash.lower())
        self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(), FIXTURE_SHA256)
        self.assertIn("MIT License", (fixture_root / "LICENSE").read_text(encoding="utf-8"))

        install = subprocess.run(
            [str(installer.resolve()), "/S", f"/D={install_dir}"],
            capture_output=True, text=True, timeout=180,
        )
        self.assertEqual(install.returncode, 0, f"silent install failed: {install.stdout}\n{install.stderr}")
        close_script = (
            "$root = $env:AN3_TEST_INSTALL_DIR; "
            "Get-CimInstance Win32_Process -Filter \"Name = 'an3-offline-native.exe'\" | "
            "Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($root, "
            "[StringComparison]::OrdinalIgnoreCase) } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        install_env = os.environ.copy()
        install_env["AN3_TEST_INSTALL_DIR"] = str(install_dir.resolve())
        subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-Command", close_script],
                       env=install_env, check=True, capture_output=True, text=True, timeout=20)
        player = install_dir / "runtime" / "windows-x64" / "an3-native-runtime.exe"
        libdir = player.parent / "libretro"
        core = libdir / "azahar_libretro.dll"
        self.assertTrue(player.is_file(), "installed player is missing")
        self.assertTrue(core.is_file(), "installed Azahar core is missing")
        with socket.socket() as probe:
            self.assertNotEqual(probe.connect_ex(("127.0.0.1", 38471)), 0,
                                "installer left the shell's loopback port occupied")

        sd_game = storage / "saves" / "native-libretro" / "Azahar" / "sdmc" / "game"
        sd_game.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(fixture_root / "game", sd_game)
        env = os.environ.copy()
        env.update({"AN3_OFFLINE_LIBDIR": str(libdir), "SDL_AUDIODRIVER": "dummy"})
        log_path = evidence / "player.log"
        command = [str(player), "--rom", str(fixture), "--system", "3ds",
                   "--renderer", "vulkan", "--control-stdin", "--no-controls",
                   "--storage", str(storage)]
        log_stream = log_path.open("w", encoding="utf-8")
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, env=env)
        output_lines = queue.Queue()

        def drain_output():
            for line in process.stdout:
                log_stream.write(line)
                log_stream.flush()
                output_lines.put(line)

        reader = threading.Thread(target=drain_output, daemon=True)
        reader.start()
        hwnd = 0
        try:
            # 3DS shader/core startup can exceed ten seconds on a hosted CPU renderer.
            wait_for_output(output_lines, "AN3_NATIVE_READY", timeout=45)
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Packaged player exited {process.returncode} before showing a window.")
                hwnd = ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE)
                if hwnd:
                    break
                time.sleep(0.25)
            self.assertTrue(hwnd, "packaged 3DS player window did not appear within 60 seconds")
            ctypes.windll.user32.ShowWindow(hwnd, 5)
            ctypes.windll.user32.SetForegroundWindow(hwnd)

            baseline_path = evidence / "3ds-title.png"
            deadline = time.monotonic() + 30
            baseline = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Packaged player exited {process.returncode} before rendering.")
                baseline = capture_client(hwnd, baseline_path)
                game = game_area(baseline)
                colors = len(game.getcolors(maxcolors=game.width * game.height) or [])
                visible_pixels = sum(pixel != (0, 0, 0) for pixel in game.getdata())
                visible_percent = visible_pixels * 100 / (game.width * game.height)
                if colors > 16 and visible_percent > 2.0:
                    break
                time.sleep(1)
            self.assertIsNotNone(baseline)
            self.assertGreater(colors, 16, "3DS client area remained blank or nearly uniform")
            self.assertGreater(visible_percent, 2.0, "3DS game area stayed black; see player log")

            process.stdin.write("1\tbutton\t8:1\n")
            process.stdin.flush()
            wait_for_output(output_lines, "AN3_NATIVE_CONTROL_RESULT 1 OK")
            time.sleep(0.5)
            input_path = evidence / "3ds-after-a.png"
            after_a = capture_client(hwnd, input_path)
            baseline_game, after_a_game = game_area(baseline), game_area(after_a)
            self.assertEqual(baseline_game.size, after_a_game.size)
            difference = ImageChops.difference(baseline_game, after_a_game)
            changed = sum(pixel != (0, 0, 0) for pixel in difference.getdata())
            changed_percent = changed * 100 / (baseline_game.width * baseline_game.height)
            self.assertGreater(changed_percent, 1.0, "visible 3DS screen did not change after A input")
        finally:
            shutdown_mode = "already-exited"
            shutdown_debugger = "not-needed"
            if process.poll() is None and process.stdin:
                process.stdin.write("QUIT\n")
                process.stdin.flush()
                shutdown_mode = "control-stdin-quit"
            try:
                return_code = process.wait(timeout=45)
            except subprocess.TimeoutExpired:
                debugger = shutil.which("gdb.exe") or shutil.which("gdb")
                if debugger and process.poll() is None:
                    try:
                        commands = evidence / "shutdown-gdb.commands"
                        commands.write_text(
                            f"attach {process.pid}\nthread apply all backtrace\ndetach\n",
                            encoding="utf-8",
                        )
                        trace = subprocess.run(
                            [debugger, "-batch", "-x", str(commands)],
                            capture_output=True, text=True, timeout=20,
                        )
                        shutdown_debugger = f"gdb-exit-{trace.returncode}"
                        (evidence / "shutdown-stacks.txt").write_text(
                            f"command: {debugger} -batch -x {commands}\n"
                            f"exitCode: {trace.returncode}\nstdout:\n{trace.stdout}\nstderr:\n{trace.stderr}",
                            encoding="utf-8",
                        )
                    except (OSError, subprocess.TimeoutExpired) as error:
                        shutdown_debugger = f"gdb-failed-{type(error).__name__}"
                        (evidence / "shutdown-stacks.txt").write_text(
                            f"GDB stack capture failed: {type(error).__name__}: {error}\n",
                            encoding="utf-8",
                        )
                else:
                    shutdown_debugger = "gdb-unavailable" if not debugger else "process-exited"
                    (evidence / "shutdown-stacks.txt").write_text(
                        f"GDB executable: {debugger or 'not found'}\n",
                        encoding="utf-8",
                    )
                if hwnd and process.poll() is None:
                    ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE fallback
                    shutdown_mode = "window-close-fallback"
                try:
                    return_code = process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    shutdown_mode = "forced-termination"
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   capture_output=True, check=False, timeout=10)
                    return_code = process.wait(timeout=5)
            if process.stdin:
                process.stdin.close()
            reader.join(timeout=2)
            if process.stdout:
                process.stdout.close()
            log_stream.close()

        record = {
            "packageArtifactRunId": os.environ["ARTIFACT_RUN_ID"],
            "sourceSha": expected_sha,
            "installer": installer.name,
            "installerSha256": installer_hash,
            "playerSha256": hashlib.sha256(player.read_bytes()).hexdigest(),
            "core": "Azahar",
            "coreSha256": hashlib.sha256(core.read_bytes()).hexdigest(),
            "fixtureSource": "https://github.com/16BitWonder/3DS-TEST",
            "fixtureCommit": FIXTURE_COMMIT,
            "fixtureSha256": FIXTURE_SHA256,
            "renderer": "Vulkan",
            "titleFrame": {"path": baseline_path.name, "width": baseline.width,
                           "height": baseline.height, "distinctColors": colors,
                           "visiblePixelsPercent": round(visible_percent, 4)},
            "afterAFrame": {"path": input_path.name},
            "aInputChangedPixels": changed,
            "aInputChangedPercent": round(changed_percent, 4),
            "shutdown": shutdown_mode,
            "shutdownExitCode": return_code,
            "shutdownDebugger": shutdown_debugger,
            "audio": "SDL dummy driver; audible output UNVERIFIED",
            "validation": "Hosted Windows visible window; physical GPU/display, controls, audible output, orderly process shutdown, and long-session behavior UNVERIFIED",
        }
        (evidence / "3ds-smoke.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main(verbosity=2)
