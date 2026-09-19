#!/usr/bin/env python3
"""AN3 orchestrator run-state manager (deterministic, atomic, non-destructive).

Usage:
  orchestrator_state.py model
  orchestrator_state.py init --base-sha <sha> [--run-id <id>] [--goal ...] [--target-branch <b>] [--repo <path>] [--force]
  orchestrator_state.py show --run-id <id> [--repo <path>]
  orchestrator_state.py add-task --run-id <id> --json '<task json>' [--update]
  orchestrator_state.py add-session --run-id <id> --domain <d> --session-id <s> --worktree <w> --branch <b> [--pid N] [--model M]
  orchestrator_state.py set-candidate --run-id <id> --domain <d> [--commit <sha>] [--stage S] [--state candidate|integrated|rejected] [--note ...]
  orchestrator_state.py record-provenance --run-id <id> --domain <d> --worker-commit <sha> --integrated-commit <sha> --method <m> [--adapter-commit <sha>] [--reviewed-commit <sha>] [--integration-input-commit <sha>]
  orchestrator_state.py check-provenance --run-id <id>
  orchestrator_state.py pressure --run-id <id>
  orchestrator_state.py metrics --run-id <id>
  orchestrator_state.py check-target --run-id <id>
  orchestrator_state.py set-status --run-id <id> (--dimension D --value V | --overall V)
  orchestrator_state.py set-head --run-id <id> --field integrationHead|stagingHead --commit <sha>
  orchestrator_state.py check-model --run-id <id>
  orchestrator_state.py validate --run-id <id>

Every compound operation holds the run-level lock so concurrent workers cannot
lose updates across sessions.json / candidates.json / manifest.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import orchestrator_lib as lib  # noqa: E402

CFG = lib.load_config()
DIMENSIONS = CFG["statuses"]["dimensions"]
OVERALL = CFG["statuses"]["overall"]
STAGES = CFG.get("candidateStages", [])
METHODS = CFG.get("integrationMethods", [])
BACKLOG = CFG.get("backlog", {})

_STATE_LEGACY = {"candidate": "READY_FOR_REVIEW", "integrated": "INTEGRATED", "rejected": "REJECTED"}


def _read(rdir, name, default):
    path = os.path.join(rdir, name)
    return lib.read_json(path) if os.path.exists(path) else default


def cmd_model(_args: argparse.Namespace) -> None:
    lib.emit({"ok": True, "model": lib.CANONICAL_MODEL, "policy": "exclusive"})


def cmd_init(args: argparse.Namespace) -> None:
    repo = lib.find_repo_root(args.repo)
    run_id = args.run_id or lib.utc_now_iso().replace("-", "").replace(":", "").replace("T", "-")[:13]
    lib.validate_run_id(run_id)
    rdir = lib.run_dir(repo, run_id)
    manifest_path = os.path.join(rdir, "manifest.json")
    if os.path.exists(manifest_path) and not args.force:
        lib.fail("run %s already exists (use --force to overwrite)" % run_id, code=3, runId=run_id)
    base_sha = args.base_sha or lib.run_git(repo, ["rev-parse", "HEAD"]).stdout.strip()
    base_sha = lib.require_commit(repo, base_sha, "base-sha")
    target_branch = args.target_branch
    if not target_branch:
        proc = lib.run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"], check=False)
        target_branch = proc.stdout.strip() if proc.returncode == 0 else "main"
    target_head = lib.run_git(
        repo, ["rev-parse", "refs/heads/%s" % target_branch], check=False
    ).stdout.strip() or base_sha

    manifest = {
        "skillVersion": CFG["skillVersion"],
        "manifestSchemaVersion": lib.MANIFEST_SCHEMA_VERSION,
        "provenanceSchemaVersion": CFG.get("provenanceSchemaVersion", 1),
        "runId": run_id,
        "createdAt": lib.utc_now_iso(),
        "repoRoot": repo,
        "baseSha": base_sha,
        "integrationTargetBranch": target_branch,
        "targetHeadAtStart": target_head,
        "model": lib.CANONICAL_MODEL,
        "modelVerified": False,
        "userGoals": args.goal or [],
        "classifications": [],
        "dag": {"nodes": [], "edges": []},
        "worktrees": {},
        "branches": {},
        "sessions": {},
        "resources": {},
        "candidates": {},
        "qa": {},
        "integrationHead": None,
        "stagingHead": None,
        "statuses": {d: "PENDING" for d in DIMENSIONS},
        "overallStatus": "PENDING",
        "unresolvedGaps": [],
        "scopeChanges": [],
        "metrics": {},
    }
    for name in ("resources", "evidence", "status", "sessions"):
        os.makedirs(os.path.join(rdir, name), exist_ok=True)
    lib.atomic_write_json(manifest_path, manifest)
    lib.atomic_write_json(os.path.join(rdir, "tasks.json"), [])
    lib.atomic_write_json(os.path.join(rdir, "sessions.json"), {})
    lib.atomic_write_json(os.path.join(rdir, "candidates.json"), {})
    lib.atomic_write_json(
        os.path.join(rdir, "status.json"),
        {"runId": run_id, "statuses": manifest["statuses"], "overallStatus": "PENDING",
         "updatedAt": lib.utc_now_iso()},
    )
    lib.emit({"ok": True, "runId": run_id, "runDir": rdir, "baseSha": base_sha,
              "targetBranch": target_branch, "model": lib.CANONICAL_MODEL})


def _load_run(args: argparse.Namespace):
    repo = lib.find_repo_root(args.repo)
    rdir = lib.run_dir(repo, args.run_id)
    if not os.path.isdir(rdir):
        lib.fail("unknown run %s" % args.run_id, code=4, runDir=rdir)
    return repo, rdir


def cmd_show(args: argparse.Namespace) -> None:
    _, rdir = _load_run(args)
    out = {"runDir": rdir}
    for name in ("manifest.json", "tasks.json", "sessions.json", "candidates.json", "status.json"):
        out[name] = _read(rdir, name, None)
    lib.emit({"ok": True, **out})


def cmd_add_task(args: argparse.Namespace) -> None:
    _, rdir = _load_run(args)
    task = json.loads(args.json)
    if "id" not in task or "class" not in task:
        lib.fail("task requires at least 'id' and 'class'", code=64)
    if task["class"] not in ("S", "A", "W", "I"):
        lib.fail("task class must be S|A|W|I", code=64)
    with lib.run_lock(rdir):
        tasks = _read(rdir, "tasks.json", [])
        existing = [t for t in tasks if t.get("id") == task["id"]]
        if existing and not args.update:
            lib.fail("task %s exists (use --update)" % task["id"], code=3)
        tasks = [t for t in tasks if t.get("id") != task["id"]]
        tasks.append(task)
        lib.atomic_write_json(os.path.join(rdir, "tasks.json"), tasks)
        manifest = _read(rdir, "manifest.json", {})
        manifest["dag"] = {
            "nodes": [{"id": t["id"], "class": t["class"], "owner": t.get("owner"),
                       "dependsOn": t.get("dependsOn", [])} for t in tasks],
            "edges": [[d, t["id"]] for t in tasks for d in t.get("dependsOn", [])],
        }
        manifest["classifications"] = tasks
        lib.atomic_write_json(os.path.join(rdir, "manifest.json"), manifest)
    lib.emit({"ok": True, "taskId": task["id"], "count": len(tasks)})


def cmd_add_session(args: argparse.Namespace) -> None:
    _, rdir = _load_run(args)
    with lib.run_lock(rdir):
        sessions = _read(rdir, "sessions.json", {})
        sessions[args.domain] = {
            "domain": args.domain,
            "sessionId": args.session_id,
            "launcherPid": args.pid,
            "pid": args.pid,
            "worktree": args.worktree,
            "branch": args.branch,
            "model": args.model or lib.CANONICAL_MODEL,
            "recordedAt": lib.utc_now_iso(),
        }
        lib.atomic_write_json(os.path.join(rdir, "sessions.json"), sessions)
        manifest = _read(rdir, "manifest.json", {})
        manifest.setdefault("sessions", {})[args.domain] = sessions[args.domain]
        manifest.setdefault("worktrees", {})[args.domain] = args.worktree
        manifest.setdefault("branches", {})[args.domain] = args.branch
        lib.atomic_write_json(os.path.join(rdir, "manifest.json"), manifest)
    lib.emit({"ok": True, "domain": args.domain, "sessionId": args.session_id})


def _normalize_candidate(args):
    stage = args.stage or _STATE_LEGACY.get(args.state or "", None)
    record = {
        "domain": args.domain,
        "stage": stage,
        "workerCommit": args.worker_commit or args.commit,
        "commit": args.worker_commit or args.commit,
        "note": args.note or "",
        "at": lib.utc_now_iso(),
    }
    return record


def cmd_set_candidate(args: argparse.Namespace) -> None:
    _, rdir = _load_run(args)
    if args.stage and args.stage not in STAGES:
        lib.fail("stage must be one of %s" % ", ".join(STAGES), code=64)
    record = _normalize_candidate(args)
    if not record["workerCommit"] and not record["stage"]:
        lib.fail("set-candidate needs --commit/--worker-commit or --stage", code=64)
    lib.validate_domain(args.domain)
    with lib.run_lock(rdir):
        candidates = _read(rdir, "candidates.json", {})
        candidates.setdefault(args.domain, []).append(record)
        lib.atomic_write_json(os.path.join(rdir, "candidates.json"), candidates)
        manifest = _read(rdir, "manifest.json", {})
        manifest.setdefault("candidates", {})[args.domain] = candidates[args.domain]
        lib.atomic_write_json(os.path.join(rdir, "manifest.json"), manifest)
    lib.emit({"ok": True, "domain": args.domain, "stage": record["stage"],
              "workerCommit": record["workerCommit"]})


def _latest_candidate(candidates, domain):
    entries = candidates.get(domain) or []
    return entries[-1] if entries else None


def cmd_record_provenance(args: argparse.Namespace) -> None:
    repo, rdir = _load_run(args)
    if args.method not in METHODS:
        lib.fail("method must be one of %s" % ", ".join(METHODS), code=64)
    worker = lib.require_commit(repo, args.worker_commit, "worker-commit")
    integrated = lib.require_commit(repo, args.integrated_commit, "integrated-commit")
    worker_tree = lib.git_tree(repo, worker)
    integrated_tree = lib.git_tree(repo, integrated)
    worker_patch = lib.git_patch_id(repo, worker)
    integrated_patch = lib.git_patch_id(repo, integrated)
    already_integrated = args.method == "already-integrated"
    if worker_patch and integrated_patch and worker_patch == integrated_patch:
        content_equivalent = True
    elif worker_tree and integrated_tree and worker_tree == integrated_tree:
        content_equivalent = True
    else:
        content_equivalent = False
    changed_files = lib.git_changed_files(repo, worker, integrated) if not content_equivalent else []
    provenance = {
        "schemaVersion": CFG.get("provenanceSchemaVersion", 1),
        "workerCommit": worker,
        "reviewedCommit": args.reviewed_commit,
        "integrationInputCommit": args.integration_input_commit or worker,
        "integratedCommit": integrated,
        "integrationMethod": args.method,
        "workerPatchId": worker_patch,
        "integratedPatchId": integrated_patch,
        "contentEquivalent": content_equivalent,
        "adapterCommit": args.adapter_commit,
        "changedFiles": changed_files,
        "alreadyIntegrated": already_integrated,
        "recordedAt": lib.utc_now_iso(),
    }
    with lib.run_lock(rdir):
        candidates = _read(rdir, "candidates.json", {})
        record = _latest_candidate(candidates, args.domain)
        if record is None:
            record = {"domain": args.domain, "stage": "REVIEWED", "workerCommit": worker,
                      "at": lib.utc_now_iso()}
            candidates.setdefault(args.domain, []).append(record)
        record["provenance"] = provenance
        if args.method == "already-integrated":
            record["duplicateIntegration"] = True
        if not content_equivalent and args.adapter_commit is None and args.method != "adapted":
            record["adaptationUndeclared"] = True
        if content_equivalent:
            record["stage"] = "INTEGRATED"
        lib.atomic_write_json(os.path.join(rdir, "candidates.json"), candidates)
        manifest = _read(rdir, "manifest.json", {})
        manifest.setdefault("candidates", {})[args.domain] = candidates[args.domain]
        lib.atomic_write_json(os.path.join(rdir, "manifest.json"), manifest)
    payload = {"ok": content_equivalent or args.method in ("adapted", "already-integrated"),
               "domain": args.domain, "provenance": provenance}
    if record.get("adaptationUndeclared"):
        payload["warning"] = "content changed without an adapter commit; declare --method adapted --adapter-commit"
    lib.emit(payload, exit_code=0 if payload["ok"] else 1)


def cmd_check_provenance(args: argparse.Namespace) -> None:
    repo, rdir = _load_run(args)
    candidates = _read(rdir, "candidates.json", {})
    problems, checked = [], 0
    for domain, entries in candidates.items():
        for record in entries:
            prov = record.get("provenance")
            if not prov:
                continue
            checked += 1
            if not lib.ref_exists(repo, prov["integratedCommit"]):
                problems.append("%s: integrated commit %s is missing" % (domain, prov["integratedCommit"]))
                continue
            wpid = lib.git_patch_id(repo, prov["workerCommit"]) if lib.ref_exists(repo, prov["workerCommit"]) else None
            ipid = lib.git_patch_id(repo, prov["integratedCommit"])
            expected = prov.get("contentEquivalent")
            actual = bool(wpid and ipid and wpid == ipid)
            if expected and not actual:
                problems.append("%s: recorded contentEquivalent=true but patch ids now differ" % domain)
            if record.get("adaptationUndeclared"):
                problems.append("%s: adaptation recorded without an adapter commit" % domain)
    lib.emit({"ok": not problems, "checked": checked, "problems": problems},
             exit_code=0 if not problems else 1)


def _candidate_stage_counts(candidates):
    counts = {stage: 0 for stage in STAGES}
    latest = {}
    for domain, entries in (candidates or {}).items():
        if not entries:
            continue
        stage = entries[-1].get("stage") or _STATE_LEGACY.get(entries[-1].get("state", ""), "WORKING")
        latest[domain] = stage
        counts[stage] = counts.get(stage, 0) + 1
    return counts, latest


def cmd_pressure(args: argparse.Namespace) -> None:
    _, rdir = _load_run(args)
    candidates = _read(rdir, "candidates.json", {})
    counts, latest = _candidate_stage_counts(candidates)
    ready = counts.get("READY_FOR_REVIEW", 0)
    qa = counts.get("IN_QA", 0)
    integration = counts.get("REVIEWED", 0)
    reasons = []
    if ready > BACKLOG.get("readyForReview", 3):
        reasons.append("READY_FOR_REVIEW backlog %d > %d" % (ready, BACKLOG.get("readyForReview", 3)))
    if qa > BACKLOG.get("qaQueue", 3):
        reasons.append("QA queue %d > %d" % (qa, BACKLOG.get("qaQueue", 3)))
    if integration > BACKLOG.get("integrationQueue", 3):
        reasons.append("integration queue %d > %d" % (integration, BACKLOG.get("integrationQueue", 3)))
    if integration > 0:
        reasons.append("integration has %d reviewed candidate(s) to merge" % integration)
    pressure = "HIGH" if len(reasons) >= 2 else ("MEDIUM" if reasons else "LOW")
    allow_new_writers = pressure != "HIGH"
    lib.emit({"ok": True, "runId": args.run_id, "pressure": pressure,
              "allowNewWriters": allow_new_writers,
              "maxNewWriters": 0 if pressure == "HIGH" else (1 if pressure == "MEDIUM" else 2),
              "counts": counts, "latest": latest, "reasons": reasons,
              "policy": "HIGH pressure: stop spawning lower-priority write sessions, allow read-only "
                        "investigation, drain QA/integration; MEDIUM: at most one new writer."})


def cmd_metrics(args: argparse.Namespace) -> None:
    _, rdir = _load_run(args)
    manifest = _read(rdir, "manifest.json", {})
    sessions = _read(rdir, "sessions.json", {})
    candidates = _read(rdir, "candidates.json", {})
    tasks = _read(rdir, "tasks.json", [])
    candidates_flat = [r for entries in candidates.values() for r in entries]
    metrics = {
        "workersSpawned": len([s for s in sessions.values()]),
        "subagentsSpawned": None,  # not observable from state; recorded by orchestrator when known
        "workerCommits": len({r.get("workerCommit") for r in candidates_flat if r.get("workerCommit")}),
        "candidates": len(candidates),
        "candidateRecords": len(candidates_flat),
        "integrationAdaptations": len([r for r in candidates_flat
                                       if r.get("provenance", {}).get("integrationMethod") == "adapted"]),
        "integrationAdapters": len([r for r in candidates_flat
                                    if r.get("provenance", {}).get("adapterCommit")]),
        "duplicateIntegrations": len([r for r in candidates_flat if r.get("duplicateIntegration")]),
        "qaFailures": len([r for r in candidates_flat if r.get("stage") == "NEEDS_FIX"]),
        "blockedCandidates": len([r for r in candidates_flat if r.get("stage") == "BLOCKED"]),
        "tasks": {c: len([t for t in tasks if t.get("class") == c]) for c in ("S", "A", "W", "I")},
    }
    manifest["metrics"] = {k: v for k, v in metrics.items() if v is not None}
    lib.atomic_write_json(os.path.join(rdir, "manifest.json"), manifest)
    lib.emit({"ok": True, "runId": args.run_id, "metrics": metrics})


def cmd_check_target(args: argparse.Namespace) -> None:
    repo, rdir = _load_run(args)
    manifest = _read(rdir, "manifest.json", {})
    branch = manifest.get("integrationTargetBranch")
    start = manifest.get("targetHeadAtStart")
    current = lib.resolve_head(repo, "refs/heads/%s" % branch) if branch else None
    moved = bool(current and start and current != start)
    integrated = manifest.get("integrationHead")
    if not moved:
        safe = True
        reasons = []
    elif integrated and lib.git_is_ancestor(repo, start, current):
        # target advanced on the same line; integration can be replayed on top
        safe = False
        reasons = ["target branch advanced after the run started; replay and re-test the candidate"]
    else:
        safe = False
        reasons = ["target branch moved or diverged; reconciliation required before promotion"]
    lib.emit({"ok": not moved, "runId": args.run_id, "targetBranch": branch,
              "targetHeadAtStart": start, "targetHeadNow": current,
              "targetMoved": moved, "promotionSafe": safe, "reasons": reasons},
             exit_code=0 if not moved else 1)


def _scan_agent_models(repo: str):
    agent_dir = os.path.join(repo, ".opencode", "agent")
    if not os.path.isdir(agent_dir):
        agent_dir = os.path.join(repo, ".opencode", "agents")
    found = []
    if os.path.isdir(agent_dir):
        for name in sorted(os.listdir(agent_dir)):
            if name.startswith("an3-") and name.endswith(".md"):
                fm = lib.parse_frontmatter(os.path.join(agent_dir, name))
                found.append({"agent": name[:-3], "model": fm.get("model")})
    return found


def cmd_set_head(args: argparse.Namespace) -> None:
    _, rdir = _load_run(args)
    with lib.run_lock(rdir):
        manifest = _read(rdir, "manifest.json", {})
        manifest[args.field] = args.commit
        lib.atomic_write_json(os.path.join(rdir, "manifest.json"), manifest)
    lib.emit({"ok": True, "field": args.field, "value": manifest.get(args.field)})


def cmd_check_model(args: argparse.Namespace) -> None:
    repo, rdir = _load_run(args)
    sessions = _read(rdir, "sessions.json", {})
    agents = _scan_agent_models(repo)
    problems = []
    if not agents:
        problems.append("no an3-* agents found to pin the model")
    for entry in agents:
        if entry["model"] != lib.CANONICAL_MODEL:
            problems.append("%s pins %r, expected %r" % (entry["agent"], entry["model"], lib.CANONICAL_MODEL))
    for domain, session in sessions.items():
        model = session.get("model") or session.get("modelUsed")
        if model and model != lib.CANONICAL_MODEL:
            problems.append("session %s used %r, expected %r" % (domain, model, lib.CANONICAL_MODEL))
    payload = {"ok": not problems, "model": lib.CANONICAL_MODEL, "agents": agents,
               "sessions": sessions, "problems": problems}
    if problems:
        payload["status"] = "MODEL_UNAVAILABLE"
        lib.emit(payload, exit_code=5)
    payload["status"] = "OK"
    lib.emit(payload)


def cmd_validate(args: argparse.Namespace) -> None:
    repo, rdir = _load_run(args)
    manifest_path = os.path.join(rdir, "manifest.json")
    if not os.path.exists(manifest_path):
        lib.fail("manifest.json missing", code=4)
    manifest = lib.read_json(manifest_path)
    problems = []
    required = ["runId", "baseSha", "model", "statuses", "manifestSchemaVersion", "repoRoot"]
    for key in required:
        if key in manifest and manifest[key] in (None, "", {}, []):
            problems.append("manifest.%s is empty" % key)
        elif key not in manifest:
            problems.append("manifest.%s missing" % key)
    schema = manifest.get("manifestSchemaVersion")
    if schema != lib.MANIFEST_SCHEMA_VERSION:
        if isinstance(schema, int) and schema < lib.MANIFEST_SCHEMA_VERSION:
            problems.append("manifest schema %s is older than supported %s (upgrade path required)"
                            % (schema, lib.MANIFEST_SCHEMA_VERSION))
        else:
            problems.append("manifest schema %s is newer than supported %s" % (schema, lib.MANIFEST_SCHEMA_VERSION))
    for key, value in (manifest.get("statuses") or {}).items():
        if key not in DIMENSIONS:
            problems.append("unknown status dimension %s" % key)
    if manifest.get("model") != lib.CANONICAL_MODEL:
        problems.append("manifest model %r != %r" % (manifest.get("model"), lib.CANONICAL_MODEL))
    payload = {"ok": not problems, "runId": args.run_id, "schema": lib.MANIFEST_SCHEMA_VERSION,
               "problems": problems}
    lib.emit(payload, exit_code=0 if not problems else 1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AN3 orchestrator run state")
    parser.add_argument("--repo", default=None, help="repository root (default: discover from cwd)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("model").set_defaults(func=cmd_model)

    p = sub.add_parser("init")
    p.add_argument("--run-id")
    p.add_argument("--base-sha")
    p.add_argument("--goal", action="append")
    p.add_argument("--target-branch")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("show")
    p.add_argument("--run-id", required=True)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("add-task")
    p.add_argument("--run-id", required=True)
    p.add_argument("--json", required=True)
    p.add_argument("--update", action="store_true")
    p.set_defaults(func=cmd_add_task)

    p = sub.add_parser("add-session")
    p.add_argument("--run-id", required=True)
    p.add_argument("--domain", required=True)
    p.add_argument("--session-id", required=True)
    p.add_argument("--worktree", required=True)
    p.add_argument("--branch", required=True)
    p.add_argument("--pid", type=int)
    p.add_argument("--model")
    p.set_defaults(func=cmd_add_session)

    p = sub.add_parser("set-candidate")
    p.add_argument("--run-id", required=True)
    p.add_argument("--domain", required=True)
    p.add_argument("--commit")
    p.add_argument("--worker-commit")
    p.add_argument("--stage", choices=STAGES)
    p.add_argument("--state", choices=["candidate", "integrated", "rejected"])
    p.add_argument("--note")
    p.set_defaults(func=cmd_set_candidate)

    p = sub.add_parser("record-provenance")
    p.add_argument("--run-id", required=True)
    p.add_argument("--domain", required=True)
    p.add_argument("--worker-commit", required=True)
    p.add_argument("--integrated-commit", required=True)
    p.add_argument("--method", required=True, choices=METHODS)
    p.add_argument("--reviewed-commit")
    p.add_argument("--integration-input-commit")
    p.add_argument("--adapter-commit")
    p.set_defaults(func=cmd_record_provenance)

    p = sub.add_parser("check-provenance")
    p.add_argument("--run-id", required=True)
    p.set_defaults(func=cmd_check_provenance)

    p = sub.add_parser("pressure")
    p.add_argument("--run-id", required=True)
    p.set_defaults(func=cmd_pressure)

    p = sub.add_parser("metrics")
    p.add_argument("--run-id", required=True)
    p.set_defaults(func=cmd_metrics)

    p = sub.add_parser("check-target")
    p.add_argument("--run-id", required=True)
    p.set_defaults(func=cmd_check_target)

    p = sub.add_parser("set-status")
    p.add_argument("--run-id", required=True)
    p.add_argument("--dimension", choices=DIMENSIONS)
    p.add_argument("--value")
    p.add_argument("--overall", choices=OVERALL)
    p.set_defaults(func=cmd_set_status)

    p = sub.add_parser("check-model")
    p.add_argument("--run-id", required=True)
    p.set_defaults(func=cmd_check_model)

    p = sub.add_parser("set-head")
    p.add_argument("--run-id", required=True)
    p.add_argument("--field", choices=["integrationHead", "stagingHead"], required=True)
    p.add_argument("--commit", required=True)
    p.set_defaults(func=cmd_set_head)

    p = sub.add_parser("validate")
    p.add_argument("--run-id", required=True)
    p.set_defaults(func=cmd_validate)
    return parser


def cmd_set_status(args: argparse.Namespace) -> None:
    _, rdir = _load_run(args)
    if args.dimension:
        if args.dimension not in DIMENSIONS:
            lib.fail("unknown dimension %s" % args.dimension, code=64)
        if args.value is None:
            lib.fail("--value is required with --dimension", code=64)
    if args.overall and args.overall not in OVERALL:
        lib.fail("overall must be one of %s" % ", ".join(OVERALL), code=64)
    with lib.run_lock(rdir):
        status = _read(rdir, "status.json", {"statuses": {d: "PENDING" for d in DIMENSIONS}})
        status.setdefault("statuses", {})
        if args.dimension:
            status["statuses"][args.dimension] = args.value
        if args.overall:
            status["overallStatus"] = args.overall
        status["updatedAt"] = lib.utc_now_iso()
        lib.atomic_write_json(os.path.join(rdir, "status.json"), status)
        manifest = _read(rdir, "manifest.json", {})
        manifest["statuses"] = status["statuses"]
        manifest["overallStatus"] = status.get("overallStatus", "PENDING")
        lib.atomic_write_json(os.path.join(rdir, "manifest.json"), manifest)
    lib.emit({"ok": True, "statuses": status["statuses"],
              "overallStatus": status.get("overallStatus")})


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except lib.OrchestratorError as exc:
        lib.fail(exc.message, code=exc.code, **exc.detail)


if __name__ == "__main__":
    main()
