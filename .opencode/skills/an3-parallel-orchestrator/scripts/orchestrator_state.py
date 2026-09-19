#!/usr/bin/env python3
"""AN3 orchestrator run-state manager (deterministic, atomic, non-destructive).

Usage:
  orchestrator_state.py model
  orchestrator_state.py init --base-sha <sha> [--run-id <id>] [--goal ...] [--target-branch <b>] [--repo <path>] [--force]
  orchestrator_state.py show --run-id <id> [--repo <path>]
  orchestrator_state.py add-task --run-id <id> --json '<task json>' [--update]
  orchestrator_state.py add-session --run-id <id> --domain <d> --session-id <s> --worktree <w> --branch <b> [--pid N] [--model M]
  orchestrator_state.py set-candidate --run-id <id> --domain <d> --commit <sha> [--state candidate|integrated|rejected] [--note ...]
  orchestrator_state.py set-status --run-id <id> (--dimension D --value V | --overall V)
  orchestrator_state.py check-model --run-id <id>
  orchestrator_state.py validate --run-id <id>
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import orchestrator_lib as lib  # noqa: E402

DIMENSIONS = lib.load_config()["statuses"]["dimensions"]
OVERALL = lib.load_config()["statuses"]["overall"]


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
        target_branch = proc.stdout.strip() if proc.returncode == 0 else "apps-web"
    target_head = lib.run_git(
        repo, ["rev-parse", "refs/heads/%s" % target_branch], check=False
    ).stdout.strip() or base_sha

    manifest = {
        "skillVersion": lib.load_config()["skillVersion"],
        "manifestSchemaVersion": lib.MANIFEST_SCHEMA_VERSION,
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
    }
    for name in ("resources", "evidence", "status"):
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
        path = os.path.join(rdir, name)
        out[name] = lib.read_json(path) if os.path.exists(path) else None
    lib.emit({"ok": True, **out})


def cmd_add_task(args: argparse.Namespace) -> None:
    _, rdir = _load_run(args)
    task = json.loads(args.json)
    if "id" not in task or "class" not in task:
        lib.fail("task requires at least 'id' and 'class'", code=64)
    if task["class"] not in ("S", "A", "W", "I"):
        lib.fail("task class must be S|A|W|I", code=64)

    def mutate(tasks):
        existing = [t for t in tasks if t.get("id") == task["id"]]
        if existing and not args.update:
            raise lib.OrchestratorError("task %s exists (use --update)" % task["id"], code=3)
        tasks = [t for t in tasks if t.get("id") != task["id"]]
        tasks.append(task)
        return tasks

    tasks_path = os.path.join(rdir, "tasks.json")
    try:
        tasks = lib.update_json(tasks_path, mutate)
    except lib.OrchestratorError as exc:
        lib.fail(exc.message, code=exc.code)
    # keep the DAG mirror in the manifest in sync
    def sync(manifest):
        manifest["dag"] = {
            "nodes": [{"id": t["id"], "class": t["class"], "owner": t.get("owner"),
                       "dependsOn": t.get("dependsOn", [])} for t in tasks],
            "edges": [[d, t["id"]] for t in tasks for d in t.get("dependsOn", [])],
        }
        manifest["classifications"] = tasks
        return manifest

    lib.update_json(os.path.join(rdir, "manifest.json"), sync)
    lib.emit({"ok": True, "taskId": task["id"], "count": len(tasks)})


def cmd_add_session(args: argparse.Namespace) -> None:
    _, rdir = _load_run(args)

    def mutate(sessions):
        sessions[args.domain] = {
            "domain": args.domain,
            "sessionId": args.session_id,
            "pid": args.pid,
            "worktree": args.worktree,
            "branch": args.branch,
            "model": args.model or lib.CANONICAL_MODEL,
            "recordedAt": lib.utc_now_iso(),
        }
        return sessions

    lib.update_json(os.path.join(rdir, "sessions.json"), mutate)

    def sync(manifest):
        manifest["sessions"] = lib.read_json(os.path.join(rdir, "sessions.json"))
        manifest["worktrees"][args.domain] = args.worktree
        manifest["branches"][args.domain] = args.branch
        return manifest

    lib.update_json(os.path.join(rdir, "manifest.json"), sync)
    lib.emit({"ok": True, "domain": args.domain, "sessionId": args.session_id})


def cmd_set_candidate(args: argparse.Namespace) -> None:
    _, rdir = _load_run(args)

    def mutate(candidates):
        entry = candidates.setdefault(args.domain, [])
        entry.append({"commit": args.commit, "state": args.state,
                      "note": args.note or "", "at": lib.utc_now_iso()})
        return candidates

    lib.update_json(os.path.join(rdir, "candidates.json"), mutate)
    lib.emit({"ok": True, "domain": args.domain, "commit": args.commit, "state": args.state})


def cmd_set_status(args: argparse.Namespace) -> None:
    _, rdir = _load_run(args)
    if args.dimension:
        if args.dimension not in DIMENSIONS:
            lib.fail("unknown dimension %s" % args.dimension, code=64)
        if args.value is None:
            lib.fail("--value is required with --dimension", code=64)
    if args.overall and args.overall not in OVERALL:
        lib.fail("overall must be one of %s" % ", ".join(OVERALL), code=64)

    def mutate(status):
        if args.dimension:
            status["statuses"][args.dimension] = args.value
        if args.overall:
            status["overallStatus"] = args.overall
        status["updatedAt"] = lib.utc_now_iso()
        return status

    status = lib.update_json(os.path.join(rdir, "status.json"), mutate)
    lib.update_json(os.path.join(rdir, "manifest.json"),
                    lambda m: {**m, "statuses": status["statuses"],
                               "overallStatus": status["overallStatus"]})
    lib.emit({"ok": True, "statuses": status["statuses"], "overallStatus": status["overallStatus"]})


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

    def mutate(manifest):
        manifest[args.field] = args.commit
        return manifest

    manifest = lib.update_json(os.path.join(rdir, "manifest.json"), mutate)
    lib.emit({"ok": True, "field": args.field, "value": manifest.get(args.field)})


def cmd_check_model(args: argparse.Namespace) -> None:
    repo, rdir = _load_run(args)
    sessions = lib.read_json(os.path.join(rdir, "sessions.json"))
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
    p.add_argument("--commit", required=True)
    p.add_argument("--state", choices=["candidate", "integrated", "rejected"], default="candidate")
    p.add_argument("--note")
    p.set_defaults(func=cmd_set_candidate)

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


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except lib.OrchestratorError as exc:
        lib.fail(exc.message, code=exc.code, **exc.detail)


if __name__ == "__main__":
    main()
