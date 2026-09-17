# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

import netcode as nc
import sync_engine as se


class Clock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class CodeTests(unittest.TestCase):
    def test_pairing_codes_are_six_digits_and_allow_leading_zeroes(self):
        for _ in range(200):
            code = nc.generate_pairing_code()
            self.assertEqual(len(code), 6)
            self.assertTrue(code.isdigit(), code)
            self.assertTrue(nc.is_pairing_code(code))
        # A leading zero is a valid code, and the digit draw is unbiased.
        self.assertEqual(nc.generate_pairing_code(6, randbelow=lambda n: 0), "000000")
        self.assertEqual(nc.generate_pairing_code(2, randbelow=lambda n: 9), "99")
        self.assertFalse(nc.is_pairing_code(""))
        self.assertFalse(nc.is_pairing_code("ABCD12"))
        self.assertFalse(nc.is_pairing_code("12345"))
        self.assertFalse(nc.is_pairing_code("1234567"))

    def test_room_codes_avoid_ambiguous_characters_and_have_the_right_length(self):
        code = nc.generate_room_code(8)
        self.assertEqual(len(code), 8)
        for character in code:
            self.assertIn(character, nc.CODE_ALPHABET)
        for ambiguous in "ILOU":
            self.assertNotIn(ambiguous, nc.CODE_ALPHABET)

    def test_generation_is_injectable_for_determinism(self):
        code = nc.generate_room_code(4, randbelow=lambda n: 0)
        self.assertEqual(code, nc.CODE_ALPHABET[0] * 4)
        with self.assertRaises(nc.NetcodeError):
            nc.generate_room_code(0)
        with self.assertRaises(nc.NetcodeError):
            nc.generate_pairing_code(0)

    def test_pairing_code_generation_uses_a_secure_ten_way_draw(self):
        draws = []
        nc.generate_pairing_code(6, randbelow=lambda n: (draws.append(n), 3)[1])
        self.assertTrue(draws and all(value == 10 for value in draws), draws)

    def test_normalize_code_is_forgiving(self):
        self.assertEqual(nc.normalize_code(" ab-cd 12 "), "ABCD12")
        self.assertEqual(nc.normalize_code(" 482 193 "), "482193")


class TokenTests(unittest.TestCase):
    def test_new_token_digest_matches_and_raw_is_not_the_digest(self):
        token, digest = nc.new_session_token()
        self.assertEqual(digest, nc.token_digest(token))
        self.assertNotEqual(token, digest)
        self.assertNotIn(token, digest)


class RateLimiterTests(unittest.TestCase):
    def test_blocks_after_limit_and_recovers_after_window(self):
        clock = Clock()
        limiter = nc.SlidingRateLimiter(limit=2, window_seconds=10, clock=clock)
        limiter.check("a")
        limiter.check("a")
        with self.assertRaises(nc.RateLimitedError):
            limiter.check("a")
        clock.advance(11)
        limiter.check("a")

    def test_requires_positive_configuration(self):
        with self.assertRaises(nc.NetcodeError):
            nc.SlidingRateLimiter(limit=0, window_seconds=1)


class ControllerWireTests(unittest.TestCase):
    def test_zero_axes_are_omitted_from_the_wire(self):
        state = nc.ControllerState(sequence=1, buttons=frozenset({nc.PadButton.A.value}))
        wire = state.to_wire()
        self.assertNotIn("a", wire)
        self.assertEqual(wire["s"], 1)

    def test_axes_are_included_when_present_and_round_trip(self):
        state = nc.ControllerState(sequence=5, buttons=frozenset({"a", "start"}),
                                   left_x=0.5, left_y=-0.25)
        wire = state.to_wire()
        self.assertEqual(wire["a"], [0.5, -0.25, 0, 0])
        restored = nc.ControllerState.from_wire(wire)
        self.assertEqual(restored.sequence, 5)
        self.assertEqual(restored.buttons, frozenset({"a", "start"}))
        self.assertAlmostEqual(restored.left_x, 0.5)

    def test_malformed_frames_are_rejected(self):
        with self.assertRaises(nc.NetcodeError):
            nc.ControllerState.from_wire({"b": ["a"]})
        with self.assertRaises(nc.NetcodeError):
            nc.ControllerState.from_wire({"s": 1, "a": [0, 0]})

    def test_touch_tuple_round_trips_and_absence_means_released(self):
        state = nc.ControllerState(sequence=3, buttons=frozenset(), touch_active=True, touch_x=0.25, touch_y=0.75)
        wire = state.to_wire()
        self.assertEqual(wire["t"], [0.25, 0.75])
        restored = nc.ControllerState.from_wire(wire)
        self.assertTrue(restored.touch_active)
        self.assertAlmostEqual(restored.touch_x, 0.25)
        self.assertAlmostEqual(restored.touch_y, 0.75)
        self.assertFalse(nc.ControllerState.from_wire({"s": 4, "b": []}).touch_active)
        with self.assertRaises(nc.NetcodeError):
            nc.ControllerState.from_wire({"s": 5, "b": [], "t": [0.1]})


class ControllerSessionTests(unittest.TestCase):
    def _session(self, clock):
        return nc.ControllerSession(code="ABC123", host_device_id="tv", created_at=clock(), clock=clock)

    def test_pair_authenticate_and_disconnect(self):
        clock = Clock()
        session = self._session(clock)
        token = session.pair("phone")
        self.assertTrue(session.paired)
        self.assertTrue(session.authenticate(token))
        self.assertFalse(session.authenticate("wrong"))
        session.disconnect()
        self.assertFalse(session.paired)

    def test_latest_state_wins_and_stale_frames_are_dropped(self):
        clock = Clock()
        session = self._session(clock)
        token = session.pair("phone")
        first = session.accept_state({"s": 2, "b": ["a"]}, token=token)
        self.assertIsNotNone(first)
        duplicate = session.accept_state({"s": 2, "b": ["b"]}, token=token)
        self.assertIsNone(duplicate)
        stale = session.accept_state({"s": 1, "b": ["start"]}, token=token)
        self.assertIsNone(stale)
        newest = session.accept_state({"s": 9, "b": ["start"]}, token=token)
        self.assertEqual(newest.sequence, 9)
        self.assertEqual(session.current_buttons(), frozenset({"start"}))

    def test_input_is_active_only_after_the_host_acknowledges(self):
        clock = Clock()
        session = self._session(clock)
        token = session.pair("phone")
        session.accept_state({"s": 4, "b": ["a"]}, token=token)
        self.assertFalse(session.input_active())
        self.assertEqual(session.ack(4), 4)
        self.assertTrue(session.input_active())
        # An out-of-order acknowledgement cannot move backwards.
        self.assertEqual(session.ack(2), 4)
        # The host may lag by a frame or two, but a host whose input path stops
        # advancing must fall out of the live window.
        session.accept_state({"s": 7, "b": ["a"]}, token=token)
        self.assertFalse(session.input_active())
        session.ack(7)
        self.assertTrue(session.input_active())
        session.disconnect()
        self.assertFalse(session.input_active())

    def test_input_requires_a_valid_token(self):
        clock = Clock()
        session = self._session(clock)
        session.pair("phone")
        with self.assertRaises(nc.NotPairedError):
            session.accept_state({"s": 1, "b": []}, token="nope")

    def test_expired_pairing_is_rejected(self):
        clock = Clock()
        session = nc.ControllerSession(code="X", host_device_id="tv", created_at=clock(),
                                       ttl_seconds=30, clock=clock)
        clock.advance(31)
        self.assertTrue(session.is_expired())
        with self.assertRaises(nc.ExpiredError):
            session.pair("phone")

    def test_host_requests_resync_until_first_frame(self):
        clock = Clock()
        session = self._session(clock)
        token = session.pair("phone")
        self.assertTrue(session.needs_resync())
        session.accept_state({"s": 1, "b": []}, token=token)
        self.assertFalse(session.needs_resync())


def signature(**kwargs):
    base = dict(system="gba", core="mgba", rom_hash="sha256:abc")
    base.update(kwargs)
    return nc.GameSignature(**base)


class RoomServiceTests(unittest.TestCase):
    def _service(self, clock):
        return nc.RoomService(clock=clock, room_ttl_seconds=100)

    def test_create_and_join_with_matching_signature(self):
        clock = Clock()
        service = self._service(clock)
        room, host_token = service.create_room(signature(), "tv")
        joined, guest_token = service.join_room(room.code, signature(), "phone")
        self.assertTrue(joined.full)
        self.assertEqual(service.authenticate(room.code, host_token), nc.RoomRole.HOST)
        self.assertEqual(service.authenticate(room.code, guest_token), nc.RoomRole.GUEST)

    def test_incompatible_game_is_rejected_before_session(self):
        clock = Clock()
        service = self._service(clock)
        room, _ = service.create_room(signature(rom_hash="sha256:a"), "tv")
        with self.assertRaises(nc.IncompatibleError):
            service.join_room(room.code, signature(rom_hash="sha256:b"), "phone")
        with self.assertRaises(nc.IncompatibleError):
            service.join_room(room.code, signature(system="nds", core="melonds"), "phone")
        self.assertFalse(room.full)

    def test_unknown_and_full_rooms_fail(self):
        clock = Clock()
        service = self._service(clock)
        with self.assertRaises(nc.NetcodeError):
            service.join_room("ZZZZZZ", signature(), "phone")
        room, _ = service.create_room(signature(), "tv")
        service.join_room(room.code, signature(), "phone")
        with self.assertRaises(nc.NetcodeError):
            service.join_room(room.code, signature(), "tablet")

    def test_expiry_is_enforced_and_reaped(self):
        clock = Clock()
        service = self._service(clock)
        room, _ = service.create_room(signature(), "tv")
        code = room.code
        clock.advance(101)
        with self.assertRaises(nc.ExpiredError):
            service.join_room(code, signature(), "phone")
        self.assertEqual(service.reap(), [])

    def test_host_leaving_ends_room_and_guest_leaving_keeps_host(self):
        clock = Clock()
        service = self._service(clock)
        room, host_token = service.create_room(signature(), "tv")
        service.join_room(room.code, signature(), "phone")
        service.leave(room.code, nc.RoomRole.GUEST)
        self.assertFalse(room.full)
        self.assertEqual(service.authenticate(room.code, host_token), nc.RoomRole.HOST)
        service.leave(room.code, nc.RoomRole.HOST)
        self.assertNotIn(room.code, service.rooms)

    def test_reconnect_reissues_only_for_known_devices(self):
        clock = Clock()
        service = self._service(clock)
        room, _ = service.create_room(signature(), "tv")
        service.join_room(room.code, signature(), "phone")
        _, token = service.reconnect(room.code, signature(), "phone")
        self.assertEqual(service.authenticate(room.code, token), nc.RoomRole.GUEST)
        with self.assertRaises(nc.NotPairedError):
            service.reconnect(room.code, signature(), "stranger")

    def test_join_rate_limit_applies(self):
        clock = Clock()
        service = nc.RoomService(clock=clock, room_ttl_seconds=100,
                                 join_limiter=nc.SlidingRateLimiter(limit=1, window_seconds=60, clock=clock))
        room, _ = service.create_room(signature(), "tv")
        service.join_room(room.code, signature(), "phone-a", client_key="1.2.3.4")
        with self.assertRaises(nc.RateLimitedError):
            service.join_room(room.code, signature(), "phone-b", client_key="1.2.3.4")

    def test_signature_compatibility(self):
        self.assertTrue(signature().compatible_with(signature()))
        self.assertFalse(signature().compatible_with(signature(rom_hash="other")))
        self.assertFalse(signature().compatible_with(signature(core="other-core")))
        self.assertFalse(signature().compatible_with(signature(system="nds")))


class TransportChoiceTests(unittest.TestCase):
    def test_reuses_sync_engine_lan_preference(self):
        self.assertEqual(nc.choose_transport(se.SyncMode.LAN_DRIVE, same_lan=True), se.Transport.LAN)
        self.assertEqual(nc.choose_transport(se.SyncMode.LAN_DRIVE, same_lan=False), se.Transport.DRIVE)
        self.assertIsNone(nc.choose_transport(se.SyncMode.OFF, same_lan=True))


if __name__ == "__main__":
    unittest.main()
