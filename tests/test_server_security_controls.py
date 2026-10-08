# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Goal-1 server controls: CSP/XSS escaping and request-derived filesystem paths.

This module pins the two remaining Goal-1 controls for the server security
audit:

* Output encoding. Every active model value that reaches a rendered page is
  escaped exactly once with ``app.esc`` (``html.escape(..., quote=True)``), so a
  game field carrying markup is rendered as text. The player CSP is asserted
  here too: no wildcard source, no inline
  script, and ``object-src``/``base-uri``/``frame-ancestors`` stay locked down.
* Path containment. ``app.safe_data_path`` keeps request-/model-derived paths
  inside their configured roots, and static serving must refuse traversal.

The tests are behavioral: they call the real renderer against a real SQLite
schema and exercise real static-serving paths.
"""

import html
import io
import os
import tempfile
import unittest
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
    """The active public game page escapes stored game fields."""

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
            patch.object(app, "EMULATOR_CACHE_DIR", os.path.join(root, "emulatorjs-cache")),
            patch.object(app, "PREPARED_ROM_DIR", os.path.join(root, "prepared-roms")),
        ]
        for active in self.patches:
            active.start()
        app.init_db()
        with app.db() as conn:
            conn.execute(
                "INSERT INTO games(id,slug,title_vi,title_en,description_vi,description_en,"
                "system,rom_path,rom_name,cover_path,file_size,published,experimental,"
                "system_auto,created_at,updated_at) "
                "VALUES(1,'xss-game',?,?,?,?,'gba','','','',0,1,0,0,1,1)",
                (CANARY, CANARY, CANARY, CANARY),
            )
        with app.db() as conn:
            self.game = conn.execute("SELECT * FROM games WHERE id=1").fetchone()

    def tearDown(self):
        for active in self.patches:
            active.stop()
        self.temp.cleanup()

    def test_game_page_escapes_stored_game_fields(self):
        rendered = app.game_page(self.game, "en")
        self.assertNotIn(CANARY, rendered)
        self.assertIn(ESCAPED_CANARY, rendered)


if __name__ == "__main__":
    unittest.main()
