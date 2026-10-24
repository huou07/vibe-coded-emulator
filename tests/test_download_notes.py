# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The download page must say when one platform's newest build is older.

Platform artifacts are rebuilt independently, so the catalog can hold several
versions at once (the release tests already allow it). A card that shows only
"Ready" would then hide the fact that, on that platform, the current download is
an older build. `note` is the artifact field that closes that gap.
"""
import unittest

import app


def artifact(**overrides):
    item = {
        "version": "3.6.11",
        "platform": "Linux",
        "architecture": "amd64",
        "format": "DEB",
        "filename": "vibecodedemulator-3.6.11-linux-amd64.deb",
        "status": "available",
        "download_url": "/download-app/release/vibecodedemulator-3.6.11-linux-amd64.deb",
        "sha256": "0" * 64,
        "release_id": "production-test",
    }
    item.update(overrides)
    return item


class DownloadPlatformNoteTests(unittest.TestCase):
    def test_a_card_without_a_note_renders_no_note(self):
        card = app.download_platform_card("Linux", [artifact()], "en")
        self.assertIn("platform-card ready", card)
        self.assertNotIn("platform-note", card)
        self.assertIn("3.6.11", card)

    def test_a_card_shows_the_version_and_the_note_it_carries(self):
        card = app.download_platform_card(
            "macOS",
            [artifact(platform="macOS", format="DMG", version="3.6.10",
                      filename="vibecodedemulator-3.6.10-macos-aarch64.dmg",
                      note="3.6.10 build: it predates the optional-feature entry points.")],
            "en",
        )
        self.assertIn("3.6.10", card)
        self.assertIn('class="platform-note"', card)
        self.assertIn("predates the optional-feature entry points", card)

    def test_a_note_is_escaped_and_only_applies_to_the_primary_action(self):
        card = app.download_platform_card(
            "Windows",
            [artifact(platform="Windows", format="EXE", note="<script>alert(1)</script>")],
            "en",
        )
        self.assertNotIn("<script>", card)
        self.assertIn("&lt;script&gt;", card)


if __name__ == "__main__":
    unittest.main()
