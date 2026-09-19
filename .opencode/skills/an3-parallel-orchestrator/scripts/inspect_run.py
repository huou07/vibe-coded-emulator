#!/usr/bin/env python3
"""Read-only inspector and recovery advisor for orchestration runs.

Usage:
  inspect_run.py list [--repo P]
  inspect_run.py [--run-id ID] [--repo P]
  inspect_run.py recover --run-id ID [--repo P]

`recover` never performs destructive recovery: it reports the baseline, session
lifecycle, branches/worktrees, dirty state, commits, QA/integration state,
resource leases, staging state and the safe next actions.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import orchestrator_lib as lib  # noqa: E402

CFG = lib.load_config()
BACKLOG = CFG.get("backlog", {})
_STATE_LEGACY = {"candidate": "READY_FOR_REVIEW", "integrated": "INTEGRATED", "rejected": "REJECTED"}


def read_optional(rdir, name, default):
    path = os.path.join(rdir, name)
    if os.path.exists(path):
        try:
            return lib.read_json(path)
        except ValueError:
            return default
    return default


def _leases(repo, run_id):
    root = lib.locks_dir(repo)
    leases = []
    if not os.path.isdir(root):
        return leases
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        lease_path = os.path.join(path, "lease.json")
        if not os.path.isdir(path) or not os.path.exists(lease_path):
            continue
        try:
            lease = lib.read_json(lease_path)
        except ValueError:
            continue
        if lease.get("runId") == run_id:
            leases.append(lease)
    return leases


def _candidate_counts(candidates):
    counts = {stage: 0 for stage in CFG.get("candidateStages", [])}
    for entries in (candidates or {}).values():
        if not entries:
            continue
        stage = entries[-1].get("stage") or _STATE_LEGACY.get(entries[-1].get("state", ""), "WORKING")
        counts[stage] = counts.get(stage, 0) + 1
    return counts


def _pressure(counts):
    ready = counts.get("READY_FOR_REVIEW", 0)
    qa = counts.get("IN_QA", 0)
    integration = counts.get("REVIEWED", 0)
    reasons = []
    if ready > BACKLOG.get("readyForReview", 3):
        reasons.append("READY_FOR_REVIEW backlog %d" % ready)
    if qa > BACKLOG.get("qaQueue", 3):
        reasons.append("QA queue %d" % qa)
    if integration > BACKLOG.get("integrationQueue", 3):
        reasons.append("integration queue %d" % integration)
    return ("HIGH" if len(reasons) >= 2 else ("MEDIUM" if reasons else "LOW")), reasons


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
        log_path = os.path.join(rdir, "sessions", "%s.ndjson" % domain)
        entry["sessionState"] = lib.session_state(session, log_path)
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
    counts = _candidate_counts(candidates)
    pressure, reasons = _pressure(counts)
    branch = manifest.get("integrationTargetBranch")
    target_now = lib.resolve_head(repo, "refs/heads/%s" % branch) if branch else None
    target_start = manifest.get("targetHeadAtStart")
    return {
        "runId": run_id,
        "runDir": rdir,
        "overallStatus": manifest.get("overallStatus"),
        "statuses": status.get("statuses", manifest.get("statuses")),
        "baseSha": manifest.get("baseSha"),
        "targetBranch": branch,
        "targetHeadAtStart": target_start,
        "targetHeadNow": target_now,
        "targetMoved": bool(target_now and target_start and target_now != target_start),
        "integrationHead": manifest.get("integrationHead"),
        "stagingHead": manifest.get("stagingHead"),
        "model": manifest.get("model"),
        "modelVerified": manifest.get("modelVerified"),
        "tasks": tasks,
        "sessions": session_view,
        "candidates": candidates,
        "candidateCounts": counts,
        "pressure": pressure,
        "pressureReasons": reasons,
        "leases": _leases(repo, run_id),
        "evidence": evidence,
        "unresolvedGaps": manifest.get("unresolvedGaps", []),
    }


def _next_actions(view):
    actions = []
    for entry in view["sessions"]:
        state = entry.get("sessionState")
        domain = entry.get("domain")
        if state == "SESSION_RESUMABLE":
            actions.append("resume worker %s (session %s) with a concise checkpoint"
                           % (domain, entry.get("sessionId")))
        elif state == "SESSION_UNKNOWN":
            actions.append("inspect worker %s log; if the session id is unusable, restart a worker "
                           "in %s with a checkpoint" % (domain, entry.get("worktree")))
        elif entry.get("worktreeDirty"):
            actions.append("worker %s has a dirty worktree %s; inspect before cleanup"
                           % (domain, entry.get("worktree")))
    for lease in view["leases"]:
        actions.append("check/release lease %s held by %s" % (lease.get("resource"), lease.get("ownerSession")))
    if view["candidateCounts"].get("REVIEWED"):
        actions.append("continue integration of %d reviewed candidate(s)"
                       % view["candidateCounts"]["REVIEWED"])
    if view["candidateCounts"].get("READY_FOR_REVIEW"):
        actions.append("route %d candidate(s) to QA" % view["candidateCounts"]["READY_FOR_REVIEW"])
    if view["targetMoved"]:
        actions.append("reconcile target branch movement (%s moved from %s to %s) before promotion"
                       % (view["targetBranch"], (view["targetHeadAtStart"] or "")[:12],
                          (view["targetHeadNow"] or "")[:12]))
    if not actions:
        actions.append("no recovery action required")
    return actions


def cmd_recover(args):
    repo = lib.find_repo_root(args.repo)
    run_id = args.run_id
    if not run_id:
        root = lib.state_root(repo)
        runs = ([n for n in sorted(os.listdir(root))
                 if os.path.isfile(os.path.join(root, n, "manifest.json"))]
                if os.path.isdir(root) else [])
        if not runs:
            lib.fail("no runs found", code=4, stateRoot=root)
        run_id = runs[-1]
    if not os.path.isdir(lib.run_dir(repo, run_id)):
        lib.fail("unknown run %s" % run_id, code=4)
    view = describe_run(repo, run_id)
    dead = all(s.get("sessionState") == "SESSION_DEAD" for s in view["sessions"]) if view["sessions"] else False
    active = [s for s in view["sessions"] if s.get("sessionState") == "PROCESS_RUNNING"]
    if view["overallStatus"] in ("COMPLETE", "CANCELLED"):
        state = view["overallStatus"]
    elif view["overallStatus"] == "FAILED":
        state = "FAILED"
    elif active or any(s.get("sessionState") in ("SESSION_RESUMABLE", "SESSION_UNKNOWN")
                       for s in view["sessions"]) or view["candidateCounts"].get("REVIEWED"):
        state = "RECOVERABLE"
    elif dead:
        state = "STALLED"
    else:
        state = "RECOVERABLE"
    lib.emit({"ok": True, "run": run_id, "state": state, "view": view,
              "nextActions": _next_actions(view),
              "destructiveRecovery": "never automatic; inspect and act explicitly"})


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
    sub.add_parser("show").set_defaults(func=cmd_show)
    p = sub.add_parser("recover")
    p.add_argument("--run-id")
    p.set_defaults(func=cmd_recover)
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
