"""GPLv3 licensing transition: LICENSE, notices, SPDX headers and the UI route."""

import http.client
import pathlib
import threading
import unittest
from http.server import ThreadingHTTPServer

import app


ROOT = pathlib.Path(__file__).resolve().parents[1]


class LicenseFileTests(unittest.TestCase):
    def test_license_is_the_unmodified_gnu_gplv3_text(self):
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("                    GNU GENERAL PUBLIC LICENSE"))
        self.assertIn("Version 3, 29 June 2007", text)
        self.assertIn("TERMS AND CONDITIONS", text)
        self.assertIn("END OF TERMS AND CONDITIONS", text)
        self.assertIn("How to Apply These Terms to Your New Programs", text)
        # A truncated or edited license would lose these markers.
        self.assertGreater(len(text), 30000)

    def test_readme_states_the_gpl_terms(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("GPL-3.0-or-later", readme)
        self.assertIn("commercial", readme.lower())
        self.assertIn("modif", readme.lower())
        self.assertIn("redistribut", readme.lower())
        self.assertIn("LICENSE", readme)

    def test_third_party_notices_name_every_bundled_core_and_license(self):
        notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        for name, license_name in (
            ("Azahar", "GPL-2.0-or-later"),
            ("melonDS DS", "GPL-3.0-or-later"),
            ("mGBA", "MPL-2.0"),
            ("EmulatorJS", "GPL-3.0"),
            ("MoltenVK", "Apache-2.0"),
        ):
            with self.subTest(component=name):
                self.assertIn(name, notices)
                self.assertIn(license_name, notices)
        # The bundled native notices must carry the app's own license too.
        native_notices = (ROOT / "native-offline/THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("GPL-3.0-or-later", native_notices)

    def test_spdx_headers_on_original_sources_and_not_on_third_party(self):
        for relative in (
            "app.py",
            "netcode.py",
            "sync_engine.py",
            "google_sync.py",
            "static/player.js",
            "static/controller.js",
            "native-offline/src-tauri/src/lib.rs",
            "native-offline/src-tauri/src/controller_host.rs",
            "native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/ControllerClient.kt",
            "native-offline/native-runtime/core/libretro_host.cpp",
        ):
            with self.subTest(file=relative):
                head = (ROOT / relative).read_text(encoding="utf-8")[:400]
                self.assertIn("SPDX-License-Identifier: GPL-3.0-or-later", head)
        # Vendored third-party files must NOT be stamped with our license.
        for relative in ("qrcodegen.py", "native-offline/native-runtime/core/vendor/libretro.h"):
            with self.subTest(file=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertNotIn("SPDX-License-Identifier: GPL-3.0-or-later", text)

    def test_no_proprietary_license_reference_remains_in_the_app(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("LicenseRef-proprietary", source)


class LicenseRouteTests(unittest.TestCase):
    def setUp(self):
        import os
        import tempfile
        from unittest.mock import patch

        self.temp = tempfile.TemporaryDirectory(prefix="an3-license-test-")
        root = self.temp.name
        self.patches = [
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

    def get(self, path):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        connection.request("GET", path)
        response = connection.getresponse()
        status, headers, data = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return status, headers, data

    def test_licenses_page_lists_the_project_and_third_party_terms(self):
        status, headers, body = self.get("/licenses")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        text = body.decode("utf-8")
        self.assertIn("GPL-3.0-or-later", text)
        self.assertIn("Azahar Emulator Project", text)
        self.assertIn("/licenses/gpl-3.0.txt", text)

    def test_license_text_is_served(self):
        status, headers, body = self.get("/licenses/gpl-3.0.txt")
        self.assertEqual(status, 200)
        self.assertIn("text/plain", headers.get("Content-Type", ""))
        self.assertTrue(body.startswith(b"                    GNU GENERAL PUBLIC LICENSE"))


if __name__ == "__main__":
    unittest.main()
