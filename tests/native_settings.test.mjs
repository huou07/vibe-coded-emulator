// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Behavioral tests for the canonical native settings model generated from
// shared/native-settings-schema.json. These exercise the same pure logic the
// offline shell UI uses, not source strings.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../native-offline/web/native-settings.js", import.meta.url), "utf8");

const load = (userAgent = "Android") => {
  const sandbox = { module: { exports: {} }, navigator: { userAgent } };
  vm.runInNewContext(source, sandbox);
  return sandbox.module.exports;
};

// A minimal in-memory adapter mirroring the Android SharedPreferences layout.
const memoryStore = seed => {
  const data = {...seed};
  return {
    get: key => data[key],
    all: () => ({...data}),
    apply: edits => { for (const [key, value] of Object.entries(edits)) data[key] = value; },
  };
};

test("the model exposes the four canonical systems and labels", () => {
  const model = load();
  assert.equal(model.systems.join(","), "gba,nds,3ds,switch");
  assert.equal(model.systemLabels["3ds"], "3DS");
  assert.equal(model.store, "an3-native-game");
});

test("every per-system definition is stored under a system-scoped key", () => {
  const model = load();
  for (const system of model.systems) {
    for (const definition of model.graphics[system]) {
      assert.equal(model.key(definition.id, system), `${definition.id}-${system}`);
    }
  }
  assert.equal(model.key("volume", null), "volume");
});

test("renderer edits are isolated per core", () => {
  const model = load();
  const store = memoryStore({});
  for (const system of model.systems) {
    const edit = model.buildEdit(model.graphics[system][0], system, "vulkan");
    store.apply({[edit.key]: edit.value});
  }
  store.apply({[model.buildEdit(model.graphics["3ds"][0], "3ds", "opengl").key]: "opengl"});
  assert.equal(store.get("renderer-3ds"), "opengl");
  assert.equal(store.get("renderer-gba"), "vulkan");
  assert.equal(store.get("renderer-nds"), "vulkan");
  assert.equal(store.get("renderer-switch"), "vulkan");
});

test("changing one system's layout does not change another", () => {
  const model = load();
  const store = memoryStore({"screen-layout-nds": "left-right", "screen-layout-3ds": "left-right"});
  const edit = model.buildEdit(model.graphics["3ds"].find(d => d.id === "screen-layout"), "3ds", "top-bottom");
  store.apply({[edit.key]: edit.value});
  assert.equal(store.get("screen-layout-3ds"), "top-bottom");
  assert.equal(store.get("screen-layout-nds"), "left-right");
});

test("effective value resolution prefers stored, then legacy, then default", () => {
  const model = load();
  const renderer = model.renderer;
  assert.equal(model.effective(renderer, "3ds", {}, {}), "auto");
  assert.equal(model.effective(renderer, "3ds", {}, {renderer: "vulkan"}), "vulkan");
  assert.equal(model.effective(renderer, "3ds", {"renderer-3ds": "opengl"}, {renderer: "vulkan"}), "opengl");
  // An unsupported legacy value must not leak through.
  assert.equal(model.effective(renderer, "3ds", {}, {renderer: "webgpu"}), "auto");
});

test("legacy fallback is idempotent and never rewritten", () => {
  const model = load();
  const legacy = {renderer: "vulkan"};
  for (let index = 0; index < 5; index += 1) {
    assert.equal(model.effective(model.renderer, "gba", {}, legacy), "vulkan");
  }
  assert.deepEqual(legacy, {renderer: "vulkan"});
});

test("validation rejects unsupported enums and out-of-range integers", () => {
  const model = load();
  assert.equal(model.validate(model.renderer, "webgpu").ok, false);
  assert.equal(model.validate(model.renderer, "vulkan").ok, true);
  const volume = model.global.find(definition => definition.id === "volume");
  assert.equal(model.validate(volume, 50).ok, true);
  assert.equal(model.validate(volume, 150).ok, false);
  assert.equal(model.validate(volume, "not-a-number").ok, false);
  assert.equal(model.buildEdit(model.renderer, "3ds", "webgpu"), null);
});

test("coerce falls back to a supported default instead of storing junk", () => {
  const model = load();
  assert.equal(model.coerce(model.renderer, "webgpu"), "auto");
  const volume = model.global.find(definition => definition.id === "volume");
  assert.equal(model.coerce(volume, "999"), "100");
});

test("reset graphics only targets the selected system", () => {
  const model = load();
  const edits = model.resetGraphicsEdits("3ds");
  assert.ok(Object.keys(edits).length > 0);
  for (const key of Object.keys(edits)) assert.match(key, /-3ds$/);
  assert.equal(edits["renderer-3ds"], "auto");
  assert.ok(!Object.keys(edits).some(key => /-(gba|nds|switch)$/.test(key)));
});

test("Switch is available on Android and remains a stored setting", () => {
  const model = load("Android 15");
  assert.equal(model.isAvailable("switch", "android"), true);
  assert.equal(model.unavailableReason("switch", "android"), null);
  assert.equal(model.isAvailable("3ds", "android"), true);
  const edit = model.buildEdit(model.graphics["switch"][0], "switch", "vulkan");
  assert.equal(edit.key, "renderer-switch");
});

test("pinned core options are declared per system", () => {
  const model = load();
  assert.ok(model.pinnedCoreOptions["3ds"].includes("citra_graphics_api"));
  assert.ok(model.pinnedCoreOptions["3ds"].includes("citra_use_hw_shader"));
  assert.ok(model.pinnedCoreOptions["3ds"].includes("citra_use_disk_shader_cache"));
  assert.ok(model.pinnedCoreOptions["3ds"].includes("citra_layout_option"));
  assert.equal(model.pinnedCoreOptions["3ds"].length, 4);
  assert.ok(model.pinnedCoreOptions["nds"].includes("melonds_render_mode"));
  assert.ok(model.pinnedCoreOptions["nds"].includes("melonds_threaded_renderer"));
  assert.ok(model.pinnedCoreOptions["nds"].includes("melonds_show_cursor"));
  assert.equal(model.pinnedCoreOptions["nds"].length, 6);
  assert.equal(model.pinnedCoreOptions["gba"].length, 0);
  assert.equal(model.pinnedCoreOptions["switch"].length, 0);
});

test("the Emulation registry exposes real per-core options", () => {
  const model = load();
  const counts = {gba: model.emulation.gba.length, nds: model.emulation.nds.length, "3ds": model.emulation["3ds"].length, switch: model.emulation.switch.length};
  assert.equal(counts.gba, 17);
  assert.equal(counts.nds, 73);
  assert.equal(counts["3ds"], 32);
  assert.equal(counts.switch, 0);
  for (const system of ["gba", "nds", "3ds"]) {
    for (const definition of model.emulation[system]) {
      assert.ok(definition.values.length > 0, definition.id);
      assert.ok(definition.values.includes(definition.default), `${definition.id} default`);
      assert.equal(definition.storageKey, `core-${system}-${definition.id}`);
    }
  }
});

test("runtime-pinned emulation options are present but not editable", () => {
  const model = load();
  const renderMode = model.emulation.nds.find(definition => definition.id === "melonds_render_mode");
  assert.ok(renderMode);
  assert.equal(renderMode.pinned, true);
  assert.equal(renderMode.editable, false);
  assert.equal(model.buildEdit(renderMode, "nds", "opengl"), null);
  const jit = model.emulation.nds.find(definition => definition.id === "melonds_jit_enable");
  assert.equal(jit.editable, true);
  assert.equal(model.buildEdit(jit, "nds", "disabled").key, "core-nds-melonds_jit_enable");
});

test("emulation edits are isolated per core and never use another key shape", () => {
  const model = load();
  const store = memoryStore({});
  const gba = model.emulation.gba.find(definition => definition.id === "mgba_allow_opposing_directions");
  const nds = model.emulation.nds.find(definition => definition.id === "melonds_jit_enable");
  store.apply({[model.buildEdit(gba, "gba", "yes").key]: "yes"});
  store.apply({[model.buildEdit(nds, "nds", "disabled").key]: "disabled"});
  assert.equal(store.get("core-gba-mgba_allow_opposing_directions"), "yes");
  assert.equal(store.get("core-nds-melonds_jit_enable"), "disabled");
  assert.equal(store.get("core-3ds-melonds_jit_enable"), undefined);
});

test("a legacy renderer no longer leaks into Switch", () => {
  const model = load();
  const renderer = system => model.graphics[system].find(definition => definition.id === "renderer");
  assert.equal(model.effective(renderer("gba"), "gba", {}, {renderer: "vulkan"}), "vulkan");
  assert.equal(model.effective(renderer("nds"), "nds", {}, {renderer: "vulkan"}), "vulkan");
  assert.equal(model.effective(renderer("3ds"), "3ds", {}, {renderer: "vulkan"}), "vulkan");
  assert.equal(model.effective(renderer("switch"), "switch", {}, {renderer: "vulkan"}), "auto");
});

test("an explicit per-system Auto overrides the legacy renderer", () => {
  const model = load();
  assert.equal(model.effective(model.renderer, "3ds", {"renderer-3ds": "auto"}, {renderer: "vulkan"}), "auto");
});
