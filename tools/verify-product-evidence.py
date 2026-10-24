#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check admissibility of one scoped product claim, never authenticity of its observations."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

REQUIRED = {
    "ui-journey": ("navigation", "recovery", "persistence"),
    "experimental": ("control", "discover", "activate", "interface", "behavior",
                     "disable", "restart", "off-services"),
    "gameplay": ("boot", "render", "input", "audio", "save-load", "exit", "relaunch"),
    "gameplay-performance": ("boot", "render", "input", "audio", "save-load",
                             "exit", "relaunch", "profile"),
    "packaged": ("first-launch", "import", "library", "gameplay", "input", "menu",
                 "save-load", "exit", "relaunch", "persistence", "window-or-touch"),
}
RUNTIMES = {"browser-ui", "browser-wasm", "native-test", "native-package", "android-device"}
SHA = re.compile(r"^[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9a-f]{40}$")


def evaluate(record, base, revision):
    failures, gaps = [], []
    def need(ok, reason):
        if not ok:
            gaps.append(reason)
    need(record.get("schema") == 1, "schema must be 1")
    need(bool(REVISION.fullmatch(str(record.get("revision", "")))), "exact source SHA missing")
    need(record.get("revision") == revision, "source revision differs from requested revision")
    need(record.get("dirty") is False, "dirty or unidentified source cannot establish acceptance")
    for key in ("build", "platform", "backend", "timestamp", "command"):
        need(isinstance(record.get(key), str) and bool(record[key].strip()), f"{key} missing")
    runtime, claim = record.get("runtime"), record.get("claim")
    need(runtime in RUNTIMES, "runtime must identify actual browser/native/device execution")
    need(claim in REQUIRED, "unknown product claim")
    if claim in ("experimental", "packaged"):
        need(runtime in ("native-package", "android-device"),
             "native feature/package acceptance needs the distribution app or installed Android package")
    if claim in ("gameplay", "gameplay-performance"):
        need(runtime in ("browser-wasm", "native-package", "android-device"),
             "gameplay needs the actual emulator runtime and product path")
        fixture = record.get("fixture") or {}
        need(fixture.get("kind") in ("homebrew", "purpose-built"),
             "synthetic animation/build smoke cannot establish gameplay")
        need(bool(SHA.fullmatch(str(fixture.get("sha256", "")))), "fixture checksum missing")
        need(bool(fixture.get("name")), "fixture identity missing")
    if runtime in ("native-package", "android-device"):
        package = record.get("package") or {}
        need(bool(SHA.fullmatch(str(package.get("sha256", "")))), "package checksum missing")
        need(package.get("revision") == revision, "package source differs from requested revision")
        need(package.get("distribution") is True, "test-only automation build is not distribution acceptance")

    checks = record.get("checks") or {}
    if not isinstance(checks, dict):
        checks = {}
        gaps.append("checks must be an object")
    for name in REQUIRED.get(claim, ()):
        check = checks.get(name) or {}
        result = check.get("result")
        if result == "FAIL":
            failures.append(f"{name}: observed failure")
        need(result == "PASS", f"{name}: {result or 'NOT RUN'}")
        for key in ("action", "observed"):
            need(isinstance(check.get(key), str) and bool(check[key].strip()), f"{name}: {key} missing")
        path = check.get("evidence")
        digest = str(check.get("sha256", ""))
        need(bool(path) and bool(SHA.fullmatch(digest)), f"{name}: evidence path/checksum missing")
        if path and SHA.fullmatch(digest):
            candidate = (base / path).resolve()
            # Evidence is local to the record; never follow arbitrary host paths.
            if not candidate.is_relative_to(base.resolve()):
                gaps.append(f"{name}: evidence escapes record directory")
            elif not candidate.is_file():
                gaps.append(f"{name}: evidence file missing")
            elif hashlib.sha256(candidate.read_bytes()).hexdigest() != digest:
                failures.append(f"{name}: evidence checksum mismatch")

    if claim == "gameplay-performance":
        perf = record.get("performance") or {}
        need(bool(perf.get("baseline")), "comparable measured baseline missing")
        need(bool(perf.get("conditions")), "hardware/browser/core/settings conditions missing")
        need(perf.get("representative") is True, "menu/diagnostic fixture is insufficient for representative gameplay")
        # Budgets come from a reviewed same-workload baseline; this tool supplies no FPS default.
        metrics = perf.get("metrics") or {}
        for name, direction in (("core_fps", "min"), ("presentation_p95_ms", "max"), ("audio_underruns", "max")):
            entry = metrics.get(name) or {}
            actual, limit = entry.get("actual"), entry.get("limit")
            numeric = lambda n: type(n) in (int, float) and math.isfinite(n) and n >= 0
            valid = numeric(actual) and numeric(limit) and entry.get("direction") == direction
            need(valid, f"{name}: measurement and baseline-derived limit missing")
            if valid and ((entry["direction"] == "min" and actual < limit)
                          or (entry["direction"] == "max" and actual > limit)):
                failures.append(f"{name}: {actual} violates {entry['direction']} {limit}")
        for name in ("unique_display_frames", "cpu", "gpu", "memory", "main_thread", "workers"):
            measurement = perf.get(name)
            need(isinstance(measurement, dict) and type(measurement.get("value")) in (int, float)
                 and math.isfinite(measurement["value"]) and measurement["value"] >= 0
                 and bool(measurement.get("unit")) and bool(measurement.get("method")),
                 f"{name}: numeric measurement/unit/method missing")
    verdict = "FAIL" if failures else "BLOCKED" if gaps else "PASS"
    return {"verdict": verdict, "claim": claim, "revision": record.get("revision"),
            "failures": failures, "gaps": gaps,
            "limit": "Evidence admissibility only; review observations and fixture suitability independently."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    try:
        record = json.loads(args.record.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise ValueError("record must be an object")
        result = evaluate(record, args.record.parent, args.revision)
    except (OSError, ValueError, TypeError, AttributeError) as error:
        result = {"verdict": "BLOCKED", "gaps": [str(error)]}
    print(json.dumps(result, sort_keys=True))
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[result["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
