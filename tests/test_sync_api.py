# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Staging-only cross-device sync: settings, planning, and LAN discovery.

The pure decision logic is covered by ``tests/test_sync_engine.py``; these
tests cover the app wiring: per-device mode persistence, the Drive gate, the
plan/conflict endpoints, and the subnet-scoped LAN peer registry.
"""

import http.client
import base64
import hashlib
import json
import os
import pathlib
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import app
import sync_engine


ROOT = pathlib.Path(__file__).resolve().parents[1]


class SyncApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="an3-sync-test-")
        root = self.temp.name
        self.patches = [
            patch.object(app, "SYNC_ENABLED", True),
            patch.object(app, "GOOGLE_DRIVE_ENABLED", False),
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

    # -- settings ----------------------------------------------------------

    def test_default_mode_is_off_and_persists_per_device(self):
        status, body = self.request("GET", "/api/sync/settings")
        self.assertEqual(status, 200)
        settings = json.loads(body)
        self.assertEqual(settings["mode"], "off")
        self.assertFalse(settings["driveConfigured"])
        self.assertEqual([mode["id"] for mode in settings["modes"]], ["auto", "lan", "drive", "off"])
        self.assertEqual([mode["label"] for mode in settings["modes"]][0], "Automatic")
        # ROM sync is off by default; every other content class is on.
        self.assertEqual(settings["content"], {"save": True, "state": True, "library": True, "rom": False})

        status, body = self.request("POST", "/api/sync/settings", {"mode": "lan"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["mode"], "lan")

        status, body = self.request("GET", "/api/sync/settings")
        self.assertEqual(json.loads(body)["mode"], "lan")

    def test_automatic_mode_is_available_without_drive_credentials(self):
        status, body = self.request("POST", "/api/sync/settings", {"mode": "auto"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["mode"], "auto")

    def test_content_toggles_persist_and_rom_warns(self):
        status, body = self.request("POST", "/api/sync/settings", {
            "mode": "auto",
            "content": {"save": True, "state": False, "library": True, "rom": True},
        })
        self.assertEqual(status, 200)
        settings = json.loads(body)
        self.assertEqual(settings["content"], {"save": True, "state": False, "library": True, "rom": True})
        rom_option = [option for option in settings["contentOptions"] if option["id"] == "rom"][0]
        self.assertIn("bandwidth", rom_option["warning"])

    def test_invalid_and_unconfigured_modes_are_rejected(self):
        status, _ = self.request("POST", "/api/sync/settings", {"mode": "bogus"})
        self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/sync/settings", {"mode": ""})
        self.assertEqual(status, 400)
        # Drive is unavailable until owner OAuth credentials exist.
        status, body = self.request("POST", "/api/sync/settings", {"mode": "drive"})
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(body)["reason"], "drive-unavailable")
        status, _ = self.request("POST", "/api/sync/settings", {"mode": "lan_drive"})
        self.assertEqual(status, 409)

    def test_drive_mode_is_accepted_when_credentials_are_configured(self):
        with patch.object(app, "GOOGLE_DRIVE_ENABLED", True):
            status, body = self.request("POST", "/api/sync/settings", {"mode": "lan_drive"})
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(body)["driveConfigured"])

    # -- planning ----------------------------------------------------------

    @staticmethod
    def record(key, **overrides):
        base = {"key": key}
        base.update(overrides)
        return base

    def test_plan_returns_the_engine_decision_per_file(self):
        records = [
            self.record("new-save", local={"content_hash": "a" * 64, "size": 10}),
            self.record("remote-save", remote={"content_hash": "b" * 64, "size": 11}),
            self.record("identical", local={"content_hash": "c" * 64}, remote={"content_hash": "c" * 64}),
            self.record("remote-edit", local={"content_hash": "d" * 64}, remote={"content_hash": "e" * 64}, last_synced_hash="d" * 64),
            self.record("conflict", local={"content_hash": "f" * 64}, remote={"content_hash": "0" * 64}, last_synced_hash="9" * 64),
        ]
        status, body = self.request("POST", "/api/sync/plan", {"mode": "lan", "sameLan": True, "kind": "save", "records": records})
        self.assertEqual(status, 200)
        plan = json.loads(body)
        self.assertEqual(plan["transport"], "lan")
        self.assertFalse(plan["clean"])
        directions = {transfer["key"]: transfer["direction"] for transfer in plan["transfers"]}
        self.assertEqual(directions["new-save"], "upload")
        self.assertEqual(directions["remote-save"], "download")
        self.assertEqual(directions["identical"], "none")
        self.assertEqual(directions["remote-edit"], "download")
        self.assertEqual(directions["conflict"], "conflict")
        self.assertEqual(plan["summary"]["conflicts"], 1)
        self.assertEqual(plan["summary"]["actions"], 4)

    def test_plan_off_moves_nothing_and_ineligible_kinds_are_refused(self):
        records = [self.record("save", local={"content_hash": "a" * 64})]
        status, body = self.request("POST", "/api/sync/plan", {"mode": "off", "records": records, "kind": "save"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["transfers"], [])

        status, body = self.request("POST", "/api/sync/plan", {"mode": "lan", "records": records, "kind": "firmware"})
        self.assertEqual(status, 200)
        transfer = json.loads(body)["transfers"][0]
        self.assertEqual(transfer["direction"], "none")
        self.assertEqual(transfer["reason"], "not-eligible")

    def test_plan_rejects_bad_manifests(self):
        status, _ = self.request("POST", "/api/sync/plan", {"mode": "lan", "kind": "nope", "records": []})
        self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/sync/plan", {"mode": "lan", "kind": "save", "records": "x"})
        self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/sync/plan", {"mode": "drive", "kind": "save", "records": []})
        self.assertEqual(status, 409)
        status, _ = self.request("POST", "/api/sync/plan", {"mode": "lan", "kind": "save", "records": [{"nokey": 1}]})
        self.assertEqual(status, 400)

    def test_conflict_resolution_keep_local_remote_or_both(self):
        for resolution, direction, has_copy in (("local", "upload", False), ("remote", "download", False), ("both", "upload", True)):
            with self.subTest(resolution=resolution):
                status, body = self.request("POST", "/api/sync/resolve", {
                    "key": "save-1", "kind": "save", "resolution": resolution,
                    "localHash": "a" * 64, "remoteHash": "b" * 64,
                })
                self.assertEqual(status, 200)
                payload = json.loads(body)
                self.assertEqual(payload["direction"], direction)
                self.assertEqual(bool(payload["copyKey"]), has_copy)
        status, _ = self.request("POST", "/api/sync/resolve", {"key": "save-1", "resolution": "guess"})
        self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/sync/resolve", {"resolution": "local"})
        self.assertEqual(status, 400)

    # -- LAN discovery -----------------------------------------------------

    def test_lan_announce_lists_same_subnet_peers(self):
        status, body = self.request("POST", "/api/sync/lan/announce", {"deviceId": "device-aaaaaaaa", "name": "Living room", "port": 8092})
        self.assertEqual(status, 200)
        peers = json.loads(body)["peers"]
        self.assertEqual([peer["deviceId"] for peer in peers], ["device-aaaaaaaa"])
        self.assertEqual(peers[0]["address"], "127.0.0.1")
        self.assertEqual(peers[0]["port"], 8092)

        status, body = self.request("GET", "/api/sync/lan/peers")
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body)["peers"]), 1)

    def test_lan_rejects_a_bad_device_id_and_port(self):
        status, _ = self.request("POST", "/api/sync/lan/announce", {"deviceId": "x"})
        self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/sync/lan/announce", {"deviceId": "device-bbbbbbbb", "port": 99999})
        self.assertEqual(status, 400)

    def test_lan_snapshot_is_subnet_scoped_and_reaps_expired(self):
        import time as clock
        now = clock.monotonic()
        app.LAN_PEERS.update({
            "local-device": {"name": "here", "ip": "192.0.2.10", "port": 1, "seen": now},
            "far-device": {"name": "away", "ip": "10.0.0.5", "port": 1, "seen": now},
            "stale-device": {"name": "old", "ip": "192.0.2.11", "port": 1, "seen": now - app.LAN_PEER_TTL_SECONDS - 5},
        })
        peers = app.lan_peer_snapshot("192.0.2.20", now=now)
        self.assertEqual([peer["deviceId"] for peer in peers], ["local-device"])
        self.assertNotIn("stale-device", app.LAN_PEERS)
        self.assertIn("far-device", app.LAN_PEERS)
        self.assertTrue(app.sync_same_subnet("192.0.2.4", "192.0.2.200"))
        self.assertFalse(app.sync_same_subnet("192.0.2.4", "198.51.100.200"))
        self.assertFalse(app.sync_same_subnet("::1", "192.0.2.4"))

    # -- LAN transfer ------------------------------------------------------

    @staticmethod
    def blob(payload: bytes):
        return {
            "key": "gba/pokemon-emerald/slot1.state",
            "contentHash": hashlib.sha256(payload).hexdigest(),
            "data": base64.b64encode(payload).decode("ascii"),
        }

    def publish(self, payload: bytes, *, kind="state", device="device-aaaaaaaa", **overrides):
        item = self.blob(payload)
        item.update(overrides)
        return self.request("POST", "/api/sync/lan/publish", {
            "deviceId": device, "kind": kind, "items": [item],
        })

    def test_lan_blob_publish_manifest_and_download_round_trip(self):
        payload = b"save-state-bytes" * 100
        status, body = self.publish(payload)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["stored"], 1)

        status, body = self.request("GET", "/api/sync/lan/manifest?kind=state")
        self.assertEqual(status, 200)
        manifest = json.loads(body)
        self.assertEqual(len(manifest["items"]), 1)
        entry = manifest["items"][0]
        self.assertEqual(entry["key"], "gba/pokemon-emerald/slot1.state")
        self.assertEqual(entry["size"], len(payload))
        self.assertEqual(entry["deviceId"], "device-aaaaaaaa")

        status, downloaded = self.request(
            "GET", f"/api/sync/lan/blob?kind=state&key={entry['key']}&hash={entry['contentHash']}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(downloaded, payload)
        self.assertEqual(hashlib.sha256(downloaded).hexdigest(), entry["contentHash"])

    def test_lan_blob_download_requires_the_exact_hash(self):
        payload = b"state"
        self.publish(payload)
        status, _ = self.request(
            "GET", "/api/sync/lan/blob?kind=state&key=gba/pokemon-emerald/slot1.state&hash=" + "0" * 64
        )
        self.assertEqual(status, 404)
        status, _ = self.request("GET", "/api/sync/lan/blob?kind=state&key=missing&hash=" + "0" * 64)
        self.assertEqual(status, 404)

    def test_lan_publish_rejects_ineligible_kinds_and_bad_hashes(self):
        payload = b"keys"
        status, _ = self.publish(payload, kind="firmware")
        self.assertEqual(status, 400)
        status, _ = self.publish(payload, kind="keys")
        self.assertEqual(status, 400)
        status, _ = self.publish(payload, kind="nope")
        self.assertEqual(status, 400)
        status, _ = self.publish(payload, contentHash="a" * 64)  # hash does not match the bytes
        self.assertEqual(status, 400)
        # A fabricated short hash is also rejected.
        status, _ = self.publish(payload, contentHash="ab")
        self.assertEqual(status, 400)

    def test_lan_publish_rejects_oversize_items(self):
        with patch.object(app, "LAN_BLOB_MAX_BYTES", 1024):
            status, _ = self.publish(b"x" * 2048)
        self.assertEqual(status, 413)

    def test_lan_transfer_is_disabled_in_production(self):
        with patch.object(app, "SYNC_ENABLED", False):
            self.assertEqual(self.request("POST", "/api/sync/lan/publish", {"deviceId": "device-aaaaaaaa", "kind": "state", "items": []})[0], 404)
            self.assertEqual(self.request("GET", "/api/sync/lan/manifest?kind=state")[0], 404)
            self.assertEqual(self.request("GET", "/api/sync/lan/blob?kind=state&key=k&hash=h")[0], 404)

    # -- gating ------------------------------------------------------------

    def test_production_serves_404_for_every_sync_surface(self):
        with patch.object(app, "SYNC_ENABLED", False):
            self.assertEqual(self.request("GET", "/api/sync/settings")[0], 404)
            self.assertEqual(self.request("POST", "/api/sync/settings", {"mode": "lan"})[0], 404)
            self.assertEqual(self.request("POST", "/api/sync/plan", {"records": []})[0], 404)
            self.assertEqual(self.request("POST", "/api/sync/resolve", {"key": "k", "resolution": "local"})[0], 404)
            self.assertEqual(self.request("POST", "/api/sync/lan/announce", {"deviceId": "device-aaaaaaaa"})[0], 404)
            self.assertEqual(self.request("GET", "/api/sync/lan/peers")[0], 404)
            self.assertEqual(self.request("GET", "/sync")[0], 404)


class SyncPageTests(unittest.TestCase):
    def test_page_markup_ships_the_mode_surface(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        for marker in ('id="syncMode"', 'id="syncSave"', 'id="syncRefreshPeers"', 'id="syncPeers"', "/static/sync.js"):
            self.assertIn(marker, source)
        script = (ROOT / "static/sync.js").read_text(encoding="utf-8")
        self.assertIn('"/api/sync/settings"', script)
        self.assertIn('"/api/sync/lan/announce"', script)
        self.assertNotIn("eval(", script)


if __name__ == "__main__":
    unittest.main()
