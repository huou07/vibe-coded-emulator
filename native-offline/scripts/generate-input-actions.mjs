// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Generates the canonical input/action contract for the Android overlay
// (Kotlin) and the web Phone Controller (JavaScript) from one shared schema.
// The circular D-pad geometry is emitted into both languages so they cannot
// drift. Run through `npm run prepare-web`; the outputs are committed.
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
  if (!button.wire || !/^[a-z0-9_]+$/.test(button.wire)) fail(`invalid wire name for ${action}`);
}
const utility = Object.entries(schema.utility || {});
if (utility.length === 0) fail("utility actions must be declared");
for (const [action, entry] of utility) {
  if (!/^[A-Z0-9_]+$/.test(action) || !entry.wire) fail(`invalid utility action ${action}`);
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

/** Canonical input/action contract shared by the in-game overlay and Phone Controller. */
object NativeInputActions {
${buttons.map(([action, button]) => `    const val ${action} = ${button.libretro}`).join("\n")}

    val buttonIds: Map<String, Int> = ${kotlinMap(buttons.map(([action, button]) => [action, String(button.libretro)]))}
    val wireToId: Map<String, Int> = ${kotlinMap(buttons.map(([, button]) => [button.wire, String(button.libretro)]))}
    val buttonLabels: Map<String, String> = ${kotlinMap(buttons.map(([action, button]) => [action, kotlinString(button.label || action)]))}

    val utilityActions: List<String> = ${kotlinStrings(utility.map(([action]) => action))}
    val utilityWireToAction: Map<String, String> = ${kotlinMap(utility.map(([action, entry]) => [entry.wire, kotlinString(action)]))}
    val utilityLabels: Map<String, String> = ${kotlinMap(utility.map(([action, entry]) => [action, kotlinString(entry.label || action)]))}

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

const js = `// Generated from native-offline/shared/input-actions-schema.json; edit the shared model.
(function (root, factory) {
  const model = factory();
  if (typeof module === "object" && module.exports) module.exports = model;
  else root.AN3InputActions = model;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const model = ${JSON.stringify({
    version: schema.version,
    buttons: schema.buttons,
    utility: schema.utility,
    directionalControls: schema.directionalControls,
    speeds: schema.speeds,
    circular,
  }, null, 2)};
  const sectors = model.circular.sectors;
  const deadzone = model.circular.deadzone;
  const hysteresis = model.circular.hysteresisDegrees;
  const sectorIds = sectors.map((sector) => sector.id);
  const sectorCenters = sectors.map((sector) => sector.center);
  const sectorActions = sectors.map((sector) => sector.actions.slice());

  model.buttonActions = Object.keys(model.buttons);
  model.wireToId = {};
  model.idToWire = {};
  for (const [action, button] of Object.entries(model.buttons)) {
    model.wireToId[button.wire] = button.libretro;
    model.idToWire[button.libretro] = button.wire;
  }
  model.utilityActions = Object.keys(model.utility);
  model.utilityWireToAction = {};
  for (const [action, entry] of Object.entries(model.utility)) model.utilityWireToAction[entry.wire] = action;

  // Directional geometry for a pointer normalized so one radius is 1.0.
  model.circularDirections = function (dx, dy, previous) {
    if (!Number.isFinite(dx) || !Number.isFinite(dy)) return {actions: [], region: null};
    if (Math.hypot(dx, dy) < deadzone) return {actions: [], region: null};
    let angle = Math.atan2(-dy, dx) * 180 / Math.PI;
    if (angle < 0) angle += 360;
    if (previous) {
      const index = sectorIds.indexOf(previous);
      if (index >= 0) {
        let distance = Math.abs(angle - sectorCenters[index]);
        if (distance > 180) distance = 360 - distance;
        if (distance <= 22.5 + hysteresis) return {actions: sectorActions[index].slice(), region: sectorIds[index]};
      }
    }
    let best = 0;
    let bestDistance = Infinity;
    for (let index = 0; index < sectorIds.length; index += 1) {
      let distance = Math.abs(angle - sectorCenters[index]);
      if (distance > 180) distance = 360 - distance;
      if (distance < bestDistance) { bestDistance = distance; best = index; }
    }
    return {actions: sectorActions[best].slice(), region: sectorIds[best]};
  };

  return model;
});
`;

await writeFile(resolve(root, "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeInputActions.kt"), kotlin);
await writeFile(resolve(root, "..", "static", "input-actions.js"), js);
console.log(`INPUT_ACTIONS=generated buttons=${buttons.length} utility=${utility.length} sectors=${sectors.length}`);
