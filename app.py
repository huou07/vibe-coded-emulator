#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import base64
import binascii
import bug_report
import hashlib
import hmac
import html
import io
import json
import mimetypes
import netcode
import os
import qrcodegen
import re
import secrets
import shutil
import sqlite3
import subprocess
import sync_engine
import sys
import threading
import time
import unicodedata
import zipfile
from datetime import datetime, time as datetime_time, timedelta, timezone
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import Request, urlopen


APP_DIR = os.path.abspath(os.environ.get("AN3_APP_DIR", os.path.dirname(__file__)))
DATA_DIR = os.path.abspath(os.environ.get("AN3_DATA_DIR", os.path.join(APP_DIR, "data")))
STATIC_DIR = os.path.join(APP_DIR, "static")
# Downloadable Linux installer scripts live with the source, not in the app
# bundle. Only these exact names are served; no directory traversal is possible.
INSTALL_SCRIPTS_DIR = os.path.join(APP_DIR, "scripts", "install")
INSTALL_SCRIPTS = {
    "/install/install-deb.sh": "install-deb.sh",
    "/install/install-flatpak.sh": "install-flatpak.sh",
}
NATIVE_OFFLINE_DIR = os.path.join(APP_DIR, "native-offline")
NATIVE_OFFLINE_RELEASE_DIR = os.path.join(NATIVE_OFFLINE_DIR, "releases")
# Release metadata is finalized after builds; it is not a native build input.
# Missing metadata fails closed and never republishes a historical installer.
try:
    with open(os.path.join(NATIVE_OFFLINE_RELEASE_DIR, "catalog.json"), encoding="utf-8") as handle:
        NATIVE_RELEASE_METADATA = json.load(handle)
except FileNotFoundError:
    NATIVE_RELEASE_METADATA = {"artifacts": []}
NATIVE_RELEASE_CATALOG = tuple(NATIVE_RELEASE_METADATA["artifacts"])


def static_asset_version():
    digest = hashlib.sha256()
    for directory, directories, filenames in os.walk(STATIC_DIR):
        directories.sort()
        for name in sorted(filenames):
            path = os.path.join(directory, name)
            if not os.path.isfile(path):
                continue
            relative = os.path.relpath(path, STATIC_DIR).replace(os.sep, "/")
            digest.update(relative.encode("utf-8"))
            with open(path, "rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
    return digest.hexdigest()[:12]


ASSET_VERSION = static_asset_version()
PLAYER_BOOT_ASSETS = frozenset({"offline.js", "player-ui.js", "player-runtime.js", "renderer-worker.js", "nds-touch.js", "lan-peer.js", "sync-transfer.js", "player.js", "site.css"})

# The public source location for the GPL corresponding source. The owner sets
# the real URL (via AN3_SOURCE_REPOSITORY or by editing this default) so the
# project never advertises an invented repository.
SOURCE_REPOSITORY = os.environ.get("AN3_SOURCE_REPOSITORY", "https://REPLACE-WITH-PUBLIC-REPOSITORY-URL")

# Shown on /licenses. Each component keeps its own copyright and license.
LICENSES_THIRD_PARTY = (
    ("Azahar libretro 2126.1.1", "GPL-2.0-or-later", "Azahar Emulator Project"),
    ("melonDS DS libretro 1.3.1", "GPL-3.0-or-later", "melonDS DS contributors"),
    ("mGBA libretro 0.11-219", "MPL-2.0", "mGBA contributors"),
    ("EmulatorJS 4.2.3", "GPL-3.0", "EmulatorJS contributors"),
    ("MoltenVK 1.4.2", "Apache-2.0", "The Khronos Group"),
    ("Tauri 2 / tauri-plugin-dialog", "Apache-2.0 OR MIT", "Tauri contributors"),
    ("Rust crates (Cargo.lock)", "MIT / Apache-2.0 / BSD", "respective authors"),
    ("AndroidX / Material Components", "Apache-2.0", "The Android Open Source Project / Google"),
    ("Apache Commons Compress 1.21", "Apache-2.0", "The Apache Software Foundation"),
    ("XZ for Java 1.9", "Public domain", "Lasse Collin"),
    ("Lucide icons", "ISC", "Lucide Icons and Contributors"),
    ("Pixelify Sans, Roboto Condensed", "SIL OFL 1.1", "respective font authors"),
    ("qrcodegen (Python)", "MIT", "Project Nayuki"),
)


def versioned_player_asset(name):
    """Return a pathname-versioned player asset that old workers cannot alias."""
    if name not in PLAYER_BOOT_ASSETS:
        raise ValueError("unsupported player boot asset")
    return f"/static/v/{ASSET_VERSION}/{name}"


ROM_DIR = os.path.join(DATA_DIR, "roms")
COVER_DIR = os.path.join(DATA_DIR, "covers")
SCREENSHOT_DIR = os.path.join(DATA_DIR, "screenshots")
CUSTOM_DIR = os.path.join(DATA_DIR, "custom")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
EMULATOR_CACHE_DIR = os.path.join(DATA_DIR, "emulatorjs-cache")
PREPARED_ROM_DIR = os.path.join(DATA_DIR, "prepared-roms")
DB_PATH = os.path.join(DATA_DIR, "arcade.db")
HOST = os.environ.get("AN3_HOST", "0.0.0.0")
PORT = int(os.environ.get("AN3_PORT", "8091"))
BASE_URL = os.environ.get("AN3_BASE_URL", f"http://127.0.0.1:{PORT}").rstrip("/")
COOKIE_SECURE = os.environ.get("AN3_COOKIE_SECURE", "0") == "1"
MAX_ROM_BYTES = int(os.environ.get("AN3_MAX_ROM_BYTES", str(8 * 1024**3)))
MAX_COVER_BYTES = 12 * 1024**2
MAX_SCREENSHOT_BYTES = 12 * 1024**2
MAX_UPLOAD_CHUNK_BYTES = int(os.environ.get("AN3_UPLOAD_CHUNK_BYTES", str(8 * 1024**2)))
UPLOAD_TTL = 24 * 3600
SESSION_TTL = 30 * 86400
SCRYPT_N = 8192
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 32 * 1024 * 1024
SCRYPT_AVAILABLE = hasattr(hashlib, "scrypt")
VISITOR_TTL = 365 * 86400
ANALYTICS_SESSION_SECONDS = 30 * 60
SITE_NAME = "Vibe Coded Emulator"
MAX_JSON_BYTES = 1024 * 1024
ENVIRONMENT = os.environ.get("AN3_ENVIRONMENT", "production").strip().lower()
NDS_DEBUG_ALLOWED = ENVIRONMENT in {"staging", "development"}
PUBLIC_NATIVE_RELEASE_ENVIRONMENTS = frozenset({"staging", "development", "production"})
PRODUCTION_ROM_LIBRARY_PREFIXES = ("/game/", "/play/", "/download/", "/game-file/", "/cover/", "/screenshot/", "/custom/")
# Netplay is opt-in and is deliberately unavailable in production.  The
# browser is given an absolute, LAN-scoped origin only after the standalone
# Rust relay has been explicitly installed for staging.  Leaving this empty
# keeps EmulatorJS's native netplay UI disabled.
_netplay_origin = os.environ.get("AN3_NETPLAY_ORIGIN", "").strip().rstrip("/")
_netplay_parts = urlparse(_netplay_origin) if _netplay_origin else None
NETPLAY_ORIGIN = (
    _netplay_origin
    if ENVIRONMENT in {"staging", "development"}
    and _netplay_parts
    and _netplay_parts.scheme in {"http", "https"}
    and _netplay_parts.netloc
    and _netplay_parts.path in {"", "/"}
    and not _netplay_parts.params
    and not _netplay_parts.query
    and not _netplay_parts.fragment
    else ""
)
# AN3 multiplayer rooms are staging-only, exactly like the EmulatorJS Netplay
# relay they pair with. Production serves 404 for every room endpoint, so no
# unauthenticated room or controller endpoint is ever exposed there.
MULTIPLAYER_ENABLED = ENVIRONMENT in {"staging", "development"} and bool(NETPLAY_ORIGIN)
ROOMS = netcode.RoomService(
    room_ttl_seconds=900,
    join_limiter=netcode.SlidingRateLimiter(limit=20, window_seconds=60),
    create_limiter=netcode.SlidingRateLimiter(limit=10, window_seconds=60),
)

# Capability is per core, not global. The staged web EmulatorJS build has no
# WebRTC: netplay is relay-mediated input lockstep (each peer runs its own core).
# Only GBA is runtime-verified (RG-086), so every other system advertises
# "Not available" rather than a dead Create Room button.
MULTIPLAYER_CORE_CAPABILITY = {
    "gba": {"available": True, "transport": "relay", "verified": True},
    "gbc": {"available": False, "transport": "relay", "verified": False},
    "nds": {"available": False, "transport": "relay", "verified": False},
    "3ds": {"available": False, "transport": "relay", "verified": False},
    "switch": {"available": False, "transport": "none", "verified": False},
    "html5": {"available": False, "transport": "none", "verified": False},
}


def multiplayer_capability(system):
    entry = MULTIPLAYER_CORE_CAPABILITY.get(str(system or "").lower())
    if entry and entry.get("available"):
        return {"available": True, "transport": entry.get("transport", "relay"), "verified": bool(entry.get("verified"))}
    return {"available": False, "transport": "relay", "verified": False,
            "reason": "Not available for this system"}


# Legacy web-controller endpoints are staging/development test fixtures only.
# Installed AN3 applications host and pair over the direct native LAN peer
# layer; these endpoints are not part of the product controller architecture.
CONTROLLER_ENABLED = ENVIRONMENT in {"staging", "development"}
CONTROLLERS = {}
CONTROLLER_LOCK = threading.Lock()
CONTROLLER_LIMITER = netcode.SlidingRateLimiter(limit=30, window_seconds=60)
CONTROLLER_TTL_SECONDS = 120
# Systems a host may advertise so the phone can pick the right pad layout.
CONTROLLER_SYSTEMS = frozenset({"auto", "gba", "gbc", "nds", "3ds", "switch", "html5"})


def clean_controller_name(value, fallback):
    """A short printable device label. It is never an address or a token."""

    text = re.sub(r"[^\w .:'()\-]", "", str(value or "")).strip()
    text = re.sub(r"\s+", " ", text)[:32]
    return text or fallback


def controller_reap():
    """Drop expired controller sessions. Called on every mutating request."""

    with CONTROLLER_LOCK:
        expired = [code for code, record in CONTROLLERS.items() if record["session"].is_expired()]
        for code in expired:
            CONTROLLERS.pop(code, None)
    return len(expired)


# Legacy web sync fixtures are staging/development-only. The pure planning core
# lives in sync_engine; installed AN3 applications use the direct native peer
# transport and do not call this application for LAN data.
# Google Drive transport needs owner OAuth credentials and stays unavailable
# (mode rejected, option unadvertised) until configured.
SYNC_ENABLED = ENVIRONMENT in {"staging", "development"}
GOOGLE_DRIVE_ENABLED = bool(os.environ.get("AN3_GOOGLE_CLIENT_ID", "").strip())
# LAN Sync is the global, user-facing master switch for device-to-device sync.
# It composes with the deployment gate above: ``SYNC_ENABLED`` decides whether
# the sync service exists at all in this environment, while LAN Sync lets the
# user turn LAN discovery/transfer on or off. Both must allow an operation for
# it to run. Phone Controller networking is a separate service and is never
# behind this switch. Default ON keeps the previous behaviour; a fresh device
# still transfers nothing until it selects a sync mode.
LAN_SYNC_DEFAULT = True
LAN_PEER_TTL_SECONDS = 90
LAN_PEERS = {}
LAN_PEERS_LOCK = threading.Lock()
SYNC_LIMITER = netcode.SlidingRateLimiter(limit=60, window_seconds=60)
SYNC_MANIFEST_LIMIT = 2000
# Development/test compatibility fixture: eligible save/state blobs are kept in
# memory for a short window so deterministic browser/API tests can exercise the
# old HTTP envelope. This is not the installed-app LAN transport, is never a
# production default, and is not a product data store. Only user data kinds are
# accepted, and firmware/keys can never be published.
LAN_BLOB_TTL_SECONDS = 900
LAN_BLOB_MAX_BYTES = 16 * 1024 * 1024
# A LAN item is base64-wrapped in the JSON envelope. Keep the generic API
# payload limit small while allowing the documented per-item byte limit here.
LAN_BLOB_MAX_JSON_BYTES = (LAN_BLOB_MAX_BYTES * 4 // 3) + 256 * 1024
LAN_BLOB_MAX_ITEMS = 512
LAN_SAVE_SET_MEMBER_LIMIT = 64
LAN_SAVE_SET_MAX_BYTES = 64 * 1024 * 1024
# Keep the existing request envelope ceiling for both legacy single blobs and
# the set envelope. The per-member and aggregate caps below add constraints;
# they never enlarge the generic LAN JSON budget.
LAN_SAVE_SET_MAX_JSON_BYTES = LAN_BLOB_MAX_JSON_BYTES
LAN_BLOBS = {}
LAN_BLOBS_LOCK = threading.Lock()

# --- Bug report pipeline -----------------------------------------------------
# User bug reports are collected on the client only after local sanitization and
# explicit consent, re-sanitized on the server, stored even when the downstream
# GitHub call fails, and finally turned into a GitHub issue with a server-only
# token. The token is never sent to, or readable by, the client.
BUG_REPORT_ENABLED = os.environ.get("AN3_BUG_REPORTS_ENABLED", "1").strip() != "0"
BUG_REPORT_MAX_BYTES = 256 * 1024
BUG_REPORT_RATE_LIMIT = 12
BUG_REPORT_USER_LIMIT = 6
BUG_REPORT_RATE_WINDOW = 3600
BUG_REPORT_COOLDOWN = 60
RUNTIME_BUILD_ID = os.environ.get("AN3_BUILD_ID", "").strip() or ASSET_VERSION
GITHUB_ISSUES_TOKEN = os.environ.get("AN3_GITHUB_ISSUES_TOKEN", "").strip()
GITHUB_ISSUES_REPOSITORY = os.environ.get("AN3_GITHUB_REPOSITORY", "").strip()
GITHUB_ISSUE_LABELS = tuple(
    label.strip() for label in os.environ.get("AN3_GITHUB_ISSUE_LABELS", "bug-report").split(",") if label.strip()
)
# Anonymous native support. The packaged offline app has no account session or
# cookie, so an owner may allowlist the exact app origins permitted to request a
# short-lived opaque capability and submit sanitized anonymous bug reports. An
# empty allowlist disables the whole path (fail closed): the app keeps the
# copy-the-report fallback. No token, secret, or shared key ever reaches the
# client, and the capability carries no MAC or device-fingerprint identity.
SUPPORT_ALLOWED_ORIGINS = tuple(
    origin.strip().rstrip("/")
    for origin in os.environ.get("AN3_SUPPORT_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
)
SUPPORT_CAPABILITY_PATH = "/api/support/capability"
SUPPORT_PATHS = frozenset({SUPPORT_CAPABILITY_PATH, "/api/bug-reports"})
SUPPORT_CAPABILITY_RATE_LIMIT = 6
SUPPORT_CAPABILITY_REPORT_LIMIT = 6
# -----------------------------------------------------------------------------

LAN_SAVE_MEMBER_RE = re.compile(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*\Z")
LAN_SAVE_HASH_RE = re.compile(r"[a-f0-9]{64}\Z")


def _sync_safe_segment(value, fallback, limit):
    result = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or fallback).strip())
    if re.fullmatch(r"\.+", result or ""):
        result = ""
    return (result or str(fallback))[:limit]


def _sync_save_identity(data):
    core = str(data.get("core") or "").strip()
    game_id = str(data.get("gameId") or data.get("game_id") or "").strip()
    rom_hash = str(data.get("romHash") or data.get("rom_hash") or "").strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", core):
        raise ValueError("invalid save-set core")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", game_id):
        raise ValueError("invalid save-set game identity")
    if not re.fullmatch(r"(?:sha256:)?[a-f0-9]{64}", rom_hash):
        raise ValueError("invalid save-set ROM hash")
    set_id = ":".join((
        "save",
        _sync_safe_segment(core, "unknown-core", 48),
        _sync_safe_segment(game_id, "unknown-game", 48),
        _sync_safe_segment(rom_hash, "unknown-rom", 80),
    ))
    return {"core": core, "gameId": game_id, "romHash": rom_hash, "setId": set_id}


def _sync_save_set_payload(save_set):
    return {
        "setId": save_set["setId"],
        "core": save_set["core"],
        "gameId": save_set["gameId"],
        "romHash": save_set["romHash"],
        "memberCount": save_set["memberCount"],
        "totalSize": save_set["totalSize"],
        "members": [
            {
                "memberId": member["memberId"],
                "path": member["path"],
                "size": member["size"],
                "contentHash": member["contentHash"],
            }
            for member in save_set["members"]
        ],
    }


def _sync_save_set_hash(save_set):
    payload = json.dumps(_sync_save_set_payload(save_set), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sync_validate_save_set(data):
    if not isinstance(data, dict):
        raise ValueError("invalid save-set manifest")
    identity = _sync_save_identity(data)
    expected_set_id = identity["setId"]
    set_id = str(data.get("setId") or "")
    if set_id not in {expected_set_id, expected_set_id + ".conflict"}:
        raise ValueError("invalid save-set identity")
    members = data.get("members")
    if not isinstance(members, list) or not members or len(members) > LAN_SAVE_SET_MEMBER_LIMIT:
        raise ValueError("invalid save-set member list")
    if data.get("memberCount") != len(members):
        raise ValueError("save-set member count does not match")
    total_size = data.get("totalSize")
    if isinstance(total_size, bool) or not isinstance(total_size, int) or total_size < 1 or total_size > LAN_SAVE_SET_MAX_BYTES:
        raise ValueError("invalid save-set total size")
    seen = set()
    normalized_members = []
    calculated_total = 0
    previous_member = None
    for member in members:
        if not isinstance(member, dict):
            raise ValueError("invalid save-set member")
        member_id = str(member.get("memberId") or "")
        path = str(member.get("path") or "")
        if not LAN_SAVE_MEMBER_RE.fullmatch(member_id) or member_id in seen or path != "/data/saves/" + member_id:
            raise ValueError("invalid save-set member path")
        if previous_member is not None and previous_member >= member_id:
            raise ValueError("save-set members must be deterministically ordered")
        size = member.get("size")
        content_hash = str(member.get("contentHash") or "").lower()
        key = str(member.get("key") or "")
        if isinstance(size, bool) or not isinstance(size, int) or size < 1:
            raise ValueError("invalid save-set member size")
        if not LAN_SAVE_HASH_RE.fullmatch(content_hash):
            raise ValueError("invalid save-set member hash")
        if key != set_id + ":" + member_id or not re.fullmatch(r"[A-Za-z0-9._:@/\-]{1,256}", key):
            raise ValueError("invalid save-set member identity")
        seen.add(member_id)
        previous_member = member_id
        calculated_total += size
        normalized_members.append({
            "key": key,
            "memberId": member_id,
            "path": path,
            "size": size,
            "contentHash": content_hash,
        })
    if calculated_total != total_size:
        raise ValueError("save-set total size does not match its members")
    normalized = {
        "kind": "save",
        "setId": set_id,
        "core": identity["core"],
        "gameId": identity["gameId"],
        "romHash": identity["romHash"],
        "memberCount": len(normalized_members),
        "totalSize": total_size,
        "members": normalized_members,
        "manifestHash": str(data.get("manifestHash") or "").lower(),
    }
    if not LAN_SAVE_HASH_RE.fullmatch(normalized["manifestHash"]):
        raise ValueError("invalid save-set aggregate hash")
    if _sync_save_set_hash(normalized) != normalized["manifestHash"]:
        raise ValueError("save-set aggregate hash does not match its members")
    return normalized


def lan_blob_reap(now=None):
    """Drop expired LAN blobs; call on every LAN transfer request."""

    now = time.monotonic() if now is None else now
    with LAN_BLOBS_LOCK:
        expired = [key for key, record in LAN_BLOBS.items() if now - record["updated"] > LAN_BLOB_TTL_SECONDS]
        for key in expired:
            LAN_BLOBS.pop(key, None)
    return len(expired)


def sync_mode_catalog():
    """Selectable modes with availability, Drive gated on owner credentials.

    The normal UI shows the plain-language labels; ``detail`` carries the short
    qualifier ("Recommended") and ``advanced`` marks the modes that only appear
    once the user opens Advanced Settings.
    """

    return [
        {"id": sync_engine.SyncMode.AUTO.value, "label": "Automatic", "detail": "Recommended",
         "available": True, "advanced": False},
        {"id": sync_engine.SyncMode.LAN.value, "label": "Local network only",
         "detail": "", "available": True, "advanced": True},
        {"id": sync_engine.SyncMode.DRIVE.value, "label": "Google Drive only",
         "detail": "Coming later", "available": GOOGLE_DRIVE_ENABLED, "advanced": True},
        {"id": sync_engine.SyncMode.OFF.value, "label": "Off", "detail": "",
         "available": True, "advanced": False},
    ]


DEFAULT_SYNC_CONTENT = {
    "save": True,
    "state": True,
    "library": True,
    "rom": False,
}


def parse_sync_content(raw):
    """Coerce a stored/requested content map into the four known booleans."""

    content = dict(DEFAULT_SYNC_CONTENT)
    if isinstance(raw, dict):
        for key in DEFAULT_SYNC_CONTENT:
            if key in raw:
                content[key] = bool(raw[key])
    if content["rom"]:
        content["rom"] = True
    return content


def sync_content_from_row(value):
    if not value:
        return dict(DEFAULT_SYNC_CONTENT)
    try:
        return parse_sync_content(json.loads(value))
    except (TypeError, ValueError):
        return dict(DEFAULT_SYNC_CONTENT)


def sync_mode_status(conn, device_key):
    """Return ``(mode, updated_at, content)`` for a device, defaulting to OFF."""

    row = conn.execute("SELECT mode, updated_at, content FROM sync_settings WHERE device_key=?", (device_key,)).fetchone()
    if not row:
        return sync_engine.SyncMode.OFF, 0, dict(DEFAULT_SYNC_CONTENT)
    return (sync_engine.parse_sync_mode(row["mode"]), int(row["updated_at"]),
            sync_content_from_row(row["content"]))


def sync_lan_status(conn, device_key):
    """Return the persisted global LAN Sync switch for a device.

    Missing rows fall back to ``LAN_SYNC_DEFAULT`` so a device that never opened
    the Sync settings keeps the previous behaviour. This is the user-level gate,
    not the deployment gate; callers still check ``SYNC_ENABLED`` first.
    """

    row = conn.execute("SELECT lan_enabled FROM sync_settings WHERE device_key=?", (device_key,)).fetchone()
    if not row or row["lan_enabled"] is None:
        return LAN_SYNC_DEFAULT
    return bool(row["lan_enabled"])


def sync_same_subnet(first, second):
    """True only for two IPv4 addresses in the same /24 (LAN discovery scope)."""

    if not first or not second or ":" in first or ":" in second:
        return False
    return first.rsplit(".", 1)[0] == second.rsplit(".", 1)[0]


def lan_peer_snapshot(request_ip, *, now=None):
    """Live peers on the requester's subnet, with expired entries reaped.

    Peers are held in memory only (never persisted) and their address is
    disclosed only to a requester on the same /24.
    """

    now = time.monotonic() if now is None else now
    peers = []
    with LAN_PEERS_LOCK:
        for device, record in list(LAN_PEERS.items()):
            if now - record["seen"] > LAN_PEER_TTL_SECONDS:
                LAN_PEERS.pop(device, None)
                continue
            same = sync_same_subnet(request_ip, record["ip"])
            if not same:
                continue
            peers.append({
                "deviceId": device,
                "name": record["name"],
                "address": record["ip"],
                "port": record["port"],
                "sameSubnet": True,
            })
    peers.sort(key=lambda item: item["deviceId"])
    return peers


def room_signature_from(data):
    """Validate the client-supplied game identity (system + core + ROM hash)."""

    system = str(data.get("system") or "").strip().lower()
    core = str(data.get("core") or "").strip()
    rom_hash = str(data.get("romHash") or data.get("rom_hash") or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9]{1,24}", system):
        raise netcode.NetcodeError("invalid system")
    if not re.fullmatch(r"[A-Za-z0-9_.:\-]{1,64}", core):
        raise netcode.NetcodeError("invalid core")
    if not re.fullmatch(r"(sha256:)?[a-f0-9]{16,64}", rom_hash):
        raise netcode.NetcodeError("invalid rom hash")
    return netcode.GameSignature(system=system, core=core, rom_hash=rom_hash)


AUTH_PEPPER = os.environ.get("AN3_AUTH_PEPPER", "")
PEER_PROOF_TTL_SECONDS = 120
PEER_PROOF_CHALLENGE_RE = re.compile(r"^[A-Za-z0-9._:-]{16,256}$")
# Native AN3 account requests originate from the Tauri WebView, not from the
# website itself.  Keep this allow-list narrow: LAN payloads never use these
# endpoints, and arbitrary web origins must not receive credentialed account
# responses.
NATIVE_ACCOUNT_ORIGINS = frozenset(
    origin.strip()
    for origin in os.environ.get(
        "AN3_NATIVE_ACCOUNT_ORIGINS",
        "https://tauri.localhost,http://tauri.localhost,tauri://localhost,https://appassets.androidplatform.net",
    ).split(",")
    if origin.strip()
)
EMULATOR_CDN = "https://cdn.emulatorjs.org"
EMULATOR_CACHE_LOCK = threading.Lock()
EMULATOR_ASSET_LOCKS = {}
PREPARED_ROM_LOCK = threading.Lock()
PREPARED_ROM_LOCKS = {}
_CPU_SAMPLE_LOCK = threading.Lock()
_CPU_SAMPLE = None
THERMAL_ROOT = "/sys/class/thermal"
HWMON_ROOT = "/sys/class/hwmon"
TURBOSTAT_HELPER = os.environ.get("AN3_TURBOSTAT_HELPER", "/usr/local/libexec/an3-arcade-turbostat")


def _read_cpu_totals():
    try:
        with open("/proc/stat", "r", encoding="ascii") as handle:
            fields = handle.readline().split()
        if fields[0] != "cpu" or len(fields) < 5:
            return None
        values = [int(value) for value in fields[1:]]
        return sum(values), values[3] + (values[4] if len(values) > 4 else 0)
    except (OSError, ValueError, IndexError):
        return None


def _cpu_percent():
    global _CPU_SAMPLE
    current = _read_cpu_totals()
    if current is None:
        return None
    with _CPU_SAMPLE_LOCK:
        previous = _CPU_SAMPLE
        _CPU_SAMPLE = current
    if not previous:
        return None
    total_delta = current[0] - previous[0]
    idle_delta = current[1] - previous[1]
    if total_delta <= 0:
        return None
    return round(max(0.0, min(100.0, (total_delta - idle_delta) * 100 / total_delta)), 1)


def _proc_meminfo():
    values = {}
    try:
        with open("/proc/meminfo", "r", encoding="ascii") as handle:
            for line in handle:
                key, _, raw = line.partition(":")
                if key in {"MemTotal", "MemAvailable"}:
                    values[key] = int(raw.strip().split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    total, available = values.get("MemTotal"), values.get("MemAvailable")
    if not total or available is None:
        return None
    used = max(0, total - available)
    return {"used_bytes": used, "total_bytes": total, "used_percent": round(used * 100 / total, 1)}


def _read_uptime():
    try:
        with open("/proc/uptime", "r", encoding="ascii") as handle:
            return round(float(handle.read().split()[0]), 1)
    except (OSError, ValueError, IndexError):
        return None


def _read_text(path):
    try:
        with open(path, "r", encoding="ascii") as handle:
            return handle.read().strip()
    except OSError:
        return None


def _read_temperature(path):
    raw = _read_text(path)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if -100000 <= value <= 200000:
        return round(value / 1000, 1)
    return None


def _temperature():
    """Select a CPU-package temperature, never the first arbitrary thermal zone."""
    candidates = []
    try:
        thermal_names = sorted(os.listdir(THERMAL_ROOT))
    except OSError:
        thermal_names = []
    for name in thermal_names:
        if not name.startswith("thermal_zone"):
            continue
        root = os.path.join(THERMAL_ROOT, name)
        sensor_type = (_read_text(os.path.join(root, "type")) or "").lower()
        value = _read_temperature(os.path.join(root, "temp"))
        if value is None:
            continue
        if sensor_type == "x86_pkg_temp":
            candidates.append((0, name, value))
        elif sensor_type in {"cpu package", "cpu_package"}:
            candidates.append((1, name, value))

    try:
        hwmon_names = sorted(os.listdir(HWMON_ROOT))
    except OSError:
        hwmon_names = []
    for name in hwmon_names:
        root = os.path.join(HWMON_ROOT, name)
        if (_read_text(os.path.join(root, "name")) or "").lower() != "coretemp":
            continue
        try:
            filenames = sorted(os.listdir(root))
        except OSError:
            continue
        for label_name in filenames:
            if not re.fullmatch(r"temp\d+_label", label_name):
                continue
            label = (_read_text(os.path.join(root, label_name)) or "").lower()
            value = _read_temperature(os.path.join(root, label_name.replace("_label", "_input")))
            if value is None:
                continue
            if label == "package id 0":
                candidates.append((2, name, value))
            elif label.startswith("core "):
                candidates.append((3, name, value))

    return min(candidates, default=(None, None, None))[2]


def _power_watts():
    """Read CPU package power from the fixed root-owned turbostat helper."""
    try:
        result = subprocess.run(
            ["/usr/bin/sudo", "-n", TURBOSTAT_HELPER],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
        if result.returncode != 0:
            return None
        value = float(result.stdout.strip())
        return round(value, 2) if 0 <= value <= 10000 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def system_metrics():
    cpu = _cpu_percent()
    memory = _proc_meminfo()
    try:
        usage = shutil.disk_usage(DATA_DIR if os.path.isdir(DATA_DIR) else APP_DIR)
        disk = {"used_bytes": usage.used, "total_bytes": usage.total, "used_percent": round(usage.used * 100 / usage.total, 1)}
    except OSError:
        disk = None
    temperature, power = _temperature(), _power_watts()
    try:
        with db() as conn:
            conn.execute("SELECT 1").fetchone()
        app_ok = True
    except Exception:
        app_ok = False
    return {
        "cpu": {"used_percent": cpu, "status": "normal" if cpu is not None and cpu < 80 else "warning" if cpu is not None else "unavailable"},
        "ram": {**(memory or {}), "status": "normal" if memory and memory["used_percent"] < 85 else "warning" if memory else "unavailable"},
        "disk": {**(disk or {}), "status": "normal" if disk and disk["used_percent"] < 85 else "warning" if disk else "unavailable"},
        "temperature": {"celsius": temperature, "status": "normal" if temperature is not None else "unavailable"},
        "power": {"watts": power, "status": "normal" if power is not None else "unavailable"},
        "uptime_seconds": _read_uptime(),
        "app": {"ok": app_ok, "status": "normal" if app_ok else "error"},
        "updated_at": int(time.time()),
    }

SYSTEMS = {
    "gb": ("Game Boy / Color", "stable"),
    "gba": ("Game Boy Advance", "stable"),
    "nds": ("Nintendo DS", "stable"),
    "3ds": ("Nintendo 3DS", "latest"),
    "nes": ("NES / Famicom", "stable"),
    "snes": ("SNES / Super Famicom", "stable"),
    "n64": ("Nintendo 64", "stable"),
    "psx": ("PlayStation", "stable"),
    "psp": ("PSP", "stable"),
    "segaMD": ("Mega Drive / Genesis", "stable"),
    "segaMS": ("Master System", "stable"),
    "segaGG": ("Game Gear", "stable"),
    "sega32x": ("Sega 32X", "stable"),
    "segaCD": ("Sega CD", "stable"),
    "segaSaturn": ("Sega Saturn", "stable"),
    "arcade": ("Arcade / FBNeo", "stable"),
    "3do": ("3DO", "stable"),
    "atari2600": ("Atari 2600", "stable"),
    "atari7800": ("Atari 7800", "stable"),
    "jaguar": ("Atari Jaguar", "stable"),
    "lynx": ("Atari Lynx", "stable"),
    "pce": ("PC Engine", "stable"),
    "amiga": ("Amiga", "stable"),
    "c64": ("Commodore 64", "stable"),
    "doom": ("DOOM / PrBoom", "stable"),
    "html5": ("HTML5", "native"),
}

# Mirrors static/player.js `primaryCores`. tests/test_multiplayer_api.py asserts
# the two stay in sync so a room signature cannot drift from the real core.
PRIMARY_CORES = {
    "gb": "gambatte", "gba": "mgba", "nds": "melonds", "3ds": "azahar",
    "nes": "fceumm", "snes": "snes9x", "n64": "mupen64plus_next",
    "psx": "pcsx_rearmed", "psp": "ppsspp",
    "segaMD": "genesis_plus_gx", "segaMS": "smsplus", "segaGG": "genesis_plus_gx",
    "sega32x": "picodrive", "segaCD": "genesis_plus_gx", "segaSaturn": "yabause",
    "arcade": "fbneo", "3do": "opera", "atari2600": "stella2014",
    "atari7800": "prosystem", "jaguar": "virtualjaguar", "lynx": "handy",
    "pce": "mednafen_pce", "amiga": "puae", "c64": "vice_x64sc", "doom": "prboom",
}

# The game-only offline app deliberately has no server-side library, account,
# or upload surface.  It may start only systems backed by the existing
# EmulatorJS player contract.  In particular, Nintendo Switch is intentionally
# absent from this allowlist; the browser client reports it as deferred rather
# than trying to preload or launch it.

EXTENSIONS = {
    "gb": {".gb", ".gbc", ".zip", ".7z"},
    "gba": {".gba", ".zip", ".7z", ".raw"},
    "nds": {".nds", ".zip", ".7z"},
    "3ds": {".3ds", ".cci", ".cxi", ".app", ".zip", ".7z"},
    "nes": {".nes", ".fds", ".zip", ".7z"},
    "snes": {".sfc", ".smc", ".fig", ".swc", ".zip", ".7z"},
    "n64": {".n64", ".z64", ".v64", ".zip", ".7z"},
    "psx": {".bin", ".cue", ".chd", ".pbp", ".iso", ".img", ".zip", ".7z"},
    "psp": {".iso", ".cso", ".pbp", ".elf", ".zip", ".7z"},
    "segaMD": {".md", ".gen", ".smd", ".bin", ".zip", ".7z"},
    "segaMS": {".sms", ".zip", ".7z"},
    "segaGG": {".gg", ".zip", ".7z"},
    "sega32x": {".32x", ".bin", ".zip", ".7z"},
    "segaCD": {".cue", ".bin", ".chd", ".iso", ".zip", ".7z"},
    "segaSaturn": {".cue", ".bin", ".chd", ".iso", ".zip", ".7z"},
    "arcade": {".zip", ".7z"},
    "3do": {".iso", ".chd", ".cue", ".bin", ".zip", ".7z"},
    "atari2600": {".a26", ".bin", ".zip"},
    "atari7800": {".a78", ".bin", ".zip"},
    "jaguar": {".j64", ".jag", ".rom", ".zip"},
    "lynx": {".lnx", ".zip"},
    "pce": {".pce", ".sgx", ".cue", ".chd", ".zip"},
    "amiga": {".adf", ".adz", ".dms", ".ipf", ".hdf", ".lha", ".zip", ".7z"},
    "c64": {".d64", ".g64", ".t64", ".tap", ".crt", ".prg", ".zip"},
    "doom": {".wad", ".iwad", ".pk3", ".pk4", ".zip"},
    "html5": {".zip", ".html"},
}

SYSTEM_HINTS = {
    "3ds": ("3ds", "citra", "azahar"), "nds": ("nds", "nintendo-ds", "melonds"),
    "gba": ("gba", "gameboy-advance"), "gb": ("gbc", "gameboy-color", "game-boy"),
    "psp": ("psp",), "psx": ("ps1", "psx", "playstation"), "n64": ("n64",),
    "snes": ("snes", "super-nintendo"), "nes": ("nes", "famicom"),
    "segaMD": ("genesis", "megadrive"), "segaSaturn": ("saturn",),
    "segaCD": ("segacd", "mega-cd"), "arcade": ("arcade", "fbneo", "mame"),
}


def infer_system(filename, archive_path=None):
    lowered = filename.lower().replace("_", "-").replace(" ", "-")
    ext = os.path.splitext(lowered)[1]
    if ext == ".zip" and archive_path and zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as zf:
            names = [item.filename for item in zf.infolist() if not item.is_dir()]
        if any(name.lower().rstrip("/").endswith("index.html") for name in names):
            return "html5"
        detected = {infer_system(name) for name in names}
        detected.discard(None)
        if len(detected) == 1:
            return detected.pop()
    candidates = [system for system, extensions in EXTENSIONS.items() if ext in extensions and ext not in {".zip", ".7z", ".bin", ".cue", ".iso", ".chd"}]
    if len(candidates) == 1:
        return candidates[0]
    for system, hints in SYSTEM_HINTS.items():
        if any(re.search(rf"(^|[-.]){re.escape(hint)}($|[-.])", lowered) for hint in hints):
            return system
    return None


def clear_prepared_game_roms(game_id):
    prefix = f"{int(game_id)}-"
    try:
        names = os.listdir(PREPARED_ROM_DIR)
    except OSError:
        return
    for name in names:
        if not name.startswith(prefix) or not re.fullmatch(r"[0-9]+-[a-f0-9]{20}\.[A-Za-z0-9]+", name):
            continue
        try:
            os.remove(safe_data_path(PREPARED_ROM_DIR, name))
        except OSError:
            pass


def prepared_browser_rom(game):
    """Return a raw handheld ROM for play while preserving the uploaded archive."""
    source = safe_data_path(ROM_DIR, game["rom_path"])
    if game["system"] not in {"gb", "gba", "nds"} or os.path.splitext(source)[1].lower() != ".zip":
        return source, game["rom_name"]
    if not zipfile.is_zipfile(source):
        return source, game["rom_name"]

    raw_extensions = EXTENSIONS[game["system"]] - {".zip", ".7z"}
    with zipfile.ZipFile(source) as archive:
        candidates = [
            info for info in archive.infolist()
            if not info.is_dir() and os.path.splitext(info.filename.lower())[1] in raw_extensions
        ]
        if len(candidates) != 1:
            return source, game["rom_name"]
        member = candidates[0]
        if member.flag_bits & 1 or member.file_size <= 0 or member.file_size > MAX_ROM_BYTES:
            return source, game["rom_name"]
        inner_name = os.path.basename(member.filename)
        inner_ext = os.path.splitext(inner_name)[1].lower()
        stat = os.stat(source)
        fingerprint = hashlib.sha256(
            f"{game['rom_path']}:{stat.st_size}:{stat.st_mtime_ns}:{member.CRC}:{member.file_size}:{member.filename}".encode("utf-8")
        ).hexdigest()[:20]
        prepared_name = f"{int(game['id'])}-{fingerprint}{inner_ext}"
        target = safe_data_path(PREPARED_ROM_DIR, prepared_name)
        if os.path.isfile(target) and os.path.getsize(target) == member.file_size:
            return target, inner_name

    with PREPARED_ROM_LOCK:
        asset_lock = PREPARED_ROM_LOCKS.setdefault(prepared_name, threading.Lock())
    with asset_lock:
        if os.path.isfile(target) and os.path.getsize(target) == member.file_size:
            return target, inner_name
        temp = f"{target}.part-{secrets.token_hex(6)}"
        try:
            with zipfile.ZipFile(source) as archive, archive.open(member) as src, open(temp, "xb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
                dst.flush()
                os.fsync(dst.fileno())
            if os.path.getsize(temp) != member.file_size:
                raise OSError("prepared ROM size mismatch")
            os.replace(temp, target)
        finally:
            try:
                if os.path.exists(temp):
                    os.remove(temp)
            except OSError:
                pass
        return target, inner_name


_ROM_HASH_CACHE = {}
_ROM_HASH_LOCK = threading.Lock()


def game_rom_hash(game):
    """Stable SHA-256 of a game's ROM bytes, cached by path/size/mtime.

    This is the multiplayer room signature's ROM identity. It is computed
    server-side so two clients cannot disagree about the same game, and it is
    only ever a hash: the ROM itself is never sent to another player.
    """

    if not game or not game["rom_path"]:
        return ""
    path = safe_data_path(ROM_DIR, game["rom_path"])
    try:
        stat = os.stat(path)
    except OSError:
        return ""
    key = (path, stat.st_size, stat.st_mtime_ns)
    with _ROM_HASH_LOCK:
        cached = _ROM_HASH_CACHE.get(path)
        if cached and cached[0] == key:
            return cached[1]
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    value = "sha256:" + digest.hexdigest()
    with _ROM_HASH_LOCK:
        _ROM_HASH_CACHE[path] = (key, value)
    return value


def browser_rom_name(game):
    """Return the filename EmulatorJS should infer from the playable URL.

    NDS ZIPs deliberately keep their archive suffix: EmulatorJS uses the URL
    suffix to select its decompressor before handing the extracted ROM to
    melonDS.  The GB/GBA paths use prepared raw ROMs instead.
    """
    try:
        source = safe_data_path(ROM_DIR, game["rom_path"])
        if game["system"] not in {"gb", "gba"} or os.path.splitext(source)[1].lower() != ".zip" or not zipfile.is_zipfile(source):
            return game["rom_name"]
        raw_extensions = EXTENSIONS[game["system"]] - {".zip", ".7z"}
        with zipfile.ZipFile(source) as archive:
            candidates = [
                info for info in archive.infolist()
                if not info.is_dir() and os.path.splitext(info.filename.lower())[1] in raw_extensions
            ]
        if len(candidates) == 1:
            return os.path.basename(candidates[0].filename)
    except (OSError, ValueError, zipfile.BadZipFile):
        pass
    return game["rom_name"]


def cached_emulator_asset(channel, relative):
    if channel not in {"stable", "latest"}:
        raise ValueError("unsupported emulator channel")
    relative = unquote(str(relative or "")).lstrip("/")
    if not relative or ".." in relative.split("/") or not re.fullmatch(r"[A-Za-z0-9._~+@/-]+", relative):
        raise ValueError("invalid emulator asset")
    target = safe_data_path(EMULATOR_CACHE_DIR, os.path.join(channel, relative))
    if os.path.isfile(target) and os.path.getsize(target) > 0:
        return target
    with EMULATOR_CACHE_LOCK:
        asset_lock = EMULATOR_ASSET_LOCKS.setdefault(f"{channel}/{relative}", threading.Lock())
    with asset_lock:
        if os.path.isfile(target) and os.path.getsize(target) > 0:
            return target
        os.makedirs(os.path.dirname(target), exist_ok=True)
        temp = f"{target}.part-{secrets.token_hex(6)}"
        url = f"{EMULATOR_CDN}/{channel}/data/{relative}"
        try:
            request = Request(url, headers={"User-Agent": "VibeCodedEmulator/1.0", "Accept-Encoding": "identity"})
            with urlopen(request, timeout=60) as response:
                final = urlparse(response.geturl())
                if final.scheme != "https" or final.hostname != "cdn.emulatorjs.org" or getattr(response, "status", 200) != 200:
                    raise OSError("emulator CDN rejected the request")
                with open(temp, "wb") as handle:
                    shutil.copyfileobj(response, handle, 1024 * 1024)
                    handle.flush()
                    os.fsync(handle.fileno())
            if not os.path.getsize(temp):
                raise OSError("empty emulator asset")
            os.replace(temp, target)
            return target
        finally:
            try:
                if os.path.exists(temp):
                    os.remove(temp)
            except OSError:
                pass

RATE_LIMIT = {}
RATE_LIMIT_LOCK = threading.Lock()
RATE_LIMIT_MAX_KEYS = 4096
RATE_LIMIT_MAX_WINDOW = 600


def _prune_rate_limit(now, preserve):
    """Bound the RATE_LIMIT key space; callers must hold RATE_LIMIT_LOCK.

    Buckets whose newest timestamp is older than the largest window in use can
    no longer affect any decision and are dropped first. If the cap is still
    exceeded the least-recently-seen buckets are evicted. The key being checked
    is always preserved so a request is never rejected by its own sweep.
    """

    for key in list(RATE_LIMIT):
        if key == preserve:
            continue
        entries = RATE_LIMIT[key]
        if not entries or now - entries[-1] >= RATE_LIMIT_MAX_WINDOW:
            RATE_LIMIT.pop(key, None)
    overflow = len(RATE_LIMIT) - RATE_LIMIT_MAX_KEYS
    if overflow <= 0:
        return
    evictable = sorted(
        (key for key in RATE_LIMIT if key != preserve),
        key=lambda key: RATE_LIMIT[key][-1] if RATE_LIMIT[key] else now - RATE_LIMIT_MAX_WINDOW,
    )
    for key in evictable[:overflow]:
        RATE_LIMIT.pop(key, None)


def db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def init_db():
    os.makedirs(ROM_DIR, exist_ok=True)
    os.makedirs(COVER_DIR, exist_ok=True)
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    os.makedirs(CUSTOM_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(EMULATOR_CACHE_DIR, exist_ok=True)
    os.makedirs(PREPARED_ROM_DIR, exist_ok=True)
    with db() as conn:
        # WAL is a persistent database mode.  Setting it once during startup
        # avoids a write-capable PRAGMA round trip on every page and asset
        # request while retaining the existing concurrent reader behavior.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
              display_name TEXT NOT NULL DEFAULT '', password_hash TEXT NOT NULL,
              role TEXT NOT NULL DEFAULT 'user', created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
              token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              csrf TEXT NOT NULL, expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS games (
              id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, title_vi TEXT NOT NULL, title_en TEXT NOT NULL,
              description_vi TEXT NOT NULL DEFAULT '', description_en TEXT NOT NULL DEFAULT '',
              system TEXT NOT NULL, rom_path TEXT NOT NULL DEFAULT '', rom_name TEXT NOT NULL DEFAULT '',
              cover_path TEXT NOT NULL DEFAULT '', file_size INTEGER NOT NULL DEFAULT 0,
              published INTEGER NOT NULL DEFAULT 0, experimental INTEGER NOT NULL DEFAULT 0,
              system_auto INTEGER NOT NULL DEFAULT 0,
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ratings (
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
              value INTEGER NOT NULL CHECK(value BETWEEN 1 AND 5), updated_at INTEGER NOT NULL,
              PRIMARY KEY(user_id, game_id)
            );
            CREATE TABLE IF NOT EXISTS comments (
              id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
              body TEXT NOT NULL, created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS favorites (
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
              created_at INTEGER NOT NULL,
              PRIMARY KEY(user_id, game_id)
            );
            CREATE TABLE IF NOT EXISTS reports (
              id INTEGER PRIMARY KEY,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
              category TEXT NOT NULL,
              body TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'open',
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS site_settings (
              key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT ''
            );
            -- Bug report pipeline (separate from the content `reports` table).
            CREATE TABLE IF NOT EXISTS bug_reports (
              id INTEGER PRIMARY KEY,
              user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
              fingerprint TEXT NOT NULL DEFAULT '',
              report_schema_version INTEGER NOT NULL DEFAULT 1,
              app_version TEXT NOT NULL DEFAULT '',
              build_id TEXT NOT NULL DEFAULT '',
              platform TEXT NOT NULL DEFAULT '',
              emulator_system TEXT NOT NULL DEFAULT '',
              core_name TEXT NOT NULL DEFAULT '',
              game_title TEXT NOT NULL DEFAULT '',
              game_identifier TEXT NOT NULL DEFAULT '',
              description TEXT NOT NULL DEFAULT '',
              payload TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'open',
              github_issue_number INTEGER,
              github_issue_url TEXT NOT NULL DEFAULT '',
              created_at INTEGER NOT NULL
            );
            -- Anonymous native support capabilities. Only the digest is kept;
            -- the raw bearer token exists in the issue response and the client
            -- memory only. Finite lifetime and use count bound a leaked token.
            CREATE TABLE IF NOT EXISTS support_capabilities (
              token_hash TEXT PRIMARY KEY,
              origin TEXT NOT NULL DEFAULT '',
              created_at INTEGER NOT NULL,
              expires_at INTEGER NOT NULL,
              uses INTEGER NOT NULL DEFAULT 0,
              max_uses INTEGER NOT NULL DEFAULT 5
            );
            CREATE TABLE IF NOT EXISTS page_views (
              id INTEGER PRIMARY KEY, visitor_hash TEXT NOT NULL, user_id INTEGER,
              path TEXT NOT NULL, created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS play_events (
              id INTEGER PRIMARY KEY, visitor_hash TEXT NOT NULL, user_id INTEGER,
              game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
              created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS download_events (
              id INTEGER PRIMARY KEY, visitor_hash TEXT NOT NULL, user_id INTEGER,
              path TEXT NOT NULL, created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS game_screenshots (
              id INTEGER PRIMARY KEY, game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
              file_path TEXT NOT NULL, created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS game_updates (
              id INTEGER PRIMARY KEY, game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
              title_vi TEXT NOT NULL, title_en TEXT NOT NULL,
              body_vi TEXT NOT NULL DEFAULT '', body_en TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS upload_sessions (
              id TEXT PRIMARY KEY, game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
              kind TEXT NOT NULL, filename TEXT NOT NULL, expected_size INTEGER NOT NULL,
              received_size INTEGER NOT NULL DEFAULT 0, temp_name TEXT NOT NULL,
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sync_settings (
              device_key TEXT PRIMARY KEY, mode TEXT NOT NULL, updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS comments_game_idx ON comments(game_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS games_public_idx ON games(published, updated_at DESC);
            CREATE INDEX IF NOT EXISTS favorites_user_idx ON favorites(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS reports_status_idx ON reports(status, updated_at DESC);
            CREATE INDEX IF NOT EXISTS bug_reports_created_idx ON bug_reports(created_at DESC);
            CREATE INDEX IF NOT EXISTS bug_reports_fingerprint_idx ON bug_reports(fingerprint);
            CREATE INDEX IF NOT EXISTS support_capabilities_expires_idx ON support_capabilities(expires_at);
            CREATE INDEX IF NOT EXISTS page_views_created_idx ON page_views(created_at DESC);
            CREATE INDEX IF NOT EXISTS play_events_created_idx ON play_events(created_at DESC);
            CREATE INDEX IF NOT EXISTS play_events_game_idx ON play_events(game_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS download_events_created_idx ON download_events(created_at DESC);
            CREATE INDEX IF NOT EXISTS game_screenshots_game_idx ON game_screenshots(game_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS game_updates_game_idx ON game_updates(game_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS upload_sessions_updated_idx ON upload_sessions(updated_at);
            """
        )
        user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        if "display_name" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN display_name TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE users SET display_name=name WHERE display_name='' OR display_name IS NULL")
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(games)")}
        if "system_auto" not in columns:
            conn.execute("ALTER TABLE games ADD COLUMN system_auto INTEGER NOT NULL DEFAULT 0")
        sync_columns = {row["name"] for row in conn.execute("PRAGMA table_info(sync_settings)")}
        if "content" not in sync_columns:
            conn.execute("ALTER TABLE sync_settings ADD COLUMN content TEXT NOT NULL DEFAULT ''")
        if "lan_enabled" not in sync_columns:
            conn.execute("ALTER TABLE sync_settings ADD COLUMN lan_enabled INTEGER NOT NULL DEFAULT 1")
        defaults = {
            "maintainer_email": os.environ.get("AN3_MAINTAINER_EMAIL", ""),
            "maintainer_facebook": "",
            "maintainer_links": "",
        }
        for key, value in defaults.items():
            conn.execute("INSERT OR IGNORE INTO site_settings(key,value) VALUES(?,?)", (key, value))
        stale = conn.execute("SELECT temp_name FROM upload_sessions WHERE updated_at<?", (int(time.time()) - UPLOAD_TTL,)).fetchall()
        conn.execute("DELETE FROM upload_sessions WHERE updated_at<?", (int(time.time()) - UPLOAD_TTL,))
    for item in stale:
        try:
            os.remove(safe_data_path(UPLOAD_DIR, item["temp_name"]))
        except OSError:
            pass


def password_hash(password):
    salt = os.urandom(16)
    if SCRYPT_AVAILABLE:
        digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32, maxmem=SCRYPT_MAXMEM)
        return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()
    iterations = 120000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)
    return f"pbkdf2_sha256${iterations}$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()


def password_ok(password, encoded):
    try:
        parts = encoded.split("$")
        scheme = parts[0]
        if scheme == "scrypt" and len(parts) == 6 and SCRYPT_AVAILABLE:
            _, n, r, p, salt, expected = parts
            n, r, p = int(n), int(r), int(p)
            if not (1 <= n <= 32768 and 1 <= r <= 16 and 1 <= p <= 4):
                return False
            digest = hashlib.scrypt(password.encode("utf-8"), salt=base64.urlsafe_b64decode(salt), n=n, r=r, p=p, dklen=32, maxmem=SCRYPT_MAXMEM)
        elif scheme == "pbkdf2_sha256" and len(parts) == 4:
            _, rounds, salt, expected = parts
            digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.urlsafe_b64decode(salt), int(rounds), dklen=32)
        else:
            return False
        return secrets.compare_digest(base64.urlsafe_b64encode(digest).decode(), expected)
    except Exception:
        return False


def password_needs_upgrade(encoded):
    return SCRYPT_AVAILABLE and not encoded.startswith(f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}$")


def upgrade_password_hash(user_id, password):
    try:
        with db() as conn:
            conn.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash(password), user_id))
    except Exception:
        pass


def bootstrap_admin():
    name = os.environ.get("AN3_ADMIN_NAME", "admin").strip()
    password = os.environ.get("AN3_ADMIN_PASSWORD", "")
    if not password:
        return
    with db() as conn:
        row = conn.execute("SELECT id FROM users WHERE name=?", (name,)).fetchone()
        if row:
            conn.execute("UPDATE users SET role='admin' WHERE id=?", (row["id"],))
        else:
            conn.execute(
                "INSERT INTO users(name,display_name,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                (name, name, password_hash(password), "admin", int(time.time())),
            )


def esc(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def ref_icon(name, extra=""):
    """Render a local, non-interactive icon from the bundled Lucide asset set."""
    safe_name = re.sub(r"[^a-z0-9-]", "", str(name))
    safe_extra = re.sub(r"[^a-z0-9 -]", "", str(extra))
    return f'<span class="ui-mask ui-ref-{safe_name} {safe_extra}" aria-hidden="true"></span>'


def clean_name(value):
    value = unicodedata.normalize("NFKC", str(value or "")).strip()
    if len(value) < 3 or len(value) > 32 or any(ord(ch) < 32 for ch in value):
        raise ValueError("Name must be 3-32 characters")
    return value


def clean_display_name(value):
    value = unicodedata.normalize("NFKC", str(value or "")).strip()
    if len(value) < 2 or len(value) > 40 or any(ord(ch) < 32 for ch in value):
        raise ValueError("Nickname must be 2-40 characters")
    return value


def safe_next_path(value, fallback="/"):
    raw = str(value or "").strip()
    if not raw or not raw.startswith("/") or raw.startswith("//") or "\\" in raw or any(ord(ch) < 32 for ch in raw):
        return fallback
    parsed = urlparse(raw)
    if parsed.scheme or parsed.netloc:
        return fallback
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def validate_password(password, confirm, lang="en"):
    if len(password) < 10 or len(password) > 200 or password != confirm:
        raise ValueError(tr(lang, "Mật khẩu phải có 10–200 ký tự và trùng khớp", "Passwords must match and contain 10–200 characters"))
    groups = sum(bool(re.search(pattern, password)) for pattern in (r"[a-z]", r"[A-Z]", r"\d", r"[^\w\s]"))
    if groups < 2:
        raise ValueError(tr(lang, "Mật khẩu cần dùng ít nhất hai loại ký tự", "Use at least two character types in the password"))


class RateLimited(PermissionError):
    pass


def auth_hash(value):
    return hashlib.sha256((AUTH_PEPPER + str(value)).encode("utf-8")).hexdigest()


def make_peer_proof(user_id, challenge):
    """Create a short-lived opaque proof for an already authenticated user.

    The proof is only useful inside the freshly encrypted native peer session;
    discovery never carries it, and the endpoint never returns a password or
    reusable session bearer token.
    """

    if not AUTH_PEPPER:
        raise RuntimeError("native peer account proof is not configured")
    if not PEER_PROOF_CHALLENGE_RE.fullmatch(str(challenge or "")):
        raise ValueError("invalid peer challenge")
    payload = {
        "v": 1,
        "userId": int(user_id),
        "challenge": str(challenge),
        "expiresAt": int(time.time()) + PEER_PROOF_TTL_SECONDS,
        "nonce": secrets.token_urlsafe(18),
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(AUTH_PEPPER.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return encoded + "." + base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")


def verify_peer_proof(user_id, challenge, proof):
    if not AUTH_PEPPER or not PEER_PROOF_CHALLENGE_RE.fullmatch(str(challenge or "")):
        return False
    try:
        encoded, signature = str(proof or "").split(".", 1)
        if not encoded or len(encoded) > 4096:
            return False
        supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        expected = hmac.new(AUTH_PEPPER.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(supplied, expected):
            return False
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8"))
    except (ValueError, TypeError, binascii.Error, json.JSONDecodeError, UnicodeDecodeError):
        return False
    return (
        payload.get("v") == 1
        and int(payload.get("userId", -1)) == int(user_id)
        and payload.get("challenge") == str(challenge)
        and int(payload.get("expiresAt", 0)) >= int(time.time())
        and isinstance(payload.get("nonce"), str)
        and 12 <= len(payload["nonce"]) <= 128
    )


def clean_contribution(body, maximum, kind):
    body = unicodedata.normalize("NFKC", str(body or "")).strip()
    if not body or len(body) > maximum or any(ord(char) < 32 and char not in "\n\t" for char in body):
        raise ValueError(f"{kind} must be 1-{maximum} characters")
    lowered = body.lower()
    if len(re.findall(r"(?:https?://|www\.)", lowered)) > 1 or re.search(r"(.)\1{11,}", lowered):
        raise ValueError("Content rejected by the anti-spam system")
    compact = re.sub(r"\W+", "", lowered)
    if len(compact) >= 36 and len(set(compact)) <= 3:
        raise ValueError("Content rejected by the anti-spam system")
    return body


def add_game_update(conn, game_id, title_vi, title_en, body_vi="", body_en=""):
    conn.execute(
        "INSERT INTO game_updates(game_id,title_vi,title_en,body_vi,body_en,created_at) VALUES(?,?,?,?,?,?)",
        (game_id, str(title_vi)[:120], str(title_en)[:120], str(body_vi)[:4000], str(body_en)[:4000], int(time.time())),
    )


def clean_contact_links(value):
    lines = []
    for raw in str(value or "").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        if "|" not in raw:
            raise ValueError("Each social link must use Name|https://url")
        label, url = (part.strip() for part in raw.split("|", 1))
        if not label or len(label) > 40 or not re.fullmatch(r"https?://[^\s]{1,500}", url):
            raise ValueError("Invalid social link")
        lines.append(f"{label}|{url}")
    if len(lines) > 8:
        raise ValueError("At most 8 social links")
    return "\n".join(lines)


def parse_contact_links(value):
    links = []
    for raw in str(value or "").splitlines():
        if "|" not in raw:
            continue
        label, url = (part.strip() for part in raw.split("|", 1))
        if label and re.fullmatch(r"https?://[^\s]{1,500}", url):
            links.append((label, url))
    return links


def site_settings(conn):
    rows = conn.execute("SELECT key,value FROM site_settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


def display_name(user):
    return user["display_name"] or user["name"]


def slugify(value):
    raw = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-") or "game"
    return raw[:70]


def unique_slug(conn, title, game_id=None):
    base = slugify(title)
    slug = base
    index = 2
    while conn.execute("SELECT id FROM games WHERE slug=? AND id!=?", (slug, game_id or 0)).fetchone():
        slug = f"{base}-{index}"
        index += 1
    return slug


def format_size(value):
    size = float(value or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def language(handler):
    # The product ships English-only; the language switch has been removed.
    return "en"


def tr(lang, vi, en):
    return en


def safe_data_path(root, relative):
    target = os.path.abspath(os.path.join(root, relative or ""))
    root = os.path.abspath(root)
    if target != root and not target.startswith(root + os.sep):
        raise ValueError("invalid path")
    return target


def game_title(game, lang):
    return game["title_en"] if lang == "en" and game["title_en"] else game["title_vi"]


def game_description(game, lang):
    return game["description_en"] if lang == "en" and game["description_en"] else game["description_vi"]


def filename_title(value):
    name = os.path.basename(str(value or "")).strip()
    stem = os.path.splitext(name)[0]
    title = re.sub(r"[_-]+", " ", stem).strip()
    return unicodedata.normalize("NFKC", title)[:120] or "Game"


def game_cover(game):
    return f"/cover/{game['id']}" if game["cover_path"] else "/static/default-cover.webp"


def rating_summary(conn, game_id):
    row = conn.execute("SELECT COALESCE(AVG(value),0) avg, COUNT(*) count FROM ratings WHERE game_id=?", (game_id,)).fetchone()
    return float(row["avg"]), int(row["count"])


def library_fingerprint(conn):
    row = conn.execute(
        """SELECT COALESCE(MAX(g.updated_at),0) changed, COUNT(DISTINCT g.id) games,
                  COUNT(r.value) ratings, COALESCE(SUM(r.value),0) score
           FROM games g LEFT JOIN ratings r ON r.game_id=g.id"""
    ).fetchone()
    return f'{row["changed"]}:{row["games"]}:{row["ratings"]}:{row["score"]}'


def layout(title, content, lang, user=None, csrf="", player=False, offline=False, guide_trigger=False, library=False, auth=False, admin=False):
    with db() as conn:
        settings = site_settings(conn)
    account = ""
    if user:
        admin_link = f'<a class="nav-dashboard" href="/admin">{ref_icon("chart-no-axes-column")}{tr(lang,"Dashboard","Dashboard")}</a>' if user["role"] == "admin" else ""
        account = (
            f'{admin_link}<a class="account" href="/account">{ref_icon("users-round", "account-menu-icon")}{esc(display_name(user))}</a>'
            f'<button class="link-button nav-logout" data-action="logout">{ref_icon("log-out")}{tr(lang,"Đăng xuất","Log out")}</button>'
        )
    else:
        account = f'<a href="/login">{tr(lang,"Đăng nhập","Log in")}</a><a href="/register">{tr(lang,"Tạo tài khoản","Register")}</a>'
    # The onboarding guide explained the retired online library + player flow.
    guide_nav = ""
    # The reference header keeps the same offline-state affordance across its
    # public, account and dashboard surfaces. The existing link remains intact.
    mode_label = "Offline"
    online_target = "/games" if ENVIRONMENT != "production" else "/"
    mode_aria = tr(lang,"Mở thư viện trực tuyến","Open online library") if offline and ENVIRONMENT != "production" else (tr(lang,"Mở trang tải ứng dụng","Open app downloads") if offline else tr(lang,"Mở thư viện ngoại tuyến","Open offline library"))
    mode_icon = '<span class="ui-mask ui-wifi-off" aria-hidden="true"></span>'
    mode = f'<a id="modeSwitch" class="mode-switch" href="{online_target if offline else "/offline"}" aria-label="{mode_aria}">{mode_icon}<span>{mode_label}</span></a>'
    # The web offline page is a minimal connection notice; the PWA shortcut
    # control belonged to the retired browser-local library and is gone.
    shortcut = ""
    contacts = []
    if settings.get("maintainer_email"):
        contacts.append(f'<a href="mailto:{esc(settings["maintainer_email"])}">{esc(settings["maintainer_email"])}</a>')
    if settings.get("maintainer_facebook"):
        contacts.append(f'<a href="{esc(settings["maintainer_facebook"])}" rel="me noopener noreferrer" target="_blank">Facebook</a>')
    contacts.extend(f'<a href="{esc(url)}" rel="me noopener noreferrer" target="_blank">{esc(label)}</a>' for label, url in parse_contact_links(settings.get("maintainer_links")))
    contact_block = f'<div class="contact-links"><span>{tr(lang,"Liên hệ maintain:","Maintainer contact:")}</span>{"".join(contacts)}</div>' if contacts else ""
    stage_badge = '<span class="stage-badge">STAGING</span>' if ENVIRONMENT == "staging" else ""
    # Removed with the obsolete online-library onboarding flow.
    welcome = ""
    body_classes = []
    if player:
        body_classes.append("player-page")
    if library:
        body_classes.append("library-shell")
    if offline:
        body_classes.append("offline-shell")
    if auth:
        body_classes.append("auth-page")
    if admin:
        body_classes.append("admin-shell")
    if not player:
        body_classes.append("reference-shell")
    page_scripts = f'<script src="/static/site.js?v={ASSET_VERSION}" defer></script>' + (f'<script src="/static/reference-charts.js?v={ASSET_VERSION}" defer></script>' if admin else "")
    return f"""<!doctype html>
<html lang="{lang}" class="{'library-root' if library else ''}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="csrf-token" content="{esc(csrf)}"><meta name="theme-color" content="#07060c"><title>{esc(title)} · {esc(SITE_NAME)}</title>
<link rel="manifest" href="/static/manifest.webmanifest?v={ASSET_VERSION}">
<link rel="icon" type="image/png" sizes="192x192" href="/static/icon-192.png?v={ASSET_VERSION}">
<link rel="apple-touch-icon" href="/static/icon-192.png?v={ASSET_VERSION}">
<link rel="stylesheet" href="{versioned_player_asset("site.css") if player else f"/static/site.css?v={ASSET_VERSION}"}">{"" if player else f'<link rel="stylesheet" href="/static/theme-violet.css?v={ASSET_VERSION}">'}</head><body class="{' '.join(body_classes)}">
<header class="site-header"><a class="brand" href="/" aria-label="{esc(SITE_NAME)}"><img class="brand-logo" src="/static/brand-logo.png?v={ASSET_VERSION}" alt="{esc(SITE_NAME)}" width="52" height="52"></a>{stage_badge}<nav id="siteNav" class="site-nav">{"" if ENVIRONMENT == "production" else f'<a class="nav-games" href="/games">{ref_icon("gamepad-2")}{tr(lang,"Trò chơi","Games")}</a>'}<a class="nav-download-app" href="/">{ref_icon("download")}{tr(lang,"Tải app","Download app")}</a>{guide_nav}{account}</nav><div class="header-actions">{shortcut}{mode}<button id="navToggle" class="nav-toggle" type="button" aria-label="{tr(lang,'Mở menu','Open menu')}" aria-controls="siteNav" aria-expanded="false"><span class="ui-mask ui-menu" aria-hidden="true"></span><span class="nav-toggle-label">{tr(lang,"Menu","Menu")}</span></button></div></header>
{content}
<footer class="site-footer"><div><strong>{esc(SITE_NAME)}</strong><span>{tr(lang,"Game chạy trên phần cứng của thiết bị người chơi.","Games run on the player's device.")}</span></div>{contact_block}
<div class="credits"><span>{tr(lang,"Công cụ và nguồn mở:","Tools and open source:")}</span><a href="https://emulatorjs.org/">EmulatorJS</a><a href="https://www.retroarch.com/">RetroArch</a><a href="https://github.com/mgba-emu/mgba">mGBA</a><a href="https://melonds.kuribo64.net/">melonDS</a><a href="https://github.com/azahar-emu/azahar">Azahar</a><a href="https://www.python.org/">Python</a><a href="https://sqlite.org/">SQLite</a><a href="/licenses">{tr(lang,"Giấy phép","Licenses")}</a></div></footer>
{welcome}<div id="toast" role="status"></div>{page_scripts}</body></html>"""


def status_page(code, lang, user=None, csrf=""):
    if code == 403:
        title = tr(lang, "Không có quyền truy cập", "Access restricted")
        message = tr(lang, "Dashboard này chỉ dành cho quản trị viên. Tài khoản hiện tại của bạn vẫn có thể duyệt và chơi game.", "This dashboard is available to administrators only. Your current account can still browse and play games.")
    else:
        title = tr(lang, "Không tìm thấy trang", "Page not found")
        message = tr(lang, "Liên kết này có thể đã thay đổi hoặc game không còn ở địa chỉ này.", "This link may have changed, or the game is no longer available at this address.")
    primary_href = "/games" if ENVIRONMENT != "production" else "/"
    primary_label = tr(lang, 'Duyệt thư viện', 'Browse library') if ENVIRONMENT != "production" else tr(lang, 'Tải ứng dụng', 'Download app')
    body = f'''<main class="page status-page"><section class="status-card" aria-labelledby="statusTitle"><p class="eyebrow">{tr(lang,'Mã trạng thái','Status code')} {code}</p><h1 id="statusTitle">{title}</h1><p>{message}</p><div class="status-actions"><a class="button primary" href="{primary_href}">{primary_label}</a><a class="button" href="/offline">{tr(lang,'Mở game trên thiết bị','Open device games')}</a></div></section></main>'''
    return layout(f"{code} · {title}", body, lang, user, csrf)


OS_ICONS = {
    "macOS": '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M16.7 12.9c0-2.1 1.7-3.1 1.8-3.2-1-1.4-2.5-1.6-3-1.6-1.3-.1-2.5.8-3.1.8-.6 0-1.6-.8-2.7-.8-1.4 0-2.7.8-3.4 2.1-1.5 2.5-.4 6.3 1 8.4.7 1 1.5 2.1 2.6 2.1 1 0 1.4-.7 2.7-.7 1.2 0 1.6.7 2.7.7 1.1 0 1.8-1 2.5-2 .8-1.2 1.1-2.3 1.1-2.4-.1 0-2.2-.9-2.2-3.4zM14.8 6.7c.6-.7 1-1.7.9-2.7-.9 0-1.9.6-2.5 1.3-.5.6-1 1.6-.9 2.6 1 .1 2-.5 2.5-1.2z"/></svg>',
    "Windows": '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M3 5.6 10.2 4.6v7.1H3zM11.2 4.5 21 3v8.7H11.2zM3 12.7h7.2v7.1L3 18.7zM11.2 12.7H21V21l-9.8-1.4z"/></svg>',
    "Linux": '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2c-2 0-3.4 1.6-3.4 3.6 0 .9.1 1.7-.2 2.5-.7 1.6-2.4 2.9-3 4.8-.6 1.9-.1 3.7 1.2 4.7.6.5 1.4.7 2.2.7.9 0 1.7-.3 2.4-.3h1.6c.7 0 1.5.3 2.4.3.8 0 1.6-.2 2.2-.7 1.3-1 1.8-2.8 1.2-4.7-.6-1.9-2.3-3.2-3-4.8-.3-.8-.2-1.6-.2-2.5C15.4 3.6 14 2 12 2zm-1.6 3.1c.3 0 .5.3.5.6s-.2.6-.5.6-.5-.3-.5-.6.2-.6.5-.6zm3.2 0c.3 0 .5.3.5.6s-.2.6-.5.6-.5-.3-.5-.6.2-.6.5-.6z"/></svg>',
    "Android": '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 9h10a1 1 0 0 1 1 1v6a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2v-6a1 1 0 0 1 1-1zM4.5 9.5a1 1 0 0 0-1 1v4a1 1 0 0 0 2 0v-4a1 1 0 0 0-1-1zm15 0a1 1 0 0 0-1 1v4a1 1 0 0 0 2 0v-4a1 1 0 0 0-1-1zM7.2 7.6l-1-1.8a.4.4 0 0 1 .7-.4l1 1.8a5.9 5.9 0 0 1 4.2 0l1-1.8a.4.4 0 0 1 .7.4l-1 1.8A5 5 0 0 1 15.6 8H8.4a5 5 0 0 1 1.1-.4zM9.2 5.4a.6.6 0 1 0 0-1.2.6.6 0 0 0 0 1.2zm5.6 0a.6.6 0 1 0 0-1.2.6.6 0 0 0 0 1.2z"/></svg>',
}
DOWNLOAD_PLATFORM_ORDER = ("macOS", "Windows", "Linux", "Android")
DOWNLOAD_PLATFORM_PREFERRED = {
    "macOS": ("DMG", "ZIP"),
    "Windows": ("EXE", "MSI"),
    "Linux": ("DEB", "Flatpak", "AppImage"),
    "Android": ("APK",),
}


def download_platform_card(platform, items, lang):
    """One release card per OS with exactly one primary download action."""
    t = lambda vi, en: tr(lang, vi, en)
    available = [item for item in items if item["status"] == "available" and item["download_url"]]
    ordered = []
    for fmt in DOWNLOAD_PLATFORM_PREFERRED.get(platform, ()):
        ordered.extend(item for item in available if item["format"] == fmt and item not in ordered)
    ordered.extend(item for item in available if item not in ordered)
    icon = OS_ICONS.get(platform, OS_ICONS["Linux"])
    if ordered:
        primary = ordered[0]
        status = f'<span class="platform-status ok">{t("Sẵn sàng tải","Ready")} · {esc(primary["version"])}</span>'
        action = (
            f'<a class="button primary" href="{esc(primary["download_url"])}" download>'
            f'{ref_icon("download")}{t("Tải cho","Download for")} {esc(platform)}</a>'
        )
        if len(ordered) > 1:
            extras = " · ".join(
                f'<a href="{esc(item["download_url"])}" download>{esc(item["format"])}</a>' for item in ordered[1:]
            )
            action += f'<span class="platform-status">{extras}</span>'
        meta = f'{esc(primary["architecture"])} · {esc(primary["format"])}'
    else:
        newest = items[0] if items else None
        status = f'<span class="platform-status">{t("Chưa có bản dựng đã xác minh","No verified build yet")}</span>'
        action = f'<button class="button" type="button" disabled>{t("Sắp có","Coming soon")}</button>'
        meta = f'{esc(newest["architecture"])} · {esc(newest["format"])}' if newest else t("Đang chuẩn bị","Preparing")
    return (
        f'<article class="platform-card {"ready" if ordered else "pending"}" data-platform="{esc(platform)}">'
        f'<span class="platform-icon">{icon}</span>'
        f'<div><h3>{esc(platform)}</h3><p class="platform-meta">{meta}</p>{status}</div>'
        f'<div class="platform-action">{action}</div>'
        f'</article>'
    )


def download_app_page(lang, user, csrf, origin=""):
    """Download-first homepage: platform cards are the primary content."""
    t = lambda vi, en: tr(lang, vi, en)
    source_available = ENVIRONMENT in {"staging", "development"}
    source_action = ""
    if source_available:
        source_action = (
            f'<a class="button" href="/download-app/source">{ref_icon("download")}{t("Tải source build staging (.zip)","Download staging build source (.zip)")}</a>'
            f'<a class="button" href="/download-app/artifacts.json">{t("Manifest artifact","Artifact manifest")}</a>'
            f'<small data-release-id="{native_release_identity()}">{t("Bản dựng","Build")} {native_release_identity()}</small>'
        )
    elif ENVIRONMENT == "production":
        source_action = f'<small data-release-id="{native_release_identity()}">{t("Bản phát hành","Release")} {native_release_identity()}</small>'

    artifacts = native_artifact_manifest()["artifacts"]
    by_platform = {}
    for item in artifacts:
        by_platform.setdefault(item["platform"], []).append(item)
    platform_cards = "".join(
        download_platform_card(platform, by_platform.get(platform, []), lang)
        for platform in DOWNLOAD_PLATFORM_ORDER
    )

    linux_install = f'''<section class="download-features linux-install" aria-labelledby="linuxInstallTitle">
<header><p class="eyebrow">LINUX</p><h2 id="linuxInstallTitle">{t("Cài đặt trên Linux","Install on Linux")}</h2><p>{t("Tải script, xem qua, rồi chạy. Script kiểm tra SHA-256 với catalog phát hành trước khi cài.","Download the script, inspect it, then run it. The script verifies SHA-256 against the release catalog before installing.")}</p></header>
<article><div><strong>{t("Gói DEB (Ubuntu/Debian)","DEB package (Ubuntu/Debian)")}</strong><span>{t("Tải script rồi chạy:","Download the script, then run:")} <code>bash install-deb.sh --base-url {esc(origin)}</code></span><p><a class="button" href="/install/install-deb.sh">{ref_icon("download")}{t("Tải install-deb.sh","Download install-deb.sh")}</a></p><small>{t("Dùng apt để xử lý phụ thuộc khi có sẵn. Bạn vẫn có thể tải trực tiếp gói DEB ở thẻ Linux phía trên.","Uses apt for dependencies when available. The DEB itself is also available from the Linux card above.")}</small></div></article>
<article><div><strong>Flatpak</strong><span>{t("Tải script rồi chạy:","Download the script, then run:")} <code>bash install-flatpak.sh --base-url {esc(origin)}</code></span><p><a class="button" href="/install/install-flatpak.sh">{ref_icon("download")}{t("Tải install-flatpak.sh","Download install-flatpak.sh")}</a></p><small>{t("Mặc định cài cho người dùng hiện tại (--user); dùng --system để cài toàn hệ thống. Script không cài thêm remote nào.","Defaults to a per-user install (--user); use --system for system-wide. The script installs no extra remotes.")}</small></div></article>
</section>'''

    body = f'''<main class="page download-app-page">
<section class="download-app-hero">
<p class="eyebrow">VIBE CODED EMULATOR · OFFLINE</p>
<h1>{t("TẢI ỨNG DỤNG CHƠI OFFLINE","DOWNLOAD THE OFFLINE APP")}</h1>
<p>{t("Chạy GBA, NDS và 3DS từ ROM của chính bạn. Không tài khoản. Không cần internet.","Play GBA, NDS and 3DS from your own ROM files. No account. No internet required.")}</p>
<div class="download-app-actions">{source_action}<a class="button" href="/offline">{t("Mở bản web offline","Open the web offline player")}</a></div>
</section>
<section class="download-app-platforms" aria-labelledby="platformTitle">
<header><p class="eyebrow">{t("NỀN TẢNG","PLATFORMS")}</p><h2 id="platformTitle">{t("Chọn hệ điều hành của bạn","Choose your operating system")}</h2></header>
<div class="platform-grid">{platform_cards}</div>
</section>
{linux_install}
<section class="download-features" aria-label="{t("Điểm chính","Highlights")}">
<article>{ref_icon("hard-drive")}<div><strong>{t("ROM cục bộ","Local ROMs")}</strong><span>{t("Chọn tệp trên máy. ROM không rời khỏi thiết bị.","Pick files on your device. ROMs never leave it.")}</span></div></article>
<article>{ref_icon("eye-off")}<div><strong>{t("Không tài khoản","No account")}</strong><span>{t("Không đăng nhập, không theo dõi, không kho game trên web.","No sign-in, no tracking, no web game catalog.")}</span></div></article>
<article>{ref_icon("gamepad-2")}<div><strong>{t("Chơi offline","Plays offline")}</strong><span>{t("Menu, phím ảo, cảm ứng và bàn phím vật lý ngay trong app.","Menu, virtual pad, touch and physical keyboard inside the app.")}</span></div></article>
</section>
<section class="download-features" aria-labelledby="publicTestTitle">
<header><p class="eyebrow">{t("THỬ NGHIỆM CÔNG KHAI","PUBLIC TESTING")}</p><h2 id="publicTestTitle">{t("Bản phát hành để thử nghiệm","A release for testing")}</h2><p>{t("Đây là bản phát hành thử nghiệm: không phải tính năng nào cũng được kiểm chứng ở mức như nhau.","This is a testing release: not every feature is verified to the same degree.")}</p></header>
<article><div><strong>{t("Hạn chế đã biết","Known limitations")}</strong><span>{t("Đồng bộ LAN giữa hai thiết bị cần được thử rộng hơn; lỗi handshake LAN gián đoạn đang được điều tra; độ trễ Phone Controller chưa được tối ưu; tương thích Eden/Switch chưa được kiểm chứng toàn diện; hành vi runtime Windows/Linux có thể ít được kiểm chứng hơn phần đóng gói.","LAN Sync between two devices still needs broader public testing; an intermittent LAN handshake EOF is under investigation; Phone Controller latency is not yet optimized; Eden/Switch compatibility is not comprehensively verified; Windows/Linux runtime behaviour may be less verified than packaging.")}</span></div></article>
<article><div><strong>{t("Báo lỗi","Report a bug")}</strong><span>{t("Dùng mục Báo lỗi trong app (Help / About). Nêu nền tảng, phiên bản app, core và các bước tái hiện. Không đính kèm ROM, firmware, key hay tệp save.","Use the in-app Report a bug flow (Help / About). Include platform, app version, core and steps to reproduce. Do not attach ROMs, firmware, keys or saves.")}</span></div></article>
</section>
</main>'''
    return layout(tr(lang, "Tải ứng dụng", "Download app"), body, lang, user, csrf)


def native_offline_source_bundle():
    """Return the small, auditable Tauri source archive for staging downloads."""
    root = os.path.realpath(NATIVE_OFFLINE_DIR)
    if not os.path.isdir(root):
        raise FileNotFoundError("native offline source is unavailable")
    payload = io.BytesIO()
    excluded_directories = {".gradle", ".signing", "build", "dist", "node_modules", "releases", "target"}
    blocked_names = {".DS_Store", "local.properties", "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"}
    blocked_suffixes = (".env", ".pem", ".key", ".p12", ".pfx", ".jks", ".keystore")
    secret_markers = (
        re.compile(br"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        re.compile(br"\bAKIA[0-9A-Z]{16}\b"),
        re.compile(br"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
        re.compile(br"\bxox[baprs]-[A-Za-z0-9-]{15,}\b"),
        re.compile(br"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    )
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for directory, directories, filenames in os.walk(root):
            directories[:] = sorted(name for name in directories if name not in excluded_directories and not os.path.islink(os.path.join(directory, name)))
            for filename in sorted(filenames):
                source = os.path.join(directory, filename)
                if filename in blocked_names or filename.endswith(blocked_suffixes) or os.path.islink(source) or not os.path.isfile(source):
                    continue
                with open(source, "rb") as handle:
                    contents = handle.read()
                if any(marker.search(contents) for marker in secret_markers):
                    continue
                relative = os.path.relpath(source, root).replace(os.sep, "/")
                archive.writestr(f"an3-offline-native/{relative}", contents)
    return payload.getvalue()


def native_release_path(name):
    """Resolve one immutable native installer without exposing arbitrary files."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}", str(name or "")):
        return None
    root = os.path.realpath(NATIVE_OFFLINE_RELEASE_DIR)
    candidate = os.path.realpath(os.path.join(root, name))
    if os.path.commonpath((root, candidate)) != root or not os.path.isfile(candidate):
        return None
    return candidate


def _file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def native_release_identity():
    """Installer byte identity is independent of the web asset cache version."""
    payload = {"asset_version": ASSET_VERSION,
               "source_fingerprint": NATIVE_RELEASE_METADATA.get("source_fingerprint"),
               "artifacts": NATIVE_RELEASE_CATALOG}
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
    identity_environment = ENVIRONMENT if ENVIRONMENT in {"staging", "production"} else "development"
    return f"{identity_environment}-{fingerprint}"


def native_artifact_manifest():
    """Describe evidenced artifacts and fail closed if their bytes drift."""
    artifacts = []
    for expected in NATIVE_RELEASE_CATALOG:
        item = dict(expected)
        path = native_release_path(item["filename"]) if item["filename"] else None
        intact = bool(path and os.path.getsize(path) == item["size"] and _file_sha256(path) == item["sha256"])
        item["asset_version"] = ASSET_VERSION
        item["release_id"] = native_release_identity()
        item["build_timestamp"] = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).isoformat().replace("+00:00", "Z") if intact else None
        item["status"] = "available" if intact else "blocked"
        item["download_url"] = f'/download-app/release/{quote(item["filename"])}?sha256={item["sha256"]}' if intact else None
        if item["filename"] and not intact:
            item["runtime_status"] = "blocked: evidenced artifact is missing or failed integrity verification"
        artifacts.append(item)
    return {"manifest_version": 2, "asset_version": ASSET_VERSION, "release_id": native_release_identity(), "source_fingerprint": NATIVE_RELEASE_METADATA.get("source_fingerprint"), "artifacts": artifacts}


def published_native_release(name, expected_sha256=None):
    for item in native_artifact_manifest()["artifacts"]:
        if item["filename"] == name and item["status"] == "available" and (expected_sha256 is None or expected_sha256 == item["sha256"]):
            return native_release_path(name)
    return None


def release_pending_action(label):
    return f'<em>{esc(label)}</em>'


def native_release_action(filename, lang, unavailable_label=None):
    if ENVIRONMENT not in PUBLIC_NATIVE_RELEASE_ENVIRONMENTS or not published_native_release(filename):
        return release_pending_action(unavailable_label or tr(lang, "Chưa có binary staging", "No staging binary yet"))
    extension = os.path.splitext(filename)[1].lstrip(".").upper() or tr(lang, "file", "file")
    label = tr(lang, f"Tải {extension} staging", f"Download staging {extension}") if ENVIRONMENT != "production" else tr(lang, f"Tải {extension}", f"Download {extension}")
    item = next(item for item in native_artifact_manifest()["artifacts"] if item["filename"] == filename)
    return f'<a class="button" href="{esc(item["download_url"])}" download>{ref_icon("download")}{esc(label)}</a>'


def home_page(lang, user, csrf):
    with db() as conn:
        games = conn.execute(
            """SELECT g.*, COALESCE(AVG(r.value),0) rating, COUNT(r.value) rating_count,
                      COALESCE(p.play_count,0) play_count
               FROM games g
               LEFT JOIN ratings r ON r.game_id=g.id
               LEFT JOIN (
                 SELECT game_id, COUNT(*) AS play_count FROM play_events GROUP BY game_id
               ) p ON p.game_id=g.id
               GROUP BY g.id ORDER BY g.updated_at DESC"""
        ).fetchall()
        version = library_fingerprint(conn)

    home_system_labels = {
        "gb": "GB/C", "gba": "GBA", "nds": "NDS", "3ds": "3DS",
        "nes": "NES", "snes": "SNES", "n64": "N64", "psx": "PSX",
        "psp": "PSP", "segaMD": "MD", "segaMS": "MS", "segaGG": "GG",
        "sega32x": "32X", "segaCD": "CD", "segaSaturn": "SAT", "arcade": "ARC",
    }

    def card(game, recommended=False, lead=False, compact=False):
        title = game_title(game, lang)
        description = game_description(game, lang).strip()
        draft = f'<span class="badge draft">{tr(lang,"Draft","Draft")}</span>' if not game["published"] else ""
        testing = f'<span class="badge testing">Testing</span>' if game["experimental"] else ""
        image_loading = 'loading="eager" fetchpriority="high"' if lead else 'loading="lazy"'
        system_label = home_system_labels.get(game["system"], SYSTEMS[game["system"]][0])
        classes = "game-card"
        if recommended:
            classes += " recommended-card"
        if lead:
            classes += " lead-card"
        if compact:
            classes += " collection-card"
        marker = f'<span class="recommendation-marker" aria-label="{tr(lang,"Đề xuất","Recommended")}"><span class="ui-mask ui-star" aria-hidden="true"></span></span>' if recommended else ""
        if compact:
            return f"""<article class="{classes}" data-system="{esc(game['system'])}" data-system-section="{esc(game['system'])}" data-game-slug="{esc(game['slug'])}"><a class="cover" href="/game/{esc(game['slug'])}" aria-label="{tr(lang,'Chi tiết','Details')}: {esc(title)}"><img src="{game_cover(game)}" alt="{esc(title)}" width="720" height="960" {image_loading}></a>
<div class="game-card-body"><h2><a href="/game/{esc(game['slug'])}">{esc(title)}</a></h2><div class="game-meta"><span class="badge">{esc(system_label)}</span>{draft}{testing}</div></div></article>"""
        secondary_action = f'''<a class="card-download" href="/download/{esc(game['slug'])}" aria-label="{tr(lang,'Tải game','Download game')}: {esc(title)}"><span class="ui-mask ui-download" aria-hidden="true"></span></a>'''
        lead_action = f'''<a class="button primary" href="/play/{esc(game['slug'])}"><span class="ui-mask ui-play" aria-hidden="true"></span>{tr(lang,"Chơi ngay","Play now")}</a>'''
        return f"""<article class="{classes}" data-system="{esc(game['system'])}" data-system-section="{esc(game['system'])}" data-game-slug="{esc(game['slug'])}">{marker}<a class="cover" href="/game/{esc(game['slug'])}" aria-label="{tr(lang,'Chi tiết','Details')}: {esc(title)}"><img src="{game_cover(game)}" alt="{esc(title)}" width="720" height="960" {image_loading}></a>
<div class="game-card-body"><h2><a href="/game/{esc(game['slug'])}">{esc(title)}</a></h2>
<p class="card-description">{esc(description)}</p>
<div class="game-meta"><span class="badge">{esc(system_label)}</span>{draft}{testing}</div>
<div class="rating" aria-label="{tr(lang,'Đánh giá','Rating')}: {float(game['rating']):.1f} {tr(lang,'trên 5','out of 5')}"><span class="rating-label">{tr(lang,'Điểm','Score')}</span> {float(game['rating']):.1f}<span>/5 · {game['rating_count']}</span></div>
<div class="card-actions">{lead_action if lead else secondary_action}</div></div></article>"""

    grouped = {system: [] for system in SYSTEMS}
    for game in games:
        grouped.setdefault(game["system"], []).append(game)
    home_system_order = ("gba", "nds") + tuple(system for system in SYSTEMS if system not in {"gba", "nds"})
    populated = [(system, grouped[system]) for system in home_system_order if grouped.get(system)]
    filters = "".join(
        f'<button class="system-filter" type="button" data-system-filter="{esc(system)}" aria-pressed="false">{esc(home_system_labels.get(system, SYSTEMS[system][0]))}<span>{len(items)}</span></button>'
        for system, items in populated
    )
    recommended_games = sorted(
        (game for game in games if game["system"] == "gba" and game["published"] and not game["experimental"] and game["rom_path"]),
        key=lambda game: (int(game["play_count"]), float(game["rating"]), -int(game["id"])),
        reverse=True,
    )[:4]
    recommended = ""
    if recommended_games:
        recommended_cards = "".join(card(game, True, index == 0) for index, game in enumerate(recommended_games))
        recommended = f'''<section class="game-system-section recommended-section" data-section-kind="recommended"><div class="section-title"><div class="section-heading"><span class="ui-mask ui-star-outline" aria-hidden="true"></span><h2>{tr(lang,"Đề xuất cho bạn","Recommended for you")}</h2></div><button class="section-link" type="button" data-library-reset>{tr(lang,"Xem tất cả","View all")}<span class="ui-mask ui-chevron-right" aria-hidden="true"></span></button></div><div class="game-grid">{recommended_cards}</div></section>'''
    recommended_slugs = {game["slug"] for game in recommended_games}
    collection_games = [game for game in games if game["slug"] not in recommended_slugs] or games
    collection_cards = "".join(card(game, compact=True) for game in collection_games)
    collection = f'''<section class="game-system-section collection-section" data-section-kind="collection"><div class="section-title"><div class="section-heading"><span class="ui-mask ui-gamepad" aria-hidden="true"></span><h2>{tr(lang,"Bộ sưu tập của bạn","Your collection")}</h2></div><button class="section-link collection-link" type="button" data-library-reset>{tr(lang,"Xem tất cả","View all")}<span class="ui-mask ui-chevron-right" aria-hidden="true"></span></button></div><div class="game-grid">{collection_cards}</div></section>'''
    empty = f'<div class="empty-state"><strong>{tr(lang,"Thư viện đang chờ game đầu tiên.","The library is waiting for its first game.")}</strong><span>{tr(lang,"Bạn vẫn có thể mở ROM riêng đã lưu trên thiết bị.","You can still open a private ROM saved on this device.")}</span><a class="button primary" href="/offline">{tr(lang,"Mở thư viện ngoại tuyến","Open offline library")}</a></div>'
    populated_library = f'''<nav id="systemFilters" class="system-filters" aria-label="{tr(lang,"Lọc theo hệ máy","Filter by system")}"><button class="system-filter active" type="button" data-system-filter="all" aria-pressed="true">{tr(lang,"Tất cả","All")}<span>{len(games)}</span></button>{filters}</nav><p id="libraryStatus" class="library-status" aria-live="polite"></p>{recommended}{collection}<div id="libraryNoResults" class="empty-state" hidden><strong>{tr(lang,"Không tìm thấy trò chơi phù hợp.","No matching games found.")}</strong><span>{tr(lang,"Thử từ khóa khác hoặc xóa bộ lọc hệ máy.","Try another search or clear the system filter.")}</span><button id="resetLibrary" class="button" type="button">{tr(lang,"Xóa tìm kiếm và bộ lọc","Clear search and filters")}</button></div>'''
    body = f"""<main class="page library-page"><section class="library-head"><div><p class="eyebrow">example.com</p><h1>{tr(lang,"Thư viện trò chơi","Game library")}</h1><p class="muted">{tr(lang,"Chọn game và chơi ngay trên thiết bị của bạn.","Choose a game and play it on your own device.")}</p></div></section>
<section class="library-toolbar" aria-label="{tr(lang,'Tìm và lọc trò chơi','Find and filter games')}"><label class="search" for="gameSearch"><span>{tr(lang,'Tìm trò chơi','Search games')}</span><span class="search-field"><span class="ui-mask ui-search" aria-hidden="true"></span><input id="gameSearch" type="search" placeholder="{tr(lang,'Tìm trò chơi','Search games')}" autocomplete="off"><button id="clearSearch" class="search-clear" type="button" hidden>{tr(lang,'Xóa','Clear')}</button></span></label></section>
<div id="gameGrid" class="game-library" data-library-version="{version}">{populated_library if games else empty}</div></main>"""
    return layout(tr(lang, "Trò chơi", "Games"), body, lang, user, csrf, guide_trigger=True, library=True)


def auth_page(kind, lang, user, csrf, error="", next_path="/"):
    register = kind == "register"
    next_path = safe_next_path(next_path)
    heading = tr(lang, "Tạo tài khoản", "Create account") if register else tr(lang, "Chào mừng trở lại!", "Welcome back!")
    submit_label = tr(lang, "Tạo tài khoản", "Create account") if register else tr(lang, "Đăng nhập", "Log in")
    intro = tr(lang, "Tạo tài khoản để lưu tiến độ và lưu các game yêu thích của bạn.", "Create an account to continue and save your favorite games.") if register else tr(lang, "Đăng nhập để lưu tiến độ, đồng bộ yêu thích và trải nghiệm Vibe Coded Emulator trọn vẹn.", "Log in to save your progress, sync favorites, and enjoy the full Vibe Coded Emulator experience.")
    nickname = f'<label class="auth-field"><span>{tr(lang,"Nickname hiển thị","Display nickname")}</span><span class="auth-control">{ref_icon("users-round")}<input name="display_name" minlength="2" maxlength="40" required autocomplete="nickname" placeholder="{tr(lang,"Nhập nickname","Enter display nickname")}"></span></label>' if register else ""
    password_rules = f'<p id="passwordRules" class="field-help">{tr(lang,"Dùng 10–200 ký tự và ít nhất hai loại: chữ thường, chữ hoa, số hoặc ký hiệu.","Use 10–200 characters and at least two types: lowercase, uppercase, numbers, or symbols.")}</p>' if register else ""
    password_describedby = ' aria-describedby="passwordRules"' if register else ""
    confirm = f'<label>{tr(lang,"Nhập lại mật khẩu","Confirm password")}<input name="confirm" type="password" minlength="10" maxlength="200" required autocomplete="new-password" aria-describedby="passwordRules"></label>' if register else ""
    next_query = f'?next={quote(next_path, safe="")}' if next_path != "/" else ""
    switch = f'<section class="auth-switch"><span>{tr(lang,"Đã có tài khoản?","Already registered?") if register else tr(lang,"Chưa có tài khoản?","No account yet?")}</span><a href="/{"login" if register else "register"}{next_query}">{tr(lang,"Đăng nhập ngay","Log in now") if register else tr(lang,"Đăng ký ngay","Register now")} {ref_icon("arrow-right")}</a></section>'
    error_hidden = "" if error else " hidden"
    password_confirm = f'<label class="auth-field"><span>{tr(lang,"Nhập lại mật khẩu","Confirm password")}</span><span class="auth-control">{ref_icon("lock-keyhole")}<input name="confirm" type="password" minlength="10" maxlength="200" required autocomplete="new-password" aria-describedby="passwordRules" placeholder="{tr(lang,"Nhập lại mật khẩu","Confirm password")}"></span></label>' if register else ""
    nonfunctional_social = "" if register else f'''<div class="auth-divider" aria-hidden="true"><span></span><em>{tr(lang,"hoặc tiếp tục với","or continue with")}</em><span></span></div><div class="auth-socials" aria-label="{tr(lang,'Đăng nhập mạng xã hội chưa được hỗ trợ','Social sign-in is not supported')}"><button type="button" disabled aria-disabled="true" title="{tr(lang,'Đăng nhập Google chưa khả dụng','Google sign-in is unavailable')}"><img src="/static/ui-ref-google.svg" alt="Google" width="42" height="42"></button><button type="button" disabled aria-disabled="true" title="{tr(lang,'Đăng nhập Discord chưa khả dụng','Discord sign-in is unavailable')}"><img src="/static/ui-ref-discord.svg" alt="Discord" width="42" height="42"></button></div>'''
    benefits = "" if register else f'''<section class="auth-benefits"><article>{ref_icon("star", "benefit-icon benefit-star")}<div><strong>{tr(lang,"Đồng bộ yêu thích","Đồng bộ yêu thích")}</strong><span>{tr(lang,"Lưu game yêu thích của bạn an toàn trên đám mây.","Save your favorite games safely in the cloud.")}</span></div></article><article>{ref_icon("cloud-upload", "benefit-icon benefit-cloud")}<div><strong>{tr(lang,"Đồng bộ tiến độ","Đồng bộ tiến độ")}</strong><span>{tr(lang,"Tiếp tục chơi từ mọi thiết bị, mọi lúc.","Continue from any device, any time.")}</span></div></article></section>'''
    security = "" if register else f'''<p class="auth-security">{ref_icon("shield-check")}<span>{tr(lang,"Vibe Coded Emulator cam kết bảo mật thông tin của bạn. Chỉ dùng để đăng nhập và đồng bộ dữ liệu.","Vibe Coded Emulator protects your information. It is used only for sign-in and data sync.")}</span></p>'''
    body = f"""<main class="auth-shell"><div class="auth-background-motif" aria-hidden="true"></div><div class="auth-intro"><span class="ui-mask ui-gamepad auth-intro-marker" aria-hidden="true"></span><h1>{heading}</h1><p class="auth-copy">{intro}</p></div><section class="auth-panel">
<form id="authForm" data-kind="{kind}" aria-describedby="formError"><input name="next" type="hidden" value="{esc(next_path)}"><label class="auth-field"><span>{tr(lang,"Email hoặc tên đăng nhập","Email or username")}</span><span class="auth-control">{ref_icon("mail")}<input name="name" minlength="3" maxlength="32" required autocomplete="username" placeholder="{tr(lang,"Nhập email hoặc tên đăng nhập","Enter email or username")}"></span></label>{nickname}
<label class="auth-field"><span>{tr(lang,"Mật khẩu","Password")}</span><span class="auth-control">{ref_icon("lock-keyhole")}<input name="password" type="password" minlength="10" maxlength="200" required autocomplete="{'new-password' if register else 'current-password'}"{password_describedby} placeholder="{tr(lang,"Nhập mật khẩu","Enter password")}"><span class="auth-field-end">{ref_icon("eye-off")}</span></span></label>{password_rules}{password_confirm}
<div class="auth-options"><span class="auth-remember">{ref_icon("check")} {tr(lang,"Ghi nhớ đăng nhập","Remember sign-in")}</span><span class="auth-forgot" aria-disabled="true">{tr(lang,"Quên mật khẩu?","Forgot password?")}</span></div>
<button class="button primary" type="submit">{ref_icon("bot")}<span class="auth-submit-label">{submit_label}</span></button><div id="authProgress" class="auth-progress" hidden role="status" aria-live="polite"><span id="authProgressLabel"></span><div role="progressbar" aria-label="{tr(lang,'Tiến trình xác thực','Authentication progress')}"><i></i></div></div><p class="form-error" id="formError" role="alert" aria-live="assertive" tabindex="-1"{error_hidden}>{esc(error)}</p>{nonfunctional_social}</form></section>{benefits}{switch}{security}</main>"""
    return layout(heading, body, lang, user, csrf, auth=True)


def game_page(game, lang, user, csrf):
    with db() as conn:
        avg, count = rating_summary(conn, game["id"])
        comments = conn.execute(
            """SELECT c.*,u.name,COALESCE(NULLIF(u.display_name,''),u.name) AS display_name,u.role FROM comments c JOIN users u ON u.id=c.user_id
               WHERE c.game_id=? ORDER BY c.created_at DESC LIMIT 100""", (game["id"],)
        ).fetchall()
        own = conn.execute("SELECT value FROM ratings WHERE game_id=? AND user_id=?", (game["id"], user["id"] if user else 0)).fetchone()
        favorite = conn.execute("SELECT 1 FROM favorites WHERE game_id=? AND user_id=?", (game["id"], user["id"] if user else 0)).fetchone()
        screenshots = conn.execute("SELECT id FROM game_screenshots WHERE game_id=? ORDER BY created_at DESC", (game["id"],)).fetchall()
        updates = conn.execute("SELECT * FROM game_updates WHERE game_id=? ORDER BY created_at DESC LIMIT 60", (game["id"],)).fetchall()
    stars = "".join(f'<button type="button" class="star{" active" if own and own["value"]>=value else ""}" data-rate="{value}" aria-label="{tr(lang,"Chấm","Rate")} {value} {tr(lang,"trên 5","out of 5")}" aria-pressed="{str(bool(own and own["value"] >= value)).lower()}">{value}</button>' for value in range(1, 6))
    comment_rows = []
    for item in comments:
        remove = f'<button class="comment-delete" data-comment-delete="{item["id"]}">×</button>' if user and user["role"] == "admin" else ""
        stamp = datetime.fromtimestamp(item["created_at"]).strftime("%Y-%m-%d %H:%M")
        comment_rows.append(f'<article class="comment"><header><strong>{esc(item["display_name"])}</strong><time>{stamp}</time>{remove}</header><p>{esc(item["body"])}</p></article>')
    comment_form = f'<form id="commentForm" data-game="{game["id"]}"><input class="honeypot" name="website" tabindex="-1" autocomplete="off"><label>{tr(lang,"Bình luận của bạn","Your comment")}<textarea name="body" maxlength="1200" required placeholder="{tr(lang,"Chia sẻ trải nghiệm của bạn","Share your experience")}"></textarea></label><button class="button" type="submit">{tr(lang,"Gửi bình luận","Post comment")}</button></form>' if user else ""
    favorite_button = f'<button id="favoriteButton" class="button" data-game="{game["id"]}" aria-pressed="{str(bool(favorite)).lower()}">{tr(lang,"Bỏ yêu thích","Remove favorite") if favorite else tr(lang,"Thêm yêu thích","Add favorite")}</button>' if user else ""
    return_to = quote(f"/game/{game['slug']}", safe="")
    quick_edit = f'<a class="button quick-edit" href="/admin/game/{game["id"]}?next={return_to}">{tr(lang,"Sửa nhanh","Quick Edit")}</a>' if user and user["role"] == "admin" else ""
    report_form = f'''<form id="reportForm" data-game="{game["id"]}" class="report-form"><input class="honeypot" name="website" tabindex="-1" autocomplete="off"><label>{tr(lang,"Loại lỗi","Issue type")}<select name="category"><option value="controls">{tr(lang,"Điều khiển","Controls")}</option><option value="playback">{tr(lang,"Chạy game","Game playback")}</option><option value="other">{tr(lang,"Khác","Other")}</option></select></label><label>{tr(lang,"Mô tả lỗi","Issue details")}<textarea name="body" maxlength="1600" required placeholder="{tr(lang,"Điều gì đã xảy ra?","What happened?")}"></textarea></label><button class="button" type="submit">{tr(lang,"Báo lỗi","Report issue")}</button></form>''' if user else ""
    screenshot_rows = "".join(f'<a href="/screenshot/{item["id"]}" target="_blank" rel="noopener"><img src="/screenshot/{item["id"]}" alt="{tr(lang,"Ảnh màn hình game","Game screenshot")}" loading="lazy"></a>' for item in screenshots)
    update_rows = "".join(f'<article class="game-update"><time>{datetime.fromtimestamp(item["created_at"]).strftime("%Y-%m-%d %H:%M")}</time><h3>{esc(item["title_en"] if lang == "en" else item["title_vi"])} </h3><p>{esc(item["body_en"] if lang == "en" else item["body_vi"]).replace(chr(10),"<br>")}</p></article>' for item in updates)
    draft = f'<span class="badge draft">{tr(lang,"Draft công khai","Public draft")}</span>' if not game["published"] else ""
    testing = '<span class="badge testing">Testing</span>' if game["experimental"] else ""
    title = game_title(game, lang)
    login_next = quote(f"/game/{game['slug']}", safe="")
    media = f'<section class="description-media"><div class="section-title"><h2>{tr(lang,"Ảnh trong game","In-game images")}</h2><span>{len(screenshots)}</span></div><div class="screenshot-grid">{screenshot_rows}</div></section>' if screenshots else ''
    contribution = f'<div class="rate-box" data-game="{game["id"]}"><span>{tr(lang,"Đánh giá của bạn","Your rating")}</span><div class="star-group" role="group" aria-label="{tr(lang,"Đánh giá trò chơi","Rate this game")}">{stars}</div></div>' if user else f'<div class="contribution-prompt"><strong>{tr(lang,"Muốn lưu hoặc chia sẻ ý kiến?","Want to save or share feedback?")}</strong><span>{tr(lang,"Đăng nhập để yêu thích, đánh giá, bình luận hoặc báo lỗi.","Log in to favorite, rate, comment, or report an issue.")}</span><a class="button" href="/login?next={login_next}">{tr(lang,"Đăng nhập","Log in")}</a></div>'
    reports = f'<section class="reports"><div class="section-title"><h2>{tr(lang,"Báo lỗi","Report an issue")}</h2></div>{report_form}</section>' if user else ""
    body = f"""<main class="page detail-page"><section class="game-detail"><div class="detail-cover"><img src="{game_cover(game)}" alt="{esc(title)}" width="720" height="960"></div>
<div class="detail-copy"><div class="game-meta"><span class="badge">{esc(SYSTEMS[game['system']][0])}</span>{draft}{testing}</div><h1>{esc(title)}</h1>
<div class="rating-large"><span>{avg:.1f}/5</span><small>{count} {tr(lang,"lượt đánh giá","ratings")}</small></div>
<div class="detail-actions"><a class="button primary" href="/play/{esc(game['slug'])}">{tr(lang,"Chơi ngay","Play now")}</a><a class="button" href="/download/{esc(game['slug'])}">{tr(lang,"Tải game","Download game")} · {format_size(game['file_size'])}</a>{favorite_button}{quick_edit}</div>
<p class="description">{esc(game_description(game,lang)).replace(chr(10),'<br>')}</p>
{media}{contribution}</div></section>
<section class="game-updates"><div class="section-title"><h2>{tr(lang,"Lịch sử cập nhật","Update history")}</h2><span>{len(updates)}</span></div>{update_rows or f'<p class="muted">{tr(lang,"Chưa có cập nhật.","No updates yet.")}</p>'}</section>
<section class="comments"><div class="section-title"><h2>{tr(lang,"Bình luận","Comments")}</h2><span>{len(comments)}</span></div>{comment_form}<div id="commentList">{''.join(comment_rows) if comment_rows else f'<p class="muted">{tr(lang,"Chưa có bình luận.","No comments yet.")}</p>'}</div></section>
{reports}</main>"""
    return layout(title, body, lang, user, csrf)


def account_page(lang, user, csrf):
    with db() as conn:
        favorites = conn.execute(
            """SELECT g.*, COALESCE(AVG(r.value),0) rating, COUNT(r.value) rating_count
               FROM favorites f JOIN games g ON g.id=f.game_id
               LEFT JOIN ratings r ON r.game_id=g.id
               WHERE f.user_id=? GROUP BY g.id ORDER BY f.created_at DESC""",
            (user["id"],),
        ).fetchall()
    card_rows = []
    for index, game in enumerate(favorites):
        title = game_title(game, lang)
        image_priority = ' loading="eager" fetchpriority="high"' if index == 0 else ' loading="lazy"'
        card_rows.append(f'''<article class="game-card"><a class="cover" href="/game/{esc(game['slug'])}" aria-label="{tr(lang,'Xem chi tiết','View details')}: {esc(title)}"><img src="{game_cover(game)}" alt="{tr(lang,'Bìa game','Cover art for')} {esc(title)}" width="720" height="960"{image_priority}></a>
<div class="game-card-body"><div class="game-meta"><span class="badge">{esc(SYSTEMS[game['system']][0])}</span></div><h2><a href="/game/{esc(game['slug'])}">{esc(title)}</a></h2><div class="rating">{tr(lang,'Điểm','Score')} {float(game['rating']):.1f}/5 · {game['rating_count']}</div><div class="card-actions"><a class="button primary" href="/play/{esc(game['slug'])}">{tr(lang,"Chơi ngay","Play now")}</a></div></div></article>''')
    cards = "".join(card_rows)
    empty = f'<div class="empty-state"><strong>{tr(lang,"Chưa có game yêu thích.","No favorites yet.")}</strong><span>{tr(lang,"Lưu game từ trang chi tiết để tìm lại nhanh hơn.","Save a game from its detail page to find it faster.")}</span><a class="button" href="/">{tr(lang,"Duyệt thư viện","Browse library")}</a></div>'
    body = f'''<main class="page account-page"><section class="library-head"><div><p class="eyebrow">{esc(SITE_NAME)} ID</p><h1>{tr(lang,"Tài khoản","Account")}</h1><p class="muted">{tr(lang,"Quản lý tên hiển thị và quay lại các game bạn đã lưu.","Manage your display name and return to games you saved.")}</p></div><span class="account-role">{esc(display_name(user))}</span></section>
<section class="account-settings" aria-labelledby="displayNameTitle"><div class="section-title"><div><p class="eyebrow">{tr(lang,"Hồ sơ công khai","Public profile")}</p><h2 id="displayNameTitle">{tr(lang,"Tên hiển thị","Display name")}</h2></div></div><form id="displayNameForm" class="form-grid"><label>{tr(lang,"Tên đăng nhập (không thể đổi)","Username (cannot be changed)")}<input value="{esc(user['name'])}" readonly aria-readonly="true"></label><label>{tr(lang,"Nickname trên web","Website nickname")}<input name="display_name" value="{esc(display_name(user))}" minlength="2" maxlength="40" required autocomplete="nickname"></label><div class="form-actions"><button class="button primary" type="submit">{tr(lang,"Lưu nickname","Save nickname")}</button><p id="displayNameStatus" class="muted" role="status"></p></div></form></section>
<section class="account-favorites"><div class="section-title"><div><p class="eyebrow">{tr(lang,"Bộ sưu tập của bạn","Your collection")}</p><h2>{tr(lang,"Yêu thích","Favorites")}</h2></div><span>{len(favorites)}</span></div><div class="game-grid">{cards or empty}</div></section></main>'''
    return layout(tr(lang, "Tài khoản", "Account"), body, lang, user, csrf)


def offline_page(lang, user, csrf):
    """Minimal offline notice.

    Local ROM import, library management, core preloading and browser gameplay
    now live only in the installed Vibe Coded Emulator app, so this page communicates the
    connection state and points at the app instead of duplicating that UI.
    """
    facts = "".join(
        f'<li>{ref_icon(icon)}{label}</li>'
        for icon, label in (
            ("hard-drive", "Play local games"),
            ("folder-open", "Use your own ROMs"),
            ("wifi", "No internet required"),
        )
    )
    body = f'''<main class="page offline-state-page">
<section class="offline-notice" aria-labelledby="offlineTitle">
<span class="offline-notice-icon">{ref_icon("gamepad-2")}</span>
<h1 id="offlineTitle">You're offline</h1>
<p>No internet connection. Games already stored on this device can still be played in the Vibe Coded Emulator app.</p>
<div class="offline-notice-actions"><a class="button primary" href="/offline">{ref_icon("arrow-right")}Try Again</a></div>
<ul class="offline-notice-facts">{facts}</ul>
</section></main>'''
    return layout("Offline", body, lang, user, csrf, offline=True)


def core_preload_page(system, lang):
    if system not in SYSTEMS or system == "html5":
        return status_page(404, lang)
    config = {"mode": "preload", "title": "Core preload", "slug": f"core-preload-{system}", "system": system, "channel": SYSTEMS[system][1], "lang": lang}
    ui_asset = versioned_player_asset("player-ui.js")
    runtime_asset = versioned_player_asset("player-runtime.js")
    player_asset = versioned_player_asset("player.js")
    controller_utility_asset = f"/static/controller-utility.js?v={ASSET_VERSION}"
    renderer_asset = versioned_player_asset("renderer-worker.js")
    nds_touch_asset = versioned_player_asset("nds-touch.js")
    body = f'<main class="player-shell" data-player=\'{esc(json.dumps(config,ensure_ascii=False))}\'><section class="player-stage"><div id="game"></div><div id="tvPad" aria-label="Virtual controller"></div><div id="playerNotice" class="player-notice" role="status" aria-live="polite"></div><div id="loading" class="loading" role="status" aria-live="polite"><strong id="loadingText">Preparing</strong><div class="progress" role="progressbar" aria-label="Core download progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><i id="loadingBar"></i></div><span id="loadingPct">0%</span></div></section></main><script src="{ui_asset}" defer></script><script src="{runtime_asset}" defer></script><script src="{renderer_asset}" defer></script><script src="{nds_touch_asset}" defer></script><script src="{controller_utility_asset}" defer></script><script src="{player_asset}" defer></script>'
    return layout("Core preload", body, lang, None, "", player=True)


def multiplayer_page(lang, user, csrf, slug=""):
    """Room surface for the AN3 multiplayer service.

    Only routed when MULTIPLAYER_ENABLED is true, so it never appears in
    production. A game slug prefills the exact room signature so two players
    who open the same game generate an identical signature. Opening the page
    without a game shows a library picker, so the flow stays game-centered.
    Normal UI shows only user concepts; relay internals live under Advanced
    Diagnostics.
    """

    game = None
    if slug:
        with db() as conn:
            game = conn.execute("SELECT * FROM games WHERE slug=?", (slug,)).fetchone()
    games = []
    if game is None:
        with db() as conn:
            games = conn.execute("SELECT * FROM games WHERE published=1 ORDER BY title_en LIMIT 50").fetchall()

    system = (game["system"] if game else "")
    core = PRIMARY_CORES.get(system, system) if game else ""
    rom_hash = game_rom_hash(game) if game else ""
    selected_title = game_title(game, lang) if game else ""
    capability = multiplayer_capability(system)

    available_panel = f'''<section class="mp-grid" id="mpPanel" hidden>
<div class="mp-card">
<h2>{tr(lang,"Tạo phòng","Create Room")}</h2>
<p class="muted">{tr(lang,"Bắt đầu phòng và chia sẻ mã phòng.","Start a room and share the room code.")}</p>
<button id="mpCreateBtn" type="button" class="button primary">{tr(lang,"Tạo phòng","Create Room")}</button>
<div id="mpRoomBox" class="mp-room" hidden>
<p class="mp-room-label">{tr(lang,"Mã phòng","Room Code")}</p>
<p id="mpRoomCode" class="ctrl-code">—</p>
<div class="form-actions"><button id="mpCopyCode" type="button" class="button">{tr(lang,"Sao chép mã","Copy Code")}</button><button id="mpShowQr" type="button" class="button">{tr(lang,"Hiện mã QR","Show QR")}</button><button id="mpCancelRoom" type="button" class="button danger">{tr(lang,"Hủy","Cancel")}</button></div>
<img id="mpRoomQr" class="ctrl-qr" alt="{tr(lang,"Mã QR phòng chơi","Room QR code")}" hidden>
<p id="mpWaitState" class="muted" role="status">{tr(lang,"Đang chờ người chơi…","Waiting for player…")}</p>
<p><a id="mpRoomLink" class="button" href="#" hidden>{tr(lang,"Mở game để chơi","Open the game to play")}</a></p>
</div>
<p id="mpCreateOut" class="muted" role="status"></p>
</div>
<div class="mp-card">
<h2>{tr(lang,"Vào phòng","Join Room")}</h2>
<label>{tr(lang,"Mã phòng","Room code")}<input id="mpCode" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="H7K4PF"></label>
<button id="mpJoinBtn" type="button" class="button primary">{tr(lang,"Vào phòng","Join")}</button>
<p id="mpJoinOut" class="muted" role="status"></p>
</div>
</section>
<details class="tech-details"><summary>{tr(lang,"Chi tiết kỹ thuật","Technical details")}</summary><div class="tech-body">
<p>{tr(lang,"Hệ máy","System")}: <code id="mpSystemView">{esc(system)}</code> · Core: <code id="mpCoreView">{esc(core)}</code></p>
<p>ROM SHA-256: <code id="mpHashView">{esc(rom_hash[7:23] if rom_hash.startswith("sha256:") else rom_hash[:16])}</code></p>
<p id="mpTransportView">Transport: {esc(capability["transport"])}</p>
</div></details>
<input type="hidden" id="mpSystem" value="{esc(system)}"><input type="hidden" id="mpCore" value="{esc(core)}"><input type="hidden" id="mpHash" value="{esc(rom_hash)}">
<input type="hidden" id="mpJSystem" value="{esc(system)}"><input type="hidden" id="mpJCore" value="{esc(core)}"><input type="hidden" id="mpJHash" value="{esc(rom_hash)}">
<input type="hidden" id="mpHost" value="host"><input type="hidden" id="mpJDevice" value="phone"><input type="hidden" id="mpSlug" value="{esc(slug)}">'''

    unavailable_panel = f'''<section class="admin-form mp-unavailable" id="mpUnavailable" hidden>
<h2>{tr(lang,"Không khả dụng","Not available")}</h2>
<p class="muted">{tr(lang,"Hệ máy này chưa được kiểm chứng cho chơi chung.","Not available for this system.")}</p>
<p class="muted">{tr(lang,"Chơi chung hiện chỉ hoạt động với các hệ máy đã được kiểm chứng.","Multiplayer is currently offered only for verified systems.")}</p>
</section>'''

    if game is not None:
        # A direct game link reveals the decision immediately; the picker case
        # leaves both panels hidden and lets the script choose on selection.
        if capability["available"]:
            available_panel = available_panel.replace('id="mpPanel" hidden', 'id="mpPanel"', 1)
        else:
            unavailable_panel = unavailable_panel.replace('id="mpUnavailable" hidden', 'id="mpUnavailable"', 1)
        picker = ""
        lead = esc(selected_title)
    else:
        options = "".join(
            f'<option value="{esc(row["slug"])}" data-system="{esc(row["system"])}" '
            f'data-core="{esc(PRIMARY_CORES.get(row["system"], row["system"]))}" '
            f'data-hash="{esc(game_rom_hash(row))}" data-title="{esc(game_title(row, lang))}" '
            f'data-available="{1 if multiplayer_capability(row["system"])["available"] else 0}">{esc(game_title(row, lang))}</option>'
            for row in games
        )
        picker = (
            f'<label>{tr(lang,"Trò chơi","Game")}<select id="mpGameSelect"><option value="">'
            f'{tr(lang,"Chọn một game…","Select a game…")}</option>{options}</select></label>'
            if games else
            f'<p class="muted">{tr(lang,"Hãy thêm game vào thư viện trước.","Add a game to your library first.")}</p>'
        )
        lead = tr(lang, "Chọn một game để chơi chung.", "Select a game to play together.")

    body = f'''<main class="page multiplayer-page">
<section class="library-head"><div><p class="eyebrow">{tr(lang,"Chơi chung","Multiplayer")}</p><h1>{tr(lang,"Chơi chung","Multiplayer")}</h1></div></section>
<section class="mp-setup" id="mpSetup">{picker}<p class="muted" id="mpLead">{lead}</p></section>
{available_panel}
{unavailable_panel}
<script src="/static/multiplayer.js?v={ASSET_VERSION}" defer></script>
</main>'''
    return layout(tr(lang, "Chơi chung", "Multiplayer"), body, lang, user, csrf)


CONTROLLER_QR_MAX_TEXT = 512


def controller_join_url(scheme, host, code):
    """Absolute pairing URL built from the request's own host, never a caller value."""
    host = (host or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9.\-]{1,253}(:\d{1,5})?", host):
        return ""
    return f"{scheme}://{host}/controller/join?code={quote(code)}"


def controller_qr_svg(text, border=4):
    """Render ``text`` as a standalone SVG QR code.

    The output is a plain ``<svg>`` with a single module path: no scripts, no
    external references, no fonts, so it stays inside a strict CSP and can be
    embedded through ``img-src 'self'``.
    """
    if not text or len(text) > CONTROLLER_QR_MAX_TEXT:
        raise ValueError("unsupported QR payload length")
    qr = qrcodegen.QrCode.encode_text(text, qrcodegen.QrCode.Ecc.MEDIUM)
    size = qr.get_size()
    span = size + border * 2
    commands = []
    for y in range(size):
        run_start = -1
        for x in range(size + 1):
            dark = x < size and qr.get_module(x, y)
            if dark and run_start < 0:
                run_start = x
            elif not dark and run_start >= 0:
                commands.append(f"M{run_start + border} {y + border}h{x - run_start}v1h-{x - run_start}z")
                run_start = -1
    path = "".join(commands)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{span}" height="{span}" '
        f'viewBox="0 0 {span} {span}" shape-rendering="crispEdges" role="img" aria-label="QR code">'
        f'<rect width="{span}" height="{span}" fill="#ffffff"/>'
        f'<path d="{path}" fill="#000000"/></svg>'
    )


def controller_host_page(lang, user, csrf):
    body = f'''<main class="page controller-page">
<section class="library-head"><div><p class="eyebrow">{tr(lang,"Điều khiển","Controller")}</p><h1>{tr(lang,"Tay cầm điện thoại","Phone Controller")}</h1></div></section>
<section class="ctrl-panel" id="ctrlHostPanel">
<p class="ctrl-state" id="ctrlState">{tr(lang,"Tắt","Off")}</p>
<p class="muted" id="ctrlHint">{tr(lang,"Bắt đầu phiên trên thiết bị này, sau đó kết nối từ điện thoại.","Start a session on this device, then connect from the phone.")}</p>
<div class="form-actions"><button id="ctrlStart" type="button" class="button primary">{tr(lang,"Bắt đầu phiên tay cầm","Start Controller Session")}</button><button id="ctrlStop" type="button" class="button danger" hidden>{tr(lang,"Dừng","Stop")}</button></div>
<div id="ctrlActive" hidden>
<div class="ctrl-code-box"><span class="muted">{tr(lang,"Mã ghép đôi","Pairing code")}</span><span id="ctrlCode" class="ctrl-code">—</span></div>
<p class="muted">{tr(lang,"Trên điện thoại: Vibe Coded Emulator → Tay cầm → chọn thiết bị này. Hoặc quét mã QR / nhập mã.","On the phone: Vibe Coded Emulator → Controller → pick this device. Or scan the QR / enter the code.")}</p>
<img id="ctrlQr" class="ctrl-qr" alt="{tr(lang,"Mã QR ghép đôi","Pairing QR code")}" hidden>
<p><a id="ctrlLink" href="#">{tr(lang,"Mở liên kết ghép đôi","Open pairing link")}</a></p>
</div>
<p id="ctrlStatus" class="muted" role="status"></p>
<p class="muted"><a href="/diagnostics">{tr(lang,"Chẩn đoán nâng cao","Advanced Diagnostics")}</a></p>
</section>
<script src="/static/controller.js?v={ASSET_VERSION}" defer></script>
</main>'''
    return layout(tr(lang, "Điều khiển", "Controller"), body, lang, user, csrf)


def controller_join_page(lang, user, csrf, code=""):
    body = f'''<main class="page ctrl-phone-page">
<section class="ctrl-phone-head">
<div><p class="eyebrow">{tr(lang,"Điều khiển","Controller")}</p><h1 id="ctrlTitle">{tr(lang,"Chế độ tay cầm","Controller Mode")}</h1></div>
<label class="ctrl-layout-picker">{tr(lang,"Bố cục","Layout")}<select id="ctrlLayout">
<option value="auto">{tr(lang,"Tự động","Automatic")}</option>
<option value="gba">GBA</option>
<option value="nds">NDS</option>
<option value="3ds">3DS</option>
<option value="custom">{tr(lang,"Tùy chỉnh","Custom")}</option>
</select></label>
<label class="ctrl-layout-picker">{tr(lang,"Di chuyển","Movement")}<select id="ctrlMovement">
<option value="dpad">D-Pad</option>
<option value="joystick">{tr(lang,"Cần gạt","Analog Joystick")}</option>
<option value="circular">Circular D-pad</option>
</select></label>
</section>
<section id="ctrlJoinPanel" class="ctrl-connect">
<h2>{tr(lang,"Kết nối tới thiết bị","Connect to a device")}</h2>
<ul id="ctrlHosts" class="ctrl-hosts" hidden></ul>
<label>{tr(lang,"Mã ghép đôi","Pairing code")}<input id="ctrlCode" value="{esc(code)}" inputmode="text" autocapitalize="characters" autocomplete="off" spellcheck="false" placeholder="H7K4PF"></label>
<div class="form-actions"><button id="ctrlConnect" type="button" class="button primary">{tr(lang,"Kết nối","Connect")}</button></div>
<p id="ctrlStatus" class="muted" role="status">{tr(lang,"Tắt","Off")}</p>
</section>
<section id="ctrlPad" class="ctrl-pad" hidden>
<div class="ctrl-padbar"><span id="ctrlPadState" class="ctrl-state">{tr(lang,"Đã kết nối","Connected")}</span><button id="ctrlDisconnect" type="button">{tr(lang,"Ngắt","Disconnect")}</button></div>
<div class="ctrl-touchscreen" id="ctrlTouchscreen" data-role="touchscreen" hidden>{tr(lang,"Màn hình cảm ứng","Touch Screen")}</div>
<div class="ctrl-shoulders"><button type="button" class="ctrl-key ctrl-shoulder" data-btn="l">L</button><button type="button" class="ctrl-key ctrl-shoulder" data-btn="r">R</button></div>
<div class="ctrl-main">
<div class="ctrl-dpad" data-role="dpad">
<button type="button" class="ctrl-key dpad-up" data-btn="up" aria-label="Up">▲</button>
<button type="button" class="ctrl-key dpad-left" data-btn="left" aria-label="Left">◀</button>
<button type="button" class="ctrl-key dpad-right" data-btn="right" aria-label="Right">▶</button>
<button type="button" class="ctrl-key dpad-down" data-btn="down" aria-label="Down">▼</button>
</div>
<div id="ctrlCircular" class="ctrl-circular" data-role="circular" role="group" aria-label="Circular D-pad" hidden>
<span class="ctrl-circular-arrow up" data-dir="up">▲</span>
<span class="ctrl-circular-arrow left" data-dir="left">◀</span>
<span class="ctrl-circular-arrow right" data-dir="right">▶</span>
<span class="ctrl-circular-arrow down" data-dir="down">▼</span>
</div>
<div class="ctrl-sticks" data-role="sticks">
<span class="ctrl-stick" data-stick="left" role="slider" aria-label="{tr(lang,"Cần gạt trái","Left stick")}" tabindex="0"></span>
<span class="ctrl-stick" data-stick="right" role="slider" aria-label="{tr(lang,"Cần gạt phải","Right stick")}" tabindex="0"></span>
</div>
<div class="ctrl-face">
<button type="button" class="ctrl-key face-x" data-btn="x">X</button>
<button type="button" class="ctrl-key face-y" data-btn="y">Y</button>
<button type="button" class="ctrl-key face-a" data-btn="a">A</button>
<button type="button" class="ctrl-key face-b" data-btn="b">B</button>
</div>
</div>
<div class="ctrl-system"><button type="button" class="ctrl-key" data-btn="select">Select</button><button type="button" class="ctrl-key" data-btn="start">Start</button></div>
<div class="ctrl-utility">
<button type="button" class="ctrl-key ctrl-util" data-util="speed_down">Speed −</button>
<button type="button" class="ctrl-key ctrl-util" data-util="speed_up">Speed +</button>
<button type="button" class="ctrl-key ctrl-util" data-util="quick_save">Quick Save</button>
<button type="button" class="ctrl-key ctrl-util" data-util="quick_load">Quick Load</button>
<button type="button" class="ctrl-key ctrl-util" data-util="open_menu">Menu</button>
<label class="ctrl-layout-picker ctrl-save-slot">Save slot<select id="ctrlSaveSlot"><option value="1">Slot 1</option><option value="2">Slot 2</option><option value="3">Slot 3</option><option value="4">Slot 4</option><option value="5">Slot 5</option><option value="6">Slot 6</option><option value="7">Slot 7</option><option value="8">Slot 8</option><option value="9">Slot 9</option><option value="10">Slot 10</option></select></label>
</div>
</section>
<p class="muted ctrl-phone-foot"><a href="/diagnostics">{tr(lang,"Chẩn đoán nâng cao","Advanced Diagnostics")}</a></p>
<script src="/static/input-actions.js?v={ASSET_VERSION}" defer></script>
<script src="/static/controller.js?v={ASSET_VERSION}" defer></script>
</main>'''
    return layout(tr(lang, "Tay cầm", "Controller"), body, lang, user, csrf)


def sync_page(lang, user, csrf):
    body = f'''<main class="page sync-page">
<section class="library-head"><div><p class="eyebrow">{tr(lang,"Đồng bộ","Sync")}</p><h1>{tr(lang,"Đồng bộ","Sync")}</h1></div></section>
<section class="sync-panel" id="syncPanel">
<div class="sync-mode" id="syncLanRow">
<label class="check"><input type="checkbox" id="syncLanEnabled"> {tr(lang,"Đồng bộ LAN","LAN Sync")}</label>
<p id="syncLanDetail" class="muted">{tr(lang,"Đồng bộ save và save state giữa các thiết bị trên cùng mạng LAN.","Sync saves and save states between devices on this local network.")}</p>
</div>
<div class="sync-mode" id="syncGoogleRow">
<label class="check"><input type="checkbox" id="syncGoogleEnabled" disabled aria-disabled="true"> {tr(lang,"Đồng bộ Google","Google Sync")}</label>
<p id="syncGoogleDetail" class="muted" role="status">{tr(lang,"Sắp có","Coming later")}</p>
</div>
<div class="sync-mode">
<label for="syncMode">{tr(lang,"Chế độ","Mode")}</label>
<select id="syncMode"></select>
<p id="syncModeDetail" class="muted"></p>
</div>
<fieldset class="sync-content">
<legend>{tr(lang,"Nội dung đồng bộ","Sync content")}</legend>
<label class="check"><input type="checkbox" id="syncContentSave"> {tr(lang,"Tệp save","Save files")}</label>
<label class="check"><input type="checkbox" id="syncContentState"> {tr(lang,"Save state","Save states")}</label>
<label class="check"><input type="checkbox" id="syncContentLibrary"> {tr(lang,"Thư viện game","Game library")}</label>
<label class="check"><input type="checkbox" id="syncContentRom"> {tr(lang,"Tệp ROM","ROM files")}</label>
<p id="syncRomWarning" class="sync-warning" hidden>{tr(lang,"Thư viện ROM có thể tốn nhiều dung lượng và băng thông.","ROM libraries may use significant storage and network bandwidth.")}</p>
</fieldset>
<div class="form-actions"><button id="syncSave" type="button" class="button primary">{tr(lang,"Lưu","Save")}</button><button id="syncRefreshPeers" type="button" class="button">{tr(lang,"Tìm thiết bị","Find devices")}</button><button id="syncTransfer" type="button" class="button" disabled>{tr(lang,"Đồng bộ save state","Sync save states")}</button></div>
<p id="syncStatus" class="muted" role="status" aria-live="polite"></p>
<small id="syncAvailability" class="muted"></small>
<h2 class="sync-devices-title">{tr(lang,"Thiết bị","Devices")}</h2>
<ul id="syncPeers" class="sync-devices"></ul>
<div id="syncConflicts" class="sync-conflicts" hidden></div>
<p class="muted"><a href="/diagnostics">{tr(lang,"Chẩn đoán nâng cao","Advanced Diagnostics")}</a></p>
</section>
<script src="/static/lan-peer.js?v={ASSET_VERSION}" defer></script><script src="/static/sync-transfer.js?v={ASSET_VERSION}" defer></script><script src="/static/sync.js?v={ASSET_VERSION}" defer></script>
</main>'''
    return layout(tr(lang, "Đồng bộ", "Sync"), body, lang, user, csrf)


def diagnostics_page(lang, user, csrf):
    """Advanced Diagnostics: technical detail that normal UI deliberately hides.

    Nothing here is a secret: the page reads the environment/capability snapshot
    endpoint and shows the same fields the normal surfaces keep out of the way.
    """

    body = f'''<main class="page diagnostics-page">
<section class="library-head"><div><p class="eyebrow">{tr(lang,"Nâng cao","Advanced")}</p><h1>{tr(lang,"Chẩn đoán","Diagnostics")}</h1></div></section>
<section class="diag-panel">
<p class="muted">{tr(lang,"Số liệu vận hành và giao thức. Không chứa mã token hay địa chỉ thiết bị.","Operational and protocol detail. Never contains session tokens or device addresses.")}</p>
<pre id="diagOutput" class="diag-output" role="status">{tr(lang,"Đang tải…","Loading…")}</pre>
<div class="form-actions"><button id="diagRefresh" type="button" class="button">{tr(lang,"Làm mới","Refresh")}</button><button id="diagCopy" type="button" class="button">{tr(lang,"Sao chép","Copy")}</button></div>
</section>
<script src="/static/diagnostics.js?v={ASSET_VERSION}" defer></script>
</main>'''
    return layout(tr(lang, "Chẩn đoán", "Diagnostics"), body, lang, user, csrf)


def bug_report_page(lang, user, csrf):
    """User-facing bug report form: collect, sanitized preview, explicit consent.

    The page never contains a GitHub token. The browser only builds a local,
    sanitized payload and posts it after the user ticks the consent box.
    """

    body = f'''<main class="page diagnostics-page">
<section class="library-head"><div><p class="eyebrow">{tr(lang,"HỖ TRỢ","SUPPORT")}</p><h1>{tr(lang,"Báo lỗi","Report a bug")}</h1></div></section>
<section class="diag-panel">
<p class="muted">{tr(lang,"Chẩn đoán được thu thập và che dấu token, đường dẫn, địa chỉ thiết bị ngay trên máy bạn trước khi xem trước và gửi.","Diagnostics are collected and stripped of tokens, paths, and device identifiers on your device before preview and upload.")}</p>
<label class="wide"><span>{tr(lang,"Mô tả vấn đề","Describe the problem")}</span><textarea id="bugDescription" maxlength="4000" rows="6" placeholder="{tr(lang,"Vấn đề xảy ra khi nào và như thế nào?","What happened, and what were you doing?")}"></textarea></label>
<label><span>{tr(lang,"Tên game (không bắt buộc)","Game name (optional)")}</span><input id="bugGame" maxlength="200" autocomplete="off"></label>
<div class="form-actions"><button id="bugPreview" type="button" class="button">{tr(lang,"Xem trước bản đã lọc","Preview sanitized report")}</button></div>
<pre id="bugPreviewOutput" class="diag-output" role="status" data-build="{esc(RUNTIME_BUILD_ID)}" data-app-version="{esc(ASSET_VERSION)}">{tr(lang,"Đang thu thập…","Collecting…")}</pre>
<label class="batch-confirmation"><input id="bugConsent" type="checkbox"> {tr(lang,"Tôi đồng ý gửi báo cáo đã lọc này cho nhà phát triển.","I consent to sending this sanitized report to the maintainers.")}</label>
<div class="form-actions"><button id="bugSubmit" type="button" class="button primary" disabled>{tr(lang,"Gửi báo cáo","Send report")}</button><span id="bugStatus" role="status"></span></div>
</section>
<script src="/static/bug-report.js?v={ASSET_VERSION}" defer></script>
</main>'''
    return layout(tr(lang, "Báo lỗi", "Report a bug"), body, lang, user, csrf)


def licenses_page(lang, user, csrf):
    rows = "".join(
        f'<tr><td>{esc(name)}</td><td>{esc(license_name)}</td><td>{esc(holder)}</td></tr>'
        for name, license_name, holder in LICENSES_THIRD_PARTY
    )
    body = f'''<main class="page licenses-page">
<section class="library-head"><div><p class="eyebrow">{tr(lang,"GIẤY PHÉP","LICENSES")}</p><h1>{tr(lang,"Giấy phép &amp; nguồn mở","Licenses &amp; open source")}</h1></div></section>
<section class="native-card">
<h2>{esc(SITE_NAME)}</h2>
<p>{tr(lang,"Phần mềm này là phần mềm tự do theo GNU General Public License, phiên bản 3 hoặc mới hơn (GPL-3.0-or-later).","This software is free software under the GNU General Public License, version 3 or later (GPL-3.0-or-later).")}</p>
<p class="muted">Copyright (C) 2026 Vibe Coded Emulator contributors.</p>
<ul>
<li>{tr(lang,"Được dùng cho mục đích cá nhân và thương mại.","Use for personal and commercial purposes is permitted.")}</li>
<li>{tr(lang,"Được sửa đổi, phân phối và tạo bản phái sinh.","Modification, redistribution and forks are permitted.")}</li>
<li>{tr(lang,"Bản phân phối phải giữ thông báo bản quyền/giấy phép và cung cấp mã nguồn tương ứng theo GPL.","Distributions must keep the copyright/license notices and provide the corresponding source under the GPL.")}</li>
<li>{tr(lang,"Bản phái sinh không bắt buộc giữ tên, logo hay giao diện gốc.","Forks do not have to keep the original name, logo or UI.")}</li>
</ul>
<p><a href="/licenses/gpl-3.0.txt">GNU General Public License v3</a> · {tr(lang,"Mã nguồn:","Source:")} <code>{esc(SOURCE_REPOSITORY)}</code></p>
</section>
<section class="native-card">
<h2>{tr(lang,"Thành phần bên thứ ba","Third-party components")}</h2>
<p class="muted">{tr(lang,"Mỗi thành phần giữ bản quyền và giấy phép riêng.","Each component keeps its own copyright and license.")}</p>
<table class="licenses-table"><thead><tr><th>{tr(lang,"Thành phần","Component")}</th><th>{tr(lang,"Giấy phép","License")}</th><th>{tr(lang,"Bản quyền","Copyright")}</th></tr></thead><tbody>{rows}</tbody></table>
</section>
</main>'''
    return layout(tr(lang, "Giấy phép", "Licenses"), body, lang, user, csrf)


def player_page(game, lang, user, csrf):
    title = game_title(game, lang)
    icon = lambda name: f'<img src="/static/ui-{name}.svg?v={ASSET_VERSION}" alt="" width="24" height="24">'
    if game["system"] == "html5":
        game_area = f'<iframe class="custom-frame" src="/custom/{game["id"]}/" title="{esc(title)}" sandbox="allow-scripts allow-pointer-lock allow-forms" allow="fullscreen; gamepad"></iframe>'
        toolbar_extra = ""
        slot_panel = ""
        pad_panel = ""
        mode = "html5"
    else:
        game_area = '<div id="game"></div><div id="tvPad" aria-label="virtual controller"></div>'
        touch_toggle = f'<button id="toggleTouch" class="touch-toggle" type="button" aria-pressed="true" title="{tr(lang,"Ẩn phím ảo","Hide virtual controls")}" aria-label="{tr(lang,"Bật hoặc tắt phím ảo","Toggle virtual controls")}">Touch</button>' if game["system"] in {"gb", "gba", "nds", "3ds"} else ""
        toolbar_extra = f'{touch_toggle}<button id="slotMenu" type="button" aria-expanded="false" title="{tr(lang,"Save slot","Save slots")}" aria-label="{tr(lang,"Mở save slot trên thiết bị","Open save slots on this device")}">{icon("save")}</button><button id="playerControls" type="button" aria-expanded="false" title="{tr(lang,"Tùy chọn khác","More options")}" aria-label="{tr(lang,"Mở tùy chọn trình phát","Open player options")}">{icon("more")}</button>'
        speed_settings = f'''<section class="player-settings-group player-speed-settings"><header><strong>{tr(lang,"Tốc độ","Speed")}</strong><small>{tr(lang,"Chỉ trong phiên","Session only")}</small></header><div class="player-speed-controls" role="group" aria-label="{tr(lang,"Tốc độ trò chơi","Game speed")}"><button id="speedDown" type="button" aria-label="{tr(lang,"Chậm hơn","Slower")}">−</button><output id="speedValue" aria-live="polite">1×</output><button id="speedUp" type="button" aria-label="{tr(lang,"Nhanh hơn","Faster")}">+</button></div><small id="speedHint" class="muted">{tr(lang,"Điều chỉnh tốc độ hoạt động sau khi game khởi động.","Speed controls become available after the game starts.")}</small></section>''' if game["system"] in {"gba", "nds"} else ""
        game_settings = f'''<section class="player-settings-group player-game-settings"><header><strong>{tr(lang,"Trò chơi & save","Game & saves")}</strong><small>{tr(lang,"Trên thiết bị này","On this device")}</small></header><div class="player-panel-actions"><button id="saveState" type="button">{tr(lang,"Tải save state","Download save state")}</button><button id="loadState" type="button">{tr(lang,"Nạp save state","Load save state")}</button><button id="syncSaveFile" type="button" disabled>{tr(lang,"Đồng bộ tệp save","Sync game save")}</button><input id="stateFile" type="file" accept=".state,.savestate,application/octet-stream" hidden></div><div id="syncSaveConflicts" class="sync-conflicts" hidden></div></section>'''
        autosave_settings = f'''<section class="player-settings-group player-autosave-settings"><header><strong>{tr(lang,"Tự động lưu","Autosave")}</strong><small>{tr(lang,"Trên thiết bị này","On this device")}</small></header><label><span>{tr(lang,"Chế độ","Mode")}</span><select id="autosaveMode"><option value="off">{tr(lang,"Tắt","Off")}</option><option value="exit">{tr(lang,"Khi thoát game","On game exit")}</option><option value="30">{tr(lang,"Mỗi 30 giây","Every 30 seconds")}</option><option value="10">{tr(lang,"Mỗi 10 giây","Every 10 seconds")}</option><option value="5">{tr(lang,"Mỗi 5 giây","Every 5 seconds")}</option></select></label><small class="muted">{tr(lang,"Autosave dùng slot riêng, không thay thế save thủ công.","Autosave uses its own slot and never replaces a manual save state.")}</small></section>'''
        exit_settings = f'''<section class="player-settings-group player-exit-settings"><header><strong>{tr(lang,"Thoát game","Exit game")}</strong></header><p class="player-setting-copy">{tr(lang,"Dừng phiên giả lập và quay về thư viện.","Stop this emulation session and return to the library.")}</p><div class="player-panel-actions"><button id="exitGame" type="button">{tr(lang,"Thoát game","Exit game")}</button></div></section>'''
        phone_controller_button = f'<button id="phoneController" type="button">{tr(lang,"Điện thoại làm tay cầm","Phone controller")}</button>' if CONTROLLER_ENABLED else ""
        multiplayer_button = f'<button id="playerMultiplayer" type="button">{tr(lang,"Chơi chung","Multiplayer")}</button>' if MULTIPLAYER_ENABLED else ""
        advanced_settings = f'''<section class="player-settings-group player-advanced-settings"><header><strong>{tr(lang,"Nâng cao","Advanced")}</strong></header><p class="player-setting-copy">{tr(lang,"Mở menu EmulatorJS để dùng các cài đặt core đã được hỗ trợ.","Open the EmulatorJS menu for its supported core settings.")}</p><div class="player-panel-actions">{multiplayer_button}{phone_controller_button}<button id="castScreen" type="button">{tr(lang,"Dò TV & phát màn hình","Find TV & cast game")}</button><button id="emulatorMenu" type="button">{tr(lang,"Mở menu giả lập","Open emulator menu")}</button></div></section>'''
        slot_rows = "".join(f'<div class="save-slot" data-slot="{slot}"><strong>{tr(lang,"Slot","Slot")} {slot}</strong><small>{tr(lang,"Trống","Empty")}</small><button data-save-slot="{slot}">{tr(lang,"Lưu","Save")}</button><button data-load-slot="{slot}" disabled>{tr(lang,"Nạp","Load")}</button></div>' for slot in range(1, 11))
        auto_slot_row = f'<div class="save-slot save-slot-auto" data-auto-slot><strong>{tr(lang,"Tự động lưu","Autosave")}</strong><small>{tr(lang,"Trống","Empty")}</small><button data-save-auto>{tr(lang,"Lưu","Save")}</button><button data-load-auto disabled>{tr(lang,"Nạp","Load")}</button></div>'
        slot_panel = f'<section id="slotPanel" class="slot-panel" hidden role="dialog" aria-label="{tr(lang,"Save slot trên thiết bị này","Save slots on this device")}"><header><strong>{tr(lang,"Save slot trên thiết bị này","Save slots on this device")}</strong><button id="closeSlots" type="button">{tr(lang,"Đóng","Close")}</button></header>{auto_slot_row}{slot_rows}</section>'
        controller_panel = f'''<section id="ctrlPhonePanel" class="slot-panel controller-panel" hidden role="dialog" aria-label="{tr(lang,"Điện thoại làm tay cầm","Phone controller")}"><header><strong>{tr(lang,"Điện thoại làm tay cầm","Phone controller")}</strong><button id="closeCtrlPhone" type="button">{tr(lang,"Đóng","Close")}</button></header><p class="muted">{tr(lang,"Quét mã QR bằng điện thoại cùng mạng LAN. Tay cầm chỉ được điều khiển khi game đang chạy.","Scan the QR with a phone on the same LAN. The phone only drives the game while it is running.")}</p><img id="ctrlPhoneQr" class="ctrl-qr" alt="{tr(lang,"Mã QR ghép đôi","Pairing QR code")}" hidden><p><strong>{tr(lang,"Mã ghép đôi","Pairing code")}:</strong> <span id="ctrlPhoneCode" class="ctrl-code">—</span></p><p><strong>{tr(lang,"Liên kết","Link")}:</strong> <a id="ctrlPhoneLink" href="#">—</a></p><p id="ctrlPhoneStatus" class="muted" role="status"></p></section>''' if CONTROLLER_ENABLED else ""
        multiplayer_panel = f'''<section id="mpPlayerPanel" class="slot-panel multiplayer-panel" hidden role="dialog" aria-label="{tr(lang,"Chơi chung","Multiplayer")}"><header><strong>{tr(lang,"Chơi chung","Multiplayer")}</strong><button id="closeMpPanel" type="button">{tr(lang,"Đóng","Close")}</button></header><p class="muted">{tr(lang,"Chơi cùng một game trên cả hai thiết bị.","Play the same game on both devices.")}</p><div class="form-actions"><button id="mpPlayerCreate" type="button" class="button">{tr(lang,"Tạo phòng","Create Room")}</button><button id="mpPlayerHost" type="button" class="button primary">{tr(lang,"Bắt đầu","Start Hosting")}</button></div><p><strong>{tr(lang,"Mã phòng","Room Code")}:</strong> <span id="mpPlayerCode" class="ctrl-code">—</span></p><img id="mpPlayerQr" class="ctrl-qr" alt="{tr(lang,"Mã QR phòng chơi","Room QR code")}" hidden><p><a id="mpPlayerLink" href="#">{tr(lang,"Liên kết phòng","Room link")}</a></p><label>{tr(lang,"Nhập mã phòng","Enter a room code")}<input id="mpPlayerJoinCode" autocomplete="off" spellcheck="false" autocapitalize="characters"></label><div class="form-actions"><button id="mpPlayerJoin" type="button" class="button">{tr(lang,"Vào phòng","Join Room")}</button><button id="mpPlayerLeave" type="button" class="button">{tr(lang,"Rời phòng","Leave Room")}</button></div><p id="mpPlayerStatus" class="muted" role="status"></p></section>''' if MULTIPLAYER_ENABLED else ""
        pad_controls = [("dpad", "D-pad"), ("a", "A"), ("b", "B"), ("start", "Start"), ("select", "Select")]
        if game["system"] in {"gba", "nds", "3ds"}:
            pad_controls.extend([("l", "L"), ("r", "R")])
        if game["system"] in {"nds", "3ds"}:
            pad_controls.extend([("x", "X"), ("y", "Y")])
        pad_options = "".join(f'<option value="{control}">{label}</option>' for control, label in pad_controls)
        renderer_setting = f'<label><span>{tr(lang,"Trình dựng NDS","NDS renderer")}</span><select id="performanceRenderer"><option value="native">{tr(lang,"Mặc định của core","Core default")}</option><option value="legacy">{tr(lang,"Tương thích / ít yêu cầu hơn","Compatibility / lower demand")}</option></select></label>' if game["system"] == "nds" else ""
        presentation_renderer = f'''<section class="player-settings-group player-presentation-renderer"><header><strong>{tr(lang,"Trình dựng hiển thị","Presentation renderer")}</strong><small>{tr(lang,"Áp dụng sau khi khởi động lại","Applies after restart")}</small></header><label><span>{tr(lang,"Renderer mong muốn","Requested renderer")}</span><select id="presentationRenderer"><option value="auto">Auto</option><option value="webgpu">WebGPU</option><option value="webgl2">WebGL2</option></select></label><div class="player-renderer-status"><span>{tr(lang,"Đã chọn","Requested")}</span><output id="rendererRequestedValue">—</output><span>{tr(lang,"Đang dùng","Effective")}</span><output id="rendererEffectiveValue">—</output><span>{tr(lang,"Fallback","Fallback")}</span><output id="rendererFallbackValue">—</output></div><button id="applyPresentationRenderer" type="button">{tr(lang,"Áp dụng và khởi động lại","Apply and restart")}</button><small id="presentationRendererHint" class="muted">{tr(lang,"Lựa chọn này có hiệu lực sau khi khởi động lại trình phát.","This choice takes effect after restarting the player.")}</small></section>'''
        player_diagnostics = f'''<details id="playerDiagnostics" class="player-diagnostics"><summary>{tr(lang,"Chẩn đoán","Diagnostics")}</summary><pre id="playerDiagnosticsText"></pre><div class="player-diagnostics-actions"><button id="copyPlayerDiagnostics" type="button">{tr(lang,"Sao chép chẩn đoán","Copy diagnostics")}</button><span id="copyPlayerDiagnosticsStatus" role="status"></span></div></details>'''
        performance_settings = f'''<section class="player-settings-group player-performance-settings"><header><strong>{tr(lang,"Hiệu năng","Performance")}</strong><small id="performanceRecommendation"></small></header><p class="player-setting-copy">{tr(lang,"Khuyến nghị cho thiết bị này:","Recommended for this device:")} <strong id="recommendedPerformanceProfile"></strong></p><div class="performance-profile-options" role="radiogroup" aria-label="{tr(lang,"Hồ sơ hiệu năng","Performance profile")}"><label><input type="radio" name="performanceProfile" value="auto"> {tr(lang,"Dùng cài đặt khuyến nghị","Use recommended settings")}</label><label><input type="radio" name="performanceProfile" value="low"> {tr(lang,"Máy yếu / Tiết kiệm pin","Low-end / Battery")}</label><label><input type="radio" name="performanceProfile" value="balanced"> {tr(lang,"Cân bằng","Balanced")}</label><label><input type="radio" name="performanceProfile" value="quality"> {tr(lang,"Chất lượng","Quality")}</label><label><input type="radio" name="performanceProfile" value="custom"> {tr(lang,"Tùy chỉnh","Custom")}</label></div><div id="performanceCustomOptions" class="player-performance-custom" hidden>{renderer_setting}</div><div class="player-settings-actions"><button id="useRecommended" type="button">{tr(lang,"Đặt lại theo khuyến nghị","Use recommended settings")}</button><button id="applyPerformanceProfile" type="button">{tr(lang,"Áp dụng và khởi động lại","Apply and restart")}</button></div><small id="performanceProfileHint" class="muted"></small></section>'''
        pad_settings = f'''<section class="player-pad-settings"><header><strong>{tr(lang,"Phím ảo","Virtual controls")}</strong></header><label><span>{tr(lang,"Điều hướng","Directional control")}</span><select id="padDirectionalControl"><option value="dpad">D-Pad</option><option value="joystick">Analog Joystick</option></select></label><label><span>{tr(lang,"Kích thước chung","Overall size")} <output id="padGlobalScaleValue">100%</output></span><input id="padGlobalScale" type="range" min="70" max="100" step="1" value="100"></label><small id="padGlobalScaleHint" class="muted">{tr(lang,"Mức tối đa giữ nguyên bố cục đã duyệt để tránh chồng phím trên màn hình hẹp.","The maximum keeps the approved layout from overlapping on narrow screens.")}</small><div><button id="resetPadGlobalScale" type="button">{tr(lang,"Đặt lại kích thước chung","Reset overall size")}</button></div><details class="player-pad-advanced"><summary>{tr(lang,"Kích thước từng phím","Individual control sizes")}</summary><p class="player-setting-copy">{tr(lang,"Tỷ lệ tính theo kích thước mặc định của từng phím. Không thể lưu mức làm phím chồng nhau hoặc ra ngoài màn hình.","Sizes are relative to each control’s approved default. Unsafe overlap and off-screen sizes are not saved.")}</p><label><span>{tr(lang,"Phím cần chỉnh","Control to resize")}</span><select id="padTarget">{pad_options}</select></label><label><span>{tr(lang,"Kích thước tương đối","Relative size")} <output id="padSizeValue">100%</output></span><input id="padSize" type="range" min="50" max="200" step="1" value="100"></label><small id="padSizeHint" class="muted"></small><div class="player-pad-button-actions"><button id="resetPadTarget" type="button">{tr(lang,"Đặt lại phím này","Reset this control")}</button><button id="resetPadSizes" type="button">{tr(lang,"Đặt lại từng phím","Reset all individual sizes")}</button></div></details><label><span>{tr(lang,"Độ mờ","Opacity")}</span><input id="padOpacity" type="range" min="30" max="100" step="1"></label><div class="player-pad-actions"><button id="editPad" type="button">{tr(lang,"Kéo thả","Move")}</button><button id="resetPadLayout" type="button">{tr(lang,"Đặt lại bố cục này","Reset this layout")}</button><button id="resetPad" type="button">{tr(lang,"Đặt lại tất cả phím ảo","Reset all virtual controls")}</button></div></section>''' if game["system"] in {"gb", "gba", "nds", "3ds"} else ""
        if pad_settings:
            pad_settings = pad_settings.replace('<section class="player-pad-settings">', f'<section class="player-settings-group player-controls-settings player-pad-settings"><header><strong>{tr(lang,"Điều khiển","Controls")}</strong><small>{tr(lang,"Phím ảo","Virtual controls")}</small></header><div class="player-controls-visibility"><span>{tr(lang,"Phím ảo","Virtual controls")}</span><button id="togglePad" type="button" aria-pressed="false">{tr(lang,"Hiện phím ảo","Show virtual controls")}</button></div>', 1).replace(f'<header><strong>{tr(lang,"Phím ảo","Virtual controls")}</strong></header>', '', 1)
        pad_panel = f'<section id="padPanel" class="pad-panel" role="dialog" aria-label="{tr(lang,"Tùy chọn trình phát","Player options")}"><header><strong>{tr(lang,"Tùy chọn trình phát","Player options")}</strong><button id="closePad" type="button">{tr(lang,"Đóng","Close")}</button></header>{presentation_renderer}{player_diagnostics}{performance_settings}{speed_settings}{pad_settings}{game_settings}{autosave_settings}{exit_settings}{advanced_settings}</section>'
        mode = "emulator"
    config = {
        "mode": mode, "title": title, "slug": game["slug"], "system": game["system"],
        "romUrl": f"/game-file/{game['slug']}/{quote(browser_rom_name(game))}", "channel": SYSTEMS[game["system"]][1],
        "downloadName": game["rom_name"], "lang": lang, "ndsDebugAllowed": NDS_DEBUG_ALLOWED,
        "netplayServer": NETPLAY_ORIGIN, "netplayGameId": f"an3:{game['id']}:{game['system']}",
        "controllerEnabled": CONTROLLER_ENABLED,
        "multiplayerEnabled": MULTIPLAYER_ENABLED,
        "roomSignature": {
            "system": game["system"],
            "core": PRIMARY_CORES.get(game["system"], game["system"]),
            "romHash": game_rom_hash(game),
        },
    }
    back_path = f"/game/{game['slug']}"
    body = f"""<main class="player-shell" data-player='{esc(json.dumps(config,ensure_ascii=False))}'>
<div class="player-toolbar" role="toolbar" aria-label="{tr(lang,'Điều khiển trình phát','Player controls')}"><a class="player-back" href="{back_path}" title="{tr(lang,'Quay lại','Back')}" aria-label="{tr(lang,'Quay lại trang game','Back to game details')}">{icon("arrow-left")}</a><span class="player-title">{esc(title)}</span><div class="player-toolbar-actions"><button id="fullscreen" type="button" title="{tr(lang,'Toàn màn hình','Fullscreen')}" aria-label="{tr(lang,'Toàn màn hình','Fullscreen')}">{icon("maximize")}</button>{toolbar_extra}</div></div>
<section class="player-stage player-stage-ui">{game_area}<div class="player-status"><span class="player-runtime-state"><i aria-hidden="true"></i><span id="playerStatusText">{tr(lang,'Đang chuẩn bị','Preparing')}</span></span><span id="playerSaveStatus" class="player-save-state">{tr(lang,'Chưa có save trên thiết bị','No save on this device')}</span><div id="playerNotice" class="player-notice" role="status" aria-live="polite"></div></div><div id="loading" class="loading" role="status" aria-live="polite"><strong id="loadingText">{tr(lang,'Đang chuẩn bị','Preparing')}</strong><div class="progress" role="progressbar" aria-label="{tr(lang,'Tiến trình khởi động','Startup progress')}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><i id="loadingBar"></i></div><span id="loadingPct">0%</span></div></section>
{slot_panel}{pad_panel}{controller_panel}{multiplayer_panel}</main>
<script src="{versioned_player_asset("player-ui.js")}" defer></script><script src="{versioned_player_asset("player-runtime.js")}" defer></script><script src="{versioned_player_asset("renderer-worker.js")}" defer></script><script src="{versioned_player_asset("nds-touch.js")}" defer></script><script src="{versioned_player_asset("lan-peer.js")}" defer></script><script src="{versioned_player_asset("sync-transfer.js")}" defer></script><script src="{versioned_player_asset("player.js")}" defer></script>"""
    return layout(title, body, lang, user, csrf, player=True)


DASHBOARD_RANGES = (
    ("7", "7 days", 7),
    ("30", "30 days", 30),
    ("90", "90 days", 90),
    ("all", "All time", None),
)
DASHBOARD_DEFAULT_RANGE = "30"


def dashboard_analytics(conn, days):
    """Return visits/downloads for the selected window plus its comparison.

    ``days`` of ``None`` means all time. The result is a tuple of
    ``(totals, previous, series)`` where the totals are session-collapsed counts
    for the window, ``previous`` covers the equal-length window before it, and
    ``series`` is a list of ``(day, visits, downloads)`` points.
    """
    now = int(time.time())
    today = datetime.fromtimestamp(now).date()
    if days:
        start_day = today - timedelta(days=days - 1)
    else:
        oldest = []
        for table in ("page_views", "download_events"):
            row = conn.execute(f"SELECT MIN(created_at) AS oldest FROM {table}").fetchone()
            if row and row["oldest"]:
                oldest.append(int(row["oldest"]))
        start_day = datetime.fromtimestamp(min(oldest)).date() if oldest else today
        days = max(1, (today - start_day).days + 1)
    previous_start_day = start_day - timedelta(days=days)
    window_start = int(datetime.combine(previous_start_day, datetime_time.min).timestamp())
    day_keys = [(start_day + timedelta(days=offset)).isoformat() for offset in range(days)]
    previous_keys = [(previous_start_day + timedelta(days=offset)).isoformat() for offset in range(days)]
    window_keys = previous_keys + day_keys
    visits = {day: set() for day in window_keys}
    downloads = {day: set() for day in window_keys}
    # Collapse per-route rows into the 30-minute session model so a chart point
    # represents a person visiting or downloading, not reloads/navigation.
    for row in conn.execute("SELECT visitor_hash,created_at FROM page_views WHERE created_at>=?", (window_start,)):
        stamp = int(row["created_at"])
        day = datetime.fromtimestamp(stamp).strftime("%Y-%m-%d")
        if day in visits:
            visits[day].add((row["visitor_hash"], stamp // ANALYTICS_SESSION_SECONDS))
    for row in conn.execute("SELECT visitor_hash,path,created_at FROM download_events WHERE created_at>=?", (window_start,)):
        stamp = int(row["created_at"])
        day = datetime.fromtimestamp(stamp).strftime("%Y-%m-%d")
        if day in downloads:
            downloads[day].add((row["visitor_hash"], row["path"], stamp // ANALYTICS_SESSION_SECONDS))
    series = [(day, len(visits[day]), len(downloads[day])) for day in day_keys]
    totals = {
        "visits": sum(len(visits[day]) for day in day_keys),
        "downloads": sum(len(downloads[day]) for day in day_keys),
    }
    previous = {
        "visits": sum(len(visits[day]) for day in previous_keys),
        "downloads": sum(len(downloads[day]) for day in previous_keys),
    }
    return totals, previous, series


def dashboard_range(value):
    for key, label, days in DASHBOARD_RANGES:
        if key == value:
            return key, label, days
    _, label, days = next(item for item in DASHBOARD_RANGES if item[0] == DASHBOARD_DEFAULT_RANGE)
    return DASHBOARD_DEFAULT_RANGE, label, days


def dashboard_delta(current, previous):
    if not previous:
        return ""
    change = (current - previous) / previous * 100
    arrow = "▲" if change >= 0 else "▼"
    return f"{arrow} {abs(change):.0f}%"


def dashboard_axis_labels(day_keys):
    if len(day_keys) <= 6:
        picks = day_keys
    else:
        step = (len(day_keys) - 1) / 5
        picks = [day_keys[round(index * step)] for index in range(6)]
    return "".join(f"<span>{datetime.strptime(day, '%Y-%m-%d').strftime('%b %d')}</span>" for day in picks)


def format_dashboard_count(value):
    return f"{int(value):,}"


BATCH_STATUS = {
    "draft": (0, 0, "Draft"),
    "testing": (1, 1, "Testing"),
    "release": (1, 0, "Release"),
}


def game_status_key(game):
    if not game["published"]:
        return "draft"
    return "testing" if game["experimental"] else "release"


def batch_game_ids(value):
    if not isinstance(value, list) or not value or len(value) > 50:
        raise ValueError("select 1-50 games")
    try:
        ids = [int(item) for item in value]
    except (TypeError, ValueError):
        raise ValueError("invalid game selection")
    if any(item <= 0 for item in ids) or len(set(ids)) != len(ids):
        raise ValueError("invalid game selection")
    return ids


def batch_status_request(data):
    target = str(data.get("status") or "")
    if target not in BATCH_STATUS:
        raise ValueError("invalid target status")
    return target, batch_game_ids(data.get("ids"))


def batch_status_preview(conn, target, ids):
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT id,title_vi,title_en,published,experimental FROM games WHERE id IN ({placeholders})", ids
    ).fetchall()
    if len(rows) != len(ids):
        raise ValueError("one or more games no longer exist")
    row_by_id = {row["id"]: row for row in rows}
    selected = [row_by_id[item] for item in ids]
    published, experimental, label = BATCH_STATUS[target]
    confirmation = f"APPLY {len(selected)} GAME{'S' if len(selected) != 1 else ''} AS {label.upper()}"
    return {
        "target": target,
        "target_label": label,
        "published": published,
        "experimental": experimental,
        "confirmation": confirmation,
        "games": [
            {"id": row["id"], "title": row["title_en"] or row["title_vi"], "current": game_status_key(row)}
            for row in selected
        ],
    }


def admin_page(lang, user, csrf, edit_id=None, return_to="/admin", range_key=DASHBOARD_DEFAULT_RANGE):
    """Product analytics dashboard plus admin operations.

    The top of the page stays focused on the two metrics that matter to an
    app-distribution site (visits and app downloads). Server monitoring is a
    collapsed secondary panel; library/account/report tools follow below.
    Play counts, unique-player and ROM-catalog analytics were intentionally
    removed.
    """
    selected_range, range_label, range_days = dashboard_range(range_key)
    with db() as conn:
        games = conn.execute("SELECT * FROM games ORDER BY updated_at DESC").fetchall()
        users = conn.execute("SELECT id,name,display_name,role,created_at FROM users ORDER BY role DESC, name COLLATE NOCASE").fetchall()
        reports = conn.execute(
            """SELECT r.*,COALESCE(NULLIF(u.display_name,''),u.name) AS reporter,g.title_vi,g.slug FROM reports r
               JOIN users u ON u.id=r.user_id JOIN games g ON g.id=r.game_id
               ORDER BY CASE r.status WHEN 'open' THEN 0 ELSE 1 END, r.updated_at DESC LIMIT 80"""
        ).fetchall()
        bug_reports = conn.execute(
            """SELECT b.*,COALESCE(NULLIF(u.display_name,''),u.name) AS reporter FROM bug_reports b
               LEFT JOIN users u ON u.id=b.user_id ORDER BY b.created_at DESC LIMIT 60"""
        ).fetchall()
        settings = site_settings(conn)
        totals, previous, series = dashboard_analytics(conn, range_days)
    visit_series = ",".join(str(visits) for _, visits, _ in series)
    download_series = ",".join(str(downloads) for _, _, downloads in series)
    chart_labels = dashboard_axis_labels([day for day, _, _ in series])
    def range_option(key, label):
        active = key == selected_range
        css = "range-option active" if active else "range-option"
        current = ' aria-current="true"' if active else ""
        return f'<a class="{css}" href="/admin?range={key}"{current}>{label}</a>'

    range_options = "".join(range_option(key, label) for key, label, _ in DASHBOARD_RANGES)

    def game_status(game):
        return {"draft": "Draft", "testing": "Testing", "release": "Release"}[game_status_key(game)]

    reported_game_ids = {item["game_id"] for item in reports}
    rows = "".join(
        f'<tr data-admin-game data-status="{game_status_key(g)}" data-reported="{str(g["id"] in reported_game_ids).lower()}">'
        f'<td><input type="checkbox" data-batch-game value="{g["id"]}" aria-label="Select {esc(game_title(g, lang))} for batch status"></td>'
        f'<td><div class="table-actions"><a href="/play/{esc(g["slug"])}">Play</a><button class="button danger" type="button" data-delete-game="{g["id"]}">Delete</button></div></td>'
        f'<td><a href="/game/{esc(g["slug"])}">{esc(game_title(g, lang))}</a></td><td>{esc(SYSTEMS[g["system"]][0])}</td>'
        f'<td>{game_status(g)}</td><td>{format_size(g["file_size"])}</td></tr>'
        for g in games
    )
    user_rows = "".join(
        f'''<tr><td>{esc(item['name'])}</td><td>{esc(item['role'])}</td><td><form class="user-display-name" data-user-id="{item['id']}"><input name="display_name" value="{esc(item['display_name'] or item['name'])}" maxlength="40" aria-label="Display name"><button class="button" type="submit">Save</button></form></td></tr>'''
        for item in users
    )
    report_rows = "".join(
        f'''<article class="admin-report" data-report-id="{item['id']}"><header><strong>{esc(item['title_vi'])}</strong><span>{esc(item['category'])}</span><time>{datetime.fromtimestamp(item['created_at']).strftime('%Y-%m-%d %H:%M')}</time></header><p>{esc(item['body'])}</p><footer><span>{esc(item['reporter'])}</span><label>Status<select data-report-status aria-label="Issue report status"><option value="open"{' selected' if item['status']=='open' else ''}>open</option><option value="resolved"{' selected' if item['status']=='resolved' else ''}>resolved</option></select></label></footer></article>'''
        for item in reports
    )
    bug_report_rows = "".join(
        f'''<article class="admin-report" data-bug-report-id="{item['id']}"><header><strong>{esc(item['game_title'] or item['emulator_system'] or 'Bug report')}</strong><span>{esc(item['platform'])}</span><time>{datetime.fromtimestamp(item['created_at']).strftime('%Y-%m-%d %H:%M')}</time></header><p>{esc(item['description'])}</p><details><summary>Sanitized diagnostics</summary><pre>{esc(item['payload'])}</pre></details><footer><span>{esc(item['reporter'] or 'anonymous')}</span><span>{esc(item['app_version'])} · {esc(item['build_id'])}</span><span>{f'<a href="{esc(item["github_issue_url"])}" rel="noopener noreferrer" target="_blank">Issue #{item["github_issue_number"]}</a>' if item['github_issue_url'] else 'No GitHub issue'}</span></footer></article>'''
        for item in bug_reports
    )
    reference_monitor = lambda metric, icon, label: f'''<article class="monitor-card reference-monitor-card" data-metric-card="{metric}">{ref_icon(icon)}<div><span>{label}</span><strong class="reference-monitor-value" data-metric-value>—</strong><small class="reference-monitor-status" data-metric-status>Loading…</small></div><i class="reference-monitor-meter" aria-hidden="true"></i></article>'''

    def metric_card(icon, label, value, delta):
        delta_html = f'<small class="metric-delta">{delta}</small>' if delta else ""
        return f'<article class="reference-metric-card">{ref_icon(icon)}<div><span>{label}</span><strong>{value}</strong>{delta_html}</div></article>'

    body = f"""<main class="page admin-page">
<section class="admin-head"><div><p class="eyebrow">ADMIN ONLY</p><h1>Dashboard</h1></div><nav class="range-selector" aria-label="Date range">{range_options}</nav></section>
<nav class="admin-task-nav" aria-label="Admin tasks"><a href="#adminOverview">{ref_icon("star")}<span>Overview</span></a><a href="#adminMonitoring">Server status</a><a href="#adminLibrary">Library</a><a href="#adminOperations">Accounts and reports</a></nav>
<section id="adminOverview" class="analytics">
<div class="stats-overview">{metric_card("globe","Total Visits",format_dashboard_count(totals['visits']),dashboard_delta(totals['visits'],previous['visits']))}{metric_card("download","App Downloads",format_dashboard_count(totals['downloads']),dashboard_delta(totals['downloads'],previous['downloads']))}</div>
<section class="reference-chart-section"><header><h2>{ref_icon("chart-no-axes-combined")}Visits &amp; downloads</h2><span>{range_label}</span></header><article class="reference-chart-wide"><header><span class="chart-legends"><i class="chart-dot visits"></i>Visits<i class="chart-dot downloads"></i>Downloads</span><b>{format_dashboard_count(totals['visits'])} <small class="chart-total-sep">/</small> {format_dashboard_count(totals['downloads'])}</b></header><canvas class="reference-line-chart" width="900" height="300" data-color="#a855f7" data-series="{visit_series}" data-color2="#22d3ee" data-series2="{download_series}" aria-label="Visits and downloads for {esc(range_label)}"></canvas><footer>{chart_labels}</footer></article></section>
</section>
<details id="adminMonitoring" class="admin-monitoring admin-list"><summary><span>{ref_icon("chart-no-axes-combined")}Server status</span><span id="monitoringUpdated" class="monitoring-reference-updated" aria-live="polite"></span><i class="details-chevron" aria-hidden="true"></i></summary><div class="monitoring-grid">{reference_monitor("cpu","cpu","CPU")}{reference_monitor("ram","memory-stick","RAM")}{reference_monitor("disk","hard-drive","Storage")}{reference_monitor("temperature","thermometer","Temperature")}{reference_monitor("power","zap","Power")}{reference_monitor("uptime","clock-3","Uptime")}{reference_monitor("app","router","Vibe Coded")}</div></details>
<section id="adminLibrary" class="admin-list"><header><h2>Library</h2><span>Select up to 50 games for a safe status change</span></header><form id="batchStatusForm" class="batch-status-form"><label>New status<select name="status"><option value="draft">Draft</option><option value="testing">Testing</option><option value="release">Release</option></select></label><button class="button" type="submit">Preview change</button><p id="batchPreview" class="muted" role="status"></p><label class="batch-confirmation" hidden>Type the exact confirmation to apply<input id="batchConfirmation" autocomplete="off" disabled></label><button id="batchApply" class="button primary" type="button" disabled>Apply previewed change</button></form><div class="table-wrap"><table><thead><tr><th>Select</th><th>Actions</th><th>Game</th><th>System</th><th>Status</th><th>Size</th></tr></thead><tbody>{rows or '<tr><td colspan="6">Empty</td></tr>'}</tbody></table></div></section>
<section id="adminOperations" class="admin-tools"><section class="admin-list"><h2>Administrators</h2><form id="adminCreateForm" class="admin-create"><label>Username (cannot change)<input name="name" minlength="3" maxlength="32" required autocomplete="username"></label><label>Display nickname<input name="display_name" minlength="2" maxlength="40" required autocomplete="nickname"></label><label>Password<input name="password" type="password" minlength="10" maxlength="200" required autocomplete="new-password" aria-describedby="adminPasswordRules"></label><p id="adminPasswordRules" class="field-help">Use 10–200 characters and at least two character types.</p><label>Confirm password<input name="confirm" type="password" minlength="10" maxlength="200" required autocomplete="new-password" aria-describedby="adminPasswordRules"></label><button class="button primary" type="submit">Create admin</button></form></section>
<section class="admin-list"><h2>Accounts</h2><div class="table-wrap"><table><thead><tr><th>Username</th><th>Role</th><th>Display nickname</th></tr></thead><tbody>{user_rows}</tbody></table></div></section>
<section class="admin-list"><h2>Issue reports</h2><div class="report-list">{report_rows or '<p class="muted">No reports.</p>'}</div></section><section class="admin-list"><h2>Bug reports</h2><div class="report-list">{bug_report_rows or '<p class="muted">No bug reports.</p>'}</div></section></section>
<section class="contact-settings admin-list"><h2>Maintainer contact</h2><form id="siteSettingsForm" class="form-grid"><label>Email<input name="maintainer_email" type="email" value="{esc(settings.get('maintainer_email'))}" maxlength="254"></label><label>Facebook URL<input name="maintainer_facebook" type="url" value="{esc(settings.get('maintainer_facebook'))}" maxlength="500" placeholder="https://facebook.com/..." ></label><label class="wide">Other social links<textarea name="maintainer_links" maxlength="4000" placeholder="Discord|https://...&#10;YouTube|https://...">{esc(settings.get('maintainer_links'))}</textarea></label><div class="form-actions"><button class="button primary" type="submit">Save contact</button></div></form></section></main>"""
    return layout("Dashboard", body, lang, user, csrf, admin=True)


def rate_allowed(ip, action, limit, window=600, subject=""):
    global RATE_LIMIT_MAX_WINDOW
    now = time.time()
    key = (auth_hash(ip), action, str(subject))
    with RATE_LIMIT_LOCK:
        if window > RATE_LIMIT_MAX_WINDOW:
            RATE_LIMIT_MAX_WINDOW = window
        entries = [stamp for stamp in RATE_LIMIT.get(key, []) if now - stamp < window]
        if len(entries) >= limit:
            RATE_LIMIT[key] = entries
            return False
        entries.append(now)
        RATE_LIMIT[key] = entries
        if len(RATE_LIMIT) > RATE_LIMIT_MAX_KEYS:
            _prune_rate_limit(now, key)
        return True


def player_content_security_policy(netplay_origin):
    """The strict CSP for the player page.

    The EmulatorJS netplay client reaches the relay over a WebSocket, and CSP
    ``connect-src`` treats ``ws:``/``wss:`` as distinct schemes from
    ``http:``/``https:``, so the WebSocket origin must be listed explicitly.
    """

    netplay_connect = ""
    if netplay_origin:
        netplay_connect = f" {netplay_origin}"
        if netplay_origin.startswith("https://"):
            netplay_connect += " " + netplay_origin.replace("https://", "wss://", 1)
        elif netplay_origin.startswith("http://"):
            netplay_connect += " " + netplay_origin.replace("http://", "ws://", 1)
    return (
        "default-src 'self' blob: data: https://cdn.emulatorjs.org; "
        "img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline' https://cdn.emulatorjs.org; "
        "script-src 'self' 'unsafe-eval' 'wasm-unsafe-eval' blob: https://cdn.emulatorjs.org; "
        f"connect-src 'self' blob: https://cdn.emulatorjs.org{netplay_connect}; "
        "worker-src 'self' blob: https://cdn.emulatorjs.org; "
        "frame-src 'self' blob:; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'self'"
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "VibeCodedEmulator/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stdout.write("%s %s\n" % (self.address_string(), fmt % args))

    def native_account_endpoint(self):
        # Some security tests exercise the renderer with a socket-free Handler
        # stub.  Treat a missing request path as a non-account endpoint rather
        # than allowing a response-header helper to raise while handling an
        # otherwise valid static 404/asset response.
        path = urlparse(getattr(self, "path", "")).path
        return path in {"/api/login", "/api/logout"} or path.startswith("/api/account/")

    def native_account_origin(self):
        if not self.native_account_endpoint():
            return ""
        origin = self.headers.get("Origin", "").strip()
        return origin if origin in NATIVE_ACCOUNT_ORIGINS else ""

    def common_headers(self, content_type, length=None, cache="no-store", csp=None, cross_origin_isolated=False):
        # The native support surface is the only cross-origin API: an allowlisted
        # app origin may read the capability and the submission receipt. Every
        # other response stays same-origin exactly as before.
        cors_origin = getattr(self, "_cors_origin", "")
        account_origin = self.native_account_origin()
        self.send_header("Content-Type", content_type)
        if length is not None:
            self.send_header("Content-Length", str(length))
        if cors_origin:
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, " + bug_report.SUPPORT_CAPABILITY_HEADER)
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Vary", "Origin")
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        # A COEP: require-corp document may only read a cross-origin response
        # that opts in, so support responses declare cross-origin explicitly.
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin" if (cors_origin or account_origin) else "same-origin")
        if cross_origin_isolated:
            self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("X-Permitted-Cross-Domain-Policies", "none")
        if COOKIE_SECURE:
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        self.send_header("Content-Security-Policy", csp or "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'self'; worker-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'")
        if account_origin:
            self.send_header("Access-Control-Allow-Origin", account_origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")
        if getattr(self, "_visitor_cookie", ""):
            self.send_header("Set-Cookie", self._visitor_cookie)

    def handle_one_request(self):
        # Body accounting is per request: one handler instance serves an entire
        # keep-alive connection, so each request boundary must reset the count.
        self._body_consumed = 0
        super().handle_one_request()

    def handle_expect_100(self):
        # RFC 9110 10.1.1: the interim `100 Continue` is emitted before the
        # request body is sent, so there is no body to drain yet and blocking in
        # rfile.read() would deadlock an Expect: 100-continue client. Suppress
        # the end_headers drain for this interim response only; every terminal
        # response (including a final error reply) still drains normally.
        self._interim_response = True
        try:
            return super().handle_expect_100()
        finally:
            self._interim_response = False

    def end_headers(self):
        # Every terminal response flushes its headers through here, including
        # the direct writers (redirect, serve_static, serve_file,
        # /download-app/source, login/logout) and send_error. Draining the
        # declared-but-unread request body at this single terminal point keeps
        # the next request on a keep-alive connection correctly framed. The
        # interim `100 Continue` (handle_expect_100) is not terminal and must
        # not drain, or the client never learns it may send the body.
        if not getattr(self, "_interim_response", False):
            self.drain_unread_body()
        super().end_headers()

    def declared_body_length(self):
        headers = getattr(self, "headers", None)
        if headers is None:
            return 0
        try:
            return max(0, int(headers.get("Content-Length", "0") or 0))
        except (TypeError, ValueError):
            return 0

    def drain_unread_body(self):
        """Consume a declared body the handler never read.

        HTTP/1.1 keep-alive parses the next request from the same connection, so
        a body left in the socket is mistaken for the next request line (a
        request desync). Every terminal response flushes through ``end_headers``,
        which drains whatever the handler left behind before the response headers
        are written; a body larger than one bounded read closes the connection
        instead of blocking forever. The interim ``100 Continue`` is the one
        exception: it is emitted before the request body and is therefore not a
        terminal response, so ``end_headers`` skips the drain for it.
        """

        if self.close_connection:
            return
        remaining = self.declared_body_length() - getattr(self, "_body_consumed", 0)
        if remaining <= 0:
            return
        chunk = min(remaining, MAX_JSON_BYTES)
        self.rfile.read(chunk)
        self._body_consumed = getattr(self, "_body_consumed", 0) + chunk
        if remaining > chunk:
            self.close_connection = True

    def send_bytes(self, status, data, content_type="application/json; charset=utf-8", cache="no-store", csp=None, cross_origin_isolated=False):
        self.send_response(status)
        self.common_headers(content_type, len(data), cache, csp, cross_origin_isolated)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def send_json(self, payload, status=200):
        self.send_bytes(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        if not self.native_account_endpoint():
            self.send_bytes(404, b"not found\n", "text/plain; charset=utf-8")
            return
        if not self.native_account_origin():
            self.send_bytes(403, b"origin not allowed\n", "text/plain; charset=utf-8")
            return
        self.send_response(204)
        self.common_headers("text/plain; charset=utf-8", 0)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-CSRF-Token")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def send_html(self, content, status=200, player=False):
        csp = None
        if player:
            csp = player_content_security_policy(NETPLAY_ORIGIN)
        self.send_bytes(status, content.encode("utf-8"), "text/html; charset=utf-8", csp=csp, cross_origin_isolated=player)

    def read_json(self, maximum=MAX_JSON_BYTES):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0 or length > maximum:
            raise ValueError("invalid request size")
        raw = self.rfile.read(length)
        self._body_consumed = getattr(self, "_body_consumed", 0) + len(raw)
        return json.loads(raw.decode("utf-8"))

    def discard_request_body(self, maximum=MAX_JSON_BYTES):
        """Consume a small declared body when a request is rejected early.

        An unread body would otherwise be parsed as the next request line on a
        keep-alive connection, corrupting the following request.
        """

        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return
        raw = self.rfile.read(min(length, maximum))
        self._body_consumed = getattr(self, "_body_consumed", 0) + len(raw)

    def read_optional_json(self, maximum=MAX_JSON_BYTES):
        """Read a small JSON body when present, otherwise return ``{}``.

        HTTP/1.1 keep-alive requires every request body to be consumed before
        the next request on the same connection, even for endpoints that ignore
        the payload; an unread body corrupts the next request line.
        """

        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        if length > maximum:
            raise ValueError("invalid request size")
        raw = self.rfile.read(length)
        self._body_consumed = getattr(self, "_body_consumed", 0) + len(raw)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}

    def cookie_jar(self):
        return cookies.SimpleCookie(self.headers.get("Cookie", ""))

    def visitor_hash(self):
        raw = self.cookie_jar().get("an3_visitor")
        token = raw.value if raw else ""
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,80}", token):
            token = secrets.token_urlsafe(24)
            flags = f"Path=/; HttpOnly; SameSite=Lax; Max-Age={VISITOR_TTL}" + ("; Secure" if COOKIE_SECURE else "")
            self._visitor_cookie = f"an3_visitor={token}; {flags}"
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def track_visit(self, path, user=None, game_id=None):
        visitor = self.visitor_hash()
        now = int(time.time())
        user_id = user["id"] if user else None
        with db() as conn:
            recent = conn.execute("SELECT 1 FROM page_views WHERE visitor_hash=? AND created_at>? LIMIT 1", (visitor, now - ANALYTICS_SESSION_SECONDS)).fetchone()
            if not recent:
                conn.execute("INSERT INTO page_views(visitor_hash,user_id,path,created_at) VALUES(?,?,?,?)", (visitor, user_id, path, now))
            if game_id:
                played = conn.execute("SELECT 1 FROM play_events WHERE visitor_hash=? AND game_id=? AND created_at>?", (visitor, game_id, now - ANALYTICS_SESSION_SECONDS)).fetchone()
                if not played:
                    conn.execute("INSERT INTO play_events(visitor_hash,user_id,game_id,created_at) VALUES(?,?,?,?)", (visitor, user_id, game_id, now))

    def track_download(self, path, user=None):
        """Record one app-installer download per visitor and session.

        Analytics is best-effort: a tracking failure must never interrupt or
        fail the actual download response.
        """
        try:
            visitor = self.visitor_hash()
            now = int(time.time())
            user_id = user["id"] if user else None
            with db() as conn:
                recent = conn.execute(
                    "SELECT 1 FROM download_events WHERE visitor_hash=? AND path=? AND created_at>?",
                    (visitor, path, now - ANALYTICS_SESSION_SECONDS),
                ).fetchone()
                if not recent:
                    conn.execute(
                        "INSERT INTO download_events(visitor_hash,user_id,path,created_at) VALUES(?,?,?,?)",
                        (visitor, user_id, path, now),
                    )
        except Exception:
            return

    def check_contribution_limit(self, user, game_id, kind):
        now = int(time.time())
        if kind == "comment":
            limit, window, cooldown = 4, 3600, 30
            table = "comments"
        else:
            limit, window, cooldown = 3, 86400, 90
            table = "reports"
        with db() as conn:
            recent = conn.execute(
                f"SELECT created_at FROM {table} WHERE user_id=? ORDER BY created_at DESC LIMIT 1", (user["id"],)
            ).fetchone()
            total = conn.execute(
                f"SELECT COUNT(*) AS count FROM {table} WHERE user_id=? AND created_at>?", (user["id"], now - window)
            ).fetchone()["count"]
        if recent and now - recent["created_at"] < cooldown:
            raise RateLimited("Please wait before sending again")
        if total >= limit:
            raise RateLimited("You reached today's send limit")
        if not rate_allowed(self.client_address[0], f"{kind}-ip", limit, window):
            raise RateLimited("Too many requests from this network")
        if not rate_allowed(self.client_address[0], f"{kind}-user", limit, window, user["id"]):
            raise RateLimited("You reached the send limit")

    def current_user(self):
        token = self.cookie_jar().get("an3_session")
        if not token:
            return None, ""
        token_hash = hashlib.sha256(token.value.encode()).hexdigest()
        with db() as conn:
            row = conn.execute(
                """SELECT u.*,s.csrf,s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id
                   WHERE s.token_hash=? AND s.expires_at>?""", (token_hash, int(time.time()))
            ).fetchone()
        return (row, row["csrf"]) if row else (None, "")

    def require_user(self, admin=False, csrf=True):
        user, token = self.current_user()
        if not user:
            self.send_json({"error": "login required"}, 401)
            return None
        if admin and user["role"] != "admin":
            self.send_json({"error": "admin required"}, 403)
            return None
        if csrf and not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), token):
            self.send_json({"error": "invalid csrf token"}, 403)
            return None
        return user

    def set_session(self, user_id):
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        expires = int(time.time()) + SESSION_TTL
        with db() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at<?", (int(time.time()),))
            conn.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES(?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user_id, csrf, expires))
        same_site = "None" if self.native_account_origin() and COOKIE_SECURE else "Lax"
        flags = f"Path=/; HttpOnly; SameSite={same_site}; Max-Age={SESSION_TTL}" + ("; Secure" if COOKIE_SECURE else "")
        self.send_header("Set-Cookie", f"an3_session={token}; {flags}")

    def clear_session(self):
        jar = self.cookie_jar()
        token = jar.get("an3_session")
        if token:
            with db() as conn:
                conn.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.value.encode()).hexdigest(),))
        same_site = "None" if self.native_account_origin() and COOKIE_SECURE else "Lax"
        flags = f"Path=/; HttpOnly; SameSite={same_site}; Max-Age=0" + ("; Secure" if COOKIE_SECURE else "")
        self.send_header("Set-Cookie", f"an3_session=; {flags}")

    def find_game(self, slug, include_draft=True):
        with db() as conn:
            return conn.execute("SELECT * FROM games WHERE slug=?", (slug,)).fetchone()

    def redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def serve_static(self, root, relative, cache="public,max-age=86400", sandbox=False):
        try:
            path = safe_data_path(root, unquote(relative))
            if os.path.isdir(path):
                path = safe_data_path(root, os.path.join(relative, "index.html"))
            if not os.path.isfile(path):
                raise ValueError("not found")
            content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
            size = os.path.getsize(path)
            self.send_response(200)
            csp = "sandbox allow-scripts allow-pointer-lock allow-forms; default-src 'self' data: blob:; img-src 'self' data: blob:; media-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; connect-src 'self' blob:; object-src 'none'" if sandbox else None
            # Dedicated workers loaded by an isolated player must opt into the
            # same embedder policy or the browser rejects them before execution.
            renderer_worker = os.path.abspath(path) == os.path.join(os.path.abspath(STATIC_DIR), "renderer-worker.js")
            self.common_headers(content_type, size, cache, csp, cross_origin_isolated=renderer_worker)
            if sandbox:
                self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.end_headers()
            if self.command != "HEAD":
                with open(path, "rb") as handle:
                    shutil.copyfileobj(handle, self.wfile, 1024 * 1024)
        except Exception:
            self.send_bytes(404, b"not found\n", "text/plain; charset=utf-8")

    def serve_service_worker(self):
        """Render the cache namespace after the static content hash is known."""
        try:
            path = safe_data_path(STATIC_DIR, "service-worker.js")
            with open(path, "rb") as handle:
                payload = handle.read().replace(b"__ASSET_VERSION__", ASSET_VERSION.encode("ascii"))
            self.send_bytes(200, payload, "application/javascript; charset=utf-8", "no-cache")
        except Exception:
            self.send_bytes(404, b"not found\n", "text/plain; charset=utf-8")

    def serve_file(self, path, filename, attachment=False, cache="private,max-age=3600"):
        size = os.path.getsize(path)
        start, end = 0, size - 1
        status = 200
        range_header = self.headers.get("Range", "")
        if range_header.startswith("bytes="):
            match = re.match(r"bytes=(\d*)-(\d*)", range_header)
            if match:
                if match.group(1):
                    start = int(match.group(1))
                if match.group(2):
                    end = min(int(match.group(2)), end)
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = 206
        length = end - start + 1
        self.send_response(status)
        self.common_headers(mimetypes.guess_type(filename)[0] or "application/octet-stream", length, cache)
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        disposition = "attachment" if attachment else "inline"
        self.send_header("Content-Disposition", f"{disposition}; filename*=UTF-8''{quote(filename)}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def multiplayer_unavailable(self):
        self.send_json({"error": "not found"}, 404)

    def multiplayer_create_room(self):
        if not MULTIPLAYER_ENABLED:
            return self.multiplayer_unavailable()
        data = self.read_json()
        try:
            signature = room_signature_from(data)
        except netcode.NetcodeError as exc:
            return self.send_json({"error": str(exc)}, 400)
        device = str(data.get("deviceId") or "")[:64]
        try:
            room, token = ROOMS.create_room(
                signature, device, signaling_hint=NETPLAY_ORIGIN, client_key=self.client_address[0])
        except netcode.RateLimitedError as exc:
            return self.send_json({"error": str(exc)}, 429)
        self.send_json({
            "code": room.code,
            "token": token,
            "role": "host",
            "relay": NETPLAY_ORIGIN,
            "expiresInSeconds": int(room.ttl_seconds),
            "signature": {"system": signature.system, "core": signature.core, "romHash": signature.rom_hash},
        }, 201)

    def multiplayer_join_room(self):
        if not MULTIPLAYER_ENABLED:
            return self.multiplayer_unavailable()
        data = self.read_json()
        try:
            signature = room_signature_from(data)
        except netcode.NetcodeError as exc:
            return self.send_json({"error": str(exc)}, 400)
        code = str(data.get("code") or "")
        device = str(data.get("deviceId") or "")[:64]
        try:
            room, token = ROOMS.join_room(code, signature, device, client_key=self.client_address[0])
        except netcode.RateLimitedError as exc:
            return self.send_json({"error": str(exc)}, 429)
        except netcode.IncompatibleError as exc:
            return self.send_json({"error": str(exc), "reason": "incompatible"}, 409)
        except netcode.ExpiredError as exc:
            return self.send_json({"error": str(exc), "reason": "expired"}, 410)
        except netcode.NetcodeError as exc:
            return self.send_json({"error": str(exc)}, 404)
        self.send_json({
            "code": room.code,
            "token": token,
            "role": "guest",
            "relay": NETPLAY_ORIGIN,
            "expiresInSeconds": int(room.ttl_seconds),
        })

    def multiplayer_leave_room(self):
        if not MULTIPLAYER_ENABLED:
            return self.multiplayer_unavailable()
        data = self.read_json()
        code = str(data.get("code") or "")
        token = str(data.get("token") or "")
        try:
            role = ROOMS.authenticate(code, token)
        except netcode.NetcodeError:
            return self.send_json({"ok": True})
        ROOMS.leave(code, role)
        self.send_json({"ok": True})

    def multiplayer_reconnect(self):
        """Resume a room membership with the previous member token.

        Background/resume and reload recovery: the client persists its token,
        presents it here, and receives a freshly rotated token for the same
        role. A non-member or an expired/closed room is refused.
        """

        if not MULTIPLAYER_ENABLED:
            return self.multiplayer_unavailable()
        data = self.read_json()
        code = str(data.get("code") or "")
        token = str(data.get("token") or "")
        try:
            room, role, fresh = ROOMS.resume(code, token)
        except netcode.ExpiredError as exc:
            return self.send_json({"error": str(exc), "reason": "expired"}, 404)
        except netcode.NetcodeError as exc:
            return self.send_json({"error": str(exc)}, 403)
        self.send_json({
            "code": room.code,
            "token": fresh,
            "role": role.value,
            "relay": NETPLAY_ORIGIN,
            "expiresInSeconds": int(room.ttl_seconds),
        })

    def multiplayer_publish_input(self):
        """Store one member's latest coalesced input snapshot.

        The live input path is the EmulatorJS relay (RG-086); this is the
        resume/checkpoint anchor so a peer that reconnects can read the other
        peer's newest frame instead of replaying relay history.
        """

        if not MULTIPLAYER_ENABLED:
            return self.multiplayer_unavailable()
        data = self.read_json()
        code = str(data.get("code") or "")
        token = str(data.get("token") or "")
        frame = {key: value for key, value in data.items() if key not in {"code", "token"}}
        try:
            room, role, applied = ROOMS.publish_input(code, token, frame)
        except netcode.ExpiredError:
            return self.send_json({"error": "room is no longer available"}, 404)
        except netcode.NotPairedError:
            return self.send_json({"error": "not a room member"}, 403)
        except netcode.NetcodeError as exc:
            return self.send_json({"error": str(exc)}, 400)
        self.send_json({
            "applied": applied is not None,
            "role": role.value,
            "sequence": applied.sequence if applied is not None else (
                room.latest_input(role).sequence if room.latest_input(role) is not None else 0),
        })

    def multiplayer_member_state(self):
        """Return the caller's own and the peer's latest input snapshot."""

        if not MULTIPLAYER_ENABLED:
            return self.multiplayer_unavailable()
        query = parse_qs(urlparse(self.path).query)
        code = query.get("code", [""])[0]
        token = query.get("token", [""])[0]
        try:
            room, role = ROOMS.member_state(code, token)
        except netcode.ExpiredError:
            return self.send_json({"error": "room is no longer available"}, 404)
        except netcode.NotPairedError:
            return self.send_json({"error": "not a room member"}, 403)
        except netcode.NetcodeError as exc:
            return self.send_json({"error": str(exc)}, 404)
        peer_role = netcode.RoomRole.GUEST if role is netcode.RoomRole.HOST else netcode.RoomRole.HOST
        own = room.latest_input(role)
        peer = room.latest_input(peer_role)
        remaining = max(0, int(room.ttl_seconds - (room.clock() - room.created_at)))
        self.send_json({
            "state": "full" if room.full else "waiting",
            "role": role.value,
            "players": 2 if room.full else 1,
            "expiresInSeconds": remaining,
            "self": own.to_wire() if own is not None else None,
            "peer": peer.to_wire() if peer is not None else None,
        })

    def multiplayer_room_status(self):
        if not MULTIPLAYER_ENABLED:
            return self.multiplayer_unavailable()
        query = parse_qs(urlparse(self.path).query)
        code = query.get("code", [""])[0]
        token = query.get("token", [""])[0]
        try:
            role = ROOMS.authenticate(code, token)
        except netcode.NetcodeError as exc:
            return self.send_json({"error": str(exc)}, 404)
        room = ROOMS.rooms.get(netcode.normalize_code(code))
        if room is None:
            return self.send_json({"error": "room not found"}, 404)
        remaining = max(0, int(room.ttl_seconds - (room.clock() - room.created_at)))
        self.send_json({
            "state": "full" if room.full else "waiting",
            "role": role.value,
            "players": 2 if room.full else 1,
            "expiresInSeconds": remaining,
        })

    def multiplayer_qr(self):
        """Serve a same-origin join QR for a game's room as an SVG."""

        if not MULTIPLAYER_ENABLED:
            return self.multiplayer_unavailable()
        query = parse_qs(urlparse(self.path).query)
        slug = query.get("slug", [""])[0]
        code = netcode.normalize_code(query.get("code", [""])[0])
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", slug) or not re.fullmatch(r"[A-Z0-9]{1,16}", code):
            return self.send_json({"error": "invalid room link"}, 400)
        scheme = self.headers.get("X-Forwarded-Proto", "https" if COOKIE_SECURE else "http")
        if scheme not in {"http", "https"}:
            scheme = "http"
        host = (self.headers.get("Host", "") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9.\-]{1,253}(:\d{1,5})?", host):
            return self.send_json({"error": "invalid host"}, 400)
        try:
            svg = controller_qr_svg(f"{scheme}://{host}/play/{slug}?room={code}")
        except ValueError:
            return self.send_json({"error": "invalid payload"}, 400)
        self.send_bytes(200, svg.encode("utf-8"), "image/svg+xml; charset=utf-8", cache="no-store")

    def sync_unavailable(self):
        self.send_json({"error": "not found"}, 404)

    def sync_lan_denied(self):
        """Refuse a LAN sync operation while the global LAN Sync switch is OFF."""

        self.send_json({"error": "LAN sync is turned off", "reason": "lan-sync-disabled"}, 409)

    def sync_lan_enabled_for_request(self):
        with db() as conn:
            return sync_lan_status(conn, self.visitor_hash())

    def sync_settings_payload(self, mode, updated_at, content, lan_enabled):
        return {
            "mode": mode.value,
            "modes": sync_mode_catalog(),
            "content": content,
            "contentOptions": [
                {"id": "save", "label": "Save files"},
                {"id": "state", "label": "Save states"},
                {"id": "library", "label": "Game library"},
                {"id": "rom", "label": "ROM files", "warning": "ROM libraries may use significant storage and network bandwidth."},
            ],
            "driveConfigured": GOOGLE_DRIVE_ENABLED,
            "lanEnabled": mode.lan_enabled,
            "driveEnabled": mode.drive_enabled,
            "lanSyncEnabled": bool(lan_enabled),
            "lanSyncAvailable": SYNC_ENABLED,
            "googleSync": {
                "enabled": False,
                "available": GOOGLE_DRIVE_ENABLED,
                "status": "coming-later",
                "message": "Google Drive sync is not available yet.",
            },
            "updatedAt": updated_at,
        }

    def sync_get_settings(self):
        if not SYNC_ENABLED:
            return self.sync_unavailable()
        device = self.visitor_hash()
        with db() as conn:
            mode, updated_at, content = sync_mode_status(conn, device)
            lan_enabled = sync_lan_status(conn, device)
        self.send_json(self.sync_settings_payload(mode, updated_at, content, lan_enabled))

    def sync_set_settings(self):
        if not SYNC_ENABLED:
            return self.sync_unavailable()
        SYNC_LIMITER.check(self.client_address[0])
        data = self.read_json()
        toggles_lan = "lanSyncEnabled" in data
        requested = str(data.get("mode") or "").strip().lower()
        device = self.visitor_hash()
        with db() as conn:
            configured, _, existing = sync_mode_status(conn, device)
            existing_lan = sync_lan_status(conn, device)
        if not requested:
            if not toggles_lan:
                return self.send_json({"error": "invalid sync mode"}, 400)
            mode = configured
        elif requested not in {mode.value for mode in sync_engine.SyncMode} and requested not in {"automatic", "recommended", "local"}:
            return self.send_json({"error": "invalid sync mode"}, 400)
        else:
            mode = sync_engine.parse_sync_mode(requested)
        if mode.requires_drive and not GOOGLE_DRIVE_ENABLED:
            return self.send_json({"error": "google drive sync is not configured", "reason": "drive-unavailable"}, 409)
        lan_enabled = bool(data.get("lanSyncEnabled")) if toggles_lan else existing_lan
        now = int(time.time())
        with db() as conn:
            content = parse_sync_content(data.get("content")) if "content" in data else existing
            conn.execute(
                "INSERT INTO sync_settings(device_key,mode,updated_at,content,lan_enabled) VALUES(?,?,?,?,?) "
                "ON CONFLICT(device_key) DO UPDATE SET mode=excluded.mode, updated_at=excluded.updated_at, "
                "content=excluded.content, lan_enabled=excluded.lan_enabled",
                (device, mode.value, now, json.dumps(content, sort_keys=True), 1 if lan_enabled else 0),
            )
        self.send_json({"ok": True, **self.sync_settings_payload(mode, now, content, lan_enabled)})

    def sync_plan(self):
        """Plan one pass through the pure sync engine.

        The caller owns hashing and byte transfer; this returns the decision for
        each logical file (direction + reason) plus conflict counts.
        """

        if not SYNC_ENABLED:
            return self.sync_unavailable()
        SYNC_LIMITER.check(self.client_address[0])
        data = self.read_json()
        device = self.visitor_hash()
        with db() as conn:
            configured, _, content = sync_mode_status(conn, device)
            lan_enabled = sync_lan_status(conn, device)
        mode = sync_engine.parse_sync_mode(data.get("mode", configured.value))
        if mode.lan_enabled and not lan_enabled:
            return self.sync_lan_denied()
        if mode.requires_drive and not GOOGLE_DRIVE_ENABLED:
            return self.send_json({"error": "google drive sync is not configured", "reason": "drive-unavailable"}, 409)
        try:
            kind = sync_engine.ItemKind(str(data.get("kind") or "save"))
        except ValueError:
            return self.send_json({"error": "invalid item kind"}, 400)
        records = data.get("records")
        if not isinstance(records, list) or len(records) > SYNC_MANIFEST_LIMIT:
            return self.send_json({"error": "invalid manifest"}, 400)
        try:
            entries = sync_engine.entries_from_records(records, kind=kind)
        except sync_engine.SyncError as error:
            return self.send_json({"error": str(error)}, 400)
        plan = sync_engine.build_plan(mode, entries, same_lan=bool(data.get("sameLan")),
                                      drive_available=GOOGLE_DRIVE_ENABLED)
        self.send_json({
            "mode": plan.mode.value,
            "content": content,
            "transport": plan.transport.value if plan.transport else None,
            "clean": plan.clean,
            "summary": sync_engine.summarize(plan),
            "transfers": [
                {
                    "key": transfer.entry.key,
                    "kind": transfer.entry.kind.value,
                    "direction": transfer.direction.value,
                    "reason": transfer.reason,
                    "copyKey": transfer.copy_key,
                }
                for transfer in plan.transfers
            ],
        })

    def sync_resolve(self):
        """Turn one conflict into a concrete action (keep local/remote/both)."""

        if not SYNC_ENABLED:
            return self.sync_unavailable()
        if not self.sync_lan_enabled_for_request():
            return self.sync_lan_denied()
        SYNC_LIMITER.check(self.client_address[0])
        data = self.read_json()
        resolution = str(data.get("resolution") or "").strip().lower()
        try:
            kind = sync_engine.ItemKind(str(data.get("kind") or "save"))
        except ValueError:
            return self.send_json({"error": "invalid item kind"}, 400)
        key = str(data.get("key") or "").strip()
        if not key or len(key) > 256:
            return self.send_json({"error": "invalid entry key"}, 400)
        entry = sync_engine.SyncEntry(kind=kind, key=key)
        conflict = sync_engine.TransferPlan(entry, sync_engine.Direction.CONFLICT, reason="both-changed")
        try:
            resolved = sync_engine.resolve_conflict(
                conflict, resolution,
                local_hash=str(data.get("localHash") or ""),
                remote_hash=str(data.get("remoteHash") or ""),
            )
        except sync_engine.SyncError as error:
            return self.send_json({"error": str(error)}, 400)
        self.send_json({
            "key": key,
            "direction": resolved.direction.value,
            "reason": resolved.reason,
            "copyKey": resolved.copy_key,
        })

    def lan_peer_announce(self):
        if not SYNC_ENABLED:
            return self.sync_unavailable()
        if not self.sync_lan_enabled_for_request():
            return self.sync_lan_denied()
        SYNC_LIMITER.check(self.client_address[0])
        data = self.read_json()
        device = str(data.get("deviceId") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", device):
            return self.send_json({"error": "invalid device id"}, 400)
        name = str(data.get("name") or "").strip()[:48]
        try:
            port = int(data.get("port") or 0)
        except (TypeError, ValueError):
            port = 0
        if port < 0 or port > 65535:
            return self.send_json({"error": "invalid port"}, 400)
        request_ip = self.client_address[0]
        with LAN_PEERS_LOCK:
            LAN_PEERS[device] = {"name": name, "ip": request_ip, "port": port, "seen": time.monotonic()}
        self.send_json({"peers": lan_peer_snapshot(request_ip)})

    def lan_peer_list(self):
        if not SYNC_ENABLED:
            return self.sync_unavailable()
        if not self.sync_lan_enabled_for_request():
            return self.sync_lan_denied()
        request_ip = self.client_address[0]
        self.send_json({"peers": lan_peer_snapshot(request_ip)})

    def sync_lan_publish(self):
        """Accept eligible save/state blobs from a LAN device for peers to pull."""

        if not SYNC_ENABLED:
            return self.sync_unavailable()
        if not self.sync_lan_enabled_for_request():
            return self.sync_lan_denied()
        SYNC_LIMITER.check(self.client_address[0])
        data = self.read_json(maximum=LAN_SAVE_SET_MAX_JSON_BYTES)
        device = str(data.get("deviceId") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", device):
            return self.send_json({"error": "invalid device id"}, 400)
        try:
            kind = sync_engine.ItemKind(str(data.get("kind") or ""))
        except ValueError:
            return self.send_json({"error": "invalid item kind"}, 400)
        if not sync_engine.is_sync_eligible(kind):
            return self.send_json({"error": "kind is not sync-eligible"}, 400)
        items = data.get("items")
        if not isinstance(items, list) or not items or len(items) > LAN_BLOB_MAX_ITEMS:
            return self.send_json({"error": "invalid item list"}, 400)
        now = time.monotonic()
        request_ip = self.client_address[0]
        lan_blob_reap(now)
        prepared = []
        seen_item_keys = set()
        save_set = data.get("set") if kind is sync_engine.ItemKind.SAVE else None
        replace_manifest_hash = str(data.get("replaceManifestHash") or "").strip().lower()
        if replace_manifest_hash and not LAN_SAVE_HASH_RE.fullmatch(replace_manifest_hash):
            return self.send_json({"error": "invalid replacement manifest hash"}, 400)
        validated_set = None
        member_by_key = {}
        if save_set is not None:
            try:
                validated_set = _sync_validate_save_set(save_set)
            except ValueError as error:
                return self.send_json({"error": str(error)}, 400)
            if len(items) != validated_set["memberCount"]:
                return self.send_json({"error": "save-set item count does not match its manifest"}, 400)
            member_by_key = {member["key"]: member for member in validated_set["members"]}
        for item in items:
            if not isinstance(item, dict):
                return self.send_json({"error": "invalid item"}, 400)
            key = str(item.get("key") or "")
            if not re.fullmatch(r"[A-Za-z0-9._:@/\-]{1,256}", key):
                return self.send_json({"error": "invalid item key"}, 400)
            if key in seen_item_keys:
                return self.send_json({"error": "duplicate item key"}, 400)
            seen_item_keys.add(key)
            content_hash = str(item.get("contentHash") or "").strip().lower()
            if not re.fullmatch(r"[a-f0-9]{16,64}", content_hash):
                return self.send_json({"error": "invalid content hash"}, 400)
            member = None
            if save_set is not None:
                member = member_by_key.get(key)
                if member is None:
                    return self.send_json({"error": "unknown save-set member"}, 400)
                if (str(item.get("memberId") or "") != member["memberId"]
                        or str(item.get("path") or "") != member["path"]
                        or content_hash != member["contentHash"]
                        or item.get("size") != member["size"]):
                    return self.send_json({"error": "save-set member metadata does not match its manifest"}, 400)
            try:
                blob = base64.b64decode(str(item.get("data") or ""), validate=True)
            except (ValueError, binascii.Error):
                return self.send_json({"error": "invalid item data"}, 400)
            if len(blob) > LAN_BLOB_MAX_BYTES:
                return self.send_json({"error": "item too large"}, 413)
            if member is not None and len(blob) != member["size"]:
                return self.send_json({"error": "save-set member size does not match its manifest"}, 400)
            digest = hashlib.sha256(blob).hexdigest()
            hash_matches = digest == content_hash if save_set is not None else digest[: len(content_hash)] == content_hash
            if not hash_matches:
                return self.send_json({"error": "content hash does not match the data"}, 400)
            prepared.append({
                "key": key,
                "hash": content_hash,
                "device": device,
                "ip": request_ip,
                "data": blob,
                "updated": now,
                "set": validated_set,
                "setId": validated_set["setId"] if validated_set else None,
            })
        if validated_set and sum(len(item["data"]) for item in prepared) != validated_set["totalSize"]:
            return self.send_json({"error": "save-set payload size does not match its manifest"}, 400)

        conflict = None
        with LAN_BLOBS_LOCK:
            set_id = validated_set["setId"] if validated_set else None
            existing_set = [record for (blob_kind, _), record in LAN_BLOBS.items()
                            if blob_kind == kind.value and set_id and record.get("setId") == set_id]
            existing_hashes = {record.get("set", {}).get("manifestHash") for record in existing_set}
            replace_allowed = bool(existing_hashes) and existing_hashes == {replace_manifest_hash}
            if validated_set and existing_hashes and not replace_allowed and existing_hashes != {validated_set["manifestHash"]}:
                return self.send_json({"error": "a different save set already owns this identity"}, 409)
            for entry in prepared:
                existing = LAN_BLOBS.get((kind.value, entry["key"]))
                if existing is not None and (existing.get("device") != device or existing.get("ip") != request_ip):
                    if not (replace_allowed and existing.get("setId") == set_id):
                        conflict = entry["key"]
                        break
            if conflict is None:
                if validated_set:
                    for blob_key, record in list(LAN_BLOBS.items()):
                        if blob_key[0] == kind.value and record.get("setId") == set_id:
                            LAN_BLOBS.pop(blob_key, None)
                for record in prepared:
                    LAN_BLOBS[(kind.value, record["key"])] = record
        if conflict is not None:
            return self.send_json({
                "error": "item key is owned by another device",
                "reason": "lan-blob-owner-conflict",
                "key": conflict,
            }, 409)
        stored = [{"key": record["key"], "contentHash": record["hash"], "size": len(record["data"])} for record in prepared]
        response = {"ok": True, "stored": len(stored), "items": stored}
        if validated_set:
            response["setId"] = validated_set["setId"]
            response["manifestHash"] = validated_set["manifestHash"]
        self.send_json(response)

    def sync_lan_manifest(self):
        if not SYNC_ENABLED:
            return self.sync_unavailable()
        if not self.sync_lan_enabled_for_request():
            return self.sync_lan_denied()
        query = parse_qs(urlparse(self.path).query)
        try:
            kind = sync_engine.ItemKind(query.get("kind", ["save"])[0])
        except ValueError:
            return self.send_json({"error": "invalid item kind"}, 400)
        now = time.monotonic()
        lan_blob_reap(now)
        items = []
        save_sets = {}
        with LAN_BLOBS_LOCK:
            for (blob_kind, key), record in LAN_BLOBS.items():
                if blob_kind != kind.value:
                    continue
                item = {
                    "key": key,
                    "contentHash": record["hash"],
                    "size": len(record["data"]),
                    "deviceId": record["device"],
                    "ageSeconds": int(now - record["updated"]),
                }
                items.append(item)
                if kind is sync_engine.ItemKind.SAVE and record.get("setId") and record.get("set"):
                    group = save_sets.setdefault(record["setId"], {"set": record["set"], "records": []})
                    group["records"].append(record)
        items.sort(key=lambda item: item["key"])
        sets = []
        for set_id, group in sorted(save_sets.items()):
            declared = dict(group["set"])
            actual_by_key = {record["key"]: record for record in group["records"]}
            members = []
            for member in declared.get("members", []):
                entry = dict(member)
                record = actual_by_key.get(member["key"])
                if record:
                    entry["deviceId"] = record["device"]
                members.append(entry)
            declared["members"] = members
            declared["deviceId"] = next(iter(actual_by_key.values()))["device"] if actual_by_key else ""
            sets.append(declared)
        self.send_json({"kind": kind.value, "items": items, "sets": sets})

    def sync_lan_blob(self):
        if not SYNC_ENABLED:
            return self.sync_unavailable()
        if not self.sync_lan_enabled_for_request():
            return self.sync_lan_denied()
        query = parse_qs(urlparse(self.path).query)
        try:
            kind = sync_engine.ItemKind(query.get("kind", ["save"])[0])
        except ValueError:
            return self.send_json({"error": "invalid item kind"}, 400)
        key = query.get("key", [""])[0]
        content_hash = query.get("hash", [""])[0].strip().lower()
        if not re.fullmatch(r"[A-Za-z0-9._:@/\-]{1,256}", key):
            return self.send_json({"error": "invalid item key"}, 400)
        if not re.fullmatch(r"[a-f0-9]{16,64}", content_hash):
            return self.send_json({"error": "invalid content hash"}, 400)
        lan_blob_reap()
        with LAN_BLOBS_LOCK:
            record = LAN_BLOBS.get((kind.value, key))
            payload = record["data"] if record and record["hash"] == content_hash else None
        if payload is None:
            return self.send_bytes(404, b"not found\n", "text/plain; charset=utf-8")
        self.send_bytes(200, payload, "application/octet-stream", cache="no-store")

    def controller_unavailable(self):
        self.send_json({"error": "not found"}, 404)

    def controller_create_session(self):
        if not CONTROLLER_ENABLED:
            return self.controller_unavailable()
        # Consume the body (keep-alive safety) and honour a bounded lifetime so a
        # native game session can outlive the 2-minute web pairing window.
        data = self.read_optional_json()
        ttl_seconds = CONTROLLER_TTL_SECONDS
        try:
            requested = int(data.get("ttlSeconds"))
        except (TypeError, ValueError):
            requested = 0
        if requested > 0:
            ttl_seconds = max(60, min(3600, requested))
        system = str(data.get("system") or "auto").strip().lower()
        if system not in CONTROLLER_SYSTEMS:
            system = "auto"
        name = clean_controller_name(data.get("name"), "Vibe Coded Emulator")
        CONTROLLER_LIMITER.check(self.client_address[0])
        controller_reap()
        with CONTROLLER_LOCK:
            code = netcode.generate_pairing_code(6)
            while code in CONTROLLERS:
                code = netcode.generate_pairing_code(6)
            session = netcode.ControllerSession(
                code=code,
                host_device_id="host",
                created_at=time.monotonic(),
                ttl_seconds=ttl_seconds,
            )
            host_token, host_digest = netcode.new_session_token()
            CONTROLLERS[code] = {
                "session": session,
                "host": host_digest,
                "ip": self.client_address[0],
                "name": name,
                "system": system,
                "started": time.monotonic(),
            }
        self.send_json({
            "code": code,
            "hostToken": host_token,
            "ttlSeconds": ttl_seconds,
            "system": system,
            "name": name,
            "joinPath": f"/controller/join?code={code}",
        }, 201)

    def controller_pair(self):
        if not CONTROLLER_ENABLED:
            return self.controller_unavailable()
        data = self.read_json()
        code = netcode.normalize_code(str(data.get("code") or ""))
        try:
            CONTROLLER_LIMITER.check(self.client_address[0])
            controller_reap()
            with CONTROLLER_LOCK:
                record = CONTROLLERS.get(code)
            if record is None:
                raise netcode.NetcodeError("pairing code not found")
            token = record["session"].pair(str(data.get("deviceId") or "phone")[:64])
        except netcode.RateLimitedError as exc:
            return self.send_json({"error": str(exc)}, 429)
        except netcode.ExpiredError as exc:
            return self.send_json({"error": str(exc), "reason": "expired"}, 410)
        except netcode.NetcodeError as exc:
            return self.send_json({"error": str(exc)}, 404)
        self.send_json({"code": code, "token": token, "role": "phone"})

    def controller_submit_state(self):
        if not CONTROLLER_ENABLED:
            return self.controller_unavailable()
        data = self.read_json()
        code = netcode.normalize_code(str(data.get("code") or ""))
        token = str(data.get("token") or "")
        frame = data.get("frame") or data
        with CONTROLLER_LOCK:
            record = CONTROLLERS.get(code)
        if record is None:
            return self.send_json({"error": "session not found"}, 404)
        try:
            applied = record["session"].accept_state(frame, token=token)
        except netcode.NotPairedError as exc:
            return self.send_json({"error": str(exc)}, 403)
        except netcode.NetcodeError as exc:
            return self.send_json({"error": str(exc)}, 400)
        self.send_json({"ok": True, "applied": applied is not None})

    def controller_host_state(self):
        if not CONTROLLER_ENABLED:
            return self.controller_unavailable()
        query = parse_qs(urlparse(self.path).query)
        code = netcode.normalize_code(query.get("code", [""])[0])
        host_token = query.get("hostToken", [""])[0]
        controller_reap()
        with CONTROLLER_LOCK:
            record = CONTROLLERS.get(code)
        if record is None:
            return self.send_json({"error": "session not found"}, 404)
        if not host_token or not hmac.compare_digest(record["host"], netcode.token_digest(host_token)):
            return self.send_json({"error": "host token rejected"}, 403)
        session = record["session"]
        latest = session.latest_state()
        self.send_json({
            "paired": session.paired,
            "needsResync": session.needs_resync(),
            "lastSequence": session.last_sequence(),
            "ackSequence": session.ack_sequence(),
            "inputActive": session.input_active(),
            "system": record.get("system") or "auto",
            "name": record.get("name") or "",
            "expiresInSeconds": max(0, int(session.ttl_seconds - (session.clock() - session.created_at))),
            "utilities": session.pending_utilities(),
            "state": latest.to_wire() if latest else None,
        })

    def controller_ack(self):
        """Host reports the newest frame it has pushed into the emulator."""

        if not CONTROLLER_ENABLED:
            return self.controller_unavailable()
        data = self.read_json()
        code = netcode.normalize_code(str(data.get("code") or ""))
        host_token = str(data.get("hostToken") or "")
        with CONTROLLER_LOCK:
            record = CONTROLLERS.get(code)
        if record is None:
            return self.send_json({"error": "session not found"}, 404)
        if not host_token or not hmac.compare_digest(record["host"], netcode.token_digest(host_token)):
            return self.send_json({"error": "host token rejected"}, 403)
        session = record["session"]
        applied = session.ack(data.get("sequence"), data.get("utilitySequence"))
        # The host tells us which system is running so the phone can pick the
        # matching pad layout without the user choosing one.
        system = str(data.get("system") or "").strip().lower()
        if system in CONTROLLER_SYSTEMS:
            with CONTROLLER_LOCK:
                if code in CONTROLLERS:
                    CONTROLLERS[code]["system"] = system
        self.send_json({"ok": True, "ackSequence": applied, "inputActive": session.input_active()})

    def controller_link_status(self):
        """Phone-facing status: is the transport paired and is input applied?

        The phone holds only its own guest token, so it cannot read the host
        state. This endpoint tells it the truth without exposing host details.
        """

        if not CONTROLLER_ENABLED:
            return self.controller_unavailable()
        query = parse_qs(urlparse(self.path).query)
        code = netcode.normalize_code(query.get("code", [""])[0])
        token = query.get("token", [""])[0]
        controller_reap()
        with CONTROLLER_LOCK:
            record = CONTROLLERS.get(code)
        if record is None:
            return self.send_json({"error": "session not found"}, 404)
        session = record["session"]
        if not session.authenticate(token):
            return self.send_json({"error": "session token rejected"}, 403)
        self.send_json({
            "paired": session.paired,
            "inputActive": session.input_active(),
            "lastSequence": session.last_sequence(),
            "ackSequence": session.ack_sequence(),
            "system": record.get("system") or "auto",
            "name": record.get("name") or "",
            "expiresInSeconds": max(0, int(session.ttl_seconds - (session.clock() - session.created_at))),
            # Track B1: echo the phone's own capture time for the frame the host
            # acknowledged, so the phone can compute controller RTT entirely on
            # its own monotonic clock. Never compared against a host clock.
            "echoCaptureMs": session.acked_capture_ms(),
        })

    def controller_nearby_hosts(self):
        """Active controller hosts on the caller's own subnet.

        This is the LAN rendezvous the phone uses to offer "nearby hosts"
        instead of forcing a code; addresses are never disclosed, only the code
        the user would otherwise type and a short label.
        """

        if not CONTROLLER_ENABLED:
            return self.controller_unavailable()
        request_ip = self.client_address[0]
        controller_reap()
        hosts = []
        with CONTROLLER_LOCK:
            for code, record in CONTROLLERS.items():
                if not sync_same_subnet(request_ip, record.get("ip", "")):
                    continue
                session = record["session"]
                hosts.append({
                    "code": code,
                    "name": record.get("name") or "Vibe Coded Emulator",
                    "system": record.get("system") or "auto",
                    "paired": session.paired,
                })
        hosts.sort(key=lambda item: (item["paired"], item["name"]))
        self.send_json({"hosts": hosts})

    def diagnostics_snapshot(self):
        """Technical snapshot for Advanced Diagnostics.

        Deliberately excludes tokens, addresses and any per-device identity.
        """

        if not (CONTROLLER_ENABLED or SYNC_ENABLED or MULTIPLAYER_ENABLED):
            return self.send_json({"error": "not found"}, 404)
        controller_reap()
        lan_blob_reap()
        with CONTROLLER_LOCK:
            sessions = len(CONTROLLERS)
            paired = sum(1 for record in CONTROLLERS.values() if record["session"].paired)
        with LAN_PEERS_LOCK:
            peers = len(LAN_PEERS)
        with LAN_BLOBS_LOCK:
            blobs = len(LAN_BLOBS)
        self.send_json({
            "environment": ENVIRONMENT,
            "assetVersion": ASSET_VERSION,
            "buildId": RUNTIME_BUILD_ID,
            "controller": {
                "enabled": CONTROLLER_ENABLED,
                "sessions": sessions,
                "pairedSessions": paired,
                "defaultTtlSeconds": CONTROLLER_TTL_SECONDS,
                "systems": sorted(CONTROLLER_SYSTEMS),
                "ackRequiredForInput": True,
            },
            "sync": {
                "enabled": SYNC_ENABLED,
                "driveConfigured": GOOGLE_DRIVE_ENABLED,
                "defaultContent": dict(DEFAULT_SYNC_CONTENT),
                "peerTtlSeconds": LAN_PEER_TTL_SECONDS,
                "peerCount": peers,
                "blobCount": blobs,
                "blobTtlSeconds": LAN_BLOB_TTL_SECONDS,
                "manifestLimit": SYNC_MANIFEST_LIMIT,
                "transports": [transport.value for transport in sync_engine.Transport],
            },
            "multiplayer": {
                "enabled": MULTIPLAYER_ENABLED,
                "relay": NETPLAY_ORIGIN,
                "transport": "relay",
                "roomTtlSeconds": 900,
                "capability": MULTIPLAYER_CORE_CAPABILITY,
            },
            "updatedAt": int(time.time()),
        })

    def support_origin(self):
        """Return the allowlisted app origin for this request, or an empty string.

        The allowlist is exact-match and fail-closed: an empty configuration, an
        absent ``Origin``, or any unlisted origin yields no cross-origin grant.
        """

        if not SUPPORT_ALLOWED_ORIGINS:
            return ""
        origin = (self.headers.get("Origin", "") or "").strip().rstrip("/")
        return origin if origin in SUPPORT_ALLOWED_ORIGINS else ""

    def support_capability_issue(self):
        """Issue a short-lived opaque capability to an allowlisted app origin.

        No account, cookie, secret, or device identity is involved. The token is
        high-entropy and server-side only; the response also tells the client
        whether the anonymous support path is available at all.
        """

        if not BUG_REPORT_ENABLED:
            return self.send_json({"error": "not found"}, 404)
        origin = self.support_origin()
        if not origin:
            return self.send_json({"error": "origin not allowed"}, 403)
        if not rate_allowed(
            self.client_address[0], "support-capability-ip", SUPPORT_CAPABILITY_RATE_LIMIT, BUG_REPORT_RATE_WINDOW
        ):
            raise RateLimited("Too many capability requests from this network")
        token, digest = bug_report.new_support_capability()
        now = int(time.time())
        expires = now + bug_report.CAPABILITY_TTL_SECONDS
        with db() as conn:
            conn.execute("DELETE FROM support_capabilities WHERE expires_at<?", (now,))
            conn.execute(
                "INSERT INTO support_capabilities(token_hash,origin,created_at,expires_at,uses,max_uses) VALUES(?,?,?,?,?,?)",
                (digest, origin, now, expires, 0, bug_report.CAPABILITY_MAX_USES),
            )
        self.send_json(
            {
                "ok": True,
                "capability": token,
                "expiresAt": expires,
                "maxUses": bug_report.CAPABILITY_MAX_USES,
                "reportPath": "/api/bug-reports",
                "header": bug_report.SUPPORT_CAPABILITY_HEADER,
            },
            201,
        )

    def support_capability_consume(self):
        """Consume one use of a capability header; ``None`` when absent/invalid.

        Expiry and the finite use count are enforced atomically, so a captured
        token cannot be replayed after it lapses or is spent. The token is also
        scoped to the allowlisted origin it was issued to: a capability obtained
        through one app origin must not be replayable from another origin (or
        from a non-browser client that simply forges an ``Origin``), so the
        issuing origin is re-checked against the live allowlist on every use.
        """

        token = (self.headers.get(bug_report.SUPPORT_CAPABILITY_HEADER, "") or "").strip()
        if not token:
            return None
        request_origin = self.support_origin()
        if not request_origin:
            return None
        digest = bug_report.support_capability_digest(token)
        now = int(time.time())
        with db() as conn:
            row = conn.execute(
                "SELECT token_hash,origin,expires_at,uses,max_uses FROM support_capabilities WHERE token_hash=?",
                (digest,),
            ).fetchone()
            if not row or row["expires_at"] < now or row["uses"] >= row["max_uses"]:
                return None
            if request_origin != row["origin"]:
                return None
            updated = conn.execute(
                "UPDATE support_capabilities SET uses=uses+1 WHERE token_hash=? AND expires_at>=? AND uses<max_uses",
                (digest, now),
            )
            if updated.rowcount != 1:
                return None
        return dict(row)

    def ingest_bug_report(self, data, user_id):
        """Sanitize, persist, then optionally file a GitHub issue.

        The sanitized report is persisted before any GitHub call, so a failed
        or misconfigured integration can never lose the admin report. Returns
        the JSON receipt the caller sends.
        """

        report = bug_report.build_report(
            data, build_id=RUNTIME_BUILD_ID, app_version=ASSET_VERSION, channel=ENVIRONMENT
        )
        bug_report.assert_no_forbidden(report)
        fingerprint = bug_report.issue_fingerprint(report)
        now = int(time.time())
        with db() as conn:
            if user_id is not None:
                recent = conn.execute(
                    "SELECT created_at FROM bug_reports WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
                    (user_id,),
                ).fetchone()
                if recent and now - recent["created_at"] < BUG_REPORT_COOLDOWN:
                    raise RateLimited("Please wait before sending another report")
            duplicate = conn.execute(
                "SELECT github_issue_number,github_issue_url FROM bug_reports WHERE fingerprint=? AND github_issue_url!='' ORDER BY created_at DESC LIMIT 1",
                (fingerprint,),
            ).fetchone()
            cur = conn.execute(
                """INSERT INTO bug_reports(user_id,fingerprint,report_schema_version,app_version,build_id,platform,
                   emulator_system,core_name,game_title,game_identifier,description,payload,status,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    user_id, fingerprint, report["reportSchemaVersion"], report["appVersion"], report["buildId"],
                    report["platform"], report["emulatorSystem"], report["coreName"], report["gameTitle"],
                    report["gameIdentifier"], report["description"],
                    json.dumps(report, ensure_ascii=False, sort_keys=True), "open", now,
                ),
            )
            report_id = cur.lastrowid
        issue = {"attempted": False, "created": False, "reason": "duplicate" if duplicate else "not configured"}
        try:
            if duplicate:
                with db() as conn:
                    conn.execute(
                        "UPDATE bug_reports SET github_issue_number=?,github_issue_url=? WHERE id=?",
                        (duplicate["github_issue_number"], duplicate["github_issue_url"], report_id),
                    )
                issue = {"attempted": True, "created": False, "duplicate": True,
                         "number": duplicate["github_issue_number"], "url": duplicate["github_issue_url"]}
            elif GITHUB_ISSUES_TOKEN and GITHUB_ISSUES_REPOSITORY:
                issue = bug_report.create_github_issue(
                    report, token=GITHUB_ISSUES_TOKEN, repository=GITHUB_ISSUES_REPOSITORY, labels=GITHUB_ISSUE_LABELS
                )
                if issue.get("created"):
                    with db() as conn:
                        conn.execute(
                            "UPDATE bug_reports SET github_issue_number=?,github_issue_url=? WHERE id=?",
                            (issue.get("number"), issue.get("url") or "", report_id),
                        )
        except Exception:
            issue = {"attempted": True, "created": False, "reason": "issue creation failed"}
        return {"ok": True, "id": report_id, "fingerprint": fingerprint, "issue": issue}

    def bug_report_submit(self):
        """Rate-limited bug report ingestion for an account or a capability.

        An authenticated user submits with their cookie and CSRF token exactly
        as before. The packaged native app, which has neither, submits with the
        server-issued opaque capability it obtained from an allowlisted origin.
        """

        if not BUG_REPORT_ENABLED:
            return self.send_json({"error": "not found"}, 404)
        user, csrf_token = self.current_user()
        if user:
            if not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), csrf_token):
                self.discard_request_body(BUG_REPORT_MAX_BYTES)
                return self.send_json({"error": "invalid csrf token"}, 403)
        elif self.support_capability_consume() is None:
            # No session and no valid capability: never a silent drop.
            self.discard_request_body(BUG_REPORT_MAX_BYTES)
            return self.send_json({"error": "login required"}, 401)
        if not rate_allowed(self.client_address[0], "bug-report-ip", BUG_REPORT_RATE_LIMIT, BUG_REPORT_RATE_WINDOW):
            raise RateLimited("Too many bug reports from this network")
        if user and not rate_allowed(
            self.client_address[0], "bug-report-user", BUG_REPORT_USER_LIMIT, BUG_REPORT_RATE_WINDOW, user["id"]
        ):
            raise RateLimited("You reached the bug report limit")
        data = self.read_json(BUG_REPORT_MAX_BYTES)
        self.send_json(self.ingest_bug_report(data, user["id"] if user else None), 201)

    def controller_disconnect(self):
        """Release a pairing only for a holder of the host or guest token.

        The pairing code is public (shown on the host page, encoded in the QR
        and discoverable to same-subnet phones), so it must not be a bearer
        credential here: an unauthenticated caller could otherwise tear down
        any live session and its pending one-shot utilities. An unknown code is
        still idempotent, but an existing session is only cleared when the
        request proves possession of the host token or the paired guest token.
        """

        if not CONTROLLER_ENABLED:
            return self.controller_unavailable()
        data = self.read_json()
        code = netcode.normalize_code(str(data.get("code") or ""))
        host_token = str(data.get("hostToken") or "")
        guest_token = str(data.get("token") or "")
        with CONTROLLER_LOCK:
            record = CONTROLLERS.get(code)
        if record is None:
            return self.send_json({"ok": True})
        session = record["session"]
        host_ok = bool(host_token) and hmac.compare_digest(record["host"], netcode.token_digest(host_token))
        if not (host_ok or session.authenticate(guest_token)):
            return self.send_json({"error": "session token rejected"}, 403)
        session.disconnect()
        self.send_json({"ok": True})

    def controller_qr(self):
        """Serve the pairing QR as a self-contained SVG (strict-CSP safe)."""

        if not CONTROLLER_ENABLED:
            return self.controller_unavailable()
        query = parse_qs(urlparse(self.path).query)
        code = netcode.normalize_code(query.get("code", [""])[0])
        if not code:
            return self.send_json({"error": "missing pairing code"}, 400)
        scheme = self.headers.get("X-Forwarded-Proto", "https" if COOKIE_SECURE else "http")
        if scheme not in {"http", "https"}:
            scheme = "http"
        join_url = controller_join_url(scheme, self.headers.get("Host", ""), code)
        if not join_url:
            return self.send_json({"error": "invalid host"}, 400)
        try:
            svg = controller_qr_svg(join_url)
        except ValueError:
            return self.send_json({"error": "invalid payload"}, 400)
        self.send_bytes(200, svg.encode("utf-8"), "image/svg+xml; charset=utf-8", cache="no-store")

    def request_origin(self):
        """Best-effort public origin (scheme://host) for install instructions.

        Derived from the request so no production domain is hardcoded in the
        source or shipped assets. Returns an empty string when the Host header
        is missing or not a plain host[:port]."""
        scheme = self.headers.get("X-Forwarded-Proto", "https" if COOKIE_SECURE else "http")
        if scheme not in {"http", "https"}:
            scheme = "http"
        host = (self.headers.get("Host", "") or "").strip()
        if not host or not re.fullmatch(r"[A-Za-z0-9.\-]+(?::\d{1,5})?", host):
            return ""
        return f"{scheme}://{host}"

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        lang = language(self)
        if path == SUPPORT_CAPABILITY_PATH:
            self._cors_origin = self.support_origin()
            try:
                self.support_capability_issue()
            except RateLimited as exc:
                self.send_json({"error": str(exc)}, 429)
            except Exception:
                self.send_json({"error": "Request could not be processed"}, 400)
            return
        # The dedicated offline app has been consolidated into ``/offline``.
        # Keep explicit redirects so existing shortcuts and cached bookmarks
        # land on the supported surface without reviving a second player.
        #
        # This is deliberately a tiny retirement worker rather than the old
        # offline-app implementation. Browsers which had that old PWA open
        # will fetch it as an update, unregister the obsolete scope, and then
        # navigate back to the supported offline surface. It neither reads nor
        # clears the user's IndexedDB, ROMs, or save data.
        if path == "/offline-app-service-worker.js":
            retired_worker = b'''self.addEventListener("install", event => event.waitUntil(self.skipWaiting()));
self.addEventListener("activate", event => event.waitUntil((async () => {
  const clients = await self.clients.matchAll({type:"window", includeUncontrolled:true});
  await self.registration.unregister();
  await Promise.all(clients.map(client => client.navigate("/offline")));
})()));
'''
            self.send_bytes(200, retired_worker, "application/javascript; charset=utf-8", "no-cache")
            return
        if path in {"/offline-app", "/offline-app/"}:
            suffix = f"?{parsed.query}" if parsed.query else ""
            self.redirect(f"/offline{suffix}")
            return
        if path.startswith("/offline-app-core-preload/"):
            system = path.rsplit("/", 1)[1]
            self.redirect(f"/core-preload/{quote(system)}")
            return
        if path == "/download-app/source":
            # This source bundle is staging-only and never contains runtime
            # data, databases, credentials, or server ROMs.
            if ENVIRONMENT not in {"staging", "development"}:
                self.send_bytes(404, b"not found\n", "text/plain; charset=utf-8")
                return
            try:
                bundle = native_offline_source_bundle()
            except FileNotFoundError:
                self.send_bytes(404, b"native source unavailable\n", "text/plain; charset=utf-8")
                return
            self.send_response(200)
            self.common_headers("application/zip", len(bundle), "no-store")
            self.send_header("Content-Disposition", 'attachment; filename="an3-offline-native-staging-source.zip"')
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(bundle)
            return
        if path == "/download-app/artifacts.json":
            # Public release metadata (filenames, sizes, SHA-256, status) that
            # both the download page and the Linux installer scripts rely on.
            # It carries no secrets, so it is served in every release
            # environment, including production.
            if ENVIRONMENT not in PUBLIC_NATIVE_RELEASE_ENVIRONMENTS:
                self.send_bytes(404, b"not found\n", "text/plain; charset=utf-8")
                return
            self.send_json(native_artifact_manifest())
            return
        if path.startswith("/download-app/release/"):
            if ENVIRONMENT not in PUBLIC_NATIVE_RELEASE_ENVIRONMENTS:
                self.send_bytes(404, b"not found\n", "text/plain; charset=utf-8")
                return
            filename = unquote(path.rsplit("/", 1)[1])
            release = published_native_release(filename, query.get("sha256", [None])[0])
            if not release:
                self.send_bytes(404, b"release not found\n", "text/plain; charset=utf-8")
                return
            content_type = mimetypes.guess_type(release)[0] or "application/octet-stream"
            size = os.path.getsize(release)
            if self.command != "HEAD":
                self.track_download("/download-app/release", None)
            self.send_response(200)
            self.common_headers(content_type, size, "no-store")
            self.send_header("Content-Disposition", f'attachment; filename="{os.path.basename(release)}"')
            self.end_headers()
            if self.command != "HEAD":
                with open(release, "rb") as handle:
                    shutil.copyfileobj(handle, self.wfile, length=1024 * 1024)
            return
        # Production is download-first and intentionally carries no public
        # server-ROM catalog. The offline page remains available for a visitor's
        # own device-local files, but every legacy public library path is gone.
        if ENVIRONMENT == "production" and (path == "/games" or path == "/api/library-version" or path.startswith(PRODUCTION_ROM_LIBRARY_PREFIXES) or path.startswith("/api/games/")):
            self.send_bytes(404, b"not found\n", "text/plain; charset=utf-8")
            return
        # Public files are requested in bursts while a game starts.  A logged
        # in visitor does not need a SQLite session lookup for each CSS, core,
        # cover, or ROM byte range; dynamic pages continue to resolve the
        # account exactly as before.
        public_resource = (
            path == "/service-worker.js"
            or path == "/health"
            or path.startswith(("/emulatorjs/", "/static/", "/cover/", "/screenshot/", "/download/", "/game-file/", "/custom/"))
        )
        user, csrf = (None, "") if public_resource else self.current_user()
        if path == "/":
            self.track_visit("/download-app", user)
            origin = f"{self.request_origin()}"
            self.send_html(download_app_page(lang, user, csrf, origin))
        elif path == "/games":
            self.track_visit("/games", user)
            self.send_html(home_page(lang, user, csrf))
        elif path == "/api/library-version":
            with db() as conn:
                version = library_fingerprint(conn)
            self.send_json({"version": version})
        elif path == "/login":
            self.send_html(auth_page("login", lang, user, csrf, next_path=parse_qs(parsed.query).get("next", ["/"])[0]))
        elif path == "/register":
            self.send_html(auth_page("register", lang, user, csrf, next_path=parse_qs(parsed.query).get("next", ["/"])[0]))
        elif path == "/account":
            if not user:
                self.redirect("/login?next=%2Faccount")
            else:
                self.send_html(account_page(lang, user, csrf))
        elif path == "/offline":
            self.track_visit("/offline", user)
            self.send_html(offline_page(lang, user, csrf))
        elif path == "/multiplayer":
            if not MULTIPLAYER_ENABLED:
                self.send_html(status_page(404, lang, user, csrf), 404)
            else:
                self.track_visit("/multiplayer", user)
                self.send_html(multiplayer_page(lang, user, csrf, parse_qs(parsed.query).get("slug", [""])[0]))
        elif path == "/download-app":
            self.track_visit("/download-app", user)
            origin = f"{self.request_origin()}"
            self.send_html(download_app_page(lang, user, csrf, origin))
        elif path.startswith("/core-preload/"):
            system = path.rsplit("/", 1)[1]
            self.send_html(core_preload_page(system, lang), 200 if system in SYSTEMS and system != "html5" else 404, player=True)
        elif path.startswith("/game/"):
            game = self.find_game(path.split("/", 2)[2])
            if game:
                self.track_visit("/game", user)
            self.send_html(game_page(game, lang, user, csrf) if game else status_page(404, lang, user, csrf), 200 if game else 404)
        elif path.startswith("/play/"):
            game = self.find_game(path.split("/", 2)[2])
            if game:
                self.track_visit("/play", user, game["id"])
            self.send_html(player_page(game, lang, user, csrf) if game else status_page(404, lang, user, csrf), 200 if game else 404, player=bool(game))
        elif path == "/admin" or path.startswith("/admin/game/"):
            if not user:
                self.redirect("/login")
            elif user["role"] != "admin":
                self.send_html(status_page(403, lang, user, csrf), 403)
            else:
                edit_id = int(path.rsplit("/", 1)[1]) if path.startswith("/admin/game/") and path.rsplit("/", 1)[1].isdigit() else None
                self.send_html(admin_page(lang, user, csrf, edit_id, parse_qs(parsed.query).get("next", ["/admin"])[0], parse_qs(parsed.query).get("range", [DASHBOARD_DEFAULT_RANGE])[0]))
        elif path == "/service-worker.js":
            self.serve_service_worker()
        elif path.startswith("/emulatorjs/"):
            # Data paths are versioned only when a core needs a repaired
            # binary. They resolve to the same checked server cache while
            # allowing browsers to retain their old offline core downloads.
            match = re.fullmatch(r"/emulatorjs/(stable|latest)/data(?:-v[1-9][0-9]*)?/(.+)", path)
            if not match:
                self.send_bytes(404, b"not found\n", "text/plain; charset=utf-8")
            else:
                try:
                    asset = cached_emulator_asset(match.group(1), match.group(2))
                    self.serve_file(asset, os.path.basename(asset), cache="public,max-age=604800,immutable")
                except ValueError:
                    self.send_bytes(404, b"not found\n", "text/plain; charset=utf-8")
                except Exception:
                    self.send_bytes(502, b"emulator asset unavailable\n", "text/plain; charset=utf-8")
        elif path.startswith("/static/v/"):
            match = re.fullmatch(r"/static/v/([a-f0-9]{12})/(offline\.js|player-ui\.js|player-runtime\.js|renderer-worker\.js|nds-touch\.js|lan-peer\.js|sync-transfer\.js|player\.js|site\.css)", path)
            if not match or match.group(1) != ASSET_VERSION:
                self.send_bytes(404, b"not found\n", "text/plain; charset=utf-8")
            else:
                self.serve_static(STATIC_DIR, match.group(2), "public,max-age=31536000,immutable")
        elif path.startswith("/static/"):
            requested_asset = query.get("v", [""])[0]
            static_cache = "public,max-age=31536000,immutable" if requested_asset == ASSET_VERSION else "public,max-age=86400"
            self.serve_static(STATIC_DIR, path[8:], static_cache)
        elif path in INSTALL_SCRIPTS:
            self.serve_file(
                os.path.join(INSTALL_SCRIPTS_DIR, INSTALL_SCRIPTS[path]),
                INSTALL_SCRIPTS[path],
                attachment=True,
                cache="public,max-age=300",
            )
        elif path.startswith("/cover/"):
            game_id = path.rsplit("/", 1)[1]
            with db() as conn:
                game = conn.execute("SELECT cover_path FROM games WHERE id=?", (game_id,)).fetchone()
            if game and game["cover_path"]:
                self.serve_static(COVER_DIR, game["cover_path"], "public,max-age=3600")
            else:
                self.serve_static(STATIC_DIR, "default-cover.webp")
        elif path.startswith("/screenshot/"):
            screenshot_id = path.rsplit("/", 1)[1]
            with db() as conn:
                screenshot = conn.execute("SELECT s.file_path FROM game_screenshots s WHERE s.id=?", (screenshot_id,)).fetchone()
            if screenshot:
                self.serve_static(SCREENSHOT_DIR, screenshot["file_path"], "public,max-age=3600")
            else:
                self.send_bytes(404, b"screenshot not found\n", "text/plain; charset=utf-8")
        elif path.startswith("/download/") or path.startswith("/game-file/"):
            slug = path.split("/", 3)[2]
            game = self.find_game(slug)
            if not game or not game["rom_path"]:
                self.send_bytes(404, b"game file not found\n", "text/plain; charset=utf-8")
            else:
                try:
                    rom = safe_data_path(ROM_DIR, game["rom_path"])
                    rom_name = game["rom_name"]
                    # melonDS can unpack the original ZIP itself. Keeping NDS
                    # compressed cuts the first network transfer substantially
                    # (for example 46 MB instead of a 128 MB extracted ROM).
                    if path.startswith("/game-file/") and game["system"] != "nds":
                        rom, rom_name = prepared_browser_rom(game)
                    self.serve_file(rom, rom_name, path.startswith("/download/"))
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception:
                    self.send_bytes(404, b"game file not found\n", "text/plain; charset=utf-8")
        elif path.startswith("/custom/"):
            parts = path.strip("/").split("/", 2)
            game_id = parts[1] if len(parts) > 1 else ""
            relative = parts[2] if len(parts) > 2 else ""
            with db() as conn:
                custom_game = conn.execute("SELECT id FROM games WHERE id=? AND system='html5'", (game_id,)).fetchone()
            if not custom_game:
                self.send_bytes(404, b"not found\n", "text/plain; charset=utf-8")
            else:
                self.serve_static(os.path.join(CUSTOM_DIR, game_id), relative, "no-store", sandbox=True)
        elif path == "/api/admin/system-metrics":
            if self.require_user(admin=True, csrf=False):
                self.send_json(system_metrics())
        elif path == "/health":
            self.send_json({"ok": True, "environment": ENVIRONMENT, "asset_version": ASSET_VERSION, "release_id": native_release_identity(), "time": int(time.time())})
        elif path == "/api/account/session":
            account, _ = self.current_user()
            if not account:
                self.send_json({"authenticated": False})
            else:
                self.send_json({
                    "authenticated": True,
                    "userId": int(account["id"]),
                    "name": account["display_name"] or account["name"],
                    "csrf": csrf,
                })
        elif path == "/api/multiplayer/room":
            self.multiplayer_room_status()
        elif path == "/api/multiplayer/state":
            self.multiplayer_member_state()
        elif path == "/api/multiplayer/qr.svg":
            self.multiplayer_qr()
        elif path == "/api/controller/state":
            self.controller_host_state()
        elif path == "/api/controller/link":
            self.controller_link_status()
        elif path == "/api/controller/hosts":
            self.controller_nearby_hosts()
        elif path == "/api/controller/qr.svg":
            self.controller_qr()
        elif path == "/api/diagnostics":
            self.diagnostics_snapshot()
        elif path == "/api/sync/settings":
            self.sync_get_settings()
        elif path == "/api/sync/lan/peers":
            self.lan_peer_list()
        elif path == "/api/sync/lan/manifest":
            self.sync_lan_manifest()
        elif path == "/api/sync/lan/blob":
            self.sync_lan_blob()
        elif path == "/sync":
            if not SYNC_ENABLED:
                self.send_html(status_page(404, lang, user, csrf), 404)
            else:
                self.track_visit("/sync", user)
                self.send_html(sync_page(lang, user, csrf))
        elif path == "/licenses":
            self.send_html(licenses_page(lang, user, csrf))
        elif path == "/licenses/gpl-3.0.txt":
            license_path = os.path.join(APP_DIR, "LICENSE")
            if not os.path.isfile(license_path):
                self.send_bytes(404, b"license not found\n", "text/plain; charset=utf-8")
            else:
                with open(license_path, "rb") as handle:
                    self.send_bytes(200, handle.read(), "text/plain; charset=utf-8")
        elif path == "/controller":
            if not CONTROLLER_ENABLED:
                self.send_html(status_page(404, lang, user, csrf), 404)
            else:
                self.track_visit("/controller", user)
                self.send_html(controller_host_page(lang, user, csrf))
        elif path == "/controller/join":
            if not CONTROLLER_ENABLED:
                self.send_html(status_page(404, lang, user, csrf), 404)
            else:
                self.send_html(controller_join_page(lang, user, csrf, parse_qs(parsed.query).get("code", [""])[0]))
        elif path == "/diagnostics":
            if not (CONTROLLER_ENABLED or SYNC_ENABLED or MULTIPLAYER_ENABLED):
                self.send_html(status_page(404, lang, user, csrf), 404)
            else:
                self.track_visit("/diagnostics", user)
                self.send_html(diagnostics_page(lang, user, csrf))
        elif path == "/bug-report":
            if not BUG_REPORT_ENABLED:
                self.send_html(status_page(404, lang, user, csrf), 404)
            elif not user:
                self.redirect("/login?next=%2Fbug-report")
            else:
                self.track_visit("/bug-report", user)
                self.send_html(bug_report_page(lang, user, csrf))
        else:
            if path.startswith("/api/") or path.startswith("/admin/api/"):
                self.send_json({"error": "not found"}, 404)
            else:
                self.send_html(status_page(404, lang, user, csrf), 404)

    do_HEAD = do_GET

    def do_OPTIONS(self):
        """CORS preflight for the allowlisted native support endpoints only.

        The response is empty and carries no credentials; it exists so the
        packaged app's ``application/json`` POST is not blocked by the browser.
        """

        path = urlparse(self.path).path
        support_path = path in SUPPORT_PATHS
        account_path = self.native_account_endpoint()
        if not support_path and not account_path:
            return self.send_json({"error": "not found"}, 404)
        if support_path:
            origin = self.support_origin()
            if not origin:
                return self.send_json({"error": "origin not allowed"}, 403)
            self._cors_origin = origin
        elif not self.native_account_origin():
            return self.send_json({"error": "origin not allowed"}, 403)
        self.send_response(204)
        self.common_headers("text/plain; charset=utf-8", 0, cache="no-store")
        if account_path:
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-CSRF-Token")
            self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        lang = language(self)
        try:
            if ENVIRONMENT == "production" and path.startswith("/api/games/"):
                self.send_json({"error": "not found"}, 404)
                return
            if path == "/api/register":
                if not rate_allowed(self.client_address[0], "register", 5, 3600):
                    raise PermissionError("too many attempts")
                data = self.read_json()
                name = clean_name(data.get("name"))
                display = clean_display_name(data.get("display_name") or name)
                password = str(data.get("password") or "")
                validate_password(password, str(data.get("confirm") or ""), lang)
                redirect = safe_next_path(data.get("next"), "/")
                with db() as conn:
                    try:
                        cur = conn.execute("INSERT INTO users(name,display_name,password_hash,role,created_at) VALUES(?,?,?,?,?)", (name, display, password_hash(password), "user", int(time.time())))
                    except sqlite3.IntegrityError:
                        raise ValueError(tr(lang, "Tên này đã được sử dụng", "This username is already in use"))
                payload = json.dumps({"ok": True, "redirect": redirect}).encode()
                self.send_response(201)
                self.set_session(cur.lastrowid)
                self.common_headers("application/json; charset=utf-8", len(payload))
                self.end_headers()
                self.wfile.write(payload)
            elif path == "/api/login":
                if not rate_allowed(self.client_address[0], "login", 10, 900):
                    raise RateLimited("too many attempts")
                data = self.read_json()
                password = str(data.get("password") or "")
                with db() as conn:
                    user = conn.execute("SELECT * FROM users WHERE name=?", (str(data.get("name") or "").strip(),)).fetchone()
                if not user or not password_ok(password, user["password_hash"]):
                    raise PermissionError(tr(lang, "Sai tên hoặc mật khẩu", "Incorrect username or password"))
                upgrade = password_needs_upgrade(user["password_hash"])
                requested = safe_next_path(data.get("next"), "")
                redirect = requested or ("/admin" if user["role"] == "admin" else "/")
                payload = json.dumps({"ok": True, "redirect": redirect}).encode()
                self.send_response(200)
                self.set_session(user["id"])
                self.common_headers("application/json; charset=utf-8", len(payload))
                self.end_headers()
                self.wfile.write(payload)
                if upgrade:
                    threading.Thread(target=upgrade_password_hash, args=(user["id"], password), daemon=True).start()
            elif path == "/api/account/peer-proof":
                user = self.require_user(csrf=False)
                if not user: return
                if not AUTH_PEPPER:
                    self.send_json({"error": "native peer account proof is not configured"}, 503)
                    return
                data = self.read_json()
                self.send_json({"proof": make_peer_proof(user["id"], data.get("challenge")), "expiresInSeconds": PEER_PROOF_TTL_SECONDS})
            elif path == "/api/account/peer-proof/verify":
                user = self.require_user(csrf=False)
                if not user: return
                if not AUTH_PEPPER:
                    self.send_json({"error": "native peer account proof is not configured"}, 503)
                    return
                data = self.read_json()
                challenge = str(data.get("challenge") or "")
                proof = str(data.get("proof") or "")
                if not PEER_PROOF_CHALLENGE_RE.fullmatch(challenge):
                    raise ValueError("invalid peer challenge")
                self.send_json({"sameAccount": verify_peer_proof(user["id"], challenge, proof)})
            elif path == "/api/logout":
                if not self.require_user(): return
                payload = b'{"ok":true}'
                self.send_response(200)
                self.clear_session()
                self.common_headers("application/json; charset=utf-8", len(payload))
                self.end_headers(); self.wfile.write(payload)
            elif re.fullmatch(r"/api/games/\d+/rating", path):
                user = self.require_user()
                if not user: return
                if not rate_allowed(self.client_address[0], "rating", 60, 600): raise PermissionError("too many requests")
                game_id = int(path.split("/")[3]); value = int(self.read_json().get("value", 0))
                if value not in range(1, 6): raise ValueError("rating must be 1-5")
                with db() as conn:
                    conn.execute("INSERT INTO ratings(user_id,game_id,value,updated_at) VALUES(?,?,?,?) ON CONFLICT(user_id,game_id) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (user["id"], game_id, value, int(time.time())))
                    avg, count = rating_summary(conn, game_id)
                self.send_json({"ok": True, "average": avg, "count": count})
            elif re.fullmatch(r"/api/games/\d+/comments", path):
                user = self.require_user()
                if not user: return
                data = self.read_json()
                if str(data.get("website") or "").strip(): raise RateLimited("spam detected")
                game_id = int(path.split("/")[3]); body = clean_contribution(data.get("body"), 1200, "comment")
                self.check_contribution_limit(user, game_id, "comment")
                with db() as conn:
                    duplicate = conn.execute("SELECT 1 FROM comments WHERE user_id=? AND game_id=? AND body=? AND created_at>?", (user["id"], game_id, body, int(time.time()) - 86400)).fetchone()
                    if duplicate: raise RateLimited("This comment was already sent")
                    conn.execute("INSERT INTO comments(user_id,game_id,body,created_at) VALUES(?,?,?,?)", (user["id"], game_id, body, int(time.time())))
                self.send_json({"ok": True}, 201)
            elif re.fullmatch(r"/api/games/\d+/favorite", path):
                user = self.require_user()
                if not user: return
                if not rate_allowed(self.client_address[0], "favorite", 90, 600): raise PermissionError("too many requests")
                game_id = int(path.split("/")[3])
                with db() as conn:
                    game = conn.execute("SELECT id FROM games WHERE id=?", (game_id,)).fetchone()
                    if not game: raise ValueError("game not found")
                    existing = conn.execute("SELECT 1 FROM favorites WHERE user_id=? AND game_id=?", (user["id"], game_id)).fetchone()
                    if existing:
                        conn.execute("DELETE FROM favorites WHERE user_id=? AND game_id=?", (user["id"], game_id))
                        favorited = False
                    else:
                        conn.execute("INSERT INTO favorites(user_id,game_id,created_at) VALUES(?,?,?)", (user["id"], game_id, int(time.time())))
                        favorited = True
                self.send_json({"ok": True, "favorited": favorited})
            elif re.fullmatch(r"/api/games/\d+/reports", path):
                user = self.require_user()
                if not user: return
                game_id = int(path.split("/")[3])
                data = self.read_json()
                if str(data.get("website") or "").strip(): raise RateLimited("spam detected")
                category = str(data.get("category") or "other")
                body = clean_contribution(data.get("body"), 1600, "report")
                if category not in {"controls", "playback", "other"}: raise ValueError("invalid report category")
                self.check_contribution_limit(user, game_id, "report")
                with db() as conn:
                    game = conn.execute("SELECT id FROM games WHERE id=?", (game_id,)).fetchone()
                    if not game: raise ValueError("game not found")
                    now = int(time.time())
                    duplicate = conn.execute("SELECT 1 FROM reports WHERE user_id=? AND game_id=? AND body=? AND created_at>?", (user["id"], game_id, body, now - 7 * 86400)).fetchone()
                    if duplicate: raise RateLimited("This report was already sent")
                    conn.execute("INSERT INTO reports(user_id,game_id,category,body,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (user["id"], game_id, category, body, "open", now, now))
                self.send_json({"ok": True}, 201)
            elif path == "/api/account/display-name":
                user = self.require_user()
                if not user: return
                display = clean_display_name(self.read_json().get("display_name"))
                with db() as conn:
                    conn.execute("UPDATE users SET display_name=? WHERE id=?", (display, user["id"]))
                self.send_json({"ok": True, "display_name": display})
            elif re.fullmatch(r"/admin/api/games/\d+/uploads", path):
                user = self.require_user(admin=True)
                if not user:
                    return
                data = self.read_json()
                game_id = int(path.split("/")[4])
                kind = str(data.get("kind") or "")
                name = os.path.basename(str(data.get("name") or "")).strip()
                size = int(data.get("size") or 0)
                if kind != "rom" or size <= 0 or size > MAX_ROM_BYTES:
                    raise ValueError("invalid upload session")
                with db() as conn:
                    game = conn.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
                if not game:
                    raise ValueError("game not found")
                self.upload_specs(game, kind, name)
                upload_id = secrets.token_urlsafe(24)
                temp_name = f"{upload_id}.part"
                temp = safe_data_path(UPLOAD_DIR, temp_name)
                with open(temp, "xb"):
                    pass
                try:
                    now = int(time.time())
                    with db() as conn:
                        conn.execute("INSERT INTO upload_sessions(id,game_id,kind,filename,expected_size,received_size,temp_name,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (upload_id, game_id, kind, name, size, 0, temp_name, now, now))
                except Exception:
                    try:
                        os.remove(temp)
                    except OSError:
                        pass
                    raise
                self.send_json({"ok": True, "upload_id": upload_id, "chunk_size": MAX_UPLOAD_CHUNK_BYTES}, 201)
            elif re.fullmatch(r"/admin/api/uploads/[A-Za-z0-9_-]{16,128}/complete", path):
                user = self.require_user(admin=True)
                if not user:
                    return
                self.read_json()
                upload_id = path.split("/")[4]
                with db() as conn:
                    session = conn.execute("SELECT * FROM upload_sessions WHERE id=?", (upload_id,)).fetchone()
                if not session:
                    raise ValueError("upload session not found")
                if session["received_size"] != session["expected_size"]:
                    raise ValueError("upload is incomplete")
                temp = safe_data_path(UPLOAD_DIR, session["temp_name"])
                result = self.finalize_game_upload(session["game_id"], session["kind"], session["filename"], temp, session["expected_size"])
                with db() as conn:
                    conn.execute("DELETE FROM upload_sessions WHERE id=?", (upload_id,))
                self.send_json(result)
            elif path == "/admin/api/games":
                user = self.require_user(admin=True)
                if not user: return
                data = self.read_json(); now = int(time.time())
                requested_system = data.get("system")
                automatic = requested_system == "auto"
                system = infer_system(str(data.get("rom_name") or "")) if automatic else requested_system
                system = system or "gb"
                if system not in SYSTEMS: raise ValueError("unsupported system")
                fallback_title = filename_title(data.get("rom_name"))
                title_vi = str(data.get("title_vi") or "").strip()[:120] or fallback_title
                title_en = str(data.get("title_en") or "").strip()[:120] or fallback_title
                with db() as conn:
                    slug = unique_slug(conn, title_en or title_vi)
                    cur = conn.execute("INSERT INTO games(slug,title_vi,title_en,description_vi,description_en,system,published,experimental,system_auto,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (slug,title_vi,title_en,str(data.get("description_vi") or "")[:8000],str(data.get("description_en") or "")[:8000],system,int(bool(data.get("published"))),int(bool(data.get("experimental") or system=="3ds")),int(automatic),now,now))
                    add_game_update(conn, cur.lastrowid, "Game created", "Game created", str(data.get("update_note") or "")[:4000], str(data.get("update_note") or "")[:4000])
                self.send_json({"ok": True, "id": cur.lastrowid, "slug": slug}, 201)
            elif path == "/admin/api/games/batch-status/preview":
                user = self.require_user(admin=True)
                if not user: return
                target, ids = batch_status_request(self.read_json())
                with db() as conn:
                    preview = batch_status_preview(conn, target, ids)
                self.send_json({"ok": True, **preview})
            elif path == "/admin/api/games/batch-status/apply":
                user = self.require_user(admin=True)
                if not user: return
                data = self.read_json()
                target, ids = batch_status_request(data)
                with db() as conn:
                    preview = batch_status_preview(conn, target, ids)
                    if str(data.get("confirmation") or "") != preview["confirmation"]:
                        raise ValueError("explicit preview confirmation does not match")
                    now = int(time.time())
                    with conn:
                        for item in preview["games"]:
                            conn.execute("UPDATE games SET published=?,experimental=?,updated_at=? WHERE id=?", (preview["published"], preview["experimental"], now, item["id"]))
                            add_game_update(conn, item["id"], "Batch status updated", "Batch status updated", preview["target_label"], preview["target_label"])
                self.send_json({"ok": True, "changed": len(preview["games"]), "target": preview["target"], "confirmation": preview["confirmation"]})
            elif re.fullmatch(r"/admin/api/games/\d+", path):
                user = self.require_user(admin=True)
                if not user: return
                game_id = int(path.rsplit("/",1)[1]); data=self.read_json(); requested_system=data.get("system")
                automatic = requested_system == "auto"
                with db() as conn: current_game=conn.execute("SELECT system,rom_name,title_vi,title_en FROM games WHERE id=?",(game_id,)).fetchone()
                if not current_game: raise ValueError("game not found")
                system = current_game["system"] if automatic else requested_system
                if system not in SYSTEMS: raise ValueError("unsupported system")
                fallback_title = filename_title(data.get("rom_name") or current_game["rom_name"])
                title_vi=str(data.get("title_vi") or "").strip()[:120] or fallback_title or current_game["title_vi"]
                title_en=str(data.get("title_en") or "").strip()[:120] or fallback_title or current_game["title_en"]
                with db() as conn:
                    slug=unique_slug(conn,title_en or title_vi,game_id)
                    conn.execute("UPDATE games SET slug=?,title_vi=?,title_en=?,description_vi=?,description_en=?,system=?,published=?,experimental=?,system_auto=?,updated_at=? WHERE id=?", (slug,title_vi,title_en,str(data.get("description_vi") or "")[:8000],str(data.get("description_en") or "")[:8000],system,int(bool(data.get("published"))),int(bool(data.get("experimental") or system=="3ds")),int(automatic),int(time.time()),game_id))
                    note = str(data.get("update_note") or "").strip()[:4000]
                    add_game_update(conn, game_id, "Game information updated", "Game information updated", note, note)
                self.send_json({"ok": True,"id":game_id,"slug":slug})
            elif re.fullmatch(r"/admin/api/games/\d+/updates", path):
                user = self.require_user(admin=True)
                if not user: return
                game_id = int(path.split("/")[4]); data = self.read_json()
                title = str(data.get("title") or "").strip()[:120]
                body = str(data.get("body") or "").strip()[:4000]
                if not title:
                    raise ValueError("missing update title")
                with db() as conn:
                    if not conn.execute("SELECT id FROM games WHERE id=?", (game_id,)).fetchone():
                        raise ValueError("game not found")
                    add_game_update(conn, game_id, title, title, body, body)
                self.send_json({"ok": True}, 201)
            elif re.fullmatch(r"/admin/api/comments/\d+/delete", path):
                user=self.require_user(admin=True)
                if not user:return
                with db() as conn: conn.execute("DELETE FROM comments WHERE id=?",(int(path.split("/")[4]),))
                self.send_json({"ok":True})
            elif path == "/admin/api/users":
                user = self.require_user(admin=True)
                if not user: return
                data = self.read_json()
                name = clean_name(data.get("name"))
                display = clean_display_name(data.get("display_name") or name)
                password = str(data.get("password") or "")
                validate_password(password, str(data.get("confirm") or ""), lang)
                with db() as conn:
                    try:
                        cur = conn.execute("INSERT INTO users(name,display_name,password_hash,role,created_at) VALUES(?,?,?,?,?)", (name, display, password_hash(password), "admin", int(time.time())))
                    except sqlite3.IntegrityError:
                        raise ValueError(tr(lang, "Tên này đã được sử dụng", "This username is already in use"))
                self.send_json({"ok": True, "id": cur.lastrowid}, 201)
            elif re.fullmatch(r"/admin/api/users/\d+", path):
                user = self.require_user(admin=True)
                if not user: return
                user_id = int(path.rsplit("/", 1)[1])
                display = clean_display_name(self.read_json().get("display_name"))
                with db() as conn:
                    if not conn.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone():
                        raise ValueError("account not found")
                    conn.execute("UPDATE users SET display_name=? WHERE id=?", (display, user_id))
                self.send_json({"ok": True, "display_name": display})
            elif path == "/admin/api/site-settings":
                user = self.require_user(admin=True)
                if not user: return
                data = self.read_json()
                email = str(data.get("maintainer_email") or "").strip()
                facebook = str(data.get("maintainer_facebook") or "").strip()
                if email and (len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)):
                    raise ValueError("invalid email")
                if facebook and not re.fullmatch(r"https?://[^\s]{1,500}", facebook):
                    raise ValueError("invalid Facebook URL")
                links = clean_contact_links(data.get("maintainer_links"))
                with db() as conn:
                    for key, value in (("maintainer_email", email), ("maintainer_facebook", facebook), ("maintainer_links", links)):
                        conn.execute("INSERT INTO site_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
                self.send_json({"ok": True})
            elif re.fullmatch(r"/admin/api/reports/\d+", path):
                user = self.require_user(admin=True)
                if not user: return
                report_id = int(path.rsplit("/", 1)[1])
                status = str(self.read_json().get("status") or "")
                if status not in {"open", "resolved"}: raise ValueError("invalid report status")
                with db() as conn:
                    cur = conn.execute("UPDATE reports SET status=?,updated_at=? WHERE id=?", (status, int(time.time()), report_id))
                    if cur.rowcount != 1: raise ValueError("report not found")
                self.send_json({"ok": True, "status": status})
            elif path == "/api/bug-reports":
                self._cors_origin = self.support_origin()
                self.bug_report_submit()
            elif path == "/api/multiplayer/room":
                self.multiplayer_create_room()
            elif path == "/api/multiplayer/join":
                self.multiplayer_join_room()
            elif path == "/api/multiplayer/leave":
                self.multiplayer_leave_room()
            elif path == "/api/multiplayer/reconnect":
                self.multiplayer_reconnect()
            elif path == "/api/multiplayer/input":
                self.multiplayer_publish_input()
            elif path == "/api/controller/session":
                self.controller_create_session()
            elif path == "/api/controller/pair":
                self.controller_pair()
            elif path == "/api/controller/state":
                self.controller_submit_state()
            elif path == "/api/controller/ack":
                self.controller_ack()
            elif path == "/api/controller/disconnect":
                self.controller_disconnect()
            elif path == "/api/sync/settings":
                self.sync_set_settings()
            elif path == "/api/sync/plan":
                self.sync_plan()
            elif path == "/api/sync/resolve":
                self.sync_resolve()
            elif path == "/api/sync/lan/announce":
                self.lan_peer_announce()
            elif path == "/api/sync/lan/publish":
                self.sync_lan_publish()
            else:
                self.send_json({"error":"not found"},404)
        except RateLimited as exc:
            self.send_json({"error":str(exc)},429)
        except netcode.RateLimitedError as exc:
            self.send_json({"error": str(exc)}, 429)
        except PermissionError as exc:
            self.send_json({"error":str(exc)},403)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error":str(exc)},400)
        except Exception:
            self.send_json({"error":"Request could not be processed"},400)

    def upload_specs(self, game, kind, name):
        name = os.path.basename(name).strip()
        ext = os.path.splitext(name.lower())[1]
        if not name:
            raise ValueError("missing file name")
        if kind in {"cover", "screenshot"}:
            if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
                raise ValueError("unsupported image")
            root = SCREENSHOT_DIR if kind == "screenshot" else COVER_DIR
            filename = f"{game['id']}-{int(time.time())}-{secrets.token_hex(4)}{ext}" if kind == "screenshot" else f"{game['id']}{ext}"
        elif kind == "rom":
            allowed = set().union(*EXTENSIONS.values()) if game["system_auto"] else EXTENSIONS.get(game["system"], set())
            if ext not in allowed:
                raise ValueError("unsupported game file")
            root = ROM_DIR
            stem = re.sub(r"[^A-Za-z0-9._-]+", "-", os.path.splitext(name)[0]).strip("-.")[:140] or "game"
            filename = f"{game['id']}-{stem}{ext}"
        else:
            raise ValueError("unsupported upload kind")
        return name, ext, root, filename

    def write_upload_body(self, temp, length, mode="wb"):
        remaining = length
        with open(temp, mode) as handle:
            while remaining:
                chunk = self.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self._body_consumed = getattr(self, "_body_consumed", 0) + len(chunk)
                handle.write(chunk)
                remaining -= len(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if remaining:
            # The client declared more than it sent; there is no body left to
            # drain, so close the connection instead of blocking on a read.
            self.close_connection = True
            raise ValueError("incomplete upload")

    def finalize_game_upload(self, game_id, kind, name, temp, size):
        with db() as conn:
            game = conn.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
        if not game:
            raise ValueError("game not found")
        name, ext, root, filename = self.upload_specs(game, kind, name)
        target = safe_data_path(root, filename)
        detected = infer_system(name, temp) if kind == "rom" and game["system_auto"] else game["system"]
        if kind == "rom" and not detected:
            raise ValueError("Could not detect the system; choose it manually")
        os.replace(temp, target)
        if kind == "rom":
            clear_prepared_game_roms(game_id)
        if kind == "cover":
            with db() as conn:
                conn.execute("UPDATE games SET cover_path=?,updated_at=? WHERE id=?", (filename, int(time.time()), game_id))
        elif kind == "screenshot":
            with db() as conn:
                conn.execute("INSERT INTO game_screenshots(game_id,file_path,created_at) VALUES(?,?,?)", (game_id, filename, int(time.time())))
        else:
            if detected == "html5":
                self.extract_custom(game_id, target, ext)
            with db() as conn:
                conn.execute("UPDATE games SET rom_path=?,rom_name=?,file_size=?,system=?,system_auto=0,experimental=CASE WHEN ?='3ds' THEN 1 ELSE experimental END,updated_at=? WHERE id=?", (filename, name, size, detected, detected, int(time.time()), game_id))
        previous = game["cover_path"] if kind == "cover" else (game["rom_path"] if kind == "rom" else "")
        if previous and previous != filename:
            try:
                os.remove(safe_data_path(root, previous))
            except OSError:
                pass
        return {"ok": True, "size": size, "system": detected if kind == "rom" else game["system"]}

    def do_PUT(self):
        path = urlparse(self.path).path
        chunk_match = re.fullmatch(r"/admin/api/uploads/([A-Za-z0-9_-]{16,128})", path)
        if chunk_match:
            user = self.require_user(admin=True)
            if not user:
                return
            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
                offset = int(self.headers.get("X-Upload-Offset", "-1"))
                if length <= 0 or length > MAX_UPLOAD_CHUNK_BYTES or offset < 0:
                    raise ValueError("invalid upload chunk")
                upload_id = chunk_match.group(1)
                with db() as conn:
                    session = conn.execute("SELECT * FROM upload_sessions WHERE id=?", (upload_id,)).fetchone()
                    if not session:
                        raise ValueError("upload session not found")
                    if offset != session["received_size"]:
                        self.send_json({"error": "upload offset conflict", "received": session["received_size"]}, 409)
                        return
                    if offset + length > session["expected_size"]:
                        raise ValueError("upload exceeds expected size")
                    temp = safe_data_path(UPLOAD_DIR, session["temp_name"])
                    self.write_upload_body(temp, length, "ab")
                    received = offset + length
                    conn.execute("UPDATE upload_sessions SET received_size=?,updated_at=? WHERE id=?", (received, int(time.time()), upload_id))
                self.send_json({"ok": True, "received": received, "complete": received == session["expected_size"]})
            except ValueError as exc:
                self.send_json({"error": str(exc)}, 400)
            except Exception:
                self.send_json({"error": "Upload could not be processed"}, 400)
            return

        match = re.fullmatch(r"/admin/api/games/(\d+)/(rom|cover|screenshot)", path)
        if not match:
            self.send_json({"error": "not found"}, 404)
            return
        user = self.require_user(admin=True)
        if not user:
            return
        game_id, kind = int(match.group(1)), match.group(2)
        temp = ""
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
            limit = MAX_ROM_BYTES if kind == "rom" else (MAX_SCREENSHOT_BYTES if kind == "screenshot" else MAX_COVER_BYTES)
            if length <= 0 or length > limit:
                raise ValueError("invalid file size")
            name = os.path.basename(unquote(parse_qs(urlparse(self.path).query).get("name", [""])[0])).strip()
            temp = safe_data_path(UPLOAD_DIR, f"direct-{secrets.token_urlsafe(18)}.part")
            self.write_upload_body(temp, length)
            self.send_json(self.finalize_game_upload(game_id, kind, name, temp, length))
        except (ValueError, zipfile.BadZipFile) as exc:
            if temp and os.path.exists(temp):
                os.remove(temp)
            self.send_json({"error": str(exc)}, 400)
        except Exception:
            if temp and os.path.exists(temp):
                os.remove(temp)
            self.send_json({"error": "Upload could not be processed"}, 400)

    def extract_custom(self, game_id, archive, ext):
        destination=os.path.join(CUSTOM_DIR,str(game_id))
        staging=destination+".new"
        if os.path.isdir(staging): shutil.rmtree(staging)
        os.makedirs(staging)
        if ext==".html":
            shutil.copy2(archive,os.path.join(staging,"index.html"))
        else:
            total=0
            with zipfile.ZipFile(archive) as zf:
                for item in zf.infolist():
                    total+=item.file_size
                    if total>2*1024**3 or len(zf.infolist())>20000: raise ValueError("custom game archive too large")
                    target=safe_data_path(staging,item.filename)
                    if item.is_dir(): os.makedirs(target,exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(target),exist_ok=True)
                        with zf.open(item) as src,open(target,"wb") as dst: shutil.copyfileobj(src,dst,1024*1024)
            if not os.path.isfile(os.path.join(staging,"index.html")):
                roots=[name for name in os.listdir(staging) if os.path.isdir(os.path.join(staging,name))]
                if len(roots)==1 and os.path.isfile(os.path.join(staging,roots[0],"index.html")):
                    nested=os.path.join(staging,roots[0])
                    for name in os.listdir(nested): shutil.move(os.path.join(nested,name),os.path.join(staging,name))
                    os.rmdir(nested)
                else: raise ValueError("custom game needs index.html")
        if os.path.isdir(destination): shutil.rmtree(destination)
        os.replace(staging,destination)

    def do_DELETE(self):
        path=urlparse(self.path).path
        upload_match = re.fullmatch(r"/admin/api/uploads/([A-Za-z0-9_-]{16,128})", path)
        if upload_match:
            user = self.require_user(admin=True)
            if not user:
                return
            with db() as conn:
                upload = conn.execute("SELECT temp_name FROM upload_sessions WHERE id=?", (upload_match.group(1),)).fetchone()
                if upload:
                    conn.execute("DELETE FROM upload_sessions WHERE id=?", (upload_match.group(1),))
            if upload:
                try:
                    os.remove(safe_data_path(UPLOAD_DIR, upload["temp_name"]))
                except OSError:
                    pass
            self.send_json({"ok": True})
            return
        match=re.fullmatch(r"/admin/api/games/(\d+)",path)
        if not match: self.send_json({"error":"not found"},404); return
        user=self.require_user(admin=True)
        if not user:return
        game_id=int(match.group(1))
        with db() as conn:
            game=conn.execute("SELECT * FROM games WHERE id=?",(game_id,)).fetchone()
            if not game: self.send_json({"error":"not found"},404); return
            screenshots=conn.execute("SELECT file_path FROM game_screenshots WHERE game_id=?",(game_id,)).fetchall()
            uploads=conn.execute("SELECT temp_name FROM upload_sessions WHERE game_id=?", (game_id,)).fetchall()
            conn.execute("DELETE FROM games WHERE id=?",(game_id,))
        for root,key in ((ROM_DIR,"rom_path"),(COVER_DIR,"cover_path")):
            if game[key]:
                try: os.remove(safe_data_path(root,game[key]))
                except OSError: pass
        for screenshot in screenshots:
            try: os.remove(safe_data_path(SCREENSHOT_DIR,screenshot["file_path"]))
            except OSError: pass
        for upload in uploads:
            try: os.remove(safe_data_path(UPLOAD_DIR,upload["temp_name"]))
            except OSError: pass
        clear_prepared_game_roms(game_id)
        custom=os.path.join(CUSTOM_DIR,str(game_id))
        if os.path.isdir(custom): shutil.rmtree(custom)
        self.send_json({"ok":True})


if __name__ == "__main__":
    init_db()
    bootstrap_admin()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Vibe Coded Emulator listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()
