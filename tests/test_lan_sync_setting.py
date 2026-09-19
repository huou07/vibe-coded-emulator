# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Global LAN Sync switch: real gating, persistence, and scope limits.

The switch is a user-level feature gate that composes with the staging
``SYNC_ENABLED`` deployment gate. These tests cover:

* OFF blocks LAN discovery/advertising, planning, and transfer;
* ON reuses the existing sync engine and LAN transfer endpoints;
* Phone Controller networking is a separate service and stays up;
* the setting persists and survives a restart;
* unsupported sync kinds stay unsupported and Google Sync stays disabled.
"""

import base64
import hashlib
import http.client
import json
import os
import pathlib
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import app
import netcode


ROOT = pathlib.Path(__file__).resolve().parents[1]


class LanSyncSettingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="an3-lan-sync-test-")
        root = self.temp.name
        self.patches = [
            patch.object(app, "SYNC_ENABLED", True),
            patch.object(app, "GOOGLE_DRIVE_ENABLED", False),
            patch.object(app, "CONTROLLER_ENABLED", True),
            patch.object(app, "DB_PATH", os.path.join(root, "arcade.db")),
            patch.object(app, "ROM_DIR", os.path.join(root, "roms")),
            patch.object(app, "COVER_DIR", os.path.join(root, "covers")),
            patch.object(app, "SCREENSHOT_DIR", os.path.join(root, "screenshots")),
            patch.object(app, "CUSTOM_DIR", os.path.join(root, "custom")),
            patch.object(app, "UPLOAD_DIR", os.path.join(root, "uploads")),
            patch.object(app, "EMULATOR_CACHE_DIR", os.path.join(root, "emulatorjs-cache")),
            patch.object(app, "PREPARED_ROM_DIR", os.path.join(root, "prepared-roms")),
            patch.object(app, "LAN_PEERS", {}),
            patch.object(app, "LAN_BLOBS", {}),
            patch.object(app, "CONTROLLERS", {}),
            patch.object(app, "CONTROLLER_LIMITER", netcode.SlidingRateLimiter(limit=200, window_seconds=60)),
        ]
        for active in self.patches:
            active.start()
        app.init_db()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookies = {}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        for active in self.patches:
            active.stop()
        self.temp.cleanup()

    def request(self, method, path, payload=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        headers = {}
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{key}={value}" for key, value in self.cookies.items())
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        status, data = response.status, response.read()
        for name, value in response.getheaders():
            if name.lower() == "set-cookie":
                token = value.split(";")[0]
                if "=" in token:
                    key, raw = token.split("=", 1)
                    self.cookies[key] = raw
        connection.close()
        return status, data

    def settings(self):
        status, body = self.request("GET", "/api/sync/settings")
        self.assertEqual(status, 200)
        return json.loads(body)

    def set_lan(self, enabled):
        status, body = self.request("POST", "/api/sync/settings", {"lanSyncEnabled": enabled})
        self.assertEqual(status, 200, body)
        return json.loads(body)

    @staticmethod
    def blob(payload):
        return {
            "key": "gba/pokemon-emerald/slot1.state",
            "contentHash": hashlib.sha256(payload).hexdigest(),
            "data": base64.b64encode(payload).decode("ascii"),
        }

    # -- default, persistence, restart -------------------------------------

    def test_default_is_on_and_google_sync_is_visible_but_disabled(self):
        settings = self.settings()
        self.assertTrue(settings["lanSyncEnabled"])
        self.assertTrue(settings["lanSyncAvailable"])
        self.assertFalse(settings["googleSync"]["enabled"])
        self.assertEqual(settings["googleSync"]["status"], "coming-later")
        self.assertIn("not available yet", settings["googleSync"]["message"])
        drive = [mode for mode in settings["modes"] if mode["id"] == "drive"][0]
        self.assertFalse(drive["available"])
        self.assertEqual(drive["detail"], "Coming later")

    def test_setting_persists_and_survives_a_restart(self):
        self.set_lan(False)
        self.assertFalse(self.settings()["lanSyncEnabled"])
        # A restart re-runs init_db against the same database file.
        app.init_db()
        self.assertFalse(self.settings()["lanSyncEnabled"])
        self.set_lan(True)
        self.assertTrue(self.settings()["lanSyncEnabled"])

    def test_toggling_lan_off_does_not_reset_the_selected_mode(self):
        status, _ = self.request("POST", "/api/sync/settings", {"mode": "lan"})
        self.assertEqual(status, 200)
        self.set_lan(False)
        settings = self.settings()
        self.assertEqual(settings["mode"], "lan")
        self.assertFalse(settings["lanSyncEnabled"])

    def test_lan_content_and_mode_persist_together(self):
        status, body = self.request("POST", "/api/sync/settings", {
            "mode": "lan",
            "content": {"save": True, "state": False, "library": True, "rom": False},
            "lanSyncEnabled": True,
        })
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["lanSyncEnabled"])
        self.assertEqual(payload["content"], {"save": True, "state": False, "library": True, "rom": False})

    # -- OFF blocks sync behavior ------------------------------------------

    def test_lan_off_blocks_discovery_advertising_and_transfer(self):
        self.set_lan(False)
        status, body = self.request("POST", "/api/sync/lan/announce", {"deviceId": "device-aaaaaaaa", "name": "Living room"})
        self.assertEqual(status, 409, body)
        self.assertEqual(json.loads(body)["reason"], "lan-sync-disabled")
        self.assertEqual(self.request("GET", "/api/sync/lan/peers")[0], 409)
        self.assertEqual(self.request("POST", "/api/sync/lan/publish", {
            "deviceId": "device-aaaaaaaa", "kind": "state", "items": [self.blob(b"x")],
        })[0], 409)
        self.assertEqual(self.request("GET", "/api/sync/lan/manifest?kind=state")[0], 409)
        self.assertEqual(self.request("GET", "/api/sync/lan/blob?kind=state&key=k&hash=h")[0], 409)

    def test_lan_off_blocks_planning_and_conflict_resolution(self):
        self.set_lan(False)
        records = [{"key": "save", "local": {"content_hash": "a" * 64}}]
        status, body = self.request("POST", "/api/sync/plan", {"mode": "lan", "sameLan": True, "kind": "save", "records": records})
        self.assertEqual(status, 409, body)
        self.assertEqual(json.loads(body)["reason"], "lan-sync-disabled")
        status, body = self.request("POST", "/api/sync/resolve", {
            "key": "save-1", "kind": "save", "resolution": "local",
        })
        self.assertEqual(status, 409, body)
        # An OFF plan is harmless and still reports nothing to move.
        status, body = self.request("POST", "/api/sync/plan", {"mode": "off", "kind": "save", "records": records})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["transfers"], [])
        # The settings surface must stay reachable so the user can re-enable it.
        self.assertEqual(self.request("GET", "/api/sync/settings")[0], 200)

    # -- ON permits supported behavior -------------------------------------

    def test_lan_on_reuses_the_existing_engine_and_transfer_endpoints(self):
        status, _ = self.request("POST", "/api/sync/settings", {"mode": "lan"})
        self.assertEqual(status, 200)
        records = [{"key": "new-save", "local": {"content_hash": "a" * 64, "size": 10}}]
        status, body = self.request("POST", "/api/sync/plan", {"mode": "lan", "sameLan": True, "kind": "save", "records": records})
        self.assertEqual(status, 200)
        plan = json.loads(body)
        self.assertEqual(plan["transport"], "lan")
        self.assertEqual(plan["transfers"][0]["direction"], "upload")

        payload = b"save-state-bytes" * 50
        status, body = self.request("POST", "/api/sync/lan/publish", {
            "deviceId": "device-aaaaaaaa", "kind": "state", "items": [self.blob(payload)],
        })
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["stored"], 1)
        status, body = self.request("GET", "/api/sync/lan/manifest?kind=state")
        entry = json.loads(body)["items"][0]
        status, downloaded = self.request(
            "GET", f"/api/sync/lan/blob?kind=state&key={entry['key']}&hash={entry['contentHash']}"
        )
        self.assertEqual(downloaded, payload)
        status, body = self.request("POST", "/api/sync/lan/announce", {"deviceId": "device-aaaaaaaa", "name": "Living room"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["peers"][0]["deviceId"], "device-aaaaaaaa")

    # -- Phone Controller is separate --------------------------------------

    def test_lan_off_does_not_gate_phone_controller(self):
        self.set_lan(False)
        status, body = self.request("POST", "/api/controller/session", {"name": "Living room", "system": "gba"})
        self.assertEqual(status, 201, body)
        session = json.loads(body)
        self.assertIn("code", session)
        self.assertIn("hostToken", session)

        status, body = self.request("POST", "/api/controller/pair", {
            "code": session["code"], "deviceId": "phone-device",
        })
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["role"], "phone")

        status, body = self.request("GET", "/api/controller/hosts")
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["hosts"][0]["code"], session["code"])

    # -- deployment gate still wins ----------------------------------------

    def test_lan_sync_never_bypasses_the_staging_gate(self):
        with patch.object(app, "SYNC_ENABLED", False):
            for method, path, payload in (
                ("GET", "/api/sync/settings", None),
                ("POST", "/api/sync/settings", {"lanSyncEnabled": True}),
                ("POST", "/api/sync/plan", {"mode": "lan", "records": []}),
                ("POST", "/api/sync/lan/announce", {"deviceId": "device-aaaaaaaa"}),
                ("GET", "/api/sync/lan/peers", None),
                ("GET", "/sync", None),
            ):
                with self.subTest(path=path):
                    self.assertEqual(self.request(method, path, payload)[0], 404)

    # -- unsupported kinds and Google Sync --------------------------------

    def test_unsupported_kinds_stay_unsupported_while_lan_is_on(self):
        for kind in ("firmware", "keys", "nope"):
            with self.subTest(kind=kind):
                status, _ = self.request("POST", "/api/sync/lan/publish", {
                    "deviceId": "device-aaaaaaaa", "kind": kind, "items": [self.blob(b"secret")],
                })
                self.assertEqual(status, 400)
        records = [{"key": "fw", "local": {"content_hash": "a" * 64}}]
        status, body = self.request("POST", "/api/sync/plan", {"mode": "lan", "kind": "firmware", "records": records})
        self.assertEqual(status, 200)
        transfer = json.loads(body)["transfers"][0]
        self.assertEqual(transfer["direction"], "none")
        self.assertEqual(transfer["reason"], "not-eligible")

    def test_google_sync_stays_unimplemented_even_with_credentials(self):
        with patch.object(app, "GOOGLE_DRIVE_ENABLED", True):
            settings = self.settings()
            self.assertTrue(settings["googleSync"]["available"])
            self.assertFalse(settings["googleSync"]["enabled"])
            self.assertEqual(settings["googleSync"]["status"], "coming-later")


class LanSyncPageTests(unittest.TestCase):
    def test_page_and_script_expose_both_switches(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        for marker in (
            'id="syncLanEnabled"',
            'id="syncLanDetail"',
            'id="syncGoogleEnabled"',
            'id="syncGoogleDetail"',
        ):
            self.assertIn(marker, source)
        script = (ROOT / "static" / "sync.js").read_text(encoding="utf-8")
        self.assertIn("lanSyncEnabled", script)
        self.assertIn("syncLanEnabled", script)
        self.assertIn("syncGoogleEnabled", script)
        self.assertIn('"/api/sync/settings"', script)


if __name__ == "__main__":
    unittest.main()
