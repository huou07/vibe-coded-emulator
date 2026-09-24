# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import http.client
import http.server
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.py")
PORT = 18795
FAKE_TOKEN = "ghp_" + "A" * 36
FAKE_PAT = "github_pat_" + "B" * 30
FAKE_MAC = "de:ad:be:ef:00:11"


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class FakeGitHubHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        self.rfile.read(length)
        self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"message":"service unavailable"}')

    def log_message(self, *args):
        return


class Client:
    def __init__(self, port):
        self.port = port
        self.cookie = ""

    def request(self, method, path, payload=None, csrf=None):
        body = None if payload is None else json.dumps(payload).encode()
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.cookie:
            headers["Cookie"] = self.cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        raw = response.read()
        cookie = response.getheader("Set-Cookie")
        if cookie and "an3_session=" in cookie:
            self.cookie = cookie.split(";", 1)[0]
        connection.close()
        return response.status, dict(response.getheaders()), raw

    def json(self, method, path, payload=None, csrf=None):
        status, _, raw = self.request(method, path, payload, csrf)
        try:
            return status, json.loads(raw)
        except ValueError:
            return status, {}

    def csrf_token(self):
        status, _, raw = self.request("GET", "/bug-report")
        if status != 200:
            return ""
        match = re.search(rb'<meta name="csrf-token" content="([^"]+)"', raw)
        return match.group(1).decode() if match else ""


class BugReportApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.mkdtemp(prefix="an3-bug-report-")
        cls.data_dir = os.path.join(cls.temp, "data")
        cls.db_path = os.path.join(cls.data_dir, "arcade.db")
        cls.api_port = free_port()
        cls.api = http.server.ThreadingHTTPServer(("127.0.0.1", cls.api_port), FakeGitHubHandler)
        cls.api_thread = threading.Thread(target=cls.api.serve_forever, daemon=True)
        cls.api_thread.start()
        env = os.environ.copy()
        env.update(
            {
                "AN3_DATA_DIR": cls.data_dir,
                "AN3_PORT": str(PORT),
                "AN3_ENVIRONMENT": "staging",
                "AN3_ADMIN_NAME": "bug-admin",
                "AN3_ADMIN_PASSWORD": "bug-admin-pass-123",
                "AN3_GITHUB_ISSUES_TOKEN": FAKE_TOKEN,
                "AN3_GITHUB_REPOSITORY": "owner/repo",
                "AN3_GITHUB_API_BASE": "http://127.0.0.1:%d" % cls.api_port,
            }
        )
        cls.server = subprocess.Popen(
            [sys.executable, APP], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                if Client(PORT).request("GET", "/health")[0] == 200:
                    return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("bug report test server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        try:
            cls.server.wait(timeout=8)
        except subprocess.TimeoutExpired:
            cls.server.kill()
        cls.api.shutdown()
        import shutil

        shutil.rmtree(cls.temp)

    def register(self, name):
        client = Client(PORT)
        status, _ = client.json(
            "POST",
            "/api/register",
            {"name": name, "display_name": name, "password": name + "-pass-123", "confirm": name + "-pass-123"},
        )
        self.assertEqual(status, 201)
        return client

    def seed_payload(self, description):
        return {
            "description": description,
            "platform": "Android",
            "emulatorSystem": "nds",
            "coreName": "melonds",
            "gameTitle": "Test Game",
            "userAgent": "Mozilla/5.0",
        }

    def fingerprint_for(self, payload):
        import bug_report

        status, _, raw = Client(PORT).request("GET", "/health")
        health = json.loads(raw)
        report = bug_report.build_report(
            payload,
            build_id=health["asset_version"],
            app_version=health["asset_version"],
            channel=health["environment"],
        )
        return bug_report.issue_fingerprint(report)

    def db(self):
        connection = sqlite3.connect(self.db_path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    def test_page_requires_login_and_post_requires_authentication(self):
        anonymous = Client(PORT)
        status, headers, _ = anonymous.request("GET", "/bug-report")
        self.assertEqual(status, 303)
        self.assertIn("/login", headers.get("Location", ""))
        self.assertEqual(anonymous.request("POST", "/api/bug-reports", self.seed_payload("x"))[0], 401)

    def test_csrf_is_required(self):
        client = self.register("csrf-user")
        status, _ = client.json("POST", "/api/bug-reports", self.seed_payload("no csrf"))
        self.assertEqual(status, 403)

    def test_report_is_sanitized_stored_and_survives_issue_failure(self):
        client = self.register("sanitize-user")
        csrf = client.csrf_token()
        self.assertTrue(csrf)
        payload = self.seed_payload("game crashed after load")
        payload.update(
            {
                "romPath": "~/<REDACTED_PATH>",
                "tomPath": "ignored",
                "accessToken": FAKE_TOKEN,
                "refreshToken": "refresh-value",
                "saveState": "AAECAwQ=",
                "macAddress": FAKE_MAC,
                "password": "hunter2",
                "gpu": "Adreno 740",
                "logs": ["boot ok", "token " + FAKE_PAT, "ip 10.0.0.7"],
                "description": "crashed with token " + FAKE_TOKEN + " on ~/<REDACTED_PATH>",
            }
        )
        status, data = client.json("POST", "/api/bug-reports", payload, csrf)
        self.assertEqual(status, 201)
        self.assertTrue(data["ok"])
        self.assertIn("id", data)
        # GitHub returned 503, so the issue was not created, but the report is stored.
        self.assertTrue(data["issue"]["attempted"])
        self.assertFalse(data["issue"]["created"])

        with self.db() as connection:
            row = connection.execute("SELECT * FROM bug_reports WHERE id=?", (data["id"],)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "open")
        stored = row["payload"]
        for forbidden in ("romPath", "accessToken", "refreshToken", "saveState", "macAddress", "password", FAKE_TOKEN, FAKE_PAT, FAKE_MAC):
            self.assertNotIn(forbidden, stored)
        self.assertNotIn("developer", stored)
        self.assertNotIn("hunter2", stored)
        self.assertNotIn("game.nds", stored)
        self.assertIn("redacted", stored)
        serialized = json.dumps(dict(row))
        self.assertNotIn(FAKE_TOKEN, serialized)

        # The page must never expose the server-only GitHub token.
        status, _, page = client.request("GET", "/bug-report")
        self.assertEqual(status, 200)
        self.assertNotIn(FAKE_TOKEN.encode(), page)
        self.assertNotIn(b"Authorization", page)

        # Admin dashboard lists the sanitized report.
        admin = Client(PORT)
        self.assertEqual(admin.json("POST", "/api/login", {"name": "bug-admin", "password": "bug-admin-pass-123"})[0], 200)
        status, _, admin_page = admin.request("GET", "/admin")
        self.assertEqual(status, 200)
        self.assertIn(b"Bug reports", admin_page)
        self.assertIn(b"Sanitized diagnostics", admin_page)
        self.assertIn(b"sanitize-user", admin_page)
        self.assertNotIn(FAKE_TOKEN.encode(), admin_page)
        self.assertNotIn(b"developer", admin_page)

    def test_duplicate_report_reuses_existing_issue(self):
        client = self.register("duplicate-user")
        csrf = client.csrf_token()
        payload = self.seed_payload("same problem twice")
        fingerprint = self.fingerprint_for(payload)
        with self.db() as connection:
            user = connection.execute("SELECT id FROM users WHERE name=?", ("duplicate-user",)).fetchone()
            connection.execute(
                """INSERT INTO bug_reports(user_id,fingerprint,report_schema_version,app_version,build_id,platform,
                   emulator_system,core_name,game_title,game_identifier,description,payload,status,
                   github_issue_number,github_issue_url,created_at)
                   VALUES(?,?,1,'','','Android','nds','melonds','','','',?, 'open',7,'https://github.com/owner/repo/issues/7',?)""",
                (user["id"], fingerprint, "seeded", int(time.time()) - 300),
            )
            connection.commit()
        status, data = client.json("POST", "/api/bug-reports", payload, csrf)
        self.assertEqual(status, 201)
        self.assertTrue(data["issue"].get("duplicate"))
        self.assertEqual(data["issue"]["number"], 7)
        with self.db() as connection:
            row = connection.execute("SELECT * FROM bug_reports WHERE id=?", (data["id"],)).fetchone()
        self.assertEqual(row["github_issue_url"], "https://github.com/owner/repo/issues/7")
        self.assertEqual(row["github_issue_number"], 7)

    def test_repeated_reports_are_rate_limited(self):
        client = self.register("rate-user")
        csrf = client.csrf_token()
        self.assertEqual(client.json("POST", "/api/bug-reports", self.seed_payload("first"), csrf)[0], 201)
        status, data = client.json("POST", "/api/bug-reports", self.seed_payload("second"), csrf)
        self.assertEqual(status, 429)
        self.assertIn("wait", data.get("error", "").lower())


if __name__ == "__main__":
    unittest.main()
