# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Guards for the canonical per-core settings model.

The behavior of the settings model is exercised behaviorally by
tests/native_settings.test.mjs (node --test). These checks keep the Android
adapter, the generated schema, and the migration rules wired to that one model,
and confirm the Android 3DS renderer workarounds are not bypassed.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native-offline"
SCHEMA = NATIVE / "shared" / "native-settings-schema.json"
LAYOUT_SCHEMA = NATIVE / "shared" / "native-layout-schema.json"
GENERATOR = NATIVE / "scripts" / "generate-native-settings.mjs"
KOTLIN_SCHEMA = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeSettingsSchema.kt"
KOTLIN_SETTINGS = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeSettings.kt"
GAME_ACTIVITY = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeGameActivity.kt"
OVERLAY = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeGameOverlay.kt"
MAIN_ACTIVITY = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/MainActivity.kt"
JS_MODEL = NATIVE / "web" / "native-settings.js"
WEB_UI = NATIVE / "web" / "game-settings.js"
INDEX = NATIVE / "web" / "index.html"
HOST = NATIVE / "native-runtime/core/libretro_host.cpp"
NODE_TEST = ROOT / "tests" / "native_settings.test.mjs"


def source(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


class NativeSettingsSchemaTests(unittest.TestCase):
    def test_schema_declares_global_and_per_system_scopes(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(schema["systems"], ["gba", "nds", "3ds", "switch"])
        self.assertTrue(schema["global"], "global settings must be declared")
        global_ids = {definition["id"] for definition in schema["global"]}
        # Global settings keep one shared key; they are not duplicated per core.
        for key in ("volume", "mute", "latency", "quality", "show-fps", "start-fullscreen"):
            self.assertIn(key, global_ids)

    def test_every_system_has_graphics_and_emulation_scopes(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        for system in schema["systems"]:
            self.assertIn(system, schema["systemGraphics"])
            self.assertIn(system, schema["systemEmulation"])
            self.assertIn("renderer", schema["systemGraphics"][system])
        for system in ("nds", "3ds"):
            self.assertIn("screen-layout", schema["systemGraphics"][system])
        self.assertNotIn("screen-layout", schema["systemGraphics"]["gba"])
        self.assertNotIn("screen-layout", schema["systemGraphics"]["switch"])

    def test_response_values_match_the_layout_schema(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        layouts = json.loads(LAYOUT_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(schema["screenLayout"]["valuesFrom"], "native-layout-schema")
        self.assertEqual(set(layouts["systems"].keys()), {"nds", "3ds"})

    def test_switch_is_declared_unavailable_on_android(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        entry = schema["platformAvailability"]["switch"]["android"]
        self.assertFalse(entry["available"])
        self.assertIn("Android", entry["reason"])

    def test_runtime_pinned_options_are_declared(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        pinned = schema["pinnedCoreOptions"]
        self.assertIn("citra_use_hw_shader", pinned["3ds"]["android"])
        self.assertIn("citra_use_disk_shader_cache", pinned["3ds"]["android"])
        self.assertIn("citra_graphics_api", pinned["3ds"]["android"])
        self.assertEqual(pinned["gba"]["android"], [])
        self.assertEqual(pinned["switch"]["android"], [])

    def test_generated_outputs_are_in_sync_with_the_schema(self):
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (KOTLIN_SCHEMA, JS_MODEL)}
        result = subprocess.run(
            ["node", str(GENERATOR)], cwd=NATIVE, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (KOTLIN_SCHEMA, JS_MODEL)}
        self.assertEqual(before, after, "committed generated settings files are stale; run npm run prepare-web")


class NativeSettingsAdapterTests(unittest.TestCase):
    def test_kotlin_schema_uses_system_scoped_keys(self):
        kotlin = source(KOTLIN_SCHEMA)
        self.assertIn('const val STORE = "an3-native-game"', kotlin)
        self.assertIn('fun key(id: String, system: String?): String = if (system == null) id else "$id-$system"', kotlin)
        self.assertIn('listOf("auto", "vulkan", "opengl")', kotlin)
        self.assertIn('Definition("screen-layout"', kotlin)
        self.assertIn('val unavailable: Map<String, Map<String, String>>', kotlin)
        self.assertIn('"android" to "Nintendo Switch is not supported on Android', kotlin)

    def test_adapter_reads_across_processes_and_migrates_legacy(self):
        kotlin = source(KOTLIN_SETTINGS)
        # MODE_MULTI_PROCESS makes the main process observe a :game write.
        self.assertIn("Context.MODE_MULTI_PROCESS", kotlin)
        # Legacy fallback is read, never copied to every core.
        self.assertIn("definition.legacyKeys", kotlin)
        self.assertIn("NativeAutoSave.resolve", kotlin)
        # One transaction for several related edits, committed before returning.
        self.assertIn("val editor = prefs(context).edit()", kotlin)
        self.assertIn("editor.commit()", kotlin)
        self.assertIn("fun resetGraphics(context: Context, system: String)", kotlin)

    def test_bridge_registers_the_settings_surface(self):
        activity = source(MAIN_ACTIVITY)
        self.assertIn('webView.addJavascriptInterface(AndroidNativeSettingsBridge(this), "AN3AndroidSettings")', activity)
        self.assertIn("fun all(): String = NativeSettings.all(activity).toString()", activity)
        self.assertIn("fun resetGraphics(system: String): String", activity)

    def test_game_reads_per_system_settings(self):
        activity = source(GAME_ACTIVITY)
        self.assertIn("NativeSettings.renderer(preferences, system)", activity)
        self.assertIn("NativeSettings.layout(preferences, system)", activity)
        self.assertNotIn('preferences.getString("renderer", "auto")', activity)

    def test_overlay_writes_per_system_settings_and_hides_pinned_options(self):
        overlay = source(OVERLAY)
        self.assertIn('edit.putString("renderer-$system", v)', overlay)
        self.assertIn("NativeSettings.renderer(prefs, system)", overlay)
        self.assertIn("key in NativeSettingsSchema.pinned(system)", overlay)
        self.assertIn("Reset Graphics to Defaults", overlay)
        self.assertIn("NativeSettings.resetGraphics(activity, system)", overlay)
        # The draft/discard and explicit Save semantics are preserved.
        self.assertIn("val draft = mutableMapOf", overlay)
        self.assertIn('button("Save Settings")', overlay)

    def test_web_shell_loads_the_canonical_model(self):
        index = source(INDEX)
        self.assertIn('/native-settings.js?v=', index)
        self.assertIn('/game-settings.js?v=', index)
        self.assertIn('data-testid="game-settings"', index)
        self.assertIn('data-testid="application-settings"', index)
        ui = source(WEB_UI)
        self.assertIn("window.NativeSettingsModel", ui)
        self.assertIn("window.AN3AndroidSettings", ui)
        self.assertIn("Reset Graphics to Defaults", ui)

    def test_js_model_per_core_keys(self):
        model = source(JS_MODEL)
        self.assertIn("const key = (id, system) => (system == null ? id : id + \"-\" + system);", model)
        self.assertIn("resetGraphicsEdits", model)
        self.assertIn("effective", model)


class NativeSettingsWorkaroundTests(unittest.TestCase):
    def test_android_3ds_gles_and_vulkan_pins_remain(self):
        host = source(HOST)
        self.assertIn('!std::strcmp(variable->key, "citra_use_hw_shader")) variable->value="disabled";', host)
        self.assertIn('!std::strcmp(variable->key, "citra_use_disk_shader_cache")) variable->value="disabled";', host)
        self.assertIn('graphics_api_ == "Vulkan"', host)
        # Pins stay scoped to the 3DS system.
        self.assertIn("system_ == NativeSystem::ThreeDS", host)

    def test_settings_model_cannot_override_pinned_options(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        editable = set()
        for definitions in schema["systemGraphics"].values():
            editable.update(definitions)
        # The runtime-pinned names are not offered as editable setting ids.
        for pinned in schema["pinnedCoreOptions"]["3ds"]["android"]:
            self.assertNotIn(pinned, editable)


class NativeSettingsBehaviorTests(unittest.TestCase):
    def test_behavioral_model_suite_passes(self):
        result = subprocess.run(
            ["node", "--test", str(NODE_TEST)], cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pass", result.stdout)


if __name__ == "__main__":
    unittest.main()
