# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import bug_report  # noqa: E402

# Deliberately fake values. None of these are real credentials or personal data.
FAKE_GITHUB_TOKEN = "ghp_" + "A" * 36
FAKE_PAT = "github_pat_" + "B" * 30
FAKE_SK = "sk-" + "c" * 32
FAKE_MAC = "de:ad:be:ef:00:11"
FAKE_EMAIL = "someone@example.invalid"


class ScrubTests(unittest.TestCase):
    def test_github_tokens_are_removed(self):
        text = bug_report.scrub_text("token=%s and %s" % (FAKE_GITHUB_TOKEN, FAKE_PAT))
        self.assertNotIn(FAKE_GITHUB_TOKEN, text)
        self.assertNotIn(FAKE_PAT, text)
        self.assertNotIn("ghp_", text)
        self.assertNotIn("github_pat_", text)

    def test_api_keys_and_bearer_are_removed(self):
        text = bug_report.scrub_text("Authorization: Bearer abcdefghijklmnop12345 sk=%s" % FAKE_SK)
        self.assertNotIn("abcdefghijklmnop12345", text)
        self.assertNotIn(FAKE_SK, text)

    def test_private_key_block_is_removed(self):
        text = bug_report.scrub_text("-----BEGIN RSA PRIVATE KEY-----\nMIIsecret\n-----END RSA PRIVATE KEY-----")
        self.assertNotIn("MIIsecret", text)
        self.assertIn("redacted-private-key", text)

    def test_query_parameters_are_removed(self):
        text = bug_report.scrub_text("https://x.invalid/cb?access_token=abcdef&refresh_token=uvwxyz&page=2")
        self.assertNotIn("abcdef", text)
        self.assertNotIn("uvwxyz", text)
        self.assertIn("page=2", text)

    def test_mac_address_is_removed(self):
        text = bug_report.scrub_text("adapter %s online" % FAKE_MAC)
        self.assertNotIn(FAKE_MAC, text)
        self.assertIn("redacted-mac", text)

    def test_ip_addresses_are_removed(self):
        text = bug_report.scrub_text("peer 192.0.2.55 and fe80:1:2:3:4:5:6:7")
        self.assertNotIn("192.0.2.55", text)
        self.assertNotIn("fe80:1:2:3:4:5:6:7", text)

    def test_email_is_removed(self):
        text = bug_report.scrub_text("contact %s" % FAKE_EMAIL)
        self.assertNotIn(FAKE_EMAIL, text)
        self.assertIn("redacted-email", text)

    def test_username_in_paths_is_removed(self):
        for raw in ("~/<REDACTED_PATH>", "C:\\Users\\developer\\ROMs\\game.nds"):
            text = bug_report.scrub_text(raw)
            self.assertNotIn("developer", text)
            self.assertNotIn(".gba", text)
            self.assertNotIn(".nds", text)

    def test_control_characters_are_removed(self):
        text = bug_report.scrub_text("hello\x00world\x07")
        self.assertNotIn("\x00", text)
        self.assertNotIn("\x07", text)


class BuildReportTests(unittest.TestCase):
    def test_forbidden_top_level_fields_are_dropped(self):
        report = bug_report.build_report(
            {
                "description": "game crashed",
                "romPath": "~/<REDACTED_PATH>",
                "romData": "BASE64ROMBYTES",
                "accessToken": FAKE_GITHUB_TOKEN,
                "refreshToken": "refresh-value",
                "saveState": "AAECAwQ=",
                "env": {"HOME": "~"},
                "macAddress": FAKE_MAC,
                "ipAddress": "10.0.0.9",
                "password": "hunter2",
            },
            build_id="build-1",
            app_version="0.0.0-test",
        )
        serialized = json.dumps(report)
        for forbidden in (
            "romPath",
            "romData",
            "accessToken",
            "refreshToken",
            "saveState",
            "macAddress",
            "ipAddress",
            "password",
            FAKE_GITHUB_TOKEN,
            FAKE_MAC,
            "hunter2",
            "BASE64ROMBYTES",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertGreaterEqual(report["droppedFieldCount"], 8)
        bug_report.assert_no_forbidden(report)

    def test_allowed_fields_are_scrubbed_and_bounded(self):
        long_description = "x" * (bug_report.MAX_DESCRIPTION + 500)
        report = bug_report.build_report(
            {
                "description": "leak %s and %s" % (FAKE_GITHUB_TOKEN, "~/<REDACTED_PATH>"),
                "logs": ["ok line", "bad %s" % FAKE_EMAIL] * 50,
                "platform": "macOS",
                "emulatorSystem": "nds",
                "coreName": "/private/cores/melonds_libretro.dylib",
                "settings": {"renderer": "webgl2", "access_token": "nope", long_description: "x"},
                "crash": {"message": "boom", "stack": "at ~/<REDACTED_PATH>:1"},
            },
            build_id="b",
            app_version="a",
        )
        self.assertLessEqual(len(report["description"]), bug_report.MAX_DESCRIPTION + 500)
        serialized = json.dumps(report)
        self.assertNotIn("developer", serialized)
        self.assertNotIn(FAKE_GITHUB_TOKEN, serialized)
        self.assertNotIn(FAKE_EMAIL, serialized)
        self.assertNotEqual(report["coreName"], "/private/cores/melonds_libretro.dylib")
        self.assertNotIn("access_token", report["settings"])
        self.assertLessEqual(len(report["logs"]), bug_report.MAX_LOG_LINES)
        bug_report.assert_no_forbidden(report)

    def test_game_identifier_is_anonymous_and_stable(self):
        personal_path = "/Users/" + "player" + "/ROMs/" + "Pokemon Emerald.gba"
        first = bug_report.build_report({"gameTitle": personal_path})
        second = bug_report.build_report({"gameTitle": "Pokemon Emerald"})
        self.assertEqual(first["gameIdentifier"], second["gameIdentifier"])
        self.assertTrue(first["gameIdentifier"].startswith("game-"))
        self.assertNotIn("player", json.dumps(first))
        self.assertNotIn("Emerald", first["gameIdentifier"])

    def test_explicit_slug_identifier_is_kept_but_path_is_not(self):
        report = bug_report.build_report({"gameTitle": "Emerald", "gameIdentifier": "~/<REDACTED_PATH>"})
        self.assertTrue(report["gameIdentifier"].startswith("game-"))
        self.assertNotIn("developer", report["gameIdentifier"])

    def test_server_facts_override_client_values(self):
        report = bug_report.build_report(
            {"appVersion": "spoofed", "buildId": "spoofed"},
            build_id="server-build",
            app_version="server-app",
            channel="staging",
        )
        self.assertEqual(report["buildId"], "server-build")
        self.assertEqual(report["appVersion"], "server-app")
        self.assertEqual(report["channel"], "staging")

    def test_assert_no_forbidden_rejects_injected_payload(self):
        report = bug_report.build_report({"description": "clean"})
        report["logs"] = ["token " + FAKE_GITHUB_TOKEN]
        with self.assertRaises(ValueError):
            bug_report.assert_no_forbidden(report)


class IssueTests(unittest.TestCase):
    def _report(self):
        return bug_report.build_report(
            {
                "description": "Controls stop responding",
                "platform": "Android",
                "emulatorSystem": "nds",
                "coreName": "melonds",
                "gameTitle": "Test Game",
            },
            build_id="build-9",
            app_version="1.2.3",
            channel="staging",
        )

    def test_fingerprint_is_stable_and_description_sensitive(self):
        first = bug_report.issue_fingerprint(self._report())
        same = bug_report.issue_fingerprint(self._report())
        self.assertEqual(first, same)
        other = bug_report.build_report({"description": "Different problem", "platform": "Android"})
        self.assertNotEqual(first, bug_report.issue_fingerprint(other))

    def test_issue_body_contains_marker_and_no_secrets(self):
        body = bug_report.github_issue_body(self._report())
        self.assertIn("an3-bug-fingerprint:", body)
        self.assertIn("Controls stop responding", body)
        self.assertNotIn("ghp_", body)

    def test_create_issue_not_configured_does_not_attempt(self):
        result = bug_report.create_github_issue(self._report(), token="", repository="")
        self.assertFalse(result["attempted"])
        self.assertFalse(result["created"])

    def test_create_issue_network_failure_is_not_fatal(self):
        def failing_fetch(request, timeout=10):
            raise OSError("network down")

        result = bug_report.create_github_issue(
            self._report(), token="fake-token", repository="owner/repo", fetch=failing_fetch
        )
        self.assertTrue(result["attempted"])
        self.assertFalse(result["created"])
        self.assertIn("request failed", result["reason"])

    def test_create_issue_success_returns_number_and_url(self):
        class FakeResponse:
            status = 201

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"number": 42, "html_url": "https://github.com/owner/repo/issues/42"}).encode()

        result = bug_report.create_github_issue(
            self._report(), token="fake-token", repository="owner/repo", fetch=lambda request, timeout=10: FakeResponse()
        )
        self.assertTrue(result["created"])
        self.assertEqual(result["number"], 42)


if __name__ == "__main__":
    unittest.main()
