// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Generates the canonical local input contract for the Android overlay.
import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const schema = JSON.parse(await readFile(resolve(root, "shared/input-actions-schema.json"), "utf8"));

const fail = message => { throw new Error(`input-actions-schema: ${message}`); };
const buttons = Object.entries(schema.buttons || {});
if (buttons.length === 0) fail("buttons must be declared");
const seenIds = new Set();
for (const [action, button] of buttons) {
  if (!/^[A-Z0-9_]+$/.test(action)) fail(`invalid action ${action}`);
  if (!Number.isInteger(button.libretro) || button.libretro < 0 || button.libretro > 15) fail(`invalid libretro id for ${action}`);
  if (seenIds.has(button.libretro)) fail(`duplicate libretro id ${button.libretro}`);
  seenIds.add(button.libretro);
  if (!button.label) fail(`missing label for ${action}`);
}
const circular = schema.circular || {};
const sectors = circular.sectors || [];
if (sectors.length !== 8) fail("circular D-pad needs eight sectors");
for (const sector of sectors) {
  if (!/^[A-Z]+$/.test(sector.id) || !Number.isFinite(sector.center) || !Array.isArray(sector.actions) || sector.actions.length === 0) fail(`invalid sector ${sector.id}`);
  for (const action of sector.actions) if (!schema.buttons[action]) fail(`sector ${sector.id} references unknown action ${action}`);
}
if (!(circular.deadzone > 0 && circular.deadzone < 1)) fail("circular deadzone must be within 0..1");
if (!(circular.hysteresisDegrees >= 0 && circular.hysteresisDegrees < 22.5)) fail("hysteresis must be below half a sector");

const kotlinString = value => JSON.stringify(value);
const kotlinStrings = values => `listOf(${values.map(kotlinString).join(", ")})`;
const kotlinMap = entries => entries.length === 0 ? "emptyMap()" : `mapOf(${entries.map(([k, v]) => `${kotlinString(k)} to ${v}`).join(", ")})`;

const sectorIds = sectors.map(sector => kotlinString(sector.id)).join(", ");
const sectorCenters = sectors.map(sector => `${sector.center}.0`).join(", ");
const sectorActions = sectors.map(sector => `setOf(${sector.actions.map(kotlinString).join(", ")})`).join(", ");

const kotlin = `// Generated from native-offline/shared/input-actions-schema.json; edit the shared model.
package space.an3tocom.offline

import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.hypot

/** Canonical local input contract for the native overlay and physical controllers. */
object NativeInputActions {
${buttons.map(([action, button]) => `    const val ${action} = ${button.libretro}`).join("\n")}

    val buttonIds: Map<String, Int> = ${kotlinMap(buttons.map(([action, button]) => [action, String(button.libretro)]))}
    val buttonLabels: Map<String, String> = ${kotlinMap(buttons.map(([action, button]) => [action, kotlinString(button.label || action)]))}

    val speeds: List<String> = ${kotlinStrings(schema.speeds || ["1"])}
    val directionalControls: List<String> = ${kotlinStrings((schema.directionalControls || []).map(control => control.id))}
    val directionalControlLabels: Map<String, String> = ${kotlinMap((schema.directionalControls || []).map(control => [control.id, kotlinString(control.label || control.id)]))}

    private val sectorIds = listOf(${sectorIds})
    private val sectorCenters = listOf(${sectorCenters})
    private val sectorActions = listOf(${sectorActions})
    private const val DEADZONE = ${circular.deadzone}
    private const val HYSTERESIS = ${circular.hysteresisDegrees}

    data class CircularResult(val actions: Set<String>, val region: String?)

    /**
     * Directional geometry for a pointer at (dx, dy) normalized so one control
     * radius is 1.0. Returns the cardinal/diagonal digital actions; a diagonal
     * is two simultaneous cardinals, never a synthetic button.
     */
    fun circularDirections(dx: Float, dy: Float, previous: String?): CircularResult {
        if (!dx.isFinite() || !dy.isFinite()) return CircularResult(emptySet(), null)
        val radius = hypot(dx.toDouble(), dy.toDouble())
        if (radius < DEADZONE) return CircularResult(emptySet(), null)
        var angle = Math.toDegrees(atan2((-dy).toDouble(), dx.toDouble()))
        if (angle < 0.0) angle += 360.0
        if (previous != null) {
            val index = sectorIds.indexOf(previous)
            if (index >= 0) {
                var distance = abs(angle - sectorCenters[index])
                if (distance > 180.0) distance = 360.0 - distance
                if (distance <= 22.5 + HYSTERESIS) return CircularResult(sectorActions[index], sectorIds[index])
            }
        }
        var best = 0
        var bestDistance = Double.MAX_VALUE
        for (index in sectorIds.indices) {
            var distance = abs(angle - sectorCenters[index])
            if (distance > 180.0) distance = 360.0 - distance
            if (distance < bestDistance) { bestDistance = distance; best = index }
        }
        return CircularResult(sectorActions[best], sectorIds[best])
    }

    /** Pressed cardinal actions for a pointer, preserving the previous region's hysteresis. */
    fun pressedCardinals(actions: Set<String>): Set<Int> =
        actions.mapNotNull { buttonIds[it] }.toSet()
}
`;

await writeFile(resolve(root, "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeInputActions.kt"), kotlin);
console.log(`INPUT_ACTIONS=generated buttons=${buttons.length} sectors=${sectors.length}`);
