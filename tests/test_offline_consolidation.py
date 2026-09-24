# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import pathlib
import sys
import unittest
import io
import re
import zipfile
import subprocess
import json


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app


OFFLINE_JS = (ROOT / "static" / "offline.js").read_text(encoding="utf-8")
PLAYER_JS = (ROOT / "static" / "player.js").read_text(encoding="utf-8")


class OfflineConsolidationTests(unittest.TestCase):
    def test_offline_is_the_single_pwa_surface(self):
        source = pathlib.Path(app.__file__).read_text(encoding="utf-8")
        # The web /offline page is now a minimal connection notice; the local
        # ROM library lives only in the installed AN3 app.
        self.assertIn('class="offline-notice"', source)
        self.assertNotIn('id="offlineGameForm"', source)
        self.assertNotIn('id="offlineShortcut"', source)
        self.assertIn('versioned_player_asset("player.js")', source)
        self.assertIn('path == "/offline-app-service-worker.js"', source)
        self.assertIn('self.registration.unregister()', source)
        self.assertNotIn('def offline_app_page', source)
        self.assertFalse((ROOT / "static" / "offline-app.js").exists())
        # The native app keeps the local-ROM import library and app shell.
        native = (ROOT / "native-offline" / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="offlineGameForm"', native)
        self.assertIn('id="offlineGameGrid"', native)
        self.assertIn('/native-app.js', native)

    def test_shortcut_action_saves_the_supported_pwa_before_prompting(self):
        self.assertIn('const setupOfflineShortcut = () =>', OFFLINE_JS)
        self.assertIn('await ensureOfflineRuntime();', OFFLINE_JS)
        self.assertIn('await updateReadiness();', OFFLINE_JS)
        self.assertIn('beforeinstallprompt', OFFLINE_JS)
        self.assertIn('deferredPrompt.prompt()', OFFLINE_JS)
        self.assertIn('Chrome/Edge', OFFLINE_JS)

    def test_3ds_uses_the_supported_azahar_core_and_has_separate_touch_pad(self):
        self.assertIn('"3ds":"azahar"', OFFLINE_JS)
        self.assertIn('const threeDsPad = config.system === "3ds";', PLAYER_JS)
        self.assertIn('["gba", "gb", "nds", "3ds"].includes(config.system)', PLAYER_JS)
        self.assertIn('const protectThreeDsCanvas = () =>', PLAYER_JS)
        self.assertIn('const bindThreeDsTouch = canvas =>', PLAYER_JS)
        self.assertIn('dispatchNdsMouse(canvas,"mousedown",event,1)', PLAYER_JS)
        self.assertIn('if(ndsPad || threeDsPad)controls.push', PLAYER_JS)
        self.assertIn('const localization = config.lang === "en" ? "en-US.json" : "vi-VN.json";', PLAYER_JS)
        self.assertIn('const localizationRoot = configuredOrigin ? `${configuredOrigin}/stable/data/` : "/emulatorjs/stable/data/";', PLAYER_JS)
        self.assertIn('window.EJS_language = emulatorLanguage;', PLAYER_JS)

    def test_native_player_keeps_the_requested_performance_defaults(self):
        self.assertIn('vsync:"disabled"', PLAYER_JS)
        self.assertIn('melonds_audio_bitrate:"16-bit"', PLAYER_JS)
        self.assertIn('keyboardInput:"enabled"', PLAYER_JS)
        self.assertIn('window.EJS_disableLocalStorage = ndsPad || threeDsPad;', PLAYER_JS)

    def test_library_never_blocks_a_playable_card_and_repairs_missing_native_roms(self):
        # No browser-only lock may be added back: the only remaining gate is the
        # Android capability declaration, and a missing copied ROM offers a
        # one-tap re-import instead of a dead end.
        self.assertNotIn('browserThreeDsUnavailable', OFFLINE_JS)
        self.assertNotIn('threeDsUnavailable', OFFLINE_JS)
        self.assertIn('play.disabled=game.system==="html5"||androidThreeDsUnavailable(game.system);', OFFLINE_JS)
        self.assertIn('data-repair-native', OFFLINE_JS)
        self.assertIn('repairNativeRom', OFFLINE_JS)
        # The native launch carries the recorded byte size so the Android side
        # can recover a ROM whose stored id no longer matches its file.
        self.assertIn('return launch(romId,game.system,"preserve",game.size);', OFFLINE_JS)
        bootstrap = (ROOT / "native-offline" / "web" / "native-bootstrap.js").read_text(encoding="utf-8")
        self.assertIn('bridge.launchNativeSized(romId, system, expectedSize)', bootstrap)
        activity = (ROOT / "native-offline" / "src-tauri" / "gen" / "android" / "app" / "src" / "main" / "java" / "space" / "an3tocom" / "offline" / "MainActivity.kt").read_text(encoding="utf-8")
        self.assertIn('fun launchNativeSized(romId: String, system: String, expectedSize: Long)', activity)
        self.assertIn('file.length() == expectedSize', activity)

    def test_offline_player_exposes_the_shared_directional_control_choice(self):
        # The offline shell must let the player choose D-Pad or the shared
        # analog joystick. Without the select control, AN3PlayerUI loaded but
        # the joystick could never be enabled from the offline library.
        self.assertIn('<select id="padDirectionalControl">', OFFLINE_JS)
        self.assertIn('<option value="joystick">Analog Joystick</option>', OFFLINE_JS)
        self.assertIn('addAnalogStick(controls[0])', PLAYER_JS)
        self.assertIn('padRoot.classList.toggle("analog-mode"', PLAYER_JS)
        # The shared model stays the single source of joystick geometry.
        self.assertIn('ui.model.joystick.thumbRadiusRatio', PLAYER_JS)
        self.assertIn('ui.model.joystick.travelRatio', PLAYER_JS)

    def test_native_import_classifies_supported_roms_and_preserves_content_suffixes(self):
        native_source = (ROOT / "native-offline" / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")
        self.assertIn('fn native_system_from_extension(extension: &str)', native_source)
        self.assertIn('pub(crate) const NATIVE_3DS_FILE_EXTENSIONS', native_source)
        self.assertIn('fn native_system_from_header(source: &Path, file_size: u64)', native_source)
        self.assertIn('ZIP archives and CIA install packages are not playable in the in-app native player.', native_source)
        self.assertNotIn('fn native_system_from_zip(source: &Path, file_size: u64)', native_source)
        self.assertIn('url: format!("/_an3/rom/{rom_id}.{extension}")', native_source)
        self.assertIn('system: Some(system.to_owned())', native_source)
        self.assertIn('path == "index.html" || path == "native-bootstrap.js" || path.starts_with("static/")', native_source)
        self.assertIn('const system=typeof imported.system==="string"&&systems[imported.system]?imported.system:await inferFile({name:imported.name});', OFFLINE_JS)
        self.assertIn('return `${nativeUrl}.${extension}`;', OFFLINE_JS)

    def test_native_gba_nds_and_3ds_offer_unified_control_routes(self):
        self.assertIn('const nativeIntegratedLauncher = () => {', OFFLINE_JS)
        # Native launch must not derive a new portrait default from transient
        # browser geometry; the host restores the protected per-system layout.
        self.assertIn('invoke("start_native_game",{romId,system,layout:layout||"preserve"})', OFFLINE_JS)
        self.assertNotIn('invoke("launch_native_3ds"', OFFLINE_JS)
        self.assertIn('const nativeRomIdForGame = game => {', OFFLINE_JS)
        self.assertIn('Imported records from older native builds predate `nativeRomId`', OFFLINE_JS)
        # Every imported ROM on the native app resolves to its own record id,
        # and no front-end lock refuses a ROM because of its size.
        self.assertIn('if(nativeOfflineApp && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(recordId)) return recordId;', OFFLINE_JS)
        self.assertNotIn('embeddedThreeDsLimit', OFFLINE_JS)
        self.assertNotIn('ROM 3DS lớn cần engine native', OFFLINE_JS)
        self.assertIn('Azahar native chạy trong VibeCodedEmulator với Menu → phím ảo → cảm ứng → bàn phím.', OFFLINE_JS)
        self.assertIn('Bấm màn hình game để khóa con trỏ cho cảm ứng; Esc nhả con trỏ', OFFLINE_JS)
        bootstrap = (ROOT / "native-offline" / "web" / "native-bootstrap.js").read_text(encoding="utf-8")
        # No Android front-end redirect may hijack a requested play session.
        self.assertNotIn('request.has("play")', bootstrap)
        # Exercise each shell branch; Android now consumes the portable host.
        script = r"""
const vm = require('node:vm');
const source = JSON.parse(process.argv[1]);
const result = ['Android', 'Macintosh', 'iPhone'].map(userAgent => {
  const context = {window: {}, navigator: {userAgent}, location: {search: '', pathname: '/index.html'}, URLSearchParams};
  vm.runInNewContext(source, context);
  return context.window.AN3NativeIntegratedSystems;
});
console.log(JSON.stringify(result));
"""
        systems = json.loads(subprocess.check_output(['node', '-e', script, json.dumps(bootstrap)], text=True))
        self.assertEqual(systems, [["gba", "nds", "3ds", "switch"], ["gba", "nds", "3ds"], []])
        self.assertIn('window.AN3NativeLaunchGame = (romId, system, layout) => {', bootstrap)
        self.assertNotIn('AN3AndroidLaunchThreeDs', bootstrap)
        self.assertIn('const androidThreeDsUnavailable = system =>', OFFLINE_JS)
        self.assertIn('3DS is unavailable on Android in this build.', OFFLINE_JS)
        native_host = (ROOT / "native-offline" / "src-tauri" / "src" / "azahar_host.mm").read_text(encoding="utf-8")
        self.assertIn('Option + arrows: Circle Pad.', native_host)
        self.assertIn('default: [40,360) x [240,480); side by side: [400,720) x [0,240).', native_host)
        self.assertIn('CGAssociateMouseAndMouseCursorPosition(false)', native_host)
        self.assertIn('Cursor locked · Esc', native_host)
        self.assertIn('system_ == "nds"', native_host)
        self.assertIn('vulkan_.initialize_software', native_host)

    def test_large_local_roms_use_opfs_handles_instead_of_picker_files(self):
        self.assertIn('navigator.storage?.getDirectory', OFFLINE_JS)
        self.assertIn('getDirectoryHandle("an3-arcade-roms",{create:true})', OFFLINE_JS)
        self.assertIn('const getFile = async id => {', OFFLINE_JS)
        self.assertIn('window.AN3OfflineLibrary', OFFLINE_JS)
        self.assertIn('list:all', OFFLINE_JS)
        self.assertIn('put', OFFLINE_JS)
        self.assertIn('const playableThreeDsFile = async file => {', OFFLINE_JS)
        self.assertIn('const browserArrayBufferLimit=2**31;', OFFLINE_JS)
        self.assertIn('String.fromCharCode(...header.slice(0x100,0x104))!=="NCSD"', OFFLINE_JS)
        self.assertIn('return new File([file.slice(0,payloadEnd)]', OFFLINE_JS)
        self.assertIn('const file = await window.AN3OfflineLibrary?.getFile?.(config.offlineId);', PLAYER_JS)
        self.assertNotIn('return new File([local.file]', PLAYER_JS)

    def test_native_offline_shell_is_isolated_from_web_routes_and_release_secrets(self):
        source = pathlib.Path(app.__file__).read_text(encoding="utf-8")
        native_root = ROOT / "native-offline"
        self.assertTrue((native_root / "src-tauri" / "Cargo.toml").is_file())
        self.assertTrue((native_root / "web" / "index.html").is_file())
        self.assertTrue((native_root / "src-tauri" / "gen" / "android").is_dir())
        self.assertIn('window.AN3NativeOfflineApp = true', (native_root / "web" / "native-bootstrap.js").read_text(encoding="utf-8"))
        native_index = (native_root / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('/static/offline.js?v=', native_index)
        self.assertIn('/static/player-runtime.js?v=', native_index)
        self.assertIn('/static/nds-touch.js?v=', native_index)
        self.assertIn('/static/player.js?v=', native_index)
        capabilities = (native_root / "src-tauri" / "capabilities" / "default.json").read_text(encoding="utf-8")
        self.assertIn('"allow-start-native-game"', capabilities)
        self.assertIn('"allow-stop-native-game"', capabilities)
        self.assertIn('"allow-set-native-input"', capabilities)
        self.assertNotIn('"allow-launch-native-3ds"', capabilities)
        # Every Tauri command must be allowed by the capability ACL and listed in
        # build.rs's AppManifest, or the WebView gets "Command ... not allowed by
        # ACL" at runtime. Commands may be defined in lib.rs or a helper module.
        command_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((native_root / "src-tauri" / "src").glob("*.rs"))
        )
        commands = re.findall(r"#\[tauri::command\]\s*(?:pub\s+)?(?:async\s+)?fn\s+([a-z0-9_]+)", command_sources)
        self.assertIn("native_controller_status", commands)
        build_rs = (native_root / "src-tauri" / "build.rs").read_text(encoding="utf-8")
        manifest = build_rs[build_rs.index(".commands(&["):]
        manifest = manifest[:manifest.index("]")]
        declared = re.findall(r'"([a-z0-9_]+)"', manifest)
        self.assertEqual(sorted(declared), sorted(commands), "build.rs commands must match the #[tauri::command] set")
        for command in commands:
            permission = "allow-" + command.replace("_", "-")
            self.assertIn(f'"{permission}"', capabilities, f"capability missing {permission}")
        self.assertIn('const nativeOfflineApp = globalThis.AN3NativeOfflineApp === true;', OFFLINE_JS)
        self.assertIn('const configuredOrigin=typeof config.emulatorOrigin', PLAYER_JS)
        self.assertIn('def native_offline_source_bundle():', source)
        archive = app.native_offline_source_bundle()
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            names = bundle.namelist()
        self.assertIn("an3-offline-native/src-tauri/Cargo.toml", names)
        self.assertIn("an3-offline-native/src-tauri/gen/android/gradlew", names)
        self.assertFalse(any("/.signing/" in name or "/releases/" in name or "/target/" in name or name.endswith("local.properties") for name in names))

    def test_library_render_discards_a_stale_async_snapshot(self):
        # A slow older read must never overwrite a newer render, or an
        # out-of-order IndexedDB resolution can drop whole system sections (the
        # intermittent "only NDS" library).
        self.assertIn("const libraryRenderState = {generation: 0};", OFFLINE_JS)
        self.assertIn("const generation=beginLibraryRender();", OFFLINE_JS)
        self.assertIn(
            "const games=await all();\n      if(!isCurrentLibraryRender(generation))return;",
            OFFLINE_JS,
        )
        # The generated Android mirror must carry the same guard.
        mirror = (ROOT / "native-offline/src-tauri/gen/android/app/src/main/assets/static/offline.js").read_text(encoding="utf-8")
        self.assertIn("if(!isCurrentLibraryRender(generation))return;", mirror)


if __name__ == "__main__":
    unittest.main()
