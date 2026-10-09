# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared networking core for multiplayer rooms.

Section 13 of the product spec asks for one reusable layer (discovery,
pairing/session identity, transport choice, auth, lifecycle) *without*
flattening protocols that have genuinely different needs. This module provides
that shared layer:

* :func:`generate_pairing_code` / :func:`generate_room_code` — short, unbiased,
  ambiguity-free human codes.
* :func:`new_session_token` / :func:`token_digest` — bearer tokens that are
  stored only as a SHA-256 digest server-side.
* :class:`SlidingRateLimiter` — bounded request throttling.
* :class:`RoomService` — short-lived room codes with core/ROM-hash
  compatibility validation and reconnect handling.

Transport is intentionally *not* implemented here. Netplay picks its own
transport; this module owns room identity, validation, and lifecycle.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple



# Crockford-style alphabet: no I, L, O, U to avoid transcription errors.
CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class NetcodeError(RuntimeError):
    pass


class NotPairedError(NetcodeError):
    pass


class IncompatibleError(NetcodeError):
    pass


class ExpiredError(NetcodeError):
    pass


class RateLimitedError(NetcodeError):
    pass


def _generate_code(length: int, *, randbelow: Callable[[int], int] = secrets.randbelow) -> str:
    if length <= 0:
        raise NetcodeError("code length must be positive")
    return "".join(CODE_ALPHABET[randbelow(len(CODE_ALPHABET))] for _ in range(length))


def generate_room_code(length: int = 6, *, randbelow: Callable[[int], int] = secrets.randbelow) -> str:
    return _generate_code(length, randbelow=randbelow)


def normalize_code(code: str) -> str:
    """Uppercase and strip spaces/dashes so typing the code is forgiving."""

    return "".join(character for character in str(code or "").upper()
                   if character.isalnum())


def token_digest(token: str) -> str:
    """Digest used for at-rest storage. Raw tokens are never persisted."""

    return hashlib.sha256(("vibe-controller:" + str(token)).encode("utf-8")).hexdigest()


def new_session_token() -> Tuple[str, str]:
    """Return ``(token, digest)``. Only the digest should be stored."""

    token = secrets.token_urlsafe(32)
    return token, token_digest(token)


class SlidingRateLimiter:
    """A small fixed-window limiter keyed by client identity.

    Not a substitute for an edge rate limit, but it keeps a single abusive
    client from exhausting a per-room or per-pairing operation. The key space
    is bounded by ``max_keys``: once that many distinct identities are tracked,
    fully expired buckets are dropped first and then the least-recently-seen
    buckets are evicted, so a flood of distinct source identities cannot grow
    the process without bound. The identity being checked is always preserved.
    """

    def __init__(self, *, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic,
                 max_keys: int = 1024):
        if limit <= 0 or window_seconds <= 0:
            raise NetcodeError("rate limiter needs a positive limit and window")
        if max_keys <= 0:
            raise NetcodeError("rate limiter needs a positive key cap")
        self.limit = limit
        self.window = window_seconds
        self.clock = clock
        self.max_keys = max_keys
        self._buckets: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        with self._lock:
            now = self.clock()
            events = [stamp for stamp in self._buckets.get(key, []) if now - stamp < self.window]
            limited = len(events) >= self.limit
            if not limited:
                events.append(now)
            self._buckets[key] = events
            self._prune(now, key)
            if limited:
                raise RateLimitedError("too many attempts; try again shortly")

    def reset(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)

    def _prune(self, now: float, preserve: str) -> None:
        """Keep the key space bounded; callers must hold ``self._lock``."""

        if len(self._buckets) <= self.max_keys:
            return
        for name in list(self._buckets):
            events = self._buckets[name]
            if name != preserve and (not events or now - events[-1] >= self.window):
                self._buckets.pop(name, None)
        overflow = len(self._buckets) - self.max_keys
        if overflow <= 0:
            return
        evictable = sorted(
            (name for name in self._buckets if name != preserve),
            key=lambda name: self._buckets[name][-1] if self._buckets[name] else now - self.window,
        )
        for name in evictable[:overflow]:
            self._buckets.pop(name, None)


# ---------------------------------------------------------------------------
# Multiplayer game input
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ControllerState:
    """One controller snapshot.

    Analogue axes are -1.0..1.0. ``touch_*`` is the normalized 0..1 position of
    the single stylus finger on the host's touch screen (NDS/3DS). A frame that
    omits the touch tuple means "released", because every frame is a complete
    snapshot rather than a delta.
    """

    sequence: int
    buttons: frozenset
    left_x: float = 0.0
    left_y: float = 0.0
    right_x: float = 0.0
    right_y: float = 0.0
    sent_at: float = 0.0
    received_at: float = 0.0
    touch_active: bool = False
    touch_x: float = 0.0
    touch_y: float = 0.0

    def to_wire(self) -> dict:
        """Compact payload: short keys, omitted zero axes, touch when pressed."""

        payload = {"s": self.sequence, "b": sorted(self.buttons)}
        axes = []
        for value in (self.left_x, self.left_y, self.right_x, self.right_y):
            axes.append(round(value, 3) if value else 0)
        if any(axes):
            payload["a"] = axes
        if self.touch_active:
            payload["t"] = [round(self.touch_x, 4), round(self.touch_y, 4)]
        return payload

    @classmethod
    def from_wire(cls, payload: dict, *, received_at: float = 0.0) -> "ControllerState":
        try:
            sequence = int(payload["s"])
        except (KeyError, TypeError, ValueError) as error:
            raise NetcodeError("input frame is missing a sequence") from error
        axes = payload.get("a") or [0, 0, 0, 0]
        if len(axes) != 4:
            raise NetcodeError("input frame has an invalid axis tuple")
        touch = payload.get("t")
        touch_active = False
        touch_x = touch_y = 0.0
        if touch is not None:
            if not isinstance(touch, (list, tuple)) or len(touch) != 2:
                raise NetcodeError("input frame has an invalid touch tuple")
            try:
                touch_x = min(1.0, max(0.0, float(touch[0])))
                touch_y = min(1.0, max(0.0, float(touch[1])))
            except (TypeError, ValueError) as error:
                raise NetcodeError("input frame has a non-numeric touch tuple") from error
            touch_active = True
        return cls(
            sequence=sequence,
            buttons=frozenset(str(name) for name in payload.get("b") or []),
            left_x=float(axes[0]), left_y=float(axes[1]),
            right_x=float(axes[2]), right_y=float(axes[3]),
            received_at=received_at,
            touch_active=touch_active, touch_x=touch_x, touch_y=touch_y,
        )


# ---------------------------------------------------------------------------
# Rooms / invite codes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GameSignature:
    """What must match before two peers may share a netplay session."""

    system: str
    core: str
    rom_hash: str
    version: str = ""

    def compatible_with(self, other: "GameSignature") -> bool:
        return (self.system == other.system
                and self.core == other.core
                and self.rom_hash == other.rom_hash)


class RoomRole(str, Enum):
    HOST = "host"
    GUEST = "guest"


@dataclass
class Room:
    code: str
    signature: GameSignature
    host_device_id: str
    created_at: float
    ttl_seconds: float = 900.0
    guest_device_id: str = ""
    _host_token_digest: str = ""
    _guest_token_digest: str = ""
    # Latest coalesced input snapshot per member. This is a resume/checkpoint
    # anchor, not the live transport: the live input path is the relay (RG-086).
    # It lets a peer that dropped and reconnected read the other peer's newest
    # frame instead of replaying relay history.
    _host_input: Optional[ControllerState] = None
    _guest_input: Optional[ControllerState] = None
    # The relay/signaling hint is deliberately opaque. A raw host IP is never
    # stored here so a room code cannot be used to discover a peer's address.
    signaling_hint: str = ""
    clock: Callable[[], float] = time.monotonic

    def is_expired(self) -> bool:
        return self.clock() - self.created_at > self.ttl_seconds

    @property
    def full(self) -> bool:
        return bool(self._guest_token_digest)

    def publish_input(self, role: "RoomRole", frame: dict) -> Optional[ControllerState]:
        """Store one member's latest snapshot; duplicates and stale frames drop.

        Returns the applied state, or ``None`` when the frame was older than the
        member's current one. The guest publishes its own input; the host reads
        it, and vice versa. The frame shares the canonical controller wire
        format, so it is validated before it can enter the channel.
        """

        state = ControllerState.from_wire(frame, received_at=self.clock())
        current = self._host_input if role is RoomRole.HOST else self._guest_input
        if current is not None and state.sequence <= current.sequence:
            return None
        if role is RoomRole.HOST:
            self._host_input = state
        else:
            self._guest_input = state
        return state

    def latest_input(self, role: "RoomRole") -> Optional[ControllerState]:
        return self._host_input if role is RoomRole.HOST else self._guest_input

    def reset_input(self, role: "Optional[RoomRole]" = None) -> None:
        """Drop one member's checkpoint, or both when ``role`` is omitted."""

        if role is None or role is RoomRole.HOST:
            self._host_input = None
        if role is None or role is RoomRole.GUEST:
            self._guest_input = None


class RoomService:
    """Creates and joins short-lived, compatibility-checked rooms.

    All operations are serialized so two peers joining, leaving, or publishing
    input at the same time cannot corrupt a room. A room is bounded by its TTL;
    every mutating or reading call first reaps expired rooms, so stale sessions
    never linger after they can no longer be used.
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic,
                 code_length: int = 6,
                 room_ttl_seconds: float = 900.0,
                 join_limiter: Optional[SlidingRateLimiter] = None,
                 create_limiter: Optional[SlidingRateLimiter] = None):
        self.clock = clock
        self.code_length = code_length
        self.room_ttl_seconds = room_ttl_seconds
        self.rooms: Dict[str, Room] = {}
        self.join_limiter = join_limiter or SlidingRateLimiter(
            limit=10, window_seconds=60.0, clock=clock)
        self.create_limiter = create_limiter or SlidingRateLimiter(
            limit=10, window_seconds=60.0, clock=clock)
        self._lock = threading.RLock()

    def _new_code(self) -> str:
        for _ in range(100):
            code = generate_room_code(self.code_length)
            if code not in self.rooms:
                return code
        raise NetcodeError("could not allocate a unique room code")

    def _supersede_host_rooms(self, host_device_id: str) -> None:
        """A host starting a new game replaces its own previous room.

        Without this, an abrupt page close (game exit, crash, background kill)
        leaves an unreachable room occupying a code until its TTL expires.
        Rooms hosted by anonymous callers (empty device id) are never touched
        because they cannot be attributed to one device.
        """

        if not host_device_id:
            return
        for code, room in list(self.rooms.items()):
            if room.host_device_id == host_device_id:
                self.rooms.pop(code, None)

    def create_room(self, signature: GameSignature, host_device_id: str,
                    *, signaling_hint: str = "", client_key: str = "anonymous") -> Tuple[Room, str]:
        host_device_id = str(host_device_id)
        with self._lock:
            self.create_limiter.check(client_key)
            self.reap()
            self._supersede_host_rooms(host_device_id)
            room = Room(
                code=self._new_code(),
                signature=signature,
                host_device_id=host_device_id,
                created_at=self.clock(),
                ttl_seconds=self.room_ttl_seconds,
                signaling_hint=signaling_hint,
                clock=self.clock,
            )
            token, digest = new_session_token()
            room._host_token_digest = digest
            self.rooms[room.code] = room
            return room, token

    def join_room(self, code: str, signature: GameSignature, guest_device_id: str,
                  *, client_key: str = "anonymous") -> Tuple[Room, str]:
        guest_device_id = str(guest_device_id)
        with self._lock:
            self.join_limiter.check(client_key)
            reaped = self.reap()
            normalized = normalize_code(code)
            room = self.rooms.get(normalized)
            if room is None:
                # Preserve the difference between "never existed" and "expired":
                # the client shows a different message for each.
                if normalized in reaped:
                    raise ExpiredError("room expired")
                raise NetcodeError("room not found")
            if room.is_expired():
                self.rooms.pop(normalized, None)
                raise ExpiredError("room expired")
            if room.full:
                # The same device rejoining is a resume, not a second player.
                if guest_device_id and room.guest_device_id == guest_device_id:
                    token, digest = new_session_token()
                    room._guest_token_digest = digest
                    return room, token
                raise NetcodeError("room is full")
            # Compatibility is checked before any session is established, and the
            # system never transfers the ROM to satisfy it.
            if not room.signature.compatible_with(signature):
                raise IncompatibleError(
                    "the game or core does not match the host session")
            room.guest_device_id = guest_device_id
            token, digest = new_session_token()
            room._guest_token_digest = digest
            return room, token

    def authenticate(self, code: str, token: str) -> RoomRole:
        with self._lock:
            room = self.rooms.get(normalize_code(code))
            if room is None:
                raise NetcodeError("room not found")
            if room.is_expired():
                self.rooms.pop(room.code, None)
                raise ExpiredError("room expired")
            digest = token_digest(token)
            if room._host_token_digest and hmac.compare_digest(room._host_token_digest, digest):
                return RoomRole.HOST
            if room._guest_token_digest and hmac.compare_digest(room._guest_token_digest, digest):
                return RoomRole.GUEST
            raise NotPairedError("room token rejected")

    def leave(self, code: str, role: RoomRole) -> None:
        with self._lock:
            room = self.rooms.get(normalize_code(code))
            if room is None:
                return
            if role is RoomRole.HOST:
                # Host owns the session; closing it ends the room.
                self.rooms.pop(room.code, None)
            else:
                room.guest_device_id = ""
                room._guest_token_digest = ""
                room.reset_input(RoomRole.GUEST)

    def resume(self, code: str, token: str) -> Tuple[Room, RoomRole, str]:
        """Re-issue a fresh role token to the holder of a valid prior token.

        This is the background/resume path: the client persists its token, and
        on reload proves membership by presenting it. Rotation retires the old
        token so a leaked value is only ever valid until the next resume.
        """

        with self._lock:
            self.reap()
            room = self.rooms.get(normalize_code(code))
            if room is None or room.is_expired():
                if room is not None:
                    self.rooms.pop(room.code, None)
                raise ExpiredError("room is no longer available")
            role = self.authenticate(code, token)
            fresh, digest = new_session_token()
            if role is RoomRole.HOST:
                room._host_token_digest = digest
            else:
                room._guest_token_digest = digest
            return room, role, fresh

    def publish_input(self, code: str, token: str, frame: dict) -> Tuple[Room, RoomRole, Optional[ControllerState]]:
        """Apply one member's latest input snapshot to its room slot."""

        with self._lock:
            self.reap()
            room = self.rooms.get(normalize_code(code))
            if room is None or room.is_expired():
                if room is not None:
                    self.rooms.pop(room.code, None)
                raise ExpiredError("room is no longer available")
            role = self.authenticate(code, token)
            return room, role, room.publish_input(role, frame)

    def member_state(self, code: str, token: str) -> Tuple[Room, RoomRole]:
        with self._lock:
            self.reap()
            role = self.authenticate(code, token)
            room = self.rooms.get(normalize_code(code))
            if room is None:
                raise NetcodeError("room not found")
            return room, role

    def reconnect(self, code: str, signature: GameSignature, device_id: str) -> Tuple[Room, str]:
        """Re-admit a known device without re-validating a new guest slot."""

        device_id = str(device_id)
        if not device_id:
            raise NotPairedError("a device identity is required")
        with self._lock:
            self.reap()
            room = self.rooms.get(normalize_code(code))
            if room is None or room.is_expired():
                if room is not None:
                    self.rooms.pop(room.code, None)
                raise ExpiredError("room is no longer available")
            if not room.signature.compatible_with(signature):
                raise IncompatibleError("game signature no longer matches")
            if room.host_device_id == device_id:
                token, digest = new_session_token()
                room._host_token_digest = digest
                return room, token
            if room.guest_device_id and room.guest_device_id == device_id:
                token, digest = new_session_token()
                room._guest_token_digest = digest
                return room, token
            raise NotPairedError("this device is not part of the room")

    def reap(self) -> List[str]:
        with self._lock:
            expired = [code for code, room in self.rooms.items() if room.is_expired()]
            for code in expired:
                self.rooms.pop(code, None)
            return sorted(expired)
