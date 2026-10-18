// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import android.content.Context
import org.json.JSONObject

/** Reads the one native layout schema bundled with every platform package. */
data class NativeScreenLayout(val id: String, val label: String)

object NativeLayoutModel {
    private var loaded: Map<String, List<NativeScreenLayout>>? = null

    private fun load(context: Context): Map<String, List<NativeScreenLayout>> {
        loaded?.let { return it }
        val result = linkedMapOf<String, List<NativeScreenLayout>>()
        val root = JSONObject(context.assets.open("native-layout-schema.json").bufferedReader().use { it.readText() })
        val systems = root.getJSONObject("systems")
        for (system in listOf("nds", "3ds")) {
            val layouts = systems.getJSONArray(system)
            result[system] = (0 until layouts.length()).map { index ->
                val item = layouts.getJSONObject(index)
                NativeScreenLayout(item.getString("id"), item.getString("label"))
            }
        }
        return result.also { loaded = it }
    }

    fun layouts(context: Context, system: String): List<NativeScreenLayout> = load(context)[system].orEmpty()

    fun normalize(context: Context, system: String, candidate: String?): String {
        val values = layouts(context, system)
        return values.firstOrNull { it.id == candidate }?.id ?: values.firstOrNull()?.id.orEmpty()
    }

    fun next(context: Context, system: String, current: String): String {
        val values = layouts(context, system)
        if (values.isEmpty()) return current
        val currentIndex = values.indexOfFirst { it.id == current }.takeIf { it >= 0 } ?: 0
        return values[(currentIndex + 1) % values.size].id
    }
}
