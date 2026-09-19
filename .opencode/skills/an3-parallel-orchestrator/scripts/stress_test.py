#!/usr/bin/env python3
"""Synthetic orchestration stress test (disposable repo, real OpenCode sessions).

Exercises 3 top-level worker sessions, read-only subagents, a dependency edge, a
shared resource lease, an integration-only task, a deliberate candidate conflict,
QA, integration with an adapter, provenance records and cleanup.

Usage:
  stress_test.py [--repo P] [--keep] [--timeout S]

Creates a throwaway git repository under the OS temp area, copies this skill and
the project agents into it, and never touches real product code or staging.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import orchestrator_lib as lib  # noqa: E402

SKILL_SRC = lib.SKILL_DIR
CFG = lib.load_config()
OC = CFG["sessions"]["binary"]


def sh(args, cwd=None, check=True):
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError("command failed: %s\n%s%s" % (args, proc.stdout, proc.stderr))
    return proc


def script(name):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


def state_script():
    return script("orchestrator_state.py")


def call(name, *args, repo, expect=None):
    proc = subprocess.run([sys.executable, script(name), "--repo", repo, *args],
                          capture_output=True, text=True)
    payload = None
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
        except ValueError:
            payload = None
    if expect is not None and proc.returncode != expect:
        raise RuntimeError("%s %s rc=%s\n%s%s" % (name, args, proc.returncode, proc.stdout, proc.stderr))
    return proc.returncode, payload, proc.stderr


class DisposableRepo:
    def __init__(self, real_repo):
        # Create under the pre-approved OpenCode temp dir so worktrees and run
        # state stay on a path the project agents' external_directory rules cover.
        base = os.path.join(tempfile.gettempdir(), "opencode")
        os.makedirs(base, exist_ok=True)
        self.root = tempfile.mkdtemp(prefix="an3-orch-stress-", dir=base)
        sh(["git", "init", "-q"], cwd=self.root)
        sh(["git", "config", "user.email", "stress@example.invalid"], cwd=self.root)
        sh(["git", "config", "user.name", "stress"], cwd=self.root)
        # copy project agents + the orchestrator skill so sessions discover them
        shutil.copytree(os.path.join(real_repo, ".opencode"), os.path.join(self.root, ".opencode"),
                        ignore=shutil.ignore_patterns("node_modules", "__pycache__", "*.pyc"))
        shutil.copy2(os.path.join(real_repo, "opencode.json"), os.path.join(self.root, "opencode.json"))
        with open(os.path.join(self.root, "README.md"), "w") as handle:
            handle.write("disposable stress repo\n")
        os.makedirs(os.path.join(self.root, "parts"), exist_ok=True)
        with open(os.path.join(self.root, "parts", "base.txt"), "w") as handle:
            handle.write("base\n")
        sh(["git", "add", "-A"], cwd=self.root)
        sh(["git", "commit", "-q", "-m", "stress base"], cwd=self.root)
        sh(["git", "branch", "-M", "main"], cwd=self.root)
        self.base = self.head()

    def head(self):
        return sh(["git", "rev-parse", "HEAD"], cwd=self.root).stdout.strip()

    def commit(self, message):
        sh(["git", "add", "-A"], cwd=self.root)
        sh(["git", "commit", "-q", "-m", message], cwd=self.root)
        return self.head()

    def cleanup(self, keep):
        if not keep:
            shutil.rmtree(self.root, ignore_errors=True)


WORKER_PROMPT = """You are a disposable AN3 orchestration stress-test worker.

Worktree: {wt}
Do EXACTLY this and nothing else (no refactors, no other files, no push, no deploy):

{steps}

End with exactly:

WORKER_STATUS_BEGIN
{{"runId": "{run}", "domain": "{domain}", "status": "READY_FOR_REVIEW", "branch": "{branch}",
 "head": "<sha>", "commits": ["<sha> <subject>"], "dependsOn": [], "sharedInterfacesChanged": [],
 "sharedFilesChanged": [], "testsPassed": [], "testsFailed": [], "unverified": [],
 "knownIssues": [], "integrationNotes": []}}
WORKER_STATUS_END
"""


def launch(repo, run_id, domain, worktree, branch, prompt, wait=40):
    sessions_dir = os.path.join(lib.run_dir(repo, run_id), "sessions")
    os.makedirs(sessions_dir, exist_ok=True)
    log_path = os.path.join(sessions_dir, "%s.ndjson" % domain)
    err_path = os.path.join(sessions_dir, "%s.err" % domain)
    cmd = [OC, "run", "--format", "json", "--agent", "an3-worker",
           "--model", lib.CANONICAL_MODEL, "--dir", worktree,
           "--title", "%s-%s" % (run_id, domain), prompt]
    log_handle = open(log_path, "w", encoding="utf-8")
    err_handle = open(err_path, "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=log_handle, stderr=err_handle, start_new_session=True)
    session_id = None
    deadline = time.time() + wait
    while time.time() < deadline:
        for event in lib.read_ndjson_events(log_path, limit=5):
            if event.get("sessionID"):
                session_id = event["sessionID"]
                break
        if session_id or proc.poll() is not None:
            break
        time.sleep(0.5)
    call("orchestrator_state.py", "add-session", "--run-id", run_id, "--domain", domain,
         "--session-id", session_id or "UNKNOWN", "--worktree", worktree, "--branch", branch,
         "--pid", str(proc.pid), repo=repo)
    return {"domain": domain, "proc": proc, "log": log_path, "err": err_path, "sessionId": session_id}


def wait_all(workers, timeout):
    deadline = time.time() + timeout
    for worker in workers:
        while time.time() < deadline and worker["proc"].poll() is None:
            time.sleep(2)
        worker["exited"] = worker["proc"].poll() is not None
        worker["rc"] = worker["proc"].returncode
    return workers


def worker_status(log_path):
    text = ""
    for event in lib.read_ndjson_events(log_path):
        part = event.get("part", {})
        if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
            text += part["text"] + "\n"
    start = text.find("WORKER_STATUS_BEGIN")
    end = text.find("WORKER_STATUS_END")
    if start < 0 or end < 0:
        return None
    blob = text[start + len("WORKER_STATUS_BEGIN"):end]
    try:
        return json.loads(blob[blob.find("{"):blob.rfind("}") + 1])
    except ValueError:
        return None


def subagent_count(log_path):
    count = 0
    for event in lib.read_ndjson_events(log_path):
        part = event.get("part", {})
        tool = (part or {}).get("tool") if isinstance(part, dict) else None
        if tool == "task":
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="AN3 orchestration stress test")
    parser.add_argument("--repo", default=None, help="real repo to copy agents from")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    real_repo = lib.find_repo_root(args.repo)
    report = {"ok": False, "steps": [], "workers": {}, "provenance": {}, "metrics": {}}
    repo = DisposableRepo(real_repo)
    run_id = time.strftime("%Y%m%d-%H%M")
    try:
        call("orchestrator_state.py", "init", "--run-id", run_id, "--base-sha", repo.base,
             "--target-branch", "main", repo=repo.root, expect=0)
        call("orchestrator_state.py", "check-model", "--run-id", run_id, repo=repo.root, expect=0)
        report["steps"].append("init+check-model")

        # tasks + DAG: C depends on A (dependent node must wait)
        for task in (
            {"id": "A", "class": "S", "owner": "alpha", "modules": ["parts/a.txt"], "dependsOn": []},
            {"id": "B", "class": "S", "owner": "beta", "modules": ["parts/b.txt"], "dependsOn": []},
            {"id": "C", "class": "S", "owner": "gamma", "modules": ["parts/shared.txt"], "dependsOn": ["A"]},
            {"id": "I", "class": "I", "owner": "integration", "dependsOn": ["A", "B", "C"]},
        ):
            call("orchestrator_state.py", "add-task", "--run-id", run_id, "--json", json.dumps(task),
                 repo=repo.root, expect=0)
        rc, overlap, _ = call("scheduler.py", "overlap", "--tasks", json.dumps([
            {"id": "A", "class": "S", "modules": ["parts/a.txt", "parts/shared.txt"], "dependsOn": []},
            {"id": "B", "class": "S", "modules": ["parts/b.txt"], "dependsOn": []},
            {"id": "C", "class": "S", "modules": ["parts/shared.txt"], "dependsOn": ["A"]},
        ]), repo=repo.root, expect=0)
        report["dagFirstWave"] = overlap["ready"]  # dependency-free frontier
        report["overlapRecommendations"] = [{"a": p["a"], "b": p["b"],
                                             "recommendation": p["recommendation"]} for p in overlap["pairs"]]

        # shared resource lease
        call("resource_lock.py", "acquire", "stress:device", "orchestrator", "stress",
             "--run-id", run_id, repo=repo.root, expect=0)
        report["steps"].append("resource-leased")

        # worktrees
        for domain in ("alpha", "beta", "gamma"):
            call("worktree.py", "create", "--run-id", run_id, "--domain", domain,
                 "--base-sha", repo.base, repo=repo.root, expect=0)
        call("worktree.py", "create-integration", "--run-id", run_id, "--base-sha", repo.base,
             repo=repo.root, expect=0)
        report["steps"].append("worktrees")

        def wt(domain):
            return os.path.join(os.path.dirname(repo.root), "an3-wt-%s-%s" % (run_id, domain))

        def branch(domain):
            return "agent/%s/%s" % (run_id, domain)

        # Wave 1: the dependency-free frontier (A and B) runs concurrently; A also
        # spawns a read-only subagent.
        a_prompt = WORKER_PROMPT.format(
            wt=wt("alpha"), run=run_id, domain="alpha", branch=branch("alpha"),
            steps="1. Use the task tool to launch the `an3-code-explorer` subagent once to report how "
                  "many files are under `parts/` (read-only).\n"
                  "2. Create `parts/a.txt` containing exactly `A`.\n"
                  "3. Create `parts/shared.txt` containing exactly `A`.\n"
                  "4. Run: git add parts/a.txt parts/shared.txt && git commit -m 'stress alpha'")
        b_prompt = WORKER_PROMPT.format(
            wt=wt("beta"), run=run_id, domain="beta", branch=branch("beta"),
            steps="1. Use the task tool to launch the `an3-code-explorer` subagent once to report the "
                  "repository root (read-only).\n"
                  "2. Create `parts/b.txt` containing exactly `B`.\n"
                  "3. Run: git add parts/b.txt && git commit -m 'stress beta'")
        a = launch(repo.root, run_id, "alpha", wt("alpha"), branch("alpha"), a_prompt)
        b = launch(repo.root, run_id, "beta", wt("beta"), branch("beta"), b_prompt)
        wait_all([a, b], args.timeout)
        report["executedWaves"] = {"wave1": ["alpha", "beta"], "wave2": ["gamma"]}
        for worker in (a, b):
            status = worker_status(worker["log"])
            report["workers"][worker["domain"]] = {"rc": worker["rc"],
                                                   "sessionId": worker["sessionId"],
                                                   "status": status,
                                                   "subagents": subagent_count(worker["log"]),
                                                   "commit": _head(wt(worker["domain"]))}

        # Wave 2: C runs only after its dependency A completed.
        c_prompt = WORKER_PROMPT.format(
            wt=wt("gamma"), run=run_id, domain="gamma", branch=branch("gamma"),
            steps="1. Create `parts/shared.txt` containing exactly `C`.\n"
                  "2. Run: git add parts/shared.txt && git commit -m 'stress gamma'")
        c = launch(repo.root, run_id, "gamma", wt("gamma"), branch("gamma"), c_prompt)
        wait_all([c], args.timeout)
        report["workers"]["gamma"] = {"rc": c["rc"], "sessionId": c["sessionId"],
                                      "status": worker_status(c["log"]),
                                      "subagents": subagent_count(c["log"]),
                                      "commit": _head(wt("gamma"))}
        report["steps"].append("waves")

        # QA: deterministic scan from the integration worktree
        int_wt = wt("integration")
        scan_rc, scan, _ = call("validate_candidate.py", "scan", "--fast", "--base", repo.base,
                                repo=int_wt)
        report["qa"] = {"rc": scan_rc, "status": scan and scan.get("status"),
                        "newWarnings": scan and scan.get("newWarnings")}
        report["steps"].append("qa")

        # Integration: exact cherry-pick of beta, then conflict-resolved gamma adapter.
        alpha_head = report["workers"]["alpha"]["commit"]
        beta_head = report["workers"]["beta"]["commit"]
        gamma_head = report["workers"]["gamma"]["commit"]
        prov = {}
        if beta_head:
            sh(["git", "-C", int_wt, "cherry-pick", "-x", beta_head])
            integrated_beta = sh(["git", "-C", int_wt, "rev-parse", "HEAD"]).stdout.strip()
            call("orchestrator_state.py", "set-candidate", "--run-id", run_id, "--domain", "beta",
                 "--worker-commit", beta_head, "--stage", "INTEGRATED", repo=repo.root, expect=0)
            _, out, _ = call("orchestrator_state.py", "record-provenance", "--run-id", run_id,
                             "--domain", "beta", "--worker-commit", beta_head,
                             "--integrated-commit", integrated_beta, "--method", "cherry-pick",
                             repo=repo.root, expect=0)
            prov["beta"] = out["provenance"]
        if alpha_head:
            sh(["git", "-C", int_wt, "cherry-pick", "-x", alpha_head])
            integrated_alpha = sh(["git", "-C", int_wt, "rev-parse", "HEAD"]).stdout.strip()
            call("orchestrator_state.py", "set-candidate", "--run-id", run_id, "--domain", "alpha",
                 "--worker-commit", alpha_head, "--stage", "INTEGRATED", repo=repo.root, expect=0)
            _, out, _ = call("orchestrator_state.py", "record-provenance", "--run-id", run_id,
                             "--domain", "alpha", "--worker-commit", alpha_head,
                             "--integrated-commit", integrated_alpha, "--method", "cherry-pick",
                             repo=repo.root, expect=0)
            prov["alpha"] = out["provenance"]
        # deliberate conflict: gamma rewrites the same shared.txt that alpha added
        if gamma_head:
            sh(["git", "-C", int_wt, "cherry-pick", "-x", gamma_head], check=False)
            conflict = sh(["git", "-C", int_wt, "status", "--porcelain"]).stdout
            if "UU parts/shared.txt" in conflict or "AA parts/shared.txt" in conflict:
                with open(os.path.join(int_wt, "parts", "shared.txt"), "w") as handle:
                    handle.write("A\nC\n")
                sh(["git", "-C", int_wt, "add", "parts/shared.txt"])
                env = dict(os.environ, GIT_EDITOR="true")
                subprocess.run(["git", "-C", int_wt, "cherry-pick", "--continue"],
                               env=env, capture_output=True, text=True)
                adapter = sh(["git", "-C", int_wt, "rev-parse", "HEAD"]).stdout.strip()
                call("orchestrator_state.py", "set-candidate", "--run-id", run_id, "--domain", "gamma",
                     "--worker-commit", gamma_head, "--stage", "REVIEWED", repo=repo.root, expect=0)
                _, out, _ = call("orchestrator_state.py", "record-provenance", "--run-id", run_id,
                                 "--domain", "gamma", "--worker-commit", gamma_head,
                                 "--integrated-commit", adapter, "--method", "adapted",
                                 "--adapter-commit", adapter, repo=repo.root, expect=0)
                prov["gamma"] = out["provenance"]
            else:
                report["integrationConflict"] = "NOT_TRIGGERED"
        report["provenance"] = prov
        report["steps"].append("integration")

        # metrics + provenance verification
        _, metrics, _ = call("orchestrator_state.py", "metrics", "--run-id", run_id, repo=repo.root)
        report["metrics"] = metrics["metrics"]
        prov_rc, prov_check, _ = call("orchestrator_state.py", "check-provenance",
                                      "--run-id", run_id, repo=repo.root)
        report["provenanceCheck"] = {"rc": prov_rc, "ok": prov_check["ok"]}
        report["steps"].append("metrics+provenance")

        ok = (all(w.get("commit") for w in report["workers"].values())
              and prov.get("beta", {}).get("contentEquivalent") is True
              and prov.get("gamma", {}).get("contentEquivalent") is False
              and prov.get("gamma", {}).get("adapterCommit"))
        report["ok"] = bool(ok)
    finally:
        # manifest metrics snapshot + cleanup worktrees, keep the run state
        try:
            call("cleanup_run.py", "--run-id", run_id, "--apply", "--allow-unmerged", repo=repo.root)
        except Exception:
            pass
        for domain in ("alpha", "beta", "gamma", "integration"):
            path = os.path.join(os.path.dirname(repo.root), "an3-wt-%s-%s" % (run_id, domain))
            if os.path.isdir(path):
                subprocess.run([sys.executable, script("worktree.py"), "--repo", repo.root,
                                "remove", "--run-id", run_id, "--domain", domain,
                                "--allow-unmerged"], capture_output=True, text=True)
        report["stressRepo"] = repo.root
        repo.cleanup(args.keep)
        print(json.dumps(report, indent=2, sort_keys=True))
        sys.exit(0 if report["ok"] else 1)


def _head(worktree):
    if not os.path.isdir(worktree):
        return None
    proc = subprocess.run(["git", "-C", worktree, "rev-parse", "HEAD"], capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else None


if __name__ == "__main__":
    main()
