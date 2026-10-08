// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Generates the Android settings schema (Kotlin) and the shared offline-shell
// settings model (JavaScript) from one canonical JSON schema, plus the verified
// core-option registry (shared/core-option-registry.json). Run through
// `npm run prepare-web`; the outputs are committed.
import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const schema = JSON.parse(await readFile(resolve(root, "shared/native-settings-schema.json"), "utf8"));
const layouts = JSON.parse(await readFile(resolve(root, "shared/native-layout-schema.json"), "utf8"));
const registry = JSON.parse(await readFile(resolve(root, "shared", schema.coreOptionRegistry), "utf8"));

const fail = message => { throw new Error(`native-settings-schema: ${message}`); };
const systems = schema.systems;
if (!Array.isArray(systems) || systems.length === 0) fail("systems must be a non-empty array");

const definitionIds = new Set();
const knownTypes = new Set(["enum", "int", "bool", "string"]);
const validateDefinition = (definition, system) => {
  if (!definition.id || !/^[a-z0-9_-]+$/.test(definition.id)) fail(`invalid id ${definition.id}`);
  const scoped = system ? `${system}:${definition.id}` : definition.id;
  if (definitionIds.has(scoped)) fail(`duplicate definition ${scoped}`);
  definitionIds.add(scoped);
  if (!knownTypes.has(definition.type)) fail(`invalid type on ${scoped}`);
  if (definition.type === "enum" && !definition.valuesFrom && (!Array.isArray(definition.values) || definition.values.length === 0)) fail(`enum ${scoped} needs values`);
  if (definition.type === "int" && (!Number.isInteger(definition.min) || !Number.isInteger(definition.max) || definition.min >= definition.max)) fail(`int ${scoped} needs a min < max`);
  if (definition.default !== null && definition.default !== undefined && definition.type === "enum" && !definition.valuesFrom && !definition.values.includes(definition.default)) fail(`default of ${scoped} is not an offered value`);
};

for (const definition of schema.global) validateDefinition(definition, null);

const expand = (definition, system, applyLegacy = true) => {
  const values = definition.valuesFrom
    ? (layouts.systems[system] || []).map(item => item.id)
    : (definition.values || []);
  const labels = {};
  if (definition.valuesFrom) {
    for (const item of layouts.systems[system] || []) labels[item.id] = item.label;
  } else if (definition.labels) {
    Object.assign(labels, definition.labels);
  }
  const key = system ? `${definition.id}-${system}` : definition.id;
  const legacyKeys = applyLegacy ? (definition.legacyKeys || []).map(item => item.replace("{key}", key)) : [];
  return {
    id: definition.id,
    label: definition.label,
    category: definition.category || "emulation",
    type: definition.type,
    storage: definition.storage || (definition.type === "int" ? "int" : definition.type === "bool" ? "bool" : "string"),
    values,
    labels,
    min: Number.isInteger(definition.min) ? definition.min : null,
    max: Number.isInteger(definition.max) ? definition.max : null,
    default: definition.default === undefined ? null : definition.default,
    legacyKeys,
    legacyResolve: definition.legacyResolve || null,
    restart: definition.restart || "none",
    note: definition.note || null,
    external: definition.external !== false,
    pinned: false,
    editable: true,
    storageKey: null,
  };
};

const rendererDefinition = system => expand(
  schema.renderer,
  system,
  !schema.renderer.legacySystems || schema.renderer.legacySystems.includes(system),
);

const globalDefinitions = schema.global.map(definition => expand(definition, null));
const graphics = {};
for (const system of systems) {
  graphics[system] = (schema.systemGraphics[system] || []).map(id => {
    if (id === "renderer") return rendererDefinition(system);
    if (id === "screen-layout") {
      if (!(schema.systemLayoutSystems || schema.screenLayout.systems).includes(system)) fail(`screen-layout is not valid for ${system}`);
      return expand(schema.screenLayout, system);
    }
    fail(`unknown graphics definition ${id} for ${system}`);
  });
}

const emulation = {};
for (const system of systems) {
  const declared = schema.systemEmulation[system] || [];
  if (declared.length === 0) { emulation[system] = []; continue; }
  if (!(declared.length === 1 && declared[0] === "from-core-option-registry")) fail(`unknown systemEmulation policy for ${system}`);
  const entry = registry.systems[system];
  if (!entry) fail(`core-option registry has no ${system} entry`);
  const pinned = new Set(schema.pinnedCoreOptions?.[system]?.android || []);
  emulation[system] = entry.options
    .filter(option => Array.isArray(option.values) && option.values.length > 0)
    .map(option => {
      const values = option.values.map(item => item.value);
      const labels = Object.fromEntries(option.values.map(item => [item.value, item.label || item.value]));
      const isPinned = pinned.has(option.key);
      return {
        id: option.key,
        label: option.label || option.key,
        category: option.category || "emulation",
        type: "enum",
        storage: "string",
        values,
        labels,
        min: null,
        max: null,
        default: option.default && values.includes(option.default) ? option.default : values[0],
        legacyKeys: [],
        legacyResolve: null,
        restart: /restart/i.test(option.label || "") ? "core" : "none",
        note: option.description || null,
        external: true,
        pinned: isPinned,
        editable: !isPinned,
        storageKey: `core-${system}-${option.key}`,
      };
    });
}

const availability = {};
for (const [system, platforms] of Object.entries(schema.platformAvailability || {})) {
  availability[system] = {};
  for (const [platform, entry] of Object.entries(platforms)) {
    if (entry.available !== false) continue;
    availability[system][platform] = entry.reason || "Unavailable on this platform.";
  }
}

const pinned = {};
for (const system of systems) pinned[system] = (schema.pinnedCoreOptions?.[system]?.android) || [];

const model = {
  version: schema.version,
  store: schema.store,
  systems,
  systemLabels: schema.systemLabels,
  renderer: expand(schema.renderer, null),
  global: globalDefinitions,
  graphics,
  emulation,
  availability,
  pinnedCoreOptions: pinned,
};

const kotlinString = value => JSON.stringify(value);
const kotlinStrings = values => values.length === 0 ? `emptyList()` : `listOf(${values.map(kotlinString).join(", ")})`;
const kotlinLabels = (map, indent) => {
  const entries = Object.entries(map);
  if (entries.length === 0) return `emptyMap()`;
  const pad = " ".repeat(indent);
  return `mapOf(\n${entries.map(([key, value]) => `${pad}${kotlinString(key)} to ${kotlinString(value)},`).join("\n")}\n${" ".repeat(indent - 4)})`;
};
const kotlinDefinition = (definition, indent) => {
  const pad = " ".repeat(indent);
  const values = definition.values.length === 0 ? "emptyList()" : `listOf(${definition.values.map(kotlinString).join(", ")})`;
  const labels = Object.keys(definition.labels).length === 0 ? "emptyMap()" : `mapOf(${Object.entries(definition.labels).map(([k, v]) => `${kotlinString(k)} to ${kotlinString(v)}`).join(", ")})`;
  const storageKey = definition.storageKey === null ? "null" : kotlinString(definition.storageKey);
  return `${pad}Definition(${kotlinString(definition.id)}, ${kotlinString(definition.label)}, ${kotlinString(definition.category)}, Type.${definition.type.toUpperCase()}, ${kotlinString(definition.storage)}, ${values}, ${labels}, ${definition.min ?? "null"}, ${definition.max ?? "null"}, ${definition.default === null ? "null" : kotlinString(definition.default)}, ${kotlinStrings(definition.legacyKeys)}, ${definition.legacyResolve === null ? "null" : kotlinString(definition.legacyResolve)}, ${kotlinString(definition.restart)}, ${definition.note === null ? "null" : kotlinString(definition.note)}, ${definition.external}, ${definition.pinned}, ${definition.editable}, ${storageKey})`;
};

const kotlin = `// Generated from native-offline/shared/native-settings-schema.json; edit the shared model.
package space.an3tocom.offline

/** Canonical definition of every native application and per-core setting. */
object NativeSettingsSchema {
    const val STORE = ${kotlinString(schema.store)}
    const val VERSION = ${schema.version}
    val systems = ${kotlinStrings(systems)}
    val systemLabels = ${kotlinLabels(schema.systemLabels, 8)}

    enum class Type { ENUM, INT, BOOL, STRING }

    data class Definition(
        val id: String,
        val label: String,
        val category: String,
        val type: Type,
        val storage: String,
        val values: List<String>,
        val labels: Map<String, String>,
        val min: Int?,
        val max: Int?,
        val default: String?,
        val legacyKeys: List<String>,
        val legacyResolve: String?,
        val restart: String,
        val note: String?,
        val external: Boolean,
        val pinned: Boolean,
        val editable: Boolean,
        val storageKey: String?,
    )

    val global: List<Definition> = listOf(
${globalDefinitions.map(definition => kotlinDefinition(definition, 8)).join(",\n")}
    )

    val graphics: Map<String, List<Definition>> = mapOf(
${systems.map(system => `        ${kotlinString(system)} to listOf(\n${graphics[system].map(definition => kotlinDefinition(definition, 12)).join(",\n")}\n        ),`).join("\n")}
    )

    val emulation: Map<String, List<Definition>> = mapOf(
${systems.map(system => `        ${kotlinString(system)} to listOf(\n${emulation[system].map(definition => kotlinDefinition(definition, 12)).join(",\n")}\n        ),`).join("\n")}
    )

    val pinnedCoreOptions: Map<String, List<String>> = mapOf(
${systems.map(system => `        ${kotlinString(system)} to ${kotlinStrings(pinned[system])},`).join("\n")}
    )

    // system -> platform -> reason. A missing entry means the system is available.
    val unavailable: Map<String, Map<String, String>> = mapOf(
${Object.entries(availability).map(([system, platforms]) => `        ${kotlinString(system)} to ${kotlinLabels(platforms, 12)},`).join("\n")}
    )

    fun key(id: String, system: String?): String = if (system == null) id else "$id-$system"

    fun storageKey(definition: Definition, system: String?): String = definition.storageKey ?: key(definition.id, system)

    fun definitionsFor(system: String): List<Definition> = graphics[system].orEmpty() + emulation[system].orEmpty()

    fun editableFor(system: String): List<Definition> = definitionsFor(system).filter { it.editable }

    fun definition(id: String, system: String?): Definition? =
        if (system == null) global.firstOrNull { it.id == id } else definitionsFor(system).firstOrNull { it.id == id }

    fun isAvailable(platform: String, system: String): Boolean = unavailable[system]?.containsKey(platform) != true

    fun unavailableReason(platform: String, system: String): String? = unavailable[system]?.get(platform)

    fun pinned(system: String): List<String> = pinnedCoreOptions[system].orEmpty()
}
`;

const js = `// Generated from native-offline/shared/native-settings-schema.json; edit the shared model.
(function (root, factory) {
  const model = factory();
  if (typeof module === "object" && module.exports) module.exports = model;
  else root.NativeSettingsModel = model;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const schema = ${JSON.stringify(model, null, 2)};

  const platform = (ua) => {
    const text = String(ua || (typeof navigator !== "undefined" ? navigator.userAgent : "") || "");
    if (/Android/i.test(text)) return "android";
    if (/iPhone|iPad|iPod/i.test(text)) return "ios";
    return "desktop";
  };

  const key = (id, system) => (system == null ? id : id + "-" + system);

  const storageKeyFor = (definition, system) => definition.storageKey || key(definition.id, system);

  const definitionsFor = (system) => [...(schema.graphics[system] || []), ...(schema.emulation[system] || [])];

  const editable = (definitions) => definitions.filter((definition) => definition.editable !== false);

  const pinned = (definitions) => definitions.filter((definition) => definition.editable === false);

  const externalGlobal = () => schema.global.filter((definition) => definition.external);

  const valuesOf = (definition) => definition.values || [];

  const labelOf = (definition, value) => (definition.labels && definition.labels[value]) || value;

  const validate = (definition, value) => {
    if (value == null) return { ok: false, reason: "Missing value" };
    if (definition.type === "bool") {
      const normal = String(value).toLowerCase();
      if (normal === "true" || normal === "false") return { ok: true, value: normal };
      return { ok: false, reason: "Expected true or false" };
    }
    if (definition.type === "int") {
      const number = Number(value);
      if (!Number.isInteger(number) || number < definition.min || number > definition.max) return { ok: false, reason: "Expected an integer between " + definition.min + " and " + definition.max };
      return { ok: true, value: String(number) };
    }
    if (definition.type === "enum") {
      const text = String(value);
      if (!valuesOf(definition).includes(text)) return { ok: false, reason: "Unsupported value" };
      return { ok: true, value: text };
    }
    return { ok: true, value: String(value) };
  };

  const coerce = (definition, value) => {
    const result = validate(definition, value);
    if (result.ok) return result.value;
    return definition.default != null ? definition.default : (valuesOf(definition)[0] != null ? valuesOf(definition)[0] : "");
  };

  // Stored per-system value, then the documented legacy fallback, then default.
  const effective = (definition, system, stored, legacy) => {
    const own = stored ? stored[storageKeyFor(definition, system)] : undefined;
    const ownCheck = validate(definition, own);
    if (ownCheck.ok) return ownCheck.value;
    for (const legacyKey of definition.legacyKeys || []) {
      const candidate = legacy ? legacy[legacyKey] : undefined;
      const legacyCheck = validate(definition, candidate);
      if (legacyCheck.ok) return legacyCheck.value;
    }
    return definition.default;
  };

  const buildEdit = (definition, system, value) => {
    if (definition.editable === false) return null;
    const result = validate(definition, value);
    if (!result.ok) return null;
    return { key: storageKeyFor(definition, system), value: result.value };
  };

  const resetGraphicsEdits = (system, defaultValue) => {
    const edits = {};
    for (const definition of schema.graphics[system] || []) {
      const value = defaultValue ? defaultValue(definition, system) : definition.default;
      edits[storageKeyFor(definition, system)] = coerce(definition, value);
    }
    return edits;
  };

  const isAvailable = (system, currentPlatform) => !(schema.availability[system] && schema.availability[system][currentPlatform || platform()]);

  const unavailableReason = (system, currentPlatform) => {
    const entry = schema.availability[system];
    return entry ? (entry[currentPlatform || platform()] || null) : null;
  };

  return {
    version: schema.version,
    store: schema.store,
    systems: schema.systems,
    systemLabels: schema.systemLabels,
    renderer: schema.renderer,
    global: schema.global,
    graphics: schema.graphics,
    emulation: schema.emulation,
    pinnedCoreOptions: schema.pinnedCoreOptions,
    platform,
    key,
    storageKeyFor,
    definitionsFor,
    editable,
    pinned,
    externalGlobal,
    valuesOf,
    labelOf,
    validate,
    coerce,
    effective,
    buildEdit,
    resetGraphicsEdits,
    isAvailable,
    unavailableReason,
  };
});
`;

await writeFile(resolve(root, "src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeSettingsSchema.kt"), kotlin);
await writeFile(resolve(root, "web/native-settings.js"), js);
console.log(`NATIVE_SETTINGS_SCHEMA=generated emulation gba=${emulation.gba.length} nds=${emulation.nds.length} 3ds=${emulation["3ds"].length} switch=${emulation.switch.length}`);
