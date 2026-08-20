#!/usr/bin/env python3
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
PORT = 18791
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class Client:
    def __init__(self):
        self.cookie = ""

    def raw(self, method, path, body=None, headers=None):
        request_headers = {"Accept": "application/json"}
        if self.cookie:
            request_headers["Cookie"] = self.cookie
        request_headers.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", PORT, timeout=12)
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


class ArcadeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.mkdtemp(prefix="an3-arcade-test-")
        env = os.environ.copy()
        env.update({
            "AN3_DATA_DIR": os.path.join(cls.temp, "data"),
            "AN3_PORT": str(PORT),
            "AN3_ADMIN_NAME": "rootadmin",
            "AN3_ADMIN_PASSWORD": "admin-pass-123",
            "AN3_COOKIE_SECURE": "0",
            "AN3_ENVIRONMENT": "production",
        })
        cls.server = subprocess.Popen([sys.executable, APP], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.time() + 12
        while time.time() < deadline:
            try:
                if Client().request("GET", "/health")[0] == 200:
                    return
            except OSError:
                time.sleep(.1)
        raise RuntimeError("test server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        cls.server.wait(timeout=8)
        shutil.rmtree(cls.temp)

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

        public = Client()
        status, headers, body = public.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertNotIn(b"Dashboard</a>", body)
        self.assertIn("Ăn 3 Tô Cơm".encode(), body)
        self.assertNotIn("Ăn 3 Tô Cơm lãnh địa".encode(), body)
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertIn("Content-Security-Policy", headers)
        asset_version = re.search(rb'/static/site\.js\?v=([a-f0-9]{12})', body)
        self.assertIsNotNone(asset_version)

        status, _, body = public.request("GET", "/login")
        self.assertEqual(status, 200)
        self.assertIn(b'id="authProgress"', body)

        admin = Client()
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

        for path in ("/", f"/game/{draft['slug']}", f"/play/{draft['slug']}", f"/game-file/{draft['slug']}"):
            status, _, body = public.request("GET", path)
            self.assertEqual(status, 200, path)
        status, _, body = public.request("GET", "/")
        self.assertIn(b"Draft", body)
        self.assertIn(b"Testing", body)
        self.assertIn(b"Public Draft", body)
        self.assertIn(b'id="systemFilters"', body)
        self.assertIn(b'data-system-section="nds"', body)
        self.assertIn(b'data-system-section="gba"', body)
        self.assertIn(b'data-section-kind="recommended"', body)
        self.assertIn(b"Stable GBA Pick", body)
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
        self.assertIn(f"/game-file/{zipped_nds['slug']}/prepared-game.nds".encode(), player_body)
        player_config_match = re.search(rb"data-player='([^']+)'", player_body)
        self.assertIsNotNone(player_config_match)
        player_config = json.loads(html.unescape(player_config_match.group(1).decode()))
        self.assertEqual(player_config["ndsDebugAllowed"], False)
        status, _, debug_player_body = public.request("GET", f"/play/{zipped_nds['slug']}?ndsdebug=1")
        self.assertEqual(status, 200)
        debug_config_match = re.search(rb"data-player='([^']+)'", debug_player_body)
        self.assertIsNotNone(debug_config_match)
        debug_config = json.loads(html.unescape(debug_config_match.group(1).decode()))
        self.assertEqual(debug_config["ndsDebugAllowed"], False)
        status, _, playable_named = public.request("GET", f"/game-file/{zipped_nds['slug']}/prepared-game.nds")
        self.assertEqual((status, playable_named), (200, zipped_bytes))
        status, _, original_download = public.request("GET", f"/download/{zipped_nds['slug']}")
        self.assertEqual((status, original_download), (200, zipped_bytes))

        guest = Client()
        status, _ = guest.post("/api/register", {"name": "guest-player", "display_name": "Guest Nick", "password": "guest-pass-123", "confirm": "guest-pass-123"})
        self.assertEqual(status, 201)
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
        self.assertIn("Draft và Testing".encode(), body)
        self.assertIn(b"data-delete-game", body)
        status, _, deleted = admin.request("DELETE", f"/admin/api/games/{large['id']}", None, {"X-CSRF-Token": csrf})
        self.assertEqual((status, json.loads(deleted)["ok"]), (200, True))
        self.assertEqual(public.request("GET", f"/game/{large['slug']}")[0], 404)

        status, _ = admin.post("/admin/api/users", {"name": "secondadmin", "display_name": "Second Admin", "password": "second-admin-123", "confirm": "second-admin-123"}, csrf)
        self.assertEqual(status, 201)
        second = Client()
        status, login = second.post("/api/login", {"name": "secondadmin", "password": "second-admin-123"})
        self.assertEqual((status, login["redirect"]), (200, "/admin"))
        self.assertEqual(second.request("GET", "/admin")[0], 200)

        for path, marker in (("/offline", b"offlineGameForm"), ("/service-worker.js", b"an3-arcade-pwa-v24"), ("/static/default-cover.webp", b"RIFF"), ("/static/fonts/pixelify-sans-latin.woff2", b"wOF2"), ("/static/ui-library-search.svg", b"<svg"), ("/static/manifest.webmanifest", "Ăn 3 Tô Cơm".encode())):
            status, response_headers, body = public.request("GET", path)
            self.assertEqual(status, 200)
            self.assertIn(marker, body)
            if path == "/offline":
                self.assertEqual(response_headers.get("Cross-Origin-Embedder-Policy"), "require-corp")

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
        self.assertIn(b"an3-pad-v${ndsPad ? 4 : 3}", body)
        self.assertIn(b'canvas.classList.remove("ejs-canvas-no-pointer")', body)
        self.assertIn(b"new MutationObserver(protectNdsCanvas)", body)
        self.assertIn(b"dispatchNdsMouse", body)
        self.assertIn(b"window.EJS_noAutoFocus = ndsPad", body)
        self.assertIn(b'config.system === "doom" ? "prboom"', body)
        self.assertIn(b'nds:"melonds"', body)
        self.assertIn(b'const emulatorSystem = config.system === "doom" ? "prboom" : config.system', body)
        self.assertIn(b'retroarch_core:"melonds"', body)
        self.assertIn(b"window.EJS_disableLocalStorage = ndsPad", body)
        self.assertNotIn("Vào game".encode(), body)
        self.assertIn(b"window.EJS_startOnLoaded = true", body)
        self.assertNotIn(b"window.EJS_emulator.startButtonClicked", body)
        self.assertIn(b"if (gameStarted) clearInterval(ready)", body)
        self.assertNotIn(b"if (window.EJS_emulator?.gameManager) { clearInterval(ready)", body)
        self.assertIn(b"preloadCoreAssets", body)
        self.assertIn(b"cores/${coreFile}", body)
        self.assertIn(b'indexedDB.open("EmulatorJS-core",1)', body)
        self.assertIn(b"putCoreRecord(coreFile,coreData,report.buildStart)", body)
        self.assertIn(b"report?.options?.defaultWebGL2", body)
        self.assertIn(b"return config.romUrl", body)
        self.assertNotIn(b"const chunks = []", body)
        self.assertIn(b"window.EJS_threads = threadedCore", body)
        self.assertIn(b"/emulatorjs/${config.channel}/data/", body)
        self.assertNotIn(b'setTimeout(() => window.parent?.postMessage({type:"an3-core-preload"', body)
        self.assertEqual(public.request("GET", "/emulatorjs/stable/data/../loader.js")[0], 404)

        with open(APP, "rb") as app_source:
            self.assertIn(b'path.startswith("/game-file/") and game["system"] != "nds"', app_source.read())

        status, _, body = public.request("GET", "/service-worker.js")
        self.assertEqual(status, 200)
        self.assertIn(b'an3-arcade-cores-v1', body)
        self.assertIn(b'Preserve them before removing stale shells', body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
