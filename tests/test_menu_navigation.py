# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""In-game menu navigation, save/discard/exit and tab-arrow guards.

The footer and tab strip are Kotlin views, so these tests pin the structural
contract (which actions persist, which discard, which terminate) and the
scroll-indicator logic. Live behavior is verified on the AVD.
"""

from __future__ import annotations

import json
import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native-offline"
OVERLAY = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeGameOverlay.kt"
ACTIVITY = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeGameActivity.kt"
SETTINGS = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeSettings.kt"
HOST = NATIVE / "native-runtime/core/libretro_host.cpp"
SCHEMA = NATIVE / "shared/native-settings-schema.json"


def source(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


class MenuFooterTests(unittest.TestCase):
    def setUp(self):
        self.overlay = source(OVERLAY)

    def test_footer_has_the_three_actions(self):
        self.assertIn('footerButton("Save and Exit")', self.overlay)
        self.assertIn('footerButton("Exit")', self.overlay)
        self.assertIn('footerButton("Return to Library")', self.overlay)
        self.assertNotIn('"Save Settings"', self.overlay)

    def test_save_and_exit_persists_through_the_canonical_service(self):
        self.assertIn("val result = NativeSettings.save(activity, edits)", self.overlay)
        self.assertIn("if (!result.optBoolean(\"ok\")) return false", self.overlay)
        # Only the successful branch closes the menu.
        self.assertRegex(self.overlay, r"if \(persistDraft\(\)\) \{\s*saved\.text = [^\n]*\n\s*dialog\.dismiss\(\)")
        self.assertIn("Could not save settings. The menu stays open so nothing is lost.", self.overlay)

    def test_save_targets_per_core_keys_not_a_global_renderer(self):
        self.assertIn('edits.put("renderer-$system", draft.getValue("renderer"))', self.overlay)
        self.assertNotRegex(self.overlay, r'putString\("renderer",')
        for key in ('"volume"', '"latency"', '"quality"', '"autosave-mode"', '"key-map"'):
            self.assertIn(f"edits.put({key}", self.overlay)

    def test_exit_discards_without_persisting(self):
        block = self.overlay[self.overlay.index('footerButton("Exit")'):]
        block = block[:block.index("\n")]
        self.assertIn("dialog.dismiss()", block)
        self.assertNotIn("persistDraft", block)

    def test_return_to_library_terminates_and_does_not_persist(self):
        block = self.overlay[self.overlay.index('footerButton("Return to Library")'):]
        block = block[:block.index("\n")]
        self.assertIn("dialog.dismiss()", block)
        self.assertIn("activity.finish()", block)
        self.assertNotIn("persistDraft", block)

    def test_dismiss_reverts_immediate_previews(self):
        listener = self.overlay[self.overlay.index("dialog.setOnDismissListener"):]
        listener = listener[:listener.index("dialog.window")]
        self.assertIn("previewLayout(NativeLayoutModel.normalize(activity, system,", listener)
        self.assertIn("refreshPreferences()", listener)

    def test_escape_is_discard(self):
        escape = self.overlay[self.overlay.index("fun handleEscape()"):]
        escape = escape[:escape.index("\n    }")]
        self.assertIn("menu?.dismiss()", escape)
        self.assertNotIn("persistDraft", escape)


class MenuTabArrowTests(unittest.TestCase):
    def setUp(self):
        self.overlay = source(OVERLAY)

    def test_arrows_exist_with_accessible_labels(self):
        self.assertIn('contentDescription = "Previous tabs"', self.overlay)
        self.assertIn('contentDescription = "Next tabs"', self.overlay)

    def test_visibility_tracks_real_scroll_extent(self):
        update = self.overlay[self.overlay.index("fun updateTabArrows()"):]
        update = update[:update.index("fun scrollToNextTab")]
        self.assertIn("tabScroll.canScrollHorizontally(-1)", update)
        self.assertIn("tabScroll.canScrollHorizontally(1)", update)
        # No hardcoded screen dimensions.
        self.assertNotRegex(update, r"\b\d{3,}\b")

    def test_arrows_scroll_and_track_changes(self):
        self.assertIn("previousTabs.setOnClickListener { scrollToNextTab(-1)", self.overlay)
        self.assertIn("nextTabs.setOnClickListener { scrollToNextTab(1)", self.overlay)
        self.assertIn("tabScroll.setOnScrollChangeListener { _, _, _, _, _ -> updateTabArrows() }", self.overlay)
        self.assertIn("tabs.addOnLayoutChangeListener { _, _, _, _, _, _, _, _, _ -> updateTabArrows() }", self.overlay)

    def test_active_tab_is_scrolled_into_view(self):
        self.assertIn("ensureTabVisible(tab)", self.overlay)
        ensure = self.overlay[self.overlay.index("fun ensureTabVisible("):]
        ensure = ensure[:ensure.index("previousTabs.setOnClickListener")]
        self.assertIn("child.left < visibleLeft", ensure)
        self.assertIn("child.right > visibleRight", ensure)

    def test_next_tab_scroll_reveals_a_hidden_tab(self):
        scroll = self.overlay[self.overlay.index("fun scrollToNextTab("):]
        scroll = scroll[:scroll.index("fun ensureTabVisible(")]
        self.assertIn("child.right > visibleRight + 1", scroll)
        self.assertIn("child.left < visibleLeft - 1", scroll)
        self.assertIn("smoothScrollTo", scroll)


class MenuLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.activity = source(ACTIVITY)

    def test_return_to_library_uses_the_existing_termination_path(self):
        # finish() destroys the activity; onDestroy stops the native session once.
        destroy = self.activity[self.activity.index("override fun onDestroy()"):]
        destroy = destroy[:destroy.index("super.onDestroy()")]
        self.assertIn("if (active) {", destroy)
        self.assertIn("if (system == \"switch\")", destroy)
        self.assertIn("nativeEdenStop(edenHandle)", destroy)
        self.assertIn("nativeEdenDestroy(edenHandle)", destroy)
        self.assertIn("else nativeStop(false)", destroy)
        self.assertIn("unbindService(controllerConnection)", destroy)
        self.assertIn("sendToControllerService(ControllerHostService.MSG_DETACH)", destroy)
        self.assertIn("nativeCancelPointer()", destroy)

    def test_surface_destroy_preserves_resume_semantics(self):
        surface = self.activity[self.activity.index("override fun surfaceDestroyed"):]
        surface = surface[:surface.index("override fun onPause")]
        self.assertIn("nativeStop(!isFinishing)", surface)
        self.assertIn("releasePointer()", surface)

    def test_phone_menu_utility_still_opens_the_menu(self):
        overlay = source(OVERLAY)
        self.assertIn('"OPEN_MENU" -> if (!isMenuOpen()) showMenu()', overlay)
        self.assertIn("fun isMenuOpen()", overlay)
        # Remote input is released when the menu opens and on disconnect.
        self.assertIn("fun releaseRemoteInput()", overlay)
        self.assertIn("for (index in 0..11) input(index, false)", overlay)

    def test_menu_does_not_own_a_second_settings_store(self):
        overlay = source(OVERLAY)
        # The overlay edits the SharedPreferences it was handed; no new store.
        self.assertNotIn("getSharedPreferences(", overlay)
        self.assertIn("NativeSettings.save(activity, edits)", overlay)


class MenuRendererSafetyTests(unittest.TestCase):
    def test_android_3ds_renderer_pins_remain(self):
        host = source(HOST)
        self.assertIn('!std::strcmp(variable->key, "citra_use_hw_shader")) variable->value="disabled";', host)
        self.assertIn('!std::strcmp(variable->key, "citra_use_disk_shader_cache")) variable->value="disabled";', host)

    def test_settings_schema_unchanged_per_core(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        for system in ("gba", "nds", "3ds", "switch"):
            self.assertIn("renderer", schema["systemGraphics"][system])


if __name__ == "__main__":
    unittest.main()
