#!/usr/bin/env python3
"""Safe cleanup for an orchestration run (dry-run by default).

Usage:
  cleanup_run.py --run-id <id> [--repo P] [--apply] [--allow-unmerged] [--delete-branches]

Releases the run's resource leases and removes its worktrees/branches. Evidence
under the Git common dir is always kept. Nothing is removed unless `--apply` is
given, and an unmerged or dirty worktree is refused without `--allow-unmerged`.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import orchestrator_lib as lib  # noqa: E402

WORKTREE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "worktree.py")


def plan_leases(repo, run_id):
    root = lib.locks_dir(repo)
    leases = []
    if not os.path.isdir(root):
        return leases
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        lease_path = os.path.join(path, "lease.json")
        if os.path.isdir(path) and os.path.exists(lease_path):
            lease = lib.read_json(lease_path)
            if lease.get("runId") == run_id and not lease.get("releasedAt"):
                leases.append(lease)
    return leases


def main():
    parser = argparse.ArgumentParser(description="Clean up an AN3 orchestrator run")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repo", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-unmerged", action="store_true")
    parser.add_argument("--delete-branches", action="store_true")
    args = parser.parse_args()
    try:
        repo = lib.find_repo_root(args.repo)
        lib.validate_run_id(args.run_id)
        rdir = lib.run_dir(repo, args.run_id)
        manifest_path = os.path.join(rdir, "manifest.json")
        if not os.path.exists(manifest_path):
            lib.fail("unknown run %s" % args.run_id, code=4)
        manifest = lib.read_json(manifest_path)
        worktrees = manifest.get("worktrees") or {}
        leases = plan_leases(repo, args.run_id)
        plan = {
            "runId": args.run_id,
            "dryRun": not args.apply,
            "leasesToRelease": [{"resource": l.get("resource"), "owner": l.get("ownerSession")} for l in leases],
            "worktreesToRemove": list(worktrees.keys()),
            "keepEvidence": os.path.join(rdir, "evidence"),
            "deleteBranches": args.delete_branches,
        }
        if not args.apply:
            lib.emit({"ok": True, "plan": plan, "applied": False})
        actions = []
        for lease in leases:
            proc = subprocess.run(
                [sys.executable, os.path.join(os.path.dirname(WORKTREE_SCRIPT), "resource_lock.py"),
                 "--repo", repo, "release", lease["resource"], lease.get("ownerSession", "")],
                capture_output=True, text=True,
            )
            actions.append({"release": lease.get("resource"), "rc": proc.returncode})
        for domain in list(worktrees.keys()):
            cmd = [sys.executable, WORKTREE_SCRIPT, "--repo", repo, "remove", "--run-id", args.run_id,
                   "--domain", domain, "--keep-branch"]
            if args.allow_unmerged:
                cmd.append("--allow-unmerged")
            proc = subprocess.run(cmd, capture_output=True, text=True)
            actions.append({"remove": domain, "rc": proc.returncode,
                            "detail": (proc.stdout or proc.stderr).strip()[:400]})
        if args.delete_branches:
            for domain, branch in (manifest.get("branches") or {}).items():
                flag = "-D" if args.allow_unmerged else "-d"
                lib.run_git(repo, ["branch", flag, branch], check=False)
                actions.append({"delete-branch": branch, "flag": flag})
        lib.emit({"ok": True, "plan": plan, "applied": True, "actions": actions})
    except lib.OrchestratorError as exc:
        lib.fail(exc.message, code=exc.code, **exc.detail)


if __name__ == "__main__":
    main()
