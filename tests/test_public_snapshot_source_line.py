# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Only the core-only public product may be published to the public repository.

The public line is the core-only product: its own contract tests require the
account/login, CMS/analytics and phone-controller surfaces to be absent, and
those tests stay on the public line when a review branch is overlaid onto it.
``tools/publish-github.sh`` copies ``app.py`` verbatim, so publishing a candidate
exported from the full-featured private development line replaces the public
``app.py`` with one that still defines those routes. That happened for real: a
snapshot exported from the development line and published as a review branch
failed the public Python job with 54 failures and 48 errors, and the pull
request had to be closed unmerged.

These checks exercise the real script against synthetic candidates, so they are
safe to run anywhere and never publish anything.
"""

import pathlib
import re
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/publish-github.sh"

CORE_ONLY_APP = """\
# A core-only candidate: no account, CMS or phone-controller surface.
def route(path):
    if path == "/games":
        return 200
    return 404
"""

FULL_FEATURE_APP = """\
def route(path):
    if path == "/games":
        return 200
    if path == "/login":
        return 200
    if path == "/api/account/session":
        return 200
    return 404
"""


class PublicPublicationSourceLineTests(unittest.TestCase):
    def _candidate(self, directory, app_source):
        candidate = pathlib.Path(directory) / "candidate"
        candidate.mkdir()
        (candidate / "app.py").write_text(app_source, encoding="utf-8")
        return candidate

    def _check(self, candidate):
        return subprocess.run(
            ["bash", str(SCRIPT), "--check-candidate", "--snapshot", str(candidate)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_check_candidate_refuses_a_full_featured_candidate(self):
        if not SCRIPT.is_file():
            self.skipTest("tools/publish-github.sh is not part of this tree")
        with tempfile.TemporaryDirectory(prefix="an3-publish-source-") as temporary:
            result = self._check(self._candidate(temporary, FULL_FEATURE_APP))
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn("PUBLISH=FAIL", output)
        self.assertIn("core-only", output)
        for marker in ('path == "/login"', '"/api/account/'):
            self.assertIn(marker, output, "the refusal must name the offending surface")

    def test_check_candidate_accepts_a_core_only_candidate(self):
        if not SCRIPT.is_file():
            self.skipTest("tools/publish-github.sh is not part of this tree")
        with tempfile.TemporaryDirectory(prefix="an3-publish-source-") as temporary:
            result = self._check(self._candidate(temporary, CORE_ONLY_APP))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PUBLICATION_SOURCE=PASS", result.stdout)

    def test_check_candidate_needs_no_confirm_and_publishes_nothing(self):
        if not SCRIPT.is_file():
            self.skipTest("tools/publish-github.sh is not part of this tree")
        with tempfile.TemporaryDirectory(prefix="an3-publish-source-") as temporary:
            candidate = self._candidate(temporary, CORE_ONLY_APP)
            result = self._check(candidate)
            # It must not have turned the candidate into a repository or a PR.
            self.assertFalse((candidate / ".git").exists())
        self.assertNotIn("--confirm", result.stderr)
        self.assertNotIn("PUBLISH=FAIL", result.stdout)

    def test_publication_checks_the_source_line_before_it_initialises_git(self):
        if not SCRIPT.is_file():
            self.skipTest("tools/publish-github.sh is not part of this tree")
        script = SCRIPT.read_text(encoding="utf-8")
        check = script.find("check_core_only_candidate \"$SNAPSHOT\"")
        init = script.find('git -C "$SNAPSHOT" init')
        self.assertNotEqual(check, -1, "publishing must verify the core-only source line")
        self.assertNotEqual(init, -1)
        self.assertLess(
            check,
            init,
            "the source-line check must run before the candidate is made into a repository",
        )
        # The check must also be wired into the publication flow, not only into
        # the standalone --check-candidate path.
        self.assertGreaterEqual(len(re.findall(r"check_core_only_candidate", script)), 3)


if __name__ == "__main__":
    unittest.main()
