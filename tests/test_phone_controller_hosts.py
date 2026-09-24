# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phone Controller host integrations.

Covers the shared utility dispatcher (behavioral), the browser player host
wiring, the desktop shared Rust host wiring, and confirms the Android host and
canonical action model are reused rather than duplicated.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "native-offline" / "shared" / "input-actions-schema.json"
UTILITY_JS = ROOT / "static" / "controller-utility.js"
PLAYER = ROOT / "static" / "player.js"
DESKTOP_HOST = ROOT / "native-offline" / "src-tauri" / "src" / "controller_host.rs"
LAN_HOST = ROOT / "native-offline" / "src-tauri" / "src" / "lan_host.rs"
AZAHAR = ROOT / "native-offline" / "src-tauri" / "src" / "azahar.rs"
ANDROID_CLIENT = ROOT / "native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/ControllerClient.kt"
ANDROID_HOST = ROOT / "native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/An3ControllerHost.kt"
NETCODE = ROOT / "netcode.py"
APP = ROOT / "app.py"
INDEX = ROOT / "native-offline" / "web" / "index.html"
NODE_TEST = ROOT / "tests" / "controller_utility.test.js"


def source(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


class SharedUtilityActionTests(unittest.TestCase):
    def test_behavioral_dispatcher_suite_passes(self):
        result = subprocess.run(["node", str(NODE_TEST)], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("controller utility behavior: ok", result.stdout)

    def test_dispatcher_reuses_the_canonical_action_names(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        actions = set(schema["utility"])
        utility = source(UTILITY_JS)
        for action in actions:
            self.assertIn(f'"{action}"', utility)

    def test_netcode_still_validates_utility_wire_names_from_the_schema(self):
        netcode = source(NETCODE)
        self.assertIn("input-actions-schema.json", netcode)
        self.assertIn("CONTROLLER_UTILITY_ACTIONS", netcode)


class BrowserHostTests(unittest.TestCase):
    def test_player_loads_the_shared_dispatcher(self):
        page = source(APP)
        index = source(INDEX)
        for text in (page, index):
            self.assertIn("controller-utility.js", text)
        player = source(PLAYER)
        self.assertIn("window.AN3ControllerUtility", player)

    def test_browser_host_dispatches_utilities_to_existing_operations(self):
        player = source(PLAYER)
        self.assertIn("controllerUtility.dispatch(payload.utilities)", player)
        # Reuses the existing save/speed/menu operations; no second implementation.
        self.assertIn("QUICK_SAVE: entry => saveSlot(entry?.slot || readQuickSlot())", player)
        self.assertIn("QUICK_LOAD: entry => loadSlot(entry?.slot || readQuickSlot())", player)
        self.assertIn("SPEED_UP: () => shiftSpeed(1)", player)
        self.assertIn("SPEED_DOWN: () => shiftSpeed(-1)", player)
        self.assertIn("OPEN_MENU: () => openPlayerOptions()", player)
        self.assertIn("const openPlayerOptions = () =>", player)
        self.assertNotIn("function saveSlot2", player)

    def test_browser_host_acknowledges_the_utility_sequence(self):
        player = source(PLAYER)
        self.assertIn("const controllerAck = (sequence, utilitySequence)", player)
        self.assertIn("utilitySequence:utilitySequence||0", player)
        self.assertIn("controllerAck(payload.lastSequence, controllerUtility.lastSequence)", player)
        self.assertIn("controllerUtility.reset()", player)

    def test_browser_quick_save_remembers_the_last_slot(self):
        player = source(PLAYER)
        self.assertIn('QUICK_SLOT_KEY="vibe-quick-save-slot-v1"', player)
        self.assertIn("const readQuickSlot=", player)
        self.assertIn("writeQuickSlot(slot);", player)


class DesktopHostTests(unittest.TestCase):
    def test_shared_host_dispatches_utilities_once(self):
        host = source(DESKTOP_HOST)
        self.assertIn("pub(crate) type UtilitySink = Arc<dyn Fn(&HostAction) -> bool + Send + Sync>", host)
        self.assertIn("pub(crate) fn dispatch_utilities(", host)
        self.assertIn("host_actions::dispatch", host)
        self.assertIn("dispatch_utilities(&payload, &mut last_utility, &utility_sink)", host)
        self.assertIn("utilitySequence", host)
        self.assertIn("{utility_sequence}", host)

    def test_shared_host_rejects_unsupported_actions_instead_of_pretending(self):
        # The desktop host routes the canonical actions to each platform's
        # existing native operations, so the old "not wired yet" placeholder is
        # gone. The honest-behaviour invariant it protected still holds: an
        # unsupported action is rejected explicitly, never reported as applied.
        host = source(DESKTOP_HOST)
        azahar = source(ROOT / "native-offline" / "src-tauri" / "src" / "azahar.rs")
        self.assertNotIn("is not wired on this desktop host yet", host)
        self.assertIn("crate::azahar::apply_utility_at_slot(&command.action, command.slot)", host)
        self.assertIn("Unsupported utility action", azahar)
        self.assertIn("fn is_known_utility(", azahar)

    def test_shared_host_acknowledges_only_executed_actions(self):
        host = source(DESKTOP_HOST)
        # The sink reports whether the platform actually ran the action, so an
        # unsupported action can never advance the acknowledged sequence.
        actions = source(ROOT / "native-offline" / "src-tauri" / "src" / "host_actions.rs")
        self.assertIn("if sink(&command)", actions)
        self.assertIn("executed = executed.max(command.sequence)", actions)

    def test_direct_lan_host_executes_utility_frames(self):
        lan = source(LAN_HOST)
        self.assertIn("dispatch_utilities(frame, &mut replay, &controller_utility_sink())", lan)
        self.assertIn("last_utility", lan)
        self.assertIn("command_id", lan)
        # The app's direct-LAN frame carries the canonical `u` array.
        self.assertIn('"u"', lan)

    def test_macos_platform_maps_canonical_utility_actions(self):
        overlay = source(ROOT / "native-offline" / "src-tauri" / "src" / "azahar_host.mm")
        self.assertIn("an3_native_apply_utility", overlay)
        for action in ("QUICK_SAVE", "QUICK_LOAD", "SPEED_UP", "SPEED_DOWN", "OPEN_MENU"):
            self.assertIn(f'"{action}"', overlay)
        # Windows and Linux route through their portable runtime, which reports
        # an unavailable action instead of silently succeeding.
        for runtime in ("windows_runtime.rs", "linux_runtime.rs"):
            body = source(ROOT / "native-offline" / "src-tauri" / "src" / runtime)
            self.assertIn("pub(super) fn utility(", body)

    def test_shared_host_still_owns_input_and_authentication(self):
        host = source(DESKTOP_HOST)
        # Auth is unchanged: the host token stays in the host and utilities only
        # arrive through the authenticated host-state endpoint.
        self.assertIn("hostToken={host_token}", host)
        self.assertIn("Ok((403, _)) | Ok((404, _))", host)


class AndroidHostUnchangedTests(unittest.TestCase):
    def test_android_already_dispatches_utilities_with_dedup(self):
        client = source(ANDROID_CLIENT)
        self.assertIn("dispatchUtilities", client)
        self.assertIn("if (sequence <= lastUtility) continue", client)
        self.assertIn('put("utilitySequence", lastUtility)', client)
        host = source(ANDROID_HOST)
        self.assertIn("fun utility(action: String, slot: Int)", host)
        self.assertIn("onUtility = { action, slot -> sink?.utility(action, slot) }", host)

    def test_android_advertises_only_the_capability_it_currently_serves(self):
        client = source(ANDROID_CLIENT)
        self.assertIn('.put("capabilities", JSONArray().put("controller"))', client)
        self.assertNotIn('JSONArray().put("controller").put("sync")', client)

    def test_android_pairing_rejects_wrong_capability_and_limits_failed_attempts(self):
        client = source(ANDROID_CLIENT)
        self.assertIn("MAX_FAILURES_PER_MINUTE = 6", client)
        self.assertIn("rateLimited(peerAddress)", client)
        self.assertIn("noteFailure(peerAddress)", client)
        self.assertIn("clearFailures(peerAddress)", client)
        self.assertIn('hello.optString("capability") != "controller"', client)
        self.assertIn('Regex("^[A-Za-z0-9._-]{8,64}$").matches(peerId)', client)


if __name__ == "__main__":
    unittest.main()
