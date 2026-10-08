#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Dependency-free secret and private-data scan for release artifacts.

Run before publication, next to the unknown-license gate. The tool scans built
release artifacts and the release evidence bundle at the byte level (including
binary installers), so a credential, token or developer path embedded in an
artifact is caught without network access or a ``gitleaks`` install.

* No network access and no third-party dependency: ``re``/``os``/``json`` only.
* The embedded rule set is a curated subset of the project-specific patterns
  already used by ``tools/publication-check.sh`` plus common credential shapes
  from the gitleaks default set.
* ``tools/publication/.gitleaks.toml`` stays the single source of truth for
  suppressions: ``[[allowlists]]`` (``paths`` + ``regexes``) are honoured, and
  additional ``[[rules]]`` with an inline ``regex`` are merged into the rule set.
* A matched value is never printed or written to the report. Only the rule id,
  category, path, byte offset, line and match length are recorded.
* Compressed container members are expanded with the standard library only
  (``zipfile``/``tarfile``/``gzip``/``lzma``/``bz2``) so credentials inside an
  ``.apk`` (a ZIP), a ``.deb`` (an ``ar`` archive of ``control``/``data``
  tarballs), a ``.tar.gz``/``.zip``/``.tar.xz`` bundle, or a nested archive are
  found instead of hiding behind compression. Members are streamed in memory and
  never extracted to disk; a member path is reported as ``container!member``.
  The UDIF ``.dmg``, Flatpak bundle and NSIS ``.exe`` containers have no
  standard-library reader, so those (and any other unrecognised container) are
  raw-scanned as before (see ``docs/licensing/distribution-compliance.md``).

Usage:
    python3 tools/release-artifact-scan.py [--config FILE] [--json REPORT]
        [--max-file-bytes N] TARGET [TARGET ...]

TARGET is a file or directory (directories are walked recursively). The exit
status is 0 when clean, 1 when any finding is reported, and 2 on a usage or
configuration error.
"""
from __future__ import annotations

import argparse
import bz2
import gzip
import io
import json
import lzma
import os
import re
import sys
import tarfile
import zipfile
import zlib
from pathlib import Path

TOOL_NAME = "release-artifact-scan"
TOOL_VERSION = "1"
SCHEMA_VERSION = 1

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "tools" / "publication" / ".gitleaks.toml"

# (rule id, category, bytes regex)
#
# "secret"       -> an active credential; must be rotated/removed before publish.
# "private-data" -> a developer or infrastructure value that must not ship.
DEFAULT_RULES = (
    ("private-key-block", "secret", rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    ("google-api-key", "secret", rb"AIza[0-9A-Za-z_\-]{35}"),
    ("google-oauth-client-secret", "secret", rb"GOCSPX-[0-9A-Za-z_\-]{20,}"),
    ("aws-access-key-id", "secret", rb"\b(?:AKIA|ASIA|A3T[A-Z0-9])[0-9A-Z]{16}\b"),
    ("github-token", "secret", rb"\bgh[pousr]_[0-9A-Za-z]{36,255}"),
    ("slack-token", "secret", rb"\bxox[baprs]-[0-9A-Za-z-]{10,}"),
    ("stripe-secret-key", "secret", rb"\bsk_live_[0-9A-Za-z]{20,}"),
    (
        "jwt",
        "secret",
        rb"\beyJ[A-Za-z0-9_\-]{10,8192}\.[A-Za-z0-9_\-]{10,8192}\.[A-Za-z0-9_\-]{10,8192}",
    ),
    (
        "an3-env-secret",
        "secret",
        rb"AN3_(?:GOOGLE_CLIENT_SECRET|AUTH_PEPPER|GITHUB_ISSUES_TOKEN)=[A-Za-z0-9_\-]{8,1024}",
    ),
    ("an3-google-client-id", "private-data", rb"AN3_GOOGLE_CLIENT_ID=[A-Za-z0-9._\-]{8,}"),
    ("home-directory-path", "private-data", rb"/Users/[A-Za-z][A-Za-z0-9._-]*/"),
    ("windows-home-path", "private-data", rb"[A-Za-z]:\\Users\\[A-Za-z]"),
    ("lan-address", "private-data", rb"\b192\.168\.\d{1,3}\.\d{1,3}\b"),
    # The local part is bounded ({1,64}) and the domain is completed with a
    # required TLD so a long unanchored run cannot trigger quadratic
    # backtracking on hostile, minified or undecodable artifact bytes.
    (
        "personal-email",
        "private-data",
        rb"[A-Za-z0-9._%+-]{1,64}@(?:gmail|outlook|yahoo|hotmail)\.[A-Za-z]{2,}",
    ),
    ("private-infra-host", "private-data", rb"\ban3tocom\.space\b"),
    ("developer-handle", "private-data", rb"\bmeomeo\b"),
    ("legacy-marker", "private-data", rb"\ban3" + rb"_codex\b"),
)

DEFAULT_MAX_FILE_BYTES = 512 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
FINDING_LIMIT = 1000

# Compressed-container expansion. A container is expanded at most
# ARCHIVE_MAX_DEPTH levels deep; every member is capped by --max-file-bytes, so
# a nesting or decompression bomb cannot exhaust memory or disk. Members are
# never written to disk.
ARCHIVE_SNIFF_BYTES = 512
ARCHIVE_MAX_DEPTH = 2
ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
GZIP_MAGIC = b"\x1f\x8b"
TAR_MAGIC_OFFSET = 257
TAR_MAGIC = b"ustar"
XZ_MAGIC = b"\xfd7zXZ\x00"
BZIP2_MAGIC = b"BZh"
AR_MAGIC = b"!<arch>\n"
AR_MEMBER_HEADER = 60


class ConfigError(Exception):
    """The scanner cannot run because its configuration is unusable."""


def _compile_rules(rule_specs):
    compiled = []
    seen = set()
    for rule_id, category, pattern in rule_specs:
        if rule_id in seen:
            raise ConfigError(f"duplicate rule id: {rule_id}")
        seen.add(rule_id)
        try:
            compiled.append((rule_id, category, re.compile(pattern)))
        except re.error as error:  # pragma: no cover - defensive
            raise ConfigError(f"invalid regex for rule {rule_id}: {error}") from error
    return compiled


def _unquote(value: str) -> str:
    value = value.strip()
    for quote in ("'''", '"""'):
        if len(value) >= 6 and value.startswith(quote) and value.endswith(quote):
            return value[3:-3]
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        if value[0] == '"':
            inner = (
                inner.replace("\\\\", "\x00")
                .replace('\\"', '"')
                .replace("\x00", "\\")
            )
        return inner
    return value


def _split_array_items(inner: str):
    items = []
    buffer = []
    quote = None
    index = 0
    while index < len(inner):
        char = inner[index]
        if quote:
            buffer.append(char)
            if char == "\\" and quote == '"' and index + 1 < len(inner):
                buffer.append(inner[index + 1])
                index += 2
                continue
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            buffer.append(char)
        elif char == ",":
            items.append("".join(buffer))
            buffer = []
        else:
            buffer.append(char)
        index += 1
    if "".join(buffer).strip():
        items.append("".join(buffer))
    return [_unquote(item) for item in items if item.strip()]


def _parse_value(raw: str):
    raw = raw.strip()
    if raw in ("true", "false"):
        return raw == "true"
    if raw.startswith("[") and raw.endswith("]"):
        return _split_array_items(raw[1:-1])
    return _unquote(raw)


def _balanced(text: str) -> bool:
    """True when brackets and quoted strings in ``text`` are closed."""
    index = 0
    length = len(text)
    depth = 0
    while index < length:
        if text.startswith("'''", index) or text.startswith('"""', index):
            closer = text[index : index + 3]
            end = text.find(closer, index + 3)
            if end < 0:
                return False
            index = end + 3
        elif text[index] in "\"'":
            quote = text[index]
            index += 1
            while index < length:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == quote:
                    index += 1
                    break
                index += 1
            else:
                return False
        elif text[index] == "[":
            depth += 1
            index += 1
        elif text[index] == "]":
            depth -= 1
            index += 1
        else:
            index += 1
    return depth <= 0


def _statements(lines):
    buffer = []
    for line in lines:
        buffer.append(line)
        if _balanced("\n".join(buffer)):
            yield "\n".join(buffer)
            buffer = []
    if "".join(buffer).strip():
        yield "\n".join(buffer)


_KEY_VALUE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", re.DOTALL)


def parse_gitleaks_config(text: str):
    """Parse the allowlists and inline custom rules from a gitleaks config.

    Supports the subset of TOML this repository uses plus the common
    ``[[rules]]``/``regex`` form. Unsupported rule shapes are reported as
    warnings rather than silently dropped.
    """
    allowlists = []
    custom_rules = []
    extend_default = False
    warnings = []
    block = None
    current = None

    for statement in _statements(text.splitlines()):
        stripped = statement.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[[") and stripped.endswith("]]"):
            name = stripped[2:-2].strip()
            if name == "allowlists":
                current = {"paths": [], "regexes": []}
                allowlists.append(current)
                block = "allowlist"
            elif name == "rules":
                current = {}
                custom_rules.append(current)
                block = "rule"
            else:
                current = None
                block = None
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            block = "extend" if stripped.strip("[]").strip() == "extend" else None
            current = None
            continue
        match = _KEY_VALUE.match(stripped)
        if not match:
            continue
        key, raw_value = match.group(1), match.group(2)
        value = _parse_value(raw_value)
        if block == "extend" and key == "useDefault":
            extend_default = bool(value)
        elif block == "allowlist" and current is not None:
            if key in ("paths", "regexes") and isinstance(value, list):
                current[key] = value
        elif block == "rule" and current is not None:
            current[key] = value

    rules = list(DEFAULT_RULES)
    for index, rule in enumerate(custom_rules):
        rule_id = rule.get("id") or f"custom-{index + 1}"
        pattern = rule.get("regex")
        if not pattern:
            warnings.append(
                f"custom rule {rule_id!r} has no inline regex; only inline "
                "regex rules are supported and this rule was ignored"
            )
            continue
        rules.append((str(rule_id), "custom", pattern.encode("utf-8")))
    return {
        "rules": rules,
        "allowlists": allowlists,
        "extend_default": extend_default,
        "warnings": warnings,
    }


def _allowlist_matches(allowlist, display_path: str, match_bytes: bytes) -> bool:
    paths = allowlist.get("paths") or []
    regexes = allowlist.get("regexes") or []
    if not paths:
        return False
    if not any(re.search(path, display_path) for path in paths):
        return False
    if not regexes:
        return True
    return any(
        re.search(regex.encode("utf-8") if isinstance(regex, str) else regex, match_bytes)
        for regex in regexes
    )


def _target_files(targets):
    files = []
    for target in targets:
        path = Path(target)
        if path.is_dir():
            for item in sorted(path.rglob("*")):
                if item.is_file() and not item.is_symlink():
                    files.append(item)
        elif path.is_file():
            files.append(path)
        else:
            raise ConfigError(f"target does not exist: {target}")
    return files


def _display_path(path: Path) -> str:
    try:
        return Path(os.path.relpath(path)).as_posix()
    except ValueError:  # pragma: no cover - different drive on Windows
        return path.as_posix()


def _line_number(state, window: bytes, match_start: int) -> int:
    carry_newlines = state["carry"].count(b"\n")
    base = state["newlines"] - carry_newlines + 1
    return base + window[:match_start].count(b"\n")


def _scan_stream(stream, display, rules, allowlists, max_bytes, findings):
    """Match ``rules`` over a binary stream, appending findings to ``findings``.

    Returns ``(suppressed, status)`` where ``status`` is ``None`` on completion,
    ``"finding limit reached"`` when the per-file cap is hit, or an oversize
    message when the stream is longer than ``max_bytes``.
    """
    suppressed = 0
    overlap = max(1, max(len(rule.pattern) for _, _, rule in rules))
    state = {"carry": b"", "newlines": 0, "abs": 0}
    while True:
        chunk = stream.read(CHUNK_BYTES)
        if not chunk:
            break
        window = state["carry"] + chunk
        window_base = state["abs"] - len(state["carry"])
        for rule_id, category, rule in rules:
            for match in rule.finditer(window):
                if match.end() <= len(state["carry"]):
                    # The whole match sits inside bytes already scanned as the
                    # previous window's tail, so it was reported then; dropping
                    # it here prevents a duplicate at every chunk boundary.
                    continue
                line = _line_number(state, window, match.start())
                if any(
                    _allowlist_matches(entry, display, match.group(0))
                    for entry in allowlists
                ):
                    suppressed += 1
                    continue
                findings.append(
                    {
                        "rule": rule_id,
                        "category": category,
                        "path": display,
                        "offset": window_base + match.start(),
                        "line": line,
                        "match_length": match.end() - match.start(),
                    }
                )
                if len(findings) >= FINDING_LIMIT:
                    return suppressed, "finding limit reached"
        state["newlines"] += chunk.count(b"\n")
        state["abs"] += len(chunk)
        state["carry"] = window[-overlap:]
        if state["abs"] > max_bytes:
            return suppressed, f"file exceeds --max-file-bytes ({max_bytes} bytes)"
    return suppressed, None


class _PrefixedReader:
    """Replay an already-read prefix, then continue from ``stream``."""

    def __init__(self, prefix, stream):
        self._prefix = prefix
        self._stream = stream

    def read(self, size=-1):
        if not self._prefix:
            return self._stream.read(size)
        if size is None or size < 0:
            data = self._prefix + self._stream.read()
            self._prefix = b""
            return data
        data = self._prefix[:size]
        self._prefix = self._prefix[size:]
        if len(data) < size:
            data += self._stream.read(size - len(data))
        return data


class _LimitedReader:
    """Expose at most ``limit`` bytes of ``stream`` (an archive member)."""

    def __init__(self, stream, limit):
        self._stream = stream
        self._remaining = max(0, limit)

    def read(self, size=-1):
        if self._remaining <= 0:
            return b""
        if size is None or size < 0:
            size = self._remaining
        data = self._stream.read(min(size, self._remaining))
        self._remaining -= len(data)
        return data


def _discard(stream):
    while stream.read(CHUNK_BYTES):
        pass


def _sniff_archive(header: bytes):
    """Return the container format implied by ``header`` bytes, or ``None``."""
    if len(header) >= 8 and header[:8] == AR_MAGIC:
        return "ar"
    if len(header) >= 4 and header[:4] in ZIP_SIGNATURES:
        return "zip"
    if (
        len(header) >= 4
        and header[:2] == GZIP_MAGIC
        and header[2] == 0x08
        and not header[3] & 0xE0
    ):
        return "gzip"
    if (
        len(header) >= TAR_MAGIC_OFFSET + len(TAR_MAGIC)
        and header[TAR_MAGIC_OFFSET : TAR_MAGIC_OFFSET + len(TAR_MAGIC)] == TAR_MAGIC
    ):
        return "tar"
    if len(header) >= 6 and header[:6] == XZ_MAGIC:
        return "xz"
    if (
        len(header) >= 4
        and header[:3] == BZIP2_MAGIC
        and header[3:4] in b"123456789"
    ):
        return "bzip2"
    return None


def _clean_member_name(name: str) -> str:
    cleaned = name.replace("\\", "/").lstrip("/")
    return cleaned or "(unnamed)"


def _decompressed_stream(stream, kind):
    if kind == "gzip":
        return gzip.GzipFile(fileobj=stream)
    if kind == "xz":
        return lzma.LZMAFile(stream)
    if kind == "bzip2":
        return bz2.BZ2File(stream)
    raise ConfigError(f"unsupported container format: {kind}")


def _scan_member_stream(
    stream, display, size, rules, allowlists, max_bytes, depth, findings, skips
):
    """Scan one container member, recursing into a nested container.

    A nested container is buffered in memory only, up to ``max_bytes``; an
    unreadable or oversized member is recorded in ``skips`` rather than trusted.
    """
    if size is not None and size > max_bytes:
        skips.append(f"{display} exceeds --max-file-bytes ({size} bytes)")
        return 0, None
    header = stream.read(ARCHIVE_SNIFF_BYTES)
    nested = _sniff_archive(header) if depth < ARCHIVE_MAX_DEPTH else None
    if nested is None:
        return _scan_stream(
            _PrefixedReader(header, stream), display, rules, allowlists, max_bytes, findings
        )
    buffered = bytearray(header)
    while True:
        chunk = stream.read(CHUNK_BYTES)
        if not chunk:
            break
        buffered.extend(chunk)
        if len(buffered) > max_bytes:
            skips.append(f"{display} exceeds --max-file-bytes ({max_bytes} bytes)")
            return 0, None
    return _scan_container_stream(
        io.BytesIO(bytes(buffered)),
        nested,
        display,
        rules,
        allowlists,
        max_bytes,
        depth + 1,
        findings,
        skips,
    )


def _scan_zip_stream(stream, display, rules, allowlists, max_bytes, depth, findings, skips):
    suppressed = 0
    with zipfile.ZipFile(stream) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            member_display = f"{display}!{_clean_member_name(info.filename)}"
            with archive.open(info, "r") as member:
                member_suppressed, status = _scan_member_stream(
                    member,
                    member_display,
                    info.file_size,
                    rules,
                    allowlists,
                    max_bytes,
                    depth,
                    findings,
                    skips,
                )
            suppressed += member_suppressed
            if status == "finding limit reached":
                return suppressed, status
    return suppressed, None


def _scan_tar_stream(stream, display, rules, allowlists, max_bytes, depth, findings, skips):
    suppressed = 0
    with tarfile.open(fileobj=stream, mode="r|") as archive:
        for member in archive:
            if not member.isfile():
                continue
            member_stream = archive.extractfile(member)
            if member_stream is None:
                continue
            member_display = f"{display}!{_clean_member_name(member.name)}"
            with member_stream:
                member_suppressed, status = _scan_member_stream(
                    member_stream,
                    member_display,
                    member.size,
                    rules,
                    allowlists,
                    max_bytes,
                    depth,
                    findings,
                    skips,
                )
            suppressed += member_suppressed
            if status == "finding limit reached":
                return suppressed, status
    return suppressed, None


def _scan_ar_stream(stream, display, rules, allowlists, max_bytes, depth, findings, skips):
    """Expand an ``ar`` archive (the ``.deb`` container) member by member."""
    suppressed = 0
    if stream.read(8) != AR_MAGIC:
        raise ValueError("bad ar magic")
    while True:
        header = stream.read(AR_MEMBER_HEADER)
        if not header:
            break
        if len(header) < AR_MEMBER_HEADER or header[58:60] != b"`\n":
            raise ValueError("bad ar member header")
        raw_name = header[:16].decode("ascii", "replace").strip()
        try:
            data_size = int(header[48:58].decode("ascii", "replace").strip() or "0")
        except ValueError as error:
            raise ValueError("bad ar member size") from error
        content_size = data_size
        if raw_name == "//":
            member_name = None
        elif raw_name.startswith("#1/"):
            name_length = int(raw_name[3:] or "0")
            name_bytes = stream.read(name_length)
            if len(name_bytes) != name_length:
                raise ValueError("truncated ar member name")
            member_name = name_bytes.decode("utf-8", "replace").rstrip("\x00")
            content_size -= name_length
            if content_size < 0:
                raise ValueError("bad ar member size")
        elif raw_name.endswith("/"):
            member_name = raw_name[:-1]
        else:
            member_name = raw_name
        if member_name is None:
            _discard(_LimitedReader(stream, content_size))
        else:
            reader = _LimitedReader(stream, content_size)
            member_display = f"{display}!{_clean_member_name(member_name)}"
            member_suppressed, status = _scan_member_stream(
                reader,
                member_display,
                content_size,
                rules,
                allowlists,
                max_bytes,
                depth,
                findings,
                skips,
            )
            _discard(reader)
            suppressed += member_suppressed
            if status == "finding limit reached":
                return suppressed, status
        if data_size % 2:
            stream.read(1)
    return suppressed, None


def _scan_container_stream(
    stream, kind, display, rules, allowlists, max_bytes, depth, findings, skips
):
    """Expand one container and scan its members; never extracts to disk."""
    suppressed = 0
    try:
        if kind == "ar":
            return _scan_ar_stream(
                stream, display, rules, allowlists, max_bytes, depth, findings, skips
            )
        if kind == "zip":
            return _scan_zip_stream(
                stream, display, rules, allowlists, max_bytes, depth, findings, skips
            )
        if kind == "tar":
            return _scan_tar_stream(
                stream, display, rules, allowlists, max_bytes, depth, findings, skips
            )
        decompressed = _decompressed_stream(stream, kind)
        prefix = decompressed.read(ARCHIVE_SNIFF_BYTES)
        reader = _PrefixedReader(prefix, decompressed)
        if _sniff_archive(prefix) == "tar":
            return _scan_tar_stream(
                reader, display, rules, allowlists, max_bytes, depth, findings, skips
            )
        member_suppressed, status = _scan_stream(
            reader, display, rules, allowlists, max_bytes, findings
        )
        suppressed += member_suppressed
        return suppressed, status
    except (
        zipfile.BadZipFile,
        tarfile.TarError,
        EOFError,
        OSError,
        ValueError,
        NotImplementedError,
        RuntimeError,
        zlib.error,
        lzma.LZMAError,
    ) as error:
        skips.append(f"{display} could not be expanded ({type(error).__name__})")
        return suppressed, None


def scan_file(path, rules, allowlists, max_bytes=DEFAULT_MAX_FILE_BYTES):
    """Stream one file (expanding container members) and return the result tuple."""
    findings = []
    size = path.stat().st_size
    if size > max_bytes:
        return findings, 0, f"file exceeds --max-file-bytes ({size} bytes)", size
    display = _display_path(path)
    skips = []
    with path.open("rb") as handle:
        header = handle.read(ARCHIVE_SNIFF_BYTES)
        kind = _sniff_archive(header)
        handle.seek(0)
        if kind is None:
            suppressed, status = _scan_stream(
                handle, display, rules, allowlists, max_bytes, findings
            )
        else:
            suppressed, status = _scan_container_stream(
                handle, kind, display, rules, allowlists, max_bytes, 0, findings, skips
            )
    if status:
        skips.append(status)
    unique = []
    for reason in skips:
        if reason not in unique:
            unique.append(reason)
    return findings, suppressed, "; ".join(unique) or None, size


def scan(targets, rules, allowlists, max_bytes=DEFAULT_MAX_FILE_BYTES):
    files_scanned = 0
    findings = []
    skipped = []
    suppressed = 0
    total_bytes = 0
    for path in _target_files(targets):
        file_findings, file_suppressed, file_skipped, size = scan_file(
            path, rules, allowlists, max_bytes=max_bytes
        )
        files_scanned += 1
        total_bytes += size
        suppressed += file_suppressed
        # Retain findings even when scanning stopped early (finding limit or
        # oversize): dropping them would turn a real leak into a clean exit.
        findings.extend(file_findings)
        if file_skipped:
            skipped.append({"path": _display_path(path), "reason": file_skipped})
    findings.sort(key=lambda item: (item["path"], item["line"], item["rule"]))
    return {
        "files_scanned": files_scanned,
        "bytes_scanned": total_bytes,
        "findings": findings,
        "skipped": skipped,
        "suppressed": suppressed,
    }


def _summary_line(result):
    counts = {"secret": 0, "private-data": 0, "custom": 0}
    for finding in result["findings"]:
        counts[finding["category"]] = counts.get(finding["category"], 0) + 1
    return (
        f"files={result['files_scanned']} findings={len(result['findings'])} "
        f"secrets={counts['secret']} private_data={counts['private-data']} "
        f"custom={counts['custom']} suppressed={result['suppressed']}"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("targets", nargs="+", help="Files or directories to scan.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Gitleaks TOML config.")
    parser.add_argument("--json", default=None, help="Write a JSON report to this path.")
    parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=DEFAULT_MAX_FILE_BYTES,
        help="Skip files larger than this many bytes.",
    )
    args = parser.parse_args(argv)

    if args.max_file_bytes <= 0:
        parser.error("--max-file-bytes must be positive")

    config_path = Path(args.config)
    if not config_path.is_file():
        print(f"RELEASE_ARTIFACT_SCAN=ERROR config not found: {config_path}", file=sys.stderr)
        return 2
    try:
        config = parse_gitleaks_config(config_path.read_text(encoding="utf-8"))
        rules = _compile_rules(config["rules"])
        result = scan(args.targets, rules, config["allowlists"], max_bytes=args.max_file_bytes)
    except ConfigError as error:
        print(f"RELEASE_ARTIFACT_SCAN=ERROR {error}", file=sys.stderr)
        return 2
    for warning in config["warnings"]:
        print(f"RELEASE_ARTIFACT_SCAN=WARN {warning}", file=sys.stderr)

    report = {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "config": _display_path(config_path),
        "rules": len(rules),
        "allowlists": len(config["allowlists"]),
        "summary": {
            "files_scanned": result["files_scanned"],
            "bytes_scanned": result["bytes_scanned"],
            "findings": len(result["findings"]),
            "suppressed": result["suppressed"],
            "skipped": len(result["skipped"]),
        },
        "findings": result["findings"],
        "skipped": result["skipped"],
    }
    if args.json:
        destination = Path(args.json)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if result["skipped"]:
        reasons = ", ".join(sorted({item["reason"] for item in result["skipped"]}))
        print(
            f"RELEASE_ARTIFACT_SCAN=WARN {len(result['skipped'])} file(s) were not "
            f"scanned completely ({reasons}); content is unverified",
            file=sys.stderr,
        )
    if result["findings"]:
        print(f"RELEASE_ARTIFACT_SCAN=FINDINGS {_summary_line(result)}", file=sys.stderr)
        for finding in result["findings"][:20]:
            print(
                f"  {finding['category']} {finding['rule']} "
                f"{finding['path']}:{finding['line']} (length {finding['match_length']})",
                file=sys.stderr,
            )
        if len(result["findings"]) > 20:
            print(f"  ... {len(result['findings']) - 20} more finding(s)", file=sys.stderr)
        return 1
    print(f"RELEASE_ARTIFACT_SCAN=CLEAN {_summary_line(result)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
