# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Source contracts for the hosted Windows package-to-game smoke."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/native-build.yml").read_text(encoding="utf-8")
SMOKE = (ROOT / "tools/windows-runtime-smoke.ps1").read_text(encoding="utf-8")
BUILDER = (ROOT / "native-offline/scripts/build-windows-automation.ps1").read_text(encoding="utf-8")
TAURI_LIB = (ROOT / "native-offline/src-tauri/src/lib.rs").read_text(encoding="utf-8")


class WindowsRuntimeSmokeTests(unittest.TestCase):
    def test_smoke_harness_changes_trigger_the_hosted_package_build(self):
        self.assertGreaterEqual(WORKFLOW.count("tests/test_windows_runtime_smoke.py"), 2)
        self.assertGreaterEqual(WORKFLOW.count("tools/windows-runtime-smoke.ps1"), 2)
        self.assertIn("      - '.github/workflows/**'", WORKFLOW)

    def test_test_shell_is_separate_source_matched_and_test_feature_only(self):
        windows_job = WORKFLOW[WORKFLOW.index("  windows-exe:"):WORKFLOW.index("  windows-runtime-smoke:")]
        self.assertIn("Build canonical Windows installer", windows_job)
        self.assertIn("upload-artifact", windows_job)
        self.assertIn("build-windows-automation.ps1", windows_job)
        self.assertIn("windows-ui-control-test-shell", windows_job)
        self.assertIn("retention-days: 7", windows_job)
        self.assertIn("cargo build --release --features ui-control", BUILDER)
        self.assertIn("space.an3tocom.offline.automation", BUILDER)
        self.assertIn("windows-ui-control-test-shell", BUILDER)
        self.assertIn("AN3_UI_CONTROL_FILE", BUILDER)

    def test_pr_runs_the_exact_package_and_shell_import_launch_smoke(self):
        smoke_job = WORKFLOW[WORKFLOW.index("  windows-runtime-smoke:"):WORKFLOW.index("  android-smoke:")]
        self.assertIn("github.event_name == 'pull_request'", smoke_job)
        self.assertIn("needs: windows-exe", smoke_job)
        self.assertIn("needs.windows-exe.result == 'success'", smoke_job)
        self.assertIn("name: windows-exe", smoke_job)
        self.assertIn("name: windows-ui-control-test-shell", smoke_job)
        self.assertIn("-AutomationDirectory artifacts/windows-ui-control", smoke_job)
        self.assertIn("windows_expected_source_sha", smoke_job)
        self.assertIn("windows_artifact_run_id", smoke_job)

        self.assertIn("AN3_UI_TEST_ROM", SMOKE)
        self.assertIn("'open-rom'", SMOKE)
        self.assertNotIn("DOM.setFileInputFiles", SMOKE)
        self.assertIn("'game-card'", SMOKE)
        self.assertIn("'game-launch'", SMOKE)
        self.assertIn("'native-status'", SMOKE)
        self.assertIn("$nativeStatus.data.node.state -in @('running', 'error')", SMOKE)
        self.assertIn("Write-Evidence 'launch.json'", SMOKE)
        self.assertIn("lastStatusQueryError = $nativeStatusQueryError", SMOKE)
        self.assertIn("Write-Evidence 'native-rom-storage.json'", SMOKE)
        self.assertIn("Get-WindowsPageDiagnostics", SMOKE)
        self.assertIn("Write-Evidence 'game-card-rom-id.json'", SMOKE)
        self.assertIn("Runtime.evaluate", SMOKE)
        self.assertIn("launchToastDetail = $launchToastDetail", SMOKE)
        self.assertIn("space.an3tocom.offline.automation", SMOKE)
        self.assertIn("an3-native-runtime.exe", SMOKE)
        self.assertIn("ParentProcessId", SMOKE)
        self.assertIn("MainWindowHandle", SMOKE)
        self.assertIn("shell-shutdown.json", SMOKE)
        self.assertIn("nativePlayerExited = $true", SMOKE)
        self.assertIn("WINDOWS_INSTALL_SHELL_IMPORT_LAUNCH_AND_DIRECT_PLAYER_INPUT_SAVE_LOAD=GOOD", SMOKE)

    def test_smoke_preserves_distribution_binary_and_verifies_test_import_guard(self):
        # The hosted runner's PowerShell parser rejects digit separators in this script.
        self.assertNotRegex(SMOKE, r"\b\d+(?:_\d+)+\b")
        self.assertIn("$automationBackup = \"$mainExe.distribution-backup\"", SMOKE)
        self.assertIn("AN3_UI_CONTROL_FILE", SMOKE)
        self.assertIn("Move-Item -LiteralPath $automationBackup -Destination $mainExe", SMOKE)
        self.assertIn("Remove-Item Env:AN3_UI_TEST_ROM", SMOKE)
        self.assertIn("--seq', 'A@0-1'", SMOKE)
        self.assertIn("--save-state", SMOKE)
        self.assertIn("--load-state", SMOKE)

        import_start = TAURI_LIB.index("async fn pick_and_import_native_rom(")
        import_end = TAURI_LIB.index("\nfn native_app_data_directory", import_start)
        import_command = TAURI_LIB[import_start:import_end]
        self.assertIn('#[cfg(feature = "ui-control")]', import_command)
        self.assertIn("AN3_UI_TEST_ROM", import_command)
        self.assertIn("import_native_rom(&import_app, &rom_id, PathBuf::from(path))", import_command)
        self.assertIn("blocking_pick_file()", import_command)


if __name__ == "__main__":
    unittest.main()
