#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import http.client
import hashlib
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.py")
# Production is download-first and intentionally does not serve the public
# server-ROM library. Library routes are exercised against a staging server on
# its own port so both contracts keep live coverage instead of one test
# environment silently disabling the other.
PRODUCTION_PORT = 18791
LIBRARY_PORT = 18792
MULTIPLAYER_PORT = 18793
PORT = PRODUCTION_PORT
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class Client:
    def __init__(self, port=PRODUCTION_PORT):
        self.cookie = ""
        self.port = port

    def raw(self, method, path, body=None, headers=None):
        request_headers = {"Accept": "application/json"}
        if self.cookie:
            request_headers["Cookie"] = self.cookie
        request_headers.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=12)
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        raw = response.read()
        set_cookie = response.getheader("Set-Cookie")
        if set_cookie and "an3_session=" in set_cookie:
            self.cookie = set_cookie.split(";", 1)[0]
        connection.close()
        return response.status, dict(response.getheaders()), raw

    def request(self, method, path, payload=None, headers=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request_headers = {"Content-Type": "application/json"} if body is not None else {}
        request_headers.update(headers or {})
        return self.raw(method, path, body, request_headers)

    def csrf(self, path="/"):
        status, _, body = self.request("GET", path)
        token = re.search(rb'<meta name="csrf-token" content="([^"]*)">', body)
        if status != 200 or not token:
            raise AssertionError("csrf token unavailable")
        return token.group(1).decode()

    def post(self, path, payload, csrf=None):
        headers = {"X-CSRF-Token": csrf} if csrf else {}
        status, _, body = self.request("POST", path, payload, headers)
        return status, json.loads(body.decode("utf-8"))

    def upload(self, path, payload, csrf):
        status, _, body = self.raw("PUT", path, payload, {"X-CSRF-Token": csrf, "Content-Type": "application/octet-stream"})
        return status, json.loads(body.decode("utf-8"))


class SystemInferenceTests(unittest.TestCase):
    def test_native_artifact_manifest_fails_closed_on_integrity_drift(self):
        import app
        with tempfile.TemporaryDirectory(prefix="an3-artifacts-") as root:
            filename = "verified-1.0-test.bin"
            path = os.path.join(root, filename)
            payload = b"verified artifact bytes"
            with open(path, "wb") as handle:
                handle.write(payload)
            original_dir = app.NATIVE_OFFLINE_RELEASE_DIR
            original_catalog = app.NATIVE_RELEASE_CATALOG
            app.NATIVE_OFFLINE_RELEASE_DIR = root
            app.NATIVE_RELEASE_CATALOG = ({
                "version": "1.0", "platform": "Test", "architecture": "test", "format": "BIN",
                "filename": filename, "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
                "signature_status": "verified", "runtime_status": "passed",
            },)
            try:
                artifact = app.native_artifact_manifest()["artifacts"][0]
                self.assertEqual(artifact["status"], "available")
                self.assertEqual(artifact["download_url"], f"/download-app/release/{filename}?sha256={artifact['sha256']}")
                self.assertTrue(artifact["build_timestamp"].endswith("Z"))
                with open(path, "ab") as handle:
                    handle.write(b"drift")
                artifact = app.native_artifact_manifest()["artifacts"][0]
                self.assertEqual(artifact["status"], "blocked")
                self.assertIsNone(artifact["download_url"])
                self.assertIsNone(app.published_native_release(filename))
            finally:
                app.NATIVE_OFFLINE_RELEASE_DIR = original_dir
                app.NATIVE_RELEASE_CATALOG = original_catalog

    def test_current_staging_catalog_names_only_the_current_verified_installers(self):
        import app
        available = [item for item in app.NATIVE_RELEASE_CATALOG if item["filename"]]
        self.assertEqual(
            [item["filename"] for item in available],
            [
                "vibecodedemulator-2.2.0-macos-aarch64.dmg",
                "vibecodedemulator-2.2.0-android-arm64-staging.apk",
                "vibecodedemulator-2.2.0-linux-amd64.deb",
                "an3-offline-2.2.0-linux-amd64-staging.flatpak",
                "vibecodedemulator-2.2.0-windows-x64-staging.exe",
            ],
        )
        self.assertEqual(
            {item["format"]: item["version"] for item in available},
            {"DMG": "2.2.0", "APK": "2.2.0", "DEB": "2.2.0", "Flatpak": "2.2.0", "EXE": "2.2.0"},
        )
        self.assertTrue(all(item["size"] and item["sha256"] for item in available))

    def test_unique_extensions_hints_and_archives(self):
        import app
        cases = {
            "Pokemon Emerald.gba": "gba",
            "Pokemon Platinum.nds": "nds",
            "Zelda.3ds": "3ds",
            "Mario Kart.z64": "n64",
            "Final Fantasy-psx.chd": "psx",
            "God-of-War-psp.iso": "psp",
            "Sonic-megadrive.bin": "segaMD",
        }
        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                self.assertEqual(app.infer_system(filename), expected)
        self.assertIsNone(app.infer_system("ambiguous.iso"))
        with tempfile.NamedTemporaryFile(suffix=".zip") as archive:
            with zipfile.ZipFile(archive.name, "w") as zf:
                zf.writestr("roms/game.nds", b"nds")
                zf.writestr("readme.txt", b"test")
            self.assertEqual(app.infer_system("bundle.zip", archive.name), "nds")
        with tempfile.NamedTemporaryFile(suffix=".zip") as archive:
            with zipfile.ZipFile(archive.name, "w") as zf:
                zf.writestr("web/index.html", "<!doctype html>")
            self.assertEqual(app.infer_system("browser-game.zip", archive.name), "html5")

    def test_static_asset_version_includes_nested_assets(self):
        import app
        with tempfile.TemporaryDirectory(prefix="an3-static-version-") as root:
            nested = os.path.join(root, "fonts")
            os.makedirs(nested)
            with open(os.path.join(root, "site.js"), "wb") as handle:
                handle.write(b"site")
            font = os.path.join(nested, "display.ttf")
            with open(font, "wb") as handle:
                handle.write(b"font-v1")
            original_static_dir = app.STATIC_DIR
            try:
                app.STATIC_DIR = root
                first = app.static_asset_version()
                with open(font, "wb") as handle:
                    handle.write(b"font-v2")
                self.assertNotEqual(first, app.static_asset_version())
            finally:
                app.STATIC_DIR = original_static_dir


class ServerBackedTestCase(unittest.TestCase):
    ENVIRONMENT = "production"
    PORT = PRODUCTION_PORT
    EXTRA_ENV = {}

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.mkdtemp(prefix="an3-arcade-test-")
        env = os.environ.copy()
        env.update({
            "AN3_DATA_DIR": os.path.join(cls.temp, "data"),
            "AN3_PORT": str(cls.PORT),
            "AN3_ADMIN_NAME": "rootadmin",
            "AN3_ADMIN_PASSWORD": "admin-pass-123",
            "AN3_COOKIE_SECURE": "0",
            "AN3_ENVIRONMENT": cls.ENVIRONMENT,
        })
        env.update(cls.EXTRA_ENV)
        cls.server = subprocess.Popen([sys.executable, APP], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.time() + 12
        while time.time() < deadline:
            try:
                if Client(cls.PORT).request("GET", "/health")[0] == 200:
                    return
            except OSError:
                time.sleep(.1)
        raise RuntimeError("test server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        cls.server.wait(timeout=8)
        shutil.rmtree(cls.temp)


class ArcadeLibraryIntegrationTests(ServerBackedTestCase):
    """Library-surface coverage.

    ``/game``, ``/play`` and the interactive ROM APIs are intentionally
    retired in production, so their behavior is verified against the staging
    environment where those routes are actually served.
    """

    ENVIRONMENT = "staging"
    PORT = LIBRARY_PORT

    def test_public_drafts_testing_admin_and_resumable_uploads(self):
        import app
        modern_hash = app.password_hash("modern-password-123")
        expected_scheme = "scrypt$8192$8$1$" if app.SCRYPT_AVAILABLE else "pbkdf2_sha256$120000$"
        self.assertTrue(modern_hash.startswith(expected_scheme))
        self.assertTrue(app.password_ok("modern-password-123", modern_hash))
        legacy_salt = b"legacy-test-salt"
        legacy_digest = hashlib.pbkdf2_hmac("sha256", b"legacy-password-123", legacy_salt, 310000, dklen=32)
        legacy_hash = "pbkdf2_sha256$310000$" + app.base64.urlsafe_b64encode(legacy_salt).decode() + "$" + app.base64.urlsafe_b64encode(legacy_digest).decode()
        self.assertTrue(app.password_ok("legacy-password-123", legacy_hash))
        self.assertEqual(app.password_needs_upgrade(legacy_hash), app.SCRYPT_AVAILABLE)
        with open(APP, "r", encoding="utf-8") as source:
            self.assertIn('scheme == "scrypt" and len(parts) == 6', source.read())

        public = Client(LIBRARY_PORT)
        status, headers, body = public.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertNotIn(b"Dashboard</a>", body)
        self.assertIn(b"Vibe Coded Emulator", body)
        self.assertNotIn("Ăn 3 Tô Cơm".encode(), body)
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertIn("Content-Security-Policy", headers)
        asset_version = re.search(rb'/static/site\.js\?v=([a-f0-9]{12})', body)
        self.assertIsNotNone(asset_version)
        versioned_site_js = f"/static/site.js?v={asset_version.group(1).decode()}"
        status, headers, _ = public.request("GET", versioned_site_js)
        self.assertEqual(status, 200)
        self.assertIn("immutable", headers.get("Cache-Control", ""))
        status, headers, _ = public.request("GET", "/static/site.js")
        self.assertEqual(status, 200)
        self.assertNotIn("immutable", headers.get("Cache-Control", ""))

        status, headers, _ = public.request("GET", "/offline-app")
        self.assertEqual(status, 303)
        self.assertEqual(headers.get("Location"), "/offline")
        status, headers, body = public.request("GET", "/offline-app-service-worker.js")
        self.assertEqual(status, 200)
        self.assertIn("no-cache", headers.get("Cache-Control", ""))
        self.assertIn(b"self.registration.unregister()", body)
        self.assertEqual(public.request("GET", "/static/offline-app.js")[0], 404)

        status, _, body = public.request("GET", "/login")
        self.assertEqual(status, 200)
        self.assertIn(b'id="authProgress"', body)

        admin = Client(LIBRARY_PORT)
        status, login = admin.post("/api/login", {"name": "rootadmin", "password": "admin-pass-123"})
        self.assertEqual((status, login["redirect"]), (200, "/admin"))
        csrf = admin.csrf("/admin")
        status, _, body = admin.request("GET", "/admin")
        self.assertEqual(status, 200)
        self.assertIn(b"Dashboard", body)
        self.assertNotIn(b"twoFactor", body)

        status, draft = admin.post("/admin/api/games", {
            "title_vi": "", "title_en": "", "description_vi": "", "description_en": "",
            "system": "auto", "rom_name": "Public-Draft.nds", "published": False, "experimental": True,
        }, csrf)
        self.assertEqual(status, 201)
        status, uploaded = admin.upload(f"/admin/api/games/{draft['id']}/rom?name=Public-Draft.nds", b"test nds rom", csrf)
        self.assertEqual((status, uploaded["system"]), (200, "nds"))

        status, gba = admin.post("/admin/api/games", {
            "title_vi": "Stable GBA Pick", "title_en": "Stable GBA Pick", "description_vi": "", "description_en": "",
            "system": "auto", "rom_name": "stable-pick.gba", "published": True, "experimental": False,
        }, csrf)
        self.assertEqual(status, 201)
        gba_payload = b"stable gba rom payload"
        status, uploaded = admin.upload(f"/admin/api/games/{gba['id']}/rom?name=stable-pick.gba", gba_payload, csrf)
        self.assertEqual((status, uploaded["system"]), (200, "gba"))

        status, _, body = public.request("GET", f"/game/{gba['slug']}")
        self.assertEqual(status, 200)
        self.assertNotIn(b"Quick Edit", body)
        status, _, body = admin.request("GET", f"/game/{gba['slug']}")
        self.assertEqual(status, 200)
        status, _, body = admin.request("GET", "/admin")
        self.assertEqual(status, 200)
        self.assertIn(b'id="batchStatusForm"', body)
        self.assertIn(b"data-delete-game", body)
        self.assertNotIn(b"data-approve-enrichment", body)
        self.assertNotIn(b"id=\"enrichmentProposalForm\"", body)
        self.assertNotIn(b"id=\"gameForm\"", body)
        self.assertNotIn(b"id=\"bulkGameForm\"", body)

        status, preview = admin.post("/admin/api/games/batch-status/preview", {"ids": [draft["id"]], "status": "testing"}, csrf)
        self.assertEqual((status, len(preview["games"]), preview["target"]), (200, 1, "testing"))
        status, failed_batch = admin.post("/admin/api/games/batch-status/apply", {"ids": [draft["id"]], "status": "testing", "confirmation": "wrong"}, csrf)
        self.assertIn("confirmation", failed_batch["error"])
        status, applied_batch = admin.post("/admin/api/games/batch-status/apply", {"ids": [draft["id"]], "status": "testing", "confirmation": preview["confirmation"]}, csrf)
        self.assertEqual((status, applied_batch["changed"], applied_batch["target"]), (200, 1, "testing"))

        for path in ("/games", f"/game/{draft['slug']}", f"/play/{draft['slug']}", f"/game-file/{draft['slug']}"):
            status, _, body = public.request("GET", path)
            self.assertEqual(status, 200, path)
        status, _, body = public.request("GET", "/games")
        self.assertIn(b"Draft", body)
        self.assertIn(b"Testing", body)
        self.assertIn(b"Public Draft", body)
        self.assertIn(b'id="systemFilters"', body)
        self.assertIn(b'data-system-section="nds"', body)
        self.assertIn(b'data-system-section="gba"', body)
        self.assertIn(b'data-section-kind="recommended"', body)
        status, headers, partial = public.raw("GET", f"/game-file/{gba['slug']}", None, {"Range": "bytes=0-5"})
        self.assertEqual((status, headers.get("Content-Range"), partial), (206, f"bytes 0-5/{len(gba_payload)}", gba_payload[:6]))

        status, zipped_nds = admin.post("/admin/api/games", {
            "title_vi": "Prepared NDS", "title_en": "Prepared NDS", "description_vi": "", "description_en": "",
            "system": "auto", "rom_name": "prepared-nds.zip", "published": False, "experimental": True,
        }, csrf)
        self.assertEqual(status, 201)
        nds_payload = b"raw nds payload for browser"
        zipped_payload = io.BytesIO()
        with zipfile.ZipFile(zipped_payload, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("roms/prepared-game.nds", nds_payload)
            archive.writestr("readme.txt", b"archive metadata")
        zipped_bytes = zipped_payload.getvalue()
        status, uploaded = admin.upload(f"/admin/api/games/{zipped_nds['id']}/rom?name=prepared-nds.zip", zipped_bytes, csrf)
        self.assertEqual((status, uploaded["system"]), (200, "nds"))
        status, headers, playable = public.request("GET", f"/game-file/{zipped_nds['slug']}")
        self.assertEqual((status, playable), (200, zipped_bytes))
        self.assertIn("prepared-nds.zip", headers.get("Content-Disposition", ""))
        status, _, player_body = public.request("GET", f"/play/{zipped_nds['slug']}")
        self.assertEqual(status, 200)
        self.assertIn(f'/static/v/{asset_version.group(1).decode()}/site.css'.encode(), player_body)
        self.assertIn(f"/game-file/{zipped_nds['slug']}/prepared-nds.zip".encode(), player_body)
        # Phase A: the rendered player exposes the autosave options, a dedicated
        # autosave slot and an explicit Exit Game control.
        for marker in (b'id="autosaveMode"', b'id="exitGame"', b"data-auto-slot", b"data-load-auto", b'value="exit"'):
            self.assertIn(marker, player_body)
        player_config_match = re.search(rb"data-player='([^']+)'", player_body)
        self.assertIsNotNone(player_config_match)
        player_config = json.loads(html.unescape(player_config_match.group(1).decode()))
        # The staging server is the environment where NDS diagnostics exist.
        self.assertEqual(player_config["ndsDebugAllowed"], True)
        # The phone-controller host UI ships only where the staging-only
        # controller endpoints exist, and the player page can host a session.
        self.assertEqual(player_config["controllerEnabled"], True)
        self.assertIn(b'id="ctrlPhonePanel"', player_body)
        self.assertIn(b'id="phoneController"', player_body)
        # The multiplayer bridge ships only where the relay is configured, with
        # the server-computed compatibility signature for the room. This class
        # runs without a relay, so the config flag gates the panel markup.
        self.assertIn("multiplayerEnabled", player_config)
        self.assertEqual(player_config["roomSignature"]["system"], "nds")
        self.assertTrue(player_config["roomSignature"]["romHash"].startswith("sha256:"))
        if player_config["multiplayerEnabled"]:
            self.assertIn(b'id="mpPlayerPanel"', player_body)
            self.assertIn(b'id="playerMultiplayer"', player_body)
        else:
            self.assertNotIn(b'id="mpPlayerPanel"', player_body)
        status, _, debug_player_body = public.request("GET", f"/play/{zipped_nds['slug']}?ndsdebug=1")
        self.assertEqual(status, 200)
        debug_config_match = re.search(rb"data-player='([^']+)'", debug_player_body)
        self.assertIsNotNone(debug_config_match)
        debug_config = json.loads(html.unescape(debug_config_match.group(1).decode()))
        self.assertEqual(debug_config["ndsDebugAllowed"], True)
        status, _, playable_named = public.request("GET", f"/game-file/{zipped_nds['slug']}/prepared-game.nds")
        self.assertEqual((status, playable_named), (200, zipped_bytes))
        status, _, original_download = public.request("GET", f"/download/{zipped_nds['slug']}")
        self.assertEqual((status, original_download), (200, zipped_bytes))

        guest = Client(LIBRARY_PORT)
        status, _ = guest.post("/api/register", {"name": "guest-player", "display_name": "Guest Nick", "password": "guest-pass-123", "confirm": "guest-pass-123"})
        self.assertEqual(status, 201)
        status, _, body = guest.request("GET", f"/game/{gba['slug']}")
        self.assertEqual(status, 200)
        self.assertNotIn(b"Quick Edit", body)
        guest_csrf = guest.csrf(f"/game/{gba['slug']}")
        status, denied_batch = guest.post("/admin/api/games/batch-status/preview", {"ids": [gba["id"]], "status": "draft"}, guest_csrf)
        self.assertEqual(status, 403)
        guest_csrf = guest.csrf(f"/game/{draft['slug']}")
        status, rating = guest.post(f"/api/games/{draft['id']}/rating", {"value": 5}, guest_csrf)
        self.assertEqual((status, rating["count"]), (200, 1))
        status, favorite = guest.post(f"/api/games/{draft['id']}/favorite", {}, guest_csrf)
        self.assertEqual((status, favorite["favorited"]), (200, True))
        status, report = guest.post(f"/api/games/{draft['id']}/reports", {"category": "controls", "body": "Public draft control test"}, guest_csrf)
        self.assertEqual((status, report["ok"]), (201, True))
        status, comment = guest.post(f"/api/games/{draft['id']}/comments", {"body": "Works nicely."}, guest_csrf)
        self.assertEqual((status, comment["ok"]), (201, True))

        status, large = admin.post("/admin/api/games", {
            "title_vi": "Large 3DS", "title_en": "Large 3DS", "description_vi": "", "description_en": "",
            "system": "auto", "rom_name": "large-test.3ds", "published": False, "experimental": False,
        }, csrf)
        self.assertEqual(status, 201)
        payload = b"3DS-test-payload-" * 4096
        status, session = admin.post(f"/admin/api/games/{large['id']}/uploads", {"kind": "rom", "name": "large-test.3ds", "size": len(payload)}, csrf)
        self.assertEqual(status, 201)
        upload_id = session["upload_id"]
        middle = len(payload) // 2
        status, _, body = admin.raw("PUT", f"/admin/api/uploads/{upload_id}", payload[:middle], {"X-CSRF-Token": csrf, "X-Upload-Offset": "0"})
        self.assertEqual((status, json.loads(body)["received"]), (200, middle))
        status, _, body = admin.raw("PUT", f"/admin/api/uploads/{upload_id}", payload[middle:], {"X-CSRF-Token": csrf, "X-Upload-Offset": str(middle)})
        self.assertTrue(json.loads(body)["complete"])
        status, completed = admin.post(f"/admin/api/uploads/{upload_id}/complete", {}, csrf)
        self.assertEqual((status, completed["system"]), (200, "3ds"))
        status, _, downloaded = public.request("GET", f"/game-file/{large['slug']}")
        self.assertEqual((status, downloaded), (200, payload))

        status, _, body = admin.request("GET", "/admin")
        self.assertIn(b"Public draft control test", body)
        self.assertIn(b"data-delete-game", body)
        status, _, deleted = admin.request("DELETE", f"/admin/api/games/{large['id']}", None, {"X-CSRF-Token": csrf})
        self.assertEqual((status, json.loads(deleted)["ok"]), (200, True))
        self.assertEqual(public.request("GET", f"/game/{large['slug']}")[0], 404)

        status, _ = admin.post("/admin/api/users", {"name": "secondadmin", "display_name": "Second Admin", "password": "second-admin-123", "confirm": "second-admin-123"}, csrf)
        self.assertEqual(status, 201)
        second = Client(LIBRARY_PORT)
        status, login = second.post("/api/login", {"name": "secondadmin", "password": "second-admin-123"})
        self.assertEqual((status, login["redirect"]), (200, "/admin"))
        self.assertEqual(second.request("GET", "/admin")[0], 200)

        for path, marker in (("/offline", b"offline-notice"), ("/service-worker.js", b"an3-arcade-pwa-v31-"), ("/static/default-cover.webp", b"RIFF"), ("/static/fonts/pixelify-sans-latin.woff2", b"wOF2"), ("/static/ui-library-search.svg", b"<svg"), ("/static/manifest.webmanifest", b"Vibe Coded Emulator")):
            status, response_headers, body = public.request("GET", path)
            self.assertEqual(status, 200)
            self.assertIn(marker, body)
        # The web offline page is a minimal notice: no browser-local ROM library.
        offline_status, _, offline_body = public.request("GET", "/offline")
        self.assertEqual(offline_status, 200)
        self.assertIn(b"You're offline", offline_body)
        self.assertNotIn(b"offlineGameForm", offline_body)
        self.assertNotIn(b"offlineFile", offline_body)
        self.assertNotIn(b"corePreloadGrid", offline_body)

        status, _, body = public.request("GET", "/download-app")
        self.assertEqual(status, 200)
        self.assertIn(b"DOWNLOAD THE OFFLINE APP", body)
        self.assertIn(b"VIBE CODED EMULATOR", body)
        self.assertIn(b"platform-card", body)
        self.assertIn(b'nav-download-app', public.request("GET", "/")[2])
        # Staging may host the source archive and manifest; production gating is
        # asserted separately. A superseded installer filename stays 404 even
        # when its bytes previously existed.
        self.assertEqual(public.request("GET", "/download-app/release/emulatorrust-0.1.1-macos-aarch64.dmg")[0], 404)

        status, _, body = public.request("GET", "/static/site.js")
        self.assertEqual(status, 200)
        self.assertIn(b'authForm.classList.add("is-loading")', body)
        self.assertIn(b"authProgress", body)
        self.assertIn(b"data-system-filter", body)

        status, _, body = public.request("GET", "/static/offline.js")
        self.assertEqual(status, 200)
        self.assertIn(b"createOfflineId", body)
        self.assertIn(b"getRandomValues", body)
        self.assertNotIn(b"id:crypto.randomUUID()", body)
        self.assertIn(b"an3-offline-core-v7", body)
        self.assertIn(b'const coreCandidates = system => [primaryCores[system]]', body)
        self.assertNotIn(b"desmume", body.lower())
        self.assertIn(b'indexedDB.open("EmulatorJS-core",1)', body)
        self.assertIn(b"indexedCoreEntries", body)
        self.assertIn(b"deleteIndexedCoreEntries", body)
        self.assertIn(b"inspectCore", body)
        self.assertIn(b"deleteCore", body)
        self.assertIn("Đã tải".encode(), body)
        self.assertIn(b"Downloading and verifying", body)

        status, _, body = public.request("GET", "/static/player.js")
        self.assertEqual(status, 200)
        self.assertIn(b"const ndsDefaults", body)
        self.assertIn(b"an3-pad-v${ndsPad ? 5 : threeDsPad ? 7 : 3}", body)
        self.assertIn(b'canvas.classList.remove("ejs-canvas-no-pointer")', body)
        self.assertIn(b"new MutationObserver(queueCanvasProtection)", body)
        self.assertIn(b"new MutationObserver(mutations=>{if(mutations.some(mutationTouchesEmulatorMenu))queueEmulatorMenuLayer();})", body)
        self.assertIn(b"dispatchNdsMouse", body)
        self.assertIn(b"window.EJS_noAutoFocus = ndsPad && touchFirst", body)
        self.assertIn(b'config.system === "doom" ? "prboom"', body)
        self.assertIn(b'nds:"melonds"', body)
        self.assertIn(b'const emulatorSystem = config.system === "doom" ? "prboom" : config.system', body)
        self.assertIn(b'retroarch_core:"melonds"', body)
        self.assertIn(b"window.EJS_disableLocalStorage = ndsPad", body)
        self.assertNotIn("Vào game".encode(), body)
        self.assertIn(b"window.EJS_startOnLoaded = true", body)
        self.assertNotIn(b"window.EJS_emulator.startButtonClicked", body)
        self.assertIn(b"const clearBootstrapTimers = () =>", body)
        self.assertIn(b"if (gameStarted) clearBootstrapTimers()", body)
        self.assertNotIn(b"if (window.EJS_emulator?.gameManager) { clearInterval(ready)", body)
        self.assertIn(b"preloadCoreAssets", body)
        self.assertIn(b"cores/${coreFile}", body)
        self.assertIn(b'indexedDB.open("EmulatorJS-core",1)', body)
        self.assertIn(b"putCoreRecord(coreFile,coreData,report.buildStart)", body)
        self.assertIn(b"report?.options?.defaultWebGL2", body)
        self.assertIn(b"return config.romUrl", body)
        self.assertNotIn(b"const chunks = []", body)
        self.assertIn(b"window.EJS_threads = threadedCore", body)
        self.assertIn(b'config.system === "3ds" ? "data-v2" : "data"', body)
        self.assertNotIn(b'setTimeout(() => window.parent?.postMessage({type:"an3-core-preload"', body)
        self.assertEqual(public.request("GET", "/emulatorjs/stable/data/../loader.js")[0], 404)

        with open(APP, "rb") as app_source:
            self.assertIn(b'path.startswith("/game-file/") and game["system"] != "nds"', app_source.read())

        status, _, body = public.request("GET", "/service-worker.js")
        self.assertEqual(status, 200)
        self.assertIn(b'an3-arcade-cores-v1', body)
        self.assertIn(asset_version.group(1), body)
        self.assertIn(f'/static/v/{asset_version.group(1).decode()}/player-runtime.js'.encode(), body)
        self.assertIn(f'/static/v/{asset_version.group(1).decode()}/site.css'.encode(), body)
        self.assertNotIn(b'__ASSET_VERSION__', body)
        self.assertIn(b'Preserve them before removing stale shells', body)

        # Derive from the frozen boot-asset contract so a new boot asset cannot
        # be referenced by pages while the versioned route silently 404s it.
        for name in sorted(app.PLAYER_BOOT_ASSETS):
            status, headers, alias_body = public.request("GET", f"/static/v/{asset_version.group(1).decode()}/{name}")
            self.assertEqual(status, 200)
            self.assertIn("immutable", headers.get("Cache-Control", ""))
            with open(os.path.join(ROOT, "static", name), "rb") as source:
                self.assertEqual(alias_body, source.read())
        for worker_path in ("/static/renderer-worker.js", f"/static/v/{asset_version.group(1).decode()}/renderer-worker.js"):
            for method in ("GET", "HEAD"):
                worker_status, worker_headers, _ = public.request(method, worker_path)
                self.assertEqual(worker_status, 200)
                self.assertEqual(worker_headers.get("Cross-Origin-Embedder-Policy"), "require-corp")
                self.assertEqual(worker_headers.get("Cross-Origin-Resource-Policy"), "same-origin")
        self.assertEqual(public.request("GET", "/static/v/000000000000/player-runtime.js")[0], 404)

    def test_non_player_routes_keep_shared_design_contract(self):
        public = Client(LIBRARY_PORT)
        for path, marker in (("/login", b'auth-shell'), ("/register", b'auth-shell'), ("/missing-route", b'status-page')):
            status, _, body = public.request("GET", path)
            self.assertEqual(status, 404 if path == "/missing-route" else 200)
            self.assertIn(marker, body)

        admin = Client(LIBRARY_PORT)
        status, _ = admin.post("/api/login", {"name": "rootadmin", "password": "admin-pass-123"})
        self.assertEqual(status, 200)
        csrf = admin.csrf("/admin")
        status, game = admin.post("/admin/api/games", {
            "title_vi": "Route contract", "title_en": "Route contract", "description_vi": "", "description_en": "",
            "system": "gba", "rom_name": "route-contract.gba", "published": False, "experimental": False,
        }, csrf)
        self.assertEqual(status, 201)
        status, _, body = public.request("GET", f"/game/{game['slug']}")
        self.assertEqual(status, 200)
        self.assertIn(b'detail-page', body)
        status, _, body = admin.request("GET", "/admin")
        self.assertEqual(status, 200)
        self.assertIn(b'admin-page', body)
        with open(os.path.join(ROOT, "static", "site.css"), encoding="utf-8") as stylesheet:
            self.assertIn(b'body:not(.player-page)', stylesheet.read().encode())

        user = Client(LIBRARY_PORT)
        status, _ = user.post("/api/register", {"name": "route-user", "display_name": "Route User", "password": "route-user-123", "confirm": "route-user-123"})
        self.assertEqual(status, 201)
        status, _, body = user.request("GET", "/account")
        self.assertEqual(status, 200)
        self.assertIn(b'account-page', body)


class ArcadeProductionIntegrationTests(ServerBackedTestCase):
    """Download-first production contract.

    Production serves only the app catalog plus the browser-local offline
    player. Legacy library routes and staging-only source endpoints must stay
    gone; the current catalog installers must stay downloadable.
    """

    ENVIRONMENT = "production"
    PORT = PRODUCTION_PORT

    def test_http11_reuses_the_connection_for_versioned_assets(self):
        connection = http.client.HTTPConnection("127.0.0.1", PRODUCTION_PORT, timeout=12)
        try:
            connection.request("GET", "/health", headers={"Accept": "application/json"})
            health = connection.getresponse()
            self.assertEqual((health.status, health.version), (200, 11))
            asset = json.loads(health.read().decode())["asset_version"]
            connection.request("GET", f"/static/site.js?v={asset}")
            static = connection.getresponse()
            payload = static.read()
            self.assertEqual(static.status, 200)
            self.assertIn("immutable", static.getheader("Cache-Control", ""))
            self.assertIn(b"serviceWorker", payload)

            connection.request("GET", "/offline-app")
            redirect = connection.getresponse()
            self.assertEqual((redirect.status, redirect.getheader("Content-Length")), (303, "0"))
            self.assertEqual(redirect.read(), b"")
        finally:
            connection.close()

    def test_public_rom_library_and_staging_routes_stay_retired(self):
        admin = Client(PRODUCTION_PORT)
        status, _ = admin.post("/api/login", {"name": "rootadmin", "password": "admin-pass-123"})
        self.assertEqual(status, 200)
        csrf = admin.csrf("/admin")
        status, game = admin.post("/admin/api/games", {
            "title_vi": "Retired route", "title_en": "Retired route", "description_vi": "", "description_en": "",
            "system": "gba", "rom_name": "retired-route.gba", "published": True, "experimental": False,
        }, csrf)
        self.assertEqual(status, 201)

        public = Client(PRODUCTION_PORT)
        for path in (
            "/games",
            "/api/library-version",
            f"/game/{game['slug']}",
            f"/play/{game['slug']}",
            f"/game-file/{game['slug']}",
            f"/download/{game['slug']}",
            "/cover/retired.gba",
        ):
            with self.subTest(path=path):
                self.assertEqual(public.request("GET", path)[0], 404)
        status, payload = public.post(f"/api/games/{game['id']}/rating", {"value": 5})
        self.assertEqual(status, 404)

        self.assertEqual(public.request("GET", "/download-app/source")[0], 404)
        self.assertEqual(public.request("GET", "/download-app/artifacts.json")[0], 404)

        status, _, body = public.request("GET", "/download-app")
        self.assertEqual(status, 200)
        self.assertIn(b'nav-download-app', public.request("GET", "/")[2])

        import app
        available = [item for item in app.NATIVE_RELEASE_CATALOG if item["filename"]]
        self.assertTrue(available)
        for item in available:
            with self.subTest(installer=item["filename"]):
                status, headers, _ = public.raw("HEAD", f"/download-app/release/{item['filename']}?sha256={item['sha256']}")
                self.assertEqual(status, 200)
                self.assertEqual(headers.get("Content-Length"), str(item["size"]))
                self.assertIn("no-store", headers.get("Cache-Control", ""))

    def test_multiplayer_is_absent_in_production(self):
        public = Client(PRODUCTION_PORT)
        self.assertEqual(public.request("GET", "/multiplayer")[0], 404)
        self.assertEqual(public.request("POST", "/api/multiplayer/room", {"system": "gba", "core": "mgba", "romHash": "sha256:" + "a" * 64})[0], 404)
        self.assertEqual(public.request("GET", "/controller")[0], 404)
        self.assertEqual(public.request("GET", "/controller/join")[0], 404)
        self.assertEqual(public.request("POST", "/api/controller/session", {})[0], 404)


class MultiplayerIntegrationTests(ServerBackedTestCase):
    """Staging multiplayer surface over real HTTP with a configured relay."""

    ENVIRONMENT = "staging"
    PORT = MULTIPLAYER_PORT
    EXTRA_ENV = {"AN3_NETPLAY_ORIGIN": "http://127.0.0.1:8094"}

    def test_room_page_renders_with_its_controls(self):
        public = Client(MULTIPLAYER_PORT)
        status, _, body = public.request("GET", "/multiplayer")
        self.assertEqual(status, 200)
        for marker in (b'id="mpCreateBtn"', b'id="mpJoinBtn"', b'id="mpCode"', b'/static/multiplayer.js'):
            self.assertIn(marker, body)
        # The normal surface never exposes staging feature wording or the relay
        # origin. The global environment badge in the header is not page copy.
        self.assertNotIn(b"STAGING", body[body.index(b"<main"):])
        self.assertNotIn(b"http://127.0.0.1:8094", body)
        self.assertIn(b"Technical details", body)

    def test_create_join_and_status_over_http(self):
        public = Client(MULTIPLAYER_PORT)
        signature = {"system": "gba", "core": "mgba", "romHash": "sha256:" + "a" * 64}
        status, _, body = public.request("POST", "/api/multiplayer/room", {**signature, "deviceId": "tv"})
        self.assertEqual(status, 201)
        room = json.loads(body)
        self.assertEqual(room["relay"], "http://127.0.0.1:8094")

        # A mismatched game is rejected before the room fills.
        status, _, _ = public.request("POST", "/api/multiplayer/join", {"system": "gba", "core": "mgba", "romHash": "sha256:" + "b" * 64, "code": room["code"]})
        self.assertEqual(status, 409)

        status, _, body = public.request("POST", "/api/multiplayer/join", {**signature, "code": room["code"]})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["role"], "guest")

        status, _, body = public.request("GET", f"/api/multiplayer/room?code={room['code']}&token={room['token']}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["state"], "full")

    def test_controller_pages_and_api_over_http(self):
        public = Client(MULTIPLAYER_PORT)
        for path in ("/controller", "/controller/join"):
            status, _, body = public.request("GET", path)
            self.assertEqual(status, 200, path)
            self.assertIn(b"/static/controller.js", body)
        self.assertIn(b'id="ctrlCode"', public.request("GET", "/controller")[2])

        status, _, body = public.request("POST", "/api/controller/session", {"deviceId": "host"})
        self.assertEqual(status, 201)
        session = json.loads(body)
        status, _, body = public.request("POST", "/api/controller/pair", {"code": session["code"], "deviceId": "phone"})
        self.assertEqual(status, 200)
        phone = json.loads(body)
        status, _, _ = public.request("POST", "/api/controller/state", {"code": session["code"], "token": phone["token"], "s": 1, "b": ["start"]})
        self.assertEqual(status, 200)
        status, _, body = public.request("GET", f"/api/controller/state?code={session['code']}&hostToken={session['hostToken']}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["state"]["b"], ["start"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
