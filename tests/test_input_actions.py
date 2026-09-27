# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract checks for the generated local Android input adapter."""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native-offline"
SCHEMA = NATIVE / "shared" / "input-actions-schema.json"
GENERATOR = NATIVE / "scripts" / "generate-input-actions.mjs"
KOTLIN = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeInputActions.kt"
CIRCULAR = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeCircularDpad.kt"
OVERLAY = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeGameOverlay.kt"
ACTIVITY = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeGameActivity.kt"
NODE_TEST = ROOT / "tests" / "input_actions.test.mjs"


def source(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


class LocalInputSchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    def test_gameplay_buttons_keep_unique_libretro_ids(self):
        buttons = self.schema["buttons"]
        ids = [button["libretro"] for button in buttons.values()]
        self.assertEqual(len(ids), len(set(ids)))
        for name, expected in {"UP": 4, "DOWN": 5, "LEFT": 6, "RIGHT": 7, "A": 8, "B": 0, "START": 3, "SELECT": 2}.items():
            self.assertEqual(buttons[name]["libretro"], expected)
        self.assertTrue(all("wire" not in button for button in buttons.values()))

    def test_touch_direction_modes_and_speeds_remain_local(self):
        self.assertEqual([item["id"] for item in self.schema["directionalControls"]], ["dpad", "joystick", "circular"])
        self.assertEqual(self.schema["speeds"], ["0.5", "1", "2", "4", "8"])
        sectors = self.schema["circular"]["sectors"]
        self.assertEqual(len(sectors), 8)
        self.assertEqual(sum(len(item["actions"]) == 1 for item in sectors), 4)
        self.assertEqual(sum(len(item["actions"]) == 2 for item in sectors), 4)
        for sector in sectors:
            self.assertTrue(set(sector["actions"]).issubset(self.schema["buttons"]))

    def test_generated_android_adapter_is_in_sync(self):
        before = hashlib.sha256(KOTLIN.read_bytes()).hexdigest()
        result = subprocess.run(["node", str(GENERATOR)], cwd=NATIVE, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        after = hashlib.sha256(KOTLIN.read_bytes()).hexdigest()
        self.assertEqual(before, after, "committed Android local-input adapter is stale")

    def test_native_gameplay_wiring_keeps_touch_keyboard_and_physical_gamepad(self):
        kotlin = source(KOTLIN)
        circular = source(CIRCULAR)
        overlay = source(OVERLAY)
        activity = source(ACTIVITY)
        self.assertIn("const val UP = 4", kotlin)
        self.assertIn("fun circularDirections(dx: Float, dy: Float, previous: String?): CircularResult", kotlin)
        self.assertIn("NativeInputActions.circularDirections", circular)
        self.assertIn("NativeInputActions.pressedCardinals", circular)
        self.assertIn("NativeCircularDpad(activity)", overlay)
        self.assertIn("surface.setOnTouchListener", activity)
        self.assertIn("override fun onKeyDown", activity)
        self.assertIn("override fun onKeyUp", activity)
        self.assertIn("override fun onGenericMotionEvent", activity)
        self.assertIn("gameButton(", activity)
        self.assertNotIn("ControllerHostService", activity + overlay)
        self.assertNotIn("fun utility(", overlay)

    def test_behavioral_schema_contract_passes(self):
        result = subprocess.run(["node", "--test", str(NODE_TEST)], cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
