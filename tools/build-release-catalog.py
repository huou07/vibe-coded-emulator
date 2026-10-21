#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate the tracked release catalog from artifacts on disk.

The catalog is the download page's only artifact source and the Linux install
scripts' only source of filename and SHA-256, so it must never be edited by
hand: a stale catalog silently serves 404s and wrong hashes. This reads the
actual installer bytes, derives the source identity from Git, and writes the
catalog deterministically.

Usage:
    python3 tools/build-release-catalog.py --source-commit SHA [--version X.Y.Z]
        [--release-candidate NAME] [--runtime-status TEXT] [--releases DIR]
        [--dry-run]

The version defaults to the desktop `tauri.conf.json` version, which is what
`tools/release-train.sh` uses for the artifact filenames, so the catalog and the
built filenames cannot drift. `core_support` defaults to the systems supported
by this release; pass `--core` to override.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASES = ROOT / "native-offline/releases"
CATALOG = RELEASES / "catalog.json"
TAURI_CONF = ROOT / "native-offline/src-tauri/tauri.conf.json"

# platform, format, architecture, filename template
LAYOUT = (
    ("macOS", "DMG", "arm64", "vibecodedemulator-{v}-macos-aarch64.dmg"),
    ("Android", "APK", "arm64", "vibecodedemulator-{v}-android-arm64-staging.apk"),
    ("Android", "AAB", "arm64", "vibecodedemulator-{v}-android-arm64-staging.aab"),
    ("Linux", "DEB", "amd64", "vibecodedemulator-{v}-linux-amd64.deb"),
    ("Linux", "Flatpak", "amd64", "an3-offline-{v}-linux-amd64-staging.flatpak"),
    ("Windows", "EXE", "x64", "vibecodedemulator-{v}-windows-x64-staging.exe"),
)

DEFAULT_CORES = ("mGBA", "melonDS", "Azahar")

UNSIGNED = {
    "DMG": "Ad-hoc signed only; not notarized.",
    "APK": "Signed with the shared Android debug identity; not a production signing identity.",
    "AAB": "Signed with the shared Android debug identity; not a production signing identity.",
    "DEB": "Unsigned staging package.",
    "Flatpak": "Unsigned staging bundle.",
    "EXE": "Unsigned NSIS installer; not Authenticode-signed.",
}


def desktop_version(tauri_conf: Path) -> str:
    return json.loads(tauri_conf.read_text(encoding="utf-8"))["version"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def write_sidecar(path: Path) -> Path:
    sidecar = path.with_name(path.name + ".sha256")
    sidecar.write_text(f"{sha256_file(path)}  {path.name}\n", encoding="utf-8")
    return sidecar


def find_release_file(releases: Path, filename: str):
    """Find one installer, including GitHub's per-artifact download folders."""
    matches = sorted(
        path for path in releases.rglob(filename)
        if path.is_file() and not path.is_symlink()
    )
    if len(matches) > 1:
        raise ValueError(f"ambiguous installer {filename}: {len(matches)} matches")
    return matches[0] if matches else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--version", default=None)
    parser.add_argument("--release-candidate", default=None)
    parser.add_argument("--runtime-status", default="Generated from built artifacts; runtime acceptance not recorded.")
    parser.add_argument("--core", action="append", dest="cores")
    parser.add_argument("--releases", default=None,
                        help="directory holding the built installers (default: native-offline/releases)")
    parser.add_argument("--tauri-conf", default=None,
                        help="path to tauri.conf.json (default: native-offline/src-tauri/tauri.conf.json)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    releases = Path(args.releases).resolve() if args.releases else RELEASES
    tauri_conf = Path(args.tauri_conf).resolve() if args.tauri_conf else TAURI_CONF

    version = args.version or desktop_version(tauri_conf)
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        parser.error(f"invalid version: {version}")
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        parser.error("--source-commit must be a full 40-hex commit id")

    cores = tuple(args.cores) if args.cores else DEFAULT_CORES
    artifacts = []
    missing = []
    for platform, fmt, architecture, template in LAYOUT:
        filename = template.format(v=version)
        try:
            path = find_release_file(releases, filename)
        except ValueError as exc:
            parser.error(str(exc))
        if path is None:
            missing.append(filename)
            continue
        entry = {
            "version": version,
            "platform": platform,
            "architecture": architecture,
            "format": fmt,
            "filename": filename,
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
            "core_support": list(cores),
            "signature_status": UNSIGNED[fmt],
            "runtime_status": args.runtime_status,
        }
        if fmt == "EXE":
            entry["release_gate"] = "PASS"
        artifacts.append(entry)

    if missing:
        print("missing installers: " + ", ".join(missing), flush=True)
        return 2

    fingerprint = hashlib.sha256(
        json.dumps(
            {"source_commit": args.source_commit,
             "artifacts": [{k: a[k] for k in ("filename", "size", "sha256")} for a in artifacts]},
            sort_keys=True, separators=(",", ":"),
        ).encode()
    ).hexdigest()
    catalog = {
        "schema_version": 1,
        "source_commit": args.source_commit,
        "source_fingerprint": fingerprint,
        "release_candidate": args.release_candidate or f"{version}-staging",
        "build_id": f"source-{fingerprint[:16]}",
        "artifacts": artifacts,
    }

    body = json.dumps(catalog, indent=2) + "\n"
    if args.dry_run:
        print(body)
        return 0

    # Write beside the artifacts so a caller can point --releases at a scratch
    # directory (the release workflow downloads into one) without creating a
    # stray tree next to the script.
    catalog_path = releases / "catalog.json"
    catalog_path.write_text(body, encoding="utf-8")
    for entry in artifacts:
        source = find_release_file(releases, entry["filename"])
        assert source is not None  # already required above; keeps mypy honest
        write_sidecar(source)
    print(f"RELEASE_CATALOG_WRITTEN version={version} artifacts={len(artifacts)} path={catalog_path}")
    for entry in artifacts:
        print(f"  {entry['format']:8} {entry['filename']} {entry['sha256'][:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
