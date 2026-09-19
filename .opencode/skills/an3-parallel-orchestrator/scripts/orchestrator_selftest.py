#!/usr/bin/env python3
"""Deterministic self-tests for the AN3 parallel-orchestrator.

Runs the scripts against disposable temporary Git repositories and planted
fixtures. Covers: worktree isolation, resource leases (deny/release/stale),
logical-conflict fixtures (duplicate RG ids, bad manifest hash, duplicate Tauri
commands, version inconsistency), run-state atomicity + recovery, and the static
agent permission/model policy.

Usage: python3 orchestrator_selftest.py [-v]
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SKILL_DIR)))
sys.path.insert(0, HERE)

import orchestrator_lib as lib  # noqa: E402

STATE = os.path.join("orchestrator_state.py")
WORKTREE = os.path.join("worktree.py")
LOCK = os.path.join("resource_lock.py")
VALIDATE = os.path.join("validate_candidate.py")
CLEANUP = os.path.join("cleanup_run.py")


def script(name):
    return os.path.join(HERE, name)


def run(name, *args, repo=None, expect=None):
    cmd = [sys.executable, script(name)]
    if repo is not None:
        cmd += ["--repo", repo]
    cmd += list(args)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    payload = None
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
        except ValueError:
            payload = None
    if expect is not None and proc.returncode != expect:
        raise AssertionError(
            "%s %s expected rc=%s got rc=%s\nstdout=%s\nstderr=%s"
            % (name, args, expect, proc.returncode, proc.stdout, proc.stderr)
        )
    return proc.returncode, payload, proc.stderr


class TmpRepo:
    def __init__(self):
        self.path = tempfile.mkdtemp(prefix="an3-orch-selftest-")
        self._git("init", "-q")
        self._git("config", "user.email", "selftest@example.invalid")
        self._git("config", "user.name", "selftest")
        self.write("README.md", "fixture\n")
        self.commit("init")
        self._git("branch", "-M", "main")

    def _git(self, *args):
        return subprocess.run(["git", "-C", self.path, *args], capture_output=True, text=True)

    def head(self):
        return self._git("rev-parse", "HEAD").stdout.strip()

    def write(self, rel, content):
        path = os.path.join(self.path, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)

    def commit(self, message):
        self._git("add", "-A")
        result = self._git("commit", "-q", "-m", message)
        if result.returncode != 0 and "nothing to commit" not in result.stdout + result.stderr:
            raise AssertionError("commit failed: %s %s" % (result.stdout, result.stderr))
        return self._git("rev-parse", "HEAD").stdout.strip()

    def cleanup(self):
        shutil.rmtree(self.path, ignore_errors=True)


class WorktreeTests(unittest.TestCase):
    def test_worktree_isolation_and_cleanup(self):
        tmp = TmpRepo()
        try:
            base = tmp._git("rev-parse", "HEAD").stdout.strip()
            run(STATE, "init", "--run-id", "20260101-0000", "--base-sha", base, repo=tmp.path, expect=0)
            wt_a = os.path.join(tmp.path, "wt-agent-a")
            wt_b = os.path.join(tmp.path, "wt-agent-b")
            rc, out, _ = run(WORKTREE, "create", "--run-id", "20260101-0000", "--domain", "alpha",
                             "--base-sha", base, "--path", wt_a, repo=tmp.path, expect=0)
            self.assertTrue(out["ok"])
            self.assertEqual(out["state"], "CREATED")
            rc, out, _ = run(WORKTREE, "create", "--run-id", "20260101-0000", "--domain", "beta",
                             "--base-sha", base, "--path", wt_b, repo=tmp.path, expect=0)
            self.assertTrue(os.path.isdir(os.path.join(wt_a, ".git")) or os.path.isfile(os.path.join(wt_a, ".git")))
            # writers have distinct branches
            br_a = tmp._git("-C", wt_a, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
            br_b = tmp._git("-C", wt_b, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
            self.assertNotEqual(br_a, br_b)
            # idempotent re-create
            rc, out, _ = run(WORKTREE, "create", "--run-id", "20260101-0000", "--domain", "alpha",
                             "--base-sha", base, "--path", wt_a, repo=tmp.path, expect=0)
            self.assertEqual(out["state"], "EXISTING")
            # a dirty worktree cannot be removed without override
            open(os.path.join(wt_a, "dirty.txt"), "w").close()
            rc, out, _ = run(WORKTREE, "remove", "--run-id", "20260101-0000", "--domain", "alpha",
                             repo=tmp.path, expect=3)
            self.assertFalse(out["ok"])
            rc, out, _ = run(WORKTREE, "remove", "--run-id", "20260101-0000", "--domain", "beta",
                             "--allow-unmerged", repo=tmp.path, expect=0)
            self.assertTrue(out["ok"])
            self.assertFalse(os.path.isdir(wt_b))
        finally:
            tmp.cleanup()

    def test_validate_rejects_foreign_branch(self):
        tmp = TmpRepo()
        try:
            wt = os.path.join(tmp.path, "wt-foreign")
            subprocess.run(["git", "-C", tmp.path, "worktree", "add", "-b", "random-branch", wt],
                           capture_output=True, text=True)
            rc, out, _ = run(WORKTREE, "validate", "--path", wt, repo=tmp.path, expect=1)
            self.assertFalse(out["ok"])
        finally:
            tmp.cleanup()


class ResourceLockTests(unittest.TestCase):
    def test_deny_release_reacquire(self):
        tmp = TmpRepo()
        try:
            rc, out, _ = run(LOCK, "acquire", "staging:8092", "session-a", "test", "--run-id", "r1",
                             repo=tmp.path, expect=0)
            self.assertTrue(out["acquired"])
            rc, out, _ = run(LOCK, "acquire", "staging:8092", "session-b", "test", "--run-id", "r1",
                             repo=tmp.path, expect=2)
            self.assertFalse(out["acquired"])
            rc, out, _ = run(LOCK, "release", "staging:8092", "session-b", repo=tmp.path, expect=3)
            rc, out, _ = run(LOCK, "release", "staging:8092", "session-a", repo=tmp.path, expect=0)
            self.assertTrue(out["released"])
            rc, out, _ = run(LOCK, "acquire", "staging:8092", "session-b", "test", "--run-id", "r1",
                             repo=tmp.path, expect=0)
            self.assertTrue(out["acquired"])
        finally:
            tmp.cleanup()

    def test_stale_detection_and_break(self):
        tmp = TmpRepo()
        try:
            state = lib.state_root(tmp.path)
            lock_path = os.path.join(state, "locks", "android-avd_codex-nds-api35.lock")
            os.makedirs(lock_path, exist_ok=True)
            lib.atomic_write_json(os.path.join(lock_path, "lease.json"), {
                "resource": "android-avd:codex-nds-api35",
                "ownerSession": "dead-session",
                "pid": 999999,
                "acquiredAt": "2000-01-01T00:00:00Z",
                "leaseUntil": 1,
                "purpose": "fixture",
            })
            rc, out, _ = run(LOCK, "status", "android-avd:codex-nds-api35", repo=tmp.path, expect=0)
            self.assertEqual(out["leases"][0]["state"], "STALE")
            rc, out, _ = run(LOCK, "acquire", "android-avd:codex-nds-api35", "new", "test",
                             repo=tmp.path, expect=2)
            self.assertFalse(out["acquired"])
            rc, out, _ = run(LOCK, "acquire", "android-avd:codex-nds-api35", "new", "test",
                             "--break-stale", repo=tmp.path, expect=0)
            self.assertTrue(out["acquired"])
        finally:
            tmp.cleanup()


    def test_integration_worktree_uses_integration_branch(self):
        tmp = TmpRepo()
        try:
            base = tmp._git("rev-parse", "HEAD").stdout.strip()
            run(STATE, "init", "--run-id", "20260101-0001", "--base-sha", base, repo=tmp.path, expect=0)
            rc, out, _ = run(WORKTREE, "create-integration", "--run-id", "20260101-0001",
                             "--base-sha", base, repo=tmp.path, expect=0)
            self.assertEqual(out["branch"], "integration/20260101-0001")
            # the recorded integration branch is the one removed, not an agent/ branch
            rc, out, _ = run(WORKTREE, "remove", "--run-id", "20260101-0001", "--domain", "integration",
                             repo=tmp.path, expect=0)
            self.assertEqual(out["branch"], "integration/20260101-0001")
            self.assertFalse(tmp._git("rev-parse", "--verify", "refs/heads/integration/20260101-0001").returncode == 0)
        finally:
            tmp.cleanup()


class ConflictFixtureTests(unittest.TestCase):
    def test_duplicate_regression_guard_ids(self):
        tmp = TmpRepo()
        try:
            tmp.write("docs/REGRESSION_GUARDS.md", "- RG-001: base one\n- RG-001: base dup\n")
            base = tmp.commit("guards base")
            tmp.write("docs/REGRESSION_GUARDS.md",
                      "- RG-001: base one\n- RG-001: base dup\n- RG-900: new\n- RG-900: new dup\n")
            rc, out, _ = run(VALIDATE, "duplicate-rg", "--base", base, repo=tmp.path, expect=1)
            self.assertEqual(out["status"], "FAIL")
            self.assertEqual(out["newDuplicates"], ["RG-900"])
            # pre-existing duplicates alone are not the candidate's fault
            tmp.write("docs/REGRESSION_GUARDS.md", "- RG-001: a\n- RG-001: b\n")
            rc, out, _ = run(VALIDATE, "duplicate-rg", "--base", base, repo=tmp.path, expect=0)
            self.assertEqual(out["status"], "PASS")
        finally:
            tmp.cleanup()

    def test_manifest_hash_mismatch(self):
        tmp = TmpRepo()
        try:
            artifact = os.path.join("native-offline", "releases", "an3-offline-1.0.0-test.deb")
            tmp.write(artifact, "payload")
            good = hashlib.sha256(b"payload").hexdigest()
            catalog_path = os.path.join("native-offline", "releases", "catalog.json")
            tmp.write(catalog_path, json.dumps({"artifacts": [
                {"version": "1.0.0", "filename": "an3-offline-1.0.0-test.deb",
                 "size": 7, "sha256": good}]}))
            rc, out, _ = run(VALIDATE, "manifest-hash", repo=tmp.path, expect=0)
            self.assertEqual(out["status"], "PASS")
            tmp.write(catalog_path, json.dumps({"artifacts": [
                {"version": "1.0.0", "filename": "an3-offline-1.0.0-test.deb",
                 "size": 7, "sha256": "0" * 64}]}))
            rc, out, _ = run(VALIDATE, "manifest-hash", repo=tmp.path, expect=1)
            self.assertEqual(out["status"], "FAIL")
        finally:
            tmp.cleanup()

    def test_duplicate_tauri_commands(self):
        tmp = TmpRepo()
        try:
            tmp.write("native-offline/src-tauri/src/lib.rs", (
                "#[tauri::command]\nfn alpha() {}\n\n#[tauri::command]\nfn beta() {}\n\n"
                ".invoke_handler(tauri::generate_handler![alpha, alpha])\n"))
            tmp.write("native-offline/src-tauri/build.rs",
                      "AppManifest::new().commands(&[\"alpha\"])\n")
            rc, out, _ = run(VALIDATE, "tauri-commands", repo=tmp.path, expect=1)
            self.assertEqual(out["status"], "FAIL")
            joined = " ".join(out["findings"])
            self.assertIn("duplicate generate_handler", joined)
            self.assertIn("beta", joined)
        finally:
            tmp.cleanup()

    def test_version_inconsistency(self):
        tmp = TmpRepo()
        try:
            tmp.write("native-offline/package.json", json.dumps({"version": "3.0.0"}))
            tmp.write("native-offline/src-tauri/tauri.conf.json", json.dumps({"version": "2.0.0"}))
            tmp.write("native-offline/src-tauri/Cargo.toml", 'version = "3.0.0"\n')
            tmp.write("native-offline/releases/catalog.json", json.dumps({"artifacts": [
                {"version": "9.9.9", "filename": "an3-offline-1.0.0.deb"}]}))
            rc, out, _ = run(VALIDATE, "versions", repo=tmp.path, expect=1)
            self.assertEqual(out["status"], "FAIL")
            self.assertTrue(any("disagree" in f for f in out["findings"]))
            self.assertTrue(any("9.9.9" in f for f in out["findings"]))
        finally:
            tmp.cleanup()

    def test_stale_release_filenames_relative_to_base(self):
        tmp = TmpRepo()
        try:
            tmp.write("tools/build-thing.sh", "artifact=vibecodedemulator-1.0.0-macos.dmg\n")
            base = tmp.commit("script base")
            rc, out, _ = run(VALIDATE, "stale-release-filenames", "--base", base, repo=tmp.path, expect=0)
            self.assertEqual(out["status"], "PASS")
            tmp.write("tools/build-thing.sh", "artifact=vibecodedemulator-2.0.0-macos.dmg\n")
            rc, out, _ = run(VALIDATE, "stale-release-filenames", "--base", base, repo=tmp.path, expect=1)
            self.assertEqual(out["status"], "FAIL")
        finally:
            tmp.cleanup()


class StateAndRecoveryTests(unittest.TestCase):
    def test_run_lifecycle_and_recovery(self):
        tmp = TmpRepo()
        try:
            base = tmp._git("rev-parse", "HEAD").stdout.strip()
            tmp.write(".opencode/agent/an3-worker.md",
                      '---\nname: an3-worker\nmode: primary\nmodel: %s\n---\nbody\n' % lib.CANONICAL_MODEL)
            rc, out, _ = run(STATE, "init", "--run-id", "20260101-0100", "--base-sha", base,
                             "--goal", "goal one", "--target-branch", "main", repo=tmp.path, expect=0)
            self.assertTrue(out["ok"])
            run(STATE, "add-task", "--run-id", "20260101-0100",
                "--json", json.dumps({"id": "alpha", "class": "S", "dependsOn": []}),
                repo=tmp.path, expect=0)
            run(STATE, "add-task", "--run-id", "20260101-0100",
                "--json", json.dumps({"id": "beta", "class": "A", "dependsOn": ["alpha"]}),
                repo=tmp.path, expect=0)
            run(STATE, "add-session", "--run-id", "20260101-0100", "--domain", "alpha",
                "--session-id", "ses_x", "--worktree", "/tmp/wt", "--branch", "agent/20260101-0100/alpha",
                "--pid", "1", repo=tmp.path, expect=0)
            run(STATE, "set-candidate", "--run-id", "20260101-0100", "--domain", "alpha",
                "--commit", base, repo=tmp.path, expect=0)
            run(STATE, "set-status", "--run-id", "20260101-0100", "--dimension", "IMPLEMENTATION",
                "--value", "COMPLETE", repo=tmp.path, expect=0)
            rc, out, _ = run(STATE, "validate", "--run-id", "20260101-0100", repo=tmp.path, expect=0)
            self.assertTrue(out["ok"])
            rc, out, _ = run(STATE, "check-model", "--run-id", "20260101-0100", repo=tmp.path, expect=0)
            self.assertEqual(out["status"], "OK")
            # recovery: state is readable after an "interruption" (fresh process)
            rc, out, _ = run("inspect_run.py", "--run-id", "20260101-0100", repo=tmp.path, expect=0)
            self.assertEqual(out["runId"], "20260101-0100")
            self.assertEqual(len(out["tasks"]), 2)
            self.assertEqual(out["statuses"]["IMPLEMENTATION"], "COMPLETE")
        finally:
            tmp.cleanup()

    def test_cleanup_dry_run_keeps_worktrees(self):
        tmp = TmpRepo()
        try:
            base = tmp._git("rev-parse", "HEAD").stdout.strip()
            wt = os.path.join(tmp.path, "wt-alpha")
            run(STATE, "init", "--run-id", "20260101-0200", "--base-sha", base,
                repo=tmp.path, expect=0)
            run(WORKTREE, "create", "--run-id", "20260101-0200", "--domain", "alpha",
                "--base-sha", base, "--path", wt, repo=tmp.path, expect=0)
            rc, out, _ = run(CLEANUP, "--run-id", "20260101-0200", repo=tmp.path, expect=0)
            self.assertFalse(out["applied"])
            self.assertTrue(os.path.isdir(wt))
            rc, out, _ = run(CLEANUP, "--run-id", "20260101-0200", "--apply",
                             "--allow-unmerged", "--delete-branches", repo=tmp.path, expect=0)
            self.assertTrue(out["applied"])
            self.assertFalse(os.path.isdir(wt))
        finally:
            tmp.cleanup()


class AgentPolicyTests(unittest.TestCase):
    def _agent_dir(self):
        for rel in (".opencode/agent", ".opencode/agents"):
            path = os.path.join(REPO_ROOT, rel)
            if os.path.isdir(path):
                return path
        self.skipTest("no project agent directory")

    def test_every_agent_pins_the_model(self):
        agent_dir = self._agent_dir()
        agents = [n for n in os.listdir(agent_dir) if n.startswith("an3-") and n.endswith(".md")]
        self.assertTrue(agents, "expected an3-* agents")
        for name in agents:
            fm = lib.parse_frontmatter(os.path.join(agent_dir, name))
            self.assertEqual(fm.get("model"), lib.CANONICAL_MODEL, "%s must pin the model" % name)

    def test_read_only_agents_deny_edits(self):
        agent_dir = self._agent_dir()
        for name in ("an3-blind-reviewer.md", "an3-code-explorer.md",
                     "an3-test-analyzer.md", "an3-integration-reviewer.md"):
            path = os.path.join(agent_dir, name)
            if not os.path.exists(path):
                self.fail("missing read-only agent %s" % name)
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
            self.assertRegex(text, r"(?m)^\s*edit:\s*deny\s*$", "%s must deny edits" % name)

    def test_subagents_cannot_spawn_top_level_sessions(self):
        agent_dir = self._agent_dir()
        for name in ("an3-blind-reviewer.md", "an3-code-explorer.md",
                     "an3-test-analyzer.md", "an3-integration-reviewer.md"):
            path = os.path.join(agent_dir, name)
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
            # deny-by-default bash (covers `opencode run*`) and no task spawning
            self.assertIn('"*": deny', text, "%s must deny bash by default" % name)
            self.assertRegex(text, r"(?m)^\s*task:\s*deny\s*$", "%s must deny task spawning" % name)


class SessionGuardTests(unittest.TestCase):
    def test_rejects_noncanonical_model(self):
        tmp = TmpRepo()
        try:
            rc, out, _ = run("session.py", "start", "--run-id", "20260101-0300", "--domain", "alpha",
                             "--worktree", tmp.path, "--prompt-file", os.path.join(tmp.path, "p.md"),
                             "--model", "opencode-go/glm-5.3", repo=tmp.path, expect=64)
            self.assertFalse(out["ok"])
        finally:
            tmp.cleanup()

    def test_rejects_missing_worktree(self):
        tmp = TmpRepo()
        try:
            rc, out, _ = run("session.py", "start", "--run-id", "20260101-0300", "--domain", "alpha",
                             "--worktree", os.path.join(tmp.path, "does-not-exist"),
                             "--prompt-file", os.path.join(tmp.path, "p.md"), repo=tmp.path, expect=4)
            self.assertFalse(out["ok"])
        finally:
            tmp.cleanup()

    def test_rejects_subagent_as_top_level_session(self):
        # Installed OpenCode 1.18.31 does not enforce a subagent-mode agent's
        # permissions under `opencode run --agent`; read-only subagents must run
        # via the Task tool, so session.py must refuse them as top-level sessions.
        tmp = TmpRepo()
        try:
            rc, out, _ = run("session.py", "start", "--run-id", "20260101-0700", "--domain", "x",
                             "--worktree", tmp.path, "--prompt-file", os.path.join(tmp.path, "p.md"),
                             "--agent", "an3-code-explorer", repo=tmp.path, expect=64)
            self.assertFalse(out["ok"])
            self.assertIn("an3-worker", out["allowed"])
        finally:
            tmp.cleanup()


class ProvenanceTests(unittest.TestCase):
    def _init(self, tmp, base, run_id="20260201-0000"):
        run(STATE, "init", "--run-id", run_id, "--base-sha", base, "--target-branch", "main",
            repo=tmp.path, expect=0)
        return run_id

    def test_exact_cherry_pick_is_content_equivalent(self):
        tmp = TmpRepo()
        try:
            base = tmp.head()
            tmp.write("feature.txt", "worker\n")
            worker = tmp.commit("worker feature")
            tmp._git("checkout", "-q", "-b", "integration", base)
            tmp._git("cherry-pick", "-x", worker)
            integrated = tmp.head()
            self.assertNotEqual(worker, integrated)  # cherry-pick rewrote the SHA
            self._init(tmp, base)
            rc, out, _ = run(STATE, "record-provenance", "--run-id", "20260201-0000",
                             "--domain", "feat", "--worker-commit", worker,
                             "--integrated-commit", integrated, "--method", "cherry-pick",
                             repo=tmp.path, expect=0)
            prov = out["provenance"]
            self.assertTrue(prov["contentEquivalent"])
            self.assertEqual(prov["workerPatchId"], prov["integratedPatchId"])
            self.assertEqual(prov["changedFiles"], [])
        finally:
            tmp.cleanup()

    def test_adaptation_is_recorded_separately(self):
        tmp = TmpRepo()
        try:
            base = tmp.head()
            tmp.write("feature.txt", "worker\n")
            worker = tmp.commit("worker feature")
            tmp.write("feature.txt", "worker + integration glue\n")
            adapter = tmp.commit("integration adapter: register feature")
            self._init(tmp, base)
            rc, out, _ = run(STATE, "record-provenance", "--run-id", "20260201-0000",
                             "--domain", "feat", "--worker-commit", worker,
                             "--integrated-commit", adapter, "--method", "adapted",
                             "--adapter-commit", adapter, repo=tmp.path, expect=0)
            prov = out["provenance"]
            self.assertFalse(prov["contentEquivalent"])
            self.assertEqual(prov["adapterCommit"], adapter)
            self.assertIn("feature.txt", prov["changedFiles"])
        finally:
            tmp.cleanup()

    def test_undeclared_adaptation_warns_and_fails(self):
        tmp = TmpRepo()
        try:
            base = tmp.head()
            tmp.write("feature.txt", "worker\n")
            worker = tmp.commit("worker feature")
            tmp.write("feature.txt", "changed without an adapter\n")
            changed = tmp.commit("integration changed content")
            self._init(tmp, base)
            rc, out, _ = run(STATE, "record-provenance", "--run-id", "20260201-0000",
                             "--domain", "feat", "--worker-commit", worker,
                             "--integrated-commit", changed, "--method", "cherry-pick",
                             repo=tmp.path, expect=1)
            self.assertIn("warning", out)
            self.assertFalse(out["provenance"]["contentEquivalent"])
        finally:
            tmp.cleanup()

    def test_duplicate_integration_is_detected(self):
        tmp = TmpRepo()
        try:
            base = tmp.head()
            tmp.write("feature.txt", "worker\n")
            worker = tmp.commit("worker feature")
            self._init(tmp, base)
            rc, out, _ = run(STATE, "record-provenance", "--run-id", "20260201-0000",
                             "--domain", "feat", "--worker-commit", worker,
                             "--integrated-commit", worker, "--method", "already-integrated",
                             repo=tmp.path, expect=0)
            self.assertTrue(out["provenance"]["alreadyIntegrated"])
            rc, out, _ = run(STATE, "check-provenance", "--run-id", "20260201-0000",
                             repo=tmp.path, expect=0)
            self.assertTrue(out["ok"])
        finally:
            tmp.cleanup()


class RecoveryTests(unittest.TestCase):
    def test_interrupted_run_recover_and_target_movement(self):
        tmp = TmpRepo()
        try:
            base = tmp.head()
            run(STATE, "init", "--run-id", "20260201-0100", "--base-sha", base,
                "--target-branch", "main", repo=tmp.path, expect=0)
            # simulate a worker whose launcher died but whose session is resumable
            rdir = lib.run_dir(tmp.path, "20260201-0100")
            sessions = {
                "sync": {"domain": "sync", "sessionId": "ses_dead_launcher", "pid": 999999,
                         "worktree": os.path.join(tmp.path, "wt-sync"),
                         "branch": "agent/20260201-0100/sync"},
            }
            lib.atomic_write_json(os.path.join(rdir, "sessions.json"), sessions)
            log_dir = os.path.join(rdir, "sessions")
            os.makedirs(log_dir, exist_ok=True)
            with open(os.path.join(log_dir, "sync.ndjson"), "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"type": "step_start", "sessionID": "ses_dead_launcher"}) + "\n")
                handle.write(json.dumps({"type": "step_finish", "sessionID": "ses_dead_launcher"}) + "\n")
            # target branch moves after the run started
            tmp.write("moved.txt", "target moved\n")
            tmp.commit("target movement")
            rc, out, _ = run("inspect_run.py", "recover",
                             "--run-id", "20260201-0100", repo=tmp.path, expect=0)
            self.assertEqual(out["state"], "RECOVERABLE")
            joined = " ".join(out["nextActions"])
            self.assertIn("resume worker sync", joined)
            self.assertTrue(out["view"]["targetMoved"])
            rc, out, _ = run(STATE, "check-target", "--run-id", "20260201-0100",
                             repo=tmp.path, expect=1)
            self.assertTrue(out["targetMoved"])
            self.assertFalse(out["promotionSafe"])
        finally:
            tmp.cleanup()

    def test_partial_state_is_still_readable(self):
        tmp = TmpRepo()
        try:
            base = tmp.head()
            run(STATE, "init", "--run-id", "20260201-0200", "--base-sha", base, repo=tmp.path, expect=0)
            rdir = lib.run_dir(tmp.path, "20260201-0200")
            # simulate an interruption mid-write: tasks.json missing
            os.unlink(os.path.join(rdir, "tasks.json"))
            rc, out, _ = run("inspect_run.py", "--run-id", "20260201-0200", repo=tmp.path, expect=0)
            self.assertEqual(out["tasks"], [])
            rc, out, _ = run("inspect_run.py", "recover",
                             "--run-id", "20260201-0200", repo=tmp.path, expect=0)
            self.assertIn(out["state"], ("RECOVERABLE", "STALLED"))
        finally:
            tmp.cleanup()

    def test_dirty_worktree_cleanup_is_refused(self):
        tmp = TmpRepo()
        try:
            base = tmp.head()
            run(STATE, "init", "--run-id", "20260201-0300", "--base-sha", base, repo=tmp.path, expect=0)
            wt = os.path.join(tmp.path, "wt-work")
            run(WORKTREE, "create", "--run-id", "20260201-0300", "--domain", "work",
                "--base-sha", base, "--path", wt, repo=tmp.path, expect=0)
            with open(os.path.join(wt, "dirty.txt"), "w") as handle:
                handle.write("uncommitted\n")
            rc, out, _ = run(WORKTREE, "remove", "--run-id", "20260201-0300", "--domain", "work",
                             repo=tmp.path, expect=3)
            self.assertFalse(out["ok"])
            self.assertTrue(os.path.isdir(wt))
        finally:
            tmp.cleanup()

    def test_integration_conflict_leaves_run_recoverable(self):
        tmp = TmpRepo()
        try:
            base = tmp.head()
            tmp.write("shared.txt", "base\n")
            base = tmp.commit("shared base")
            tmp._git("checkout", "-q", "-b", "feature-a", base)
            tmp.write("shared.txt", "A\n")
            tmp.commit("A changes shared")
            tmp._git("checkout", "-q", "-b", "feature-b", base)
            tmp.write("shared.txt", "B\n")
            tmp.commit("B changes shared")
            tmp._git("checkout", "-q", "main")
            tmp._git("merge", "--no-edit", "feature-a")
            merge = tmp._git("merge", "feature-b")
            self.assertNotEqual(merge.returncode, 0)  # real conflict
            status = tmp._git("status", "--porcelain").stdout
            self.assertIn("UU shared.txt", status)
            # recovery is explicit: abort restores a clean, readable state
            tmp._git("merge", "--abort")
            self.assertEqual(tmp._git("status", "--porcelain").stdout.strip(), "")
        finally:
            tmp.cleanup()


class SessionLifecycleTests(unittest.TestCase):
    def _session(self, **kw):
        base = {"sessionId": "ses_x", "pid": 999999}
        base.update(kw)
        return base

    def test_states_are_distinguished(self):
        tmp = tempfile.mkdtemp(prefix="an3-orch-log-")
        try:
            resumable = os.path.join(tmp, "resumable.ndjson")
            with open(resumable, "w") as handle:
                handle.write(json.dumps({"type": "step_finish"}) + "\n")
            unknown = os.path.join(tmp, "unknown.ndjson")
            with open(unknown, "w") as handle:
                handle.write(json.dumps({"type": "step_start"}) + "\n")
            self.assertEqual(lib.session_state(self._session(pid=os.getpid()), None), "PROCESS_RUNNING")
            self.assertEqual(lib.session_state(self._session(), resumable), "SESSION_RESUMABLE")
            self.assertEqual(lib.session_state(self._session(), unknown), "SESSION_UNKNOWN")
            self.assertEqual(lib.session_state(self._session(sessionId="UNKNOWN"), None), "SESSION_DEAD")
            self.assertEqual(lib.session_state(self._session(sessionId=None), None), "SESSION_DEAD")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_send_refuses_without_a_durable_session_id(self):
        rc, out, _ = run("session.py", "send", "--session-id", "UNKNOWN",
                         "--prompt-file", os.devnull, expect=4)
        self.assertFalse(out["deliveryConfirmed"])
        self.assertFalse(out["sent"])
        rc, out, _ = run("session.py", "send", "--session-id", "",
                         "--prompt-file", os.devnull, expect=4)


class ResourceContentionTests(unittest.TestCase):
    def test_concurrent_acquire_has_exactly_one_winner(self):
        tmp = TmpRepo()
        try:
            procs = []
            for n in range(6):
                cmd = [sys.executable, script("resource_lock.py"), "--repo", tmp.path,
                       "acquire", "shared:device", "owner-%d" % n, "race"]
                procs.append(subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                              stderr=subprocess.PIPE, text=True))
            codes = [p.wait() for p in procs]
            self.assertEqual(sorted(codes).count(0), 1, "exactly one acquisition must win")
            self.assertEqual(sorted(codes).count(2), 5, "the rest must be denied")
        finally:
            tmp.cleanup()

    def test_malformed_and_interrupted_locks_need_explicit_break(self):
        tmp = TmpRepo()
        try:
            state_root = lib.locks_dir(tmp.path)
            broken = os.path.join(state_root, "broken.lock")
            os.makedirs(broken)
            with open(os.path.join(broken, "lease.json"), "w") as handle:
                handle.write("{not json")
            rc, out, _ = run(LOCK, "status", "broken", repo=tmp.path, expect=0)
            self.assertEqual(out["leases"][0]["state"], "MALFORMED")
            rc, out, _ = run(LOCK, "acquire", "broken", "o", "p", repo=tmp.path, expect=2)
            self.assertEqual(out["state"], "MALFORMED")
            rc, out, _ = run(LOCK, "acquire", "broken", "o", "p", "--break-malformed",
                             repo=tmp.path, expect=0)
            self.assertTrue(out["acquired"])
            # interrupted write: lock dir exists but lease.json never landed
            empty = os.path.join(state_root, "crashed.lock")
            os.makedirs(empty)
            rc, out, _ = run(LOCK, "status", "crashed", repo=tmp.path, expect=0)
            self.assertEqual(out["leases"][0]["state"], "UNKNOWN")
            rc, out, _ = run(LOCK, "acquire", "crashed", "o", "p", repo=tmp.path, expect=2)
            rc, out, _ = run(LOCK, "acquire", "crashed", "o", "p", "--break-malformed",
                             repo=tmp.path, expect=0)
            self.assertTrue(out["acquired"])
        finally:
            tmp.cleanup()

    def test_stale_recovery_requires_expiry_and_dead_pid(self):
        tmp = TmpRepo()
        try:
            state_root = lib.locks_dir(tmp.path)
            stale = os.path.join(state_root, "stale.lock")
            os.makedirs(stale)
            lib.atomic_write_json(os.path.join(stale, "lease.json"), {
                "resource": "stale", "ownerSession": "dead", "pid": 999999,
                "leaseUntil": 1, "purpose": "fixture"})
            rc, out, _ = run(LOCK, "status", "stale", repo=tmp.path, expect=0)
            self.assertEqual(out["leases"][0]["state"], "STALE")
            # an unexpired lease with a dead pid is NOT stale and cannot be broken
            live = os.path.join(state_root, "unexpired.lock")
            os.makedirs(live)
            lib.atomic_write_json(os.path.join(live, "lease.json"), {
                "resource": "unexpired", "ownerSession": "dead", "pid": 999999,
                "leaseUntil": int(time.time()) + 3600, "purpose": "fixture"})
            rc, out, _ = run(LOCK, "acquire", "unexpired", "o", "p", "--break-stale",
                             repo=tmp.path, expect=2)
            self.assertFalse(out["acquired"])
            self.assertEqual(out["state"], "HELD_UNVERIFIED")
        finally:
            tmp.cleanup()


class AtomicRunStateTests(unittest.TestCase):
    def test_concurrent_session_writes_do_not_lose_updates(self):
        tmp = TmpRepo()
        try:
            base = tmp.head()
            run(STATE, "init", "--run-id", "20260201-0400", "--base-sha", base, repo=tmp.path, expect=0)
            procs = []
            for n in range(8):
                cmd = [sys.executable, script("orchestrator_state.py"), "--repo", tmp.path,
                       "add-session", "--run-id", "20260201-0400", "--domain", "d%d" % n,
                       "--session-id", "ses_%d" % n, "--worktree", "/tmp/wt%d" % n,
                       "--branch", "agent/x/d%d" % n]
                procs.append(subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                              stderr=subprocess.PIPE, text=True))
            for p in procs:
                self.assertEqual(p.wait(), 0)
            rdir = lib.run_dir(tmp.path, "20260201-0400")
            sessions = lib.read_json(os.path.join(rdir, "sessions.json"))
            self.assertEqual(len(sessions), 8, "every concurrent session write must survive")
            manifest = lib.read_json(os.path.join(rdir, "manifest.json"))
            self.assertEqual(len(manifest.get("sessions", {})), 8)
        finally:
            tmp.cleanup()


class OverlapSchedulingTests(unittest.TestCase):
    def test_central_contract_overlap_serializes(self):
        tasks = json.dumps([
            {"id": "A", "class": "S", "modules": ["native-offline/src-tauri/src/lib.rs"]},
            {"id": "B", "class": "S", "modules": ["native-offline/src-tauri/src/lib.rs"]},
            {"id": "C", "class": "S", "modules": ["docs/only.md"]},
        ])
        rc, out, _ = run("scheduler.py", "overlap", "--tasks", tasks, expect=0)
        pairs = {(p["a"], p["b"]): p["recommendation"] for p in out["pairs"]}
        self.assertEqual(pairs[("A", "B")], "SERIALIZE")
        self.assertEqual(pairs[("A", "C")], "PARALLEL_OK")

    def test_ready_frontier_respects_dependencies(self):
        tasks = json.dumps([
            {"id": "A", "class": "A", "modules": [], "dependsOn": []},
            {"id": "B", "class": "S", "modules": ["b/"], "dependsOn": ["A"]},
            {"id": "C", "class": "S", "modules": ["c/"], "dependsOn": ["B"]},
        ])
        rc, out, _ = run("scheduler.py", "overlap", "--tasks", tasks, "--done", "", expect=0)
        self.assertEqual(out["ready"], ["A"])
        rc, out, _ = run("scheduler.py", "overlap", "--tasks", tasks, "--done", "A", expect=0)
        self.assertEqual(out["ready"], ["B"])


class BacklogPressureTests(unittest.TestCase):
    def test_high_backlog_throttles_new_writers(self):
        tmp = TmpRepo()
        try:
            base = tmp.head()
            run(STATE, "init", "--run-id", "20260201-0500", "--base-sha", base, repo=tmp.path, expect=0)
            for n in range(4):
                run(STATE, "set-candidate", "--run-id", "20260201-0500", "--domain", "ready%d" % n,
                    "--stage", "READY_FOR_REVIEW", repo=tmp.path, expect=0)
            for n in range(4):
                run(STATE, "set-candidate", "--run-id", "20260201-0500", "--domain", "qa%d" % n,
                    "--stage", "IN_QA", repo=tmp.path, expect=0)
            for n in range(4):
                run(STATE, "set-candidate", "--run-id", "20260201-0500", "--domain", "rev%d" % n,
                    "--stage", "REVIEWED", repo=tmp.path, expect=0)
            rc, out, _ = run(STATE, "pressure", "--run-id", "20260201-0500", repo=tmp.path, expect=0)
            self.assertEqual(out["pressure"], "HIGH")
            self.assertFalse(out["allowNewWriters"])
            self.assertEqual(out["maxNewWriters"], 0)
        finally:
            tmp.cleanup()


class RepoDebtTests(unittest.TestCase):
    def test_worker_dispatch_with_another_model_fails_before_work(self):
        tmp = TmpRepo()
        try:
            rc, out, _ = run("session.py", "start", "--run-id", "20260201-0600", "--domain", "x",
                             "--worktree", tmp.path, "--prompt-file", os.path.join(tmp.path, "p.md"),
                             "--model", "opencode-go/glm-5.3", repo=tmp.path, expect=64)
            self.assertFalse(out["ok"])
        finally:
            tmp.cleanup()

    def test_known_regression_debt_checks_pass(self):
        rc, out, _ = run(VALIDATE, "duplicate-rg", repo=REPO_ROOT, expect=0)
        self.assertEqual(out["status"], "PASS")
        rc, out, _ = run(VALIDATE, "stale-release-filenames", repo=REPO_ROOT, expect=0)
        self.assertEqual(out["status"], "PASS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
