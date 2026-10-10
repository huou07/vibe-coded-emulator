# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify the exact Linux DEB's Azahar core with the pinned lawful test app."""

from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
AN3CTL = ROOT / "tools/an3ctl/bin/an3ctl"
FIXTURE_COMMIT = "e5b13872f0c1207cb9c86e18e710c8f1fa269fb8"
FIXTURE_SHA256 = "a9fac712e9a6e937ec3d3d3228d8031d94030f3bec3462d9048897f3be638050"


class LinuxPackaged3DSSmoke(unittest.TestCase):
    def test_exact_deb_azahar_boots_and_responds_to_a(self):
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

        def snapshot(storage, name, frames, sequence=None):
            sd_game = storage / "saves/native-libretro/Azahar/sdmc/game"
            sd_game.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(fixture_game, sd_game)
            args = [
                str(AN3CTL), "emulator", "snapshot", "--rom", str(fixture),
                "--system", "3ds", "--renderer", "vulkan", "--frames", str(frames),
                "--storage", str(storage), "--json",
            ]
            if sequence:
                args.extend(["--seq", sequence])
            result = subprocess.run(args, env=env, text=True, capture_output=True, timeout=180)
            (evidence / f"{name}-command.json").write_text(json.dumps({
                "args": args,
                "returnCode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }, indent=2) + "\n", encoding="utf-8")
            self.assertEqual(result.returncode, 0, f"an3ctl failed: {result.stdout}\n{result.stderr}")
            payload = json.loads(result.stdout)
            self.assertTrue(payload.get("ok"), payload)
            data = payload["data"]
            status = data["status"]
            raw_path = Path(data["rawPath"])
            png_path = Path(data["pngPath"])
            raw = raw_path.read_bytes()
            target_png = evidence / f"{name}.png"
            target_raw = evidence / f"{name}.rgba"
            shutil.copy2(png_path, target_png)
            shutil.copy2(raw_path, target_raw)
            self.assertEqual(status.get("system"), "3ds", status)
            self.assertEqual(status.get("frames"), frames, status)
            self.assertEqual(status.get("coreFrames"), frames, status)
            self.assertTrue(status.get("running"), status)
            self.assertTrue(status.get("captured"), status)
            self.assertGreater(status.get("width", 0), 0, status)
            self.assertGreater(status.get("height", 0), 0, status)
            self.assertEqual(len(raw), status["width"] * status["height"] * 4)
            colors = {raw[offset:offset + 4] for offset in range(0, len(raw), 4)}
            self.assertGreater(len(colors), 16, "3DS capture was a uniform/blank frame")
            snapshot_record = {
                "name": name,
                "frames": frames,
                "inputSequence": sequence,
                "status": status,
                "rawHash": data["rawHash"],
                "pngHash": data["pngHash"],
                "distinctRgbaColors": len(colors),
                "png": target_png.name,
                "raw": target_raw.name,
            }
            raw_path.unlink(missing_ok=True)
            png_path.unlink(missing_ok=True)
            return snapshot_record, raw

        with tempfile.TemporaryDirectory(prefix="an3-linux-3ds-smoke-") as temp:
            temp = Path(temp)
            baseline_record, baseline = snapshot(temp / "baseline-storage", "baseline", 120)
            input_record, with_a = snapshot(temp / "input-storage", "input-a", 240, "A@120-122")

        self.assertEqual(len(baseline), len(with_a))
        changed_pixels = sum(
            baseline[offset:offset + 4] != with_a[offset:offset + 4]
            for offset in range(0, len(baseline), 4)
        )
        changed_percent = changed_pixels * 100 / (len(baseline) // 4)
        self.assertGreater(changed_percent, 1.0, "A input did not change the captured 3DS screen")

        record = {
            "packageArtifactRunId": expected_package_run,
            "playerSha256": hashlib.sha256(player.read_bytes()).hexdigest(),
            "core": "Azahar",
            "fixtureSource": "https://github.com/16BitWonder/3DS-TEST",
            "fixtureCommit": FIXTURE_COMMIT,
            "fixtureLicense": "MIT",
            "fixtureSha256": FIXTURE_SHA256,
            "renderer": "Vulkan on Mesa llvmpipe (software)",
            "audio": "SDL dummy driver; audible output UNVERIFIED",
            "snapshots": [baseline_record, input_record],
            "aInputChangedPixels": changed_pixels,
            "aInputChangedPercent": changed_percent,
            "validation": "hosted headless capture; physical GPU/display/input/audio and long-session behavior UNVERIFIED",
        }
        (evidence / "3ds-smoke.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main(verbosity=2)
