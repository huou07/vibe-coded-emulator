// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";

const read = path => readFileSync(new URL(path, import.meta.url), "utf8");
const modelSource = read("../native-offline/web/native-settings.js");
const uiSource = read("../native-offline/web/game-settings.js");

class Element {
  constructor(tag = "div") {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.listeners = {};
    this.attributes = {};
    this.classList = {add() {}};
    this.value = "";
    this.checked = false;
    this._text = "";
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text; }
  appendChild(child) { this.children.push(child); return child; }
  addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
  setAttribute(name, value) { this.attributes[name] = value; }
  async fire(type) { return Promise.all((this.listeners[type] || []).map(handler => handler({target: this}))); }
}

const descendants = element => [element, ...element.children.flatMap(descendants)];

test("desktop Settings adapter reads, saves, and reloads per-core values asynchronously", async () => {
  const modelContext = {module: {exports: {}}, navigator: {userAgent: "macOS"}};
  vm.runInNewContext(modelSource, modelContext);
  const model = modelContext.module.exports;
  const ids = ["nativeApplicationSettingsBody", "nativeGameSettingsSystems", "nativeGameSettingsCard", "nativeGameSettingsBody", "nativeGameSettingsStatus"];
  const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
  const document = {
    readyState: "complete",
    getElementById: id => elements[id] || null,
    createElement: tag => new Element(tag),
  };
  const settings = {global: {}, systems: Object.fromEntries(model.systems.map(system => [system, {}]))};
  settings.systems.gba.renderer = "auto";
  settings.systems.nds.renderer = "auto";
  const saved = [];
  const bridge = {
    async all() { return structuredClone(settings); },
    async save(encoded) {
      const edits = JSON.parse(encoded);
      Object.assign(settings.systems.gba, {renderer: edits["renderer-gba"]});
      saved.push(edits);
      return {ok: true, saved: Object.keys(edits), rejected: []};
    },
    async resetGraphics(system) {
      settings.systems[system].renderer = "auto";
      return {ok: true, saved: [`renderer-${system}`]};
    },
  };
  const sandbox = {
    document,
    navigator: {userAgent: "Windows NT 10.0"},
    NativeSettingsModel: model,
    AN3NativeSettings: bridge,
  };
  sandbox.window = sandbox;
  vm.runInNewContext(uiSource, sandbox);
  await new Promise(resolve => setImmediate(resolve));

  const gbaTab = elements.nativeGameSettingsSystems.children.find(button => button.dataset.gsSystem === "gba");
  assert.ok(gbaTab);
  const bodyNodes = descendants(elements.nativeGameSettingsBody);
  const renderer = bodyNodes.find(node => node.tagName === "select");
  assert.ok(renderer);
  assert.equal(renderer.dataset.testid, "native-setting-renderer");
  renderer.value = "opengl";
  await renderer.fire("change");
  const save = bodyNodes.find(node => node.tagName === "button" && node.textContent === "Save settings");
  assert.ok(save);
  await save.fire("click");
  assert.equal(saved[0]["renderer-gba"], "opengl");
  assert.equal(settings.systems.gba.renderer, "opengl");

  await gbaTab.fire("click");
  const refreshed = descendants(elements.nativeGameSettingsBody).find(node => node.tagName === "select");
  assert.equal(refreshed.value, "opengl");
});

test("macOS desktop Settings shows its fixed renderer as platform-managed", async () => {
  const modelContext = {module: {exports: {}}, navigator: {userAgent: "Mac OS X"}};
  vm.runInNewContext(modelSource, modelContext);
  const model = modelContext.module.exports;
  const ids = ["nativeApplicationSettingsBody", "nativeGameSettingsSystems", "nativeGameSettingsCard", "nativeGameSettingsBody", "nativeGameSettingsStatus"];
  const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
  const document = {
    readyState: "complete",
    getElementById: id => elements[id] || null,
    createElement: tag => new Element(tag),
  };
  const settings = {global: {}, systems: Object.fromEntries(model.systems.map(system => [system, {}]))};
  const bridge = {
    async all() { return structuredClone(settings); },
    async save() { throw new Error("the Mac renderer is platform-managed"); },
    async resetGraphics(system) { return {ok: true, saved: [system]}; },
  };
  const sandbox = {
    document,
    navigator: {userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
    NativeSettingsModel: model,
    AN3NativeSettings: bridge,
  };
  sandbox.window = sandbox;
  vm.runInNewContext(uiSource, sandbox);
  await new Promise(resolve => setImmediate(resolve));

  const bodyNodes = descendants(elements.nativeGameSettingsBody);
  assert.equal(bodyNodes.some(node => node.dataset.testid === "native-setting-renderer"), false);
  assert.ok(bodyNodes.some(node => node.dataset.testid === "native-setting-managed-renderer"
    && node.textContent.includes("Managed automatically on this platform: Renderer.")));
  assert.equal(bodyNodes.some(node => node.tagName === "button" && node.textContent === "Save settings"), false);
  assert.equal(bodyNodes.some(node => node.tagName === "button" && node.textContent === "Reset Graphics to Defaults"), false);
});
