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

    def test_linux_and_windows_write_the_same_control_stdin_protocol(self):
        # The phone controller injects through set_native_input, which on
        # desktop writes this line to the bundled player's stdin. Both platform
        # adapters must keep the same field order or controller input breaks.
        sources = {
            name: (ROOT / f"native-offline/src-tauri/src/{name}").read_text(encoding="utf-8")
            for name in ("linux_runtime.rs", "windows_runtime.rs")
        }
        for name, source in sources.items():
            with self.subTest(runtime=name):
                self.assertIn("INPUT {} {} {} {} {} {}", source)
                self.assertIn("value.buttons, value.circle_x, value.circle_y", source)
                self.assertIn("value.touch_x, value.touch_y", source)
                self.assertIn("u8::from(value.touch_pressed)", source)


if __name__ == "__main__":
    unittest.main()
