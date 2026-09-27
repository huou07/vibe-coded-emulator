# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Guard removed network/account features and preserve local input paths."""

import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import app


ROOT = Path(__file__).resolve().parents[1]
TAURI = ROOT / "native-offline" / "src-tauri"
ANDROID = TAURI / "gen" / "android" / "app"
ANDROID_JAVA = ANDROID / "src" / "main" / "java" / "space" / "an3tocom" / "offline"


class RemovedNetworkProductSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="an3-core-only-")
        root = self.temp.name
        self.patches = [
            patch.object(app, "DATA_DIR", root),
            patch.object(app, "DB_PATH", os.path.join(root, "arcade.db")),
            patch.object(app, "ROM_DIR", os.path.join(root, "roms")),
            patch.object(app, "COVER_DIR", os.path.join(root, "covers")),
            patch.object(app, "SCREENSHOT_DIR", os.path.join(root, "screenshots")),
            patch.object(app, "CUSTOM_DIR", os.path.join(root, "custom")),
            patch.object(app, "EMULATOR_CACHE_DIR", os.path.join(root, "emulatorjs-cache")),
            patch.object(app, "PREPARED_ROM_DIR", os.path.join(root, "prepared-roms")),
        ]
        for active in self.patches:
            active.start()
        app.init_db()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        for active in self.patches:
            active.stop()
        self.temp.cleanup()

    def request(self, method, path, payload=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if body else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        status, data = response.status, response.read()
        connection.close()
        return status, data

    def test_legacy_sync_and_phone_controller_routes_are_absent(self):
        paths = (
            ("GET", "/sync"),
            ("GET", "/api/sync/settings"),
            ("POST", "/api/sync/plan"),
            ("POST", "/api/sync/resolve"),
            ("POST", "/api/sync/lan/announce"),
            ("GET", "/api/sync/lan/peers"),
            ("POST", "/api/sync/lan/publish"),
            ("GET", "/api/sync/lan/manifest?kind=save"),
            ("GET", "/api/sync/lan/blob?kind=save&key=old&hash=" + "a" * 64),
            ("GET", "/controller"),
            ("GET", "/controller/join"),
            ("POST", "/api/controller/session"),
            ("POST", "/api/controller/pair"),
            ("POST", "/api/controller/state"),
            ("GET", "/api/controller/state?code=ABC123&hostToken=unused"),
            ("POST", "/api/controller/ack"),
            ("GET", "/api/controller/link?code=ABC123&token=unused"),
            ("GET", "/api/controller/hosts"),
        )
        for method, path in paths:
            with self.subTest(method=method, path=path):
                status, _body = self.request(method, path, {} if method == "POST" else None)
                self.assertEqual(status, 404)

    def test_account_login_and_cloud_runtime_are_absent(self):
        paths = (
            ("GET", "/login"),
            ("GET", "/register"),
            ("GET", "/account"),
            ("GET", "/api/account/session"),
            ("POST", "/api/register"),
            ("POST", "/api/login"),
            ("POST", "/api/logout"),
            ("POST", "/api/account/peer-proof"),
        )
        for method, path in paths:
            with self.subTest(method=method, path=path):
                status, _body = self.request(method, path, {} if method == "POST" else None)
                self.assertEqual(status, 404)

        self.assertFalse((ROOT / "sync_engine.py").exists())
        self.assertFalse((ROOT / "google_sync.py").exists())
        self.assertFalse((ROOT / "native-offline" / "web" / "native-account.js").exists())
        self.assertFalse((ANDROID / "src" / "main" / "assets" / "native-account.js").exists())
        netcode = (ROOT / "netcode.py").read_text(encoding="utf-8")
        site_js = (ROOT / "static" / "site.js").read_text(encoding="utf-8")
        environment_example_path = ROOT / "tools" / "publication" / ".env.example"
        if not environment_example_path.is_file():
            environment_example_path = ROOT / ".env.example"
        environment_example = environment_example_path.read_text(encoding="utf-8")
        self.assertNotIn("sync_engine", netcode)
        self.assertNotIn("/api/login", site_js)
        self.assertNotIn("/api/account/", site_js)
        self.assertNotIn("authForm", site_js)
        for retired_setting in ("AN3_AUTH_PEPPER", "AN3_ADMIN_NAME", "AN3_ADMIN_PASSWORD", "AN3_GOOGLE_CLIENT_ID"):
            self.assertNotIn(retired_setting, environment_example)

    def test_cms_analytics_and_upload_runtime_are_absent(self):
        paths = (
            ("GET", "/admin"),
            ("GET", "/admin/game/1"),
            ("GET", "/api/admin/system-metrics"),
            ("POST", "/admin/api/games"),
            ("POST", "/admin/api/games/1/uploads"),
            ("POST", "/admin/api/uploads/abcdefghijklmnop/complete"),
            ("PUT", "/admin/api/uploads/abcdefghijklmnop/0"),
            ("DELETE", "/admin/api/games/1"),
        )
        for method, path in paths:
            with self.subTest(method=method, path=path):
                status, _body = self.request(method, path, {} if method in {"POST", "PUT", "DELETE"} else None)
                self.assertEqual(status, 404)

        with app.db() as conn:
            tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"games", "game_screenshots", "game_updates", "bug_reports", "support_capabilities"} <= tables)
        self.assertFalse({"ratings", "comments", "favorites", "reports", "page_views", "play_events", "download_events", "upload_sessions"} & tables)

        source = (ROOT / "app.py").read_text(encoding="utf-8")
        site_js = (ROOT / "static" / "site.js").read_text(encoding="utf-8")
        self.assertNotIn("system_metrics", source)
        self.assertNotIn("dashboard_analytics", source)
        self.assertNotIn("upload_sessions", source)
        for retired_port in ("47831", "47832", "47833"):
            self.assertNotIn(retired_port, source)
        self.assertNotIn("adminMonitoring", site_js)
        self.assertNotIn("/api/admin/", site_js)
        self.assertNotIn("batchStatusForm", site_js)
        stylesheet = (ROOT / "static" / "site.css").read_text(encoding="utf-8")
        for retired_selector in (".admin-shell", ".admin-page", "#toast", ".auth-shell", ".account-page", ".rating-large", ".comments", ".reference-chart-section", ".welcome-panel"):
            self.assertNotIn(retired_selector, stylesheet)

    def test_public_catalog_page_renders_without_rating_or_play_analytics(self):
        with app.db() as conn:
            conn.execute(
                "INSERT INTO games(slug,title_vi,title_en,system,published,rom_path,created_at,updated_at) "
                "VALUES('core-game','Core game','Core game','gba',1,'core.gba',1,1)"
            )
        with patch.object(app, "ENVIRONMENT", "staging"):
            status, body = self.request("GET", "/games")
        self.assertEqual(status, 200)
        self.assertIn(b"Core game", body)
        self.assertNotIn(b"Recommended for you", body)

    def test_publication_workflows_use_core_only_checks(self):
        workflows = ROOT / ".github" / "workflows"
        if not workflows.is_dir():
            workflows = ROOT / "tools" / "publication" / ".github" / "workflows"
        ci = (workflows / "ci.yml").read_text(encoding="utf-8")
        native = (workflows / "native-build.yml").read_text(encoding="utf-8")
        self.assertIn("python3 -m py_compile app.py bug_report.py netcode.py qrcodegen.py", ci)
        for retired in ("sync_engine.py", "google_sync.py", "3.3.1-performance-candidate"):
            self.assertNotIn(retired, ci)
        self.assertIn("'core-only/**'", ci)
        self.assertIn("'core-only/**'", native)
        self.assertIn("NativeInputActionsTest", native)
        self.assertIn("NativeSettingsTabsTest", native)
        for retired in (
            "ControllerSendQueueTest",
            "lan_host::tests::direct_transport_executes_canonical_utility_frames",
            "android-sync-status",
            "ANDROID_SYNC=",
        ):
            self.assertNotIn(retired, native)

    def test_phone_controller_native_modules_commands_and_permissions_are_removed(self):
        lib = (TAURI / "src" / "lib.rs").read_text(encoding="utf-8")
        build = (TAURI / "build.rs").read_text(encoding="utf-8")
        source = "\n".join(path.read_text(encoding="utf-8") for path in (TAURI / "src").glob("*.rs"))
        app_js = (ROOT / "native-offline" / "web" / "native-app.js").read_text(encoding="utf-8")
        bootstrap = (ROOT / "native-offline" / "web" / "native-bootstrap.js").read_text(encoding="utf-8")
        index = (ROOT / "native-offline" / "web" / "index.html").read_text(encoding="utf-8")
        player_js = (ROOT / "static" / "player.js").read_text(encoding="utf-8")
        player_page = (ROOT / "app.py").read_text(encoding="utf-8")
        capabilities = json.loads((TAURI / "capabilities" / "default.json").read_text(encoding="utf-8"))
        android_capabilities = json.loads((TAURI / "capabilities" / "android.json").read_text(encoding="utf-8"))

        for module in ("controller_host", "controller_utility_queue", "host_actions", "lan_peer", "lan_host", "latency"):
            self.assertFalse((TAURI / "src" / f"{module}.rs").exists(), module)
        self.assertNotIn("native_controller", source)
        self.assertNotIn("native_latency", source)
        self.assertNotIn("set_native_input", source)
        self.assertNotIn("controller_host", lib)
        self.assertNotIn("lan_host", lib)
        self.assertNotIn("native_controller", build)
        self.assertNotIn("native_latency", build)
        self.assertNotIn("set_native_input", build)
        self.assertNotIn("AN3NativeController", app_js + bootstrap)
        self.assertNotIn("nativeControllerCard", app_js + index)
        self.assertNotIn("settings-tab-controller", index)
        self.assertNotIn("controllerEnabled", player_page + player_js)
        self.assertNotIn("ctrlPhonePanel", player_page)
        for permissions in (capabilities["permissions"], android_capabilities["permissions"]):
            self.assertFalse(any("native-controller" in item or "native-latency" in item for item in permissions))
            self.assertNotIn("allow-set-native-input", permissions)

        manifest = (ANDROID / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")
        main_activity = (ANDROID_JAVA / "MainActivity.kt").read_text(encoding="utf-8")
        self.assertNotIn("ControllerHostService", manifest)
        self.assertNotIn("ACCESS_WIFI_STATE", manifest)
        self.assertNotIn("CHANGE_WIFI_MULTICAST_STATE", manifest)
        self.assertNotIn("WifiManager", main_activity)
        for old_port in ("47831", "47832", "47833"):
            self.assertNotIn(old_port, source + player_page)

    def test_generated_tauri_permission_schemas_match_active_commands(self):
        schema_dir = TAURI / "gen" / "schemas"
        manifest = json.loads((schema_dir / "acl-manifests.json").read_text(encoding="utf-8"))
        expected = set(manifest["__app-acl__"]["permissions"])
        prefixes = (
            "allow-native", "deny-native", "allow-start-native", "deny-start-native",
            "allow-stop-native", "deny-stop-native", "allow-set-native", "deny-set-native",
            "allow-pick-and-import-native", "deny-pick-and-import-native",
            "allow-remove-native", "deny-remove-native", "allow-switch-companion",
            "deny-switch-companion", "allow-ui-control", "deny-ui-control",
        )

        def constants(value):
            if isinstance(value, dict):
                found = {value["const"]} if isinstance(value.get("const"), str) else set()
                for child in value.values():
                    found.update(constants(child))
                return found
            if isinstance(value, list):
                found = set()
                for child in value:
                    found.update(constants(child))
                return found
            return set()

        for name in ("desktop-schema.json", "macOS-schema.json", "mobile-schema.json", "android-schema.json"):
            with self.subTest(schema=name):
                schema = json.loads((schema_dir / name).read_text(encoding="utf-8"))
                current = {item for item in constants(schema) if item.startswith(prefixes)}
                self.assertEqual(current, expected)
                self.assertNotRegex(json.dumps(schema), r"native[-_](?:sync|controller|latency)")

    def test_local_keyboard_gamepad_and_android_touch_input_survive(self):
        native_app = (ROOT / "native-offline" / "web" / "native-app.js").read_text(encoding="utf-8")
        game_activity = (ANDROID_JAVA / "NativeGameActivity.kt").read_text(encoding="utf-8")
        game_overlay = (ANDROID_JAVA / "NativeGameOverlay.kt").read_text(encoding="utf-8")
        circular = (ANDROID_JAVA / "NativeCircularDpad.kt").read_text(encoding="utf-8")
        mac_host = (TAURI / "src" / "azahar_host.mm").read_text(encoding="utf-8")
        runtime = (ROOT / "native-offline" / "native-runtime" / "platform" / "linux" / "linux_runtime.cpp").read_text(encoding="utf-8")

        self.assertIn("NativeCircularDpad(activity)", game_overlay)
        self.assertIn("surface.setOnTouchListener", game_activity)
        self.assertIn("override fun onKeyDown", game_activity)
        self.assertIn("override fun onKeyUp", game_activity)
        self.assertIn("override fun onGenericMotionEvent", game_activity)
        self.assertIn("gameButton(", game_activity)
        self.assertIn("handleLocalMenuButtons", mac_host)
        self.assertIn("local_input_buttons()", mac_host)
        self.assertIn("SDL_PollEvent", runtime)
        self.assertNotIn('controllerSender.', native_app)

    def test_android_game_toolbar_save_menu_keeps_manual_and_auto_slots(self):
        game_overlay = (ANDROID_JAVA / "NativeGameOverlay.kt").read_text(encoding="utf-8")
        self.assertIn("private val saveButton = button(NativePlayerUi.SAVE_LABEL) { showSaveMenu() }", game_overlay)
        self.assertIn("private fun showSaveMenu()", game_overlay)
        self.assertIn('NativePlayerUi.QUICK_SAVE_LABEL + "…"', game_overlay)
        self.assertIn('NativePlayerUi.QUICK_LOAD_LABEL + "…"', game_overlay)
        self.assertIn('2 -> send("save", "auto")', game_overlay)
        self.assertIn('else -> send("load", "auto")', game_overlay)

    def test_phone_casting_is_removed_but_local_player_and_multiplayer_remain(self):
        player = (ROOT / "static" / "player.js").read_text(encoding="utf-8")
        offline = (ROOT / "static" / "offline.js").read_text(encoding="utf-8")
        player_page = (ROOT / "app.py").read_text(encoding="utf-8")
        site_css = (ROOT / "static" / "site.css").read_text(encoding="utf-8")
        native_index = (ROOT / "native-offline" / "web" / "index.html").read_text(encoding="utf-8")

        for source in (player, offline, player_page, site_css):
            for removed in ("castScreen", "watchAvailability", "tv-console-mode", "castConsoleAutoPad"):
                self.assertNotIn(removed, source)
        for removed_asset in ("/static/input-actions.js", "/static/controller-utility.js", "/controller-sender.js"):
            self.assertNotIn(removed_asset, native_index)

        self.assertIn("const mpEnsureNetplay = () =>", player)
        self.assertIn('netplay.openRoom(code, 2, "")', player)
        self.assertIn('netplay.joinRoom(key, data.code)', player)
        self.assertIn('document.getElementById("editPad")?.addEventListener("click"', player)
        self.assertIn('touchToggle?.addEventListener("click",togglePad)', player)
        self.assertIn("  boot();", player)

    def test_packaged_android_web_assets_have_no_phone_controller_files(self):
        assets = ANDROID / "src" / "main" / "assets"
        for obsolete in (
            "controller-sender.js",
            "static/controller.js",
            "static/controller-utility.js",
            "static/input-actions.js",
        ):
            self.assertFalse((assets / obsolete).exists(), obsolete)
        web_files = ("index.html", "native-app.js", "native-bootstrap.js", "native-support.js", "native.css")
        static_files = ("offline.js", "player.js", "site.js", "site.css")
        for current in web_files:
            packaged = (assets / current).read_bytes()
            source = (ROOT / "native-offline" / "web" / current).read_bytes()
            if current == "index.html":
                version = json.loads((ROOT / "native-offline" / "package.json").read_text(encoding="utf-8"))["version"]
                source = source.replace(b"__AN3_VERSION__", version.encode()).replace(b"__AN3_SUPPORT_ORIGIN__", b"")
            self.assertEqual(packaged, source, current)
        for current in static_files:
            self.assertEqual((assets / "static" / current).read_bytes(), (ROOT / "static" / current).read_bytes(), current)

    def test_local_rom_catalog_and_save_recovery_remain(self):
        lib = (TAURI / "src" / "lib.rs").read_text(encoding="utf-8")
        build = (TAURI / "build.rs").read_text(encoding="utf-8")
        source = (ROOT / "native-offline" / "src-tauri" / "src" / "native_rom_library.rs").read_text(encoding="utf-8")
        web_server = (ROOT / "app.py").read_text(encoding="utf-8")
        offline = (ROOT / "static" / "offline.js").read_text(encoding="utf-8")

        self.assertIn("native_rom_library_manifest", lib)
        self.assertIn('"native_rom_library_manifest"', build)
        self.assertIn("native_rom_library::manifest", lib)
        self.assertIn('invoke("native_rom_library_manifest",{})', offline)
        self.assertIn("pub fn manifest(app_dir", source)
        self.assertIn('versioned_player_asset("local-save-recovery.js")', web_server)


if __name__ == "__main__":
    unittest.main()
