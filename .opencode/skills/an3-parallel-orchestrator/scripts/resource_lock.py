#!/usr/bin/env python3
"""Atomic cross-process resource leases for an orchestration run.

Usage:
  resource_lock.py acquire <resource> <owner> <purpose> [--ttl S] [--run-id ID] [--pid N] [--break-stale] [--break-malformed] [--repo P]
  resource_lock.py release <resource> <owner> [--break-malformed] [--repo P]
  resource_lock.py renew   <resource> <owner> [--ttl S] [--repo P]
  resource_lock.py status  [resource] [--repo P]
  resource_lock.py list    [--repo P]

Exit codes: 0 ok, 2 denied (held by another owner), 3 refused unsafe override,
4 usage/error, 7 lock error. An apparently active lease is never stolen; stale
recovery needs an expired lease AND a dead pid; malformed/crashed lock
directories require the explicit --break-malformed.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import orchestrator_lib as lib  # noqa: E402

# lease directory states
ST_HELD = "HELD"
ST_HELD_UNVERIFIED = "HELD_UNVERIFIED"
ST_STALE = "STALE"
ST_RELEASED = "RELEASED"
ST_MALFORMED = "MALFORMED"
ST_UNKNOWN = "UNKNOWN"


def slug(resource: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in resource)


def lock_dir(repo: str, resource: str) -> str:
    return os.path.join(lib.locks_dir(repo), slug(resource) + ".lock")


def lease_dir_state(path: str):
    """Return (state, lease_or_None) for a lock directory."""
    if not os.path.isdir(path):
        return None, None
    lease_path = os.path.join(path, "lease.json")
    if not os.path.exists(lease_path):
        return ST_UNKNOWN, None
    try:
        lease = lib.read_json(lease_path)
    except (OSError, ValueError):
        return ST_MALFORMED, None
    if not isinstance(lease, dict):
        return ST_MALFORMED, None
    if lease.get("releasedAt"):
        return ST_RELEASED, lease
    until = lease.get("leaseUntil")
    pid = lease.get("pid")
    expired = bool(isinstance(until, (int, float)) and until and time.time() > until)
    if expired and not lib.is_pid_alive(pid):
        return ST_STALE, lease
    if pid and not lib.is_pid_alive(pid) and not expired:
        return ST_HELD_UNVERIFIED, lease
    return ST_HELD, lease


def _history(repo: str, record) -> None:
    path = os.path.join(lib.state_root(repo), "lease-history.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with lib.file_lock(path + ".lock"):
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def cmd_acquire(args: argparse.Namespace) -> None:
    repo = lib.find_repo_root(args.repo)
    path = lock_dir(repo, args.resource)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.isdir(path):
        state, lease = lease_dir_state(path)
        broke = False
        if state == ST_STALE and args.break_stale:
            shutil.move(path, path + ".stale-%d" % int(time.time()))
            broke = True
        elif state in (ST_UNKNOWN, ST_MALFORMED) and args.break_malformed:
            shutil.move(path, path + ".malformed-%d" % int(time.time()))
            broke = True
        if not broke:
            hint = None
            if state == ST_STALE:
                hint = "lease is expired and its pid is dead; re-run with --break-stale"
            elif state in (ST_UNKNOWN, ST_MALFORMED):
                hint = "crashed or malformed lock; re-run with --break-malformed after checking no owner is active"
            lib.emit({"ok": False, "acquired": False, "resource": args.resource, "state": state,
                      "lease": lease, "hint": hint, "error": "resource is held"}, exit_code=2)
    try:
        os.mkdir(path)
    except FileExistsError:
        # another process won the mkdir race between our check and our attempt;
        # report it as a normal denial, never a hard error.
        state, lease = lease_dir_state(path)
        lib.emit({"ok": False, "acquired": False, "resource": args.resource,
                  "state": state or ST_HELD, "lease": lease,
                  "error": "lost the acquisition race to another process"}, exit_code=2)
    lease = {
        "resource": args.resource,
        "ownerSession": args.owner,
        "runId": args.run_id,
        "pid": args.pid if args.pid is not None else os.getpid(),
        "acquiredAt": lib.utc_now_iso(),
        "leaseUntil": lib.epoch_seconds() + args.ttl,
        "purpose": args.purpose,
    }
    lib.atomic_write_json(os.path.join(path, "lease.json"), lease)
    _history(repo, {"event": "acquire", **lease})
    lib.emit({"ok": True, "acquired": True, "resource": args.resource, "lease": lease})


def cmd_release(args: argparse.Namespace) -> None:
    repo = lib.find_repo_root(args.repo)
    path = lock_dir(repo, args.resource)
    if not os.path.isdir(path):
        lib.emit({"ok": True, "released": False, "reason": "not held", "resource": args.resource})
    state, lease = lease_dir_state(path)
    if state in (ST_UNKNOWN, ST_MALFORMED):
        if not args.break_malformed:
            lib.fail("lock is %s; pass --break-malformed after checking no owner is active" % state,
                     code=3, state=state)
        shutil.rmtree(path, ignore_errors=True)
        lib.emit({"ok": True, "released": True, "resource": args.resource, "state": state})
    if lease and lease.get("ownerSession") != args.owner:
        lib.fail("resource held by %s, not %s" % (lease.get("ownerSession"), args.owner),
                 code=3, lease=lease)
    if lease:
        lease["releasedAt"] = lib.utc_now_iso()
        _history(repo, {"event": "release", **lease})
    shutil.rmtree(path, ignore_errors=True)
    lib.emit({"ok": True, "released": True, "resource": args.resource, "owner": args.owner})


def cmd_renew(args: argparse.Namespace) -> None:
    repo = lib.find_repo_root(args.repo)
    path = lock_dir(repo, args.resource)
    state, lease = lease_dir_state(path)
    if not os.path.isdir(path):
        lib.fail("resource not held", code=4)
    if lease is None:
        lib.fail("lock is %s; cannot renew" % state, code=3, state=state)
    if lease.get("ownerSession") != args.owner:
        lib.fail("resource held by another owner", code=3, lease=lease)
    lease["leaseUntil"] = lib.epoch_seconds() + args.ttl
    lease["renewedAt"] = lib.utc_now_iso()
    lib.atomic_write_json(os.path.join(path, "lease.json"), lease)
    lib.emit({"ok": True, "renewed": True, "resource": args.resource, "lease": lease})


def _collect(repo, want=None):
    root = lib.locks_dir(repo)
    results = []
    if not os.path.isdir(root):
        return results
    for name in sorted(os.listdir(root)):
        if not name.endswith(".lock"):
            continue
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        state, lease = lease_dir_state(path)
        if want and (lease or {}).get("resource") != want and slug(want) != name[:-len(".lock")]:
            continue
        results.append({"state": state, "lease": lease, "dir": path})
    return results


def cmd_status(args: argparse.Namespace) -> None:
    repo = lib.find_repo_root(args.repo)
    leaselist = _collect(repo, args.resource)
    lib.emit({"ok": True, "resource": args.resource, "leases": leaselist})


def cmd_list(args: argparse.Namespace) -> None:
    repo = lib.find_repo_root(args.repo)
    lib.emit({"ok": True, "leases": _collect(repo)})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AN3 orchestrator resource leases")
    parser.add_argument("--repo", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("acquire")
    p.add_argument("resource")
    p.add_argument("owner")
    p.add_argument("purpose")
    p.add_argument("--ttl", type=int, default=1800)
    p.add_argument("--run-id")
    p.add_argument("--pid", type=int)
    p.add_argument("--break-stale", action="store_true")
    p.add_argument("--break-malformed", action="store_true")
    p.set_defaults(func=cmd_acquire)

    p = sub.add_parser("release")
    p.add_argument("resource")
    p.add_argument("owner")
    p.add_argument("--break-malformed", action="store_true")
    p.set_defaults(func=cmd_release)

    p = sub.add_parser("renew")
    p.add_argument("resource")
    p.add_argument("owner")
    p.add_argument("--ttl", type=int, default=1800)
    p.set_defaults(func=cmd_renew)

    p = sub.add_parser("status")
    p.add_argument("resource", nargs="?")
    p.set_defaults(func=cmd_status)

    sub.add_parser("list").set_defaults(func=cmd_list)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except lib.OrchestratorError as exc:
        lib.fail(exc.message, code=exc.code, **exc.detail)


if __name__ == "__main__":
    main()
