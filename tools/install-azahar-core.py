#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Install a rebuilt browser 3DS core bundle into the tracked runtime.

`tools/build-azahar-wasm.sh` produces `azahar-thread-wasm.data`; this puts it
where the web server, the desktop bundle and the Android mirror all read it, and
re-pins `native-offline/shared/web-runtime-lock.json` so the server's
lock-verified delivery keeps deciding what is served. The build report is
rewritten with a fresh `buildStart`, which is the version a returning browser
compares before it reuses a cached core.

Usage:
    tools/install-azahar-core.py <bundle.data> [--version 2.1.0]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDORED = ROOT / "native-offline/src-tauri/gen/android/app/src/main/assets/emulatorjs"
LOCK = ROOT / "native-offline/shared/web-runtime-lock.json"
CORE_KEY = "latest/data-v2/cores/azahar-thread-wasm.data"
DATA_V2 = "latest/data-v2/"
RUNTIME_DIR = VENDORED / "latest" / "data-v2"
REPORT_KEY = "latest/data-v2/cores/reports/azahar.json"
EXPECTED = {"azahar_libretro.js", "azahar_libretro.wasm", "core.json", "license.txt", "build.json"}


def die(message: str) -> None:
    raise SystemExit(f"INSTALL_AZAHAR_CORE=FAIL {message}")


def members(bundle: Path) -> set[str]:
    try:
        listed = subprocess.run(["7z", "l", "-slt", str(bundle)], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        die(f"cannot list the bundle with 7z: {error}")
    names = set()
    for line in listed.stdout.splitlines():
        if line.startswith("Path = "):
            names.add(line[len("Path = "):].strip().lstrip("./"))
    names.discard(str(bundle))
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--version", default="2.1.0")
    args = parser.parse_args()

    if not args.bundle.is_file():
        die(f"bundle not found: {args.bundle}")
    found = members(args.bundle)
    if found != EXPECTED:
        die(f"unexpected bundle members: {sorted(found)}")

    payload = args.bundle.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    target = RUNTIME_DIR / CORE_KEY.split(DATA_V2, 1)[1]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    report = {
        "core": "azahar",
        "buildStart": now,
        "buildEnd": now,
        "options": {"requireThreads": True, "requiresWebgl2": True, "supportsMouse": True, "useKeyboard": True},
    }
    report_path = RUNTIME_DIR / REPORT_KEY.split(DATA_V2, 1)[1]
    report_path.write_text(json.dumps(report), encoding="utf-8")

    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    lock[CORE_KEY] = digest
    lock[REPORT_KEY] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    LOCK.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("INSTALL_AZAHAR_CORE=PASS")
    print(f"AZAHAR_BUNDLE_VERSION={args.version}")
    print(f"AZAHAR_CORE_SHA256={digest}")
    print(f"AZAHAR_CORE_BYTES={len(payload)}")
    print(f"AZAHAR_CORE_PATH={target.relative_to(ROOT)}")
    print(f"AZAHAR_REPORT_BUILDSTART={now}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
