#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the explicit Python test contract for the sanitized core-only source."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
MANIFEST = TESTS / "core-only-test-manifest.json"


def read_contract():
    policy = json.loads(MANIFEST.read_text(encoding="utf-8"))
    included = policy.get("included")
    excluded = policy.get("excluded")
    if not isinstance(included, list) or not isinstance(excluded, dict):
        raise ValueError("core-only test manifest needs included[] and excluded{}")
    if any(not isinstance(name, str) or not name.startswith("test_") for name in included):
        raise ValueError("included test modules must be test_*.py module names")
    if any(
        not isinstance(name, str)
        or not name.startswith("test_")
        or not isinstance(reason, str)
        or not reason.strip()
        for name, reason in excluded.items()
    ):
        raise ValueError("every excluded test module needs a non-empty reason")
    if len(included) != len(set(included)):
        raise ValueError("included test module list contains duplicates")
    overlap = set(included) & set(excluded)
    if overlap:
        raise ValueError(f"test modules are both included and excluded: {sorted(overlap)}")

    discovered = {path.stem for path in TESTS.glob("test_*.py")}
    classified = set(included) | set(excluded)
    missing = sorted(discovered - classified)
    stale = sorted(classified - discovered)
    if missing or stale:
        raise ValueError(
            "core-only test inventory mismatch; "
            f"unclassified={missing}, missing_files={stale}"
        )
    return sorted(included), excluded


def main():
    try:
        included, excluded = read_contract()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"CORE_ONLY_TEST_CONTRACT=FAIL {error}", file=sys.stderr)
        return 2

    sys.path.insert(0, str(TESTS))
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for module in included:
        suite.addTests(loader.loadTestsFromName(module))

    print(
        f"CORE_ONLY_TEST_CONTRACT=PASS included_modules={len(included)} "
        f"excluded_modules={len(excluded)}"
    )
    for module, reason in sorted(excluded.items()):
        print(f"CORE_ONLY_TEST_EXCLUDED {module}: {reason}")

    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
