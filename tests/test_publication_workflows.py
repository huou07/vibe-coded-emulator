# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A published workflow may only run scripts the candidate actually contains.

The public snapshot once carried `native-build.yml`, whose jobs ran
`bash tools/release-train.sh` five times while the snapshot copied neither that
script nor a fixture directory and its `paths:` filters named a `tools/testrom/**`
directory that does not exist. Every published native job could only fail. These
tests pin the correction: the real candidate is built and checked, the checker is
proven to have teeth on a synthetic candidate, and the portable workflow's Node
commands still match suites that exist.
"""
from fnmatch import fnmatch
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / "tools/publication/.github/workflows"
CHECKER = ROOT / "tools/publication/check-workflow-scripts.py"
PUBLICATION_CHECK = ROOT / "tools/publication-check.sh"
PORTABLE_WORKFLOW = (WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8")


class PublishedWorkflowTests(unittest.TestCase):
    def test_no_published_workflow_runs_the_private_release_train(self):
        for workflow in sorted(WORKFLOW_DIR.glob("*.y*ml")):
            with self.subTest(workflow=workflow.name):
                self.assertNotIn(
                    "tools/release-train.sh",
                    workflow.read_text(encoding="utf-8"),
                    "the snapshot does not carry the private staging release train or its builders",
                )

    def test_real_candidate_references_only_scripts_it_contains(self):
        with tempfile.TemporaryDirectory(prefix="an3-published-workflows-") as temporary:
            candidate = Path(temporary) / "snapshot"
            built = subprocess.run(
                ["bash", str(ROOT / "tools/build-public-snapshot.sh"), "--output", str(candidate)],
                cwd=ROOT, capture_output=True, text=True, timeout=300,
            )
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            self.assertTrue((candidate / ".github/workflows").is_dir())
            published_ci = (candidate / ".github/workflows/ci.yml").read_text(encoding="utf-8")
            self.assertIn(
                "playwright-cli install-browser chrome-for-testing --with-deps",
                published_ci,
                "the web UI suite requires a browser installation on clean runners",
            )
            scanner_config = candidate / "tools/publication/.gitleaks.toml"
            self.assertEqual(
                scanner_config.read_text(encoding="utf-8"),
                (candidate / ".gitleaks.toml").read_text(encoding="utf-8"),
                "the artifact scanner must use the same sanitized allowlist as the published workflow",
            )

            result = subprocess.run(
                ["python3", str(CHECKER), str(candidate)],
                cwd=ROOT, capture_output=True, text=True, timeout=120,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_checker_refuses_a_workflow_that_calls_a_missing_script(self):
        with tempfile.TemporaryDirectory(prefix="an3-workflow-scripts-") as temporary:
            candidate = Path(temporary)
            workflows = candidate / ".github/workflows"
            workflows.mkdir(parents=True)
            (workflows / "native-build.yml").write_text(
                "jobs:\n  macos:\n    steps:\n      - run: bash tools/release-train.sh --staging build macos\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["python3", str(CHECKER), str(candidate)],
                cwd=ROOT, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("tools/release-train.sh", result.stderr)
            self.assertIn("native-build.yml", result.stderr)

            # The same candidate passes once the script it calls is present.
            (candidate / "tools").mkdir()
            (candidate / "tools/release-train.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            again = subprocess.run(
                ["python3", str(CHECKER), str(candidate)],
                cwd=ROOT, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)

    def test_checker_cannot_run_is_not_a_clean_result(self):
        result = subprocess.run(
            ["python3", str(CHECKER), str(ROOT / "work/does-not-exist-candidate")],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_acceptance_gate_runs_the_workflow_script_check(self):
        gate = PUBLICATION_CHECK.read_text(encoding="utf-8")
        self.assertIn("check-workflow-scripts.py", gate)
        check = gate.find("check-workflow-scripts.py")
        gitleaks = gate.find('gitleaks git "$SECRET_REPO"')
        self.assertNotEqual(gitleaks, -1)
        self.assertLess(
            check, gitleaks,
            "the workflow reference check must run before the secret scan completes the gate",
        )

    def test_node_workflow_globs_match_suites_in_this_checkout(self):
        patterns = ("tests/*.test.js", "tests/*.test.mjs")
        actual = {
            str(path.relative_to(ROOT))
            for pattern in patterns
            for path in (ROOT / "tests").glob(pattern.split("/", 1)[1])
        }
        self.assertTrue(actual, "the published Node test patterns must match files")
        for pattern in patterns:
            self.assertTrue(any(fnmatch(path, pattern) for path in actual), pattern)

        node_commands = [
            line for line in PORTABLE_WORKFLOW.splitlines()
            if line.strip().startswith("run: node --test")
        ]
        self.assertTrue(node_commands, "the portable workflow must run Node suites")
        self.assertTrue(all(all(pattern in line for pattern in patterns) for line in node_commands))
        self.assertFalse(any("native-offline/tests/*.test." in line for line in node_commands))

    def test_portable_workflow_whitespace_step_works_in_a_single_commit_snapshot(self):
        """The public repository has one commit, so `HEAD^` does not exist there."""
        self.assertIn("git rev-parse --verify -q HEAD^", PORTABLE_WORKFLOW)
        self.assertIn("git show --check", PORTABLE_WORKFLOW)
        # Vendored third-party bytes and repository-ignored generated scaffolding
        # are the only documented exclusions.
        for exclusion in (
            "native-offline/src-tauri/gen/**",
            "native-offline/native-runtime/core/vendor/**",
            "native-offline/vendor/**",
            "native-offline/patches/**",
            "qrcodegen.py",
            "static/fonts/**",
        ):
            self.assertIn(exclusion, PORTABLE_WORKFLOW)


if __name__ == "__main__":
    unittest.main()
