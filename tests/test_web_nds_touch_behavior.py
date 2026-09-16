# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class WebNdsTouchBehaviorTests(unittest.TestCase):
    def test_geometry_and_presentation_layer_contract(self):
        result = subprocess.run(
            ["node", str(ROOT / "tests" / "web_nds_touch_behavior.test.js")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("web NDS touch behavior: ok", result.stdout)

    def test_player_keeps_renderer_presentation_noninteractive(self):
        player = (ROOT / "static" / "player.js").read_text(encoding="utf-8")
        stylesheet = (ROOT / "static" / "site.css").read_text(encoding="utf-8")
        self.assertIn('canvas:not(.an3-render-canvas)', player)
        self.assertIn('resolveSourceCanvas?.(gameRoot,hit,path)', player)
        self.assertIn('isProtectedUiTarget?.(gameRoot,event.target,path)', player)
        self.assertIn('if (protectedUi) return;', player)
        self.assertIn('let releaseRootNdsTouch=()=>{};', player)
        self.assertIn('releaseRootNdsTouch("emulator-menu-open")', player)
        self.assertIn('addEventListener("blur",()=>releaseRootNdsTouch("window-blur")', player)
        self.assertIn('document.addEventListener("visibilitychange",()=>{if(document.hidden)releaseRootNdsTouch("document-hidden");}', player)
        self.assertIn('document.addEventListener("fullscreenchange",()=>releaseRootNdsTouch("fullscreen-change")', player)
        self.assertIn('isProtectedUiEvent(event)', player)
        self.assertIn('if (!mapped && type !== "mouseup") return false;', player)
        self.assertIn('.an3-render-canvas{pointer-events:none!important', stylesheet)


if __name__ == "__main__":
    unittest.main()
