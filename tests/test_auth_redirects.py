# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

from app import safe_next_path


class AuthRedirectTests(unittest.TestCase):
    def test_accepts_same_origin_paths(self):
        self.assertEqual(safe_next_path("/game/pixel-quest"), "/game/pixel-quest")
        self.assertEqual(safe_next_path("/game/pixel-quest?tab=comments#ignored"), "/game/pixel-quest?tab=comments")

    def test_rejects_external_or_ambiguous_targets(self):
        for value in ("https://example.com", "//example.com", "/\\example.com", "game/pixel-quest", "/game/pixel\nquest"):
            with self.subTest(value=value):
                self.assertEqual(safe_next_path(value, "/fallback"), "/fallback")


if __name__ == "__main__":
    unittest.main()
