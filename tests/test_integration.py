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


class ReleaseArtifactTests(unittest.TestCase):
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
                "vibecodedemulator-3.3.0-macos-aarch64.dmg",
                "vibecodedemulator-3.3.0-android-arm64-staging.apk",
                "vibecodedemulator-3.3.0-android-arm64-staging.aab",
                "vibecodedemulator-3.3.0-linux-amd64.deb",
                "an3-offline-3.3.0-linux-amd64-staging.flatpak",
                "vibecodedemulator-3.3.0-windows-x64-staging.exe",
            ],
        )
        self.assertEqual(
            {item["format"]: item["version"] for item in available},
            {
                "DMG": "3.3.0",
                "APK": "3.3.0",
                "AAB": "3.3.0",
                "DEB": "3.3.0",
                "Flatpak": "3.3.0",
                "EXE": "3.3.0",
            },
        )
        self.assertTrue(all(item["size"] and item["sha256"] for item in available))


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

    def test_account_routes_are_retired_and_public_local_surfaces_stay_clean(self):
        public = Client(LIBRARY_PORT)
        for path in ("/login", "/register", "/account", "/admin", "/bug-report", "/api/account/session"):
            with self.subTest(path=path):
                self.assertEqual(public.request("GET", path)[0], 404)

        for path in ("/api/register", "/api/login", "/api/logout", "/api/account/display-name"):
            with self.subTest(path=path):
                self.assertEqual(public.request("POST", path, {})[0], 404)

        status, _, root = public.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertNotIn(b'href="/login"', root)
        self.assertNotIn(b'href="/register"', root)
        status, _, library = public.request("GET", "/games")
        self.assertEqual(status, 200)
        self.assertNotIn(b"favoriteButton", library)
        self.assertNotIn(b"authForm", library)
        status, _, offline = public.request("GET", "/offline")
        self.assertEqual(status, 200)
        self.assertIn(b"offline-notice", offline)

        status, _, site_js = public.request("GET", "/static/site.js")
        self.assertEqual(status, 200)
        self.assertNotIn(b"/api/login", site_js)
        self.assertNotIn(b"/api/account/", site_js)
        with open(os.path.join(ROOT, "static", "site.css"), encoding="utf-8") as stylesheet:
            self.assertIn(b'body:not(.player-page)', stylesheet.read().encode())

    def test_non_player_routes_keep_shared_design_contract(self):
        public = Client(LIBRARY_PORT)
        for path, expected in (("/login", 404), ("/register", 404), ("/account", 404), ("/missing-route", 404), ("/offline", 200)):
            with self.subTest(path=path):
                self.assertEqual(public.request("GET", path)[0], expected)
        status, _, body = public.request("GET", "/offline")
        self.assertEqual(status, 200)
        self.assertIn(b'offline-notice', body)
        self.assertNotIn(b'auth-shell', body)


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
        public = Client(PRODUCTION_PORT)
        for path in (
            "/games",
            "/api/library-version",
            "/game/retired-route",
            "/play/retired-route",
            "/game-file/retired-route",
            "/download/retired-route",
            "/cover/retired.gba",
            "/login",
            "/register",
            "/account",
            "/api/account/session",
        ):
            with self.subTest(path=path):
                self.assertEqual(public.request("GET", path)[0], 404)
        self.assertEqual(public.request("POST", "/api/login", {})[0], 404)
        self.assertEqual(public.request("POST", "/api/games/1/rating", {"value": 5})[0], 404)

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

    def test_phone_controller_pages_and_api_are_retired_over_http(self):
        public = Client(MULTIPLAYER_PORT)
        for method, path, payload in (
            ("GET", "/controller", None),
            ("GET", "/controller/join", None),
            ("POST", "/api/controller/session", {}),
            ("POST", "/api/controller/pair", {}),
            ("POST", "/api/controller/state", {}),
            ("GET", "/api/controller/state?code=ABC123&hostToken=unused", None),
            ("POST", "/api/controller/ack", {}),
            ("GET", "/api/controller/link?code=ABC123&token=unused", None),
        ):
            with self.subTest(method=method, path=path):
                self.assertEqual(public.request(method, path, payload)[0], 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
