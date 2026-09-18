// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONObject

/**
 * One logical settings model shared by the library shell (MainActivity) and the
 * isolated `:game` process (NativeGameActivity + NativeGameOverlay).
 *
 * Global settings keep their historical keys. Per-system settings use
 * `<id>-<system>` from [NativeSettingsSchema], so one system's value can never
 * overwrite another's. A legacy global value (for example `renderer`) is read
 * only as a fallback until the user stores an explicit per-system value; legacy
 * preferences are never deleted or blindly copied between cores.
 */
object NativeSettings {
    private val byKey: Map<String, Pair<NativeSettingsSchema.Definition, String?>> by lazy {
        buildMap<String, Pair<NativeSettingsSchema.Definition, String?>> {
            for (definition in NativeSettingsSchema.global) put(definition.id, definition to null)
            for (system in NativeSettingsSchema.systems) {
                for (definition in NativeSettingsSchema.definitionsFor(system)) {
                    put(NativeSettingsSchema.key(definition.id, system), definition to system)
                }
            }
        }
    }

    @Suppress("DEPRECATION")
    private fun prefs(context: Context): SharedPreferences =
        context.getSharedPreferences(NativeSettingsSchema.STORE, Context.MODE_MULTI_PROCESS)

    private fun read(preferences: SharedPreferences, definition: NativeSettingsSchema.Definition, key: String): Any? {
        if (!preferences.contains(key)) return null
        return when (definition.type) {
            NativeSettingsSchema.Type.BOOL -> preferences.getBoolean(key, false)
            NativeSettingsSchema.Type.INT -> preferences.getInt(key, 0)
            else -> preferences.getString(key, null)
        }
    }

    /** Resolve the stored per-system value, the documented legacy fallback, then the default. */
    fun effective(preferences: SharedPreferences, definition: NativeSettingsSchema.Definition, system: String?): Any? {
        val own = read(preferences, definition, NativeSettingsSchema.key(definition.id, system))
        coerce(definition, own)?.let { return it }
        for (legacy in definition.legacyKeys) {
            coerce(definition, read(preferences, definition, legacy))?.let { return it }
        }
        if (definition.legacyResolve == "native-autosave") return NativeAutoSave.resolve(preferences)
        return definition.default
    }

    /** Validate a raw value; returns null when the value is unsupported or malformed. */
    fun coerce(definition: NativeSettingsSchema.Definition, value: Any?): Any? {
        if (value == null) return null
        return when (definition.type) {
            NativeSettingsSchema.Type.BOOL -> when (value) {
                is Boolean -> value
                is String -> value.lowercase().let { if (it == "true") true else if (it == "false") false else null }
                else -> null
            }
            NativeSettingsSchema.Type.INT -> {
                val number = when (value) {
                    is Int -> value
                    is Number -> value.toInt()
                    is String -> value.toIntOrNull()
                    else -> null
                }
                number?.takeIf { definition.min != null && definition.max != null && it in definition.min..definition.max }
            }
            NativeSettingsSchema.Type.ENUM -> value.toString().takeIf { it in definition.values }
            NativeSettingsSchema.Type.STRING -> value.toString()
        }
    }

    /** Effective settings for the shell UI, mirroring [NativeSettingsSchema]. */
    fun all(context: Context): JSONObject {
        val preferences = prefs(context)
        val global = JSONObject()
        for (definition in NativeSettingsSchema.global) global.put(definition.id, effective(preferences, definition, null))
        val systems = JSONObject()
        for (system in NativeSettingsSchema.systems) {
            val values = JSONObject()
            for (definition in NativeSettingsSchema.definitionsFor(system)) {
                values.put(definition.id, effective(preferences, definition, system))
            }
            systems.put(system, values)
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
     * Apply several edits in one transaction. Unknown keys, unsupported enum
     * values, and out-of-range integers are rejected instead of stored.
     */
    fun save(context: Context, edits: JSONObject): JSONObject {
        val editor = prefs(context).edit()
        val saved = mutableListOf<String>()
        val rejected = mutableListOf<String>()
        for (key in edits.keys()) {
            val entry = byKey[key]
            if (entry == null) { rejected += key; continue }
            val definition = entry.first
            val coerced = coerce(definition, edits.get(key))
            if (coerced == null) { rejected += key; continue }
            when (coerced) {
                is Boolean -> editor.putBoolean(key, coerced)
                is Int -> editor.putInt(key, coerced)
                else -> editor.putString(key, coerced.toString())
            }
            saved += key
        }
        editor.apply()
        return JSONObject().put("ok", rejected.isEmpty()).put("saved", saved).put("rejected", rejected)
    }

    /**
     * Reset one system's graphics preferences to their defaults. Legacy keys,
     * other systems, saves and ROMs are untouched.
     */
    fun resetGraphics(context: Context, system: String): JSONObject {
        val editor = prefs(context).edit()
        val saved = mutableListOf<String>()
        for (definition in NativeSettingsSchema.graphics[system].orEmpty()) {
            val key = NativeSettingsSchema.key(definition.id, system)
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
        editor.apply()
        return JSONObject().put("ok", true).put("saved", saved)
    }

    /** Requested renderer for a system (legacy `renderer` fallback included). */
    fun renderer(preferences: SharedPreferences, system: String): String {
        val definition = NativeSettingsSchema.graphics[system]?.firstOrNull { it.id == "renderer" } ?: return "auto"
        return (effective(preferences, definition, system) as? String) ?: "auto"
    }

    /** Effective screen layout for a system; empty when the system has no layouts. */
    fun layout(preferences: SharedPreferences, system: String): String? {
        val definition = NativeSettingsSchema.graphics[system]?.firstOrNull { it.id == "screen-layout" } ?: return null
        return effective(preferences, definition, system) as? String
    }

    fun isSystemAvailableOnAndroid(system: String): Boolean = NativeSettingsSchema.isAvailable("android", system)
}
