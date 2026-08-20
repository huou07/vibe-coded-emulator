#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import base64
import hashlib
import html
import json
import mimetypes
import os
import re
import secrets
import shutil
import sqlite3
import sys
import threading
import time
import unicodedata
import zipfile
from datetime import datetime
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import Request, urlopen


APP_DIR = os.path.abspath(os.environ.get("AN3_APP_DIR", os.path.dirname(__file__)))
DATA_DIR = os.path.abspath(os.environ.get("AN3_DATA_DIR", os.path.join(APP_DIR, "data")))
STATIC_DIR = os.path.join(APP_DIR, "static")


def static_asset_version():
    digest = hashlib.sha256()
    for name in sorted(os.listdir(STATIC_DIR)):
        path = os.path.join(STATIC_DIR, name)
        if not os.path.isfile(path):
            continue
        digest.update(name.encode("utf-8"))
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()[:12]


ASSET_VERSION = static_asset_version()
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
SITE_NAME = "Ăn 3 Tô Cơm"
MAX_JSON_BYTES = 1024 * 1024
ENVIRONMENT = os.environ.get("AN3_ENVIRONMENT", "production").strip().lower()
NDS_DEBUG_ALLOWED = ENVIRONMENT in {"staging", "development"}
AUTH_PEPPER = os.environ.get("AN3_AUTH_PEPPER", "")
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


def browser_rom_name(game):
    """Return the filename EmulatorJS should infer from the playable URL."""
    try:
        source = safe_data_path(ROM_DIR, game["rom_path"])
        if game["system"] not in {"gb", "gba", "nds"} or os.path.splitext(source)[1].lower() != ".zip" or not zipfile.is_zipfile(source):
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
            request = Request(url, headers={"User-Agent": "AN3Arcade/1.0", "Accept-Encoding": "identity"})
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


def db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
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
            CREATE TABLE IF NOT EXISTS page_views (
              id INTEGER PRIMARY KEY, visitor_hash TEXT NOT NULL, user_id INTEGER,
              path TEXT NOT NULL, created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS play_events (
              id INTEGER PRIMARY KEY, visitor_hash TEXT NOT NULL, user_id INTEGER,
              game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
              created_at INTEGER NOT NULL
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
            CREATE INDEX IF NOT EXISTS comments_game_idx ON comments(game_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS games_public_idx ON games(published, updated_at DESC);
            CREATE INDEX IF NOT EXISTS favorites_user_idx ON favorites(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS reports_status_idx ON reports(status, updated_at DESC);
            CREATE INDEX IF NOT EXISTS page_views_created_idx ON page_views(created_at DESC);
            CREATE INDEX IF NOT EXISTS play_events_created_idx ON play_events(created_at DESC);
            CREATE INDEX IF NOT EXISTS play_events_game_idx ON play_events(game_id, created_at DESC);
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
        defaults = {
            "maintainer_email": os.environ.get("AN3_MAINTAINER_EMAIL", "nguyen.tntl88@gmail.com"),
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


def clean_name(value):
    value = unicodedata.normalize("NFKC", str(value or "")).strip()
    if len(value) < 3 or len(value) > 32 or any(ord(ch) < 32 for ch in value):
        raise ValueError("Tên phải dài từ 3 đến 32 ký tự")
    return value


def clean_display_name(value):
    value = unicodedata.normalize("NFKC", str(value or "")).strip()
    if len(value) < 2 or len(value) > 40 or any(ord(ch) < 32 for ch in value):
        raise ValueError("Nickname phải dài từ 2 đến 40 ký tự")
    return value


def safe_next_path(value, fallback="/"):
    raw = str(value or "").strip()
    if not raw or not raw.startswith("/") or raw.startswith("//") or "\\" in raw or any(ord(ch) < 32 for ch in raw):
        return fallback
    parsed = urlparse(raw)
    if parsed.scheme or parsed.netloc:
        return fallback
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def validate_password(password, confirm, lang="vi"):
    if len(password) < 10 or len(password) > 200 or password != confirm:
        raise ValueError(tr(lang, "Mật khẩu phải có 10–200 ký tự và trùng khớp", "Passwords must match and contain 10–200 characters"))
    groups = sum(bool(re.search(pattern, password)) for pattern in (r"[a-z]", r"[A-Z]", r"\d", r"[^\w\s]"))
    if groups < 2:
        raise ValueError(tr(lang, "Mật khẩu cần dùng ít nhất hai loại ký tự", "Use at least two character types in the password"))


class RateLimited(PermissionError):
    pass


def auth_hash(value):
    return hashlib.sha256((AUTH_PEPPER + str(value)).encode("utf-8")).hexdigest()


def clean_contribution(body, maximum, kind):
    body = unicodedata.normalize("NFKC", str(body or "")).strip()
    if not body or len(body) > maximum or any(ord(char) < 32 and char not in "\n\t" for char in body):
        raise ValueError(f"{kind} must be 1-{maximum} characters")
    lowered = body.lower()
    if len(re.findall(r"(?:https?://|www\.)", lowered)) > 1 or re.search(r"(.)\1{11,}", lowered):
        raise ValueError("Nội dung bị hệ thống chống spam từ chối")
    compact = re.sub(r"\W+", "", lowered)
    if len(compact) >= 36 and len(set(compact)) <= 3:
        raise ValueError("Nội dung bị hệ thống chống spam từ chối")
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
            raise ValueError("Mỗi mạng xã hội cần có dạng Tên|https://url")
        label, url = (part.strip() for part in raw.split("|", 1))
        if not label or len(label) > 40 or not re.fullmatch(r"https?://[^\s]{1,500}", url):
            raise ValueError("Liên kết mạng xã hội không hợp lệ")
        lines.append(f"{label}|{url}")
    if len(lines) > 8:
        raise ValueError("Tối đa 8 liên kết mạng xã hội")
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
    query = parse_qs(urlparse(handler.path).query)
    requested = query.get("lang", [""])[0]
    if requested in ("vi", "en"):
        return requested
    jar = cookies.SimpleCookie(handler.headers.get("Cookie", ""))
    return jar.get("lang").value if jar.get("lang") and jar.get("lang").value in ("vi", "en") else "vi"


def tr(lang, vi, en):
    return en if lang == "en" else vi


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


def layout(title, content, lang, user=None, csrf="", player=False, offline=False, guide_trigger=False, library=False):
    with db() as conn:
        settings = site_settings(conn)
    account = ""
    if user:
        admin = '<a href="/admin">Dashboard</a>' if user["role"] == "admin" else ""
        account = f'{admin}<a class="account" href="/account">{esc(display_name(user))}</a><button class="link-button" data-action="logout">{tr(lang,"Đăng xuất","Log out")}</button>'
    else:
        account = f'<a href="/login">{tr(lang,"Đăng nhập","Log in")}</a><a href="/register">{tr(lang,"Tạo tài khoản","Register")}</a>'
    guide_nav = f'<button id="guideButton" class="link-button" type="button">{tr(lang,"Hướng dẫn","How it works")}</button>' if guide_trigger else ""
    mode_label = tr(lang,"Trực tuyến","Online") if offline else "Offline"
    mode_aria = tr(lang,"Mở thư viện trực tuyến","Open online library") if offline else tr(lang,"Mở thư viện ngoại tuyến","Open offline library")
    mode_icon = "" if offline else '<span class="ui-mask ui-wifi-off" aria-hidden="true"></span>'
    mode = f'<a id="modeSwitch" class="mode-switch" href="{"/" if offline else "/offline"}" aria-label="{mode_aria}">{mode_icon}<span>{mode_label}</span></a>'
    contacts = []
    if settings.get("maintainer_email"):
        contacts.append(f'<a href="mailto:{esc(settings["maintainer_email"])}">{esc(settings["maintainer_email"])}</a>')
    if settings.get("maintainer_facebook"):
        contacts.append(f'<a href="{esc(settings["maintainer_facebook"])}" rel="me noopener noreferrer" target="_blank">Facebook</a>')
    contacts.extend(f'<a href="{esc(url)}" rel="me noopener noreferrer" target="_blank">{esc(label)}</a>' for label, url in parse_contact_links(settings.get("maintainer_links")))
    contact_block = f'<div class="contact-links"><span>{tr(lang,"Liên hệ maintain:","Maintainer contact:")}</span>{"".join(contacts)}</div>' if contacts else ""
    stage_badge = '<span class="stage-badge">STAGING</span>' if ENVIRONMENT == "staging" else ""
    welcome = "" if player else f'''<section id="welcomeGuide" class="welcome-guide" hidden role="dialog" aria-modal="true" aria-labelledby="welcomeTitle" aria-describedby="welcomeSummary"><div class="welcome-panel"><button id="closeGuide" class="button guide-close" type="button">{tr(lang,"Đóng","Close")}</button><p class="eyebrow">{esc(SITE_NAME)}</p><h2 id="welcomeTitle">{tr(lang,"Bắt đầu chơi theo cách của bạn","Start playing your way")}</h2><p id="welcomeSummary" class="muted">{tr(lang,"Kho game chung, ROM riêng trên thiết bị và các công cụ thiết yếu nằm trong một nơi.","The shared library, device-only ROMs, and essential player tools live in one place.")}</p><div class="guide-grid"><p><strong>1.</strong> {tr(lang,"Chọn Trực tuyến để xem kho chung, hoặc Ngoại tuyến để mở ROM đã lưu trên thiết bị này.","Choose Online for the shared library, or Offline for ROMs saved on this device.")}</p><p><strong>2.</strong> {tr(lang,"Mở trang game để xem thông tin, sau đó chọn Chơi ngay.","Open a game for details, then choose Play now.")}</p><p><strong>3.</strong> {tr(lang,"Trong player, dùng thanh công cụ cho fullscreen, save state và bàn phím ảo.","In the player, use the toolbar for fullscreen, save states, and virtual controls.")}</p><p><strong>4.</strong> {tr(lang,"Đăng nhập để đánh giá, bình luận, báo lỗi hoặc lưu yêu thích.","Log in to rate, comment, report issues, or save favorites.")}</p></div><small>{tr(lang,"Bạn có thể đọc theo nhịp của mình và đóng khi sẵn sàng.","Take your time and close this guide when you are ready.")}</small></div></section>'''
    body_classes = []
    if player:
        body_classes.append("player-page")
    if library:
        body_classes.append("library-shell")
    return f"""<!doctype html>
<html lang="{lang}" class="{'library-root' if library else ''}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="csrf-token" content="{esc(csrf)}"><meta name="theme-color" content="#101311"><title>{esc(title)} · {esc(SITE_NAME)}</title>
<link rel="manifest" href="/static/manifest.webmanifest?v={ASSET_VERSION}">
<link rel="stylesheet" href="/static/site.css?v={ASSET_VERSION}"></head><body class="{' '.join(body_classes)}">
<header class="site-header"><a class="brand" href="/">{esc(SITE_NAME)}</a>{stage_badge}<nav id="siteNav" class="site-nav"><a href="/">{tr(lang,"Trò chơi","Games")}</a>{guide_nav}{account}<a class="lang" href="?lang={'vi' if lang == 'en' else 'en'}">{'VI' if lang == 'en' else 'EN'}</a></nav><div class="header-actions">{mode}<button id="navToggle" class="nav-toggle" type="button" aria-label="{tr(lang,'Mở menu','Open menu')}" aria-controls="siteNav" aria-expanded="false"><span class="ui-mask ui-menu" aria-hidden="true"></span><span class="nav-toggle-label">{tr(lang,"Menu","Menu")}</span></button></div></header>
{content}
<footer class="site-footer"><div><strong>{esc(SITE_NAME)}</strong><span>{tr(lang,"Game chạy trên phần cứng của thiết bị người chơi.","Games run on the player's device.")}</span><span>design by: Tạm gọi là công tử</span></div>{contact_block}
<div class="credits"><span>{tr(lang,"Công cụ và nguồn mở:","Tools and open source:")}</span><a href="https://emulatorjs.org/">EmulatorJS</a><a href="https://www.retroarch.com/">RetroArch</a><a href="https://github.com/mgba-emu/mgba">mGBA</a><a href="https://melonds.kuribo64.net/">melonDS</a><a href="https://github.com/azahar-emu/azahar">Azahar</a><a href="https://www.python.org/">Python</a><a href="https://sqlite.org/">SQLite</a></div></footer>
{welcome}<div id="toast" role="status"></div><script src="/static/site.js?v={ASSET_VERSION}" defer></script></body></html>"""


def status_page(code, lang, user=None, csrf=""):
    if code == 403:
        title = tr(lang, "Không có quyền truy cập", "Access restricted")
        message = tr(lang, "Dashboard này chỉ dành cho quản trị viên. Tài khoản hiện tại của bạn vẫn có thể duyệt và chơi game.", "This dashboard is available to administrators only. Your current account can still browse and play games.")
    else:
        title = tr(lang, "Không tìm thấy trang", "Page not found")
        message = tr(lang, "Liên kết này có thể đã thay đổi hoặc game không còn ở địa chỉ này.", "This link may have changed, or the game is no longer available at this address.")
    body = f'''<main class="page status-page"><section class="status-card" aria-labelledby="statusTitle"><p class="eyebrow">{tr(lang,'Mã trạng thái','Status code')} {code}</p><h1 id="statusTitle">{title}</h1><p>{message}</p><div class="status-actions"><a class="button primary" href="/">{tr(lang,'Duyệt thư viện','Browse library')}</a><a class="button" href="/offline">{tr(lang,'Mở game trên thiết bị','Open device games')}</a></div></section></main>'''
    return layout(f"{code} · {title}", body, lang, user, csrf)


def home_page(lang, user, csrf):
    with db() as conn:
        games = conn.execute(
            """SELECT g.*, COALESCE(AVG(r.value),0) rating, COUNT(r.value) rating_count,
                      (SELECT COUNT(*) FROM play_events p WHERE p.game_id=g.id) play_count
               FROM games g LEFT JOIN ratings r ON r.game_id=g.id
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
    body = f"""<main class="page library-page"><section class="library-head"><div><p class="eyebrow">an3tocom.space</p><h1>{tr(lang,"Thư viện trò chơi","Game library")}</h1><p class="muted">{tr(lang,"Chọn game và chơi ngay trên thiết bị của bạn.","Choose a game and play it on your own device.")}</p></div></section>
<section class="library-toolbar" aria-label="{tr(lang,'Tìm và lọc trò chơi','Find and filter games')}"><label class="search" for="gameSearch"><span>{tr(lang,'Tìm trò chơi','Search games')}</span><span class="search-field"><span class="ui-mask ui-search" aria-hidden="true"></span><input id="gameSearch" type="search" placeholder="{tr(lang,'Tìm trò chơi','Search games')}" autocomplete="off"><button id="clearSearch" class="search-clear" type="button" hidden>{tr(lang,'Xóa','Clear')}</button></span></label></section>
<div id="gameGrid" class="game-library" data-library-version="{version}">{populated_library if games else empty}</div></main>"""
    return layout(tr(lang, "Trò chơi", "Games"), body, lang, user, csrf, guide_trigger=True, library=True)


def auth_page(kind, lang, user, csrf, error="", next_path="/"):
    register = kind == "register"
    next_path = safe_next_path(next_path)
    heading = tr(lang, "Tạo tài khoản", "Create account") if register else tr(lang, "Đăng nhập", "Log in")
    nickname = f'<label>{tr(lang,"Nickname hiển thị","Display nickname")}<input name="display_name" minlength="2" maxlength="40" required autocomplete="nickname"></label>' if register else ""
    password_rules = f'<p id="passwordRules" class="field-help">{tr(lang,"Dùng 10–200 ký tự và ít nhất hai loại: chữ thường, chữ hoa, số hoặc ký hiệu.","Use 10–200 characters and at least two types: lowercase, uppercase, numbers, or symbols.")}</p>' if register else ""
    password_describedby = ' aria-describedby="passwordRules"' if register else ""
    confirm = f'<label>{tr(lang,"Nhập lại mật khẩu","Confirm password")}<input name="confirm" type="password" minlength="10" maxlength="200" required autocomplete="new-password" aria-describedby="passwordRules"></label>' if register else ""
    next_query = f'?next={quote(next_path, safe="")}' if next_path != "/" else ""
    switch = f'<p class="auth-switch"><a href="/{"login" if register else "register"}{next_query}">{tr(lang,"Đã có tài khoản? Đăng nhập","Already registered? Log in") if register else tr(lang,"Chưa có tài khoản? Tạo ngay","No account? Create one")}</a></p>'
    error_hidden = "" if error else " hidden"
    body = f"""<main class="auth-shell"><section class="auth-panel"><p class="eyebrow">{esc(SITE_NAME)} ID</p><h1>{heading}</h1>
<form id="authForm" data-kind="{kind}" aria-describedby="formError"><input name="next" type="hidden" value="{esc(next_path)}"><label>{tr(lang,"Tên đăng nhập","Username")}<input name="name" minlength="3" maxlength="32" required autocomplete="username"></label>{nickname}
<label>{tr(lang,"Mật khẩu","Password")}<input name="password" type="password" minlength="10" maxlength="200" required autocomplete="{'new-password' if register else 'current-password'}"{password_describedby}></label>{password_rules}{confirm}
<button class="button primary" type="submit"><span class="auth-submit-label">{heading}</span></button><div id="authProgress" class="auth-progress" hidden role="status" aria-live="polite"><span id="authProgressLabel"></span><div role="progressbar" aria-label="{tr(lang,'Tiến trình xác thực','Authentication progress')}"><i></i></div></div><p class="form-error" id="formError" role="alert" aria-live="assertive" tabindex="-1"{error_hidden}>{esc(error)}</p></form>{switch}</section></main>"""
    return layout(heading, body, lang, user, csrf)


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
<div class="detail-actions"><a class="button primary" href="/play/{esc(game['slug'])}">{tr(lang,"Chơi ngay","Play now")}</a><a class="button" href="/download/{esc(game['slug'])}">{tr(lang,"Tải game","Download game")} · {format_size(game['file_size'])}</a>{favorite_button}</div>
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
    body = f'''<main id="offlineApp" class="page offline-page"><section class="library-head"><div><p class="eyebrow">AN3 ARCADE</p><h1>{tr(lang,"Kho ngoại tuyến","Offline library")}</h1><p class="muted">{tr(lang,"Liên kết Trực tuyến phía trên chỉ quay lại kho chung; trạng thái bên dưới mô tả thiết bị này.","The Online link above only returns to the shared library; the facts below describe this device.")}</p></div></section>
<section class="offline-readiness" aria-labelledby="offlineReadinessTitle"><div class="section-title"><div><p class="eyebrow">{tr(lang,"Trạng thái thiết bị","Device facts")}</p><h2 id="offlineReadinessTitle">{tr(lang,"Sẵn sàng ngoại tuyến","Offline readiness")}</h2></div></div><div class="offline-facts"><div><span>{tr(lang,"Kết nối","Connection")}</span><strong id="offlineNetworkState">{tr(lang,"Đang kiểm tra","Checking")}</strong><small>{tr(lang,"Chỉ là trạng thái mạng do trình duyệt báo.","Browser-reported network state only.")}</small></div><div><span>{tr(lang,"Ngữ cảnh an toàn","Secure context")}</span><strong id="offlineSecureState">{tr(lang,"Đang kiểm tra","Checking")}</strong><small>HTTPS / localhost</small></div><div><span>{tr(lang,"Vỏ ứng dụng","App shell")}</span><strong id="offlineShellState">{tr(lang,"Đang kiểm tra","Checking")}</strong><small>{tr(lang,"Tách biệt với game và core.","Separate from games and cores.")}</small></div><div><span>{tr(lang,"Game cục bộ","Local games")}</span><strong id="offlineGameCount">0</strong><small>{tr(lang,"ROM chỉ lưu trong trình duyệt này.","ROMs stored only in this browser.")}</small></div><div><span>{tr(lang,"Core giả lập","Emulator cores")}</span><strong id="offlineCoreState">{tr(lang,"Chưa kiểm tra","Not checked")}</strong><small>{tr(lang,"Mở trình quản lý core để xác minh.","Open Core manager to verify.")}</small></div></div></section>
<section class="offline-library"><div class="section-title"><div><p class="eyebrow">{tr(lang,"Sẵn sàng chơi","Ready to play")}</p><h2>{tr(lang,"Game trên máy này","Games on this device")}</h2></div></div><div id="offlineGameGrid" class="offline-system-list" aria-live="polite"></div></section>
<section class="offline-upload" aria-labelledby="offlineAddTitle"><div class="section-title"><div><p class="eyebrow">{tr(lang,"ROM riêng tư","Private ROM")}</p><h2 id="offlineAddTitle">{tr(lang,"Thêm game vào thiết bị","Add a game to this device")}</h2></div></div><form id="offlineGameForm"><label>{tr(lang,"Tệp game","Game file")}<input id="offlineFile" name="file" type="file" required></label><label>{tr(lang,"Tên game","Game title")}<input id="offlineTitle" name="title" maxlength="120" required></label><label>{tr(lang,"Hệ máy","System")}<select id="offlineSystem" name="system"></select></label><button class="button primary" type="submit">{tr(lang,"Thêm vào máy này","Add to this device")}</button></form><p id="offlineDetection" class="muted" role="status"></p></section>
<details id="coreManager" class="core-preload"><summary><span><strong>{tr(lang,"Trình quản lý core","Core manager")}</strong><small>{tr(lang,"Kiểm tra, tải hoặc xóa core theo từng hệ máy.","Verify, download, or remove cores for individual systems.")}</small></span><span aria-hidden="true">{tr(lang,"Mở","Open")}</span></summary><div class="core-preload-body"><p class="muted">{tr(lang,"Core đã tải không có nghĩa ROM đã được lưu; hãy kiểm tra cả danh sách game phía trên.","A downloaded core does not mean a ROM is stored; verify the game list above as well.")}</p><div id="corePreloadGrid" class="core-preload-grid"></div><p id="corePreloadStatus" class="muted" role="status"></p></div></details></main><script src="/static/offline.js?v={ASSET_VERSION}" defer></script><script src="/static/player.js?v={ASSET_VERSION}" defer></script>'''
    return layout(tr(lang, "Ngoại tuyến", "Offline"), body, lang, user, csrf, offline=True)


def core_preload_page(system, lang):
    if system not in SYSTEMS or system == "html5":
        return status_page(404, lang)
    config = {"mode": "preload", "title": "Core preload", "slug": f"core-preload-{system}", "system": system, "channel": SYSTEMS[system][1], "lang": lang}
    body = f'<main class="player-shell" data-player=\'{esc(json.dumps(config,ensure_ascii=False))}\'><section class="player-stage"><div id="game"></div><div id="tvPad" aria-label="Virtual controller"></div><div id="playerNotice" class="player-notice" role="status" aria-live="polite"></div><div id="loading" class="loading" role="status" aria-live="polite"><strong id="loadingText">Preparing</strong><div class="progress" role="progressbar" aria-label="Core download progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><i id="loadingBar"></i></div><span id="loadingPct">0%</span></div></section></main><script src="/static/player.js?v={ASSET_VERSION}" defer></script>'
    return layout("Core preload", body, lang, None, "", player=True)


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
        toolbar_extra = f'<button id="toggleTouch" class="touch-toggle" type="button" aria-pressed="true" title="{tr(lang,"Ẩn phím ảo","Hide virtual controls")}" aria-label="{tr(lang,"Bật hoặc tắt phím ảo","Toggle virtual controls")}">Touch</button><button id="slotMenu" type="button" aria-expanded="false" title="{tr(lang,"Save slot","Save slots")}" aria-label="{tr(lang,"Mở save slot trên thiết bị","Open save slots on this device")}">{icon("save")}</button><button id="playerControls" type="button" aria-expanded="false" title="{tr(lang,"Tùy chọn khác","More options")}" aria-label="{tr(lang,"Mở tùy chọn trình phát","Open player options")}">{icon("more")}</button>'
        speed_settings = f'''<section class="player-settings-group player-speed-settings"><header><strong>{tr(lang,"Tốc độ","Speed")}</strong><small>{tr(lang,"Chỉ trong phiên","Session only")}</small></header><div class="player-speed-controls" role="group" aria-label="{tr(lang,"Tốc độ trò chơi","Game speed")}"><button id="speedDown" type="button" aria-label="{tr(lang,"Chậm hơn","Slower")}">−</button><output id="speedValue" aria-live="polite">1×</output><button id="speedUp" type="button" aria-label="{tr(lang,"Nhanh hơn","Faster")}">+</button></div><small id="speedHint" class="muted">{tr(lang,"Điều chỉnh tốc độ hoạt động sau khi game khởi động.","Speed controls become available after the game starts.")}</small></section>''' if game["system"] in {"gba", "nds"} else ""
        state_buttons = f'{speed_settings}<div class="player-panel-actions"><button id="emulatorMenu" type="button">{tr(lang,"Mở menu giả lập","Open emulator menu")}</button><button id="saveState" type="button">{tr(lang,"Tải save state","Download save state")}</button><button id="loadState" type="button">{tr(lang,"Nạp save state","Load save state")}</button><input id="stateFile" type="file" accept=".state,.savestate,application/octet-stream" hidden></div>'
        slot_rows = "".join(f'<div class="save-slot" data-slot="{slot}"><strong>{tr(lang,"Slot","Slot")} {slot}</strong><small>{tr(lang,"Trống","Empty")}</small><button data-save-slot="{slot}">{tr(lang,"Lưu","Save")}</button><button data-load-slot="{slot}" disabled>{tr(lang,"Nạp","Load")}</button></div>' for slot in range(1, 6))
        slot_panel = f'<section id="slotPanel" class="slot-panel" hidden role="dialog" aria-label="{tr(lang,"Save slot trên thiết bị này","Save slots on this device")}"><header><strong>{tr(lang,"Save slot trên thiết bị này","Save slots on this device")}</strong><button id="closeSlots" type="button">{tr(lang,"Đóng","Close")}</button></header>{slot_rows}</section>'
        pad_controls = [("dpad", "D-pad"), ("a", "A"), ("b", "B"), ("start", "Start"), ("select", "Select")]
        if game["system"] in {"gba", "nds"}:
            pad_controls.extend([("l", "L"), ("r", "R")])
        if game["system"] == "nds":
            pad_controls.extend([("x", "X"), ("y", "Y")])
        pad_options = "".join(f'<option value="{control}">{label}</option>' for control, label in pad_controls)
        renderer_setting = f'<label><span>{tr(lang,"Trình dựng NDS","NDS renderer")}</span><select id="performanceRenderer"><option value="native">{tr(lang,"Mặc định của core","Core default")}</option><option value="legacy">{tr(lang,"Tương thích / ít yêu cầu hơn","Compatibility / lower demand")}</option></select></label>' if game["system"] == "nds" else ""
        performance_settings = f'''<section class="player-settings-group player-performance-settings"><header><strong>{tr(lang,"Hiệu năng","Performance")}</strong><small id="performanceRecommendation"></small></header><p class="player-setting-copy">{tr(lang,"Khuyến nghị cho thiết bị này:","Recommended for this device:")} <strong id="recommendedPerformanceProfile"></strong></p><div class="performance-profile-options" role="radiogroup" aria-label="{tr(lang,"Hồ sơ hiệu năng","Performance profile")}"><label><input type="radio" name="performanceProfile" value="auto"> {tr(lang,"Dùng cài đặt khuyến nghị","Use recommended settings")}</label><label><input type="radio" name="performanceProfile" value="low"> {tr(lang,"Máy yếu / Tiết kiệm pin","Low-end / Battery")}</label><label><input type="radio" name="performanceProfile" value="balanced"> {tr(lang,"Cân bằng","Balanced")}</label><label><input type="radio" name="performanceProfile" value="quality"> {tr(lang,"Chất lượng","Quality")}</label><label><input type="radio" name="performanceProfile" value="custom"> {tr(lang,"Tùy chỉnh","Custom")}</label></div><div id="performanceCustomOptions" class="player-performance-custom" hidden>{renderer_setting}</div><div class="player-settings-actions"><button id="useRecommended" type="button">{tr(lang,"Đặt lại theo khuyến nghị","Use recommended settings")}</button><button id="applyPerformanceProfile" type="button">{tr(lang,"Áp dụng và khởi động lại","Apply and restart")}</button></div><small id="performanceProfileHint" class="muted"></small></section>'''
        pad_settings = f'''<section class="player-pad-settings"><header><strong>{tr(lang,"Phím ảo","Virtual controls")}</strong></header><label><span>{tr(lang,"Kích thước chung","Overall size")} <output id="padGlobalScaleValue">100%</output></span><input id="padGlobalScale" type="range" min="70" max="100" step="1" value="100"></label><small id="padGlobalScaleHint" class="muted">{tr(lang,"Mức tối đa giữ nguyên bố cục đã duyệt để tránh chồng phím trên màn hình hẹp.","The maximum keeps the approved layout from overlapping on narrow screens.")}</small><div><button id="resetPadGlobalScale" type="button">{tr(lang,"Đặt lại kích thước chung","Reset overall size")}</button></div><details class="player-pad-advanced"><summary>{tr(lang,"Kích thước từng phím","Individual control sizes")}</summary><p class="player-setting-copy">{tr(lang,"Tỷ lệ tính theo kích thước mặc định của từng phím. Không thể lưu mức làm phím chồng nhau hoặc ra ngoài màn hình.","Sizes are relative to each control’s approved default. Unsafe overlap and off-screen sizes are not saved.")}</p><label><span>{tr(lang,"Phím cần chỉnh","Control to resize")}</span><select id="padTarget">{pad_options}</select></label><label><span>{tr(lang,"Kích thước tương đối","Relative size")} <output id="padSizeValue">100%</output></span><input id="padSize" type="range" min="50" max="200" step="1" value="100"></label><small id="padSizeHint" class="muted"></small><div class="player-pad-button-actions"><button id="resetPadTarget" type="button">{tr(lang,"Đặt lại phím này","Reset this control")}</button><button id="resetPadSizes" type="button">{tr(lang,"Đặt lại từng phím","Reset all individual sizes")}</button></div></details><label><span>{tr(lang,"Độ mờ","Opacity")}</span><input id="padOpacity" type="range" min="30" max="100" step="1"></label><div class="player-pad-actions"><button id="editPad" type="button">{tr(lang,"Kéo thả","Move")}</button><button id="resetPadLayout" type="button">{tr(lang,"Đặt lại bố cục này","Reset this layout")}</button><button id="resetPad" type="button">{tr(lang,"Đặt lại tất cả phím ảo","Reset all virtual controls")}</button></div></section>''' if game["system"] in {"gb", "gba", "nds"} else ""
        pad_panel = f'<section id="padPanel" class="pad-panel" role="dialog" aria-label="{tr(lang,"Tùy chọn trình phát","Player options")}"><header><strong>{tr(lang,"Tùy chọn trình phát","Player options")}</strong><button id="closePad" type="button">{tr(lang,"Đóng","Close")}</button></header>{performance_settings}{state_buttons}{pad_settings}</section>'
        mode = "emulator"
    config = {
        "mode": mode, "title": title, "slug": game["slug"], "system": game["system"],
        "romUrl": f"/game-file/{game['slug']}/{quote(browser_rom_name(game))}", "channel": SYSTEMS[game["system"]][1],
        "downloadName": game["rom_name"], "lang": lang, "ndsDebugAllowed": NDS_DEBUG_ALLOWED,
    }
    back_path = f"/game/{game['slug']}"
    body = f"""<main class="player-shell" data-player='{esc(json.dumps(config,ensure_ascii=False))}'>
<div class="player-toolbar" role="toolbar" aria-label="{tr(lang,'Điều khiển trình phát','Player controls')}"><a class="player-back" href="{back_path}" title="{tr(lang,'Quay lại','Back')}" aria-label="{tr(lang,'Quay lại trang game','Back to game details')}">{icon("arrow-left")}</a><span class="player-title">{esc(title)}</span><div class="player-toolbar-actions"><button id="fullscreen" type="button" title="{tr(lang,'Toàn màn hình','Fullscreen')}" aria-label="{tr(lang,'Toàn màn hình','Fullscreen')}">{icon("maximize")}</button>{toolbar_extra}</div></div>
<section class="player-stage player-stage-ui">{game_area}<div class="player-status"><span class="player-runtime-state"><i aria-hidden="true"></i><span id="playerStatusText">{tr(lang,'Đang chuẩn bị','Preparing')}</span></span><span id="playerSaveStatus" class="player-save-state">{tr(lang,'Chưa có save trên thiết bị','No save on this device')}</span><div id="playerNotice" class="player-notice" role="status" aria-live="polite"></div></div><div id="loading" class="loading" role="status" aria-live="polite"><strong id="loadingText">{tr(lang,'Đang chuẩn bị','Preparing')}</strong><div class="progress" role="progressbar" aria-label="{tr(lang,'Tiến trình khởi động','Startup progress')}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><i id="loadingBar"></i></div><span id="loadingPct">0%</span></div></section>
{slot_panel}{pad_panel}</main>
<script src="/static/player.js?v={ASSET_VERSION}" defer></script>"""
    return layout(title, body, lang, user, csrf, player=True)


def dashboard_analytics(conn):
    now = int(time.time())
    start = now - 13 * 86400
    days = [(datetime.fromtimestamp(now - offset * 86400).strftime("%Y-%m-%d"), 0, 0) for offset in range(13, -1, -1)]
    visits = {day: 0 for day, _, _ in days}
    plays = {day: 0 for day, _, _ in days}
    for row in conn.execute("SELECT strftime('%Y-%m-%d',created_at,'unixepoch','localtime') AS day,COUNT(*) AS count FROM page_views WHERE created_at>=? GROUP BY day", (start,)):
        visits[row["day"]] = int(row["count"])
    for row in conn.execute("SELECT strftime('%Y-%m-%d',created_at,'unixepoch','localtime') AS day,COUNT(*) AS count FROM play_events WHERE created_at>=? GROUP BY day", (start,)):
        plays[row["day"]] = int(row["count"])
    series = [(day, visits.get(day, 0), plays.get(day, 0)) for day, _, _ in days]
    totals = conn.execute("""SELECT
        (SELECT COUNT(*) FROM page_views) AS visits,
        (SELECT COUNT(DISTINCT visitor_hash) FROM page_views) AS visitors,
        (SELECT COUNT(DISTINCT visitor_hash) FROM play_events) AS players,
        (SELECT COUNT(DISTINCT visitor_hash) FROM play_events WHERE created_at>=?) AS players_30d""", (now - 30 * 86400,)).fetchone()
    top_games = conn.execute("""SELECT g.title_vi,g.slug,COUNT(p.id) AS plays
        FROM games g JOIN play_events p ON p.game_id=g.id GROUP BY g.id
        ORDER BY plays DESC,g.title_vi COLLATE NOCASE LIMIT 7""").fetchall()
    return totals, series, top_games


def admin_page(lang, user, csrf, edit_id=None):
    with db() as conn:
        games = conn.execute("SELECT * FROM games ORDER BY updated_at DESC").fetchall()
        editing = conn.execute("SELECT * FROM games WHERE id=?", (edit_id,)).fetchone() if edit_id else None
        users = conn.execute("SELECT id,name,display_name,role,created_at FROM users ORDER BY role DESC, name COLLATE NOCASE").fetchall()
        reports = conn.execute(
            """SELECT r.*,COALESCE(NULLIF(u.display_name,''),u.name) AS reporter,g.title_vi,g.slug FROM reports r
               JOIN users u ON u.id=r.user_id JOIN games g ON g.id=r.game_id
               ORDER BY CASE r.status WHEN 'open' THEN 0 ELSE 1 END, r.updated_at DESC LIMIT 80"""
        ).fetchall()
        settings = site_settings(conn)
        totals, series, top_games = dashboard_analytics(conn)
    t = lambda vi, en: tr(lang, vi, en)
    maximum = max([1] + [max(visits, plays) for _, visits, plays in series])
    chart_rows = "".join(
        f'<tr><th scope="row">{esc(day[5:])}</th><td><progress class="chart-progress chart-visits" max="{maximum}" value="{visits}" aria-label="{esc(day)}: {visits} {t("lượt truy cập", "visits")}"></progress><span>{visits}</span></td><td><progress class="chart-progress chart-plays" max="{maximum}" value="{plays}" aria-label="{esc(day)}: {plays} {t("lượt chơi", "plays")}"></progress><span>{plays}</span></td></tr>'
        for day, visits, plays in series
    )
    top_rows = "".join(f'<li><a href="/game/{esc(item["slug"])}">{esc(item["title_vi"])}</a><strong>{item["plays"]}</strong></li>' for item in top_games)
    auto_selected = " selected" if not editing else ""
    options = f'<option value="auto"{auto_selected}>Tự động nhận diện / Auto detect</option>' + "".join(f'<option value="{esc(key)}"{" selected" if editing and editing["system"]==key else ""}>{esc(label[0])}</option>' for key, label in SYSTEMS.items())
    def game_status(game):
        labels = [t("Phát hành", "Release") if game["published"] else "Draft"]
        if game["experimental"]:
            labels.append("Testing")
        return " · ".join(labels)
    rows = "".join(f'<tr><td><a href="/game/{esc(g["slug"])}">{esc(g["title_vi"])}</a></td><td>{esc(SYSTEMS[g["system"]][0])}</td><td>{game_status(g)}</td><td>{format_size(g["file_size"])}</td><td><div class="table-actions"><a href="/play/{esc(g["slug"])}">{t("Chơi","Play")}</a><a href="/admin/game/{g["id"]}">{t("Sửa","Edit")}</a><button class="button danger" type="button" data-delete-game="{g["id"]}">{t("Xóa","Delete")}</button></div></td></tr>' for g in games)
    value = lambda key: esc(editing[key] if editing else "")
    checked = lambda key: " checked" if editing and editing[key] else ""
    user_rows = "".join(
        f'''<tr><td>{esc(item['name'])}</td><td>{esc(item['role'])}</td><td><form class="user-display-name" data-user-id="{item['id']}"><input name="display_name" value="{esc(item['display_name'] or item['name'])}" maxlength="40" aria-label="Display name"><button class="button" type="submit">Save</button></form></td></tr>'''
        for item in users
    )
    report_rows = "".join(
        f'''<article class="admin-report" data-report-id="{item['id']}"><header><strong>{esc(item['title_vi'])}</strong><span>{esc(item['category'])}</span><time>{datetime.fromtimestamp(item['created_at']).strftime('%Y-%m-%d %H:%M')}</time></header><p>{esc(item['body'])}</p><footer><span>{esc(item['reporter'])}</span><label>{t('Trạng thái','Status')}<select data-report-status aria-label="{t('Trạng thái báo lỗi','Issue report status')}"><option value="open"{' selected' if item['status']=='open' else ''}>open</option><option value="resolved"{' selected' if item['status']=='resolved' else ''}>resolved</option></select></label></footer></article>'''
        for item in reports
    )
    body = f"""<main class="page admin-page"><section class="admin-head"><div><p class="eyebrow">ADMIN ONLY</p><h1>Dashboard</h1></div><span>{len(games)} games</span></section>
<nav class="admin-task-nav" aria-label="{t('Tác vụ quản trị','Admin tasks')}"><a href="#adminOverview">{t('Tổng quan','Overview')}</a><a href="#gameForm">{t('Thêm hoặc sửa game','Add or edit game')}</a><a href="#adminLibrary">{t('Thư viện','Library')}</a><a href="#adminOperations">{t('Tài khoản và báo lỗi','Accounts and reports')}</a></nav>
<section id="adminOverview" class="analytics"><div class="stats-overview"><div><span>{t('Lượt truy cập','Visits')}</span><strong>{totals['visits']}</strong></div><div><span>{t('Khách riêng biệt','Unique visitors')}</span><strong>{totals['visitors']}</strong></div><div><span>{t('Người chơi','Players')}</span><strong>{totals['players']}</strong><small>{totals['players_30d']} / 30 {t('ngày','days')}</small></div></div><div class="analytics-grid"><section><header><h2>{t('Truy cập và lượt chơi','Visits and plays')}</h2><span>14 {t('ngày','days')}</span></header><div class="table-wrap stats-table-wrap"><table class="stats-table"><thead><tr><th>{t('Ngày','Day')}</th><th>{t('Lượt truy cập','Visits')}</th><th>{t('Lượt chơi','Plays')}</th></tr></thead><tbody>{chart_rows}</tbody></table></div></section><section class="top-games"><header><h2>{t('Game được chơi nhiều','Most played games')}</h2><span>{t('lượt chơi','plays')}</span></header><ol>{top_rows or f'<li class="muted">{t("Chưa có dữ liệu.","No data yet.")}</li>'}</ol></section></div></section>
<section id="adminBatch" class="admin-bulk-upload admin-list"><h2>{t('Thử nhanh nhiều game','Batch test games')}</h2><p class="muted">{t('Chọn nhiều ROM. Mỗi file được tạo thành Draft công khai, tự nhận diện hệ máy và dùng tên file làm tiêu đề. Game có thể sửa mô tả hoặc đánh dấu Testing sau.','Choose multiple ROMs. Each becomes a public Draft with automatic system detection and the filename as its title. Edit descriptions or mark Testing later.')}</p><form id="bulkGameForm"><label>{t('Tệp game','Game files')}<input name="roms" type="file" multiple required></label><div class="form-actions"><button class="button primary" type="submit">{t('Upload để thử','Upload for testing')}</button></div></form><progress id="bulkProgress" class="upload-progress" max="100" value="0" aria-label="{t('Tiến trình upload hàng loạt','Batch upload progress')}"></progress><p id="bulkStatus" class="muted" role="status"></p></section>
<section class="admin-grid"><form id="gameForm" class="admin-form" data-id="{editing['id'] if editing else ''}"><h2>{t('Sửa game','Edit game') if editing else t('Thêm game','New game')}</h2>
<div class="form-grid"><label>{t('Tên game','Game title')}<input name="title_en" value="{value('title_en')}" maxlength="120" placeholder="{t('Bỏ trống để dùng tên file','Leave blank to use the file name')}"></label>
<label>{t('Hệ máy','System')}<select name="system">{options}</select></label><label>ROM / game file<input name="rom" type="file"></label><label>{t('Ảnh cover','Cover image')}<input id="coverInput" name="cover" type="file" accept="image/png,image/jpeg,image/webp"></label><div id="coverPasteTarget" class="cover-paste" tabindex="0" role="button" aria-describedby="coverPasteStatus"><strong>{t('Dán cover từ clipboard','Paste cover from clipboard')}</strong><span>{t('Nhấp vào đây rồi nhấn Ctrl/Cmd + V','Click here, then press Ctrl/Cmd + V')}</span><small id="coverPasteStatus"></small></div><label>{t('Ảnh in-game trong mô tả','In-game images in description')}<input name="screenshots" type="file" accept="image/png,image/jpeg,image/webp" multiple></label>
<label class="check"><input name="published" type="checkbox"{checked('published')}> {t('Bản phát hành','Release')}</label><label class="check"><input name="experimental" type="checkbox"{checked('experimental')}> Testing</label><p class="wide muted">{t('Draft và Testing đều công khai để mọi người cùng chơi. Bản phát hành chỉ dùng để phân loại trạng thái.','Draft and Testing are public for everyone to play. Release only changes the status label.')}</p>
<label class="wide">Mô tả<textarea name="description_vi" maxlength="8000">{value('description_vi')}</textarea></label><label class="wide">{t('Ghi chú cập nhật','Update note')}<textarea name="update_note" maxlength="4000" placeholder="{t('Nội dung sẽ xuất hiện trong lịch sử cập nhật của game','This note appears in the game update history')}"></textarea></label></div>
<progress id="adminProgress" class="upload-progress" max="100" value="0" aria-label="{t('Tiến trình upload game','Game upload progress')}"></progress><p id="adminStatus" class="muted" role="status"></p><div class="form-actions"><button class="button primary" type="submit">Save game</button>{f'<button class="button danger" type="button" data-delete-game="{editing["id"]}">Delete</button>' if editing else ''}</div></form>
<section id="adminLibrary" class="admin-list"><h2>Library</h2><div class="table-wrap"><table><thead><tr><th>Game</th><th>System</th><th>Status</th><th>Size</th><th>{t('Tác vụ','Actions')}</th></tr></thead><tbody>{rows or '<tr><td colspan="5">Empty</td></tr>'}</tbody></table></div></section></section>
<section id="adminOperations" class="admin-tools"><section class="admin-list"><h2>{t('Quản trị viên','Administrators')}</h2><form id="adminCreateForm" class="admin-create"><label>{t('Tên đăng nhập (không thể đổi)','Username (cannot change)')}<input name="name" minlength="3" maxlength="32" required autocomplete="username"></label><label>{t('Nickname hiển thị','Display nickname')}<input name="display_name" minlength="2" maxlength="40" required autocomplete="nickname"></label><label>{t('Mật khẩu','Password')}<input name="password" type="password" minlength="10" maxlength="200" required autocomplete="new-password" aria-describedby="adminPasswordRules"></label><p id="adminPasswordRules" class="field-help">{t('Dùng 10–200 ký tự và ít nhất hai loại ký tự.','Use 10–200 characters and at least two character types.')}</p><label>{t('Xác nhận mật khẩu','Confirm password')}<input name="confirm" type="password" minlength="10" maxlength="200" required autocomplete="new-password" aria-describedby="adminPasswordRules"></label><button class="button primary" type="submit">{t('Tạo quản trị viên','Create admin')}</button></form></section>
<section class="admin-list"><h2>{t('Tài khoản','Accounts')}</h2><div class="table-wrap"><table><thead><tr><th>{t('Tên đăng nhập','Username')}</th><th>{t('Vai trò','Role')}</th><th>{t('Nickname hiển thị','Display nickname')}</th></tr></thead><tbody>{user_rows}</tbody></table></div></section>
<section class="admin-list"><h2>{t('Báo lỗi','Issue reports')}</h2><div class="report-list">{report_rows or f'<p class="muted">{t("Chưa có báo lỗi.","No reports.")}</p>'}</div></section></section>
<section class="contact-settings admin-list"><h2>{t('Liên hệ maintain','Maintainer contact')}</h2><form id="siteSettingsForm" class="form-grid"><label>{t('Email','Email')}<input name="maintainer_email" type="email" value="{esc(settings.get('maintainer_email'))}" maxlength="254"></label><label>{t('URL Facebook','Facebook URL')}<input name="maintainer_facebook" type="url" value="{esc(settings.get('maintainer_facebook'))}" maxlength="500" placeholder="https://facebook.com/..." ></label><label class="wide">{t('Liên kết mạng xã hội khác','Other social links')}<textarea name="maintainer_links" maxlength="4000" placeholder="Discord|https://...&#10;YouTube|https://...">{esc(settings.get('maintainer_links'))}</textarea></label><div class="form-actions"><button class="button primary" type="submit">{t('Lưu liên hệ','Save contact')}</button></div></form></section></main>"""
    return layout("Dashboard", body, lang, user, csrf)


def rate_allowed(ip, action, limit, window=600, subject=""):
    now = time.time()
    key = (auth_hash(ip), action, str(subject))
    entries = [stamp for stamp in RATE_LIMIT.get(key, []) if now - stamp < window]
    if len(entries) >= limit:
        RATE_LIMIT[key] = entries
        return False
    entries.append(now)
    RATE_LIMIT[key] = entries
    return True


class Handler(BaseHTTPRequestHandler):
    server_version = "AN3Arcade/1.0"

    def log_message(self, fmt, *args):
        sys.stdout.write("%s %s\n" % (self.address_string(), fmt % args))

    def common_headers(self, content_type, length=None, cache="no-store", csp=None, cross_origin_isolated=False):
        self.send_header("Content-Type", content_type)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        if cross_origin_isolated:
            self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("X-Permitted-Cross-Domain-Policies", "none")
        if COOKIE_SECURE:
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        self.send_header("Content-Security-Policy", csp or "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'self'; worker-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'")
        if getattr(self, "_visitor_cookie", ""):
            self.send_header("Set-Cookie", self._visitor_cookie)

    def send_bytes(self, status, data, content_type="application/json; charset=utf-8", cache="no-store", csp=None, cross_origin_isolated=False):
        self.send_response(status)
        self.common_headers(content_type, len(data), cache, csp, cross_origin_isolated)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def send_json(self, payload, status=200):
        self.send_bytes(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def send_html(self, content, status=200, player=False):
        csp = None
        if player:
            csp = "default-src 'self' blob: data: https://cdn.emulatorjs.org; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline' https://cdn.emulatorjs.org; script-src 'self' 'unsafe-eval' 'wasm-unsafe-eval' blob: https://cdn.emulatorjs.org; connect-src 'self' blob: https://cdn.emulatorjs.org; worker-src 'self' blob: https://cdn.emulatorjs.org; frame-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'"
        self.send_bytes(status, content.encode("utf-8"), "text/html; charset=utf-8", csp=csp, cross_origin_isolated=player)

    def read_json(self, maximum=MAX_JSON_BYTES):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0 or length > maximum:
            raise ValueError("invalid request size")
        return json.loads(self.rfile.read(length).decode("utf-8"))

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
            recent = conn.execute("SELECT 1 FROM page_views WHERE visitor_hash=? AND path=? AND created_at>? LIMIT 1", (visitor, path, now - 1800)).fetchone()
            if not recent:
                conn.execute("INSERT INTO page_views(visitor_hash,user_id,path,created_at) VALUES(?,?,?,?)", (visitor, user_id, path, now))
            if game_id:
                played = conn.execute("SELECT 1 FROM play_events WHERE visitor_hash=? AND game_id=? AND created_at>? LIMIT 1", (visitor, game_id, now - 600)).fetchone()
                if not played:
                    conn.execute("INSERT INTO play_events(visitor_hash,user_id,game_id,created_at) VALUES(?,?,?,?)", (visitor, user_id, game_id, now))

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
            raise RateLimited("Vui lòng chờ trước khi gửi tiếp")
        if total >= limit:
            raise RateLimited("Bạn đã đạt giới hạn gửi trong hôm nay")
        if not rate_allowed(self.client_address[0], f"{kind}-ip", limit, window):
            raise RateLimited("Quá nhiều yêu cầu từ mạng này")
        if not rate_allowed(self.client_address[0], f"{kind}-user", limit, window, user["id"]):
            raise RateLimited("Bạn đã đạt giới hạn gửi")

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
        flags = f"Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}" + ("; Secure" if COOKIE_SECURE else "")
        self.send_header("Set-Cookie", f"an3_session={token}; {flags}")

    def clear_session(self):
        jar = self.cookie_jar()
        token = jar.get("an3_session")
        if token:
            with db() as conn:
                conn.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.value.encode()).hexdigest(),))
        flags = "Path=/; HttpOnly; SameSite=Lax; Max-Age=0" + ("; Secure" if COOKIE_SECURE else "")
        self.send_header("Set-Cookie", f"an3_session=; {flags}")

    def find_game(self, slug, include_draft=True):
        with db() as conn:
            return conn.execute("SELECT * FROM games WHERE slug=?", (slug,)).fetchone()

    def redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
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
            self.common_headers(content_type, size, cache, csp)
            if sandbox:
                self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.end_headers()
            if self.command != "HEAD":
                with open(path, "rb") as handle:
                    shutil.copyfileobj(handle, self.wfile, 1024 * 1024)
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

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        lang = language(self)
        user, csrf = self.current_user()
        if parse_qs(parsed.query).get("lang", [""])[0] in ("vi", "en"):
            chosen = parse_qs(parsed.query)["lang"][0]
            clean = path
            self.send_response(303)
            self.send_header("Location", clean)
            self.send_header("Set-Cookie", f"lang={chosen}; Path=/; SameSite=Lax; Max-Age=31536000")
            self.end_headers()
            return
        if path == "/":
            self.track_visit("/", user)
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
            self.send_html(offline_page(lang, user, csrf), player=True)
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
                self.send_html(admin_page(lang, user, csrf, edit_id))
        elif path == "/service-worker.js":
            self.serve_static(STATIC_DIR, "service-worker.js", "no-cache")
        elif path.startswith("/emulatorjs/"):
            match = re.fullmatch(r"/emulatorjs/(stable|latest)/data/(.+)", path)
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
        elif path.startswith("/static/"):
            self.serve_static(STATIC_DIR, path[8:])
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
            self.send_json({"ok": True, "environment": ENVIRONMENT, "asset_version": ASSET_VERSION, "time": int(time.time())})
        else:
            if path.startswith("/api/") or path.startswith("/admin/api/"):
                self.send_json({"error": "not found"}, 404)
            else:
                self.send_html(status_page(404, lang, user, csrf), 404)

    do_HEAD = do_GET

    def do_POST(self):
        path = urlparse(self.path).path
        lang = language(self)
        try:
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
                    if duplicate: raise RateLimited("Bình luận này đã được gửi")
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
                    if duplicate: raise RateLimited("Báo lỗi này đã được gửi")
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
                    add_game_update(conn, cur.lastrowid, "Tạo game", "Game created", str(data.get("update_note") or "")[:4000], str(data.get("update_note") or "")[:4000])
                self.send_json({"ok": True, "id": cur.lastrowid, "slug": slug}, 201)
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
                    add_game_update(conn, game_id, "Cập nhật thông tin game", "Game information updated", note, note)
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
                    raise ValueError("email không hợp lệ")
                if facebook and not re.fullmatch(r"https?://[^\s]{1,500}", facebook):
                    raise ValueError("Facebook URL không hợp lệ")
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
            else:
                self.send_json({"error":"not found"},404)
        except RateLimited as exc:
            self.send_json({"error":str(exc)},429)
        except PermissionError as exc:
            self.send_json({"error":str(exc)},403)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error":str(exc)},400)
        except Exception:
            self.send_json({"error":"Yêu cầu không thể xử lý"},400)

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
                handle.write(chunk)
                remaining -= len(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if remaining:
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
            raise ValueError("Không thể tự nhận diện file; hãy chọn hệ máy trong mục nâng cao")
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
                self.send_json({"error": "Upload không thể xử lý"}, 400)
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
            self.send_json({"error": "Upload không thể xử lý"}, 400)

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
    print(f"AN3 Arcade listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()
