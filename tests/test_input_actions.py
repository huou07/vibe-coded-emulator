# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Canonical input/action contract tests.

Behavioural geometry/action coverage lives in tests/input_actions.test.mjs
(node --test). These checks keep the shared schema, the generated Kotlin/JS
adapters, the Android wiring, and the controller protocol aligned, and verify
the one-shot utility semantics at the netcode level.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import subprocess
import unittest

import netcode as nc


ROOT = pathlib.Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native-offline"
SCHEMA = NATIVE / "shared" / "input-actions-schema.json"
GENERATOR = NATIVE / "scripts" / "generate-input-actions.mjs"
KOTLIN = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeInputActions.kt"
CIRCULAR = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeCircularDpad.kt"
OVERLAY = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeGameOverlay.kt"
ACTIVITY = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeGameActivity.kt"
HOST = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/An3ControllerHost.kt"
SERVICE = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/ControllerHostService.kt"
CLIENT = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/ControllerClient.kt"
JS_MODEL = ROOT / "static" / "input-actions.js"
PHONE = ROOT / "static" / "controller.js"
APP = ROOT / "app.py"
NODE_TEST = ROOT / "tests" / "input_actions.test.mjs"


def source(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


class InputActionSchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    def test_gameplay_actions_use_unique_libretro_ids(self):
        ids = [button["libretro"] for button in self.schema["buttons"].values()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(self.schema["buttons"]["UP"]["libretro"], 4)
        self.assertEqual(self.schema["buttons"]["A"]["libretro"], 8)

    def test_utility_actions_are_one_shot_and_disjoint(self):
        actions = set(self.schema["utility"])
        self.assertEqual(actions, {"QUICK_SAVE", "QUICK_LOAD", "SPEED_UP", "SPEED_DOWN", "OPEN_MENU"})
        self.assertFalse(actions & set(self.schema["buttons"]))
        for entry in self.schema["utility"].values():
            self.assertTrue(entry["wire"])

    def test_movement_options_include_circular(self):
        ids = [control["id"] for control in self.schema["directionalControls"]]
        self.assertEqual(ids, ["dpad", "joystick", "circular"])

    def test_circular_geometry_covers_eight_sectors(self):
        circular = self.schema["circular"]
        self.assertEqual(len(circular["sectors"]), 8)
        diagonals = [sector for sector in circular["sectors"] if len(sector["actions"]) == 2]
        cardinals = [sector for sector in circular["sectors"] if len(sector["actions"]) == 1]
        self.assertEqual(len(diagonals), 4)
        self.assertEqual(len(cardinals), 4)
        for sector in diagonals:
            self.assertEqual(len(set(sector["actions"])), 2)
        self.assertTrue(0 < circular["deadzone"] < 1)

    def test_generated_outputs_are_in_sync(self):
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (KOTLIN, JS_MODEL)}
        result = subprocess.run(["node", str(GENERATOR)], cwd=NATIVE, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (KOTLIN, JS_MODEL)}
        self.assertEqual(before, after, "committed input-action adapters are stale; run npm run prepare-web")

    def test_behavioral_geometry_suite_passes(self):
        result = subprocess.run(["node", "--test", str(NODE_TEST)], cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class AndroidInputWiringTests(unittest.TestCase):
    def test_kotlin_adapter_exposes_canonical_data(self):
        kotlin = source(KOTLIN)
        self.assertIn("const val UP = 4", kotlin)
        self.assertIn('val utilityActions: List<String> = listOf("QUICK_SAVE", "QUICK_LOAD", "SPEED_UP", "SPEED_DOWN", "OPEN_MENU")', kotlin)
        self.assertIn("fun circularDirections(dx: Float, dy: Float, previous: String?): CircularResult", kotlin)
        self.assertIn("pressedCardinals", kotlin)

    def test_overlay_uses_circular_geometry_and_utility_actions(self):
        overlay = source(OVERLAY)
        self.assertIn("NativeCircularDpad(activity)", overlay)
        self.assertIn("NativeInputActions.circularDirections", source(CIRCULAR))
        self.assertIn("circularMode", overlay)
        self.assertIn("fun utility(action: String, slot: Int = quickSaveSlot())", overlay)
        self.assertIn('send("save", selected.toString())', overlay)
        self.assertIn('"QUICK_LOAD" -> send("load", slot.coerceIn(1, 10).toString())', overlay)
        self.assertIn("KEYCODE_DPAD_UP", overlay)
        self.assertNotIn('if (k == "pad")', overlay)

    def test_phone_sink_dispatches_utilities_to_the_existing_overlay(self):
        host = source(HOST)
        self.assertIn("fun utility(action: String, slot: Int)", host)
        service = source(SERVICE)
        self.assertIn('putString(KEY_KIND, "utility")', service)
        activity = source(ACTIVITY)
        self.assertIn('"utility" ->', activity)
        self.assertIn("overlay.utility(it, data.getInt(ControllerHostService.KEY_SLOT, 1))", activity)

    def test_controller_client_deduplicates_utilities(self):
        client = source(CLIENT)
        self.assertIn("lastUtility", client)
        self.assertIn("dispatchUtilities", client)
        self.assertIn('put("utilitySequence", lastUtility)', client)
        self.assertIn("if (sequence <= lastUtility) continue", client)
        self.assertIn("command_id", client)
        self.assertIn("slot !in 1..10", client)


class PhoneControllerWiringTests(unittest.TestCase):
    def test_phone_page_has_utility_buttons_and_no_pad_toggle(self):
        page = source(APP)
        self.assertIn('data-util="quick_save"', page)
        self.assertIn('data-util="quick_load"', page)
        self.assertIn('data-util="speed_up"', page)
        self.assertIn('data-util="speed_down"', page)
        self.assertIn('data-util="open_menu"', page)
        self.assertIn('id="ctrlMovement"', page)
        self.assertIn('id="ctrlCircular"', page)
        self.assertIn("input-actions.js", page)
        # The phone is the controller; it must not expose a Pad visibility toggle.
        self.assertNotIn('data-btn="pad"', page)
        self.assertNotIn('data-util="pad"', page)

    def test_phone_js_uses_shared_geometry_and_utility_model(self):
        js = source(PHONE)
        self.assertIn("AN3InputActions.circularDirections", js)
        self.assertIn("AN3InputActions.utilityWireToAction", js)
        self.assertIn("sendUtility", js)
        self.assertIn("an3-controller-movement", js)

    def test_motion_option_persists_and_defaults_to_dpad(self):
        js = source(PHONE)
        self.assertIn('var movement = "dpad";', js)
        self.assertRegex(js, r'localStorage\.setItem\("an3-controller-movement", movement\)')


class ControllerUtilityNetcodeTests(unittest.TestCase):
    def _paired(self):
        session = nc.ControllerSession(code="ABC123", host_device_id="host", created_at=0.0, clock=lambda: 0.0)
        token = session.pair("phone")
        return session, token

    def test_utility_round_trips_on_the_wire(self):
        state = nc.ControllerState(
            sequence=4,
            buttons=frozenset(),
            utility_action="quick_save",
            utility_sequence=2,
            utility_command_id="phone-session-2",
            utility_slot=10,
        )
        wire = state.to_wire()
        self.assertEqual(wire["u"], "quick_save")
        self.assertEqual(wire["us"], 2)
        self.assertEqual(wire["command_id"], "phone-session-2")
        self.assertEqual(wire["slot"], 10)
        restored = nc.ControllerState.from_wire(wire)
        self.assertEqual(restored.utility_action, "quick_save")
        self.assertEqual(restored.utility_sequence, 2)
        self.assertEqual(restored.utility_command_id, "phone-session-2")
        self.assertEqual(restored.utility_slot, 10)

    def test_explicit_command_ids_are_replay_identity(self):
        session, token = self._paired()
        session.accept_state({"s": 1, "b": [], "u": "quick_save", "us": 4, "command_id": "phone-a", "slot": 3}, token=token)
        session.accept_state({"s": 2, "b": [], "u": "quick_load", "us": 4, "command_id": "phone-b", "slot": 10}, token=token)
        session.accept_state({"s": 3, "b": [], "u": "quick_save", "us": 4, "command_id": "phone-a", "slot": 3}, token=token)
        pending = session.pending_utilities()
        self.assertEqual([(item["action"], item["slot"], item["command_id"]) for item in pending], [
            ("quick_save", 3, "phone-a"), ("quick_load", 10, "phone-b")
        ])

    def test_unknown_utility_names_are_ignored(self):
        state = nc.ControllerState.from_wire({"s": 1, "b": [], "u": "evil_command", "us": 9})
        self.assertEqual(state.utility_action, "")
        self.assertEqual(state.utility_sequence, 0)

    def test_session_queues_each_utility_once_and_clears_on_ack(self):
        session, token = self._paired()
        session.accept_state({"s": 1, "b": [], "u": "speed_up", "us": 1}, token=token)
        session.accept_state({"s": 1, "b": [], "u": "speed_up", "us": 1}, token=token)  # duplicate
        session.accept_state({"s": 2, "b": [], "u": "quick_save", "us": 2}, token=token)
        pending = session.pending_utilities()
        self.assertEqual([item["action"] for item in pending], ["speed_up", "quick_save"])
        session.ack(2, 2)
        self.assertEqual(session.pending_utilities(), [])

    def test_stale_utility_sequence_is_ignored(self):
        session, token = self._paired()
        session.accept_state({"s": 3, "b": [], "u": "open_menu", "us": 5}, token=token)
        session.accept_state({"s": 4, "b": [], "u": "speed_down", "us": 4}, token=token)
        self.assertEqual([item["action"] for item in session.pending_utilities()], ["open_menu"])

    def test_disconnect_drops_pending_utilities(self):
        session, token = self._paired()
        session.accept_state({"s": 1, "b": [], "u": "quick_save", "us": 1}, token=token)
        session.disconnect()
        self.assertEqual(session.pending_utilities(), [])

    def test_utility_requires_the_session_token(self):
        session, _ = self._paired()
        with self.assertRaises(nc.NotPairedError):
            session.accept_state({"s": 1, "b": [], "u": "quick_save", "us": 1}, token="wrong")


if __name__ == "__main__":
    unittest.main()
