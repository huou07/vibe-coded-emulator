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
NDS_SMOKE = (ROOT / "tools/windows-nds-runtime-smoke.ps1").read_text(encoding="utf-8")


class WindowsRuntimeSmokeTests(unittest.TestCase):
    def test_smoke_harness_changes_do_not_rebuild_the_all_platform_matrix_on_push(self):
        self.assertGreaterEqual(WORKFLOW.count("tests/test_windows_runtime_smoke.py"), 1)
        self.assertGreaterEqual(WORKFLOW.count("tools/windows-runtime-smoke.ps1"), 2)
        pull_request = WORKFLOW[WORKFLOW.index("  pull_request:"):WORKFLOW.index("  push:")]
        push = WORKFLOW[WORKFLOW.index("  push:"):WORKFLOW.index("\npermissions:")]
        self.assertIn("      - '.github/workflows/**'", pull_request)
        self.assertIn("      - 'tools/windows-runtime-smoke.ps1'", pull_request)
        self.assertNotIn("tools/windows-runtime-smoke.ps1", push)

    def test_hosted_windows_candidate_can_build_and_smoke_without_other_platform_jobs(self):
        self.assertIn("build_windows_candidate:", WORKFLOW)
        self.assertIn("default: false", WORKFLOW)
        self.assertIn("if: github.event_name != 'workflow_dispatch' || inputs.build_windows_candidate", WORKFLOW)
        self.assertIn("build_macos_candidate:", WORKFLOW)
        self.assertIn("inputs.build_macos_candidate", WORKFLOW)
        self.assertIn("build_linux_candidate:", WORKFLOW)
        self.assertIn("build_android_candidate:", WORKFLOW)
        web_cache_job = WORKFLOW[WORKFLOW.index("  web-runtime-cache:"):WORKFLOW.index("  macos-dmg:")]
        self.assertIn("inputs.build_linux_candidate", web_cache_job)
        self.assertIn("inputs.build_android_candidate", web_cache_job)
        android_job = WORKFLOW[WORKFLOW.index("  android-apk:"):WORKFLOW.index("  linux-deb:")]
        linux_job = WORKFLOW[WORKFLOW.index("  linux-deb:"):WORKFLOW.index("  linux-deb-install:")]
        self.assertIn("if: github.event_name != 'workflow_dispatch' || inputs.build_android_candidate", android_job)
        self.assertIn("if: github.event_name != 'workflow_dispatch' || inputs.build_linux_candidate", linux_job)
        mac_refresh_job = WORKFLOW[WORKFLOW.index("  macos-ui-control-refresh:"):WORKFLOW.index("  android-apk:")]
        self.assertIn("!inputs.build_linux_candidate && !inputs.build_android_candidate", mac_refresh_job)
        self.assertIn("inputs.windows_artifact_run_id != ''", WORKFLOW)

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
        self.assertIn("inputs.build_windows_candidate && needs.windows-exe.result == 'success'", smoke_job)
        self.assertIn("inputs.windows_artifact_run_id != ''", smoke_job)
        self.assertIn("name: windows-exe", smoke_job)
        self.assertIn("name: windows-ui-control-test-shell", smoke_job)
        self.assertIn("-AutomationDirectory artifacts/windows-ui-control", smoke_job)
        self.assertIn("windows_expected_source_sha", smoke_job)
        self.assertIn("windows_artifact_run_id", smoke_job)

        self.assertIn("AN3_UI_TEST_ROM", SMOKE)
        self.assertIn("$env:SDL_AUDIODRIVER = 'dummy'", SMOKE)
        self.assertLess(SMOKE.index("$env:SDL_AUDIODRIVER = 'dummy'"), SMOKE.index("$mainProcess = Start-Process"))
        self.assertIn("'open-rom'", SMOKE)
        self.assertNotIn("DOM.setFileInputFiles", SMOKE)
        self.assertIn("'game-card'", SMOKE)
        self.assertIn("'game-launch'", SMOKE)
        self.assertIn("'native-status'", SMOKE)
        self.assertIn("$currentStatusName -ne $initialNativeStatusName -and !$isStarting", SMOKE)
        self.assertNotIn("$nativeStatus.data.node.state", SMOKE)
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
        self.assertIn("Capture-NativePlayerWindow", SMOKE)
        self.assertIn("GetWindowsForProcess", SMOKE)
        self.assertIn("IsWindowVisible", SMOKE)
        self.assertIn("CopyFromScreen", SMOKE)
        self.assertIn("GetPixel", SMOKE)
        self.assertIn("Capture-RendererDiagnostics", SMOKE)
        self.assertIn("renderer-diagnostics.png", SMOKE)
        self.assertIn("renderer-graphics.png", SMOKE)
        self.assertIn("videoFrameStatus = $frameCapture.status", SMOKE)
        self.assertIn("videoFrameScreenshot = $frameCapture.screenshot", SMOKE)
        self.assertIn("No visible native player window displayed the fixture's $ExpectedColor frame", SMOKE)
        self.assertIn("shell-shutdown.json", SMOKE)
        self.assertIn("nativePlayerExited = $true", SMOKE)
        self.assertIn("WINDOWS_INSTALL_SHELL_IMPORT_LAUNCH_INPUT_SAVE_LOAD_SRAM=GOOD", SMOKE)

    def test_windows_session_controls_run_inside_the_shared_play_page(self):
        self.assertIn("--testid', 'native-session'", SMOKE)
        for testid in ("native-session-pause", "native-session-save", "native-session-load"):
            self.assertIn(f"--testid', '{testid}'", SMOKE)
        for result in ("Game paused.", "Game resumed.", "Quick save 1 completed.", "Quick load 1 completed."):
            self.assertIn(result, SMOKE)
        self.assertIn("windows-shell-session-controls.json", SMOKE)

    def test_targeted_windows_run_builds_lawful_nds_fixture_and_tests_exact_package(self):
        pull_request = WORKFLOW[WORKFLOW.index("  pull_request:"):WORKFLOW.index("  push:")]
        snapshot_builder = (ROOT / "tools/build-public-snapshot.sh").read_text(encoding="utf-8")
        fixture_job = WORKFLOW[WORKFLOW.index("  windows-nds-fixture:"):WORKFLOW.index("  windows-packaged-nds-smoke:")]
        nds_job = WORKFLOW[WORKFLOW.index("  windows-packaged-nds-smoke:"):WORKFLOW.index("  android-smoke:")]
        self.assertIn("tools/windows-nds-runtime-smoke.ps1", pull_request)
        self.assertIn('tools/windows-nds-runtime-smoke.ps1" ]] && cp', snapshot_builder)
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.windows_artifact_run_id != ''", fixture_job)
        self.assertIn("devkitPro/nds-examples.git", fixture_job)
        self.assertIn("f1ba715a451c6407f8b0f805999d0153062ff552", fixture_job)
        self.assertIn("devkitpro/devkitarm@sha256:340c466b53961c0d90e7536f6db3364d4bfede0f65a26492c25b118d0a00d82e", fixture_job)
        self.assertIn("3cbd04760c71e49ca2617604515abc7d26aeadd583418f28557d1a9ee7a95544", fixture_job)
        self.assertIn("run-id: ${{ inputs.windows_artifact_run_id }}", nds_job)
        self.assertIn("windows-nds-fixture", nds_job)
        self.assertIn("retention-days: 3", nds_job)
        self.assertIn("EXPECTED_SOURCE_SHA", NDS_SMOKE)
        self.assertIn("melondsds_libretro.dll", NDS_SMOKE)
        self.assertIn("'--system', 'nds'", NDS_SMOKE)
        self.assertIn("$status.coreFrames -ne 120", NDS_SMOKE)
        self.assertIn("$colors.Count -le 16", NDS_SMOKE)
        self.assertIn("$installDir = Join-Path $env:RUNNER_TEMP 'vce-windows-nds-installed'", NDS_SMOKE)
        self.assertIn("$storage = Join-Path $env:RUNNER_TEMP 'vce-windows-nds-storage'", NDS_SMOKE)
        self.assertNotIn("Join-Path $evidence 'installed-app'", NDS_SMOKE)
        self.assertNotIn("Join-Path $evidence 'storage'", NDS_SMOKE)

    def test_targeted_windows_3ds_run_uses_pinned_fixture_and_exact_package(self):
        workflow_dispatch = WORKFLOW[WORKFLOW.index("  workflow_dispatch:"):WORKFLOW.index("  pull_request:")]
        fixture_job = WORKFLOW[WORKFLOW.index("  windows-packaged-3ds-smoke:"):WORKFLOW.index("  android-smoke:")]
        snapshot_builder = (ROOT / "tools/build-public-snapshot.sh").read_text(encoding="utf-8")
        smoke = (ROOT / "tests/windows_packaged_3ds_smoke.py").read_text(encoding="utf-8")
        self.assertIn("windows_3ds_artifact_run_id", workflow_dispatch)
        self.assertIn("windows_3ds_expected_source_sha", workflow_dispatch)
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.windows_3ds_artifact_run_id != ''", fixture_job)
        self.assertIn("run-id: ${{ inputs.windows_3ds_artifact_run_id }}", fixture_job)
        self.assertIn("Configure hosted CPU Vulkan ICD for 3DS", fixture_job)
        self.assertIn("vk_swiftshader_icd.json", fixture_job)
        self.assertIn('"VK_ICD_FILENAMES=', fixture_job)
        self.assertIn("16BitWonder/3DS-TEST.git", fixture_job)
        self.assertIn("e5b13872f0c1207cb9c86e18e710c8f1fa269fb8", fixture_job)
        self.assertIn("a9fac712e9a6e937ec3d3d3228d8031d94030f3bec3462d9048897f3be638050", fixture_job)
        self.assertIn("\"--system\", \"3ds\"", smoke)
        self.assertIn("\"--renderer\", \"vulkan\"", smoke)
        self.assertIn('process.stdin.write("1\\tbutton\\t8:1\\n")', smoke)
        self.assertIn("AN3_NATIVE_CONTROL_RESULT 1 OK", smoke)
        self.assertIn("PostMessageW(hwnd, 0x0010", smoke)
        self.assertIn("thread apply all backtrace", smoke)
        self.assertIn("info sharedlibrary", smoke)
        self.assertIn('"-batch", "-x", str(commands)', smoke)
        self.assertIn('"shutdownDebugger": shutdown_debugger', smoke)
        self.assertIn('"shutdownModules": shutdown_modules', smoke)
        self.assertIn("Get-Process -Id", smoke)
        self.assertIn("ImageChops.difference", smoke)
        self.assertIn("game_area(baseline)", smoke)
        self.assertIn("visible_percent > 2.0", smoke)
        self.assertIn("windows-packaged-3ds-diagnostics", fixture_job)
        self.assertIn("pip install --disable-pip-version-check pillow", fixture_job)
        self.assertIn("cp -R \"$ROOT/tests/.\" \"$OUT/tests/\"", snapshot_builder)

    def test_native_player_shows_only_the_game_window(self):
        self.assertIn("$controlsWindow = $visibleNativeWindows | Where-Object { $_.Title -match 'Controls$' }", SMOKE)
        self.assertIn("if ($visibleNativeWindows.Count -ne 1)", SMOKE)
        self.assertIn("visibleNativeWindowCount = $visibleNativeWindows.Count", SMOKE)

    def test_windows_shell_navigation_uses_the_visible_desktop_sidebar(self):
        for section in ("library", "settings", "about", "play"):
            self.assertIn(f"--css', '.native-sidebar [data-nav=\"{section}\"]'", SMOKE)
            self.assertNotIn(f"--testid', 'nav-{section}'", SMOKE)

    def test_windows_shell_virtual_input_changes_and_restores_the_visible_frame(self):
        self.assertIn("'--css', '[data-native-button=\"8\"]'", SMOKE)
        self.assertIn("Capture-NativePlayerWindow ([int]$runtimeProcess.ProcessId) 'red'", SMOKE)
        self.assertIn("Capture-NativePlayerWindow ([int]$runtimeProcess.ProcessId) 'blue'", SMOKE)
        self.assertIn("virtualAInputFrameStatus = $inputFrameCapture.status", SMOKE)
        self.assertIn("restoredFrameStatus = $restoredFrameCapture.status", SMOKE)
        self.assertIn("WINDOWS_INSTALL_SHELL_IMPORT_LAUNCH_INPUT_SAVE_LOAD_SRAM=GOOD", SMOKE)

    def test_packaged_windows_player_persists_gba_sram_across_fresh_processes(self):
        self.assertIn("gba_homebrew_test.py $sramFixture AN3SRAMTEST", SMOKE)
        self.assertIn("'--storage', $sramStorage", SMOKE)
        self.assertEqual(
            SMOKE.count("$sramFresh = Invoke-An3ctl $sramBase")
            + SMOKE.count("$sramRestored = Invoke-An3ctl $sramBase"),
            2,
        )
        self.assertIn("$sramFresh.data.rawHash -eq $sramRestored.data.rawHash", SMOKE)
        self.assertIn("$sramSignature -ne 'AN3B'", SMOKE)
        self.assertIn("$sramBootCounter -ne 1", SMOKE)
        self.assertIn("Remove-Item -LiteralPath $sramStorage -Recurse -Force", SMOKE)
        self.assertIn("$snapshot.pngPath", SMOKE)
        self.assertIn("$snapshot.rawPath", SMOKE)
        self.assertIn("sramChangedFrameAfterRelaunch = $sramFresh.data.rawHash -ne $sramRestored.data.rawHash", SMOKE)

    def test_smoke_preserves_distribution_binary_and_verifies_test_import_guard(self):
        # The hosted runner's PowerShell parser rejects digit separators in this script.
        self.assertNotRegex(SMOKE, r"\b\d+(?:_\d+)+\b")
        self.assertIn("$automationTestExe = Join-Path $installDir 'an3-offline-native-ui-test.exe'", SMOKE)
        self.assertIn("Start-Process -FilePath $automationTestExe -WorkingDirectory $installDir", SMOKE)
        self.assertIn("$installerStartedApp = $false", SMOKE)
        self.assertIn("$_.ExecutablePath.Equals($mainExe", SMOKE)
        self.assertIn("fresh install left port 38471 occupied", SMOKE)
        self.assertIn("Write-Evidence 'distribution-shell.json'", SMOKE)
        self.assertIn("Write-Evidence 'distribution-shell-ui.json'", SMOKE)
        self.assertIn("Start-Process -FilePath $mainExe -WorkingDirectory $installDir -PassThru", SMOKE)
        self.assertIn("Packaged shell navigation ended on unexpected sections", SMOKE)
        self.assertIn("Closing the packaged shell left port 38471 occupied.", SMOKE)
        self.assertIn("Closing the packaged shell left WebView2 CDP port 9222 occupied.", SMOKE)
        self.assertIn("runtimeAndCdpPortsReleased = $true", SMOKE)
        self.assertIn("uiJourneyPassed = (Test-Path (Join-Path $evidence 'distribution-shell-ui.json'))", SMOKE)
        self.assertIn("distributionShellUnchanged = ((Get-FileHash $mainExe", SMOKE)
        self.assertIn("Remove-Item -LiteralPath $automationTestExe -Force", SMOKE)
        self.assertNotIn("Copy-Item -LiteralPath $automationExe -Destination $mainExe", SMOKE)
        self.assertIn("AN3_UI_CONTROL_FILE", SMOKE)
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
