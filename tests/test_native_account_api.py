# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression guards for retired account and login routes."""

import http.client
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import app


class RetiredAccountApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="an3-retired-account-test-")
        root = self.temp.name
        directories = {
            "DATA_DIR": root,
            "DB_PATH": os.path.join(root, "arcade.db"),
            "ROM_DIR": os.path.join(root, "roms"),
            "COVER_DIR": os.path.join(root, "covers"),
            "SCREENSHOT_DIR": os.path.join(root, "screenshots"),
            "CUSTOM_DIR": os.path.join(root, "custom"),
            "EMULATOR_CACHE_DIR": os.path.join(root, "emulatorjs-cache"),
            "PREPARED_ROM_DIR": os.path.join(root, "prepared-roms"),
        }
        self.patches = [patch.object(app, name, value) for name, value in directories.items()]
        self.patches.append(patch.object(app, "SUPPORT_ALLOWED_ORIGINS", ("https://appassets.androidplatform.net",)))
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

    def request(self, method, path, payload=None, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        request_headers = dict(headers or {})
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            request_headers["Content-Type"] = "application/json"
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        status, raw = response.status, response.read()
        received = {key.lower(): value for key, value in response.getheaders()}
        connection.close()
        return status, raw, received

    def test_account_pages_and_apis_are_gone(self):
        for path in ("/login", "/register", "/account", "/api/account/session", "/admin", "/bug-report"):
            with self.subTest(method="GET", path=path):
                status, _body, headers = self.request("GET", path)
                self.assertEqual(status, 404)
                self.assertNotIn("set-cookie", headers)

        for path in (
            "/api/register",
            "/api/login",
            "/api/logout",
            "/api/account/peer-proof",
            "/api/account/peer-proof/verify",
            "/api/account/display-name",
            "/api/games/1/rating",
            "/api/games/1/favorite",
        ):
            with self.subTest(method="POST", path=path):
                status, _body, headers = self.request("POST", path, {})
                self.assertEqual(status, 404)
                self.assertNotIn("set-cookie", headers)

    def test_old_account_cookie_is_never_authenticated(self):
        status, _body, _headers = self.request("GET", "/admin", headers={"Cookie": "an3_session=legacy-token"})
        self.assertEqual(status, 404)

    def test_account_origins_receive_no_credentialed_cors(self):
        origin = "https://tauri.localhost"
        status, _body, headers = self.request("OPTIONS", "/api/login", headers={"Origin": origin})
        self.assertEqual(status, 404)
        self.assertNotIn("access-control-allow-origin", headers)
        self.assertNotIn("access-control-allow-credentials", headers)
        status, _body, headers = self.request("GET", "/api/account/session", headers={"Origin": origin})
        self.assertEqual(status, 404)
        self.assertNotIn("access-control-allow-origin", headers)

    def test_fresh_database_does_not_create_account_sessions(self):
        with app.db() as connection:
            sessions = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions'").fetchone()
            users = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
        self.assertIsNone(sessions)
        self.assertEqual(users, 0)
        self.assertEqual(columns, {"id"})

    def test_legacy_credentials_and_sessions_are_removed(self):
        legacy_db = os.path.join(self.temp.name, "legacy.db")
        with sqlite3.connect(legacy_db) as connection:
            connection.executescript(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL DEFAULT '', password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user', created_at INTEGER NOT NULL
                );
                CREATE TABLE sessions (
                    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                    csrf TEXT NOT NULL, expires_at INTEGER NOT NULL
                );
                CREATE TABLE favorites (
                    user_id INTEGER NOT NULL REFERENCES users(id), game_id INTEGER NOT NULL,
                    created_at INTEGER NOT NULL, PRIMARY KEY(user_id, game_id)
                );
                INSERT INTO users VALUES(7,'legacy','Legacy','scrypt$secret','user',1);
                INSERT INTO sessions VALUES('legacy-token',7,'csrf',9999999999);
                INSERT INTO favorites VALUES(7,1,1);
                """
            )

        with patch.object(app, "DB_PATH", legacy_db):
            app.init_db()

        with patch.object(app, "DB_PATH", legacy_db):
            with app.db() as connection:
                columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
                user_ids = [row["id"] for row in connection.execute("SELECT id FROM users")]
                sessions = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions'").fetchone()
                favorite_user_tables = {row["table"] for row in connection.execute("PRAGMA foreign_key_list(favorites)")}
                violations = connection.execute("PRAGMA foreign_key_check").fetchall()

        self.assertEqual(columns, {"id"})
        self.assertEqual(user_ids, [7])
        self.assertIsNone(sessions)
        self.assertIn("users", favorite_user_tables)
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
