#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import bug_report
import hashlib
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
import sys
import threading
import time
import zipfile
from datetime import datetime, timezone
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
PLAYER_BOOT_ASSETS = frozenset({"offline.js", "player-ui.js", "player-runtime.js", "renderer-worker.js", "nds-touch.js", "local-save-recovery.js", "player.js", "site.css"})

# The public source location for the GPL corresponding source. Deployments can
# override the canonical project URL with AN3_SOURCE_REPOSITORY.
SOURCE_REPOSITORY = os.environ.get("AN3_SOURCE_REPOSITORY", "https://github.com/huou07/vibe-coded-emulator")

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
EMULATOR_CACHE_DIR = os.path.join(DATA_DIR, "emulatorjs-cache")
PREPARED_ROM_DIR = os.path.join(DATA_DIR, "prepared-roms")
DB_PATH = os.path.join(DATA_DIR, "arcade.db")
HOST = os.environ.get("AN3_HOST", "0.0.0.0")
PORT = int(os.environ.get("AN3_PORT", "8091"))
BASE_URL = os.environ.get("AN3_BASE_URL", f"http://127.0.0.1:{PORT}").rstrip("/")
COOKIE_SECURE = os.environ.get("AN3_COOKIE_SECURE", "0") == "1"
MAX_ROM_BYTES = int(os.environ.get("AN3_MAX_ROM_BYTES", str(8 * 1024**3)))
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
# unauthenticated room endpoint is ever exposed there.
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


# --- Bug report pipeline -----------------------------------------------------
# User bug reports are collected on the client only after local sanitization and
# explicit consent, re-sanitized on the server, stored even when the downstream
# GitHub call fails, and finally turned into a GitHub issue with a server-only
# token. The token is never sent to, or readable by, the client.
BUG_REPORT_ENABLED = os.environ.get("AN3_BUG_REPORTS_ENABLED", "1").strip() != "0"
BUG_REPORT_MAX_BYTES = 256 * 1024
BUG_REPORT_RATE_LIMIT = 12
BUG_REPORT_RATE_WINDOW = 3600
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


EMULATOR_CDN = "https://cdn.emulatorjs.org"
EMULATOR_CACHE_LOCK = threading.Lock()
EMULATOR_ASSET_LOCKS = {}
PREPARED_ROM_LOCK = threading.Lock()
PREPARED_ROM_LOCKS = {}


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
              id INTEGER PRIMARY KEY
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
            CREATE TABLE IF NOT EXISTS site_settings (
              key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT ''
            );
            -- Bug report pipeline for anonymous native support submissions.
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
            CREATE TABLE IF NOT EXISTS game_screenshots (
              id INTEGER PRIMARY KEY, game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
              file_path TEXT NOT NULL, created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS game_updates (
              id INTEGER PRIMARY KEY, game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
              title_vi TEXT NOT NULL, title_en TEXT NOT NULL,
              body_vi TEXT NOT NULL DEFAULT '', body_en TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS games_public_idx ON games(published, updated_at DESC);
            CREATE INDEX IF NOT EXISTS bug_reports_created_idx ON bug_reports(created_at DESC);
            CREATE INDEX IF NOT EXISTS bug_reports_fingerprint_idx ON bug_reports(fingerprint);
            CREATE INDEX IF NOT EXISTS support_capabilities_expires_idx ON support_capabilities(expires_at);
            CREATE INDEX IF NOT EXISTS game_screenshots_game_idx ON game_screenshots(game_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS game_updates_game_idx ON game_updates(game_id, created_at DESC);
            """
        )
        # Retire account credentials without changing user IDs referenced by
        # historical rows. Stored sessions are revocable tokens and are dropped.
        conn.execute("DROP TABLE IF EXISTS sessions")
        user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        if user_columns - {"id"}:
            conn.commit()
            conn.execute("PRAGMA foreign_keys=OFF")
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("CREATE TABLE users_core_only (id INTEGER PRIMARY KEY)")
                conn.execute("INSERT INTO users_core_only(id) SELECT id FROM users")
                conn.execute("DROP TABLE users")
                conn.execute("ALTER TABLE users_core_only RENAME TO users")
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.execute("PRAGMA foreign_keys=ON")
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(games)")}
        if "system_auto" not in columns:
            conn.execute("ALTER TABLE games ADD COLUMN system_auto INTEGER NOT NULL DEFAULT 0")
        defaults = {
            "maintainer_email": os.environ.get("AN3_MAINTAINER_EMAIL", ""),
            "maintainer_facebook": "",
            "maintainer_links": "",
        }
        for key, value in defaults.items():
            conn.execute("INSERT OR IGNORE INTO site_settings(key,value) VALUES(?,?)", (key, value))


def esc(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def ref_icon(name, extra=""):
    """Render a local, non-interactive icon from the bundled Lucide asset set."""
    safe_name = re.sub(r"[^a-z0-9-]", "", str(name))
    safe_extra = re.sub(r"[^a-z0-9 -]", "", str(extra))
    return f'<span class="ui-mask ui-ref-{safe_name} {safe_extra}" aria-hidden="true"></span>'


class RateLimited(PermissionError):
    pass


def rate_limit_hash(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()






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




def game_cover(game):
    return f"/cover/{game['id']}" if game["cover_path"] else "/static/default-cover.webp"




def library_fingerprint(conn):
    row = conn.execute(
        "SELECT COALESCE(MAX(updated_at),0) changed, COUNT(*) games FROM games"
    ).fetchone()
    return f'{row["changed"]}:{row["games"]}'


def layout(title, content, lang, player=False, offline=False, library=False):
    with db() as conn:
        settings = site_settings(conn)
    # Keep the offline-state affordance on the public reference pages.
    mode_label = "Offline"
    online_target = "/games" if ENVIRONMENT != "production" else "/"
    mode_aria = tr(lang,"Mở thư viện trực tuyến","Open online library") if offline and ENVIRONMENT != "production" else (tr(lang,"Mở trang tải ứng dụng","Open app downloads") if offline else tr(lang,"Mở thư viện ngoại tuyến","Open offline library"))
    mode_icon = '<span class="ui-mask ui-wifi-off" aria-hidden="true"></span>'
    mode = f'<a id="modeSwitch" class="mode-switch" href="{online_target if offline else "/offline"}" aria-label="{mode_aria}">{mode_icon}<span>{mode_label}</span></a>'
    contacts = []
    if settings.get("maintainer_email"):
        contacts.append(f'<a href="mailto:{esc(settings["maintainer_email"])}">{esc(settings["maintainer_email"])}</a>')
    if settings.get("maintainer_facebook"):
        contacts.append(f'<a href="{esc(settings["maintainer_facebook"])}" rel="me noopener noreferrer" target="_blank">Facebook</a>')
    contacts.extend(f'<a href="{esc(url)}" rel="me noopener noreferrer" target="_blank">{esc(label)}</a>' for label, url in parse_contact_links(settings.get("maintainer_links")))
    contact_block = f'<div class="contact-links"><span>{tr(lang,"Liên hệ maintain:","Maintainer contact:")}</span>{"".join(contacts)}</div>' if contacts else ""
    stage_badge = '<span class="stage-badge">STAGING</span>' if ENVIRONMENT == "staging" else ""
    body_classes = []
    if player:
        body_classes.append("player-page")
    if library:
        body_classes.append("library-shell")
    if offline:
        body_classes.append("offline-shell")
    if not player:
        body_classes.append("reference-shell")
    page_scripts = f'<script src="/static/site.js?v={ASSET_VERSION}" defer></script>'
    if offline:
        page_scripts += "".join(
            f'<script src="{versioned_player_asset(name)}" defer></script>'
            for name in (
                "offline.js",
                "player-ui.js",
                "player-runtime.js",
                "renderer-worker.js",
                "nds-touch.js",
                "local-save-recovery.js",
                "player.js",
            )
        )
    return f"""<!doctype html>
<html lang="{lang}" class="{'library-root' if library else ''}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#07060c"><title>{esc(title)} · {esc(SITE_NAME)}</title>
<link rel="manifest" href="/static/manifest.webmanifest?v={ASSET_VERSION}">
<link rel="icon" type="image/png" sizes="192x192" href="/static/icon-192.png?v={ASSET_VERSION}">
<link rel="apple-touch-icon" href="/static/icon-192.png?v={ASSET_VERSION}">
<link rel="stylesheet" href="{versioned_player_asset("site.css") if player else f"/static/site.css?v={ASSET_VERSION}"}">{"" if player else f'<link rel="stylesheet" href="/static/theme-violet.css?v={ASSET_VERSION}">'}</head><body class="{' '.join(body_classes)}">
<header class="site-header"><a class="brand" href="/" aria-label="{esc(SITE_NAME)}"><img class="brand-logo" src="/static/brand-logo.png?v={ASSET_VERSION}" alt="{esc(SITE_NAME)}" width="52" height="52"></a>{stage_badge}<nav id="siteNav" class="site-nav">{"" if ENVIRONMENT == "production" else f'<a class="nav-games" href="/games">{ref_icon("gamepad-2")}{tr(lang,"Trò chơi","Games")}</a>'}<a class="nav-download-app" href="/">{ref_icon("download")}{tr(lang,"Tải app","Download app")}</a></nav><div class="header-actions">{mode}<button id="navToggle" class="nav-toggle" type="button" aria-label="{tr(lang,'Mở menu','Open menu')}" aria-controls="siteNav" aria-expanded="false"><span class="ui-mask ui-menu" aria-hidden="true"></span><span class="nav-toggle-label">{tr(lang,"Menu","Menu")}</span></button></div></header>
{content}
<footer class="site-footer"><div><strong>{esc(SITE_NAME)}</strong><span>{tr(lang,"Game chạy trên phần cứng của thiết bị người chơi.","Games run on the player's device.")}</span></div>{contact_block}
<div class="credits"><span>{tr(lang,"Công cụ và nguồn mở:","Tools and open source:")}</span><a href="https://emulatorjs.org/">EmulatorJS</a><a href="https://www.retroarch.com/">RetroArch</a><a href="https://github.com/mgba-emu/mgba">mGBA</a><a href="https://melonds.kuribo64.net/">melonDS</a><a href="https://github.com/azahar-emu/azahar">Azahar</a><a href="https://www.python.org/">Python</a><a href="https://sqlite.org/">SQLite</a><a href="/licenses">{tr(lang,"Giấy phép","Licenses")}</a></div></footer>
{page_scripts}</body></html>"""


def status_page(code, lang):
    if code == 403:
        title = tr(lang, "Không có quyền truy cập", "Access restricted")
        message = tr(lang, "Trang này không khả dụng.", "This page is unavailable.")
    else:
        title = tr(lang, "Không tìm thấy trang", "Page not found")
        message = tr(lang, "Liên kết này có thể đã thay đổi hoặc game không còn ở địa chỉ này.", "This link may have changed, or the game is no longer available at this address.")
    primary_href = "/games" if ENVIRONMENT != "production" else "/"
    primary_label = tr(lang, 'Duyệt thư viện', 'Browse library') if ENVIRONMENT != "production" else tr(lang, 'Tải ứng dụng', 'Download app')
    body = f'''<main class="page status-page"><section class="status-card" aria-labelledby="statusTitle"><p class="eyebrow">{tr(lang,'Mã trạng thái','Status code')} {code}</p><h1 id="statusTitle">{title}</h1><p>{message}</p><div class="status-actions"><a class="button primary" href="{primary_href}">{primary_label}</a><a class="button" href="/offline">{tr(lang,'Mở game trên thiết bị','Open device games')}</a></div></section></main>'''
    return layout(f"{code} · {title}", body, lang)


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


def download_app_page(lang, origin=""):
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
<article><div><strong>{t("Hạn chế đã biết","Known limitations")}</strong><span>{t("Tương thích Eden/Switch chưa được kiểm chứng toàn diện; hành vi runtime Windows/Linux có thể ít được kiểm chứng hơn phần đóng gói.","Eden/Switch compatibility is not comprehensively verified; Windows/Linux runtime behaviour may be less verified than packaging.")}</span></div></article>
<article><div><strong>{t("Báo lỗi","Report a bug")}</strong><span>{t("Dùng mục Báo lỗi trong app (Help / About). Nêu nền tảng, phiên bản app, core và các bước tái hiện. Không đính kèm ROM, firmware, key hay tệp save.","Use the in-app Report a bug flow (Help / About). Include platform, app version, core and steps to reproduce. Do not attach ROMs, firmware, keys or saves.")}</span></div></article>
</section>
</main>'''
    return layout(tr(lang, "Tải ứng dụng", "Download app"), body, lang)


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


def home_page(lang):
    with db() as conn:
        games = conn.execute("SELECT * FROM games ORDER BY updated_at DESC").fetchall()
        version = library_fingerprint(conn)

    home_system_labels = {
        "gb": "GB/C", "gba": "GBA", "nds": "NDS", "3ds": "3DS",
        "nes": "NES", "snes": "SNES", "n64": "N64", "psx": "PSX",
        "psp": "PSP", "segaMD": "MD", "segaMS": "MS", "segaGG": "GG",
        "sega32x": "32X", "segaCD": "CD", "segaSaturn": "SAT", "arcade": "ARC",
    }

    def card(game):
        title = game_title(game, lang)
        description = game_description(game, lang).strip()
        draft = f'<span class="badge draft">{tr(lang,"Draft","Draft")}</span>' if not game["published"] else ""
        testing = f'<span class="badge testing">Testing</span>' if game["experimental"] else ""
        system_label = home_system_labels.get(game["system"], SYSTEMS[game["system"]][0])
        secondary_action = f'''<a class="card-download" href="/download/{esc(game['slug'])}" aria-label="{tr(lang,'Tải game','Download game')}: {esc(title)}"><span class="ui-mask ui-download" aria-hidden="true"></span></a>'''
        play_action = f'''<a class="button primary" href="/play/{esc(game['slug'])}"><span class="ui-mask ui-play" aria-hidden="true"></span>{tr(lang,"Chơi ngay","Play now")}</a>'''
        return f"""<article class="game-card" data-system="{esc(game['system'])}" data-system-section="{esc(game['system'])}" data-game-slug="{esc(game['slug'])}"><a class="cover" href="/game/{esc(game['slug'])}" aria-label="{tr(lang,'Chi tiết','Details')}: {esc(title)}"><img src="{game_cover(game)}" alt="{esc(title)}" width="720" height="960" loading="lazy"></a>
<div class="game-card-body"><h2><a href="/game/{esc(game['slug'])}">{esc(title)}</a></h2>
<p class="card-description">{esc(description)}</p>
<div class="game-meta"><span class="badge">{esc(system_label)}</span>{draft}{testing}</div>
<div class="card-actions">{play_action}{secondary_action}</div></div></article>"""

    grouped = {system: [] for system in SYSTEMS}
    for game in games:
        grouped.setdefault(game["system"], []).append(game)
    home_system_order = ("gba", "nds") + tuple(system for system in SYSTEMS if system not in {"gba", "nds"})
    populated = [(system, grouped[system]) for system in home_system_order if grouped.get(system)]
    filters = "".join(
        f'<button class="system-filter" type="button" data-system-filter="{esc(system)}" aria-pressed="false">{esc(home_system_labels.get(system, SYSTEMS[system][0]))}<span>{len(items)}</span></button>'
        for system, items in populated
    )
    collection_cards = "".join(card(game) for game in games)
    collection = f'''<section class="game-system-section collection-section" data-section-kind="collection"><div class="section-title"><div class="section-heading"><span class="ui-mask ui-gamepad" aria-hidden="true"></span><h2>{tr(lang,"Bộ sưu tập","Collection")}</h2></div><button class="section-link collection-link" type="button" data-library-reset>{tr(lang,"Xem tất cả","View all")}<span class="ui-mask ui-chevron-right" aria-hidden="true"></span></button></div><div class="game-grid">{collection_cards}</div></section>'''
    empty = f'<div class="empty-state"><strong>{tr(lang,"Thư viện đang chờ game đầu tiên.","The library is waiting for its first game.")}</strong><span>{tr(lang,"Bạn vẫn có thể mở ROM riêng đã lưu trên thiết bị.","You can still open a private ROM saved on this device.")}</span><a class="button primary" href="/offline">{tr(lang,"Mở thư viện ngoại tuyến","Open offline library")}</a></div>'
    populated_library = f'''<nav id="systemFilters" class="system-filters" aria-label="{tr(lang,"Lọc theo hệ máy","Filter by system")}"><button class="system-filter active" type="button" data-system-filter="all" aria-pressed="true">{tr(lang,"Tất cả","All")}<span>{len(games)}</span></button>{filters}</nav><p id="libraryStatus" class="library-status" aria-live="polite"></p>{collection}<div id="libraryNoResults" class="empty-state" hidden><strong>{tr(lang,"Không tìm thấy trò chơi phù hợp.","No matching games found.")}</strong><span>{tr(lang,"Thử từ khóa khác hoặc xóa bộ lọc hệ máy.","Try another search or clear the system filter.")}</span><button id="resetLibrary" class="button" type="button">{tr(lang,"Xóa tìm kiếm và bộ lọc","Clear search and filters")}</button></div>'''
    body = f"""<main class="page library-page"><section class="library-head"><div><p class="eyebrow">Vibe Coded Emulator</p><h1>{tr(lang,"Thư viện trò chơi","Game library")}</h1><p class="muted">{tr(lang,"Chọn game và chơi ngay trên thiết bị của bạn.","Choose a game and play it on your own device.")}</p></div></section>
<section class="library-toolbar" aria-label="{tr(lang,'Tìm và lọc trò chơi','Find and filter games')}"><label class="search" for="gameSearch"><span>{tr(lang,'Tìm trò chơi','Search games')}</span><span class="search-field"><span class="ui-mask ui-search" aria-hidden="true"></span><input id="gameSearch" type="search" placeholder="{tr(lang,'Tìm trò chơi','Search games')}" autocomplete="off"><button id="clearSearch" class="search-clear" type="button" hidden>{tr(lang,'Xóa','Clear')}</button></span></label></section>
<div id="gameGrid" class="game-library" data-library-version="{version}">{populated_library if games else empty}</div></main>"""
    return layout(tr(lang, "Trò chơi", "Games"), body, lang, library=True)


def game_page(game, lang):
    with db() as conn:
        screenshots = conn.execute(
            "SELECT id FROM game_screenshots WHERE game_id=? ORDER BY created_at DESC",
            (game["id"],),
        ).fetchall()
        updates = conn.execute(
            "SELECT * FROM game_updates WHERE game_id=? ORDER BY created_at DESC LIMIT 60",
            (game["id"],),
        ).fetchall()
    screenshot_rows = "".join(
        f'<a href="/screenshot/{item["id"]}" target="_blank" rel="noopener"><img src="/screenshot/{item["id"]}" alt="{tr(lang,"Ảnh trong game","Game screenshot")}" loading="lazy"></a>'
        for item in screenshots
    )
    update_rows = "".join(
        f'<article class="game-update"><time>{datetime.fromtimestamp(item["created_at"]).strftime("%Y-%m-%d %H:%M")}</time><h3>{esc(item["title_en"] if lang == "en" else item["title_vi"])}</h3><p>{esc(item["body_en"] if lang == "en" else item["body_vi"]).replace(chr(10), "<br>")}</p></article>'
        for item in updates
    )
    draft = f'<span class="badge draft">{tr(lang,"Draft công khai","Public draft")}</span>' if not game["published"] else ""
    testing = '<span class="badge testing">Testing</span>' if game["experimental"] else ""
    title = game_title(game, lang)
    media = (
        f'<section class="description-media"><div class="section-title"><h2>{tr(lang,"Ảnh trong game","In-game images")}</h2><span>{len(screenshots)}</span></div><div class="screenshot-grid">{screenshot_rows}</div></section>'
        if screenshots else ""
    )
    body = f'''<main class="page detail-page"><section class="game-detail"><div class="detail-cover"><img src="{game_cover(game)}" alt="{esc(title)}" width="720" height="960"></div>
<div class="detail-copy"><div class="game-meta"><span class="badge">{esc(SYSTEMS[game['system']][0])}</span>{draft}{testing}</div><h1>{esc(title)}</h1>
<div class="detail-actions"><a class="button primary" href="/play/{esc(game['slug'])}">{tr(lang,"Chơi ngay","Play now")}</a><a class="button" href="/download/{esc(game['slug'])}">{tr(lang,"Tải game","Download game")} · {format_size(game['file_size'])}</a></div>
<p class="description">{esc(game_description(game,lang)).replace(chr(10),'<br>')}</p>
{media}</div></section>
<section class="game-updates"><div class="section-title"><h2>{tr(lang,"Lịch sử cập nhật","Update history")}</h2><span>{len(updates)}</span></div>{update_rows or f'<p class="muted">{tr(lang,"Chưa có cập nhật.","No updates yet.")}</p>'}</section></main>'''
    return layout(title, body, lang)


def offline_page(lang):
    """Browser-local ROM library and player, independent from server ROM routes."""
    t = lambda vi, en: tr(lang, vi, en)
    body = f'''<main class="page offline-page">
<header class="library-head"><div><p class="eyebrow">{t("THƯ VIỆN RIÊNG TRÊN THIẾT BỊ","DEVICE-LOCAL LIBRARY")}</p><h1>{t("Chơi ngoại tuyến","Offline Play")}</h1><p class="muted">{t("ROM, tiến độ và core được lưu trong trình duyệt này. Tệp ROM của bạn không được tải lên máy chủ.","ROMs, progress and cores stay in this browser. Your ROM files are not uploaded to the server.")}</p></div></header>
<section class="offline-readiness" aria-labelledby="offlineReadinessTitle"><div class="section-title"><h2 id="offlineReadinessTitle">{t("Trạng thái trên thiết bị này","This device")}</h2><button id="offlineShortcut" class="button" type="button">{t("Lưu ứng dụng","Save app")}</button></div><div class="offline-facts">
<div class="offline-fact-card"><span class="ui-mask ui-ref-wifi" aria-hidden="true"></span><div><span>{t("Mạng","Network")}</span><strong id="offlineNetworkState">{t("Đang kiểm tra","Checking")}</strong><small>{t("Chỉ cần mạng để tải core lần đầu","Network is only needed for the first core download")}</small></div></div>
<div class="offline-fact-card"><span class="ui-mask ui-ref-shield-check" aria-hidden="true"></span><div><span>{t("Kết nối an toàn","Secure context")}</span><strong id="offlineSecureState">{t("Đang kiểm tra","Checking")}</strong><small>{t("HTTPS hoặc localhost cho phép lưu toàn bộ trang","HTTPS or localhost enables full offline page storage")}</small></div></div>
<div class="offline-fact-card"><span class="ui-mask ui-ref-monitor-down" aria-hidden="true"></span><div><span>{t("Giao diện","Interface")}</span><strong id="offlineShellState">{t("Đang kiểm tra","Checking")}</strong><small>{t("Trang và core được lưu riêng","The page and cores are stored separately")}</small></div></div>
<div class="offline-fact-card"><span class="ui-mask ui-ref-hard-drive" aria-hidden="true"></span><div><span>{t("Game trên thiết bị","Local games")}</span><strong id="offlineGameCount">0</strong><small>{t("Lưu riêng trong trình duyệt này","Private to this browser")}</small></div></div>
</div></section>
<section class="offline-library" aria-labelledby="offlineLibraryTitle"><div class="offline-library-title"><div><h2 id="offlineLibraryTitle">{t("Thư viện trên thiết bị","Games on this device")}</h2><em>{t("RIÊNG TƯ","PRIVATE")}</em></div><span class="offline-library-views">{t("ROM chỉ nằm trong trình duyệt này","ROMs stay in this browser")}</span></div><div id="offlineGameGrid" class="offline-system-list" aria-live="polite"></div></section>
<aside class="offline-upload" aria-labelledby="offlineImportTitle"><div class="section-title"><p class="eyebrow">{t("THÊM GAME","ADD A GAME")}</p><h2 id="offlineImportTitle">{t("Chọn một ROM từ thiết bị","Choose a ROM from this device")}</h2></div>
<form id="offlineGameForm"><label id="offlineBrowserDropzone" class="offline-dropzone" for="offlineFile"><span class="ui-mask ui-ref-folder-open" aria-hidden="true"></span><strong>{t("Chọn tệp ROM","Choose a ROM file")}</strong><span>{t("Hỗ trợ GBA, NDS, 3DS và các core EmulatorJS ngoại tuyến","Supports GBA, NDS, 3DS and offline EmulatorJS cores")}</span><input id="offlineFile" name="file" type="file" required></label>
<label class="offline-import-field">{t("Tên game","Game title")}<input id="offlineTitle" name="title" maxlength="120" required autocomplete="off"></label><label class="offline-import-field">{t("Hệ máy","System")}<select id="offlineSystem" name="system"></select></label><button id="offlineBrowserImport" class="button primary" type="submit">{t("Lưu trên thiết bị này","Save on this device")}</button></form><p id="offlineDetection" class="muted" role="status"></p>
<div class="offline-private-note"><span class="ui-mask ui-ref-shield-check" aria-hidden="true"></span><div><strong>{t("Dữ liệu riêng trên thiết bị","Private device storage")}</strong><span>{t("ROM và dữ liệu lưu không được gửi tới AN3. Xóa dữ liệu trang web trong trình duyệt sẽ xóa các bản sao cục bộ.","ROMs and saves are not sent to AN3. Clearing this site's browser data removes local copies.")}</span></div></div>
<div class="offline-quick-guide"><h3>{t("Bắt đầu chơi","Get started")}</h3><ol><li>{t("Chọn một ROM hợp pháp của bạn.","Choose a ROM you are authorized to use.")}</li><li>{t("Tải core một lần khi trực tuyến.","Download its core once while online.")}</li><li>{t("Mở game từ thư viện để chơi.","Open the game from your library.")}</li></ol></div></aside>
<details id="coreManager" class="core-preload"><summary><strong>{t("Core ngoại tuyến","Offline cores")}</strong><span>{t("Mở","Open")}</span></summary><div class="core-preload-body"><p id="offlineCoreState" class="muted">{t("Trạng thái core được lưu riêng theo hệ máy.","Core status is stored separately by system.")}</p><div id="corePreloadGrid" class="core-preload-grid"></div><p id="corePreloadStatus" class="muted" role="status"></p></div></details>
</main>'''
    return layout("Offline", body, lang, offline=True)


def core_preload_page(system, lang):
    if system not in SYSTEMS or system == "html5":
        return status_page(404, lang)
    config = {"mode": "preload", "title": "Core preload", "slug": f"core-preload-{system}", "system": system, "channel": SYSTEMS[system][1], "lang": lang}
    ui_asset = versioned_player_asset("player-ui.js")
    runtime_asset = versioned_player_asset("player-runtime.js")
    player_asset = versioned_player_asset("player.js")
    renderer_asset = versioned_player_asset("renderer-worker.js")
    nds_touch_asset = versioned_player_asset("nds-touch.js")
    body = f'<main class="player-shell" data-player=\'{esc(json.dumps(config,ensure_ascii=False))}\'><section class="player-stage"><div id="game"></div><div id="tvPad" aria-label="Virtual controller"></div><div id="playerNotice" class="player-notice" role="status" aria-live="polite"></div><div id="loading" class="loading" role="status" aria-live="polite"><strong id="loadingText">Preparing</strong><div class="progress" role="progressbar" aria-label="Core download progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><i id="loadingBar"></i></div><span id="loadingPct">0%</span></div></section></main><script src="{ui_asset}" defer></script><script src="{runtime_asset}" defer></script><script src="{renderer_asset}" defer></script><script src="{nds_touch_asset}" defer></script><script src="{player_asset}" defer></script>'
    return layout("Core preload", body, lang, player=True)


def multiplayer_page(lang, slug=""):
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

    unavailable_panel = f'''<section class="mp-card mp-unavailable" id="mpUnavailable" hidden>
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
    return layout(tr(lang, "Chơi chung", "Multiplayer"), body, lang)


QR_MAX_TEXT = 512




def qr_svg(text, border=4):
    """Render ``text`` as a standalone SVG QR code.

    The output is a plain ``<svg>`` with a single module path: no scripts, no
    external references, no fonts, so it stays inside a strict CSP and can be
    embedded through ``img-src 'self'``.
    """
    if not text or len(text) > QR_MAX_TEXT:
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






def diagnostics_page(lang):
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
    return layout(tr(lang, "Chẩn đoán", "Diagnostics"), body, lang)


def licenses_page(lang):
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
    return layout(tr(lang, "Giấy phép", "Licenses"), body, lang)


def player_page(game, lang):
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
        game_settings = f'''<section class="player-settings-group player-game-settings"><header><strong>{tr(lang,"Trò chơi & save","Game & saves")}</strong><small>{tr(lang,"Trên thiết bị này","On this device")}</small></header><div class="player-panel-actions"><button id="saveState" type="button">{tr(lang,"Tải save state","Download save state")}</button><button id="loadState" type="button">{tr(lang,"Nạp save state","Load save state")}</button><input id="stateFile" type="file" accept=".state,.savestate,application/octet-stream" hidden></div></section>'''
        autosave_settings = f'''<section class="player-settings-group player-autosave-settings"><header><strong>{tr(lang,"Tự động lưu","Autosave")}</strong><small>{tr(lang,"Trên thiết bị này","On this device")}</small></header><label><span>{tr(lang,"Chế độ","Mode")}</span><select id="autosaveMode"><option value="off">{tr(lang,"Tắt","Off")}</option><option value="exit">{tr(lang,"Khi thoát game","On game exit")}</option><option value="30">{tr(lang,"Mỗi 30 giây","Every 30 seconds")}</option><option value="10">{tr(lang,"Mỗi 10 giây","Every 10 seconds")}</option><option value="5">{tr(lang,"Mỗi 5 giây","Every 5 seconds")}</option></select></label><small class="muted">{tr(lang,"Autosave dùng slot riêng, không thay thế save thủ công.","Autosave uses its own slot and never replaces a manual save state.")}</small></section>'''
        exit_settings = f'''<section class="player-settings-group player-exit-settings"><header><strong>{tr(lang,"Thoát game","Exit game")}</strong></header><p class="player-setting-copy">{tr(lang,"Dừng phiên giả lập và quay về thư viện.","Stop this emulation session and return to the library.")}</p><div class="player-panel-actions"><button id="exitGame" type="button">{tr(lang,"Thoát game","Exit game")}</button></div></section>'''
        multiplayer_button = f'<button id="playerMultiplayer" type="button">{tr(lang,"Chơi chung","Multiplayer")}</button>' if MULTIPLAYER_ENABLED else ""
        advanced_settings = f'''<section class="player-settings-group player-advanced-settings"><header><strong>{tr(lang,"Nâng cao","Advanced")}</strong></header><p class="player-setting-copy">{tr(lang,"Mở menu EmulatorJS để dùng các cài đặt core đã được hỗ trợ.","Open the EmulatorJS menu for its supported core settings.")}</p><div class="player-panel-actions">{multiplayer_button}<button id="emulatorMenu" type="button">{tr(lang,"Mở menu giả lập","Open emulator menu")}</button></div></section>'''
        slot_rows = "".join(f'<div class="save-slot" data-slot="{slot}"><strong>{tr(lang,"Slot","Slot")} {slot}</strong><small>{tr(lang,"Trống","Empty")}</small><button data-save-slot="{slot}">{tr(lang,"Lưu","Save")}</button><button data-load-slot="{slot}" disabled>{tr(lang,"Nạp","Load")}</button></div>' for slot in range(1, 11))
        auto_slot_row = f'<div class="save-slot save-slot-auto" data-auto-slot><strong>{tr(lang,"Tự động lưu","Autosave")}</strong><small>{tr(lang,"Trống","Empty")}</small><button data-save-auto>{tr(lang,"Lưu","Save")}</button><button data-load-auto disabled>{tr(lang,"Nạp","Load")}</button></div>'
        slot_panel = f'<section id="slotPanel" class="slot-panel" hidden role="dialog" aria-label="{tr(lang,"Save slot trên thiết bị này","Save slots on this device")}"><header><strong>{tr(lang,"Save slot trên thiết bị này","Save slots on this device")}</strong><button id="closeSlots" type="button">{tr(lang,"Đóng","Close")}</button></header>{auto_slot_row}{slot_rows}</section>'
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
{slot_panel}{pad_panel}{multiplayer_panel}</main>
<script src="{versioned_player_asset("player-ui.js")}" defer></script><script src="{versioned_player_asset("player-runtime.js")}" defer></script><script src="{versioned_player_asset("renderer-worker.js")}" defer></script><script src="{versioned_player_asset("nds-touch.js")}" defer></script><script src="{versioned_player_asset("local-save-recovery.js")}" defer></script><script src="{versioned_player_asset("player.js")}" defer></script>"""
    return layout(title, body, lang, player=True)


DASHBOARD_RANGES = (
    ("7", "7 days", 7),
    ("30", "30 days", 30),
    ("90", "90 days", 90),
    ("all", "All time", None),
)
DASHBOARD_DEFAULT_RANGE = "30"












BATCH_STATUS = {
    "draft": (0, 0, "Draft"),
    "testing": (1, 1, "Testing"),
    "release": (1, 0, "Release"),
}












def rate_allowed(ip, action, limit, window=600, subject=""):
    global RATE_LIMIT_MAX_WINDOW
    now = time.time()
    key = (rate_limit_hash(ip), action, str(subject))
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

    def common_headers(self, content_type, length=None, cache="no-store", csp=None, cross_origin_isolated=False):
        # The native support surface is the only cross-origin API: an allowlisted
        # app origin may read the capability and the submission receipt. Every
        # other response stays same-origin exactly as before.
        cors_origin = getattr(self, "_cors_origin", "")
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
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin" if cors_origin else "same-origin")
        if cross_origin_isolated:
            self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("X-Permitted-Cross-Domain-Policies", "none")
        if COOKIE_SECURE:
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        self.send_header("Content-Security-Policy", csp or "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'self'; worker-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'")
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
        # /download-app/source) and send_error. Draining the
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
        if urlparse(self.path).path not in SUPPORT_PATHS:
            return self.send_json({"error": "not found"}, 404)
        origin = self.support_origin()
        if not origin:
            return self.send_json({"error": "origin not allowed"}, 403)
        self._cors_origin = origin
        self.send_response(204)
        self.common_headers("text/plain; charset=utf-8", 0)
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
            svg = qr_svg(f"{scheme}://{host}/play/{slug}?room={code}")
        except ValueError:
            return self.send_json({"error": "invalid payload"}, 400)
        self.send_bytes(200, svg.encode("utf-8"), "image/svg+xml; charset=utf-8", cache="no-store")









    def diagnostics_snapshot(self):
        """Technical snapshot for the staging multiplayer service."""

        if not MULTIPLAYER_ENABLED:
            return self.send_json({"error": "not found"}, 404)
        self.send_json({
            "environment": ENVIRONMENT,
            "assetVersion": ASSET_VERSION,
            "buildId": RUNTIME_BUILD_ID,
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

    def ingest_bug_report(self, data):
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
            duplicate = conn.execute(
                "SELECT github_issue_number,github_issue_url FROM bug_reports WHERE fingerprint=? AND github_issue_url!='' ORDER BY created_at DESC LIMIT 1",
                (fingerprint,),
            ).fetchone()
            cur = conn.execute(
                """INSERT INTO bug_reports(user_id,fingerprint,report_schema_version,app_version,build_id,platform,
                   emulator_system,core_name,game_title,game_identifier,description,payload,status,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    None, fingerprint, report["reportSchemaVersion"], report["appVersion"], report["buildId"],
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
        """Ingest a rate-limited anonymous report using a one-time capability."""

        if not BUG_REPORT_ENABLED:
            return self.send_json({"error": "not found"}, 404)
        if self.support_capability_consume() is None:
            self.discard_request_body(BUG_REPORT_MAX_BYTES)
            return self.send_json({"error": "valid support capability required"}, 401)
        if not rate_allowed(self.client_address[0], "bug-report-ip", BUG_REPORT_RATE_LIMIT, BUG_REPORT_RATE_WINDOW):
            raise RateLimited("Too many bug reports from this network")
        data = self.read_json(BUG_REPORT_MAX_BYTES)
        self.send_json(self.ingest_bug_report(data), 201)



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
        if path == "/":
            origin = f"{self.request_origin()}"
            self.send_html(download_app_page(lang, origin))
        elif path == "/games":
            self.send_html(home_page(lang))
        elif path == "/api/library-version":
            with db() as conn:
                version = library_fingerprint(conn)
            self.send_json({"version": version})
        elif path == "/offline":
            self.send_html(offline_page(lang), player=bool(query.get("play", [""])[0] or query.get("rom", [""])[0]))
        elif path == "/multiplayer":
            if not MULTIPLAYER_ENABLED:
                self.send_html(status_page(404, lang), 404)
            else:
                self.send_html(multiplayer_page(lang, parse_qs(parsed.query).get("slug", [""])[0]))
        elif path == "/download-app":
            origin = f"{self.request_origin()}"
            self.send_html(download_app_page(lang, origin))
        elif path.startswith("/core-preload/"):
            system = path.rsplit("/", 1)[1]
            self.send_html(core_preload_page(system, lang), 200 if system in SYSTEMS and system != "html5" else 404, player=True)
        elif path.startswith("/game/"):
            game = self.find_game(path.split("/", 2)[2])
            self.send_html(game_page(game, lang) if game else status_page(404, lang), 200 if game else 404)
        elif path.startswith("/play/"):
            game = self.find_game(path.split("/", 2)[2])
            self.send_html(player_page(game, lang) if game else status_page(404, lang), 200 if game else 404, player=bool(game))
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
            match = re.fullmatch(r"/static/v/([a-f0-9]{12})/(offline\.js|player-ui\.js|player-runtime\.js|renderer-worker\.js|nds-touch\.js|local-save-recovery\.js|player\.js|site\.css)", path)
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
        elif path == "/health":
            self.send_json({"ok": True, "environment": ENVIRONMENT, "asset_version": ASSET_VERSION, "release_id": native_release_identity(), "time": int(time.time())})
        elif path == "/api/multiplayer/room":
            self.multiplayer_room_status()
        elif path == "/api/multiplayer/state":
            self.multiplayer_member_state()
        elif path == "/api/multiplayer/qr.svg":
            self.multiplayer_qr()
        elif path == "/api/diagnostics":
            self.diagnostics_snapshot()
        elif path == "/licenses":
            self.send_html(licenses_page(lang))
        elif path == "/licenses/gpl-3.0.txt":
            license_path = os.path.join(APP_DIR, "LICENSE")
            if not os.path.isfile(license_path):
                self.send_bytes(404, b"license not found\n", "text/plain; charset=utf-8")
            else:
                with open(license_path, "rb") as handle:
                    self.send_bytes(200, handle.read(), "text/plain; charset=utf-8")
        elif path == "/diagnostics":
            if not MULTIPLAYER_ENABLED:
                self.send_html(status_page(404, lang), 404)
            else:
                self.send_html(diagnostics_page(lang))
        else:
            if path.startswith("/api/") or path.startswith("/admin/api/"):
                self.send_json({"error": "not found"}, 404)
            else:
                self.send_html(status_page(404, lang), 404)

    do_HEAD = do_GET

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/bug-reports":
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
            else:
                self.send_json({"error": "not found"}, 404)
        except RateLimited as exc:
            self.send_json({"error": str(exc)}, 429)
        except netcode.RateLimitedError as exc:
            self.send_json({"error": str(exc)}, 429)
        except PermissionError as exc:
            self.send_json({"error": str(exc)}, 403)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, 400)
        except Exception:
            self.send_json({"error": "Request could not be processed"}, 400)


    def do_PUT(self):
        self.send_json({"error": "not found"}, 404)


    def do_DELETE(self):
        self.send_json({"error": "not found"}, 404)



if __name__ == "__main__":
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Vibe Coded Emulator listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()
