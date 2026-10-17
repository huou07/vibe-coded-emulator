#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Summarise a verify-project run's skips as machine-readable JSON.

A green source gate must not hide what it did not run: the ledger counted 20
Python skips and a handful of Node skips with no visible reason. This reads the
captured suite logs and prints one JSON object with the count and, where the
runner reports it, the test and reason for every skip.

Usage:
  tools/verify-skip-manifest.py --python-log PATH --node-log PATH [--out PATH]

Exit status: 0 manifest produced, 1 the logs could not be read (fail closed).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

# `test_name (module.Class.test_name) ... skipped 'reason'`, and the bare-function
# form `A sentence ... skipped 'reason'` that unittest prints for tests without a
# class locator.
PYTHON_SKIP = re.compile(r"^(?P<name>.+?)\s+\.\.\.\s+skipped(?:\s+'(?P<reason>.*)')?\s*$")
PYTHON_LOCATOR = re.compile(r"\s*\([^()]*\)\s*$")
# unittest's summary when verbosity is off.
PYTHON_SUMMARY = re.compile(r"(?:OK|FAILED) \(.*?skipped=(\d+).*?\)")
# Node's spec reporter: `﹣ test name (12ms) # reason` (U+FE63 dash, not ASCII).
NODE_SKIP = re.compile(r"^[\s]*[﹣–—]\s+(.+?)(?:\s+#\s+(.*))?$")
NODE_SUMMARY = re.compile(r"^[\s]*ℹ skipped (\d+)\s*$")
NODE_DURATION = re.compile(r"\s*\(\d+(?:\.\d+)?ms\)\s*$")


def read_lines(path: pathlib.Path) -> list[str] | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None


def parse_python(lines: list[str]) -> dict:
    tests: list[dict[str, str]] = []
    summary = 0
    for line in lines:
        match = PYTHON_SKIP.match(line.strip())
        if match:
            entry = {"test": PYTHON_LOCATOR.sub("", match.group("name")).strip()}
            if match.group("reason"):
                entry["reason"] = match.group("reason")
            tests.append(entry)
            continue
        found = PYTHON_SUMMARY.search(line)
        if found:
            summary = max(summary, int(found.group(1)))
    return {"count": max(summary, len(tests)), "reported": len(tests), "tests": tests}


def parse_node(lines: list[str]) -> dict:
    tests: list[dict[str, str]] = []
    summary = 0
    for line in lines:
        stripped = line.strip()
        found = NODE_SUMMARY.match(stripped)
        if found:
            summary = max(summary, int(found.group(1)))
            continue
        match = NODE_SKIP.match(line)
        if match and "skipped" not in match.group(1).lower():
            name = NODE_DURATION.sub("", match.group(1)).strip()
            entry = {"test": name}
            if match.group(2):
                entry["reason"] = match.group(2).strip()
            tests.append(entry)
    return {"count": max(summary, len(tests)), "reported": len(tests), "tests": tests}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-log", required=True)
    parser.add_argument("--node-log", required=True)
    parser.add_argument("--out")
    parser.add_argument("--revision", default="")
    args = parser.parse_args(argv)

    python_lines = read_lines(pathlib.Path(args.python_log))
    node_lines = read_lines(pathlib.Path(args.node_log))
    if python_lines is None or node_lines is None:
        print("cannot read the suite logs; refusing to report a skip manifest", file=sys.stderr)
        return 1

    manifest = {
        "gate": "verify-project",
        "revision": args.revision,
        "skips": {
            "python": parse_python(python_lines),
            "javascript": parse_node(node_lines),
        },
    }
    manifest["total"] = manifest["skips"]["python"]["count"] + manifest["skips"]["javascript"]["count"]

    payload = json.dumps(manifest, sort_keys=True)
    if args.out:
        try:
            pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(args.out).write_text(payload + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"cannot write the skip manifest: {exc}", file=sys.stderr)
            return 1
    print(f"VERIFY_SKIPS={payload}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
