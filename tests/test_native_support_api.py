# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Anonymous native support: capability issuance and sanitized submission.

The packaged offline app has no account session and no cookie, so it cannot
authenticate to ``/api/bug-reports``. These tests cover the smallest secure
model that fits the existing server:

* only an allowlisted app origin may request a capability (fail closed);
* the capability is an opaque, server-issued, finite-lifetime, finite-use
  bearer token that carries no MAC/device-fingerprint/account identity;
* a capability submission is sanitized and persisted with ``user_id`` NULL;
* an absent, spent, or expired capability is rejected;
* the existing cookie + CSRF user path keeps working unchanged.
"""

import hashlib
import http.client
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import app
import bug_report


ALLOWED_ORIGIN = "https://appassets.androidplatform.net"
OTHER_ORIGIN = "https://evil.example"
FAKE_TOKEN = "ghp_" + "A" * 36
FAKE_MAC = "de:ad:be:ef:00:11"


class NativeSupportApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="an3-native-support-test-")
        root = self.temp.name
        self.patches = [
            patch.object(app, "BUG_REPORT_ENABLED", True),
            patch.object(app, "SUPPORT_ALLOWED_ORIGINS", (ALLOWED_ORIGIN,)),
            patch.object(app, "DB_PATH", os.path.join(root, "arcade.db")),
            patch.object(app, "ROM_DIR", os.path.join(root, "roms")),
            patch.object(app, "COVER_DIR", os.path.join(root, "covers")),
            patch.object(app, "SCREENSHOT_DIR", os.path.join(root, "screenshots")),
            patch.object(app, "CUSTOM_DIR", os.path.join(root, "custom")),
            patch.object(app, "UPLOAD_DIR", os.path.join(root, "uploads")),
            patch.object(app, "EMULATOR_CACHE_DIR", os.path.join(root, "emulatorjs-cache")),
            patch.object(app, "PREPARED_ROM_DIR", os.path.join(root, "prepared-roms")),
        ]
        for active in self.patches:
            active.start()
        app.RATE_LIMIT.clear()
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

    def request(self, method, path, payload=None, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        merged = dict(headers or {})
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            merged["Content-Type"] = "application/json"
        connection.request(method, path, body=body, headers=merged)
        response = connection.getresponse()
        status = response.status
        raw = response.read()
        received = dict(response.getheaders())
        connection.close()
        return status, received, raw

    def json(self, method, path, payload=None, headers=None):
        status, received, raw = self.request(method, path, payload, headers)
        try:
            return status, received, json.loads(raw)
        except ValueError:
            return status, received, {}

    def capability(self, origin=ALLOWED_ORIGIN):
        status, _, data = self.json("GET", app.SUPPORT_CAPABILITY_PATH, headers={"Origin": origin})
        self.assertEqual(status, 201, data)
        return data

    def payload(self, description):
        return {
            "description": description,
            "platform": "Android",
            "emulatorSystem": "nds",
            "coreName": "melonds",
            "gameTitle": "Test Game",
            "logs": ["boot ok"],
        }

    # -- capability issuance -------------------------------------------------

    def test_capability_requires_an_allowlisted_origin(self):
        status, _, data = self.json("GET", app.SUPPORT_CAPABILITY_PATH)
        self.assertEqual(status, 403)
        self.assertNotIn("capability", data)
        status, _, data = self.json(
            "GET", app.SUPPORT_CAPABILITY_PATH, headers={"Origin": OTHER_ORIGIN}
        )
        self.assertEqual(status, 403)
        self.assertNotIn("capability", data)

    def test_empty_allowlist_fails_closed(self):
        with patch.object(app, "SUPPORT_ALLOWED_ORIGINS", ()):
            status, _, _ = self.json(
                "GET", app.SUPPORT_CAPABILITY_PATH, headers={"Origin": ALLOWED_ORIGIN}
            )
            self.assertEqual(status, 403)

    def test_capability_is_opaque_and_stored_only_as_a_digest(self):
        data = self.capability()
        token = data["capability"]
        self.assertTrue(token)
        self.assertGreaterEqual(len(token), 32)
        # No identity or account material is embedded or echoed.
        serialized = json.dumps(data)
        for forbidden in ("mac", "deviceId", "device_id", "user", "email", "token_hash", "secret"):
            self.assertNotIn(forbidden, serialized)
        with app.db() as connection:
            rows = connection.execute("SELECT token_hash, origin, uses, max_uses FROM support_capabilities").fetchall()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertNotEqual(row["token_hash"], token)
        self.assertEqual(row["token_hash"], hashlib.sha256(token.encode()).hexdigest())
        self.assertEqual(row["origin"], ALLOWED_ORIGIN)
        self.assertEqual(row["uses"], 0)
        self.assertEqual(row["max_uses"], bug_report.CAPABILITY_MAX_USES)

    def test_capability_response_never_leaks_the_github_token(self):
        with patch.object(app, "GITHUB_ISSUES_TOKEN", FAKE_TOKEN):
            status, received, raw = self.request(
                "GET", app.SUPPORT_CAPABILITY_PATH, headers={"Origin": ALLOWED_ORIGIN}
            )
        self.assertEqual(status, 201)
        self.assertNotIn(FAKE_TOKEN.encode(), raw)
        self.assertNotIn(b"Authorization", raw)
        self.assertNotIn("Access-Control-Allow-Credentials", received)

    def test_capability_endpoint_is_disabled_with_bug_reports(self):
        with patch.object(app, "BUG_REPORT_ENABLED", False):
            status, _, _ = self.json(
                "GET", app.SUPPORT_CAPABILITY_PATH, headers={"Origin": ALLOWED_ORIGIN}
            )
            self.assertEqual(status, 404)

    # -- CORS ----------------------------------------------------------------

    def test_cors_headers_are_scoped_to_the_allowlisted_origin(self):
        status, received, _ = self.request(
            "GET", app.SUPPORT_CAPABILITY_PATH, headers={"Origin": ALLOWED_ORIGIN}
        )
        self.assertEqual(status, 201)
        self.assertEqual(received.get("Access-Control-Allow-Origin"), ALLOWED_ORIGIN)
        self.assertEqual(received.get("Cross-Origin-Resource-Policy"), "cross-origin")
        status, received, _ = self.request(
            "GET", app.SUPPORT_CAPABILITY_PATH, headers={"Origin": OTHER_ORIGIN}
        )
        self.assertEqual(status, 403)
        self.assertNotIn("Access-Control-Allow-Origin", received)

    def test_options_preflight_allows_only_the_support_endpoints(self):
        status, received, _ = self.request(
            "OPTIONS",
            "/api/bug-reports",
            headers={"Origin": ALLOWED_ORIGIN, "Access-Control-Request-Method": "POST"},
        )
        self.assertEqual(status, 204)
        self.assertEqual(received.get("Access-Control-Allow-Origin"), ALLOWED_ORIGIN)
        self.assertIn(bug_report.SUPPORT_CAPABILITY_HEADER, received.get("Access-Control-Allow-Headers", ""))
        status, _, _ = self.request(
            "OPTIONS", "/api/controller/session", headers={"Origin": ALLOWED_ORIGIN}
        )
        self.assertEqual(status, 404)
        status, _, _ = self.request("OPTIONS", "/api/bug-reports", headers={"Origin": OTHER_ORIGIN})
        self.assertEqual(status, 403)

    # -- anonymous submission ------------------------------------------------

    def test_anonymous_capability_submission_is_sanitized_and_persisted(self):
        token = self.capability()["capability"]
        payload = self.payload("crashed with token " + FAKE_TOKEN + " on ~/<REDACTED_PATH>")
        payload.update({"macAddress": FAKE_MAC, "accessToken": FAKE_TOKEN, "password": "hunter2"})
        status, _, data = self.json(
            "POST",
            "/api/bug-reports",
            payload,
            headers={"Origin": ALLOWED_ORIGIN, bug_report.SUPPORT_CAPABILITY_HEADER: token},
        )
        self.assertEqual(status, 201, data)
        self.assertTrue(data["ok"])
        self.assertIn("id", data)
        with app.db() as connection:
            row = connection.execute(
                "SELECT * FROM bug_reports WHERE id=?", (data["id"],)
            ).fetchone()
        self.assertIsNone(row["user_id"], "an anonymous report must not be attached to an account")
        stored = row["payload"]
        for forbidden in ("accessToken", "macAddress", "password", FAKE_TOKEN, FAKE_MAC, "developer", "game.nds"):
            self.assertNotIn(forbidden, stored)
        self.assertIn("redacted", stored)
        # The capability was spent once.
        with app.db() as connection:
            uses = connection.execute(
                "SELECT uses FROM support_capabilities WHERE token_hash=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            ).fetchone()["uses"]
        self.assertEqual(uses, 1)

    def test_submission_without_a_capability_is_rejected(self):
        status, _, data = self.json("POST", "/api/bug-reports", self.payload("x"), headers={"Origin": ALLOWED_ORIGIN})
        self.assertEqual(status, 401)
        self.assertNotIn("id", data)

    def test_unknown_or_replayed_beyond_the_limit_capability_is_rejected(self):
        status, _, _ = self.json(
            "POST",
            "/api/bug-reports",
            self.payload("x"),
            headers={bug_report.SUPPORT_CAPABILITY_HEADER: "not-a-real-token"},
        )
        self.assertEqual(status, 401)

        token = self.capability()["capability"]
        headers = {"Origin": ALLOWED_ORIGIN, bug_report.SUPPORT_CAPABILITY_HEADER: token}
        for index in range(bug_report.CAPABILITY_MAX_USES):
            status, _, data = self.json("POST", "/api/bug-reports", self.payload("report %d" % index), headers)
            self.assertEqual(status, 201, data)
        status, _, _ = self.json("POST", "/api/bug-reports", self.payload("one too many"), headers)
        self.assertEqual(status, 401, "a spent capability must not be reusable")

    def test_expired_capability_is_rejected(self):
        token, digest = bug_report.new_support_capability()
        with app.db() as connection:
            connection.execute(
                "INSERT INTO support_capabilities(token_hash,origin,created_at,expires_at,uses,max_uses) VALUES(?,?,?,?,?,?)",
                (digest, ALLOWED_ORIGIN, int(time.time()) - 60, int(time.time()) - 1, 0, 5),
            )
        status, _, _ = self.json(
            "POST",
            "/api/bug-reports",
            self.payload("x"),
            headers={"Origin": ALLOWED_ORIGIN, bug_report.SUPPORT_CAPABILITY_HEADER: token},
        )
        self.assertEqual(status, 401)

    def test_capability_is_scoped_to_its_issuing_origin(self):
        token = self.capability(ALLOWED_ORIGIN)["capability"]
        for origin in (OTHER_ORIGIN, None):
            headers = {bug_report.SUPPORT_CAPABILITY_HEADER: token}
            if origin is not None:
                headers["Origin"] = origin
            with self.subTest(origin=origin):
                status, _, data = self.json(
                    "POST", "/api/bug-reports", self.payload("cross-origin replay"), headers=headers
                )
                self.assertEqual(status, 401)
                self.assertNotIn("id", data)
        # A refused replay must not spend one of the finite uses.
        with app.db() as connection:
            uses = connection.execute(
                "SELECT uses FROM support_capabilities WHERE token_hash=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            ).fetchone()["uses"]
        self.assertEqual(uses, 0)
        # The issuing allowlisted origin still succeeds.
        status, _, data = self.json(
            "POST",
            "/api/bug-reports",
            self.payload("legit"),
            headers={"Origin": ALLOWED_ORIGIN, bug_report.SUPPORT_CAPABILITY_HEADER: token},
        )
        self.assertEqual(status, 201, data)

    def test_capability_is_bound_per_origin_when_several_origins_are_allowlisted(self):
        second_origin = "https://second.example"
        with patch.object(app, "SUPPORT_ALLOWED_ORIGINS", (ALLOWED_ORIGIN, second_origin)):
            token = self.capability(ALLOWED_ORIGIN)["capability"]
            # A capability issued through one allowlisted origin is not usable
            # from another allowlisted origin: the allowlist entry is per-origin,
            # not a deployment-wide grant.
            status, _, data = self.json(
                "POST",
                "/api/bug-reports",
                self.payload("cross allowlisted origin"),
                headers={"Origin": second_origin, bug_report.SUPPORT_CAPABILITY_HEADER: token},
            )
            self.assertEqual(status, 401)
            self.assertNotIn("id", data)
            status, _, data = self.json(
                "POST",
                "/api/bug-reports",
                self.payload("legit"),
                headers={"Origin": ALLOWED_ORIGIN, bug_report.SUPPORT_CAPABILITY_HEADER: token},
            )
            self.assertEqual(status, 201, data)

    # -- existing account path is untouched ----------------------------------

    def register(self, name):
        """Register a user and return their session cookie."""

        status, received, raw = self.request(
            "POST",
            "/api/register",
            {"name": name, "display_name": name, "password": name + "-pass-123",
             "confirm": name + "-pass-123"},
        )
        self.assertEqual(status, 201, raw)
        for header, value in received.items():
            if header.lower() == "set-cookie" and "an3_session=" in value:
                return value.split(";", 1)[0]
        self.fail("registration did not set a session cookie")

    def csrf(self, cookie):
        status, _, page = self.request("GET", "/bug-report", headers={"Cookie": cookie})
        self.assertEqual(status, 200)
        import re

        match = re.search(rb'<meta name="csrf-token" content="([^"]+)"', page)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def test_authenticated_cookie_csrf_path_still_works(self):
        cookie = self.register("support-user")
        status, _, data = self.json(
            "POST",
            "/api/bug-reports",
            self.payload("account report"),
            headers={"Cookie": cookie, "X-CSRF-Token": self.csrf(cookie)},
        )
        self.assertEqual(status, 201, data)
        with app.db() as connection:
            row = connection.execute(
                "SELECT user_id FROM bug_reports WHERE id=?", (data["id"],)
            ).fetchone()
        self.assertIsNotNone(row["user_id"])

    def test_authenticated_submit_still_requires_csrf(self):
        cookie = self.register("support-csrf")
        status, _, _ = self.json(
            "POST",
            "/api/bug-reports",
            self.payload("no csrf"),
            headers={"Cookie": cookie},
        )
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
