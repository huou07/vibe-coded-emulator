# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify the exact Linux DEB's Azahar core in its visible SDL window."""

from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest


FIXTURE_COMMIT = "e5b13872f0c1207cb9c86e18e710c8f1fa269fb8"
FIXTURE_SHA256 = "a9fac712e9a6e937ec3d3d3228d8031d94030f3bec3462d9048897f3be638050"


class LinuxPackaged3DSSmoke(unittest.TestCase):
    def test_exact_deb_azahar_visible_output_and_a_input(self):
        player = Path(os.environ["AN3_LINUX_3DS_PLAYER"]).resolve()
        libdir = Path(os.environ["AN3_LINUX_3DS_LIBDIR"]).resolve()
        fixture_root = Path(os.environ["AN3_LINUX_3DS_FIXTURE_ROOT"]).resolve()
        fixture = fixture_root / "3DS-TEST.3dsx"
        evidence = Path(os.environ["AN3_LINUX_3DS_EVIDENCE_DIR"]).resolve()
        expected_package_run = os.environ["AN3_LINUX_3DS_PACKAGE_RUN_ID"]
        evidence.mkdir(parents=True, exist_ok=True)

        self.assertTrue(player.is_file(), f"packaged Linux player is missing: {player}")
        self.assertTrue(libdir.is_dir(), f"packaged Linux runtime is missing: {libdir}")
        self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(), FIXTURE_SHA256)
        self.assertIn("MIT License", (fixture_root / "LICENSE").read_text(encoding="utf-8"))
        fixture_game = fixture_root / "game"
        self.assertTrue((fixture_game / "main.lua").is_file(), "the pinned 3DS test sidecar is incomplete")

        env = os.environ.copy()
        env.update({
            "AN3_PLAYER": str(player),
            "AN3_OFFLINE_LIBDIR": str(libdir),
            "SDL_AUDIODRIVER": "dummy",
            "LIBGL_ALWAYS_SOFTWARE": "1",
        })

        with tempfile.TemporaryDirectory(prefix="an3-linux-3ds-smoke-") as temp:
            temp = Path(temp)
            storage = temp / "storage"
            sd_game = storage / "saves/native-libretro/Azahar/sdmc/game"
            sd_game.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(fixture_game, sd_game)
            command = [
                str(player), "--rom", str(fixture), "--system", "3ds",
                "--renderer", "vulkan", "--control-stdin", "--storage", str(storage),
            ]
            log_path = evidence / "player.log"
            with log_path.open("w", encoding="utf-8") as log:
                process = subprocess.Popen(
                    command, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                    text=True, env=env,
                )
                try:
                    window = self.wait_for_window(player, process, log_path)
                    from PIL import Image, ImageChops

                    baseline_path = evidence / "3ds-title.png"
                    baseline, baseline_meta, colors = self.wait_for_visible_frame(window, baseline_path)

                    subprocess.run(["xdotool", "keydown", "x"], check=True, timeout=10)
                    try:
                        time.sleep(0.5)
                        input_path = evidence / "3ds-after-a.png"
                        input_meta = self.capture_window(window, input_path)
                    finally:
                        subprocess.run(["xdotool", "keyup", "x"], check=False, timeout=10)

                    with Image.open(input_path) as input_image:
                        input_frame = input_image.convert("RGB")
                    self.assertEqual(baseline.size, input_frame.size)
                    difference = ImageChops.difference(baseline, input_frame)
                    changed_pixels = sum(1 for pixel in difference.getdata() if pixel != (0, 0, 0))
                    changed_percent = changed_pixels * 100 / (baseline.width * baseline.height)
                    self.assertGreater(changed_percent, 1.0,
                                       "visible 3DS screen did not change after pressing A")
                finally:
                    if process.poll() is None and process.stdin:
                        process.stdin.write("QUIT\n")
                        process.stdin.flush()
                    try:
                        return_code = process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        return_code = process.wait(timeout=5)
                    if process.stdin:
                        process.stdin.close()
                    self.assertEqual(return_code, 0, f"packaged player exited {return_code}; see {log_path}")

        record = {
            "packageArtifactRunId": expected_package_run,
            "playerSha256": hashlib.sha256(player.read_bytes()).hexdigest(),
            "core": "Azahar",
            "fixtureSource": "https://github.com/16BitWonder/3DS-TEST",
            "fixtureCommit": FIXTURE_COMMIT,
            "fixtureLicense": "MIT",
            "fixtureSha256": FIXTURE_SHA256,
            "renderer": "Vulkan on Mesa llvmpipe (software)",
            "capture": "visible SDL player window under Xvfb; this path is required for hardware-rendered 3DS",
            "audio": "SDL dummy driver; audible output UNVERIFIED",
            "titleFrame": baseline_meta,
            "afterAFrame": input_meta,
            "titleFrameDistinctColors": colors,
            "aInputChangedPixels": changed_pixels,
            "aInputChangedPercent": changed_percent,
            "validation": "hosted Linux software-rendered window after visible-frame wait; physical GPU/display/input/audio and long-session behavior UNVERIFIED",
        }
        (evidence / "3ds-smoke.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def wait_for_window(player, process, log_path):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(f"packaged player exited {process.returncode}; see {log_path}")
            player_pid = process.pid
            result = subprocess.run(
                ["xdotool", "search", "--onlyvisible", "--pid", str(player_pid)],
                text=True, capture_output=True, check=False,
            )
            for window in result.stdout.split():
                title = subprocess.run(
                    ["xdotool", "getwindowname", window], text=True, capture_output=True, check=False,
                )
                if title.returncode == 0 and title.stdout.strip() == "VibeCodedEmulator":
                    subprocess.run(["xdotool", "windowactivate", "--sync", window], check=True, timeout=10)
                    time.sleep(1.0)
                    return window
            time.sleep(0.25)
        raise AssertionError(f"packaged 3DS window did not appear; see {log_path}")

    @staticmethod
    def capture_window(window, path):
        from PIL import Image

        subprocess.run(["xdotool", "windowactivate", "--sync", window], check=True, timeout=10)
        time.sleep(0.35)
        subprocess.run(["scrot", "-u", "-o", str(path)], check=True, timeout=10)
        with Image.open(path) as image:
            return {"path": path.name, "width": image.width, "height": image.height}

    @classmethod
    def wait_for_visible_frame(cls, window, target_path):
        from PIL import Image

        deadline = time.monotonic() + 15
        attempt = 0
        last_colors = 0
        while time.monotonic() < deadline:
            attempt += 1
            candidate = target_path.with_name(f"3ds-render-wait-{attempt:02d}.png")
            metadata = cls.capture_window(window, candidate)
            with Image.open(candidate) as image:
                frame = image.convert("RGB").copy()
            last_colors = len(frame.getcolors(maxcolors=frame.width * frame.height) or [])
            if last_colors > 16:
                candidate.replace(target_path)
                metadata["path"] = target_path.name
                metadata["visibleWaitSeconds"] = round(15 - max(0, deadline - time.monotonic()), 2)
                return frame, metadata, last_colors
            candidate.unlink(missing_ok=True)
            time.sleep(1.0)
        raise AssertionError(f"visible 3DS window stayed blank after 15 seconds ({last_colors} distinct colors)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
