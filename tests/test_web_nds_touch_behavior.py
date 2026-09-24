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


    def test_player_layout_keeps_virtual_controls_clear_of_the_touch_screen(self):
        player = (ROOT / "static" / "player.js").read_text(encoding="utf-8")
        bridge = (ROOT / "static" / "nds-touch.js").read_text(encoding="utf-8")
        # The shared resolver is the single source of the safe layout, and the
        # player must wire it into both placement and the resize/geometry poll.
        self.assertIn("const resolveTouchSafeControls =", bridge)
        self.assertIn("let resolvedPadPositions=null;", player)
        self.assertIn("const renderPadPositions = () => {", player)
        self.assertIn("resolvedPadPositions=padRoot.classList.contains(\"edit\") ? null : resolveTouchSafePositions(positions);", player)
        self.assertIn("applyControlSizes();renderPadPositions();", player)
        self.assertIn("refreshPadForTouchZone();", player)
        # The saved (custom) layout must survive; only the rendered slot moves.
        self.assertIn("resolvedPadPositions || positions", player)
        # The verified coordinate transform is untouched: the safe layout reuses
        # the shared bridge resolver instead of re-deriving the touch-screen map.
        self.assertIn("globalThis.AN3NdsTouchBridge?.resolveTouchSafeControls", player)
        self.assertIn("const viewport=resolveNdsVideoViewport(canvas,rect);", player)


if __name__ == "__main__":
    unittest.main()
