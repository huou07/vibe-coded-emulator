# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANSFORM = ROOT / "native-offline/src-tauri/src/native_input_transform.h"
HOST = ROOT / "native-offline/src-tauri/src/azahar_host.mm"


class NativeInputContractTests(unittest.TestCase):
    def test_relative_contract_has_one_platform_boundary(self):
        text = TRANSFORM.read_text()
        host = HOST.read_text()
        self.assertIn("right/down are", text)
        self.assertIn("physical_delta", text)
        self.assertIn("host->move_nds_cursor(event.deltaX, event.deltaY)", host)
        self.assertNotIn("CGGetLastMouseDelta", host)
        self.assertNotIn("move_nds_cursor(event.deltaX, -event.deltaY)", host)

    def test_relative_directions_and_absolute_corners(self):
        def relative(value):
            return max(-32767, min(32767, round(value)))

        self.assertGreater(relative(1), 0)       # right / down
        self.assertLess(relative(-1), 0)         # left / up
        self.assertLess(round(0 * 65534 / 100) - 32767, 0)
        self.assertGreater(round(100 * 65534 / 100) - 32767, 0)
        self.assertEqual(round(50 * 65534 / 100) - 32767, 0)

if __name__ == "__main__":
    unittest.main()
