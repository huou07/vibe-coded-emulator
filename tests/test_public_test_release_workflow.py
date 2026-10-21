# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Public-test version tags must never become the stable/latest release."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PublicTestReleaseWorkflowTests(unittest.TestCase):
    def test_tag_release_is_explicitly_a_prerelease(self):
        workflow = (ROOT / ".github/workflows/native-release.yml").read_text(encoding="utf-8")
        self.assertRegex(workflow, r'gh release create "\$TAG" \\\n\s+--prerelease \\\n')


if __name__ == "__main__":
    unittest.main()
