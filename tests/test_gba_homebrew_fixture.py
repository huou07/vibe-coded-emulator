# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contracts for deterministic, independently identifiable GBA test fixtures."""

import hashlib
import json
import unittest
from pathlib import Path

from tools.testrom.gba_homebrew_test import build


ROOT = Path(__file__).resolve().parents[1]


class GbaHomebrewFixtureTests(unittest.TestCase):
    def test_default_fixture_remains_the_recorded_canonical_rom(self):
        fixtures = json.loads((ROOT / "tools/testrom/fixtures.json").read_text(encoding="utf-8"))
        gba = next(item for item in fixtures["fixtures"] if item.get("system") == "gba")
        rom = build()

        self.assertEqual(len(rom), gba["size"])
        self.assertEqual(hashlib.sha256(rom).hexdigest(), gba["sha256"])

    def test_title_variant_keeps_the_executable_body_and_refreshes_header_checksum(self):
        canonical = build()
        variant = build(b"AN3SYNCROM5")

        self.assertEqual(len(variant), 512)
        self.assertEqual(variant[0xA0:0xAB], b"AN3SYNCROM5")
        self.assertEqual(variant[0xC0:], canonical[0xC0:])
        self.assertNotEqual(hashlib.sha256(variant).digest(), hashlib.sha256(canonical).digest())
        self.assertEqual((sum(variant[0xA0:0xBE]) + 0x19) & 0xFF, 0)

    def test_latched_input_variant_is_opt_in_and_keeps_the_recorded_fixture_unchanged(self):
        canonical = build()
        latched = build(latch_input=True)
        words = [
            int.from_bytes(latched[offset : offset + 4], "little")
            for offset in range(0xC0, 0xC0 + 38 * 4, 4)
        ]

        self.assertEqual(len(latched), 512)
        self.assertEqual(canonical, build(latch_input=False))
        self.assertNotEqual(latched[0xC0:], canonical[0xC0:])
        self.assertIn(b"AN3HOMEBREW", latched)
        self.assertEqual(words[21], 0xE3A0B000)  # clear latch on boot
        self.assertEqual(words[27:29], [0x03A0B001, 0xE35B0001])
        self.assertEqual(words[34:36], [0x1AFFFFFC, 0xEAFFFFF3])

    def test_title_rejects_values_that_cannot_fit_a_gba_header(self):
        for title in (b"", b"lowercase", b"AN3-ROM", b"AN3SYNCROM500"):
            with self.subTest(title=title), self.assertRaises(ValueError):
                build(title)


if __name__ == "__main__":
    unittest.main()
