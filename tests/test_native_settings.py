# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Guards for the canonical per-core settings model.

The behaviour of the settings model is exercised behaviorally by
tests/native_settings.test.mjs (node --test). These checks keep the Android
adapter, the generated schema, the verified core-option registry and the
migration policy wired to that one model, and confirm the Android 3DS renderer
workarounds are not bypassed.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native-offline"
SCHEMA = NATIVE / "shared" / "native-settings-schema.json"
LAYOUT_SCHEMA = NATIVE / "shared" / "native-layout-schema.json"
REGISTRY = NATIVE / "shared" / "core-option-registry.json"
REGISTRY_GENERATOR = NATIVE / "scripts" / "generate-core-option-registry.mjs"
PROBE = NATIVE / "tools" / "core_option_probe.cpp"
GENERATOR = NATIVE / "scripts" / "generate-native-settings.mjs"
KOTLIN_SCHEMA = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeSettingsSchema.kt"
KOTLIN_SETTINGS = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeSettings.kt"
GAME_ACTIVITY = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeGameActivity.kt"
OVERLAY = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeGameOverlay.kt"
AUTOSAVE = NATIVE / "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeAutoSave.kt"
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

    def test_switch_is_declared_available_on_android(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertNotIn("android", schema["platformAvailability"]["switch"])

    def test_runtime_pinned_options_are_declared(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        pinned = schema["pinnedCoreOptions"]
        for key in ("citra_graphics_api", "citra_use_hw_shader", "citra_use_disk_shader_cache", "citra_layout_option"):
            self.assertIn(key, pinned["3ds"]["android"])
        for key in ("melonds_render_mode", "melonds_threaded_renderer", "melonds_touch_mode", "melonds_show_cursor", "melonds_number_of_screen_layouts", "melonds_screen_layout1"):
            self.assertIn(key, pinned["nds"]["android"])
        self.assertEqual(pinned["gba"]["android"], [])
        self.assertEqual(pinned["switch"]["android"], [])

    def test_generated_outputs_are_in_sync_with_the_schema(self):
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (KOTLIN_SCHEMA, JS_MODEL)}
        result = subprocess.run(
            ["node", str(GENERATOR)], cwd=NATIVE, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (KOTLIN_SCHEMA, JS_MODEL)}
        self.assertEqual(before, after, "committed generated settings files are stale; run npm run prepare-web")


class CoreOptionRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = json.loads(REGISTRY.read_text(encoding="utf-8"))

    def test_registry_is_generated_from_the_vendored_cores(self):
        self.assertTrue(PROBE.is_file())
        self.assertIn("core_option_probe.cpp", source(REGISTRY_GENERATOR))
        manifest = json.loads((NATIVE / "vendor/libretro/macos-arm64/manifest.json").read_text(encoding="utf-8"))
        versions = {core["system"]: core["version"] for core in manifest["cores"]}
        self.assertEqual(self.registry["systems"]["gba"]["version"], versions["gba"])
        self.assertEqual(self.registry["systems"]["nds"]["version"], versions["nds"])
        azahar = json.loads((NATIVE / "vendor/azahar/macos-arm64/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(self.registry["systems"]["3ds"]["version"], azahar["version"])

    def test_registry_exposes_real_options_per_system(self):
        counts = {system: len(entry["options"]) for system, entry in self.registry["systems"].items()}
        self.assertEqual(counts["gba"], 17)
        self.assertEqual(counts["nds"], 73)
        self.assertEqual(counts["3ds"], 32)
        self.assertEqual(counts["switch"], 0)
        for system in ("gba", "nds", "3ds"):
            for option in self.registry["systems"][system]["options"]:
                self.assertTrue(option["key"])
                self.assertTrue(option["values"], option["key"])
                # Core defaults can differ in case from the labelled values (Azahar);
                # the generated model normalises the default to an offered value.
                self.assertTrue(any(entry["value"].lower() == option["default"].lower() for entry in option["values"]), option["key"])

    def test_no_host_specific_values_are_committed(self):
        text = REGISTRY.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", text), "MAC address leaked")
        for path in ("/Users/", "/home/", "/private/", "/tmp/"):
            self.assertNotIn(path, text)
        for option in self.registry["systems"]["nds"]["options"]:
            self.assertNotIn(option["key"], ("melonds_direct_network_interface", "melonds_firmware_nds_path", "melonds_dsi_nand_path"))


class NativeSettingsAdapterTests(unittest.TestCase):
    def test_kotlin_schema_uses_storage_keys(self):
        kotlin = source(KOTLIN_SCHEMA)
        self.assertIn('const val STORE = "an3-native-game"', kotlin)
        self.assertIn('fun storageKey(definition: Definition, system: String?): String', kotlin)
        self.assertIn('"core-gba-mgba_gb_model"', kotlin)
        self.assertIn('"core-nds-melonds_jit_enable"', kotlin)
        self.assertIn('"core-3ds-citra_cpu_clock_percentage"', kotlin)
        self.assertIn("val unavailable: Map<String, Map<String, String>>", kotlin)

    def test_adapter_reads_fresh_files_and_migrates_legacy(self):
        kotlin = source(KOTLIN_SETTINGS)
        # Shell reads re-parse the committed file, independent of process caches.
        self.assertIn('shared_prefs/${NativeSettingsSchema.STORE}.xml', kotlin)
        self.assertIn("Context.MODE_PRIVATE", kotlin)
        self.assertNotIn("Context.MODE_MULTI_PROCESS", kotlin)
        # Legacy fallback is read, never copied to every core.
        self.assertIn("definition.legacyKeys", kotlin)
        self.assertIn("NativeAutoSave.resolveValues", kotlin)
        # One committed transaction for several related edits.
        self.assertIn("val editor = prefs(context).edit()", kotlin)
        self.assertIn("editor.commit()", kotlin)
        self.assertIn("fun resetGraphics(context: Context, system: String)", kotlin)
        # Runtime-pinned options cannot be written through the bridge.
        self.assertIn("if (!definition.editable) { rejected += key; continue }", kotlin)

    def test_adapter_xml_reader_always_advances(self):
        # Regression: the `<map>` root has no `name` attribute; skipping it with
        # `?: continue` skipped `parser.next()` and hung the shell forever.
        kotlin = source(KOTLIN_SETTINGS)
        reader = kotlin[kotlin.index("private fun storedValues"):kotlin.index("fun effective(")]
        self.assertNotIn("?: continue", reader)
        self.assertIn("event = parser.next()", reader)
        self.assertIn('"set" -> parser.nextText()', reader)

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

    def test_autosave_resolves_from_a_value_map(self):
        autosave = source(AUTOSAVE)
        self.assertIn("fun resolveValues(values: Map<String, Any?>): String", autosave)
        self.assertIn('null -> true', autosave)

    def test_overlay_writes_per_system_settings_and_hides_pinned_options(self):
        overlay = source(OVERLAY)
        self.assertIn('edits.put("renderer-$system", draft.getValue("renderer"))', overlay)
        self.assertIn("NativeSettings.renderer(prefs, system)", overlay)
        self.assertIn("key in NativeSettingsSchema.pinned(system)", overlay)
        self.assertIn("Reset Graphics to Defaults", overlay)
        self.assertIn("NativeSettings.resetGraphics(activity, system)", overlay)
        self.assertIn("val draft = mutableMapOf", overlay)
        self.assertIn('footerButton("Save and Exit")', overlay)

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
        self.assertIn("editable !== false", ui)

    def test_js_model_exposes_emulation_and_storage_keys(self):
        model = source(JS_MODEL)
        self.assertIn("const storageKeyFor = (definition, system) => definition.storageKey || key(definition.id, system);", model)
        self.assertIn("resetGraphicsEdits", model)
        self.assertIn("effective", model)
        self.assertIn('"core-gba-mgba_gb_model"', model)


class NativeSettingsWorkaroundTests(unittest.TestCase):
    def test_android_3ds_gles_and_vulkan_pins_remain(self):
        host = source(HOST)
        self.assertIn('!std::strcmp(variable->key, "citra_use_hw_shader")) variable->value="disabled";', host)
        self.assertIn('!std::strcmp(variable->key, "citra_use_disk_shader_cache")) variable->value="disabled";', host)
        self.assertIn('graphics_api_ == "Vulkan"', host)
        self.assertIn("system_ == NativeSystem::ThreeDS", host)

    def test_settings_model_cannot_override_pinned_options(self):
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        model = source(JS_MODEL)
        for key in schema["pinnedCoreOptions"]["3ds"]["android"]:
            self.assertIn(f'"core-3ds-{key}"', model)
            # Pinned definitions are present but marked non-editable.
            self.assertRegex(model, re.compile(rf'"id": "{re.escape(key)}",(?:.|\n)*?"editable": false'))
        self.assertTrue(any(option["key"] == "melonds_render_mode" for option in registry["systems"]["nds"]["options"]))


class NativeSettingsBehaviorTests(unittest.TestCase):
    def test_behavioral_model_suite_passes(self):
        result = subprocess.run(
            ["node", "--test", str(NODE_TEST)], cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pass", result.stdout)


if __name__ == "__main__":
    unittest.main()
