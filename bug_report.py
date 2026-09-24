# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bug report collection, local-first sanitization, and server-side GitHub issues.

The module is intentionally free of any ``app.py`` import so the sanitizer and
issue builder can be unit-tested in isolation. Two invariants drive the design:

* Personal data and credentials are removed *before* a report is previewed,
  uploaded, stored, or turned into a GitHub issue.
* GitHub credentials never reach the client. Only the server reads the token
  from the environment and only the server talks to the GitHub API.
"""

import hashlib
import json
import os
import re
import secrets
import time
import unicodedata
from urllib.request import Request, urlopen

SCHEMA_VERSION = 1
# Anonymous native support: the packaged offline app has no account session and
# no cookie, so it cannot authenticate to /api/bug-reports. Instead the server
# issues a short-lived opaque capability that is bound to its issuing origin,
# its own expiry, and a small use count. The capability is a bearer credential, never an
# identity: it carries no MAC, device fingerprint, account, or user data. Only
# the SHA-256 digest is stored; the raw token exists only in the response and
# the client's memory.
SUPPORT_CAPABILITY_HEADER = "X-AN3-Support-Capability"
CAPABILITY_TTL_SECONDS = 30 * 60
CAPABILITY_MAX_USES = 5
CAPABILITY_TOKEN_BYTES = 32
# Server-only base URL. Defaults to the public API; an owner may point it at a
# GitHub Enterprise host. This value and the token never reach the client.
GITHUB_API_BASE = os.environ.get("AN3_GITHUB_API_BASE", "https://api.github.com").rstrip("/")
MAX_DESCRIPTION = 4000
MAX_LOG_LINES = 40
MAX_LOG_LINE = 500
MAX_SETTINGS_FIELDS = 40
MAX_SETTING_VALUE = 200
MAX_IDENTIFIER = 80
MAX_FIELD = 400

# Top-level fields a client submission may contribute. Anything else is
# dropped before storage so an unexpected key can never be persisted.
ALLOWED_FIELDS = frozenset(
    {
        "reportSchemaVersion",
        "appVersion",
        "buildId",
        "platform",
        "osVersion",
        "deviceModel",
        "cpu",
        "cpuCores",
        "deviceMemoryGb",
        "gpu",
        "gpuDriver",
        "rendererRequested",
        "rendererEffective",
        "emulatorSystem",
        "coreName",
        "coreVersion",
        "gameTitle",
        "gameIdentifier",
        "settings",
        "logs",
        "crash",
        "description",
        "timestamp",
        "language",
        "userAgent",
        "screen",
        "viewport",
        "online",
    }
)

# Exact key names that must never be uploaded. The comparison is normalized so
# ``rom_path`` and ``romPath`` resolve to the same forbidden marker.
_FORBIDDEN_KEY_NAMES = (
    "rom",
    "rompath",
    "romdata",
    "romfile",
    "romname",
    "rombytes",
    "save",
    "savefile",
    "savedata",
    "savestate",
    "state",
    "statefile",
    "token",
    "accesstoken",
    "refreshtoken",
    "pairingtoken",
    "pairingcode",
    "csrf",
    "cookiesecret",
    "password",
    "secret",
    "apikey",
    "privatekey",
    "accesskey",
    "githubtoken",
    "credential",
    "credentials",
    "env",
    "envvars",
    "environment",
    "ip",
    "ipaddress",
    "mac",
    "macaddress",
    "deviceid",
    "devicekey",
    "sessiontoken",
    "authorization",
    "sshid",
    "sshkey",
    "adbkey",
)
# Substring markers catch composed names such as ``accessToken`` or
# ``my_secret_value`` that an exact match would miss.
_FORBIDDEN_SUBSTRINGS = ("token", "password", "secret", "credential", "privatekey", "apikey")

FORBIDDEN_KEYS = frozenset(_FORBIDDEN_KEY_NAMES)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,79}$")
_SETTING_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")

# Credential material. Each replacement removes the whole value, never just
# the prefix, so a leaked token cannot survive in a stored report.
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL
)
_GITHUB_TOKEN_RE = re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b")
_GITHUB_PAT_RE = re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")
_AWS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
_SLACK_TOKEN_RE = re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")
_SK_TOKEN_RE = re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{10,}=*")
_QUERY_SECRET_RE = re.compile(
    r"(?i)\b(access_token|refresh_token|pairing_token|pairing_code|token|password|secret|api_key|apikey|key)=([^&\s\"']+)"
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_MAC_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6_RE = re.compile(r"\b(?:[0-9A-Fa-f]{1,4}:){3,7}[0-9A-Fa-f]{1,4}\b")
# Username components of common personal path roots. The directory structure
# may remain; only the account name is replaced.
_USER_PATH_RE = re.compile(r"(?i)([A-Za-z]:\\+Users\\+|/Users/|/home/)([^\\/\s\"']+)")
_ABS_PATH_RE = re.compile(
    r"(?i)(?:/(?:srv|opt|var|tmp|private|etc|root|mnt|media|Volumes|Applications|System)|[A-Za-z]:\\)(?:[^\s\"']*)?"
)
_ROM_EXT_RE = re.compile(
    r"(?i)\.(?:gba|gbc|gb|nds|3ds|cia|cci|n64|z64|v64|sfc|smc|nes|iso|chd|cso|rvz|wbfs|wad|zip|7z|rar|sav|srm|state|dsv|ss[0-9])"
)

_REDACTED = "[redacted]"


def normalize_key(key):
    """Normalize a key so ``rom_path`` and ``romPath`` compare equal."""
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def is_forbidden_key(key):
    normalized = normalize_key(key)
    if normalized in FORBIDDEN_KEYS:
        return True
    return any(marker in normalized for marker in _FORBIDDEN_SUBSTRINGS)


def scrub_text(value, *, strip_extension=True):
    """Return ``value`` with credentials, identity, and paths redacted.

    The function is deliberately total: a missing or non-string value becomes an
    empty string and every branch is best-effort, so a malformed report can
    still be sanitized rather than raising.
    """

    text = unicodedata.normalize("NFKC", str(value if value is not None else ""))
    # Drop control characters except newlines and tabs, which stay useful in
    # multi-line descriptions and log excerpts.
    text = "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)
    text = _PRIVATE_KEY_RE.sub("[redacted-private-key]", text)
    text = _GITHUB_TOKEN_RE.sub(_REDACTED, text)
    text = _GITHUB_PAT_RE.sub(_REDACTED, text)
    text = _AWS_KEY_RE.sub(_REDACTED, text)
    text = _SLACK_TOKEN_RE.sub(_REDACTED, text)
    text = _SK_TOKEN_RE.sub(_REDACTED, text)
    text = _BEARER_RE.sub("Bearer [redacted]", text)
    text = _QUERY_SECRET_RE.sub(lambda match: match.group(1) + "=" + _REDACTED, text)
    text = _EMAIL_RE.sub("[redacted-email]", text)
    text = _MAC_RE.sub("[redacted-mac]", text)
    text = _IPV6_RE.sub("[redacted-ip]", text)
    text = _IPV4_RE.sub("[redacted-ip]", text)
    text = _USER_PATH_RE.sub("[user-path]", text)
    text = _ABS_PATH_RE.sub("[path]", text)
    if strip_extension:
        text = _ROM_EXT_RE.sub("", text)
    return text.strip()


def scrub(value):
    """Recursively sanitize strings in an arbitrary JSON-like structure.

    Dictionary keys are preserved but forbidden keys are dropped entirely, so a
    nested credential can never reach the stored payload.
    """

    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if is_forbidden_key(key):
                continue
            result[str(key)] = scrub(item)
        return result
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    return scrub_text(value)


def _bounded_text(value, limit, *, strip_extension=True):
    return scrub_text(value, strip_extension=strip_extension)[:limit]


def _basename(value):
    """Keep only the final path component so a directory can never leak."""

    text = str(value if value is not None else "").replace("\\", "/")
    return text.rsplit("/", 1)[-1]


def _bounded_int(value, minimum, maximum):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number < minimum or number > maximum:
        return None
    return number


def _sanitize_settings(raw):
    if not isinstance(raw, dict):
        return {}
    settings = {}
    for key, value in raw.items():
        name = str(key)
        if not _SETTING_KEY_RE.match(name) or is_forbidden_key(name):
            continue
        if isinstance(value, bool) or isinstance(value, (int, float)):
            settings[name] = value
        else:
            settings[name] = _bounded_text(value, MAX_SETTING_VALUE)
        if len(settings) >= MAX_SETTINGS_FIELDS:
            break
    return settings


def _sanitize_logs(raw):
    if not isinstance(raw, (list, tuple)):
        return []
    lines = []
    for item in raw[-MAX_LOG_LINES:]:
        line = scrub_text(item)[:MAX_LOG_LINE]
        if line:
            lines.append(line)
    return lines


def _sanitize_crash(raw):
    if not isinstance(raw, dict):
        return {}
    crash = {}
    for key in ("stage", "message", "stack"):
        if key in raw:
            crash[key] = _bounded_text(raw[key], MAX_DESCRIPTION)
    return crash


def _game_identifier(raw, game_title):
    """A short anonymous identifier that never encodes a filesystem path."""

    candidate = str(raw.get("gameIdentifier") or "").strip().lower()
    if _SLUG_RE.match(candidate):
        return candidate[:MAX_IDENTIFIER]
    basis = (game_title or str(raw.get("gameTitle") or "")).strip().lower()
    if not basis:
        return ""
    digest = hashlib.sha256(re.sub(r"\s+", " ", basis).encode("utf-8")).hexdigest()
    return "game-" + digest[:12]


def build_report(raw, *, build_id="", app_version="", channel="", now=None):
    """Build the exact sanitized document that will be stored and uploaded.

    Client values are filtered to the allowlist, scrubbed, and bounded. Server
    facts (build id, app version, channel, receipt time) are authoritative and
    overwrite any client attempt to spoof them.
    """

    raw = raw if isinstance(raw, dict) else {}
    report = {
        "reportSchemaVersion": SCHEMA_VERSION,
        "appVersion": _bounded_text(app_version, MAX_FIELD) or _bounded_text(raw.get("appVersion"), MAX_FIELD),
        "buildId": _bounded_text(build_id, MAX_FIELD) or _bounded_text(raw.get("buildId"), MAX_FIELD),
        "channel": _bounded_text(channel, MAX_FIELD),
        "platform": _bounded_text(raw.get("platform"), MAX_FIELD),
        "osVersion": _bounded_text(raw.get("osVersion"), MAX_FIELD),
        "deviceModel": _bounded_text(raw.get("deviceModel"), MAX_FIELD),
        "cpu": _bounded_text(raw.get("cpu"), MAX_FIELD),
        "cpuCores": _bounded_int(raw.get("cpuCores"), 1, 1024),
        "deviceMemoryGb": _bounded_int(raw.get("deviceMemoryGb"), 1, 4096),
        "gpu": _bounded_text(raw.get("gpu"), MAX_FIELD),
        "gpuDriver": _bounded_text(raw.get("gpuDriver"), MAX_FIELD),
        "rendererRequested": _bounded_text(raw.get("rendererRequested"), 80),
        "rendererEffective": _bounded_text(raw.get("rendererEffective"), 80),
        "emulatorSystem": _bounded_text(raw.get("emulatorSystem"), 40),
        "coreName": _bounded_text(_basename(raw.get("coreName")), MAX_FIELD),
        "coreVersion": _bounded_text(raw.get("coreVersion"), MAX_FIELD),
        "gameTitle": _bounded_text(_basename(raw.get("gameTitle")), MAX_FIELD),
        "gameIdentifier": "",
        "settings": _sanitize_settings(raw.get("settings")),
        "logs": _sanitize_logs(raw.get("logs")),
        "crash": _sanitize_crash(raw.get("crash")),
        "description": _bounded_text(raw.get("description"), MAX_DESCRIPTION),
        "language": _bounded_text(raw.get("language"), 16),
        "userAgent": _bounded_text(raw.get("userAgent"), MAX_FIELD),
        "screen": _bounded_text(raw.get("screen"), 40),
        "viewport": _bounded_text(raw.get("viewport"), 40),
        "online": bool(raw.get("online")) if isinstance(raw.get("online"), bool) else None,
        "timestamp": _bounded_int(raw.get("timestamp"), 0, 4102444800),
    }
    report["gameIdentifier"] = _game_identifier(raw, report["gameTitle"])

    allowed = set(ALLOWED_FIELDS)
    dropped = 0
    for key in raw:
        if key not in allowed:
            dropped += 1
    report["droppedFieldCount"] = dropped

    # Server-side facts are always appended last so a client cannot override.
    report["receivedAt"] = int(now if now is not None else time.time())
    return report


def assert_no_forbidden(report):
    """Raise ``ValueError`` if a built report still contains forbidden data.

    This is the last defense before storage. It checks keys structurally and
    scans the serialized document for credential-shaped values.
    """

    def walk(value, path):
        if isinstance(value, dict):
            for key, item in value.items():
                if is_forbidden_key(key):
                    raise ValueError("forbidden field: %s%s" % (path, key))
                walk(item, path + str(key) + ".")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, "%s[%d]." % (path, index))

    walk(report, "")
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
    for pattern, label in (
        (_PRIVATE_KEY_RE, "private key"),
        (_GITHUB_TOKEN_RE, "github token"),
        (_GITHUB_PAT_RE, "github token"),
        (_AWS_KEY_RE, "aws key"),
        (_SLACK_TOKEN_RE, "slack token"),
        (_SK_TOKEN_RE, "api key"),
        (_BEARER_RE, "bearer token"),
        (_MAC_RE, "mac address"),
        (_USER_PATH_RE, "user path"),
    ):
        if pattern.search(serialized):
            raise ValueError("forbidden value: %s" % label)
    return True


def support_capability_digest(token):
    """Return the storage digest for a capability; the raw token is never stored."""

    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def new_support_capability():
    """Mint an opaque capability and its storage digest.

    The caller persists the digest with an expiry and a maximum use count. The
    token is high-entropy, URL-safe, and meaningless without the server row, so
    it can never be reused as an account credential.
    """

    token = secrets.token_urlsafe(CAPABILITY_TOKEN_BYTES)
    return token, support_capability_digest(token)


def issue_fingerprint(report):
    """Stable short fingerprint used to avoid creating duplicate issues."""

    description = re.sub(r"\s+", " ", str(report.get("description") or "").strip().lower())
    parts = [
        str(report.get("reportSchemaVersion")),
        str(report.get("appVersion") or ""),
        str(report.get("platform") or ""),
        str(report.get("emulatorSystem") or ""),
        str(report.get("coreName") or ""),
        str(report.get("gameIdentifier") or ""),
        description,
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def github_issue_title(report):
    """A short, safe issue title for the maintainer repository."""

    system = report.get("emulatorSystem") or "app"
    summary = (report.get("description") or "").strip().splitlines()
    headline = summary[0][:80] if summary else ""
    if not headline:
        headline = report.get("gameTitle") or "user submitted report"
    return "Bug report [%s]: %s" % (system, headline)


def github_issue_body(report):
    """Render the sanitized report as Markdown with a duplicate marker."""

    marker = "<!-- an3-bug-fingerprint:%s -->" % issue_fingerprint(report)
    settings = json.dumps(report.get("settings") or {}, ensure_ascii=False, sort_keys=True)
    crash = json.dumps(report.get("crash") or {}, ensure_ascii=False, sort_keys=True)
    logs = "\n".join(report.get("logs") or [])
    lines = [
        marker,
        "## User description",
        report.get("description") or "_(none provided)_",
        "",
        "## Environment",
        "- app version: `%s`" % (report.get("appVersion") or ""),
        "- build id: `%s`" % (report.get("buildId") or ""),
        "- channel: `%s`" % (report.get("channel") or ""),
        "- platform: `%s`" % (report.get("platform") or ""),
        "- OS: `%s`" % (report.get("osVersion") or ""),
        "- device: `%s`" % (report.get("deviceModel") or ""),
        "- CPU: `%s` (%s cores)" % (report.get("cpu") or "", report.get("cpuCores") or "?"),
        "- GPU: `%s`" % (report.get("gpu") or ""),
        "- GPU driver: `%s`" % (report.get("gpuDriver") or ""),
        "- renderer requested/effective: `%s` / `%s`"
        % (report.get("rendererRequested") or "", report.get("rendererEffective") or ""),
        "",
        "## Game",
        "- system: `%s`" % (report.get("emulatorSystem") or ""),
        "- core: `%s` `%s`" % (report.get("coreName") or "", report.get("coreVersion") or ""),
        "- title: `%s`" % (report.get("gameTitle") or ""),
        "- anonymous identifier: `%s`" % (report.get("gameIdentifier") or ""),
        "",
        "## Settings (sanitized)",
        "```json",
        settings,
        "```",
        "",
        "## Crash",
        "```json",
        crash,
        "```",
        "",
        "## Recent logs (sanitized)",
        "```",
        logs or "(none)",
        "```",
        "",
        "_Report schema version %s. Collected and sanitized on the client before upload; "
        "re-sanitized on the server._" % report.get("reportSchemaVersion"),
    ]
    return "\n".join(lines)[:60000]


def create_github_issue(report, *, token, repository, labels=None, fetch=urlopen, timeout=10, api_base=None):
    """Create a GitHub issue server-side. Never raises and never sees the client.

    Returns a dict describing the attempt. A failure here must never destroy the
    stored report; the caller persists first and links the issue afterwards.
    """

    if not token or not repository or "/" not in str(repository):
        return {"attempted": False, "created": False, "reason": "not configured"}
    payload = {
        "title": github_issue_title(report),
        "body": github_issue_body(report),
    }
    if labels:
        payload["labels"] = list(labels)
    data = json.dumps(payload).encode("utf-8")
    base = (api_base or GITHUB_API_BASE).rstrip("/")
    request = Request(
        "%s/repos/%s/issues" % (base, str(repository).strip()),
        data=data,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "Authorization": "Bearer %s" % token,
            "User-Agent": "an3-bug-report/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with fetch(request, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            body = response.read().decode("utf-8", "replace")
    except Exception as exc:  # network, DNS, TLS, timeout: never fatal
        return {"attempted": True, "created": False, "reason": "request failed: %s" % type(exc).__name__}
    if status not in (200, 201):
        return {"attempted": True, "created": False, "reason": "github status %s" % status}
    try:
        parsed = json.loads(body)
    except ValueError:
        parsed = {}
    return {
        "attempted": True,
        "created": True,
        "number": parsed.get("number"),
        "url": parsed.get("html_url"),
    }
