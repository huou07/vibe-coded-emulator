# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import os
from pathlib import Path
import json
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "tools/disk-preflight.sh"
PACKAGE = json.loads((ROOT / "native-offline/package.json").read_text(encoding="utf-8"))
ANDROID_BUILD = (ROOT / "native-offline/scripts/build-android-staging.sh").read_text(encoding="utf-8")
LINUX_BUILD = (ROOT / "native-offline/scripts/build-linux-staging.sh").read_text(encoding="utf-8")
WINDOWS_BUILD = (ROOT / "native-offline/scripts/build-windows-staging.ps1").read_text(encoding="utf-8")
MACOS_EDEN_BUILD = (ROOT / "native-offline/scripts/build-macos-eden-companion.sh").read_text(encoding="utf-8")
MACOS_AUTOMATION_BUILD = (ROOT / "native-offline/scripts/build-macos-automation.sh").read_text(encoding="utf-8")
WINDOWS_EDEN_BUILD = (ROOT / "native-offline/scripts/build-windows-eden-companion.ps1").read_text(encoding="utf-8")
WINDOWS_PREFLIGHT = ROOT / "tools/disk-preflight.ps1"


class DiskPreflightTests(unittest.TestCase):
    def run_preflight(self, available_gib, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            fake_bin = Path(directory) / "bin"
            fake_bin.mkdir()
            fake_df = fake_bin / "df"
            fake_df.write_text(
                '#!/bin/sh\nprintf "Filesystem 1024-blocks Used Available Capacity Mounted on\\n"\n'
                'printf "/dev/test 100000000 1 %s 1%% /\\n" '
                '"$((FAKE_AVAILABLE_GIB * 1048576))"\n',
                encoding="utf-8",
            )
            fake_df.chmod(0o755)
            env = os.environ.copy()
            env.update({key: str(value) for key, value in overrides.items()})
            env["FAKE_AVAILABLE_GIB"] = str(available_gib)
            env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
            return subprocess.run(
                ["bash", str(PREFLIGHT), "test build", directory],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

    def test_healthy_space_passes(self):
        result = self.run_preflight(50)
        self.assertEqual(result.returncode, 0)
        self.assertIn("DISK_PREFLIGHT=PASS", result.stdout)

    def test_warning_band_allows_work_with_warning(self):
        result = self.run_preflight(30)
        self.assertEqual(result.returncode, 0)
        self.assertIn("DISK_PREFLIGHT=WARNING", result.stderr)

    def test_reserve_stops_work_without_deleting_files(self):
        result = self.run_preflight(24)
        self.assertEqual(result.returncode, 75)
        self.assertIn("DISK_PREFLIGHT=STOP", result.stderr)

    def test_invalid_thresholds_fail_closed(self):
        result = self.run_preflight(50, AN3_DISK_RESERVE_GIB=41, AN3_DISK_WARNING_GIB=40)
        self.assertEqual(result.returncode, 2)
        self.assertIn("must not exceed", result.stderr)

    def test_local_heavy_package_entrypoints_check_space_before_build_work(self):
        scripts = PACKAGE["scripts"]
        for name in ("build", "build:deb", "android:build"):
            self.assertIn("disk-preflight.sh", scripts[name])
            self.assertLess(scripts[name].index("disk-preflight.sh"), scripts[name].index("prepare-"))
        self.assertLess(ANDROID_BUILD.index("disk-preflight.sh"), ANDROID_BUILD.index("build-android-runtime.sh"))
        self.assertLess(LINUX_BUILD.index("disk-preflight.sh"), LINUX_BUILD.index("fetch-linux-gba-nds-libretro.mjs"))
        self.assertTrue(WINDOWS_PREFLIGHT.is_file())
        self.assertLess(WINDOWS_BUILD.index("disk-preflight.ps1"), WINDOWS_BUILD.index("prepare-web"))
        self.assertLess(MACOS_EDEN_BUILD.index("disk-preflight.sh"), MACOS_EDEN_BUILD.index("prepare-eden-source.sh"))
        self.assertLess(MACOS_AUTOMATION_BUILD.index("disk-preflight.sh"), MACOS_AUTOMATION_BUILD.index("cargo build"))
        self.assertLess(WINDOWS_EDEN_BUILD.index("disk-preflight.ps1"), WINDOWS_EDEN_BUILD.index("remote add origin"))


if __name__ == "__main__":
    unittest.main()
