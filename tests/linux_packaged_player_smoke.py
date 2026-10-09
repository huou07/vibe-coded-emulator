# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise frames, input, SRAM, and save states with the exact Linux DEB player."""

from pathlib import Path
import hashlib
import json
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
AN3CTL = ROOT / "tools/an3ctl/bin/an3ctl"


class LinuxPackagedPlayerSmoke(unittest.TestCase):
    def test_packaged_gba_frames_input_sram_and_save_state(self):
        package_root = Path(os.environ["AN3_LINUX_PACKAGE_ROOT"]).resolve()
        fixture = Path(os.environ["AN3_LINUX_GBA_FIXTURE"]).resolve()
        evidence = Path(os.environ["AN3_LINUX_UI_EVIDENCE_DIR"]).resolve()
        evidence.mkdir(parents=True, exist_ok=True)
        player = package_root / "usr/lib/VibeCodedEmulator/runtime/linux-x86_64/an3-offline-native"
        self.assertTrue(player.is_file(), f"packaged Linux player is missing: {player}")

        env = os.environ.copy()
        env["AN3_PLAYER"] = str(player)
        env["AN3_OFFLINE_LIBDIR"] = str(player.parent)
        snapshots = []

        def snapshot(storage, *, seq=None, save_state=None, load_state=None):
            args = [
                str(AN3CTL), "emulator", "snapshot", "--rom", str(fixture),
                "--system", "gba", "--frames", "120", "--storage", str(storage),
            ]
            if seq:
                args.extend(["--seq", seq])
            if save_state:
                args.extend(["--save-state", str(save_state)])
            if load_state:
                args.extend(["--load-state", str(load_state)])
            args.append("--json")
            result = subprocess.run(args, env=env, text=True, capture_output=True, timeout=90)
            self.assertEqual(result.returncode, 0, f"an3ctl failed: {result.stdout}\n{result.stderr}")
            payload = json.loads(result.stdout)
            self.assertTrue(payload.get("ok"), payload)
            data = payload["data"]
            snapshots.extend((Path(data["pngPath"]), Path(data["rawPath"])))
            status = data["status"]
            self.assertEqual(status.get("system"), "gba", status)
            self.assertEqual(status.get("frames"), 120, status)
            self.assertGreater(status.get("width", 0), 0, status)
            self.assertGreater(status.get("height", 0), 0, status)
            self.assertRegex(data.get("rawHash", ""), r"^[0-9a-f]{64}$")
            return data

        try:
            with tempfile.TemporaryDirectory(prefix="an3-linux-player-smoke-") as temp:
                temp = Path(temp)

                # A held on a cold save and then released must change output.
                input_storage = temp / "input-storage"
                cold_a = snapshot(input_storage, seq="A@0-120")
                cold_idle = snapshot(input_storage)
                self.assertNotEqual(cold_a["rawHash"], cold_idle["rawHash"],
                                    "GBA output did not respond to held A input")

                # A new process using the same storage must see the fixture's SRAM marker.
                save_storage = temp / "sram-storage"
                cold = snapshot(save_storage)
                restored = snapshot(save_storage)
                self.assertNotEqual(cold["rawHash"], restored["rawHash"],
                                    "GBA SRAM state did not change output on the next launch")

                # Saving an idle frame, changing it with A, then loading must restore pixels.
                state_storage = temp / "state-storage"
                state_path = temp / "slot.state"
                baseline = snapshot(state_storage, save_state=state_path)
                changed = snapshot(state_storage, seq="A@0-120")
                loaded = snapshot(state_storage, load_state=state_path)
                self.assertTrue(baseline["status"].get("stateSaved"), baseline["status"])
                self.assertNotEqual(baseline["rawHash"], changed["rawHash"],
                                    "GBA output did not change before state load")
                self.assertTrue(loaded["status"].get("stateLoaded"), loaded["status"])
                self.assertEqual(baseline["rawHash"], loaded["rawHash"],
                                 "loaded save state did not restore the captured frame")

                fixture_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
                (evidence / "player-result.json").write_text(json.dumps({
                    "player": str(player),
                    "playerSha256": hashlib.sha256(player.read_bytes()).hexdigest(),
                    "fixtureSha256": fixture_hash,
                    "system": "gba",
                    "framesPerSnapshot": 120,
                    "inputChangedFrame": cold_a["rawHash"] != cold_idle["rawHash"],
                    "sramChangedFrameAfterRelaunch": cold["rawHash"] != restored["rawHash"],
                    "stateSaved": baseline["status"].get("stateSaved"),
                    "stateLoaded": loaded["status"].get("stateLoaded"),
                    "baselineRawHash": baseline["rawHash"],
                    "changedRawHash": changed["rawHash"],
                    "restoredRawHash": loaded["rawHash"],
                    "validation": "headless CPU capture; physical display/GPU/input/audio unverified",
                }, indent=2) + "\n", encoding="utf-8")
        finally:
            for path in snapshots:
                path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
