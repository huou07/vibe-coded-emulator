# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Vibe Coded Emulator sync engine (transport-agnostic core).

This module is deliberately pure: it has no network, database, or browser
dependency so the same planning logic can back Google Drive sync, LAN
device-to-device sync, and the unified sync mode.

It mirrors the shipped invariants:

* Never overwrite two independently modified copies of a user file. A logical
  file whose local and remote bytes both changed since the last successful sync
  is a conflict, not a silent overwrite.
* Content is identified by hash, never by filename alone.
* A file that was already synced is not re-treated as a conflict after a
  transfer, which prevents sync loops between LAN and Drive.
* Only user-owned emulator data is eligible. Bundled ROMs, emulator firmware,
  and encryption/production keys are never synced.

The caller (app.py / native shell) owns hashing bytes and performing transfers;
this module owns the decision of what to transfer, in which direction, and how
to resolve conflicts.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence


class SyncMode(str, enum.Enum):
    """User-selectable sync mode.

    ``AUTO`` is the recommended default: prefer a direct local-network transfer
    and fall back to the cloud only when no peer is reachable. The explicit
    ``LAN``/``DRIVE``/``LAN_DRIVE`` modes stay available for advanced users.
    """

    OFF = "off"
    AUTO = "auto"
    LAN = "lan"
    DRIVE = "drive"
    LAN_DRIVE = "lan_drive"

    @property
    def drive_enabled(self) -> bool:
        return self in (SyncMode.AUTO, SyncMode.DRIVE, SyncMode.LAN_DRIVE)

    @property
    def lan_enabled(self) -> bool:
        return self in (SyncMode.AUTO, SyncMode.LAN, SyncMode.LAN_DRIVE)

    @property
    def requires_drive(self) -> bool:
        """Modes that cannot run at all without Drive credentials."""

        return self in (SyncMode.DRIVE, SyncMode.LAN_DRIVE)


class Transport(str, enum.Enum):
    LAN = "lan"
    DRIVE = "drive"


def parse_sync_mode(value: object) -> SyncMode:
    """Parse a persisted/admin value, defaulting to OFF for anything unknown."""

    if isinstance(value, SyncMode):
        return value
    token = str(value or "").strip().lower()
    aliases = {"automatic": "auto", "recommended": "auto", "local": "lan"}
    token = aliases.get(token, token)
    for mode in SyncMode:
        if mode.value == token:
            return mode
    return SyncMode.OFF


def select_transport(mode: SyncMode, *, same_lan: bool,
                     drive_available: bool = True) -> Optional[Transport]:
    """Choose the preferred transport for this mode and network context.

    A directly reachable peer on the same LAN is preferred so device-to-device
    transfer does not detour through the cloud. Cloud is used only when LAN is
    unavailable or disabled, and never when it has no credentials.
    """

    if mode is SyncMode.OFF:
        return None
    if mode.lan_enabled and same_lan:
        return Transport.LAN
    if not drive_available:
        # AUTO/LAN fall back to local-only; DRIVE/LAN_DRIVE have nowhere to go.
        return None
    if mode.requires_drive or mode is SyncMode.AUTO:
        return Transport.DRIVE
    return None



# Kinds the sync engine is allowed to move. `firmware` and `keys` are listed so
# the guard can reject them explicitly instead of relying on callers.
class ItemKind(str, enum.Enum):
    ROM = "rom"
    SAVE = "save"
    STATE = "state"
    METADATA = "metadata"
    SETTINGS = "settings"
    FIRMWARE = "firmware"
    KEYS = "keys"


SYNC_ELIGIBLE_KINDS = frozenset(
    {ItemKind.ROM, ItemKind.SAVE, ItemKind.STATE, ItemKind.METADATA, ItemKind.SETTINGS}
)


class SyncError(ValueError):
    pass


@dataclass(frozen=True)
class ItemVersion:
    """One side's view of a logical file."""

    content_hash: str
    size: int = 0
    modified_at: float = 0.0
    device_id: str = ""
    content_id: str = ""

    @property
    def known(self) -> bool:
        return bool(self.content_hash)


@dataclass(frozen=True)
class SyncEntry:
    """A logical user file and the versions observed on each side."""

    kind: ItemKind
    key: str
    local: Optional[ItemVersion] = None
    remote: Optional[ItemVersion] = None
    # Hash recorded after the last successful sync, used to tell "changed since
    # we synced" apart from "changed independently".
    last_synced_hash: str = ""
    # Set when the entry is intentionally kept on both sides after a conflict.
    conflict_copy_key: str = ""


class Direction(str, enum.Enum):
    NONE = "none"
    UPLOAD = "upload"
    DOWNLOAD = "download"
    CONFLICT = "conflict"
    DELETE_LOCAL = "delete_local"
    DELETE_REMOTE = "delete_remote"


@dataclass
class TransferPlan:
    entry: SyncEntry
    direction: Direction
    reason: str = ""
    winner: str = ""
    loser: str = ""
    copy_key: str = ""

    @property
    def is_noop(self) -> bool:
        return self.direction is Direction.NONE


def is_sync_eligible(kind: ItemKind) -> bool:
    """Only user-supplied data may ever leave the device."""

    return kind in SYNC_ELIGIBLE_KINDS


def _changed_since_sync(version: Optional[ItemVersion], last_synced_hash: str) -> bool:
    if version is None or not version.known:
        return False
    return version.content_hash != last_synced_hash


def plan_entry(entry: SyncEntry) -> TransferPlan:
    """Decide the single action for one logical file.

    The matrix:

    * not eligible                -> NONE (never transfer)
    * no local, no remote         -> NONE
    * local only                  -> UPLOAD (new file)
    * remote only                 -> DOWNLOAD (new file)
    * both, identical hash        -> NONE (and mark as synced; loop guard)
    * one side unchanged, other changed -> apply the change
    * both changed, different     -> CONFLICT
    * both deleted                -> NONE
    * one deleted, other intact   -> propagate the deletion
    """

    if not is_sync_eligible(entry.kind):
        return TransferPlan(entry, Direction.NONE, reason="not-eligible")

    local = entry.local if entry.local and entry.local.known else None
    remote = entry.remote if entry.remote and entry.remote.known else None
    last = entry.last_synced_hash

    if local is None and remote is None:
        return TransferPlan(entry, Direction.NONE, reason="absent-both")

    if local and remote and local.content_hash == remote.content_hash:
        # Already identical. Nothing to move; callers persist last_synced_hash so
        # the next pass sees "unchanged on both sides" instead of a conflict.
        return TransferPlan(entry, Direction.NONE, reason="identical")

    local_changed = _changed_since_sync(local, last)
    remote_changed = _changed_since_sync(remote, last)

    if local and remote:
        if local_changed and remote_changed:
            return TransferPlan(entry, Direction.CONFLICT, reason="both-changed",
                                winner="local", loser="remote",
                                copy_key=entry.conflict_copy_key or f"{entry.key}.conflict")
        if local_changed:
            return TransferPlan(entry, Direction.UPLOAD, reason="local-changed")
        if remote_changed:
            return TransferPlan(entry, Direction.DOWNLOAD, reason="remote-changed")
        # Neither matches last_synced_hash but both differ: the index is stale
        # or absent. Treat it as a conflict rather than guessing.
        return TransferPlan(entry, Direction.CONFLICT, reason="index-missing",
                            winner="local", loser="remote",
                            copy_key=entry.conflict_copy_key or f"{entry.key}.conflict")

    if local and not remote:
        if last and local.content_hash == last:
            # Remote was deleted elsewhere; propagate the deletion.
            return TransferPlan(entry, Direction.DELETE_LOCAL, reason="remote-deleted",
                                winner="remote")
        if last and local.content_hash != last:
            # Local edited after remote deletion: keep the edit, re-upload it.
            return TransferPlan(entry, Direction.UPLOAD, reason="remote-deleted-local-edited")
        return TransferPlan(entry, Direction.UPLOAD, reason="local-only")

    # remote only
    if last and remote.content_hash == last:
        return TransferPlan(entry, Direction.DELETE_REMOTE, reason="local-deleted",
                            winner="local")
    return TransferPlan(entry, Direction.DOWNLOAD, reason="remote-only")


@dataclass
class SyncPlan:
    mode: SyncMode
    transport: Optional[Transport]
    transfers: List[TransferPlan] = field(default_factory=list)

    @property
    def conflicts(self) -> List[TransferPlan]:
        return [item for item in self.transfers if item.direction is Direction.CONFLICT]

    @property
    def actions(self) -> List[TransferPlan]:
        return [item for item in self.transfers if not item.is_noop]

    @property
    def clean(self) -> bool:
        return not self.conflicts


def build_plan(
    mode: SyncMode,
    entries: Iterable[SyncEntry],
    *,
    same_lan: bool,
    drive_available: bool = True,
) -> SyncPlan:
    """Plan a whole sync pass. With sync OFF nothing is transferred."""

    mode = parse_sync_mode(mode)
    transport = select_transport(mode, same_lan=same_lan, drive_available=drive_available)
    transfers = [plan_entry(entry) for entry in entries] if mode is not SyncMode.OFF else []
    return SyncPlan(mode=mode, transport=transport, transfers=transfers)


def apply_result(entry: SyncEntry, *, content_hash: str) -> SyncEntry:
    """Return the entry as it looks after a successful transfer.

    Recording the new hash as ``last_synced_hash`` is what stops a file moved
    over LAN from immediately looking like a fresh Drive conflict.
    """

    return SyncEntry(
        kind=entry.kind,
        key=entry.key,
        local=entry.local,
        remote=entry.remote,
        last_synced_hash=content_hash,
        conflict_copy_key=entry.conflict_copy_key,
    )


def resolve_conflict(
    plan: TransferPlan,
    resolution: str,
    *,
    local_hash: str,
    remote_hash: str,
) -> TransferPlan:
    """Turn a conflict into a concrete action.

    ``local`` keeps this device's copy, ``remote`` takes the other side, and
    ``both`` keeps the local copy under a conflict key while pulling the remote
    copy into the original key so no bytes are lost.
    """

    choice = str(resolution or "").strip().lower()
    if choice not in {"local", "remote", "both"}:
        raise SyncError("conflict resolution must be local, remote, or both")
    entry = plan.entry
    if choice == "local":
        return TransferPlan(entry, Direction.UPLOAD, reason="conflict-keep-local", winner="local")
    if choice == "remote":
        return TransferPlan(entry, Direction.DOWNLOAD, reason="conflict-keep-remote", winner="remote")
    copy_key = entry.conflict_copy_key or f"{entry.key}.conflict"
    return TransferPlan(entry, Direction.UPLOAD, reason="conflict-keep-both",
                        winner="local", loser="remote", copy_key=copy_key)


def summarize(plan: SyncPlan) -> Dict[str, int]:
    """Counts suitable for the compact Sync settings surface."""

    counts = {direction.value: 0 for direction in Direction}
    for transfer in plan.transfers:
        counts[transfer.direction.value] += 1
    counts["total"] = len(plan.transfers)
    counts["conflicts"] = len(plan.conflicts)
    counts["actions"] = len(plan.actions)
    return counts


def entries_from_records(
    records: Sequence[Dict[str, object]],
    *,
    kind: ItemKind,
) -> List[SyncEntry]:
    """Build entries from plain dicts (Drive listing / LAN peer / local index)."""

    entries: List[SyncEntry] = []
    for record in records:
        key = str(record.get("key") or "")
        if not key:
            raise SyncError("sync record is missing a key")

        def version(side: str) -> Optional[ItemVersion]:
            raw = record.get(side)
            if not isinstance(raw, dict) or not raw.get("content_hash"):
                return None
            return ItemVersion(
                content_hash=str(raw["content_hash"]),
                size=int(raw.get("size") or 0),
                modified_at=float(raw.get("modified_at") or 0.0),
                device_id=str(raw.get("device_id") or ""),
                content_id=str(raw.get("content_id") or ""),
            )

        entries.append(
            SyncEntry(
                kind=kind,
                key=key,
                local=version("local"),
                remote=version("remote"),
                last_synced_hash=str(record.get("last_synced_hash") or ""),
                conflict_copy_key=str(record.get("conflict_copy_key") or ""),
            )
        )
    return entries
