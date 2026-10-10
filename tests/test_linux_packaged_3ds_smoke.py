# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Source contracts for the exact-package Linux 3DS smoke."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/native-build.yml").read_text(encoding="utf-8")
SMOKE = (ROOT / "tests/linux_packaged_3ds_smoke.py").read_text(encoding="utf-8")


class LinuxPackaged3DSSmokeTests(unittest.TestCase):
    def test_job_uses_exact_deb_and_pinned_lawful_fixture(self):
        job = WORKFLOW[WORKFLOW.index("  linux-packaged-3ds-smoke:"):WORKFLOW.index("  linux-flatpak:")]
        self.assertIn("inputs.linux_3ds_artifact_run_id != ''", job)
        self.assertIn("name: linux-deb", job)
        self.assertIn("sha256sum --check ./*.deb.sha256", job)
        self.assertIn("16BitWonder/3DS-TEST.git", job)
        self.assertIn("e5b13872f0c1207cb9c86e18e710c8f1fa269fb8", job)
        self.assertIn("a9fac712e9a6e937ec3d3d3228d8031d94030f3bec3462d9048897f3be638050", job)
        self.assertIn("mesa-vulkan-drivers", job)
        self.assertIn("VK_ICD_FILENAMES", job)
        self.assertIn("tests/linux_packaged_3ds_smoke.py", job)
        self.assertIn("if: always()", job)
        self.assertIn("retention-days: 3", job)

    def test_smoke_checks_packaged_azahar_output_and_a_input(self):
        self.assertIn('"--system", "3ds"', SMOKE)
        self.assertIn('"--renderer", "vulkan"', SMOKE)
        self.assertIn('"A@120-122"', SMOKE)
        self.assertIn('self.assertEqual(status.get("coreFrames"), frames, status)', SMOKE)
        self.assertIn('self.assertGreater(len(colors), 16', SMOKE)
        self.assertIn('self.assertGreater(changed_percent, 1.0', SMOKE)
        self.assertIn('"fixtureLicense": "MIT"', SMOKE)
        self.assertIn('"audio": "SDL dummy driver; audible output UNVERIFIED"', SMOKE)
        self.assertNotIn("AN3_UI_CONTROL_FILE", SMOKE)


if __name__ == "__main__":
    unittest.main()
