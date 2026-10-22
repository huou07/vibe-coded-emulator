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


    def test_only_release_installers_are_downloaded_for_scanning(self):
        workflow = (ROOT / ".github/workflows/native-release.yml").read_text(encoding="utf-8")
        for artifact in ("macos-dmg", "windows-exe", "linux-deb", "linux-flatpak", "android-apk"):
            with self.subTest(artifact=artifact):
                self.assertIn(f"name: {artifact}", workflow)
                self.assertIn(f"path: dist/{artifact}", workflow)
        self.assertNotIn("name: macos-ui-control-test-app", workflow)
        self.assertNotIn("name: windows-ui-control-test-shell", workflow)
        self.assertNotIn("name: android-instrumentation-apk", workflow)
        self.assertNotIn("          path: dist" + chr(10), workflow)

    def test_artifact_scan_uses_the_exact_binary_exception_manifest(self):
        workflow = (ROOT / ".github/workflows/native-release.yml").read_text(encoding="utf-8")
        self.assertIn("--exact-allowlist tools/release-artifact-allowlist.json", workflow)


if __name__ == "__main__":
    unittest.main()
