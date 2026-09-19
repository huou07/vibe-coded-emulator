#!/usr/bin/env python3
"""Shared helpers for the AN3 parallel-orchestrator scripts.

Python 3.9 compatible, standard library only. Every script in this directory
imports this module for repo/state discovery, atomic JSON writes, cross-process
locking, Git access and PID liveness. Nothing here is destructive by itself.
"""
from __future__ import annotations

import errno
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

try:
    import fcntl  # POSIX (macOS/Linux)
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SKILL_DIR, "config.json")


class OrchestratorError(Exception):
    """Fatal, fail-closed error with a machine-readable exit code."""

    def __init__(self, message: str, code: int = 1, detail: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.detail = detail or {}


def load_config() -> Dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


CANONICAL_MODEL = load_config()["model"]
MANIFEST_SCHEMA_VERSION = load_config()["manifestSchemaVersion"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def epoch_seconds() -> int:
    return int(time.time())


def emit(payload: Dict[str, Any], exit_code: int = 0) -> None:
    """Print a single machine-readable JSON object and exit."""
    print(json.dumps(payload, indent=2, sort_keys=True))
    sys.exit(exit_code)


def fail(message: str, code: int = 1, **detail: Any) -> None:
    emit({"ok": False, "error": message, **detail}, code)


def run_git(repo: str, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        raise OrchestratorError(
            "git %s failed: %s" % (" ".join(args), proc.stderr.strip()),
            detail={"args": args, "stderr": proc.stderr.strip()},
        )
    return proc


def git_ok(repo: str, args: List[str]) -> bool:
    return run_git(repo, args, check=False).returncode == 0


def find_repo_root(start: Optional[str] = None) -> str:
    """Walk up from `start` (cwd by default) to the nearest git checkout."""
    current = os.path.abspath(start or os.getcwd())
    if os.path.isfile(current):
        current = os.path.dirname(current)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            raise OrchestratorError("no git repository found above %s" % (start or os.getcwd()))
        current = parent


def git_common_dir(repo: str) -> str:
    """Absolute shared Git common directory (works from any linked worktree)."""
    proc = run_git(repo, ["rev-parse", "--path-format=absolute", "--git-common-dir"], check=False)
    if proc.returncode != 0:
        proc = run_git(repo, ["rev-parse", "--git-common-dir"])
    value = proc.stdout.strip()
    if not os.path.isabs(value):
        value = os.path.abspath(os.path.join(repo, value))
    return os.path.realpath(value)


def state_root(repo: str) -> str:
    return os.path.join(git_common_dir(repo), load_config()["stateDir"])


def run_dir(repo: str, run_id: str) -> str:
    validate_run_id(run_id)
    return os.path.join(state_root(repo), run_id)


def locks_dir(repo: str) -> str:
    return os.path.join(state_root(repo), "locks")


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write_json(path: str, data: Any) -> None:
    """Write JSON via a temp file + os.replace so readers never see partial bytes."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        # fsync the directory so the rename itself is durable across a crash.
        try:
            dir_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def file_lock(path: str, timeout: float = 30.0):
    """Cross-process advisory lock (fcntl) with a bounded spin."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    handle = open(path, "a+", encoding="utf-8")
    deadline = time.time() + timeout
    if fcntl is None:  # pragma: no cover - non-POSIX fallback
        try:
            yield
        finally:
            handle.close()
        return
    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EAGAIN) or time.time() >= deadline:
                handle.close()
                raise OrchestratorError("could not acquire lock %s" % path, code=7)
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def update_json(path: str, mutator: Callable[[Any], Any]) -> Any:
    """Atomic read-modify-write under a sibling .lock file."""
    lock_path = path + ".lock"
    with file_lock(lock_path):
        if os.path.exists(path):
            data = read_json(path)
        else:
            data = {}
        result = mutator(data)
        atomic_write_json(path, result)
        return result


def is_pid_alive(pid: Optional[int]) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    return True


def validate_run_id(run_id: str) -> None:
    if not run_id or not run_id.replace("-", "").isalnum():
        raise OrchestratorError("invalid run id: %r (use <YYYYMMDD>-<HHMM>)" % run_id, code=64)


def validate_domain(domain: str) -> None:
    import re

    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", domain or ""):
        raise OrchestratorError(
            "invalid domain: %r (lowercase [a-z0-9-], no spaces/slashes)" % domain, code=64
        )


def require_commit(repo: str, sha: str, label: str) -> str:
    proc = run_git(repo, ["rev-parse", "--verify", "%s^{commit}" % sha], check=False)
    if proc.returncode != 0:
        raise OrchestratorError("%s is not a commit: %s" % (label, sha), code=4)
    return proc.stdout.strip()


def parse_frontmatter(path: str) -> Dict[str, str]:
    """Extract a flat YAML frontmatter map (top-level `key: value` lines only)."""
    with open(path, "r", encoding="utf-8") as handle:
        lines = handle.readlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result: Dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


# --- atomically serialized compound run-state updates -----------------------


@contextmanager
def run_lock(rdir: str, timeout: float = 60.0):
    """Serialize compound multi-file run-state updates across processes.

    Individual `update_json` calls are already atomic, but operations that touch
    two files (for example sessions.json + manifest.json) can interleave and
    lose updates. Wrap them in this run-level lock.
    """
    os.makedirs(rdir, exist_ok=True)
    with file_lock(os.path.join(rdir, ".run.lock"), timeout=timeout):
        yield


# --- git identity helpers (provenance) --------------------------------------


def git_patch_id(repo: str, sha: str) -> Optional[str]:
    """Stable patch-id of a commit's diff (None if the diff is empty/unknown)."""
    show = subprocess.run(["git", "-C", repo, "show", "--no-color", sha],
                          capture_output=True, text=True)
    if show.returncode != 0:
        return None
    proc = subprocess.run(["git", "-C", repo, "patch-id", "--stable"],
                          input=show.stdout, capture_output=True, text=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout.strip().split()[0]


def git_tree(repo: str, sha: str) -> Optional[str]:
    proc = run_git(repo, ["rev-parse", "%s^{tree}" % sha], check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def git_changed_files(repo: str, a: str, b: str) -> List[str]:
    proc = run_git(repo, ["diff", "--name-only", a, b], check=False)
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def git_is_ancestor(repo: str, ancestor: str, descendant: str) -> bool:
    proc = run_git(repo, ["merge-base", "--is-ancestor", ancestor, descendant], check=False)
    return proc.returncode == 0


def ref_exists(repo: str, ref: str) -> bool:
    return git_ok(repo, ["rev-parse", "--verify", ref])


def resolve_head(repo: str, ref: str) -> Optional[str]:
    proc = run_git(repo, ["rev-parse", ref], check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def paths_overlap(declared: str, pattern: str) -> bool:
    """True when a declared module/file plausibly covers a central contract.

    Declared values may be files, directories, or globs; patterns may be exact
    paths or globs. `*` matches across `/`, matching fnmatch semantics.
    """
    import fnmatch

    declared = (declared or "").rstrip("/")
    pattern = (pattern or "").rstrip("/")
    if not declared or not pattern:
        return False
    if declared == pattern:
        return True
    if pattern.startswith(declared + "/"):  # declared is a directory
        return True
    if declared.startswith(pattern + "/"):  # declared is inside a contract directory
        return True
    if fnmatch.fnmatch(declared, pattern) or fnmatch.fnmatch(pattern, declared):
        return True
    return False


# --- session lifecycle ------------------------------------------------------


def read_ndjson_events(log_path: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if not os.path.exists(log_path):
        return events
    with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
    if limit is not None:
        return events[-limit:]
    return events


def last_event_type(log_path: str) -> Optional[str]:
    last = None
    for event in read_ndjson_events(log_path):
        last = event.get("type", last)
    return last


# OpenCode event types that mean the agent loop for that prompt has finished.
# The launcher process may then exit while the session stays resumable.
TERMINAL_SESSION_EVENTS = {"step_finish", "session.idle", "session_idle", "idle"}


def session_state(session: Dict[str, Any], log_path: Optional[str] = None,
                  process_alive: Optional[bool] = None) -> str:
    """PROCESS_RUNNING | SESSION_RESUMABLE | SESSION_UNKNOWN | SESSION_DEAD.

    A launcher exiting does not mean the session is dead: `opencode run` records
    a durable session id that `--session` can resume. Only when there is no
    recorded session id at all (or it is the UNKNOWN placeholder) is the session
    considered dead.
    """
    alive = is_pid_alive(session.get("pid")) if process_alive is None else process_alive
    if alive:
        return "PROCESS_RUNNING"
    session_id = session.get("sessionId") or session.get("session_id")
    if not session_id or session_id == "UNKNOWN":
        return "SESSION_DEAD"
    last = last_event_type(log_path) if log_path else None
    if last in TERMINAL_SESSION_EVENTS:
        return "SESSION_RESUMABLE"
    if last is None:
        return "SESSION_UNKNOWN"
    # a non-terminal last event with a dead launcher is recoverable uncertainty
    return "SESSION_UNKNOWN"
