# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import http.client
import json
import pathlib
import re
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import app
import netcode


ROOT = pathlib.Path(__file__).resolve().parents[1]


class PrimaryCoreMapTests(unittest.TestCase):
    def test_python_core_map_matches_the_web_player(self):
        source = (ROOT / "static/player.js").read_text(encoding="utf-8")
        block = source[source.index("const primaryCores = {"):]
        block = block[:block.index("};")]
        player_map = {key: value for key, value in re.findall(r'["\']?([A-Za-z0-9_]+)["\']?\s*:\s*"([^"]+)"', block)}
        self.assertEqual(player_map, app.PRIMARY_CORES)
        # The room signature must not invent a core for a system the player
        # cannot boot.
        self.assertEqual(app.PRIMARY_CORES["nds"], "melonds")
        self.assertEqual(app.PRIMARY_CORES["3ds"], "azahar")


class MultiplayerRoomApiTests(unittest.TestCase):
    def setUp(self):
        self.rooms = netcode.RoomService(room_ttl_seconds=900)
        self.patches = [
            patch.object(app, "MULTIPLAYER_ENABLED", True),
            patch.object(app, "NETPLAY_ORIGIN", "http://127.0.0.1:8094"),
            patch.object(app, "ROOMS", self.rooms),
        ]
        for active in self.patches:
            active.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        for active in self.patches:
            active.stop()

    def request(self, method, path, payload=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if body else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        status, data = response.status, response.read()
        connection.close()
        return status, data

    @staticmethod
    def signature(rom_hash="a" * 64, **overrides):
        base = {"system": "gba", "core": "mgba", "romHash": "sha256:" + rom_hash}
        base.update(overrides)
        return base

    def request_full(self, method, path):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        connection.request(method, path)
        response = connection.getresponse()
        status, headers, data = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return status, headers, data

    def test_room_qr_svg_is_served_for_a_valid_link(self):
        status, headers, body = self.request_full("GET", "/api/multiplayer/qr.svg?slug=pokemon-emerald&code=AB12CD")
        self.assertEqual(status, 200)
        self.assertIn("image/svg+xml", headers.get("Content-Type", ""))
        text = body.decode("utf-8")
        self.assertTrue(text.startswith("<svg "))
        self.assertNotIn("<script", text)

    def test_room_qr_rejects_a_bad_slug_or_code(self):
        for query in ("?slug=../etc&code=AB12CD", "?slug=pokemon-emerald&code=", "?code=AB12CD", "?slug=pokemon-emerald&code=<<>>"):
            with self.subTest(query=query):
                status, _, _ = self.request_full("GET", "/api/multiplayer/qr.svg" + query)
                self.assertEqual(status, 400)

    def test_create_join_status_flow(self):
        status, body = self.request("POST", "/api/multiplayer/room", {**self.signature(), "deviceId": "tv"})
        self.assertEqual(status, 201)
        room = json.loads(body)
        self.assertEqual(room["role"], "host")
        self.assertEqual(room["relay"], "http://127.0.0.1:8094")
        self.assertEqual(len(room["code"]), 6)

        status, body = self.request("GET", f"/api/multiplayer/room?code={room['code']}&token={room['token']}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["state"], "waiting")

        status, body = self.request("POST", "/api/multiplayer/join", {**self.signature(), "code": room["code"], "deviceId": "phone"})
        self.assertEqual(status, 200)
        guest = json.loads(body)
        self.assertEqual(guest["role"], "guest")
        self.assertNotEqual(guest["token"], room["token"])

        status, body = self.request("GET", f"/api/multiplayer/room?code={room['code']}&token={room['token']}")
        self.assertEqual(json.loads(body)["state"], "full")
        self.assertEqual(json.loads(body)["players"], 2)

    def test_incompatible_rom_hash_is_rejected(self):
        _, body = self.request("POST", "/api/multiplayer/room", self.signature())
        code = json.loads(body)["code"]
        status, body = self.request("POST", "/api/multiplayer/join", {**self.signature(rom_hash="b" * 64), "code": code})
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(body)["reason"], "incompatible")

    def test_unknown_room_is_404_and_invalid_signature_is_400(self):
        status, _ = self.request("POST", "/api/multiplayer/join", {**self.signature(), "code": "ZZZZZZ"})
        self.assertEqual(status, 404)
        status, _ = self.request("POST", "/api/multiplayer/room", {"system": "gba", "core": "mgba", "romHash": "nope"})
        self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/multiplayer/room", {"system": "bad system!", "core": "mgba", "romHash": "sha256:" + "a" * 64})
        self.assertEqual(status, 400)

    def test_status_requires_a_valid_token(self):
        _, body = self.request("POST", "/api/multiplayer/room", self.signature())
        code = json.loads(body)["code"]
        status, _ = self.request("GET", f"/api/multiplayer/room?code={code}&token=wrong")
        self.assertEqual(status, 404)
        status, _ = self.request("GET", "/api/multiplayer/room")
        self.assertEqual(status, 404)

    def test_disabled_outside_staging_serves_404(self):
        with patch.object(app, "MULTIPLAYER_ENABLED", False):
            status, _ = self.request("POST", "/api/multiplayer/room", self.signature())
            self.assertEqual(status, 404)
            status, _ = self.request("GET", "/api/multiplayer/room?code=X&token=Y")
            self.assertEqual(status, 404)
            status, _ = self.request("POST", "/api/multiplayer/join", {**self.signature(), "code": "ABC123"})
            self.assertEqual(status, 404)

    def test_host_leave_ends_room_and_leave_is_idempotent(self):
        _, body = self.request("POST", "/api/multiplayer/room", {**self.signature(), "deviceId": "tv"})
        room = json.loads(body)
        status, _ = self.request("POST", "/api/multiplayer/leave", {"code": room["code"], "token": room["token"]})
        self.assertEqual(status, 200)
        self.assertNotIn(room["code"], self.rooms.rooms)
        status, _ = self.request("POST", "/api/multiplayer/leave", {"code": room["code"], "token": room["token"]})
        self.assertEqual(status, 200)

    def test_guest_leave_keeps_the_room_open_for_rejoin(self):
        _, body = self.request("POST", "/api/multiplayer/room", self.signature())
        room = json.loads(body)
        _, body = self.request("POST", "/api/multiplayer/join", {**self.signature(), "code": room["code"], "deviceId": "phone"})
        guest = json.loads(body)
        status, _ = self.request("POST", "/api/multiplayer/leave", {"code": room["code"], "token": guest["token"]})
        self.assertEqual(status, 200)
        self.assertIn(room["code"], self.rooms.rooms)
        status, body = self.request("GET", f"/api/multiplayer/room?code={room['code']}&token={room['token']}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["state"], "waiting")


class ControllerApiTests(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch.object(app, "CONTROLLER_ENABLED", True),
            patch.object(app, "CONTROLLERS", {}),
        ]
        for active in self.patches:
            active.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        for active in self.patches:
            active.stop()

    def request(self, method, path, payload=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if body else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        status, data = response.status, response.read()
        connection.close()
        return status, data

    def _session(self):
        status, body = self.request("POST", "/api/controller/session", {"deviceId": "host"})
        self.assertEqual(status, 201)
        return json.loads(body)

    def test_pair_submit_and_latest_wins(self):
        session = self._session()
        self.assertEqual(len(session["code"]), 6)
        status, body = self.request("POST", "/api/controller/pair", {"code": session["code"], "deviceId": "phone"})
        self.assertEqual(status, 200)
        phone = json.loads(body)

        status, body = self.request("POST", "/api/controller/state", {"code": session["code"], "token": phone["token"], "s": 2, "b": ["a"]})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["applied"])
        # A duplicate/older frame is accepted but not applied.
        status, body = self.request("POST", "/api/controller/state", {"code": session["code"], "token": phone["token"], "s": 2, "b": ["b"]})
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["applied"])

        status, body = self.request("GET", f"/api/controller/state?code={session['code']}&hostToken={session['hostToken']}")
        self.assertEqual(status, 200)
        state = json.loads(body)
        self.assertTrue(state["paired"])
        self.assertEqual(state["state"]["s"], 2)
        self.assertEqual(state["state"]["b"], ["a"])

    def test_host_state_requires_the_host_token(self):
        session = self._session()
        status, _ = self.request("GET", f"/api/controller/state?code={session['code']}&hostToken=wrong")
        self.assertEqual(status, 403)
        status, _ = self.request("GET", f"/api/controller/state?code={session['code']}")
        self.assertEqual(status, 403)

    def test_input_requires_a_paired_token(self):
        session = self._session()
        status, _ = self.request("POST", "/api/controller/state", {"code": session["code"], "token": "nope", "s": 1, "b": []})
        self.assertEqual(status, 403)

    def test_unknown_session_and_disabled(self):
        status, _ = self.request("POST", "/api/controller/pair", {"code": "ZZZZZZ"})
        self.assertEqual(status, 404)
        with patch.object(app, "CONTROLLER_ENABLED", False):
            status, _ = self.request("POST", "/api/controller/session", {})
            self.assertEqual(status, 404)
            status, _ = self.request("GET", "/api/controller/state?code=X&hostToken=Y")
            self.assertEqual(status, 404)

    def test_disconnect_stops_accepting_input(self):
        session = self._session()
        _, body = self.request("POST", "/api/controller/pair", {"code": session["code"]})
        phone = json.loads(body)
        status, _ = self.request("POST", "/api/controller/disconnect", {"code": session["code"]})
        self.assertEqual(status, 200)
        status, _ = self.request("POST", "/api/controller/state", {"code": session["code"], "token": phone["token"], "s": 1, "b": []})
        self.assertEqual(status, 403)

    def request_full(self, method, path):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        connection.request(method, path)
        response = connection.getresponse()
        status, headers, data = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return status, headers, data

    def test_qr_endpoint_serves_a_self_contained_svg(self):
        session = self._session()
        status, headers, body = self.request_full("GET", f"/api/controller/qr.svg?code={session['code']}")
        self.assertEqual(status, 200)
        self.assertIn("image/svg+xml", headers.get("Content-Type", ""))
        text = body.decode("utf-8")
        self.assertTrue(text.startswith("<svg "))
        self.assertIn("<path d=\"", text)
        self.assertNotIn("<script", text)

    def test_qr_endpoint_requires_a_code_and_is_disabled_in_production(self):
        status, _, _ = self.request_full("GET", "/api/controller/qr.svg")
        self.assertEqual(status, 400)
        with patch.object(app, "CONTROLLER_ENABLED", False):
            status, _, _ = self.request_full("GET", "/api/controller/qr.svg?code=ABC123")
            self.assertEqual(status, 404)

    def test_session_lifetime_is_bounded_by_the_request(self):
        for requested, expected in ((3600, 3600), (999999, 3600), (1, 60), (None, 120)):
            with self.subTest(requested=requested):
                payload = {"deviceId": "native"}
                if requested is not None:
                    payload["ttlSeconds"] = requested
                status, body = self.request("POST", "/api/controller/session", payload)
                self.assertEqual(status, 201)
                self.assertEqual(json.loads(body)["ttlSeconds"], expected)

    def test_session_create_consumes_its_body_on_a_keepalive_connection(self):
        # An unread POST body corrupts the next request line on the same
        # connection (the server sees the JSON as a bogus method).
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        body = json.dumps({"deviceId": "host"}).encode()
        connection.request("POST", "/api/controller/session", body=body, headers={"Content-Type": "application/json"})
        created = connection.getresponse()
        created.read()
        self.assertEqual(created.status, 201)
        connection.request("GET", "/health")
        health = connection.getresponse()
        payload = health.read()
        connection.close()
        self.assertEqual(health.status, 200)
        self.assertIn(b'"ok": true', payload)


class ControllerButtonParityTests(unittest.TestCase):
    """The native phone-controller host must map the same libretro indices."""

    def test_android_native_button_map_matches_the_web_controller(self):
        player = (ROOT / "static/player.js").read_text(encoding="utf-8")
        block = player[player.index("const controllerButtonIndex = {"):]
        block = block[:block.index("};")]
        web = {name: int(index) for name, index in re.findall(r"([a-z]+)\s*:\s*(\d+)", block)}
        kotlin = (
            ROOT
            / "native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/ControllerClient.kt"
        ).read_text(encoding="utf-8")
        native_block = kotlin[kotlin.index("val BUTTONS = mapOf("):]
        native_block = native_block[:native_block.index(")")]
        native = {name: int(index) for name, index in re.findall(r'"([a-z]+)"\s*to\s*(\d+)', native_block)}
        self.assertEqual(native, web)
        self.assertEqual(web["a"], 8)
        self.assertEqual(web["right"], 7)
        self.assertEqual(len(web), 12)

    def test_desktop_rust_button_map_matches_the_web_controller(self):
        player = (ROOT / "static/player.js").read_text(encoding="utf-8")
        block = player[player.index("const controllerButtonIndex = {"):]
        block = block[:block.index("};")]
        web = {name: int(index) for name, index in re.findall(r"([a-z]+)\s*:\s*(\d+)", block)}
        rust = (ROOT / "native-offline/src-tauri/src/controller_host.rs").read_text(encoding="utf-8")
        rust_block = rust[rust.index("const BUTTONS:"):]
        rust_block = rust_block[:rust_block.index("];")]
        native = {name: int(index) for name, index in re.findall(r'\("([a-z]+)",\s*(\d+)\)', rust_block)}
        self.assertEqual(native, web)
        self.assertEqual(len(native), 12)


class PlayerCspTests(unittest.TestCase):
    def test_netplay_websocket_origin_is_allowed(self):
        csp = app.player_content_security_policy("http://192.0.2.8:8094")
        self.assertIn(
            "connect-src 'self' blob: https://cdn.emulatorjs.org http://192.0.2.8:8094 ws://192.0.2.8:8094;",
            csp,
        )

    def test_secure_netplay_origin_uses_wss(self):
        csp = app.player_content_security_policy("https://relay.example")
        self.assertIn("https://relay.example wss://relay.example;", csp)
        self.assertNotIn("ws://relay.example", csp)

    def test_without_netplay_connect_src_stays_self_only(self):
        csp = app.player_content_security_policy("")
        self.assertIn("connect-src 'self' blob: https://cdn.emulatorjs.org;", csp)
        self.assertNotIn("ws://", csp)


if __name__ == "__main__":
    unittest.main()
