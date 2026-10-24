# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression contracts for the bundled Windows native player.

The installed Windows shell owns ROM picking and every control surface; the
portable player must not link GTK or open a second controls window. Those two
facts are what let the hosted package smoke see exactly one player window and
reach its first frame.
"""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILD = (ROOT / "native-offline/scripts/build-windows-runtime.sh").read_text(encoding="utf-8")
RUNTIME = (ROOT / "native-offline/native-runtime/platform/linux/linux_runtime.cpp").read_text(encoding="utf-8")
CONTROLS = (ROOT / "native-offline/native-runtime/platform/linux/linux_controls.h").read_text(encoding="utf-8")
STUB = (ROOT / "native-offline/native-runtime/platform/linux/windows_controls_stub.cpp").read_text(encoding="utf-8")
SHELL = (ROOT / "native-offline/src-tauri/src/windows_runtime.rs").read_text(encoding="utf-8")


class WindowsNativeRuntimeTests(unittest.TestCase):
    def test_player_builds_without_gtk_or_the_linux_controls_panel(self):
        self.assertIn("-DAN3_WINDOWS_TAURI_HOST", BUILD)
        self.assertIn("windows_controls_stub.cpp", BUILD)
        self.assertNotIn("linux_controls.cpp", BUILD)
        self.assertNotIn("gtk+-3.0", BUILD)
        self.assertIn("bool no_controls = true;", RUNTIME)
        # GTK's include and its file picker are Linux-only in this binary.
        include = RUNTIME.index("#include <gtk/gtk.h>")
        guard = RUNTIME.rindex("#if !defined(AN3_WINDOWS_TAURI_HOST)", 0, include)
        self.assertLess(guard, include)
        choose_rom = RUNTIME[RUNTIME.index("std::optional<std::string> choose_rom()"):]
        self.assertIn("return std::nullopt;", choose_rom[:400])

    def test_controls_stub_matches_the_current_panel_interface(self):
        self.assertIn("LinuxControlPanel::LinuxControlPanel(NativeCoreHost&", STUB)
        self.assertIn("bool LinuxControlPanel::initialize(std::string& error)", STUB)
        self.assertIn("Windows native controls are provided by the application shell.", STUB)
        self.assertIn("class LinuxControlPanel", CONTROLS)
        for member in ("pump", "show", "hide", "toggle", "show_pad", "visible"):
            self.assertIn(f"void LinuxControlPanel::{member}()" if member != "visible" else "bool LinuxControlPanel::visible() const", STUB)

    def test_shell_owns_controls_and_does_not_advertise_dead_menu_keys(self):
        self.assertIn('"--control-stdin", "--no-controls"', SHELL)
        self.assertNotIn("Menu: F2", SHELL)
        for key in ("F5/F9", "F4", "Esc"):
            self.assertIn(key, SHELL)


if __name__ == "__main__":
    unittest.main()
