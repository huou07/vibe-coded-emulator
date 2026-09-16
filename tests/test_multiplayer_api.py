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


if __name__ == "__main__":
    unittest.main()
