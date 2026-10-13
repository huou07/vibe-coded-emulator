# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression coverage for the fail-closed pre-publication security gate.

The gate once ran its project-specific secret/personal-data scan through
``git grep``. ``tools/build-public-snapshot.sh`` does not run ``git init``, and
``tools/publish-github.sh`` invokes the gate *before* it initialises the
snapshot, so the scan matched nothing on the primary publication path and the
gate reported ``PUBLICATION_CHECK=PASS`` on a candidate containing a live auth
pepper. These tests pin the corrected behaviour: the scan runs on a plain
directory, and a scanner that cannot run is a failure, never a clean result.

All fixtures are synthetic. No real credential or personal data is used.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLICATION_CHECK = ROOT / "tools/publication-check.sh"
BUILD_SNAPSHOT = ROOT / "tools/build-public-snapshot.sh"

REQUIRED_FILES = (
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    ".env.example",
    ".gitignore",
)


def make_candidate(directory: Path) -> Path:
    """Build a minimally valid candidate that passes every non-security check."""
    candidate = Path(directory) / "candidate"
    candidate.mkdir()
    for name in REQUIRED_FILES:
        (candidate / name).write_text("placeholder\n", encoding="utf-8")
    (candidate / "LICENSE").write_text(
        "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n", encoding="utf-8"
    )
    (candidate / "README.md").write_text(
        "Vibe Coded Emulator is licensed GPL-3.0-or-later.\n", encoding="utf-8"
    )
    (candidate / ".gitleaks.toml").write_text('title = "fixture"\n', encoding="utf-8")
    return candidate


def run_gate(candidate: Path):
    return subprocess.run(
        ["bash", str(PUBLICATION_CHECK), str(candidate)],
        text=True,
        capture_output=True,
        check=False,
    )


def has_gitleaks() -> bool:
    return shutil.which("gitleaks") is not None


# tests/ is published verbatim in the public snapshot, and the publication gate
# scans that snapshot. A literal `AN3_AUTH_PEPPER=<value>` in this file would
# therefore be a genuine finding against the real release candidate, so the
# synthetic value is assembled from fragments: the fixture written to the
# temporary candidate is still realistic, but no secret-shaped literal ever
# appears in published source.
FAKE_PEPPER = "AN3_AUTH_PEPPER=" + "AbCdEf" + "0123456789" + "XYZ"
FAKE_PEPPER_VALUE = FAKE_PEPPER.split("=", 1)[1]


class ProjectPatternScanTests(unittest.TestCase):
    """The project-specific scan must work without a Git repository."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.candidate = make_candidate(Path(self._tmp.name))

    def test_scan_runs_on_a_plain_directory_and_blocks(self):
        """The exact case that failed open: no .git, secret present."""
        self.assertFalse(
            (self.candidate / ".git").exists(),
            "fixture must not be a Git repository; that is the regression condition",
        )
        (self.candidate / "leaked_settings.py").write_text(
            FAKE_PEPPER + "\n", encoding="utf-8"
        )

        if not has_gitleaks():
            self.skipTest("gitleaks is not installed")

        result = run_gate(self.candidate)

        self.assertNotEqual(
            result.returncode,
            0,
            "publication gate accepted a candidate containing a live auth pepper",
        )
        self.assertIn("PUBLICATION_CHECK=FAIL", result.stderr)
        self.assertNotIn("PUBLICATION_CHECK=PASS", result.stdout)
        self.assertIn(
            "leaked_settings.py",
            result.stderr,
            "the failing file should be named so an operator can act on it",
        )

    def test_scan_does_not_leak_the_secret_value(self):
        (self.candidate / "leaked_settings.py").write_text(
            FAKE_PEPPER + "\n", encoding="utf-8"
        )

        result = run_gate(self.candidate)

        combined = result.stdout + result.stderr
        self.assertNotIn(FAKE_PEPPER_VALUE, combined)

    def test_infrastructure_address_is_blocked(self):
        (self.candidate / "deploy_notes.md").write_text(
            "reverse proxy listens on 192.168.1.8:8088\n", encoding="utf-8"
        )

        if not has_gitleaks():
            self.skipTest("gitleaks is not installed")

        result = run_gate(self.candidate)

        self.assertNotEqual(result.returncode, 0, "private LAN address must block publication")
        self.assertIn("PUBLICATION_CHECK=FAIL", result.stderr)

    def test_clean_candidate_passes(self):
        """A candidate with no forbidden content must still be publishable."""
        (self.candidate / "app.py").write_text("print('ok')\n", encoding="utf-8")

        if not has_gitleaks():
            self.skipTest("gitleaks is not installed")

        result = run_gate(self.candidate)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PUBLICATION_CHECK=PASS", result.stdout)
        self.assertIn("personal-data and infra patterns: clean", result.stdout)

    def test_scan_result_is_the_same_with_and_without_git(self):
        """The gate must not depend on the candidate's VCS state."""
        (self.candidate / "leaked_settings.py").write_text(
            FAKE_PEPPER + "\n", encoding="utf-8"
        )

        if not has_gitleaks():
            self.skipTest("gitleaks is not installed")

        without_git = run_gate(self.candidate)

        env = os.environ.copy()
        env.update(
            {
                "GIT_AUTHOR_NAME": "fixture",
                "GIT_AUTHOR_EMAIL": "fixture@example.com",
                "GIT_COMMITTER_NAME": "fixture",
                "GIT_COMMITTER_EMAIL": "fixture@example.com",
            }
        )
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.candidate)], check=True)
        subprocess.run(["git", "-C", str(self.candidate), "add", "-A"], check=True, env=env)
        subprocess.run(
            ["git", "-C", str(self.candidate), "commit", "-qm", "fixture"],
            check=True,
            env=env,
        )
        with_git = run_gate(self.candidate)

        self.assertEqual(
            without_git.returncode,
            with_git.returncode,
            "gate outcome changed when the candidate became a Git repository",
        )
        self.assertNotEqual(without_git.returncode, 0)


class ForbiddenPathTests(unittest.TestCase):
    """Non-secret forbidden content must still be rejected."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.candidate = make_candidate(Path(self._tmp.name))

    def test_private_agent_configuration_is_blocked(self):
        (self.candidate / "AGENTS.md").write_text("private instructions\n", encoding="utf-8")

        result = run_gate(self.candidate)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("forbidden path", result.stderr)

    def test_prohibited_game_content_is_blocked(self):
        (self.candidate / "roms").mkdir()
        (self.candidate / "roms/homebrew.gba").write_bytes(b"fixture")

        result = run_gate(self.candidate)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("prohibited binary", result.stderr)

    def test_missing_required_file_is_blocked(self):
        (self.candidate / "SECURITY.md").unlink()

        result = run_gate(self.candidate)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing required public file", result.stderr)


def commands_using(script: str, tool: str):
    """Return non-comment, non-doc lines that invoke `tool` as a command."""
    found = []
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # `|| git grep ...` and `if git grep ...` are real invocations; a
        # mention inside prose is not.
        if tool in stripped and stripped.split(tool)[0].rstrip().endswith(("|", "&&", "||", "(", "!", "if", "then", "=")):
            found.append(stripped)
    return found


class GateOrderTests(unittest.TestCase):
    """The gate has to run before git init, so it cannot rely on Git state."""

    def test_publish_script_gates_before_initialising_the_snapshot(self):
        publish = (ROOT / "tools/publish-github.sh").read_text(encoding="utf-8")

        gate = publish.find("publication-check.sh")
        init = publish.find('git -C "$SNAPSHOT" init')

        self.assertNotEqual(gate, -1, "publish-github.sh must run the security gate")
        self.assertNotEqual(init, -1, "publish-github.sh must initialise the snapshot")
        self.assertLess(
            gate,
            init,
            "the gate must run before `git init`; otherwise the gate cannot "
            "depend on the candidate being a Git repository",
        )

    def test_publish_script_does_not_scan_the_snapshot_with_git_grep(self):
        publish = (ROOT / "tools/publish-github.sh").read_text(encoding="utf-8")

        self.assertEqual(
            commands_using(publish, "git grep"),
            [],
            "publishing must not depend on Git-aware scanning of the candidate",
        )

    def test_gate_does_not_scan_with_git_grep(self):
        gate = PUBLICATION_CHECK.read_text(encoding="utf-8")

        self.assertEqual(
            commands_using(gate, "git grep"),
            [],
            "publication-check.sh must not scan through git grep; the candidate "
            "is not a Git repository when this gate runs",
        )

    def test_gate_scans_with_a_plain_recursive_grep(self):
        gate = PUBLICATION_CHECK.read_text(encoding="utf-8")

        self.assertIn(
            "grep -rIlE",
            gate,
            "the project-specific scan must use a recursive grep that works on "
            "a plain directory",
        )


if __name__ == "__main__":
    unittest.main()
