#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Remove one personal contact from Eden's embedded SMAA shader attribution.

The copyright year, author name, and SPDX license identifier are preserved.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

COPYRIGHT = "// SPDX-FileCopyrightText: 2013 Jose I. Echevarria"
CONTACT_LINE = re.compile(
    rf"^({re.escape(COPYRIGHT)}) \([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{{2,}}\)$",
    re.MULTILINE,
)
CLEAN_LINE = re.compile(rf"^{re.escape(COPYRIGHT)}$", re.MULTILINE)
LICENSE_LINE = "// SPDX-License-Identifier: MIT"


def sanitize(path: Path) -> bool:
    if path.name != "opengl_smaa.glsl":
        raise ValueError("expected the pinned SMAA shader source")
    text = path.read_text(encoding="utf-8")
    if text.count(LICENSE_LINE) != 1:
        raise ValueError("pinned SMAA license attribution changed")

    sanitized, count = CONTACT_LINE.subn(r"\1", text)
    if count == 1:
        path.write_text(sanitized, encoding="utf-8")
        return True
    if count == 0 and len(CLEAN_LINE.findall(text)) == 1:
        return False
    raise ValueError("pinned SMAA copyright attribution changed")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: sanitize-eden-shader-attribution.py opengl_smaa.glsl", file=sys.stderr)
        return 2
    try:
        changed = sanitize(Path(argv[0]))
    except (OSError, ValueError) as error:
        print(f"Eden shader attribution check failed: {error}", file=sys.stderr)
        return 1
    status = "REMOVED" if changed else "ALREADY_CLEAN"
    print(f"EDEN_SHADER_PERSONAL_CONTACT={status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
