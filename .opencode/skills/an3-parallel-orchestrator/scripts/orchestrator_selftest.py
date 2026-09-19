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

    def _git(self, *args):
        return subprocess.run(["git", "-C", self.path, *args], capture_output=True, text=True)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
