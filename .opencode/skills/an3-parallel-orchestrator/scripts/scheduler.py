#!/usr/bin/env python3
"""Deterministic scheduling helpers: shared-file overlap and DAG readiness.

Usage:
  scheduler.py overlap --tasks-file tasks.json [--repo P]
  scheduler.py overlap --tasks '<json array>' [--repo P]

Each task: {"id","class","owner","modules":[...],"dependsOn":[...]}.
Write classes are S and W; A and I do not compete for a worktree.

Output recommends PARALLEL_OK / CONTRACT_FIRST / SERIALIZE per write pair and
lists the ready frontier for the given `--done` task ids. Deterministic only:
no model judgement, no dynamic scheduling engine.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import orchestrator_lib as lib  # noqa: E402

CFG = lib.load_config()
CENTRAL = CFG.get("centralContracts", [])
WRITE_CLASSES = {"S", "W"}


def _central_conflicts(modules):
    hits = []
    for module in modules or []:
        for pattern in CENTRAL:
            if lib.paths_overlap(module, pattern):
                hits.append({"module": module, "contract": pattern})
    return hits


def _shared_modules(a, b):
    am = set(a.get("modules") or [])
    bm = set(b.get("modules") or [])
    exact = sorted(am & bm)
    overlap = []
    for x in am:
        for y in bm:
            if x != y and lib.paths_overlap(x, y):
                overlap.append([x, y])
    return exact, overlap


def _ready(tasks, done):
    done = set(done)
    ready = []
    for task in tasks:
        if task.get("id") in done:
            continue
        deps = task.get("dependsOn") or []
        if all(d in done for d in deps):
            ready.append(task.get("id"))
    return sorted(ready)


def cmd_overlap(args):
    repo = lib.find_repo_root(args.repo)
    if args.tasks_file:
        with open(args.tasks_file, "r", encoding="utf-8") as handle:
            tasks = json.load(handle)
    else:
        tasks = json.loads(args.tasks)
    if not isinstance(tasks, list):
        lib.fail("tasks must be a JSON array", code=64)
    writers = [t for t in tasks if t.get("class") in WRITE_CLASSES]
    pairs = []
    for i in range(len(writers)):
        for j in range(i + 1, len(writers)):
            a, b = writers[i], writers[j]
            exact, overlap = _shared_modules(a, b)
            central = _central_conflicts(a.get("modules") or []) + _central_conflicts(b.get("modules") or [])
            # a central contract touched by either writer is only a conflict if the
            # other writer plausibly touches it too (shared exact/overlap or same contract)
            central_keys = {c["contract"] for c in central}
            both_central = sorted({c["contract"] for c in _central_conflicts(a.get("modules") or [])}
                                  & {c["contract"] for c in _central_conflicts(b.get("modules") or [])})
            if both_central:
                recommendation = "SERIALIZE"
                reason = "both writers declare central contract(s): %s" % ", ".join(both_central)
            elif exact or overlap:
                recommendation = "CONTRACT_FIRST"
                reason = "shared module(s) %s" % json.dumps(exact or overlap)
            elif central_keys:
                recommendation = "PARALLEL_OK"
                reason = "central files touched but not shared between this pair"
            else:
                recommendation = "PARALLEL_OK"
                reason = "no declared overlap"
            pairs.append({"a": a.get("id"), "b": b.get("id"),
                          "sharedModules": exact, "moduleOverlap": overlap,
                          "centralContracts": sorted(central_keys),
                          "recommendation": recommendation, "reason": reason})
    serial = [{"a": p["a"], "b": p["b"], "reason": p["reason"]}
              for p in pairs if p["recommendation"] == "SERIALIZE"]
    contract_first = [{"a": p["a"], "b": p["b"], "reason": p["reason"]}
                      for p in pairs if p["recommendation"] == "CONTRACT_FIRST"]
    done = [x for x in (args.done or "").split(",") if x]
    lib.emit({"ok": True, "repo": repo, "pairs": pairs,
              "serialize": serial, "contractFirst": contract_first,
              "ready": _ready(tasks, done),
              "centralContracts": CENTRAL})


def build_parser():
    parser = argparse.ArgumentParser(description="AN3 orchestrator scheduler helpers")
    parser.add_argument("--repo", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("overlap")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--tasks-file")
    group.add_argument("--tasks")
    p.add_argument("--done", default="")
    p.set_defaults(func=cmd_overlap)
    return parser


def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except lib.OrchestratorError as exc:
        lib.fail(exc.message, code=exc.code, **exc.detail)


if __name__ == "__main__":
    main()
