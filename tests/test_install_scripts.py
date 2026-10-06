# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Linux install scripts the download page advertises must exist and serve.

`app.py` links `/install/install-deb.sh` and `/install/install-flatpak.sh` from
the download page, and `deploy/update-production.sh` requires both files in a
release archive. They were absent from the published tree, so the download page
raised `FileNotFoundError` out of `serve_file` and dropped the connection, and
production packaging failed on a missing `scripts` path. These checks pin the
files, their executability, their release-catalog contract, and the served
bytes, so the path cannot silently disappear again.
"""

import http.client
import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import app


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = {
    "/install/install-deb.sh": ROOT / "scripts/install/install-deb.sh",
    "/install/install-flatpak.sh": ROOT / "scripts/install/install-flatpak.sh",
}


class InstallScriptTests(unittest.TestCase):
    def test_both_install_scripts_exist_and_are_executable(self):
        for route, path in SCRIPTS.items():
            with self.subTest(route=route):
                self.assertTrue(path.is_file(), f"missing install script: {path}")
                self.assertTrue(
                    os.access(path, os.X_OK), f"install script is not executable: {path}"
                )

    def test_scripts_are_valid_bash_and_self_identifying(self):
        for route, path in SCRIPTS.items():
            with self.subTest(route=route):
                syntax = subprocess.run(
                    ["bash", "-n", str(path)], capture_output=True, text=True
                )
                self.assertEqual(syntax.returncode, 0, syntax.stderr)
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("#!/usr/bin/env bash"))
                self.assertIn("SPDX-License-Identifier: GPL-3.0-or-later", text)
                self.assertIn("--base-url", text)

    def test_scripts_resolve_the_release_catalog_rather_than_hardcoding_it(self):
        for route, path in SCRIPTS.items():
            with self.subTest(route=route):
                text = path.read_text(encoding="utf-8")
                self.assertIn("/download-app/artifacts.json", text)
                self.assertIn("sha256", text.lower())
                # No release version literal: the catalog is the only source.
                self.assertNotRegex(text, r"\d+\.\d+\.\d+-(linux|amd64)")

    def test_deploy_scripts_package_the_install_scripts(self):
        # The packaging allowlist ships the whole `scripts` tree; the updater
        # must then see both installer files by exact path.
        packaging = (ROOT / "deploy" / "package-production.sh").read_text(encoding="utf-8")
        self.assertRegex(packaging, r"(?m)static deploy README\.md scripts ")
        update = (ROOT / "deploy" / "update-production.sh").read_text(encoding="utf-8")
        for name in ("install-deb.sh", "install-flatpak.sh"):
            with self.subTest(name=name):
                self.assertIn(f'"$TMP/scripts/install/{name}"', update)

    def test_download_page_serves_both_scripts(self):
        with tempfile.TemporaryDirectory(prefix="an3-install-") as root:
            with patch.object(app, "DATA_DIR", root), \
                 patch.object(app, "DB_PATH", os.path.join(root, "arcade.db")), \
                 patch.object(app, "ENVIRONMENT", "staging"):
                app.init_db()
                server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    for route, path in SCRIPTS.items():
                        connection = http.client.HTTPConnection(
                            *server.server_address, timeout=5
                        )
                        connection.request("GET", route)
                        response = connection.getresponse()
                        body = response.read()
                        connection.close()
                        with self.subTest(route=route):
                            self.assertEqual(response.status, 200)
                            self.assertEqual(body, path.read_bytes())
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()

    def test_download_page_advertises_both_install_scripts(self):
        with tempfile.TemporaryDirectory(prefix="an3-install-") as root:
            with patch.object(app, "DATA_DIR", root), \
                 patch.object(app, "DB_PATH", os.path.join(root, "arcade.db")), \
                 patch.object(app, "ENVIRONMENT", "staging"):
                app.init_db()
                server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    connection = http.client.HTTPConnection(
                        *server.server_address, timeout=5
                    )
                    connection.request("GET", "/download-app")
                    response = connection.getresponse()
                    body = response.read().decode("utf-8", "replace")
                    connection.close()
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()
        for route in SCRIPTS:
            self.assertIn(route, body, f"download page does not link {route}")
        self.assertIn("--base-url", body)


if __name__ == "__main__":
    unittest.main()