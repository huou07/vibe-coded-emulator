#!/usr/bin/env python3
"""Atomic cross-process resource leases for an orchestration run.

Usage:
  resource_lock.py acquire <resource> <owner> <purpose> [--ttl S] [--run-id ID] [--pid N] [--break-stale] [--repo P]
  resource_lock.py release <resource> <owner> [--repo P]
  resource_lock.py renew   <resource> <owner> [--ttl S] [--repo P]
  resource_lock.py status  [resource] [--repo P]
  resource_lock.py list    [--repo P]

Exit codes: 0 ok, 2 denied (held by another owner), 3 refused unsafe override,
4 usage/error, 7 lock error. An apparently active lease is never stolen.
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


def slug(resource: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in resource)


def lock_dir(repo: str, resource: str) -> str:
    return os.path.join(lib.locks_dir(repo), slug(resource) + ".lock")


def read_lease(path: str):
    lease_path = os.path.join(path, "lease.json")
    if not os.path.exists(lease_path):
        return None
    try:
        return lib.read_json(lease_path)
    except (OSError, ValueError):
        return None


def lease_state(lease):
    if not lease:
        return "UNKNOWN"
    if lease.get("releasedAt"):
        return "RELEASED"
    until = lease.get("leaseUntil")
    pid = lease.get("pid")
    expired = False
    if isinstance(until, (int, float)) and until and time.time() > until:
        expired = True
    if expired and not lib.is_pid_alive(pid):
        return "STALE"
    if pid and not lib.is_pid_alive(pid) and not expired:
        return "HELD_UNVERIFIED"
    return "HELD"


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
    current = read_lease(path) if os.path.isdir(path) else None
    if os.path.isdir(path):
        state = lease_state(current)
        if args.break_stale:
            if state != "STALE":
                lib.fail("refusing --break-stale: lease state is %s" % state, code=3,
                         lease=current, state=state)
            shutil.move(path, path + ".stale-%d" % int(time.time()))
        else:
            lib.emit({"ok": False, "acquired": False, "resource": args.resource, "state": state,
                      "lease": current, "error": "resource is held"}, exit_code=2)
    try:
        os.mkdir(path)
    except FileExistsError:
        lib.fail("lost race acquiring %s" % args.resource, code=7)
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


def _owned(repo, resource, owner):
    path = lock_dir(repo, resource)
    lease = read_lease(path) if os.path.isdir(path) else None
    if lease is None:
        return path, None
    if lease.get("ownerSession") != owner:
        return path, lease
    return path, None


def cmd_release(args: argparse.Namespace) -> None:
    repo = lib.find_repo_root(args.repo)
    path, foreign = _owned(repo, args.resource, args.owner)
    if not os.path.isdir(path):
        lib.emit({"ok": True, "released": False, "reason": "not held", "resource": args.resource})
    if foreign is not None:
        lib.fail("resource held by %s, not %s" % (foreign.get("ownerSession"), args.owner),
                 code=3, lease=foreign)
    lease = read_lease(path)
    if lease:
        lease["releasedAt"] = lib.utc_now_iso()
        _history(repo, {"event": "release", **lease})
    shutil.rmtree(path, ignore_errors=True)
    lib.emit({"ok": True, "released": True, "resource": args.resource, "owner": args.owner})


def cmd_renew(args: argparse.Namespace) -> None:
    repo = lib.find_repo_root(args.repo)
    path, foreign = _owned(repo, args.resource, args.owner)
    if foreign is not None:
        lib.fail("resource held by another owner", code=3, lease=foreign)
    if not os.path.isdir(path):
        lib.fail("resource not held", code=4)
    def mutate(_):
        lease = read_lease(path)
        lease["leaseUntil"] = lib.epoch_seconds() + args.ttl
        lease["renewedAt"] = lib.utc_now_iso()
        return lease
    lease = lib.update_json(os.path.join(path, "lease.json"), mutate)
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
        lease = read_lease(path)
        state = lease_state(lease)
        if lease and lease.get("releasedAt"):
            state = "RELEASED"
        if want and (lease or {}).get("resource") != want:
            continue
        results.append({"state": state, "lease": lease, "dir": path})
    return results


def cmd_status(args: argparse.Namespace) -> None:
    repo = lib.find_repo_root(args.repo)
    lib.emit({"ok": True, "resource": args.resource, "leases": _collect(repo, args.resource)})


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
    p.set_defaults(func=cmd_acquire)

    p = sub.add_parser("release")
    p.add_argument("resource")
    p.add_argument("owner")
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
