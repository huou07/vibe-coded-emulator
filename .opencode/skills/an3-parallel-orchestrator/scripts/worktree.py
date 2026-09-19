#!/usr/bin/env python3
"""Safe, idempotent Git worktree/branch management for an orchestration run.

Usage:
  worktree.py create --run-id <id> --domain <d> --base-sha <sha> [--repo <path>] [--path <p>] [--branch <b>]
  worktree.py create-integration --run-id <id> --base-sha <sha> [--repo <path>]
  worktree.py list --run-id <id> [--repo <path>]
  worktree.py validate --path <worktree> [--repo <path>]
  worktree.py remove --run-id <id> --domain <d> [--repo <path>] [--allow-unmerged] [--keep-branch]
  worktree.py prune [--repo <path>]

Fail-closed: never overwrites a path, never removes a dirty or unintegrated
worktree without an explicit override, never touches the main worktree.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import orchestrator_lib as lib  # noqa: E402

WT = lib.load_config()["worktree"]


def worktree_root(repo: str) -> str:
    root = WT["root"]
    return root if os.path.isabs(root) else os.path.normpath(os.path.join(repo, root))


def worktree_path(repo: str, run_id: str, domain: str) -> str:
    return os.path.join(worktree_root(repo), "%s-%s-%s" % (WT["prefix"], run_id, domain))


def agent_branch(run_id: str, domain: str) -> str:
    return "%s/%s/%s" % (WT["agentBranchPrefix"], run_id, domain)


def integration_branch(run_id: str) -> str:
    return "%s/%s" % (WT["integrationBranchPrefix"], run_id)


def _worktrees(repo):
    proc = lib.run_git(repo, ["worktree", "list", "--porcelain"])
    entries = []
    block = {}
    for line in proc.stdout.splitlines() + [""]:
        if not line.strip():
            if block:
                entries.append(block)
                block = {}
            continue
        key, _, value = line.partition(" ")
        block[key] = value
    return entries


def _find_entry(entries, path):
    real = os.path.realpath(path)
    for entry in entries:
        if entry.get("worktree") and os.path.realpath(entry["worktree"]) == real:
            return entry
    return None


def _record_in_state(repo, run_id, domain, branch, path):
    rdir = lib.run_dir(repo, run_id)
    manifest = os.path.join(rdir, "manifest.json")
    if not os.path.exists(manifest):
        return
    def mutate(m):
        m.setdefault("worktrees", {})[domain] = path
        m.setdefault("branches", {})[domain] = branch
        return m
    lib.update_json(manifest, mutate)


def cmd_create(args: argparse.Namespace) -> None:
    repo = lib.find_repo_root(args.repo)
    lib.validate_run_id(args.run_id)
    lib.validate_domain(args.domain)
    base = lib.require_commit(repo, args.base_sha, "base-sha")
    branch = args.branch or agent_branch(args.run_id, args.domain)
    path = os.path.abspath(args.path or worktree_path(repo, args.run_id, args.domain))
    if os.path.realpath(path) == os.path.realpath(repo):
        lib.fail("refusing to use the main checkout as a worktree", code=3)

    entries = _worktrees(repo)
    existing = _find_entry(entries, path)
    if os.path.exists(path):
        if existing and existing.get("branch") == "refs/heads/%s" % branch:
            lib.emit({"ok": True, "state": "EXISTING", "path": path, "branch": branch})
        lib.fail("path exists but is not the expected worktree", code=3, path=path, branch=branch)

    branch_exists = lib.git_ok(repo, ["rev-parse", "--verify", "refs/heads/%s" % branch])
    if branch_exists:
        proc = lib.run_git(repo, ["worktree", "add", path, branch], check=False)
        reused = True
    else:
        proc = lib.run_git(repo, ["worktree", "add", "-b", branch, path, base], check=False)
        reused = False
    if proc.returncode != 0:
        lib.fail("git worktree add failed", code=1, stderr=proc.stderr.strip(), path=path, branch=branch)
    _record_in_state(repo, args.run_id, args.domain, branch, path)
    lib.emit({"ok": True, "state": "REUSED" if reused else "CREATED", "path": path,
              "branch": branch, "baseSha": base})


def cmd_create_integration(args: argparse.Namespace) -> None:
    args.domain = "integration"
    args.branch = integration_branch(args.run_id)
    args.path = worktree_path(lib.find_repo_root(args.repo), args.run_id, "integration")
    cmd_create(args)


def cmd_list(args: argparse.Namespace) -> None:
    repo = lib.find_repo_root(args.repo)
    lib.validate_run_id(args.run_id)
    rdir = lib.run_dir(repo, args.run_id)
    manifest_path = os.path.join(rdir, "manifest.json")
    manifest = lib.read_json(manifest_path) if os.path.exists(manifest_path) else {}
    entries = _worktrees(repo)
    result = []
    for domain, path in (manifest.get("worktrees") or {}).items():
        entry = _find_entry(entries, path)
        dirty = None
        if entry:
            status = lib.run_git(repo, ["-C", path, "status", "--porcelain"], check=False)
            dirty = bool(status.stdout.strip())
        result.append({
            "domain": domain,
            "path": path,
            "branch": (manifest.get("branches") or {}).get(domain),
            "registered": entry is not None,
            "head": (entry or {}).get("HEAD"),
            "dirty": dirty,
        })
    lib.emit({"ok": True, "runId": args.run_id, "worktrees": result})


def cmd_validate(args: argparse.Namespace) -> None:
    repo = lib.find_repo_root(args.repo)
    path = os.path.abspath(args.path)
    entry = _find_entry(_worktrees(repo), path)
    problems = []
    if entry is None:
        problems.append("path is not a registered worktree of this repository")
    else:
        if entry.get("detached") == "detached":
            problems.append("worktree is in detached HEAD")
        branch_ref = entry.get("branch", "")
        if not branch_ref.startswith("refs/heads/agent/") and not branch_ref.startswith("refs/heads/integration/") \
                and not branch_ref.startswith("refs/heads/promotion/"):
            problems.append("branch %s is outside the orchestrator naming policy" % branch_ref)
        if os.path.realpath(path) == os.path.realpath(repo):
            problems.append("path is the main checkout")
    lib.emit({"ok": not problems, "path": path, "entry": entry, "problems": problems},
             exit_code=0 if not problems else 1)


def _recorded_path(repo, run_id, domain):
    manifest_path = os.path.join(lib.run_dir(repo, run_id), "manifest.json")
    if os.path.exists(manifest_path):
        try:
            recorded = (lib.read_json(manifest_path).get("worktrees") or {}).get(domain)
            if recorded:
                return recorded
        except ValueError:
            pass
    return worktree_path(repo, run_id, domain)


def _recorded_branch(repo, run_id, domain):
    manifest_path = os.path.join(lib.run_dir(repo, run_id), "manifest.json")
    if os.path.exists(manifest_path):
        try:
            recorded = (lib.read_json(manifest_path).get("branches") or {}).get(domain)
            if recorded:
                return recorded
        except ValueError:
            pass
    return agent_branch(run_id, domain)


def cmd_remove(args: argparse.Namespace) -> None:
    repo = lib.find_repo_root(args.repo)
    lib.validate_run_id(args.run_id)
    lib.validate_domain(args.domain)
    path = os.path.abspath(args.path) if args.path else _recorded_path(repo, args.run_id, args.domain)
    branch = _recorded_branch(repo, args.run_id, args.domain)
    if os.path.realpath(path) == os.path.realpath(repo):
        lib.fail("refusing to remove the main checkout", code=3)
    entry = _find_entry(_worktrees(repo), path)
    if entry is None and not os.path.exists(path):
        lib.emit({"ok": True, "state": "NOOP", "reason": "worktree absent", "path": path})
    problems = []
    if entry is not None:
        status = lib.run_git(repo, ["-C", path, "status", "--porcelain"], check=False)
        if status.stdout.strip():
            problems.append("worktree is dirty")
    if not args.allow_unmerged:
        manifest_path = os.path.join(lib.run_dir(repo, args.run_id), "manifest.json")
        manifest = lib.read_json(manifest_path) if os.path.exists(manifest_path) else {}
        reference = integration_branch(args.run_id)
        if not lib.git_ok(repo, ["rev-parse", "--verify", "refs/heads/%s" % reference]):
            reference = (manifest.get("baseSha") or "HEAD")
        if lib.git_ok(repo, ["rev-parse", "--verify", "refs/heads/%s" % branch]):
            merged = lib.run_git(repo, ["merge-base", "--is-ancestor", branch, reference], check=False)
            if merged.returncode != 0:
                problems.append("branch %s is not merged into %s" % (branch, reference))
    if problems:
        lib.fail("refusing to remove worktree", code=3, path=path, problems=problems,
                 hint="pass --allow-unmerged to override after confirming no recoverable work")
    proc = lib.run_git(repo, ["worktree", "remove", path], check=False)
    if proc.returncode != 0:
        lib.fail("git worktree remove failed", code=1, stderr=proc.stderr.strip())
    if not args.keep_branch:
        lib.run_git(repo, ["branch", "-D" if args.allow_unmerged else "-d", branch], check=False)
    lib.emit({"ok": True, "state": "REMOVED", "path": path, "branch": branch})


def cmd_prune(args: argparse.Namespace) -> None:
    repo = lib.find_repo_root(args.repo)
    proc = lib.run_git(repo, ["worktree", "prune"])
    lib.emit({"ok": True, "pruned": True, "stdout": proc.stdout.strip()})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AN3 orchestrator worktrees")
    parser.add_argument("--repo", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create")
    p.add_argument("--run-id", required=True)
    p.add_argument("--domain", required=True)
    p.add_argument("--base-sha", required=True)
    p.add_argument("--path")
    p.add_argument("--branch")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("create-integration")
    p.add_argument("--run-id", required=True)
    p.add_argument("--base-sha", required=True)
    p.set_defaults(func=cmd_create_integration)

    p = sub.add_parser("list")
    p.add_argument("--run-id", required=True)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("validate")
    p.add_argument("--path", required=True)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("remove")
    p.add_argument("--run-id", required=True)
    p.add_argument("--domain", required=True)
    p.add_argument("--allow-unmerged", action="store_true")
    p.add_argument("--keep-branch", action="store_true")
    p.add_argument("--path")
    p.set_defaults(func=cmd_remove)

    sub.add_parser("prune").set_defaults(func=cmd_prune)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except lib.OrchestratorError as exc:
        lib.fail(exc.message, code=exc.code, **exc.detail)


if __name__ == "__main__":
    main()
