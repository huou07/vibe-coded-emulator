// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import android.content.SharedPreferences

/**
 * One auto-save mode shared by the Android game activity and its menu.
 * Tokens come from the generated shared player UI model, so the activity, the
 * menu and the native host can never drift apart.
 */
object NativeAutoSave {
    const val KEY = "autosave-mode"

    /** Resolve the stored mode, falling back to the legacy enabled+interval keys. */
    fun resolve(prefs: SharedPreferences): String = resolveValues(prefs.all)

    /** Resolve from a raw value map (used by the file-based cross-process read). */
    fun resolveValues(values: Map<String, Any?>): String {
        val stored = values[KEY] as? String
        if (stored != null && stored in NativePlayerUi.autoSaveTokens) return stored
        // The previous Android default was "enabled every 60 seconds"; keep an
        // existing install saving by landing on the slowest offered interval.
        // A missing legacy key keeps the historical enabled default.
        val legacy = values["autosave"]
        val enabled = when (legacy) {
            null -> true
            is Boolean -> legacy
            else -> legacy.toString() == "true"
        }
        return if (enabled) "30" else "off"
    }
}
