# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Goal-1 server controls: CSP/XSS escaping and request-derived filesystem paths.

This module pins the two remaining Goal-1 controls for the server security
audit:

* Output encoding. Every stored/model value that reaches a rendered page is
  escaped exactly once with ``app.esc`` (``html.escape(..., quote=True)``), so a
  comment, issue report, bug report or game field carrying markup is rendered as
  text. The player CSP is asserted here too: no wildcard source, no inline
  script, and ``object-src``/``base-uri``/``frame-ancestors`` stay locked down.
* Path containment. ``app.safe_data_path`` is the single chokepoint for every
  request-/model-derived relative path, static serving and custom-game archive
  extraction both route through it, and both must refuse traversal instead of
  reading or writing outside their root.

The tests are behavioral: they call the real renderers against a real SQLite
schema and exercise the real static-serving/extraction code paths.
"""

import html
import io
import os
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import app

CANARY = "<script>alert('an3-xss-canary')</script>"
ESCAPED_CANARY = html.escape(CANARY, quote=True)


def stub_handler():
    """A Handler instance wired for header/body capture without a socket.

    ``serve_static`` only needs ``send_response``/``send_header``/
    ``end_headers``/``wfile`` plus the request attributes used by
    ``send_bytes``; running the real ``BaseHTTPRequestHandler.__init__`` would
    require a live socket, so the bare instance is populated by hand.
    """

    handler = app.Handler.__new__(app.Handler)
    handler.command = "GET"
    handler.close_connection = False
    handler.headers = {}
    handler._cors_origin = ""
    handler.wfile = io.BytesIO()
    handler.statuses = []
    handler.header_pairs = []

    def send_response(code, message=None):
        handler.statuses.append(int(code))

    def send_header(key, value):
        handler.header_pairs.append((key, value))

    handler.send_response = send_response
    handler.send_header = send_header
    handler.end_headers = lambda: None
    return handler


class SafeDataPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="an3-safe-path-")
        self.root = self.temp.name
        os.makedirs(os.path.join(self.root, "a"), exist_ok=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_accepts_a_nested_relative_path(self):
        self.assertEqual(
            app.safe_data_path(self.root, "a/file.bin"),
            os.path.abspath(os.path.join(self.root, "a", "file.bin")),
        )

    def test_an_empty_relative_path_resolves_to_the_root(self):
        self.assertEqual(app.safe_data_path(self.root, ""), os.path.abspath(self.root))

    def test_rejects_parent_directory_escape(self):
        for relative in ("../evil", "a/../../evil", "..", "../../etc/passwd"):
            with self.subTest(relative=relative):
                with self.assertRaises(ValueError):
                    app.safe_data_path(self.root, relative)

    def test_rejects_an_absolute_path(self):
        with self.assertRaises(ValueError):
            app.safe_data_path(self.root, "/etc/passwd")

    def test_rejects_a_sibling_that_shares_the_root_prefix(self):
        # ``/tmp/x/root`` is not a parent of ``/tmp/x/root-evil``.
        with self.assertRaises(ValueError):
            app.safe_data_path(self.root, "../" + os.path.basename(self.root) + "-evil/x")


class StaticServingTraversalTests(unittest.TestCase):
    def _serve(self, relative):
        handler = stub_handler()
        handler.serve_static(app.STATIC_DIR, relative)
        return handler

    def test_traversal_relative_paths_return_404(self):
        for relative in (
            "../app.py",
            "a/../../app.py",
            "%2e%2e%2fapp.py",
            "..%2fapp.py",
            "%2e%2e/%2e%2e/etc/passwd",
            "/etc/passwd",
        ):
            with self.subTest(relative=relative):
                handler = self._serve(relative)
                self.assertEqual(handler.statuses, [404])
                self.assertEqual(handler.wfile.getvalue(), b"not found\n")

    def test_a_real_static_asset_is_still_served(self):
        handler = self._serve("site.css")
        self.assertEqual(handler.statuses, [200])
        self.assertGreater(len(handler.wfile.getvalue()), 0)


class CustomArchiveExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="an3-custom-extract-")
        self.root = self.temp.name
        self.custom_dir = os.path.join(self.root, "custom")
        os.makedirs(self.custom_dir, exist_ok=True)
        self.patcher = patch.object(app, "CUSTOM_DIR", self.custom_dir)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp.cleanup()

    def archive(self, entries):
        path = os.path.join(self.root, "game.zip")
        with zipfile.ZipFile(path, "w") as zf:
            for name, data in entries:
                zf.writestr(name, data)
        return path

    def test_zip_slip_entry_is_rejected_and_writes_nothing_outside_staging(self):
        archive = self.archive([("../../escaped.txt", b"pwned")])
        with self.assertRaises(ValueError):
            app.Handler.extract_custom(None, 7, archive, ".zip")
        # Nothing may land next to (or above) the per-game staging directory.
        self.assertFalse(os.path.exists(os.path.join(self.root, "escaped.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.custom_dir, "escaped.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.custom_dir, "7", "escaped.txt")))

    def test_absolute_entry_is_rejected(self):
        absolute_target = os.path.join(self.root, "absolute-escaped.txt")
        archive = self.archive([(absolute_target, b"pwned")])
        with self.assertRaises(ValueError):
            app.Handler.extract_custom(None, 8, archive, ".zip")
        self.assertFalse(os.path.exists(absolute_target))

    def test_a_well_formed_archive_extracts_index_and_nested_assets(self):
        archive = self.archive(
            [("index.html", b"<html>ok</html>"), ("assets/game.js", b"console.log(1)")]
        )
        app.Handler.extract_custom(None, 9, archive, ".zip")
        destination = os.path.join(self.custom_dir, "9")
        with open(os.path.join(destination, "index.html"), "rb") as handle:
            self.assertEqual(handle.read(), b"<html>ok</html>")
        with open(os.path.join(destination, "assets", "game.js"), "rb") as handle:
            self.assertEqual(handle.read(), b"console.log(1)")


class OutputEncodingTests(unittest.TestCase):
    def test_esc_quotes_every_html_metacharacter(self):
        self.assertEqual(
            app.esc("<a b=\"c\">&'</a>"),
            "&lt;a b=&quot;c&quot;&gt;&amp;&#x27;&lt;/a&gt;",
        )
        self.assertEqual(app.esc(None), "")

    def test_player_csp_has_no_wildcard_and_keeps_hardening_directives(self):
        csp = app.player_content_security_policy("")
        self.assertNotIn("*", csp)
        script_src = [part.strip() for part in csp.split(";") if part.strip().startswith("script-src")][0]
        self.assertNotIn("'unsafe-inline'", script_src)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("base-uri 'self'", csp)
        self.assertIn("frame-ancestors 'self'", csp)


class StoredContentEscapingTests(unittest.TestCase):
    """The real page renderers escape stored comments, reports and bug reports."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="an3-escaping-")
        root = self.temp.name
        self.patches = [
            patch.object(app, "ENVIRONMENT", "staging"),
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
        app.init_db()
        with app.db() as conn:
            conn.execute(
                "INSERT INTO users(id,name,display_name,password_hash,role,created_at) "
                "VALUES(1,'xssadmin','<b>Admin</b>','hash','admin',1)"
            )
            conn.execute(
                "INSERT INTO games(id,slug,title_vi,title_en,description_vi,description_en,"
                "system,rom_path,rom_name,cover_path,file_size,published,experimental,"
                "system_auto,created_at,updated_at) "
                "VALUES(1,'xss-game',?,?,?,?,'gba','','','',0,1,0,0,1,1)",
                (CANARY, CANARY, CANARY, CANARY),
            )
            conn.execute(
                "INSERT INTO comments(user_id,game_id,body,created_at) VALUES(1,1,?,1)",
                (CANARY,),
            )
            conn.execute(
                "INSERT INTO reports(user_id,game_id,category,body,status,created_at,updated_at) "
                "VALUES(1,1,'other',?,'open',1,1)",
                (CANARY,),
            )
            conn.execute(
                "INSERT INTO bug_reports(user_id,fingerprint,app_version,build_id,platform,"
                "emulator_system,game_title,game_identifier,description,payload,status,created_at) "
                "VALUES(1,'fp','1.0','build',?,?,?,?,?,?,'open',1)",
                (CANARY, CANARY, CANARY, CANARY, CANARY, CANARY),
            )
        with app.db() as conn:
            self.game = conn.execute("SELECT * FROM games WHERE id=1").fetchone()
            self.user = conn.execute("SELECT * FROM users WHERE id=1").fetchone()

    def tearDown(self):
        for active in self.patches:
            active.stop()
        self.temp.cleanup()

    def test_game_page_escapes_stored_comment_and_game_fields(self):
        rendered = app.game_page(self.game, "en", self.user, "csrf-token")
        self.assertNotIn(CANARY, rendered)
        self.assertIn(ESCAPED_CANARY, rendered)
        self.assertNotIn("<b>Admin</b>", rendered)
        self.assertIn("&lt;b&gt;Admin&lt;/b&gt;", rendered)

    def test_admin_page_escapes_bug_report_and_issue_content(self):
        rendered = app.admin_page("en", self.user, "csrf-token")
        self.assertNotIn(CANARY, rendered)
        self.assertIn(ESCAPED_CANARY, rendered)


if __name__ == "__main__":
    unittest.main()
