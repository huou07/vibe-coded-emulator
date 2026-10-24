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

import netcode as nc


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

    def test_netcode_queues_canonical_names_every_host_dispatches(self):
        # The phone page sends canonical ids (utilityWireToAction); the
        # browser dispatcher, the desktop azahar sink and the Android overlay
        # all key on canonical ids, so the queued command must be canonical.
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        session = nc.ControllerSession(code="ABC123", host_device_id="host", created_at=0.0, clock=lambda: 0.0)
        token = session.pair("phone")
        session.accept_state({"s": 1, "b": [], "u": "QUICK_SAVE", "us": 1}, token=token)
        pending = session.pending_utilities()
        self.assertEqual([item["action"] for item in pending], ["QUICK_SAVE"])
        for item in pending:
            self.assertIn(item["action"], schema["utility"])
        # Wire spellings normalize to the same dispatchable id.
        session.accept_state({"s": 2, "b": [], "u": "speed_up", "us": 2}, token=token)
        self.assertEqual(
            [item["action"] for item in session.pending_utilities()],
            ["QUICK_SAVE", "SPEED_UP"],
        )


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
        self.assertIn("QUICK_SAVE: () => saveSlot(readQuickSlot())", player)
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
        self.assertIn("pub(crate) type UtilitySink = Arc<dyn Fn(&str) -> bool + Send + Sync>", host)
        self.assertIn("pub(crate) fn dispatch_utilities(", host)
        self.assertIn("if sequence <= *last", host)
        self.assertIn("dispatch_utilities(&payload, &mut last_utility, &utility_sink)", host)
        self.assertIn("utilitySequence", host)
        self.assertIn("{utility_sequence}", host)

    def test_shared_host_acknowledges_only_executed_actions(self):
        host = source(DESKTOP_HOST)
        # The sink reports whether the platform actually ran the action, so an
        # unsupported action can never advance the acknowledged sequence.
        self.assertIn("crate::azahar::apply_controller_utility(action)", host)
        self.assertIn("if !action.is_empty() && sink(action)", host)
        self.assertIn("executed = executed.max(sequence)", host)

    def test_direct_lan_host_executes_utility_frames(self):
        lan = source(LAN_HOST)
        self.assertIn("dispatch_utilities(frame, &mut last_utility, &controller_utility_sink())", lan)
        self.assertIn("last_utility", lan)
        # The app's direct-LAN frame carries the canonical `u` array.
        self.assertIn('"u"', lan)

    def test_macos_platform_maps_canonical_utility_actions(self):
        platform = source(AZAHAR)
        for action in ("SPEED_UP", "SPEED_DOWN", "QUICK_SAVE", "OPEN_MENU"):
            self.assertIn(f'"{action}"', platform)
        self.assertIn("an3_native_controller_speed", platform)
        self.assertIn("an3_native_controller_quick_save", platform)
        self.assertIn("an3_native_controller_open_menu", platform)
        # Unavailable actions must report false instead of pretending success.
        self.assertIn("is unavailable on this host build", platform)

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
        self.assertIn("fun utility(action: String)", host)
        self.assertIn("onUtility = { action -> sink?.utility(action) }", host)

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

    def test_android_direct_controller_keeps_resume_token_private_and_reconnects_to_same_host(self):
        client = source(ANDROID_CLIENT)
        host = source(ANDROID_HOST)
        bridge = source(ROOT / "native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/MainActivity.kt")
        bootstrap = source(ROOT / "native-offline/web/native-bootstrap.js")
        shell = source(ROOT / "native-offline/web/native-app.js")
        self.assertIn("hostResumeToken: ByteArray?", client)
        self.assertIn("clientResumeToken: ByteArray?", client)
        self.assertIn('put("canReconnect", canReconnect)', client)
        self.assertIn("discoverController(if (pairing) null else clientHostId)", client)
        self.assertIn('if (usedCode) encode(hostResumeToken', client)
        self.assertIn("fun reconnect(): ControllerStatus", client)
        self.assertIn("clientResumeToken = null", client)
        self.assertIn("hostSocket != null && shouldApply() && paired", client)
        self.assertIn("try { hostSocket?.close() }", client)
        self.assertIn("if (hostSocket === connection)", client)
        self.assertIn("if (previous != null && previous !== connection)", client)
        self.assertIn(
            "lastSequence = 0\n                    lastUtility = 0\n                    ackSequence = 0\n                    hostSocket.also { hostSocket = connection }",
            client,
        )
        self.assertIn("(!activated || hostSocket === connection)", client)
        self.assertIn("fun reconnect(): ControllerStatus", host)
        self.assertIn("fun reconnect(): String", bridge)
        self.assertIn("reconnect: () => androidController.reconnect", bootstrap)
        self.assertIn('status.canReconnect ? "Reconnect" : "Join Host"', shell)

    def test_android_controller_clears_local_holds_when_transport_drops(self):
        shell = source(ROOT / "native-offline/web/native-app.js")
        self.assertIn("const controllerDisconnected =", shell)
        self.assertIn("if (controllerDisconnected) releaseAll(false)", shell)


if __name__ == "__main__":
    unittest.main()


class DirectLanFailurePathTests(unittest.TestCase):
    """A failed direct-LAN action must say why.

    A Tauri command rejection is a plain string, so `error.message` is
    undefined. The join handler used `error?.message || "Could not join the
    direct LAN host."`, which replaced the transport's own reason — "No AN3
    controller host was found on the local network.", a discovery timeout, a
    port conflict, an incompatible protocol or a rejected code — with one
    generic sentence, and made a two-peer failure undiagnosable from the UI.
    """

    def test_the_join_failure_path_surfaces_the_transport_reason(self):
        app_js = source(INDEX.parent / "native-app.js")
        self.assertIn("const describeError =", app_js)
        self.assertIn("typeof error === \"string\" ? error :", app_js)
        for generic in (
            'setStatus(error?.message || "Could not join the direct LAN host.");',
            'setStatus(error?.message || "Direct controller session ended");',
            'setMessage(error?.message || "LAN multiplayer configuration failed.");',
        ):
            self.assertNotIn(generic, app_js)
        self.assertIn('setStatus(describeError(error, "Could not join the direct LAN host."));', app_js)

    def test_discovery_reports_a_missing_host_distinctly(self):
        host = source(LAN_HOST)
        self.assertIn("No AN3 controller host was found on the local network.", host)
        self.assertIn("Direct LAN discovery is unavailable", host)
