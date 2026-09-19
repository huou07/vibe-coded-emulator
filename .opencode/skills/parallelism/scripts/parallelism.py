#!/usr/bin/env python3
"""Minimal Master/helper support for the 'parallelism' skill (v1.1).

Deterministic helpers only: model resolution and verification, a parallelization
decision, idempotent helper spawn with stable identity, on-demand event waiting,
compact worker results, no-progress detection, an exclusive integration lock, and
a pre-merge safety preflight. No background service, no autonomous supervisor,
no role pipeline, and no automatic merge.
"""
from __future__ import annotations

import argparse
import errno
import fnmatch
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone

DB_PATH = os.path.expanduser("~/.local/share/opencode/opencode.db")
STATES = ["ASSIGNED", "WORKING", "VALIDATING", "COMPLETED", "BLOCKED", "FAILED", "CANCELLED"]
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
LEVELS = {"low": 1, "medium": 2, "high": 3}


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


def _ckpt_path(repo: str, name: str) -> str:
    return os.path.join(state_dir(repo), "helpers", "%s.json" % name)


def _helpers(repo: str):
    root = os.path.join(state_dir(repo), "helpers")
    out = []
    if os.path.isdir(root):
        for name in sorted(os.listdir(root)):
            if name.endswith(".json") and not name.endswith(".tmp"):
                try:
                    out.append(read_json(os.path.join(root, name)))
                except ValueError:
                    continue
    return out


def _live_helpers(repo: str, exclude=None):
    return [h for h in _helpers(repo) if h.get("name") != exclude and is_pid_alive(h.get("pid"))]


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


def _session_model(session_id, title):
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


# --- parallelization decision ----------------------------------------------


def cmd_decide(args):
    """Deterministic heuristic: does concurrency beat sequential execution?

    Independent execution only pays off for 2+ tasks when independence is high and
    the overlap, initialization and integration costs are low. Decided by the
    Master (or this script) deterministically; never by another LLM call.
    """
    if args.tasks < 2 or args.independence == "low":
        emit({"ok": True, "recommendation": "sequential", "score": 0,
              "reason": "fewer than 2 tasks, or independence is low"})
    score = (LEVELS[args.independence] * args.tasks
             - LEVELS[args.overlap] - LEVELS[args.init_cost] - LEVELS[args.integration_cost])
    rec = "parallel" if score > 0 else "sequential"
    emit({"ok": True, "recommendation": rec, "score": score,
          "reason": "independence*tasks=%d minus overlap=%d init=%d integration=%d"
                    % (LEVELS[args.independence] * args.tasks, LEVELS[args.overlap],
                       LEVELS[args.init_cost], LEVELS[args.integration_cost])})


# --- checkpoint / status / progress ----------------------------------------


def cmd_checkpoint(args):
    repo = find_repo(args.repo)
    path = _ckpt_path(repo, args.name)
    data = read_json(path) if os.path.exists(path) else {"name": args.name, "id": args.name}
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
    helpers = _helpers(repo)
    emit({"ok": True, "count": len(helpers),
          "helpers": [{"id": h.get("id", h.get("name")), "name": h.get("name"),
                       "status": h.get("status"), "model": h.get("model"),
                       "commit": h.get("commit"), "pid": h.get("pid"),
                       "pidAlive": is_pid_alive(h.get("pid")), "stall": h.get("stall", 0),
                       "owns": h.get("owns", [])} for h in helpers]})


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


# --- spawn (idempotent, stable identity, ownership check) -------------------


def _contract(args, helper_id, model) -> str:
    lines = ["# Worker assignment %s" % helper_id, "",
             "Model (inherited from the Master): %s" % model, "",
             "Objective: %s" % (args.objective or "(see assignment file)")]
    if args.owns:
        lines.append("Owned files (you may modify only these): %s" % args.owns)
    if args.excludes:
        lines.append("Excluded files (do NOT modify): %s" % args.excludes)
    if args.accept:
        lines.append("Acceptance criteria: %s" % args.accept)
    if args.tests:
        lines.append("Required tests: %s" % args.tests)
    lines += [
        "",
        "Do only this assignment. Do not spawn other workers. Do not merge, rebase,",
        "force-push, deploy, or touch main. Commit your work when complete.",
        "",
        "Finish by writing a compact JSON result to %s and stop:"
        % os.path.join(state_dir(find_repo(args.repo)), "results", "%s.json" % helper_id),
        '{"status":"COMPLETED|BLOCKED","commit":"<sha or none>","files":[...],'
        '"tests":"pass|fail|unverified","acceptance":"...","blockers":[...]}',
    ]
    return "\n".join(lines) + "\n"


def cmd_spawn(args):
    if not args.model:
        fail("spawn requires --model (resolve it with resolve-model first)", code=64)
    model = _validate_model(args.model)
    repo = find_repo(args.repo)
    state = state_dir(repo)
    helper_id = args.id or args.name
    path = _ckpt_path(repo, args.name)
    existing = read_json(path) if os.path.exists(path) else None

    if existing and not args.force and not args.resume:
        if is_pid_alive(existing.get("pid")):
            fail("worker %r is already running; not dispatching a duplicate" % helper_id,
                 code=7, checkpoint=existing)
        if existing.get("status") not in TERMINAL:
            fail("worker %r was interrupted; pass --resume to reconcile in place" % helper_id,
                 code=7, checkpoint=existing)
        fail("worker %r already finished (%s); use a new name or --force"
             % (helper_id, existing.get("status")), code=7, checkpoint=existing)

    owns = [f for f in (args.owns or "").split(",") if f.strip()]
    for other in _live_helpers(repo, exclude=args.name):
        clash = set(owns) & set(other.get("owns") or [])
        if clash:
            fail("ownership conflict with running worker %r on %s"
                 % (other.get("name"), sorted(clash)), code=7)

    worktree = os.path.abspath(args.worktree or os.path.join(
        os.path.dirname(repo), "pw-%s" % args.name))
    branch = args.branch or ("helper/%s" % args.name)
    if not os.path.isdir(worktree):
        base = args.base_sha or "HEAD"
        proc = run_git(repo, ["worktree", "add", "-b", branch, worktree, base], check=False)
        if proc.returncode != 0:
            run_git(repo, ["worktree", "add", worktree, branch])

    if args.assignment:
        with open(args.assignment, "r", encoding="utf-8") as handle:
            prompt_text = handle.read()
    else:
        prompt_text = _contract(args, helper_id, model)
    if not prompt_text.strip():
        fail("spawn requires --assignment or --objective", code=64)

    prompt_path = os.path.join(state, "prompts", "%s.md" % args.name)
    os.makedirs(os.path.dirname(prompt_path), exist_ok=True)
    with open(prompt_path, "w", encoding="utf-8") as handle:
        handle.write(prompt_text)

    title = "parallelism-%s" % helper_id
    override = os.environ.get("PARALLELISM_LAUNCHER")
    if override:
        cmd = [override, prompt_path, args.name, helper_id]
    else:
        cmd = ["opencode", "run", "--format", "json", "--model", model,
               "--dir", worktree, "--title", title, prompt_text]
    log_path = os.path.join(state, "logs", "%s.ndjson" % args.name)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    stdout = open(log_path, "w", encoding="utf-8")
    stderr = open(log_path + ".err", "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=stdout, stderr=stderr, start_new_session=True)

    data = existing or {"name": args.name}
    data.update({"id": helper_id, "status": "WORKING", "model": model, "branch": branch,
                 "worktree": worktree, "title": title, "pid": proc.pid, "owns": owns,
                 "excludes": [f for f in (args.excludes or "").split(",") if f.strip()],
                 "group": args.group, "log": log_path, "startedAt": now()})
    data.pop("last_signature", None)
    data.pop("stall", None)
    write_json(path, data)
    emit({"ok": True, "id": helper_id, "name": args.name, "pid": proc.pid,
          "worktree": worktree, "branch": branch, "model": model, "title": title,
          "log": log_path})


# --- event-driven completion ------------------------------------------------


def _resolve_names(repo, args):
    if getattr(args, "name", None):
        return [args.name]
    if getattr(args, "names", None):
        return [n for n in args.names.split(",") if n.strip()]
    if getattr(args, "group", None):
        return [h.get("name") for h in _helpers(repo) if h.get("group") == args.group]
    return [h.get("name") for h in _helpers(repo)
            if h.get("status") not in TERMINAL and is_pid_alive(h.get("pid"))]


def _worker_done(repo, name):
    path = _ckpt_path(repo, name)
    data = read_json(path) if os.path.exists(path) else {}
    return (data.get("status") in (TERMINAL | {"BLOCKED"})) or not is_pid_alive(data.get("pid"))


def cmd_wait(args):
    """Deterministic, event-driven wait on a worker or a known group (no LLM polling)."""
    repo = find_repo(args.repo)
    names = _resolve_names(repo, args)
    if not names:
        emit({"ok": True, "completed": [], "pending": []})
    deadline = time.time() + args.timeout if args.timeout else None
    while True:
        pending = [n for n in names if not _worker_done(repo, n)]
        if not pending:
            emit({"ok": True, "completed": names, "pending": []})
        if deadline and time.time() > deadline:
            done = [n for n in names if n not in pending]
            emit({"ok": False, "error": "timeout", "pending": pending, "completed": done}, code=5)
        time.sleep(args.poll)


def cmd_collect(args):
    """Collect compact completion results for a name or group (structured, bounded)."""
    repo = find_repo(args.repo)
    names = _resolve_names(repo, args)
    out = []
    for name in names:
        path = _ckpt_path(repo, name)
        data = read_json(path) if os.path.exists(path) else {}
        out.append({"id": data.get("id", name), "name": name, "status": data.get("status"),
                    "commit": data.get("commit"), "tests": data.get("tests"),
                    "blocker": data.get("blocker"), "pidAlive": is_pid_alive(data.get("pid")),
                    "result": data.get("result")})
    emit({"ok": True, "count": len(out), "workers": out})


def cmd_result(args):
    repo = find_repo(args.repo)
    path = _ckpt_path(repo, args.name)
    if not os.path.exists(path):
        fail("no checkpoint for %r" % args.name, code=4)
    data = read_json(path)
    if args.file:
        result = read_json(args.file)
        status = (result.get("status") or "").upper()
        data["result"] = result
        if status in STATES:
            data["status"] = status
        for src, dst in (("commit", "commit"), ("acceptance", "evidence"),
                         ("tests", "tests"), ("blockers", "blocker")):
            if result.get(src) not in (None, [], ""):
                data[dst] = result[src]
        data["updatedAt"] = now()
        write_json(path, data)
    emit({"ok": True, "name": args.name, "status": data.get("status"), "result": data.get("result")})


# --- exclusive integration lock + pre-merge safety --------------------------


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


def _merge_tree_conflicts(repo, ref_a, ref_b):
    """Use `git merge-tree --write-tree` when supported; never touches a worktree."""
    proc = run_git(repo, ["merge-tree", "--write-tree", ref_a, ref_b], check=False)
    if proc.returncode == 0:
        return False, []
    if "usage:" in proc.stderr.lower() or "unknown option" in proc.stderr.lower():
        return None, ["merge-tree --write-tree unsupported"]
    conflicts = [ln.strip() for ln in proc.stdout.splitlines() if "CONFLICT" in ln.upper()]
    return True, conflicts or ["conflict detected"]


def cmd_premerge(args):
    """Deterministic pre-merge validation. Never merges, pushes, or deploys."""
    repo = find_repo(args.repo)
    lock = _lock_path(repo, args.lock)
    if not os.path.exists(lock):
        fail("refusing to integrate without the integration lock", code=7)
    holder = read_json(lock)
    if holder.get("pid") and holder.get("pid") != os.getpid() and not is_pid_alive(holder.get("pid")):
        fail("integration lock is held by a dead pid; reconcile before integrating",
             code=7, holder=holder)
    if not args.tests or "pass" not in args.tests.lower():
        fail("refusing to integrate without passing test evidence (--tests)", code=7)
    commit = run_git(repo, ["rev-parse", "--verify", "%s^{commit}" % args.candidate], check=False)
    if commit.returncode != 0:
        fail("candidate is not a commit: %s" % args.candidate, code=4)
    if args.expect_head:
        expected = run_git(repo, ["rev-parse", args.expect_head], check=False)
        if expected.returncode != 0:
            fail("cannot resolve expected head %s" % args.expect_head, code=4)
        current = run_git(repo, ["rev-parse", args.integration_branch or "HEAD"], check=False)
        if current.returncode != 0 or current.stdout.strip() != expected.stdout.strip():
            fail("stale integration HEAD: expected %s, found %s"
                 % (expected.stdout.strip()[:12], (current.stdout or "?").strip()[:12]), code=7)
    if args.worktree:
        status = run_git(repo, ["-C", args.worktree, "status", "--porcelain"], check=False)
        if status.stdout.strip():
            fail("integration worktree is not clean", code=7, worktree=args.worktree)
    conflicts = None
    if args.base:
        anc = run_git(repo, ["merge-base", "--is-ancestor", args.base, args.candidate], check=False)
        if anc.returncode != 0:
            fail("candidate %s is not a descendant of base %s" % (args.candidate, args.base), code=7)
    if args.target:
        conflicts, detail = _merge_tree_conflicts(repo, args.target, args.candidate)
        if conflicts:
            fail("merge conflict detected against %s" % args.target, code=7, conflicts=detail)
    payload = {"ok": True, "candidate": commit.stdout.strip(), "lock": holder,
               "tests": args.tests, "ownership": "single-writer", "merge": "master-must-run",
               "conflicts": "none" if conflicts is False else "not-checked", "scope": args.scope}
    if args.base:
        payload["base"] = args.base
    if args.target:
        payload["target"] = args.target
    emit(payload)


def _bounded(text, limit=2000):
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "\n...[truncated]"


def _parse_test_output(text):
    counts = {"total": None, "passed": None, "failed": None, "skipped": None}
    failed = []
    m = re.search(r"Ran (\d+) tests?", text)
    if m:
        counts["total"] = int(m.group(1))
    m = re.search(r"^OK(?: \(skipped=(\d+)\))?", text, re.MULTILINE)
    if m:
        counts["skipped"] = int(m.group(1) or 0)
        counts["failed"] = 0
        if counts["total"] is not None:
            counts["passed"] = counts["total"] - counts["skipped"]
    m = re.search(r"FAILED \(([^)]*)\)", text)
    if m:
        body = m.group(1)
        f = re.search(r"failures=(\d+)", body)
        e = re.search(r"errors=(\d+)", body)
        s = re.search(r"skipped=(\d+)", body)
        counts["failed"] = (int(f.group(1)) if f else 0) + (int(e.group(1)) if e else 0)
        counts["skipped"] = int(s.group(1)) if s else 0
        if counts["total"] is not None:
            counts["passed"] = counts["total"] - counts["failed"] - counts["skipped"]
    for key, pat in (("total", r"# tests (\d+)"), ("passed", r"# pass (\d+)"),
                     ("failed", r"# fail (\d+)"), ("skipped", r"# skipped (\d+)")):
        mm = re.search(pat, text)
        if mm:
            counts[key] = int(mm.group(1))
    for line in text.splitlines():
        if line.startswith("FAIL: ") or line.startswith("ERROR: "):
            failed.append(line.split(":", 1)[1].strip())
        mm = re.match(r"not ok \d+ - (.+)", line)
        if mm:
            failed.append(mm.group(1).strip())
    return counts, sorted(set(failed))


def _load_map(repo, path):
    for candidate in (path, os.path.join(repo, ".parallelism", "test-map.json")):
        if candidate and os.path.exists(candidate):
            try:
                return read_json(candidate)
            except ValueError:
                return None
    return None


def cmd_select_tests(args):
    """Deterministic, risk-aware test selection. Unknown/shared changes -> broad suite."""
    repo = find_repo(args.repo)
    data = _load_map(repo, args.map)
    if not data:
        fail("no test map found (--map or <repo>/.parallelism/test-map.json)", code=4)
    base = args.base or "HEAD~1"
    head = args.head or "HEAD"
    diff = run_git(repo, ["diff", "--name-only", base, head], check=False)
    if diff.returncode != 0:
        fail("cannot diff %s..%s" % (base, head), code=4)
    changed = [f for f in diff.stdout.splitlines() if f.strip()]
    shared = data.get("shared", [])
    rules = data.get("rules", [])
    selected, matched, unclassified = set(), {}, []
    full = False
    for f in changed:
        if any(f == s or f.startswith(s.rstrip("/") + "/") for s in shared):
            full = True
            matched.setdefault("shared", []).append(f)
            continue
        hit = next((r for r in rules if f == r.get("match")
                    or f.startswith(r.get("match", "").rstrip("/") + "/")
                    or fnmatch.fnmatch(f, r.get("match", ""))), None)
        if hit is None or not hit.get("tests"):
            unclassified.append(f)
            full = True
            continue
        selected.update(hit["tests"])
        matched.setdefault(hit["match"], []).append(f)
    commands = sorted(set(data.get("full", []))) if full else sorted(selected)
    emit({"ok": True, "base": base, "head": head, "changed": changed, "full": full,
          "unclassified": unclassified, "commands": commands, "matched": matched})


def cmd_run_tests(args):
    """Run a test command, write the full log to disk, return a bounded structured result."""
    repo = find_repo(args.repo)
    state = state_dir(repo)
    pyv = subprocess.run([sys.executable, "--version"], capture_output=True, text=True).stdout.strip()
    nodev = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip() \
        if shutil.which("node") else ""
    head = run_git(repo, ["rev-parse", "HEAD"], check=False).stdout.strip()
    env_id = args.platform or platform.platform()
    key = hashlib.sha256("\n".join([args.cmd, head, pyv, nodev, env_id]).encode()).hexdigest()[:16]
    ev_path = os.path.join(state, "evidence", "%s.json" % key)
    if args.reuse and os.path.exists(ev_path):
        cached = read_json(ev_path)
        cached["reused"] = True
        emit(cached)
    log_path = os.path.join(state, "logs", "test-%s.log" % key)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    timed_out, start = False, time.time()
    try:
        proc = subprocess.run(args.cmd, shell=True, cwd=repo, capture_output=True, text=True,
                              timeout=args.timeout)
        output, exit_code = proc.stdout + "\n" + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + "\n" + (exc.stderr or "")
        exit_code, timed_out = 124, True
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write(output)
    counts, failed = _parse_test_output(output)
    if timed_out:
        counts["timedOut"] = True
    ok = exit_code == 0 and not timed_out
    payload = {"ok": ok, "command": args.cmd, "exitCode": exit_code, "counts": counts,
               "failed": failed, "log": log_path, "platform": env_id,
               "runtime": {"python": pyv, "node": nodev}, "head": head, "key": key,
               "excerpt": _bounded(output[-2000:]) if not ok else "", "reused": False,
               "seconds": round(time.time() - start, 2)}
    if ok:
        write_json(ev_path, dict(payload, storedAt=now()))
    emit(payload)


def build_parser():
    parser = argparse.ArgumentParser(description="parallelism helper utilities (v1.1)")
    parser.add_argument("--repo", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("resolve-model"); p.add_argument("--model"); p.add_argument("--project")
    p.set_defaults(func=cmd_resolve_model)

    p = sub.add_parser("verify-model"); p.add_argument("--session"); p.add_argument("--title")
    p.add_argument("--expect", required=True); p.set_defaults(func=cmd_verify_model)

    p = sub.add_parser("decide"); p.add_argument("--tasks", type=int, required=True)
    for f in ("independence", "overlap", "init-cost", "integration-cost"):
        p.add_argument("--" + f, choices=list(LEVELS), required=True)
    p.set_defaults(func=cmd_decide)

    p = sub.add_parser("checkpoint"); p.add_argument("--name", required=True)
    p.add_argument("--status"); p.add_argument("--commit"); p.add_argument("--evidence")
    p.add_argument("--tests"); p.add_argument("--blocker"); p.add_argument("--message")
    p.add_argument("--model"); p.add_argument("--branch"); p.add_argument("--worktree")
    p.set_defaults(func=cmd_checkpoint)

    p = sub.add_parser("status"); p.set_defaults(func=cmd_status)

    p = sub.add_parser("progress"); p.add_argument("--name", required=True)
    p.add_argument("--limit", type=int, default=2); p.set_defaults(func=cmd_progress)

    p = sub.add_parser("spawn"); p.add_argument("--name", required=True); p.add_argument("--id")
    p.add_argument("--model", required=True); p.add_argument("--assignment")
    p.add_argument("--objective"); p.add_argument("--owns"); p.add_argument("--excludes")
    p.add_argument("--accept"); p.add_argument("--tests"); p.add_argument("--worktree")
    p.add_argument("--branch"); p.add_argument("--base-sha"); p.add_argument("--group")
    p.add_argument("--resume", action="store_true"); p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_spawn)

    p = sub.add_parser("wait"); p.add_argument("--name"); p.add_argument("--names")
    p.add_argument("--group"); p.add_argument("--timeout", type=float)
    p.add_argument("--poll", type=float, default=0.2); p.set_defaults(func=cmd_wait)

    p = sub.add_parser("collect"); p.add_argument("--name"); p.add_argument("--names")
    p.add_argument("--group"); p.set_defaults(func=cmd_collect)

    p = sub.add_parser("result"); p.add_argument("--name", required=True)
    p.add_argument("--file"); p.set_defaults(func=cmd_result)

    p = sub.add_parser("lock"); p.add_argument("action", choices=["acquire", "release", "status"])
    p.add_argument("--name", required=True); p.add_argument("--owner"); p.add_argument("--pid", type=int)
    p.set_defaults(func=cmd_lock)

    p = sub.add_parser("premerge"); p.add_argument("--candidate", required=True)
    p.add_argument("--base"); p.add_argument("--tests"); p.add_argument("--lock", default="integration")
    p.add_argument("--expect-head"); p.add_argument("--integration-branch")
    p.add_argument("--target"); p.add_argument("--worktree"); p.add_argument("--scope")
    p.set_defaults(func=cmd_premerge)

    p = sub.add_parser("select-tests"); p.add_argument("--map"); p.add_argument("--base")
    p.add_argument("--head"); p.set_defaults(func=cmd_select_tests)

    p = sub.add_parser("run-tests"); p.add_argument("--cmd", required=True)
    p.add_argument("--platform"); p.add_argument("--timeout", type=float, default=1800)
    p.add_argument("--reuse", action="store_true"); p.set_defaults(func=cmd_run_tests)

    return parser


def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except RuntimeError as exc:
        fail(str(exc), code=1)


if __name__ == "__main__":
    main()
