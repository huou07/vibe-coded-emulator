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
import time
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import app
import netcode
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
            patch.object(app, "AUTH_PEPPER", "sync-api-test-peer-proof-key"),
            patch.object(app, "LAN_PEERS", {}),
            patch.object(app, "LAN_BLOBS", {}),
            patch.object(app, "SYNC_LIMITER", netcode.SlidingRateLimiter(limit=200, window_seconds=60)),
        ]
        for active in self.patches:
            active.start()
        app.init_db()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookies = {}

    def test_native_account_session_and_peer_proof_are_account_bound(self):
        status, body = self.request("GET", "/api/account/session")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"authenticated": False})

        status, _ = self.request("POST", "/api/register", {
            "name": "peer-proof-user",
            "display_name": "Peer Proof User",
            "password": "Peer-proof-pass-123",
            "confirm": "Peer-proof-pass-123",
        })
        self.assertEqual(status, 201)
        status, body = self.request("GET", "/api/account/session")
        self.assertEqual(status, 200)
        session = json.loads(body)
        self.assertTrue(session["authenticated"])
        self.assertEqual(session["name"], "Peer Proof User")
        self.assertTrue(session["csrf"])

        challenge = "a" * 32
        status, body = self.request("POST", "/api/account/peer-proof", {"challenge": challenge})
        self.assertEqual(status, 200)
        proof = json.loads(body)["proof"]
        self.assertNotIn("Peer-proof-pass-123", proof)
        status, body = self.request("POST", "/api/account/peer-proof/verify", {"challenge": challenge, "proof": proof})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["sameAccount"])

        status, body = self.request("POST", "/api/account/peer-proof/verify", {"challenge": "b" * 32, "proof": proof})
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["sameAccount"])

        # The native client must use the server-issued CSRF token when it
        # logs out; the account cookie itself is never handed to a peer.
        csrf = session["csrf"]
        status, _ = self.request("POST", "/api/logout", None, headers={"X-CSRF-Token": csrf})
        self.assertEqual(status, 200)
        status, body = self.request("GET", "/api/account/session")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"authenticated": False})

    def test_native_account_peer_proof_fails_closed_without_server_key(self):
        with patch.object(app, "AUTH_PEPPER", ""):
            status, body = self.request("POST", "/api/account/register", {})
            self.assertEqual(status, 404)
            status, body = self.request("POST", "/api/register", {
                "name": "proof-unconfigured",
                "display_name": "Proof Unconfigured",
                "password": "Proof-unconfigured-123",
                "confirm": "Proof-unconfigured-123",
            })
            self.assertEqual(status, 201)
            status, body = self.request("POST", "/api/account/peer-proof", {"challenge": "c" * 32})
            self.assertEqual(status, 503)
            self.assertIn("not configured", json.loads(body)["error"])

    def test_native_account_cors_is_limited_to_tauri_origins(self):
        status, _body, headers = self.request_with_headers(
            "GET", "/api/account/session", {"Origin": "https://tauri.localhost"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("access-control-allow-origin"), "https://tauri.localhost")
        self.assertEqual(headers.get("access-control-allow-credentials"), "true")

        status, _body, headers = self.request_with_headers(
            "GET", "/api/account/session", {"Origin": "https://appassets.androidplatform.net"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("access-control-allow-origin"), "https://appassets.androidplatform.net")

        status, _body, headers = self.request_with_headers(
            "OPTIONS",
            "/api/login",
            {
                "Origin": "https://tauri.localhost",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(status, 204)
        self.assertEqual(headers.get("access-control-allow-methods"), "GET, POST, OPTIONS")

        status, _body, headers = self.request_with_headers(
            "GET", "/api/account/session", {"Origin": "https://evil.example"}
        )
        self.assertEqual(status, 200)
        self.assertNotIn("access-control-allow-origin", headers)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        for active in self.patches:
            active.stop()
        self.temp.cleanup()

    def request(self, method, path, payload=None, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        headers = dict(headers or {})
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

    def request_with_headers(self, method, path, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        status, data = response.status, response.read()
        received = {name.lower(): value for name, value in response.getheaders()}
        connection.close()
        return status, data, received

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

    @staticmethod
    def save_set(payloads, *, core="mgba", game_id="emerald", rom_hash="a" * 64):
        set_id = f"save:{core}:{game_id}:{rom_hash}"
        members = []
        items = []
        for member_id, payload in sorted(payloads.items()):
            digest = hashlib.sha256(payload).hexdigest()
            member = {
                "key": f"{set_id}:{member_id}",
                "memberId": member_id,
                "path": f"/data/saves/{member_id}",
                "size": len(payload),
                "contentHash": digest,
            }
            members.append(member)
            items.append({**member, "data": base64.b64encode(payload).decode("ascii")})
        save_set = {
            "setId": set_id,
            "core": core,
            "gameId": game_id,
            "romHash": rom_hash,
            "memberCount": len(members),
            "totalSize": sum(member["size"] for member in members),
            "members": members,
        }
        save_set["manifestHash"] = app._sync_save_set_hash(save_set)
        return save_set, items

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

    def test_lan_publish_cannot_overwrite_another_devices_blob(self):
        original = b"owner-save-state"
        status, _ = self.publish(original, device="device-aaaaaaaa")
        self.assertEqual(status, 200)

        # A different device may not silently replace the same (kind, key).
        status, body = self.publish(b"attacker-save-state", device="device-bbbbbbbb")
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(body)["reason"], "lan-blob-owner-conflict")

        # The original bytes and their owner survive the refused overwrite.
        status, body = self.request("GET", "/api/sync/lan/manifest?kind=state")
        entry = json.loads(body)["items"][0]
        self.assertEqual(entry["deviceId"], "device-aaaaaaaa")
        status, downloaded = self.request(
            "GET", f"/api/sync/lan/blob?kind=state&key={entry['key']}&hash={entry['contentHash']}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(downloaded, original)

        # The same device may still refresh its own record.
        status, _ = self.publish(b"owner-save-state-v2", device="device-aaaaaaaa")
        self.assertEqual(status, 200)

    def test_lan_publish_rejects_a_spoofed_owner_from_another_address(self):
        payload = b"owned-state"
        item = self.blob(payload)
        app.LAN_BLOBS[("state", item["key"])] = {
            "hash": item["contentHash"],
            "device": "device-aaaaaaaa",
            "ip": "192.0.2.6",
            "data": payload,
            "updated": time.monotonic(),
        }
        # Same device id, but this request's source address is not the owner's.
        status, body = self.publish(b"spoofed-state", device="device-aaaaaaaa")
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(body)["reason"], "lan-blob-owner-conflict")
        self.assertEqual(app.LAN_BLOBS[("state", item["key"])]["data"], payload)

    def test_lan_publish_refuses_a_mixed_batch_without_a_partial_write(self):
        item = self.blob(b"owned-state")
        self.publish(b"owned-state")
        owned_key = item["key"]
        new_key = "gba/another-game/slot1.state"
        new_payload = b"fresh-state"
        new_item = {
            "key": new_key,
            "contentHash": hashlib.sha256(new_payload).hexdigest(),
            "data": base64.b64encode(new_payload).decode("ascii"),
        }
        # One item is owned by another device; the whole batch must be refused
        # so a rejected item can never leave a half-published list behind.
        status, body = self.request("POST", "/api/sync/lan/publish", {
            "deviceId": "device-bbbbbbbb",
            "kind": "state",
            "items": [new_item, item],
        })
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(body)["reason"], "lan-blob-owner-conflict")
        self.assertEqual(json.loads(body)["key"], owned_key)
        self.assertNotIn(("state", new_key), app.LAN_BLOBS)

    def test_lan_manifest_does_not_expose_the_owner_address(self):
        payload = b"private-owner-address"
        self.publish(payload)
        status, body = self.request("GET", "/api/sync/lan/manifest?kind=state")
        self.assertEqual(status, 200)
        entry = json.loads(body)["items"][0]
        # The manifest exposes the owner device id (needed to filter peers) but
        # never the request source address used for the ownership tie-break.
        self.assertNotIn("ip", entry)
        self.assertNotIn("127.0.0.1", body.decode())

    def test_lan_blob_ownership_lapses_with_the_ttl(self):
        payload = b"owner-state"
        item = self.blob(payload)
        self.publish(payload)
        # Age the record past its TTL; the reaper runs on the next publish and
        # the key becomes claimable by whichever device publishes next.
        app.LAN_BLOBS[("state", item["key"])]["updated"] = time.monotonic() - app.LAN_BLOB_TTL_SECONDS - 1
        status, body = self.publish(b"new-owner-state", device="device-bbbbbbbb")
        self.assertEqual(status, 200, body)
        self.assertEqual(app.LAN_BLOBS[("state", item["key"])]["device"], "device-bbbbbbbb")
    def test_lan_save_set_publish_manifest_and_download_round_trip(self):
        save_set, items = self.save_set({"emerald.rtc": b"rtc-bytes", "emerald.srm": b"srm-bytes"})
        status, body = self.request("POST", "/api/sync/lan/publish", {
            "deviceId": "device-aaaaaaaa", "kind": "save", "set": save_set, "items": items,
        })
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["stored"], 2)
        status, body = self.request("GET", "/api/sync/lan/manifest?kind=save")
        self.assertEqual(status, 200)
        manifest = json.loads(body)
        self.assertEqual(len(manifest["sets"]), 1)
        published = manifest["sets"][0]
        self.assertEqual(published["setId"], save_set["setId"])
        self.assertEqual([member["memberId"] for member in published["members"]], ["emerald.rtc", "emerald.srm"])
        self.assertEqual(published["totalSize"], save_set["totalSize"])
        self.assertEqual(published["manifestHash"], save_set["manifestHash"])
        for item in items:
            status, downloaded = self.request(
                "GET", f"/api/sync/lan/blob?kind=save&key={item['key']}&hash={item['contentHash']}"
            )
            self.assertEqual(status, 200)
            self.assertEqual(downloaded, base64.b64decode(item["data"]))

    def test_lan_save_set_rejects_partial_or_corrupt_payload_without_storing_any_member(self):
        save_set, items = self.save_set({"emerald.rtc": b"rtc", "emerald.srm": b"srm"})
        invalid_payloads = []
        invalid_payloads.append({**save_set, "members": save_set["members"][:1]})
        invalid_payloads.append({**save_set, "members": [save_set["members"][0], save_set["members"][0]]})
        invalid_payloads.append(save_set)
        for index, candidate in enumerate(invalid_payloads):
            with self.subTest(index=index):
                candidate_items = list(items)
                if index == 2:
                    candidate_items[1] = {**candidate_items[1], "data": base64.b64encode(b"tampered").decode("ascii")}
                status, _ = self.request("POST", "/api/sync/lan/publish", {
                    "deviceId": "device-aaaaaaaa", "kind": "save", "set": candidate, "items": candidate_items,
                })
                self.assertEqual(status, 400)
                self.assertEqual(app.LAN_BLOBS, {})
        unknown_item = {"key": f"{save_set['setId']}:unknown.sav", "memberId": "unknown.sav", "path": "/data/saves/unknown.sav", "size": 1, "contentHash": "b" * 64, "data": base64.b64encode(b"x").decode("ascii")}
        status, _ = self.request("POST", "/api/sync/lan/publish", {
            "deviceId": "device-aaaaaaaa", "kind": "save", "set": save_set, "items": items + [unknown_item],
        })
        self.assertEqual(status, 400)
        self.assertEqual(app.LAN_BLOBS, {})

    def test_lan_save_set_replacement_requires_the_current_manifest_hash(self):
        original_set, original_items = self.save_set({"emerald.rtc": b"rtc-v1", "emerald.srm": b"srm-v1"})
        status, _ = self.request("POST", "/api/sync/lan/publish", {
            "deviceId": "device-aaaaaaaa", "kind": "save", "set": original_set, "items": original_items,
        })
        self.assertEqual(status, 200)
        replacement_set, replacement_items = self.save_set({"emerald.rtc": b"rtc-v2", "emerald.srm": b"srm-v2"})
        status, _ = self.request("POST", "/api/sync/lan/publish", {
            "deviceId": "device-bbbbbbbb", "kind": "save", "set": replacement_set, "items": replacement_items,
        })
        self.assertEqual(status, 409)
        status, body = self.request("POST", "/api/sync/lan/publish", {
            "deviceId": "device-bbbbbbbb", "kind": "save", "set": replacement_set, "items": replacement_items,
            "replaceManifestHash": original_set["manifestHash"],
        })
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["manifestHash"], replacement_set["manifestHash"])
        status, body = self.request("GET", "/api/sync/lan/manifest?kind=save")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["sets"][0]["manifestHash"], replacement_set["manifestHash"])

    def test_lan_save_set_rejects_malformed_member_identity_and_reports_missing_blob(self):
        save_set, items = self.save_set({"emerald.rtc": b"rtc", "emerald.srm": b"srm"})
        malformed = {**save_set, "members": [{**save_set["members"][0], "path": "/data/saves/../escape"}, save_set["members"][1]]}
        status, _ = self.request("POST", "/api/sync/lan/publish", {
            "deviceId": "device-aaaaaaaa", "kind": "save", "set": malformed, "items": items,
        })
        self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/sync/lan/publish", {
            "deviceId": "device-aaaaaaaa", "kind": "save", "set": save_set, "items": items,
        })
        self.assertEqual(status, 200)
        app.LAN_BLOBS.pop(("save", items[0]["key"]))
        status, _ = self.request("GET", f"/api/sync/lan/blob?kind=save&key={items[0]['key']}&hash={items[0]['contentHash']}")
        self.assertEqual(status, 404)

    def test_state_and_normal_save_namespaces_are_separate(self):
        state_payload = b"state-bytes"
        save_payload = b"normal-save-bytes"
        save_key = "save:mgba:emerald:" + "a" * 64 + ":emerald.srm"
        self.publish(state_payload)
        status, _ = self.publish(save_payload, kind="save", key=save_key)
        self.assertEqual(status, 200)
        state_status, state_body = self.request("GET", "/api/sync/lan/manifest?kind=state")
        save_status, save_body = self.request("GET", "/api/sync/lan/manifest?kind=save")
        self.assertEqual(state_status, 200)
        self.assertEqual(save_status, 200)
        self.assertEqual(json.loads(state_body)["items"][0]["key"], "gba/pokemon-emerald/slot1.state")
        self.assertEqual(json.loads(save_body)["items"][0]["key"], save_key)
        save_hash = json.loads(save_body)["items"][0]["contentHash"]
        status, downloaded = self.request("GET", f"/api/sync/lan/blob?kind=save&key={save_key}&hash={save_hash}")
        self.assertEqual(status, 200)
        self.assertEqual(downloaded, save_payload)

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

    def test_lan_publish_allows_a_valid_blob_above_the_generic_json_limit(self):
        payload = b"x" * (1024 * 1024)
        status, body = self.publish(payload)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["items"][0]["size"], len(payload))

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
        for marker in ('id="syncMode"', 'id="syncSave"', 'id="syncRefreshPeers"', 'id="syncTransfer"', 'id="syncPeers"', "/static/sync-transfer.js", "/static/sync.js"):
            self.assertIn(marker, source)
        script = (ROOT / "static/sync.js").read_text(encoding="utf-8")
        self.assertIn('"/api/sync/settings"', script)
        self.assertIn('"/api/sync/lan/announce"', script)
        self.assertIn("AN3SyncTransfer.syncState", script)
        self.assertNotIn("eval(", script)

    def test_player_page_exposes_the_real_game_save_sync_action(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('id="syncSaveFile"', source)
        self.assertIn('id="syncSaveConflicts"', source)
        self.assertIn('versioned_player_asset("sync-transfer.js")', source)
        player = (ROOT / "static/player.js").read_text(encoding="utf-8")
        self.assertIn("AN3SyncTransfer.syncSave", player)
        self.assertIn("Save set conflict", player)
        self.assertIn("memberCount", player)
        self.assertIn("getSaveFilePath", (ROOT / "static/sync-transfer.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
