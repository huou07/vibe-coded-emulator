# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOST = (ROOT / "native-offline/src-tauri/src/azahar_host.mm").read_text()
OPTIONS = (ROOT / "native-offline/native-runtime/core/core_options.h").read_text()
PLAYER = (ROOT / "static/player.js").read_text()
ENTITLEMENTS = (ROOT / "native-offline/src-tauri/native-staging.entitlements").read_text()
TAURI_CONFIG = (ROOT / "native-offline/src-tauri/tauri.conf.json").read_text()
PACKAGE_SCRIPT = (ROOT / "native-offline/scripts/package-macos.sh").read_text()
RELEASE_TRAIN = (ROOT / "tools/release-train.sh").read_text()
WINDOWS_BUILD = (ROOT / "native-offline/scripts/build-windows-staging.ps1").read_text()
LINUX_BUILD = (ROOT / "native-offline/scripts/build-linux-staging.sh").read_text()


class NativeStagingContractTests(unittest.TestCase):
    def test_native_speed_and_audio_use_bounded_real_scheduler(self):
        for speed in ("0.5", "1.0", "2.0", "4.0", "8.0"):
            self.assertIn(speed, HOST)
        self.assertIn("std::min(runs, 8u)", HOST)
        self.assertIn("core_.run()", HOST)
        self.assertIn("sample_rate * multiplier", HOST)
        self.assertIn("AVAudioConverter", HOST)
        self.assertIn("g_audio_hardware_sample_rate", HOST)

    def test_autosave_is_separate_from_quick_slots(self):
        self.assertIn(".autosave.state", HOST)
        self.assertIn('"states"', HOST)
        self.assertIn("kMaxQuickStateSlot", HOST)
        self.assertIn("Quick-save slots range from 1 to 10.", HOST)
        self.assertIn("kNativeAutoSaveModeDefaultsKey", HOST)
        self.assertIn("parse_auto_save_mode", HOST)

    def test_core_options_are_announced_persisted_and_updated(self):
        self.assertIn("CoreOptionsRegistry", OPTIONS)
        self.assertIn("SET_VARIABLES", HOST)
        self.assertIn("SET_CORE_OPTIONS_V2", HOST)
        self.assertIn("SET_CORE_OPTIONS_V2_INTL", HOST)
        self.assertIn("GET_CORE_OPTIONS_VERSION", HOST)
        self.assertIn("GET_VARIABLE_UPDATE", HOST)
        self.assertIn("an3.native-core-option.", HOST)
        self.assertIn("restart to apply", HOST)

    def test_core_options_v2_uses_the_real_abi_and_never_parses_v2_intl_as_v1(self):
        # mGBA announces v2 options. Its layout has categorized description
        # and info fields before values; v2 international settings contain
        # v2 tables. A v1 cast makes AppKit read text as popup values.
        self.assertIn("desc_categorized", OPTIONS)
        self.assertIn("info_categorized", OPTIONS)
        self.assertIn("const RetroCoreOptionsV2* us", OPTIONS)
        self.assertIn("const RetroCoreOptionsV2* local", OPTIONS)
        intl = HOST[HOST.index("case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2_INTL:"):
                    HOST.index("case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:")]
        self.assertIn("capture_v2", intl)
        self.assertNotIn("capture_legacy", intl)

    def test_escape_precedence_and_compact_layout_are_explicit(self):
        capture = HOST.index("if (_capturing_key_map)")
        menu = HOST.index("if (!_menu_panel.hidden)", capture)
        cursor = HOST.index("if ([self isNds] && _cursor_locked)", menu)
        library = HOST.index("[self returnToLibrary:nil]", cursor)
        self.assertLess(capture, menu)
        self.assertLess(menu, cursor)
        self.assertLess(cursor, library)
        self.assertIn("const bool compact_controls = width < 600.0", HOST)
        self.assertIn("const CGFloat speed_y = compact_controls ? height - 78.0 : height - 44.0", HOST)
        self.assertIn("volume_row.leadingAnchor constraintEqualToAnchor:stack.leadingAnchor", HOST)
        self.assertIn("volume_row.trailingAnchor constraintEqualToAnchor:stack.trailingAnchor", HOST)
        self.assertIn("minimum_slider_width", HOST)
        self.assertIn("minValue:0.0 maxValue:100.0", HOST)
        self.assertIn('"In-game settings"', HOST)
        self.assertIn("Nine sections · changes are kept as a draft until you save.", HOST)
        self.assertIn("_settings_tabs.controlSize = NSControlSizeSmall", HOST)
        self.assertIn("_settings_save_status.trailingAnchor constraintLessThanOrEqualToAnchor", HOST)

    def test_web_3ds_debug_gate_requires_real_playable_milestones(self):
        for milestone in (
            "PLAYER_DOCUMENT_READY",
            "SECURE_CONTEXT_OK",
            "CROSS_ORIGIN_ISOLATED_OK",
            "SAB_AVAILABLE",
            "CORE_ASSET_REQUEST_START",
            "CORE_ASSET_REQUEST_COMPLETE",
            "ROM_REQUEST_START",
            "ROM_HEADERS_RECEIVED",
            "ROM_DOWNLOAD_COMPLETE",
            "EJS_LOADER_READY",
            "WASM_COMPILE_START",
            "CORE_LOAD_GAME_START",
            "CORE_LOAD_GAME_SUCCESS",
            "SOURCE_CANVAS_AVAILABLE",
            "FIRST_VIDEO_FRAME",
            "AUDIO_STARTED",
            "THREAD_POOL_READY",
        ):
            self.assertIn(f'"{milestone}"', PLAYER)
        self.assertIn("3DS did not reach a verified source canvas, first frame, and running audio output.", PLAYER)
        self.assertIn("EmulatorJS owns the streaming body", PLAYER)

    def test_staging_bundle_can_load_plugins_and_nds_jit(self):
        self.assertIn('"entitlements": "native-staging.entitlements"', TAURI_CONFIG)
        self.assertIn("com.apple.security.cs.disable-library-validation", ENTITLEMENTS)
        self.assertIn("com.apple.security.cs.allow-jit", ENTITLEMENTS)
        self.assertIn("--entitlements", PACKAGE_SCRIPT)

    def test_release_train_has_one_explicit_staging_only_entrypoint(self):
        self.assertIn('Usage: tools/release-train.sh --staging', RELEASE_TRAIN)
        self.assertIn('This release train is staging-only', RELEASE_TRAIN)
        self.assertIn('MACOS_DMG=FAILED', RELEASE_TRAIN)
        self.assertIn('ANDROID_APK=FAILED', RELEASE_TRAIN)
        for platform in ("macos", "android", "linux-deb", "linux-flatpak", "windows", "web"):
            self.assertIn(platform, RELEASE_TRAIN)
        self.assertIn('refusing a browser-only package', LINUX_BUILD)
        self.assertIn('WINDOWS_EXE=BLOCKED', WINDOWS_BUILD)
        self.assertIn('VULKAN_SDK', WINDOWS_BUILD)
        self.assertIn('AN3_RELEASE_DIR', WINDOWS_BUILD)
        self.assertIn('--coordinated', RELEASE_TRAIN)
        self.assertIn('SOURCE_FROZEN_MANIFEST', RELEASE_TRAIN)
        self.assertIn('AN3_REQUIRE_DEPENDENCY_CACHE=1', RELEASE_TRAIN)


if __name__ == "__main__":
    unittest.main()
