# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import http.client
import json
import os
import pathlib
import re
import tempfile
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

    def test_multiplayer_capability_is_per_core_and_conservative(self):
        # Only GBA is runtime-verified; everything else must not advertise a
        # Create Room button.
        self.assertTrue(app.multiplayer_capability("gba")["available"])
        self.assertEqual(app.multiplayer_capability("gba")["transport"], "relay")
        for system in ("gbc", "nds", "3ds", "switch", "html5", "unknown", ""):
            with self.subTest(system=system):
                capability = app.multiplayer_capability(system)
                self.assertFalse(capability["available"])
                self.assertEqual(capability["reason"], "Not available for this system")






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




class RoomClient:
    """One independent HTTP client identity: its own connection and device id.

    The two clients in each lifecycle test never share a socket, a token, or a
    device identity, so the assertions exercise the real two-peer product path
    rather than one connection talking to itself.
    """

    def __init__(self, address, device_id):
        self.address = address
        self.device_id = device_id
        self.cookies = {}

    def request(self, method, path, payload=None):
        connection = http.client.HTTPConnection(*self.address, timeout=5)
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if body else {}
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{key}={value}" for key, value in self.cookies.items())
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        status, data = response.status, response.read()
        for name, value in response.getheaders():
            if name.lower() == "set-cookie":
                token = value.split(";")[0]
                if "=" in token:
                    key, raw = token.split("=", 1)
                    self.cookies[key] = raw
        connection.close()
        return status, data

    def json(self, method, path, payload=None):
        status, data = self.request(method, path, payload)
        try:
            parsed = json.loads(data)
        except ValueError:
            parsed = None
        return status, parsed


class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class MultiplayerLifecycleApiTests(unittest.TestCase):
    """Real room lifecycle driven by two independent HTTP client contexts.

    Covers create/join, state transitions, member input/state flow, reconnect,
    stale-session cleanup, new-game supersession, malformed/duplicate messages,
    rate limiting and cross-user isolation.
    """

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
        self.host = RoomClient(self.server.server_address, "living-room-tv")
        self.guest = RoomClient(self.server.server_address, "phone-a")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        for active in self.patches:
            active.stop()

    @staticmethod
    def signature(rom_hash="a" * 64, **overrides):
        base = {"system": "gba", "core": "mgba", "romHash": "sha256:" + rom_hash}
        base.update(overrides)
        return base

    def create(self, client, **overrides):
        payload = {**self.signature(), "deviceId": client.device_id, **overrides}
        return client.json("POST", "/api/multiplayer/room", payload)

    def join(self, client, code, **overrides):
        payload = {**self.signature(), "code": code, "deviceId": client.device_id, **overrides}
        return client.json("POST", "/api/multiplayer/join", payload)

    def status(self, client, code, token):
        return client.json("GET", f"/api/multiplayer/room?code={code}&token={token}")

    # -- create / join / state transitions ---------------------------------

    def test_two_clients_drive_the_full_room_state_transitions(self):
        status, room = self.create(self.host)
        self.assertEqual(status, 201, room)
        code, host_token = room["code"], room["token"]

        status, body = self.status(self.host, code, host_token)
        self.assertEqual((status, body["state"], body["players"]), (200, "waiting", 1))

        status, guest = self.join(self.guest, code)
        self.assertEqual(status, 200, guest)
        self.assertEqual(guest["role"], "guest")
        self.assertNotEqual(guest["token"], host_token)

        _, host_view = self.status(self.host, code, host_token)
        _, guest_view = self.status(self.guest, code, guest["token"])
        self.assertEqual((host_view["state"], host_view["players"]), ("full", 2))
        self.assertEqual((guest_view["state"], guest_view["role"]), ("full", "guest"))

        # Guest disconnect keeps the host's room open and flips it to waiting.
        status, _ = self.guest.request("POST", "/api/multiplayer/leave", {"code": code, "token": guest["token"]})
        self.assertEqual(status, 200)
        _, host_view = self.status(self.host, code, host_token)
        self.assertEqual(host_view["state"], "waiting")

        # The same guest can rejoin the still-open room.
        status, guest = self.join(self.guest, code)
        self.assertEqual(status, 200, guest)
        self.assertEqual(self.status(self.host, code, host_token)[1]["state"], "full")

        # Host disconnect ends the room for everyone.
        status, _ = self.host.request("POST", "/api/multiplayer/leave", {"code": code, "token": host_token})
        self.assertEqual(status, 200)
        self.assertEqual(self.status(self.guest, code, guest["token"])[0], 404)

    def test_rejoining_with_the_same_device_reissues_instead_of_full(self):
        _, room = self.create(self.host)
        code = room["code"]
        status, first = self.join(self.guest, code)
        self.assertEqual(status, 200, first)

        status, second = self.join(self.guest, code)
        self.assertEqual(status, 200, second)
        self.assertNotEqual(second["token"], first["token"])
        self.assertEqual(self.status(self.guest, code, second["token"])[1]["role"], "guest")

        other = RoomClient(self.server.server_address, "tablet-b")
        status, _ = self.join(other, code)
        self.assertEqual(status, 404)

    # -- reconnect / background-resume -------------------------------------

    def test_reconnect_resumes_a_member_and_rotates_the_token(self):
        _, room = self.create(self.host)
        code, host_token = room["code"], room["token"]
        _, guest = self.join(self.guest, code)
        old_guest = guest["token"]

        status, resumed = self.guest.json("POST", "/api/multiplayer/reconnect", {"code": code, "token": old_guest})
        self.assertEqual(status, 200, resumed)
        self.assertEqual(resumed["role"], "guest")
        self.assertNotEqual(resumed["token"], old_guest)

        # Rotation retires the previous token, so a leaked token cannot persist.
        self.assertEqual(self.status(self.guest, code, old_guest)[0], 404)
        self.assertEqual(self.status(self.guest, code, resumed["token"])[0], 200)

        # The host resumes the same way, and role identity is preserved.
        status, resumed_host = self.host.json("POST", "/api/multiplayer/reconnect", {"code": code, "token": host_token})
        self.assertEqual(status, 200, resumed_host)
        self.assertEqual(resumed_host["role"], "host")

        # A non-member cannot claim a role with a guessed token.
        self.assertEqual(
            self.guest.request("POST", "/api/multiplayer/reconnect", {"code": code, "token": "guessed"})[0], 403
        )
        # A closed room cannot be resumed.
        self.host.request("POST", "/api/multiplayer/leave", {"code": code, "token": resumed_host["token"]})
        self.assertEqual(
            self.guest.request("POST", "/api/multiplayer/reconnect", {"code": code, "token": resumed["token"]})[0], 404
        )

    # -- real member input / state flow ------------------------------------

    def test_member_input_flows_between_peers_with_dedup_and_malformed_rejection(self):
        _, room = self.create(self.host)
        code, host_token = room["code"], room["token"]
        _, guest = self.join(self.guest, code)
        guest_token = guest["token"]

        status, applied = self.guest.json(
            "POST", "/api/multiplayer/input",
            {"code": code, "token": guest_token, "s": 4, "b": ["a"], "a": [0.5, 0, 0, 0]},
        )
        self.assertEqual(status, 200, applied)
        self.assertTrue(applied["applied"])
        self.assertEqual(applied["role"], "guest")

        status, state = self.host.json("GET", f"/api/multiplayer/state?code={code}&token={host_token}")
        self.assertEqual(status, 200, state)
        self.assertEqual(state["role"], "host")
        self.assertEqual(state["peer"]["s"], 4)
        self.assertEqual(state["peer"]["b"], ["a"])
        self.assertAlmostEqual(state["peer"]["a"][0], 0.5)

        # Duplicate and stale frames are accepted but never re-applied.
        for sequence in (4, 2):
            status, replayed = self.guest.json(
                "POST", "/api/multiplayer/input",
                {"code": code, "token": guest_token, "s": sequence, "b": ["b"]},
            )
            self.assertEqual(status, 200)
            self.assertFalse(replayed["applied"])

        # The host publishes its own snapshot; the guest sees it as its peer.
        status, host_applied = self.host.json(
            "POST", "/api/multiplayer/input",
            {"code": code, "token": host_token, "s": 1, "b": ["start"]},
        )
        self.assertEqual(status, 200)
        self.assertTrue(host_applied["applied"])
        _, guest_state = self.guest.json("GET", f"/api/multiplayer/state?code={code}&token={guest_token}")
        self.assertEqual(guest_state["peer"]["s"], 1)
        self.assertEqual(guest_state["peer"]["b"], ["start"])
        # A member's own stream is reported separately from the peer's.
        self.assertEqual(guest_state["self"]["s"], 4)

        # Malformed frames are rejected before they can enter the channel.
        status, _ = self.guest.json(
            "POST", "/api/multiplayer/input",
            {"code": code, "token": guest_token, "s": 9, "a": [0, 0]},
        )
        self.assertEqual(status, 400)
        status, _ = self.guest.json(
            "POST", "/api/multiplayer/input", {"code": code, "token": guest_token, "b": ["a"]}
        )
        self.assertEqual(status, 400)

        # An unauthorized client cannot inject input into the room.
        status, _ = self.host.json(
            "POST", "/api/multiplayer/input", {"code": code, "token": "not-a-member", "s": 10, "b": []}
        )
        self.assertEqual(status, 403)
        _, state = self.host.json("GET", f"/api/multiplayer/state?code={code}&token={host_token}")
        self.assertEqual(state["peer"]["s"], 4)

    # -- stale cleanup / new game ------------------------------------------

    def test_expired_rooms_are_reaped_on_the_next_request(self):
        clock = FakeClock()
        rooms = netcode.RoomService(clock=clock, room_ttl_seconds=100)
        with patch.object(app, "ROOMS", rooms):
            status, room = self.create(self.host)
            self.assertEqual(status, 201, room)
            self.assertIn(room["code"], rooms.rooms)
            clock.advance(101)
            # A later unrelated request reaps the stale room globally.
            self.create(self.guest)
            self.assertNotIn(room["code"], rooms.rooms)
            self.assertEqual(self.status(self.host, room["code"], room["token"])[0], 404)

    def test_a_new_game_replaces_the_hosts_previous_room(self):
        _, first = self.create(self.host)
        _, second = self.create(self.host)
        self.assertNotEqual(first["code"], second["code"])
        self.assertNotIn(first["code"], self.rooms.rooms)
        self.assertIn(second["code"], self.rooms.rooms)
        self.assertEqual(self.status(self.host, first["code"], first["token"])[0], 404)

    # -- malformed / replay ------------------------------------------------

    def test_malformed_bodies_and_signatures_never_create_a_room(self):
        for body in (b"{not json", b"", b"[1,2,3]"):
            connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
            connection.request("POST", "/api/multiplayer/room", body=body,
                               headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            status = response.status
            response.read()
            connection.close()
            self.assertEqual(status, 400, body)
        self.assertEqual(self.create(self.host, romHash="not-a-hash")[0], 400)
        self.assertEqual(self.create(self.host, system="bad system!")[0], 400)
        status, _ = self.host.json("POST", "/api/multiplayer/join", {"code": "ZZZZZZ", **self.signature()})
        self.assertEqual(status, 404)

    # -- rate limiting -----------------------------------------------------

    def test_create_and_join_are_rate_limited_independently(self):
        rooms = netcode.RoomService(
            join_limiter=netcode.SlidingRateLimiter(limit=2, window_seconds=60),
            create_limiter=netcode.SlidingRateLimiter(limit=2, window_seconds=60),
        )
        with patch.object(app, "ROOMS", rooms):
            for _ in range(2):
                self.assertEqual(self.create(self.host)[0], 201)
            self.assertEqual(self.create(self.host)[0], 429)

            # The create limiter must not have consumed the join budget.
            room, _ = rooms.create_room(
                netcode.GameSignature(system="gba", core="mgba", rom_hash="sha256:" + "a" * 64), "tv"
            )
            for _ in range(2):
                self.assertEqual(self.join(self.guest, room.code)[0], 200)
            self.assertEqual(self.join(self.guest, room.code)[0], 429)

    # -- cross-user isolation ----------------------------------------------

    def test_role_tokens_are_isolated(self):
        _, room = self.create(self.host)
        code, host_token = room["code"], room["token"]
        _, guest = self.join(self.guest, code)

        # A guest token cannot close the host's room.
        self.guest.request("POST", "/api/multiplayer/leave", {"code": code, "token": guest["token"]})
        self.assertIn(code, self.rooms.rooms)
        self.assertEqual(self.status(self.host, code, host_token)[1]["state"], "waiting")

        # A wrong token never resolves to a member role, on either surface.
        self.assertEqual(self.status(self.guest, code, "wrong")[0], 404)
        self.assertEqual(
            self.guest.request("POST", "/api/multiplayer/leave", {"code": code, "token": "wrong"})[0], 200
        )
        self.assertIn(code, self.rooms.rooms)



if __name__ == "__main__":
    unittest.main()
