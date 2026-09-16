# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase A contract: Vibe Coded Emulator branding, Exit Game, autosave options.

These are source/asset contracts. The interactive autosave/exit path is
exercised separately in a browser; a static pass here is not interactive
acceptance.
"""

import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
PLAYER = (ROOT / "static" / "player.js").read_text(encoding="utf-8")
RUNTIME = (ROOT / "static" / "player-runtime.js").read_text(encoding="utf-8")
NATIVE_INDEX = (ROOT / "native-offline" / "web" / "index.html").read_text(encoding="utf-8")
NATIVE_CSS = (ROOT / "native-offline" / "web" / "native.css").read_text(encoding="utf-8")
MANIFEST = json.loads((ROOT / "static" / "manifest.webmanifest").read_text(encoding="utf-8"))


def png_size(path):
    header = path.read_bytes()[:24]
    if header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise AssertionError(f"{path.name} is not a PNG")
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


class PhaseABrandingTests(unittest.TestCase):
    def test_product_name_is_consistent_across_surfaces(self):
        self.assertIn('SITE_NAME = "Vibe Coded Emulator"', APP)
        self.assertEqual(MANIFEST["name"], "Vibe Coded Emulator")
        self.assertEqual(MANIFEST["short_name"], "Vibe Coded")
        self.assertIn("<title>Vibe Coded Emulator</title>", NATIVE_INDEX)
        self.assertIn("Vibe Coded Emulator", NATIVE_INDEX)

    def test_header_uses_transparent_brand_logo_asset(self):
        logo = ROOT / "static" / "brand-logo.png"
        self.assertTrue(logo.is_file())
        self.assertIn('class="brand-logo"', APP)
        self.assertIn('src="/static/brand-logo.png', APP)

    def test_generated_icons_match_png1_source(self):
        for name, expected in (("icon-192.png", (192, 192)), ("icon-512.png", (512, 512))):
            self.assertEqual(png_size(ROOT / "static" / name), expected)

    def test_native_shell_brand_uses_the_logo_and_version_is_bumped(self):
        self.assertIn("native-brand-logo", NATIVE_INDEX)
        self.assertIn("native-brand-logo", NATIVE_CSS)
        package = json.loads((ROOT / "native-offline" / "package.json").read_text(encoding="utf-8"))
        tauri = json.loads((ROOT / "native-offline" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
        android = json.loads((ROOT / "native-offline" / "src-tauri" / "tauri.android.conf.json").read_text(encoding="utf-8"))
        self.assertEqual(package["version"], "2.0.0")
        self.assertEqual(tauri["version"], "2.0.0")
        # GPLv3 transition release: every packaged app moves to 2.0.0.
        self.assertEqual(android["version"], "2.0.0")

    def test_flatpak_sources_track_the_desktop_version(self):
        tauri = json.loads((ROOT / "native-offline" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
        manifest = (ROOT / "native-offline" / "flatpak" / "space.an3tocom.offline.yml").read_text(encoding="utf-8")
        metainfo = (ROOT / "native-offline" / "flatpak" / "space.an3tocom.offline.metainfo.xml").read_text(encoding="utf-8")
        self.assertIn(f"vibecodedemulator-{tauri['version']}-linux-amd64.deb", manifest)
        self.assertIn(f'version="{tauri["version"]}"', metainfo)


class PhaseAAutosaveExitTests(unittest.TestCase):
    def test_autosave_modes_match_the_required_set(self):
        for mode in ('"off"', '"exit"', '"30"', '"10"', '"5"'):
            self.assertIn(mode, PLAYER)
        for value in ('value="off"', 'value="exit"', 'value="30"', 'value="10"', 'value="5"'):
            self.assertIn(value, APP)

    def test_autosave_uses_a_dedicated_slot_and_skips_unchanged_writes(self):
        self.assertIn("autoId()", RUNTIME)
        self.assertIn("getAuto()", RUNTIME)
        self.assertIn("putAuto(", RUNTIME)
        # No-op detection keeps the emulator thread and IndexedDB untouched when
        # the state digest is unchanged.
        self.assertIn("if(digest===lastAutosaveDigest)return false;", PLAYER)
        self.assertIn("data-auto-slot", APP)
        self.assertIn("data-load-auto", PLAYER)

    def test_exit_game_is_explicit_and_flushes_before_leaving(self):
        self.assertIn('id="exitGame"', APP)
        self.assertIn("function exitGame()", PLAYER)
        self.assertIn("Promise.race(", PLAYER)
        self.assertIn('addEventListener("pagehide"', PLAYER)

    def test_periodic_autosave_is_not_bound_to_the_render_loop(self):
        self.assertIn("setInterval(()=>{runAutosave()", PLAYER)
        self.assertNotIn("requestAnimationFrame(()=>{runAutosave()", PLAYER)

    def test_native_macos_shell_exposes_autosave_modes_and_exit_game(self):
        host = (ROOT / "native-offline" / "src-tauri" / "src" / "azahar_host.mm").read_text(encoding="utf-8")
        # macOS shares the auto-save model/parser with Android and Linux.
        self.assertIn('#include "../../native-runtime/core/auto_save_mode.h"', host)
        self.assertIn("an3::parse_auto_save_mode", host)
        self.assertIn("player_ui::auto_save_titles", host)
        self.assertIn("native_apply_auto_save_mode", host)
        self.assertIn("auto_save_on_exit()", host)
        self.assertIn('buttonWithTitle:@"Exit Game"', host)
        self.assertIn("- (void)exitGame:", host)
        # save_auto_state is the same atomic writer used on normal autosave.
        self.assertIn("autosave.state", host)


if __name__ == "__main__":
    unittest.main()
