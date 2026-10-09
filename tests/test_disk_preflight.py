# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "tools/disk-preflight.sh"


class DiskPreflightTests(unittest.TestCase):
    def run_preflight(self, available_gib, *extra_env):
        with tempfile.TemporaryDirectory(prefix="an3-disk-preflight-") as temp:
            bin_dir = Path(temp) / "bin"
            bin_dir.mkdir()
            fake_df = bin_dir / "df"
            fake_df.write_text(
                "#!/bin/sh\nprintf '%s\\n' 'Filesystem 1024-blocks Used Available Capacity Mounted on'\n"
                f"printf '%s\\n' '/dev/test 100000000 1 {int(available_gib) * 1048576} 1% /'\n"
            )
            fake_df.chmod(0o755)
            env = os.environ.copy()
            env.update(dict(extra_env))
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
            return subprocess.run(
                ["bash", str(PREFLIGHT), "test build", temp],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

    def test_passes_above_warning_threshold(self):
        result = self.run_preflight(50)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DISK_PREFLIGHT=PASS", result.stdout)

    def test_warns_between_reserve_and_warning_threshold(self):
        result = self.run_preflight(30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DISK_PREFLIGHT=WARNING", result.stderr)

    def test_stops_below_reserve(self):
        result = self.run_preflight(24)
        self.assertEqual(result.returncode, 75)
        self.assertIn("DISK_PREFLIGHT=STOP", result.stderr)

    def test_rejects_invalid_threshold_order(self):
        result = self.run_preflight(
            50, ("AN3_DISK_WARNING_GIB", "40"), ("AN3_DISK_RESERVE_GIB", "41")
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("must not exceed", result.stderr)

    def test_heavyweight_staging_entrypoints_preflight_before_build_work(self):
        checks = (
            (ROOT / "native-offline/scripts/build-macos-eden-companion.sh", "prepare-eden-source"),
            (ROOT / "native-offline/scripts/build-android-staging.sh", "build-android-runtime.sh"),
            (ROOT / "native-offline/scripts/build-linux-staging.sh", "prepare-web"),
        )
        for path, first_build_step in checks:
            with self.subTest(script=path.name):
                script = path.read_text()
                self.assertIn("tools/disk-preflight.sh", script)
                self.assertLess(script.index("tools/disk-preflight.sh"), script.index(first_build_step))


if __name__ == "__main__":
    unittest.main()
