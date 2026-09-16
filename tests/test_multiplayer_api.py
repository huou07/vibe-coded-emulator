import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import app
import netcode


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


if __name__ == "__main__":
    unittest.main()
