// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject
import org.xmlpull.v1.XmlPullParser
import java.io.File

/**
 * One logical settings model shared by the library shell (MainActivity) and the
 * isolated `:game` process (NativeGameActivity + NativeGameOverlay).
 *
 * Global settings keep their historical keys. Graphics use `<id>-<system>`;
 * verified per-system emulation options use `core-<system>-<coreKey>`. A legacy
 * global value (for example `renderer`) is read only as a fallback on the
 * systems that predate it; legacy preferences are never deleted or copied.
 *
 * Writes go through SharedPreferences with a synchronous commit. Reads for the
 * shell re-parse the committed XML file, so the main process sees a `:game`
 * write without relying on the deprecated MODE_MULTI_PROCESS reload.
 */
object NativeSettings {
    private val byKey: Map<String, Pair<NativeSettingsSchema.Definition, String?>> by lazy {
        buildMap<String, Pair<NativeSettingsSchema.Definition, String?>> {
            for (definition in NativeSettingsSchema.global) put(definition.id, definition to null)
            for (system in NativeSettingsSchema.systems) {
                for (definition in NativeSettingsSchema.definitionsFor(system)) {
                    put(NativeSettingsSchema.storageKey(definition, system), definition to system)
                }
            }
        }
    }

    private fun prefs(context: Context): SharedPreferences =
        context.getSharedPreferences(NativeSettingsSchema.STORE, Context.MODE_PRIVATE)

    /**
     * Read the committed preferences file directly. SharedPreferences caches per
     * process, so a `:game` write is otherwise invisible to the shell; reading
     * the file is deterministic and does not depend on MODE_MULTI_PROCESS.
     */
    private fun storedValues(context: Context): Map<String, Any?> {
        val file = File(context.applicationInfo.dataDir, "shared_prefs/${NativeSettingsSchema.STORE}.xml")
        if (!file.isFile) return prefs(context).all
        val values = HashMap<String, Any?>()
        try {
            val parser = android.util.Xml.newPullParser()
            parser.setFeature(XmlPullParser.FEATURE_PROCESS_NAMESPACES, false)
            parser.setInput(file.reader())
            var event = parser.eventType
            while (event != XmlPullParser.END_DOCUMENT) {
                if (event == XmlPullParser.START_TAG) {
                    // Never `continue` here: the loop must always advance, and the
                    // `<map>` root has no `name` attribute.
                    val name = parser.getAttributeValue(null, "name")
                    when (parser.name) {
                        "string" -> { val text = parser.nextText(); if (name != null) values[name] = text }
                        "int" -> if (name != null) values[name] = parser.getAttributeValue(null, "value")?.toIntOrNull()
                        "long" -> if (name != null) values[name] = parser.getAttributeValue(null, "value")?.toLong()
                        "float" -> if (name != null) values[name] = parser.getAttributeValue(null, "value")?.toFloatOrNull()
                        "boolean" -> if (name != null) values[name] = parser.getAttributeValue(null, "value") == "true"
                        "set" -> parser.nextText()
                    }
                }
                event = parser.next()
            }
        } catch (_: Exception) {
            return prefs(context).all
        }
        return values
    }

    /** Resolve the stored value, the documented legacy fallback, then the default. */
    fun effective(values: Map<String, Any?>, definition: NativeSettingsSchema.Definition, system: String?): Any? {
        coerce(definition, values[NativeSettingsSchema.storageKey(definition, system)])?.let { return it }
        for (legacy in definition.legacyKeys) {
            coerce(definition, values[legacy])?.let { return it }
        }
        if (definition.legacyResolve == "native-autosave") return NativeAutoSave.resolveValues(values)
        return coerce(definition, definition.default)
    }

    private fun boolOf(value: Any?): Boolean? = when (value) {
        is Boolean -> value
        is String -> when (value.lowercase()) { "true" -> true; "false" -> false; else -> null }
        else -> null
    }

    private fun intOf(value: Any?): Int? = when (value) {
        is Int -> value
        is Number -> value.toInt()
        is String -> value.toIntOrNull()
        else -> null
    }

    /**
     * Validate a raw value against its logical type (enum/range) and return it
     * in the definition's storage type; null means unsupported or malformed.
     */
    fun coerce(definition: NativeSettingsSchema.Definition, value: Any?): Any? {
        if (value == null) return null
        val logical: Any = when (definition.type) {
            NativeSettingsSchema.Type.BOOL -> boolOf(value) ?: return null
            NativeSettingsSchema.Type.INT -> {
                val number = intOf(value) ?: return null
                if (definition.min != null && definition.max != null && number !in definition.min..definition.max) return null
                number
            }
            NativeSettingsSchema.Type.ENUM -> value.toString().takeIf { it in definition.values } ?: return null
            NativeSettingsSchema.Type.STRING -> value.toString()
        }
        return when (definition.storage) {
            "int" -> when (logical) {
                is Int -> logical
                is Number -> logical.toInt()
                else -> logical.toString().toIntOrNull()
            }
            "bool" -> boolOf(logical)
            else -> logical.toString()
        }
    }

    /** Effective settings for the shell UI, mirroring [NativeSettingsSchema]. */
    fun all(context: Context): JSONObject {
        val values = storedValues(context)
        val global = JSONObject()
        for (definition in NativeSettingsSchema.global) global.put(definition.id, effective(values, definition, null))
        val systems = JSONObject()
        for (system in NativeSettingsSchema.systems) {
            val systemValues = JSONObject()
            for (definition in NativeSettingsSchema.definitionsFor(system)) {
                systemValues.put(definition.id, effective(values, definition, system))
            }
            systems.put(system, systemValues)
        }
        return JSONObject()
            .put("global", global)
            .put("systems", systems)
            .put("unavailable", unavailable())
    }

    private fun unavailable(): JSONObject {
        val result = JSONObject()
        for (system in NativeSettingsSchema.systems) {
            val reason = NativeSettingsSchema.unavailableReason("android", system) ?: continue
            result.put(system, reason)
        }
        return result
    }

    /**
     * Apply several edits in one committed transaction. Unknown keys,
     * unsupported enum values, runtime-pinned options, and out-of-range
     * integers are rejected instead of stored.
     */
    fun save(context: Context, edits: JSONObject): JSONObject {
        val editor = prefs(context).edit()
        val saved = mutableListOf<String>()
        val rejected = mutableListOf<String>()
        for (key in edits.keys()) {
            val entry = byKey[key]
            if (entry == null) { rejected += key; continue }
            val definition = entry.first
            if (!definition.editable) { rejected += key; continue }
            val coerced = coerce(definition, edits.get(key))
            if (coerced == null) { rejected += key; continue }
            when (coerced) {
                is Boolean -> editor.putBoolean(key, coerced)
                is Int -> editor.putInt(key, coerced)
                else -> editor.putString(key, coerced.toString())
            }
            saved += key
        }
        // Commit synchronously: the game process reads this file at launch, and
        // an async apply() can be lost if the device is killed right after Save.
        editor.commit()
        return JSONObject().put("ok", rejected.isEmpty()).put("saved", JSONArray(saved)).put("rejected", JSONArray(rejected))
    }

    /**
     * Reset one system's graphics preferences to their defaults. Legacy keys,
     * other systems, emulation options, saves and ROMs are untouched.
     */
    fun resetGraphics(context: Context, system: String): JSONObject {
        val editor = prefs(context).edit()
        val saved = mutableListOf<String>()
        for (definition in NativeSettingsSchema.graphics[system].orEmpty()) {
            val key = NativeSettingsSchema.storageKey(definition, system)
            val coerced = coerce(definition, definition.default)
                ?: definition.values.firstOrNull()?.let { coerce(definition, it) }
                ?: continue
            when (coerced) {
                is Boolean -> editor.putBoolean(key, coerced)
                is Int -> editor.putInt(key, coerced)
                else -> editor.putString(key, coerced.toString())
            }
            saved += key
        }
        editor.commit()
        return JSONObject().put("ok", true).put("saved", JSONArray(saved))
    }

    /** Requested renderer for a system (legacy `renderer` fallback included). */
    fun renderer(preferences: SharedPreferences, system: String): String {
        val definition = NativeSettingsSchema.graphics[system]?.firstOrNull { it.id == "renderer" } ?: return "auto"
        return (effective(preferences.all, definition, system) as? String) ?: "auto"
    }

    /** Effective screen layout for a system; null when the system has no layouts. */
    fun layout(preferences: SharedPreferences, system: String): String? {
        val definition = NativeSettingsSchema.graphics[system]?.firstOrNull { it.id == "screen-layout" } ?: return null
        return effective(preferences.all, definition, system) as? String
    }

    fun isSystemAvailableOnAndroid(system: String): Boolean = NativeSettingsSchema.isAvailable("android", system)
}
