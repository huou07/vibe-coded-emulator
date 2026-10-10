# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Source contracts for the black-box Linux distribution shell smoke."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/native-build.yml").read_text(encoding="utf-8")
SMOKE = (ROOT / "tests/linux_distribution_shell_smoke.py").read_text(encoding="utf-8")


class LinuxDistributionShellSmokeTests(unittest.TestCase):
    def test_smoke_uses_the_exact_installed_distribution_binary(self):
        job = WORKFLOW[WORKFLOW.index("  linux-distribution-shell-smoke:"):WORKFLOW.index("  linux-flatpak:")]
        self.assertIn("inputs.linux_artifact_run_id != ''", job)
        self.assertIn("name: linux-deb", job)
        self.assertIn("run-id: ${{ inputs.linux_artifact_run_id }}", job)
        self.assertIn("sha256sum --check ./*.deb.sha256", job)
        self.assertIn("/usr/bin/an3-offline-native", job)
        self.assertIn("python3-pyatspi", job)
        self.assertIn("tests/linux_distribution_shell_smoke.py", job)
        self.assertIn("getExtents(pyatspi.DESKTOP_COORDS)", SMOKE)
        self.assertIn("b\"AN3_UI_CONTROL_FILE\"", SMOKE)
        self.assertIn("subprocess.Popen([str(BINARY)]", SMOKE)
        self.assertNotIn("AN3_UI_TEST_ROM", SMOKE)
        self.assertNotIn("ui-control", SMOKE)

    def test_smoke_checks_isolated_navigation_and_shutdown(self):
        self.assertIn('"XDG_DATA_HOME": str(home / ".local/share")', SMOKE)
        self.assertIn('wait_for("Add ROM GBA · NDS · 3DS")', SMOKE)
        self.assertIn('wait_for("Search games", pyatspi.ROLE_ENTRY)', SMOKE)
        for section in ("Library", "Settings", "Help", "About", "Play"):
            self.assertIn(f'click_button("{section}")', SMOKE)
        self.assertIn('"aboutVersion": "3.6.8"', SMOKE)
        self.assertIn('"Alt+F4"', SMOKE)
        self.assertIn("port_free", SMOKE)
        self.assertIn('"screenshots": screenshots', SMOKE)
        self.assertIn('"emptyLibraryAccessible": True', SMOKE)
        self.assertIn('"libraryVisualState": "UNVERIFIED:', SMOKE)
        self.assertIn("LINUX_DISTRIBUTION_LIBRARY_VISUAL=UNVERIFIED", SMOKE)


if __name__ == "__main__":
    unittest.main()
