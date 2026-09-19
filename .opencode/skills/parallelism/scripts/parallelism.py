#!/usr/bin/env python3
"""Minimal Master/helper support for the 'parallelism' skill.

Deterministic helpers only: model resolution and verification, helper worktree
spawn + compact checkpoints, no-progress detection, and an exclusive integration
lock. No background service, no autonomous supervisor, no role pipeline.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone

DB_PATH = os.path.expanduser("~/.local/share/opencode/opencode.db")
STATES = ["ASSIGNED", "WORKING", "VALIDATING", "COMPLETED", "BLOCKED", "FAILED", "CANCELLED"]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit(obj, code: int = 0):
    print(json.dumps(obj, indent=2, sort_keys=True))
    sys.exit(code)


def fail(message: str, code: int = 1, **detail):
    emit({"ok": False, "error": message, **detail}, code)


def run_git(repo: str, args, check: bool = True):
    proc = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), proc.stderr.strip()))
    return proc


def find_repo(start: str) -> str:
    current = os.path.abspath(start or os.getcwd())
    if os.path.isfile(current):
        current = os.path.dirname(current)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            raise RuntimeError("no git repository above %s" % start)
        current = parent


def git_common_dir(repo: str) -> str:
    proc = run_git(repo, ["rev-parse", "--path-format=absolute", "--git-common-dir"], check=False)
    if proc.returncode != 0:
        proc = run_git(repo, ["rev-parse", "--git-common-dir"])
    value = proc.stdout.strip()
    if not os.path.isabs(value):
        value = os.path.abspath(os.path.join(repo, value))
    return os.path.realpath(value)


def state_dir(repo: str) -> str:
    path = os.path.join(git_common_dir(repo), "parallelism")
    os.makedirs(path, exist_ok=True)
    return path


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp, path)


def is_pid_alive(pid) -> bool:
    if not pid or int(pid) <= 0:
        return False
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    return True


# --- model resolution / verification ---------------------------------------


def _validate_model(value: str) -> str:
    value = (value or "").strip()
    if "/" not in value or value.startswith("/") or value.endswith("/"):
        fail("invalid model %r; expected provider/model-id" % value, code=64)
    return value


def cmd_resolve_model(args):
    candidates = []
    if args.model:
        candidates.append(("argument", args.model))
    if os.environ.get("PARALLELISM_MASTER_MODEL"):
        candidates.append(("env", os.environ["PARALLELISM_MASTER_MODEL"]))
    if args.project:
        proc = subprocess.run(["opencode", "debug", "config"], cwd=args.project,
                              capture_output=True, text=True)
        if proc.returncode == 0:
            try:
                value = json.loads(proc.stdout).get("model")
                if value:
                    candidates.append(("project-config", value))
            except ValueError:
                pass
    if not candidates:
        fail("cannot resolve the Master model; pass --model or set PARALLELISM_MASTER_MODEL "
             "or run from a directory with a configured model", code=2)
    source, value = candidates[0]
    emit({"ok": True, "model": _validate_model(value), "source": source})


def _session_model(session_id: str, title: str | None):
    if not os.path.exists(DB_PATH):
        fail("session store not found at %s" % DB_PATH, code=2)
    conn = sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True)
    try:
        if session_id:
            row = conn.execute("select model from session where id=?", (session_id,)).fetchone()
        else:
            row = conn.execute("select model from session where title=? order by time_updated desc limit 1",
                               (title,)).fetchone()
    finally:
        conn.close()
    if not row or not row[0]:
        return None, None
    try:
        data = json.loads(row[0])
    except ValueError:
        return None, None
    provider = data.get("providerID") or data.get("provider")
    model_id = data.get("id") or data.get("modelID")
    if not provider or not model_id:
        return None, None
    return "%s/%s" % (provider, model_id), data


def cmd_verify_model(args):
    expected = _validate_model(args.expect)
    if not args.session and not args.title:
        fail("verify-model requires --session or --title", code=64)
    actual, raw = _session_model(args.session, args.title)
    if actual is None:
        fail("helper session not found (or model unknown)", code=3,
             session=args.session, title=args.title)
    emit({"ok": actual == expected, "expected": expected, "actual": actual,
          "session": args.session, "title": args.title, "raw": raw},
         code=0 if actual == expected else 1)


# --- checkpoint / status / progress ----------------------------------------


def _ckpt_path(repo: str, name: str) -> str:
    return os.path.join(state_dir(repo), "helpers", "%s.json" % name)


def cmd_checkpoint(args):
    repo = find_repo(args.repo)
    path = _ckpt_path(repo, args.name)
    data = read_json(path) if os.path.exists(path) else {"name": args.name}
    if args.status:
        status = args.status.upper()
        if status not in STATES:
            fail("invalid status %r; one of %s" % (args.status, ", ".join(STATES)), code=64)
        data["status"] = status
    for field in ("commit", "evidence", "tests", "blocker", "message", "model", "branch", "worktree"):
        value = getattr(args, field)
        if value is not None:
            data[field] = value
    data["updatedAt"] = now()
    write_json(path, data)
    emit({"ok": True, "name": args.name, "checkpoint": data})


def cmd_status(args):
    repo = find_repo(args.repo)
    root = os.path.join(state_dir(repo), "helpers")
    helpers = []
    if os.path.isdir(root):
        for name in sorted(os.listdir(root)):
            if name.endswith(".json"):
                try:
                    helpers.append(read_json(os.path.join(root, name)))
                except ValueError:
                    continue
    emit({"ok": True, "count": len(helpers),
          "helpers": [{k: h.get(k) for k in ("name", "status", "model", "commit", "pid", "stall")}
                      for h in helpers]})


def cmd_progress(args):
    repo = find_repo(args.repo)
    path = _ckpt_path(repo, args.name)
    if not os.path.exists(path):
        fail("no checkpoint for %r" % args.name, code=4)
    data = read_json(path)
    signature = [data.get("status"), data.get("commit"), data.get("tests"),
                 data.get("evidence"), data.get("blocker")]
    if data.get("last_signature") == signature:
        data["stall"] = int(data.get("stall", 0)) + 1
    else:
        data["stall"] = 0
        data["last_signature"] = signature
    action = "continue"
    active = data.get("status") in ("WORKING", "VALIDATING", "ASSIGNED")
    if active and data["stall"] >= args.limit:
        data["status"] = "BLOCKED"
        data["redispatch"] = False
        data["blocker"] = data.get("blocker") or "no measurable progress after %d checks" % data["stall"]
        action = "park"
    data["updatedAt"] = now()
    write_json(path, data)
    emit({"ok": True, "name": args.name, "action": action, "stall": data["stall"],
          "status": data["status"], "redispatch": data.get("redispatch", True)})


# --- spawn ------------------------------------------------------------------


def cmd_spawn(args):
    if not args.model:
        fail("spawn requires --model (resolve it with resolve-model first)", code=64)
    model = _validate_model(args.model)
    repo = find_repo(args.repo)
    state = state_dir(repo)
    worktree = os.path.abspath(args.worktree or os.path.join(
        os.path.dirname(repo), "pw-%s" % args.name))
    branch = args.branch or ("helper/%s" % args.name)

    if not os.path.isdir(worktree):
        base = args.base_sha or "HEAD"
        proc = run_git(repo, ["worktree", "add", "-b", branch, worktree, base], check=False)
        if proc.returncode != 0:
            run_git(repo, ["worktree", "add", worktree, branch])

    prompt_text = ""
    if args.assignment:
        with open(args.assignment, "r", encoding="utf-8") as handle:
            prompt_text = handle.read()
    if not prompt_text.strip():
        fail("spawn requires a non-empty --assignment prompt file", code=64)

    prompt_path = os.path.join(state, "prompts", "%s.md" % args.name)
    os.makedirs(os.path.dirname(prompt_path), exist_ok=True)
    with open(prompt_path, "w", encoding="utf-8") as handle:
        handle.write(prompt_text)
    write_json(_ckpt_path(repo, args.name), {
        "name": args.name, "status": "ASSIGNED", "model": model, "branch": branch,
        "worktree": worktree, "title": "parallelism-%s" % args.name, "createdAt": now(),
    })

    log_path = os.path.join(state, "logs", "%s.ndjson" % args.name)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    title = "parallelism-%s" % args.name
    cmd = ["opencode", "run", "--format", "json", "--model", model,
           "--dir", worktree, "--title", title, prompt_text]
    stdout = open(log_path, "w", encoding="utf-8")
    stderr = open(log_path + ".err", "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=stdout, stderr=stderr, start_new_session=True)

    data = read_json(_ckpt_path(repo, args.name)) if os.path.exists(_ckpt_path(repo, args.name)) else {"name": args.name}
    data.update({"status": "WORKING", "model": model, "branch": branch, "worktree": worktree,
                 "title": title, "pid": proc.pid, "log": log_path, "startedAt": now()})
    write_json(_ckpt_path(repo, args.name), data)
    emit({"ok": True, "name": args.name, "pid": proc.pid, "worktree": worktree,
          "branch": branch, "model": model, "title": title, "log": log_path})


# --- exclusive integration lock ---------------------------------------------


def _lock_path(repo: str, name: str) -> str:
    return os.path.join(state_dir(repo), "locks", "%s.lock" % name)


def cmd_lock(args):
    repo = find_repo(args.repo)
    path = _lock_path(repo, args.name)
    if args.action == "status":
        if os.path.exists(path):
            emit({"ok": True, "name": args.name, "held": True, "holder": read_json(path)})
        emit({"ok": True, "name": args.name, "held": False})
    if args.action == "release":
        if os.path.exists(path):
            holder = read_json(path)
            holder_pid = holder.get("pid")
            if holder_pid and holder_pid != args.pid and is_pid_alive(holder_pid):
                fail("refusing to release a lock held by another live pid", code=7, holder=holder)
            os.unlink(path)
        emit({"ok": True, "name": args.name, "released": True})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"name": args.name, "owner": args.owner or "master", "pid": args.pid or os.getpid(),
               "acquiredAt": now()}
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except OSError as exc:
        if exc.errno != errno.EEXIST:
            raise
        holder = read_json(path)
        if is_pid_alive(holder.get("pid")):
            fail("lock %r is held" % args.name, code=7, holder=holder)
        os.unlink(path)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    emit({"ok": True, "name": args.name, "acquired": True, "holder": payload})


def build_parser():
    parser = argparse.ArgumentParser(description="parallelism helper utilities")
    parser.add_argument("--repo", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("resolve-model")
    p.add_argument("--model")
    p.add_argument("--project")
    p.set_defaults(func=cmd_resolve_model)

    p = sub.add_parser("verify-model")
    p.add_argument("--session")
    p.add_argument("--title")
    p.add_argument("--expect", required=True)
    p.set_defaults(func=cmd_verify_model)

    p = sub.add_parser("checkpoint")
    p.add_argument("--name", required=True)
    p.add_argument("--status")
    p.add_argument("--commit")
    p.add_argument("--evidence")
    p.add_argument("--tests")
    p.add_argument("--blocker")
    p.add_argument("--message")
    p.add_argument("--model")
    p.add_argument("--branch")
    p.add_argument("--worktree")
    p.set_defaults(func=cmd_checkpoint)

    p = sub.add_parser("status")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("progress")
    p.add_argument("--name", required=True)
    p.add_argument("--limit", type=int, default=2)
    p.set_defaults(func=cmd_progress)

    p = sub.add_parser("spawn")
    p.add_argument("--name", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--assignment", required=True)
    p.add_argument("--worktree")
    p.add_argument("--branch")
    p.add_argument("--base-sha")
    p.set_defaults(func=cmd_spawn)

    p = sub.add_parser("lock")
    p.add_argument("action", choices=["acquire", "release", "status"])
    p.add_argument("--name", required=True)
    p.add_argument("--owner")
    p.add_argument("--pid", type=int)
    p.set_defaults(func=cmd_lock)

    return parser


def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except RuntimeError as exc:
        fail(str(exc), code=1)


if __name__ == "__main__":
    main()
