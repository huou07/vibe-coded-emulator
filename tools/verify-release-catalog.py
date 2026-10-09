#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify the exact staging publication set and portable SHA-256 sidecars."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(root):
    release = root / "native-offline/releases"
    catalog = json.loads((release / "catalog.json").read_text())
    required = {"DMG", "APK", "DEB", "Flatpak"}
    found = set()
    filenames = []
    for item in catalog["artifacts"]:
        name = item.get("filename")
        if not name:
            continue
        if Path(name).name != name or name in filenames:
            raise ValueError("Invalid or duplicate artifact filename")
        path = release / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing regular installer: {name}")
        digest = sha256(path)
        if path.stat().st_size != item["size"] or digest != item["sha256"]:
            raise ValueError(f"Catalog byte mismatch: {name}")
        if (release / (name + ".sha256")).read_text().strip() != f"{digest}  {name}":
            raise ValueError(f"SHA-256 sidecar mismatch: {name}")
        if item["format"] == "EXE" and item.get("release_gate") != "PASS":
            raise ValueError("Windows must pass its native release gate before publication")
        found.add(item["format"])
        filenames.append(name)
    if not required.issubset(found):
        raise ValueError("A required fresh staging platform is missing")
    return filenames


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-filenames", action="store_true")
    args = parser.parse_args()
    names = verify(Path(__file__).resolve().parents[1])
    print("\n".join(names) if args.print_filenames else f"RELEASE_CATALOG=PASS ({len(names)} installers)")
