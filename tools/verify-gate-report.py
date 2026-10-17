#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Publish a verify-project run's coverage as the AEH gate report.

``tools/verify-project.sh`` already writes a machine-readable skip manifest
through ``tools/verify-skip-manifest.py``. AEH's quality contract
(``.aeh/quality.json``) declares ``.hub/gate-report.json`` next to it, and the
Hub ingests that report after the run: a required check named in ``skipped`` or
``not_run`` blocks the gate, and a declared report that is never produced blocks
it too. This helper reads the skip manifest (it never re-parses the suite logs
and never re-derives a skip) and writes the report, so a green run cannot hide a
lane it did not run and a red run still states exactly what was missed.

The report is runtime state under ``.hub/``: it is git-ignored, never source and
never part of the published snapshot.

Usage:
  tools/verify-gate-report.py --root DIR --manifest PATH --out PATH
      [--covered-gate NAME]... [--not-run CHECK|REASON]...
      [--artifact NAME|PATH]... [--limitation TEXT]...
      [--evidence-class CLASS] [--runner-label LABEL]

Exit status: 0 the report was written, 1 the manifest could not be read or the
report could not be written (fail closed).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import pathlib
import sys

# Every skipped/not_run entry needs a non-empty reason. The Hub treats an entry
# without one as malformed data (FAILED, never PASS), and a skip with a blank
# reason is exactly the silent gap the manifest exists to prevent.
NO_REASON = "the runner reported no reason for this skip"


def parse_pairs(values: list[str], flag: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for raw in values:
        name, separator, reason = raw.partition("|")
        name, reason = name.strip(), reason.strip()
        if not separator or not name or not reason:
            raise SystemExit(f"{flag} expects CHECK|REASON with both parts non-empty: {raw!r}")
        pairs.append((name, reason))
    return pairs


def manifest_skips(manifest: dict, runner: str) -> tuple[list[dict], list[dict]]:
    """Turn one runner's manifest section into report entries.

    Returns (entries, gaps). ``gaps`` names skips the runner counted but did not
    report per test, so an unnamed skip is still visible instead of being
    silently dropped from the report.
    """
    section = (manifest.get("skips") or {}).get(runner)
    if not isinstance(section, dict):
        return [], []
    entries: list[dict] = []
    gaps: list[dict] = []
    tests = section.get("tests")
    if isinstance(tests, list):
        for item in tests:
            if not isinstance(item, dict):
                continue
            name = str(item.get("test") or "").strip()
            if not name:
                continue
            reason = str(item.get("reason") or "").strip()
            entries.append({"check": name, "reason": reason or NO_REASON})
    counted, reported = section.get("count"), section.get("reported")
    if isinstance(counted, int) and isinstance(reported, int) and counted > reported:
        gaps.append({
            "check": f"{runner}-skips-counted-but-not-named",
            "reason": f"{counted - reported} skip(s) were counted by {runner} "
                      "but not reported per test",
        })
    return entries, gaps


def collect_artifacts(root: pathlib.Path, values: list[str]) -> tuple[list[dict], list[str]]:
    """Hash files this run really produced; a missing or escaping file is a gap.

    Nothing is invented: an artifact is listed only when the file exists under
    the project root at report time, and its sha256 is read from those bytes.
    """
    artifacts: list[dict] = []
    gaps: list[str] = []
    for raw in values:
        name, separator, path = raw.partition("|")
        name, path = name.strip(), path.strip()
        if not separator or not name or not path:
            raise SystemExit(f"--artifact expects NAME|PATH with both parts non-empty: {raw!r}")
        target = (root / path).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            gaps.append(f"artifact {name} was not published: {path} is outside the project root")
            continue
        if not target.is_file():
            gaps.append(f"artifact {name} was not published: {path} does not exist")
            continue
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        artifacts.append({
            "name": name,
            "path": target.relative_to(root).as_posix(),
            "sha256": digest,
            "platform": f"{platform.system().lower()}-{platform.machine()}",
            "result": "PASS",
        })
    return artifacts, gaps


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--covered-gate", action="append", default=[])
    parser.add_argument("--not-run", action="append", default=[])
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--limitation", action="append", default=[])
    parser.add_argument("--evidence-class", default="UNVERIFIED")
    parser.add_argument("--runner-label", default="local")
    args = parser.parse_args(argv)

    root = pathlib.Path(args.root).resolve()
    try:
        manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as error:
        print(f"cannot read the skip manifest {args.manifest}: {error}", file=sys.stderr)
        return 1
    if not isinstance(manifest, dict):
        print(f"the skip manifest is not a JSON object: {args.manifest}", file=sys.stderr)
        return 1

    skipped: list[dict] = []
    gaps: list[str] = []
    for runner in ("python", "javascript"):
        entries, runner_gaps = manifest_skips(manifest, runner)
        skipped.extend(entries)
        gaps.extend(gap["reason"] for gap in runner_gaps)
    skipped.extend({"check": "unreported-skip", "reason": reason} for reason in gaps)

    not_run = [{"check": name, "reason": reason}
               for name, reason in parse_pairs(args.not_run, "--not-run")]
    artifacts, artifact_gaps = collect_artifacts(root, args.artifact)

    limitations = list(args.limitation) + artifact_gaps
    report = {
        "skipped": skipped,
        "not_run": not_run,
        "covered_gates": list(args.covered_gate),
        "artifacts": artifacts,
        "runner": {
            "kind": "local",
            "os": platform.system().lower(),
            "arch": platform.machine(),
            "label": args.runner_label,
        },
        "evidence_class": args.evidence_class,
        "limitations": limitations,
    }
    out = pathlib.Path(args.out)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as error:
        print(f"cannot write the gate report {out}: {error}", file=sys.stderr)
        return 1

    print(f"GATE_REPORT={out} skipped={len(skipped)} not_run={len(not_run)} "
          f"artifacts={len(artifacts)} evidence_class={report['evidence_class']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
