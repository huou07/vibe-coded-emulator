# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared networking core for controller, LAN sync, and multiplayer rooms.

Section 13 of the product spec asks for one reusable layer (discovery,
pairing/session identity, transport choice, auth, lifecycle) *without*
flattening protocols that have genuinely different needs. This module provides
that shared layer:

* :func:`generate_pairing_code` / :func:`generate_room_code` — short, unbiased,
  ambiguity-free human codes.
* :func:`new_session_token` / :func:`token_digest` — bearer tokens that are
  stored only as a SHA-256 digest server-side.
* :class:`SlidingRateLimiter` — bounded request throttling.
* :class:`ControllerSession` — an ultra-low-latency, latest-state-wins control
  channel that tolerates loss and reconnects.
* :class:`RoomService` — short-lived room codes with core/ROM-hash
  compatibility validation and reconnect handling.

Transport is intentionally *not* implemented here. File sync, the remote
controller, and netplay pick different transports; callers choose a transport
and this module owns identity, validation, and lifecycle. ``choose_transport``
reuses the sync engine's LAN-first preference so devices on one network do not
detour through the cloud.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import pathlib
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

import sync_engine as se


def _load_input_actions() -> Tuple[frozenset, frozenset]:
    """Read the canonical action contract so wire names cannot drift.

    Falls back to the current literals when the schema is unavailable (for
    example when netcode is imported from an installed package without it).
    """

    path = pathlib.Path(__file__).with_name("native-offline") / "shared" / "input-actions-schema.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        buttons = frozenset(str(entry["wire"]) for entry in data["buttons"].values())
        utility = frozenset(str(entry["wire"]) for entry in data["utility"].values())
        if buttons and utility:
            return buttons, utility
    except (OSError, KeyError, TypeError, ValueError):
        pass
    return (
        frozenset({"b", "y", "select", "start", "up", "down", "left", "right", "a", "x", "l", "r"}),
        frozenset({"quick_save", "speed_up", "speed_down", "open_menu"}),
    )


CONTROLLER_BUTTONS, CONTROLLER_UTILITY_ACTIONS = _load_input_actions()


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


def generate_pairing_code(length: int = 6, *, randbelow: Callable[[int], int] = secrets.randbelow) -> str:
    """A numeric pairing code (default six digits, leading zeroes allowed).

    Drawn one decimal digit at a time from a cryptographically secure source so
    every code in ``10**length`` is equally likely. The code is a short-lived
    user confirmation factor, never the session credential.
    """

    if length <= 0:
        raise NetcodeError("code length must be positive")
    return "".join(str(randbelow(10)) for _ in range(length))


def is_pairing_code(code: object) -> bool:
    """True only for exactly six decimal digits (a leading zero is valid)."""

    text = str(code or "")
    return len(text) == 6 and text.isascii() and text.isdigit()


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
    client from exhausting a per-room or per-pairing operation.
    """

    def __init__(self, *, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic):
        if limit <= 0 or window_seconds <= 0:
            raise NetcodeError("rate limiter needs a positive limit and window")
        self.limit = limit
        self.window = window_seconds
        self.clock = clock
        self._buckets: Dict[str, List[float]] = {}

    def check(self, key: str) -> None:
        now = self.clock()
        events = [stamp for stamp in self._buckets.get(key, []) if now - stamp < self.window]
        if len(events) >= self.limit:
            self._buckets[key] = events
            raise RateLimitedError("too many attempts; try again shortly")
        events.append(now)
        self._buckets[key] = events

    def reset(self, key: str) -> None:
        self._buckets.pop(key, None)


# ---------------------------------------------------------------------------
# Remote controller
# ---------------------------------------------------------------------------


class PadButton(str, Enum):
    A = "a"
    B = "b"
    X = "x"
    Y = "y"
    L = "l"
    R = "r"
    ZL = "zl"
    ZR = "zr"
    START = "start"
    SELECT = "select"
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


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
    # One-shot canonical utility action carried by this frame, with a per-press
    # sequence so retries and duplicates never fire it twice.
    utility_action: str = ""
    utility_sequence: int = 0

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
        if self.utility_action:
            payload["u"] = self.utility_action
            payload["us"] = self.utility_sequence
        return payload

    @classmethod
    def from_wire(cls, payload: dict, *, received_at: float = 0.0) -> "ControllerState":
        try:
            sequence = int(payload["s"])
        except (KeyError, TypeError, ValueError) as error:
            raise NetcodeError("controller frame is missing a sequence") from error
        axes = payload.get("a") or [0, 0, 0, 0]
        if len(axes) != 4:
            raise NetcodeError("controller frame has an invalid axis tuple")
        touch = payload.get("t")
        touch_active = False
        touch_x = touch_y = 0.0
        if touch is not None:
            if not isinstance(touch, (list, tuple)) or len(touch) != 2:
                raise NetcodeError("controller frame has an invalid touch tuple")
            try:
                touch_x = min(1.0, max(0.0, float(touch[0])))
                touch_y = min(1.0, max(0.0, float(touch[1])))
            except (TypeError, ValueError) as error:
                raise NetcodeError("controller frame has a non-numeric touch tuple") from error
            touch_active = True
        utility_action = ""
        utility_sequence = 0
        candidate = str(payload.get("u") or "")
        if candidate and (not CONTROLLER_UTILITY_ACTIONS or candidate in CONTROLLER_UTILITY_ACTIONS):
            utility_action = candidate
            try:
                utility_sequence = int(payload.get("us") or 0)
            except (TypeError, ValueError):
                utility_sequence = 0
        return cls(
            sequence=sequence,
            buttons=frozenset(str(name) for name in payload.get("b") or []),
            left_x=float(axes[0]), left_y=float(axes[1]),
            right_x=float(axes[2]), right_y=float(axes[3]),
            received_at=received_at,
            touch_active=touch_active, touch_x=touch_x, touch_y=touch_y,
            utility_action=utility_action, utility_sequence=utility_sequence,
        )


@dataclass
class ControllerSession:
    """Host side of a remote-controller pairing.

    The guest sends small state frames; the host keeps only the most recent one.
    Out-of-order, duplicate, and stale frames are dropped rather than buffered,
    which is what makes packet loss tolerable without adding latency.
    """

    code: str
    host_device_id: str
    created_at: float
    ttl_seconds: float = 120.0
    paired_device_id: str = ""
    _token_digest: str = ""
    _last: Optional[ControllerState] = None
    _ack_sequence: int = 0
    _utility_sequence: int = 0
    _pending_utilities: List[dict] = field(default_factory=list)
    clock: Callable[[], float] = time.monotonic

    # -- lifecycle ---------------------------------------------------------
    def is_expired(self) -> bool:
        return self.clock() - self.created_at > self.ttl_seconds

    @property
    def paired(self) -> bool:
        return bool(self._token_digest)

    def pair(self, device_id: str) -> str:
        """Complete pairing and return the raw session token (once)."""

        if self.is_expired():
            raise ExpiredError("pairing code expired")
        token, digest = new_session_token()
        self.paired_device_id = str(device_id or "guest")
        self._token_digest = digest
        # A paired session is no longer valid for a second guest.
        self._last = None
        self._ack_sequence = 0
        self._utility_sequence = 0
        self._pending_utilities = []
        return token

    def authenticate(self, token: str) -> bool:
        if not self._token_digest:
            return False
        return hmac.compare_digest(self._token_digest, token_digest(token))

    def disconnect(self) -> None:
        self.paired_device_id = ""
        self._token_digest = ""
        self._last = None
        self._ack_sequence = 0
        # One-shot commands must never survive a disconnect and replay on reconnect.
        self._utility_sequence = 0
        self._pending_utilities = []

    # -- acknowledgement ---------------------------------------------------
    def ack(self, sequence: object, utility_sequence: object = 0) -> int:
        """Record the newest frame the host's input path has applied.

        The host reports this after it has pushed the frame into the emulator,
        which is what lets the phone tell "transport connected" apart from
        "input actually reaching the game". ``utility_sequence`` clears every
        pending one-shot command the host has already dispatched.
        """

        try:
            applied = int(sequence)
        except (TypeError, ValueError):
            applied = None
        if applied is not None:
            self._ack_sequence = max(self._ack_sequence, applied)
        try:
            dispatched = int(utility_sequence)
        except (TypeError, ValueError):
            dispatched = 0
        if dispatched > 0:
            self._pending_utilities = [
                item for item in self._pending_utilities if item["sequence"] > dispatched
            ]
        return self._ack_sequence

    def ack_sequence(self) -> int:
        return self._ack_sequence

    def pending_utilities(self) -> List[dict]:
        """One-shot actions the host has not acknowledged yet."""

        return list(self._pending_utilities)

    def last_sequence(self) -> int:
        return self._last.sequence if self._last else 0

    def input_active(self) -> bool:
        """True when the host's input path is keeping up with the phone.

        A live host always has the newest frame in flight while it polls, so
        requiring an exact match would report "input unavailable" forever.
        Input is considered applied when the host has acknowledged frames and
        is no more than a couple of frames behind the phone's latest snapshot;
        a host whose input path stops advancing falls out of this window.
        """

        if not self.paired or self._last is None or self._ack_sequence <= 0:
            return False
        return self._last.sequence - self._ack_sequence <= 2

    # -- input path --------------------------------------------------------
    def accept_state(self, frame: dict, *, token: str) -> Optional[ControllerState]:
        """Validate and apply one guest frame. Returns the applied state.

        Returns ``None`` when the frame is a duplicate or older than the last
        applied frame; the host must not treat that as an error.
        """

        if not self.authenticate(token):
            raise NotPairedError("session token rejected")
        state = ControllerState.from_wire(frame, received_at=self.clock())
        if self._last is not None and state.sequence <= self._last.sequence:
            return None
        self._last = state
        if state.utility_action and state.utility_sequence > self._utility_sequence:
            self._utility_sequence = state.utility_sequence
            self._pending_utilities.append({
                "action": state.utility_action,
                "sequence": state.utility_sequence,
            })
            if len(self._pending_utilities) > 32:
                del self._pending_utilities[:-32]
        return state

    def latest_state(self) -> Optional[ControllerState]:
        return self._last

    def current_buttons(self) -> frozenset:
        return self._last.buttons if self._last else frozenset()

    def needs_resync(self) -> bool:
        """A host that has never received a frame must request a full state."""

        return self.paired and self._last is None


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
    # The relay/signaling hint is deliberately opaque. A raw host IP is never
    # stored here so a room code cannot be used to discover a peer's address.
    signaling_hint: str = ""
    clock: Callable[[], float] = time.monotonic

    def is_expired(self) -> bool:
        return self.clock() - self.created_at > self.ttl_seconds

    @property
    def full(self) -> bool:
        return bool(self._guest_token_digest)


class RoomService:
    """Creates and joins short-lived, compatibility-checked rooms."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic,
                 code_length: int = 6,
                 room_ttl_seconds: float = 900.0,
                 join_limiter: Optional[SlidingRateLimiter] = None):
        self.clock = clock
        self.code_length = code_length
        self.room_ttl_seconds = room_ttl_seconds
        self.rooms: Dict[str, Room] = {}
        self.join_limiter = join_limiter or SlidingRateLimiter(
            limit=10, window_seconds=60.0, clock=clock)

    def _new_code(self) -> str:
        for _ in range(100):
            code = generate_room_code(self.code_length)
            if code not in self.rooms:
                return code
        raise NetcodeError("could not allocate a unique room code")

    def create_room(self, signature: GameSignature, host_device_id: str,
                    *, signaling_hint: str = "") -> Tuple[Room, str]:
        self.reap()
        room = Room(
            code=self._new_code(),
            signature=signature,
            host_device_id=str(host_device_id),
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
        self.join_limiter.check(client_key)
        normalized = normalize_code(code)
        room = self.rooms.get(normalized)
        if room is None:
            raise NetcodeError("room not found")
        if room.is_expired():
            self.rooms.pop(normalized, None)
            raise ExpiredError("room expired")
        if room.full:
            raise NetcodeError("room is full")
        # Compatibility is checked before any session is established, and the
        # system never transfers the ROM to satisfy it.
        if not room.signature.compatible_with(signature):
            raise IncompatibleError(
                "the game or core does not match the host session")
        room.guest_device_id = str(guest_device_id)
        token, digest = new_session_token()
        room._guest_token_digest = digest
        return room, token

    def authenticate(self, code: str, token: str) -> RoomRole:
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
        room = self.rooms.get(normalize_code(code))
        if room is None:
            return
        if role is RoomRole.HOST:
            # Host owns the session; closing it ends the room.
            self.rooms.pop(room.code, None)
        else:
            room.guest_device_id = ""
            room._guest_token_digest = ""

    def reconnect(self, code: str, signature: GameSignature, device_id: str) -> Tuple[Room, str]:
        """Re-admit a known device without re-validating a new guest slot."""

        room = self.rooms.get(normalize_code(code))
        if room is None or room.is_expired():
            raise ExpiredError("room is no longer available")
        if not room.signature.compatible_with(signature):
            raise IncompatibleError("game signature no longer matches")
        if room.host_device_id == str(device_id):
            token, digest = new_session_token()
            room._host_token_digest = digest
            return room, token
        if room.guest_device_id == str(device_id):
            token, digest = new_session_token()
            room._guest_token_digest = digest
            return room, token
        raise NotPairedError("this device is not part of the room")

    def reap(self) -> List[str]:
        expired = [code for code, room in self.rooms.items() if room.is_expired()]
        for code in expired:
            self.rooms.pop(code, None)
        return sorted(expired)


def choose_transport(mode: se.SyncMode, *, same_lan: bool) -> Optional[se.Transport]:
    """Thin re-export so networking code has one transport decision point."""

    return se.select_transport(mode, same_lan=same_lan)
