# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import app


class ReleaseFreshnessTests(unittest.TestCase):
    def test_same_filename_new_bytes_changes_identity_and_rejects_old_link(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.exe"
            old = b"old candidate"
            new = b"new candidate"
            path.write_bytes(old)
            entry = {"version": "1", "platform": "Test", "architecture": "x64",
                     "format": "EXE", "filename": path.name, "size": len(old),
                     "sha256": hashlib.sha256(old).hexdigest(),
                     "signature_status": "test", "runtime_status": "test"}
            with patch.object(app, "NATIVE_OFFLINE_RELEASE_DIR", directory), \
                 patch.object(app, "NATIVE_RELEASE_CATALOG", (entry,)), \
                 patch.object(app, "ENVIRONMENT", "staging"):
                server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                def request(url):
                    connection = http.client.HTTPConnection(*server.server_address, timeout=5)
                    connection.request("GET", url)
                    response = connection.getresponse()
                    result = response.status, dict(response.getheaders()), response.read()
                    connection.close()
                    return result
                try:
                    old_id = app.native_release_identity()
                    old_url = app.native_artifact_manifest()["artifacts"][0]["download_url"]
                    self.assertEqual(request(old_url)[2], old)
                    path.write_bytes(new)
                    self.assertIsNone(app.published_native_release(path.name))
                    entry["sha256"] = hashlib.sha256(new).hexdigest()
                    new_id = app.native_release_identity()
                    self.assertNotEqual(old_id, new_id)
                    self.assertEqual(request(old_url)[0], 404)
                    new_url = app.native_artifact_manifest()["artifacts"][0]["download_url"]
                    status, headers, body = request(new_url)
                    self.assertEqual((status, body), (200, new))
                    self.assertEqual(headers["Cache-Control"], "no-store")
                    manifest = json.loads(request("/download-app/artifacts.json")[2])
                    health = json.loads(request("/health")[2])
                    self.assertEqual(manifest["release_id"], new_id)
                    self.assertEqual(health["release_id"], new_id)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()

    def test_platform_resource_overrides_keep_native_binaries_separate(self):
        root = Path(__file__).resolve().parents[1] / "native-offline/src-tauri"
        common = json.loads((root / "tauri.conf.json").read_text())["bundle"]["resources"]
        mac = json.loads((root / "tauri.macos.conf.json").read_text())["bundle"]["resources"]
        windows = json.loads((root / "tauri.windows.conf.json").read_text())["bundle"]["resources"]
        self.assertFalse(any("macos-arm64" in source for source in common))
        self.assertFalse(any("macos-arm64" in source for source in windows))
        self.assertTrue(any("libMoltenVK.dylib" in source for source in mac))
        self.assertTrue(any("runtime/windows-x64" in value for value in windows.values()))
        windows_manifest = json.loads((root.parent / "vendor/libretro/windows-x64/manifest.json").read_text())
        self.assertEqual(
            sorted(core["coreName"] for core in windows_manifest["cores"]),
            ["azahar_libretro.dll", "melondsds_libretro.dll", "mgba_libretro.dll"],
        )
