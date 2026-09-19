#!/usr/bin/env python3
"""Read-only inspector for orchestration runs (works from any worktree).

Usage:
  inspect_run.py list [--repo P]
  inspect_run.py [--run-id ID] [--repo P] [--json]

Prints the manifest summary, task DAG, session liveness, worktree cleanliness,
candidate commits, leases, status dimensions and evidence files. Never modifies
anything, so it is always safe to run.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import orchestrator_lib as lib  # noqa: E402


def read_optional(rdir, name, default):
    path = os.path.join(rdir, name)
    if os.path.exists(path):
        try:
            return lib.read_json(path)
        except ValueError:
            return default
    return default


def describe_run(repo, run_id):
    rdir = lib.run_dir(repo, run_id)
    manifest = read_optional(rdir, "manifest.json", {})
    tasks = read_optional(rdir, "tasks.json", [])
    sessions = read_optional(rdir, "sessions.json", {})
    candidates = read_optional(rdir, "candidates.json", {})
    status = read_optional(rdir, "status.json", {})
    session_view = []
    for domain, session in (sessions or {}).items():
        entry = dict(session)
        entry["pidAlive"] = lib.is_pid_alive(session.get("pid"))
        wt = session.get("worktree")
        if wt and os.path.isdir(wt):
            porcelain = lib.run_git(repo, ["-C", wt, "status", "--porcelain"], check=False)
            entry["worktreeDirty"] = bool(porcelain.stdout.strip())
            head = lib.run_git(repo, ["-C", wt, "rev-parse", "HEAD"], check=False)
            entry["head"] = head.stdout.strip()
        else:
            entry["worktreeDirty"] = None
            entry["head"] = None
        session_view.append(entry)
    evidence_dir = os.path.join(rdir, "evidence")
    evidence = sorted(os.listdir(evidence_dir)) if os.path.isdir(evidence_dir) else []
    leases_root = lib.locks_dir(repo)
    leases = []
    if os.path.isdir(leases_root):
        for name in sorted(os.listdir(leases_root)):
            path = os.path.join(leases_root, name)
            if os.path.isdir(path) and os.path.exists(os.path.join(path, "lease.json")):
                lease = lib.read_json(os.path.join(path, "lease.json"))
                if lease.get("runId") == run_id:
                    leases.append(lease)
    return {
        "runId": run_id,
        "runDir": rdir,
        "overallStatus": manifest.get("overallStatus"),
        "statuses": status.get("statuses", manifest.get("statuses")),
        "baseSha": manifest.get("baseSha"),
        "targetBranch": manifest.get("integrationTargetBranch"),
        "integrationHead": manifest.get("integrationHead"),
        "stagingHead": manifest.get("stagingHead"),
        "model": manifest.get("model"),
        "modelVerified": manifest.get("modelVerified"),
        "tasks": tasks,
        "sessions": session_view,
        "candidates": candidates,
        "leases": leases,
        "evidence": evidence,
        "unresolvedGaps": manifest.get("unresolvedGaps", []),
    }


def cmd_list(args):
    repo = lib.find_repo_root(args.repo)
    root = lib.state_root(repo)
    runs = []
    if os.path.isdir(root):
        for name in sorted(os.listdir(root)):
            if os.path.isfile(os.path.join(root, name, "manifest.json")):
                runs.append(name)
    lib.emit({"ok": True, "stateRoot": root, "runs": runs})


def cmd_show(args):
    repo = lib.find_repo_root(args.repo)
    run_id = args.run_id
    if not run_id:
        root = lib.state_root(repo)
        candidates = []
        if os.path.isdir(root):
            candidates = [n for n in sorted(os.listdir(root))
                          if os.path.isfile(os.path.join(root, n, "manifest.json"))]
        if not candidates:
            lib.fail("no runs found", code=4, stateRoot=root)
        run_id = candidates[-1]
    if not os.path.isdir(lib.run_dir(repo, run_id)):
        lib.fail("unknown run %s" % run_id, code=4)
    lib.emit({"ok": True, **describe_run(repo, run_id)})


def build_parser():
    parser = argparse.ArgumentParser(description="Inspect AN3 orchestrator runs")
    parser.add_argument("--repo", default=None)
    parser.add_argument("--run-id")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("list").set_defaults(func=cmd_list)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "func", None):
        args.func = cmd_show
    try:
        args.func(args)
    except lib.OrchestratorError as exc:
        lib.fail(exc.message, code=exc.code, **exc.detail)


if __name__ == "__main__":
    main()
