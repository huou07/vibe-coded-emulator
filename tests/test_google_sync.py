# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import base64
import hashlib
import json
import unittest
import urllib.parse

import google_sync as gs
import sync_engine as se


class FakeTransport:
    """Routes requests to canned responses and records what was sent."""

    def __init__(self, routes):
        # routes: list of (matcher, HttpResponse). matcher is a callable
        # (method, url) -> bool, a substring of the url, or None for any.
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, *, headers=None, body=None, timeout=30.0):
        self.calls.append({"method": method, "url": url, "headers": headers or {}, "body": body})
        for match, response in self.routes:
            if callable(match):
                hit = match(method, url)
            else:
                hit = match is None or match in url
            if hit:
                return response
        return gs.HttpResponse(404, {}, b"{}")

    def body_text(self, index=0):
        return (self.calls[index]["body"] or b"").decode("utf-8", "replace")


def config(**kwargs):
    defaults = dict(client_id="client-123", redirect_uri="https://app.example/oauth/google/callback")
    defaults.update(kwargs)
    return gs.OAuthConfig(**defaults)


class PkceTests(unittest.TestCase):
    def test_challenge_is_s256_of_verifier(self):
        verifier, challenge = gs.create_pkce_pair()
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        self.assertEqual(challenge, expected)
        self.assertNotIn("=", verifier)
        self.assertNotIn("=", challenge)


class AuthorizationUrlTests(unittest.TestCase):
    def test_url_requests_offline_pkce_and_appdata_scope(self):
        verifier, challenge = gs.create_pkce_pair()
        url = gs.authorization_url(config(), state="st-1", code_challenge=challenge, login_hint="a@b.com")
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(query["client_id"], ["client-123"])
        self.assertEqual(query["state"], ["st-1"])
        self.assertEqual(query["code_challenge"], [challenge])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["access_type"], ["offline"])
        self.assertIn("drive.appdata", query["scope"][0])
        self.assertEqual(query["login_hint"], ["a@b.com"])
        # The client secret must never appear in an authorization URL.
        self.assertNotIn("client_secret", query)


class TokenTests(unittest.TestCase):
    def test_public_client_exchange_sends_no_secret(self):
        transport = FakeTransport([(None, gs.HttpResponse(200, {}, json.dumps({
            "access_token": "at", "refresh_token": "rt", "expires_in": 3600,
            "scope": "openid email", "token_type": "Bearer",
        }).encode()))])
        tokens = gs.exchange_code(config(), code="code-1", code_verifier="ver-1", transport=transport)
        self.assertEqual(tokens.access_token, "at")
        self.assertEqual(tokens.refresh_token, "rt")
        self.assertFalse(tokens.expired)
        sent = urllib.parse.parse_qs(transport.body_text())
        self.assertEqual(sent["code"], ["code-1"])
        self.assertEqual(sent["code_verifier"], ["ver-1"])
        self.assertNotIn("client_secret", sent)

    def test_confidential_client_includes_secret(self):
        transport = FakeTransport([(None, gs.HttpResponse(200, {}, b'{"access_token":"at","expires_in":60}'))])
        gs.exchange_code(config(client_secret="s3cret"), code="c", code_verifier="v", transport=transport)
        sent = urllib.parse.parse_qs(transport.body_text())
        self.assertEqual(sent["client_secret"], ["s3cret"])

    def test_error_response_raises_google_auth_error(self):
        transport = FakeTransport([(None, gs.HttpResponse(400, {}, b'{"error":"invalid_grant"}'))])
        with self.assertRaises(gs.GoogleAuthError):
            gs.exchange_code(config(), code="bad", code_verifier="v", transport=transport)

    def test_refresh_requires_a_token(self):
        with self.assertRaises(gs.GoogleAuthError):
            gs.refresh_access_token(config(), refresh_token="")

    def test_id_token_claims_are_decoded(self):
        claims = {"sub": "123", "email": "a@b.com"}
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        token = f"header.{payload}.signature"
        self.assertEqual(gs.decode_id_token_claims(token)["email"], "a@b.com")
        with self.assertRaises(gs.GoogleAuthError):
            gs.decode_id_token_claims("not-a-jwt")


class DriveClientTests(unittest.TestCase):
    def test_list_scopes_to_app_data_folder(self):
        transport = FakeTransport([("files?", gs.HttpResponse(200, {}, json.dumps(
            {"files": [{"id": "f1", "name": "save.sav", "appProperties": {"sha256": "h1"}}]}).encode()))])
        files, token = gs.GoogleDriveClient("at", transport=transport).list_app_files()
        self.assertEqual(files[0]["id"], "f1")
        self.assertEqual(token, "")
        self.assertIn("spaces=appDataFolder", transport.calls[0]["url"])

    def test_small_upload_uses_multipart_with_our_sha256(self):
        transport = FakeTransport([(None, gs.HttpResponse(200, {}, b'{"id":"f9","name":"save.sav"}'))])
        result = gs.GoogleDriveClient("at", transport=transport).upload("save.sav", b"data", sha256="abc")
        self.assertEqual(result["id"], "f9")
        body = transport.body_text()
        self.assertIn('"appDataFolder"', body)
        self.assertIn('"sha256": "abc"', body)
        self.assertIn("data", body)

    def test_large_upload_uses_resumable_chunks(self):
        big = b"x" * (gs.RESUMABLE_THRESHOLD + 10)
        start = gs.HttpResponse(200, {"Location": "https://upload.example/session"}, b"{}")
        done = gs.HttpResponse(200, {}, b'{"id":"f10"}')
        transport = FakeTransport([("uploadType=resumable", start), ("upload.example/session", done)])
        result = gs.GoogleDriveClient("at", transport=transport).upload("big.zip", big, sha256="h")
        self.assertEqual(result["id"], "f10")
        self.assertEqual(transport.calls[0]["method"], "POST")
        self.assertEqual(transport.calls[1]["method"], "PUT")
        self.assertTrue(transport.calls[1]["headers"]["Content-Range"].startswith("bytes 0-"))

    def test_download_and_delete(self):
        transport = FakeTransport([
            (lambda m, u: m == "GET" and "alt=media" in u, gs.HttpResponse(200, {}, b"payload")),
            (lambda m, u: m == "DELETE", gs.HttpResponse(204, {}, b"")),
        ])
        client = gs.GoogleDriveClient("at", transport=transport)
        self.assertEqual(client.download("file 1"), b"payload")
        client.delete("file 1")


class SyncMappingTests(unittest.TestCase):
    def test_entries_combine_drive_and_local_with_last_synced(self):
        drive_files = [
            {"id": "f1", "name": "save.sav", "appProperties": {"sha256": "remote-h"}},
        ]
        local = {"save.sav": se.ItemVersion(content_hash="local-h"), "rom.gba": se.ItemVersion(content_hash="rom-h")}
        entries = gs.build_drive_sync_entries(drive_files, local, {"save.sav": "remote-h"})
        by_key = {entry.key: entry for entry in entries}
        self.assertEqual(len(entries), 2)
        self.assertEqual(by_key["save.sav"].remote.content_id, "f1")
        self.assertEqual(by_key["save.sav"].last_synced_hash, "remote-h")
        self.assertEqual(by_key["rom.gba"].remote, None)

    def test_kind_classification(self):
        self.assertEqual(gs._kind_for_name("Pokemon.gba"), se.ItemKind.ROM)
        self.assertEqual(gs._kind_for_name("game.sav"), se.ItemKind.SAVE)
        self.assertEqual(gs._kind_for_name("game.state"), se.ItemKind.STATE)

    def test_firmware_and_keys_are_not_eligible_anywhere(self):
        self.assertFalse(se.is_sync_eligible(se.ItemKind.FIRMWARE))
        self.assertFalse(se.is_sync_eligible(se.ItemKind.KEYS))


if __name__ == "__main__":
    unittest.main()
