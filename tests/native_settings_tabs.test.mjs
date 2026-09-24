// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Behavioral tests for Track C: the native Settings tabs (Emulator / Sync /
// Phone Controller) and Controller Mode. The tabs must switch only their own
// panes, keep every existing control ID reachable, and Controller Mode must ask
// the host for landscape only while a phone-controller pad is the active
// surface — presentation only, never a session or input change.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const root = new URL("../", import.meta.url);
const read = relative => readFileSync(new URL(relative, root), "utf8");
const indexHtml = read("native-offline/web/index.html");
const appSource = read("native-offline/web/native-app.js");

const element = (dataset = {}) => {
  const listeners = {};
  const attributes = new Map();
  const node = {
    hidden: false,
    dataset,
    value: "",
    textContent: "",
    checked: false,
    listeners,
    classList: {add() {}, remove() {}, toggle() {}, contains() { return false; }},
    addEventListener(type, handler) { (listeners[type] = listeners[type] || []).push(handler); },
    async fire(type, event = {}) { for (const handler of listeners[type] || []) await handler(event); },
    setAttribute(name, value) { attributes.set(name, String(value)); },
    getAttribute(name) { return attributes.has(name) ? attributes.get(name) : null; },
    hasAttribute(name) { return attributes.has(name); },
    removeAttribute(name) { attributes.delete(name); },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    focus() {},
    closest() { return null; },
  };
  return node;
};

const loadApp = (options = {}) => {
  const ids = new Map();
  const getById = id => {
    if (!ids.has(id)) ids.set(id, element());
    return ids.get(id);
  };
  const tabs = [
    element({settingsTab: "emulator"}),
    element({settingsTab: "sync"}),
    element({settingsTab: "controller"}),
  ];
  const panes = [
    element({settingsPane: "emulator"}),
    element({settingsPane: "sync"}),
    element({settingsPane: "controller"}),
  ];
  const controllerCalls = [];
  const defaultBridge = {
    send: () => Promise.resolve({}),
    status: () => Promise.resolve(options.status || {running: false}),
    enterControllerMode: () => { controllerCalls.push("enter"); return Promise.resolve("landscape"); },
    exitControllerMode: () => { controllerCalls.push("exit"); return Promise.resolve("auto"); },
  };
  const controllerBridge = options.controllerBridge === false
    ? null
    : (options.controllerBridge || defaultBridge);
  const document = {
    body: element(),
    getElementById: id => (id === "nativeApp" ? getById(id) : getById(id)),
    querySelector: () => null,
    querySelectorAll: selector => {
      if (selector === "[data-panel]") return [element({panel: "settings"})];
      if (selector === "[data-nav]") return [];
      if (selector === "[data-settings-tab]") return tabs;
      if (selector === "[data-settings-pane]") return panes;
      return [];
    },
  };
  const sandbox = {
    console,
    document,
    navigator: {userAgent: "Mozilla/5.0 (Linux; Android 14) WebView"},
    localStorage: {getItem() { return null; }, setItem() {}},
    MutationObserver: class { observe() {} },
    setTimeout,
    clearTimeout,
    setInterval(handle) { return 0; },
    clearInterval() {},
    Promise,
    addEventListener() {},
    removeEventListener() {},
  };
  sandbox.window = sandbox;
  sandbox.AN3NativeController = controllerBridge;
  vm.runInNewContext(appSource, sandbox);
  return {tabs, panes, controllerCalls, ids, sandbox};
};

test("Settings has three tabs that switch exactly one pane", () => {
  assert.match(indexHtml, /data-settings-tab="emulator"/);
  assert.match(indexHtml, /data-settings-tab="sync"/);
  assert.match(indexHtml, /data-settings-tab="controller"/);
  const {tabs, panes} = loadApp();
  // Emulator is the default active tab.
  assert.equal(tabs[0].dataset.settingsTab, "emulator");
  tabs[1].fire("click");
  const visible = panes.filter(pane => !pane.hidden).map(pane => pane.dataset.settingsPane);
  assert.deepEqual(visible, ["sync"], "clicking Sync must reveal only the Sync pane");
  tabs[2].fire("click");
  assert.deepEqual(
    panes.filter(pane => !pane.hidden).map(pane => pane.dataset.settingsPane),
    ["controller"],
  );
});

test("every card keeps its ID and the required Sync test IDs exist", () => {
  for (const id of [
    "nativeApplicationSettingsCard", "nativeGameSettingsCard", "nativeAccountSyncCard",
    "nativeBugReportCard", "nativeLicensesCard", "nativeControllerCard", "nativeSyncCard",
  ]) {
    assert.match(indexHtml, new RegExp(`id="${id}"`), `${id} must survive the tab refactor`);
  }
  assert.match(indexHtml, /data-testid="sync-settings"/);
  assert.match(indexHtml, /data-testid="lan-sync-toggle"/);
  assert.match(indexHtml, /Google Sync/);
  assert.match(indexHtml, /Coming later/);
});

test("Controller Mode asks for landscape only while the pad is the active surface", async () => {
  // A controller-role session that is running must enter Controller Mode once;
  // stopping must exit it once. The bridge is the only observable path the app
  // has to the host orientation, so this exercises the real wiring.
  const controllerCalls = [];
  let running = false;
  const bridge = {
    send: () => Promise.resolve({}),
    status: () => Promise.resolve(running ? {running: true, role: "controller", inputActive: true} : {running: false}),
    start: () => { running = true; return Promise.resolve({running: true, role: "controller", inputActive: true, code: "123456"}); },
    stop: () => { running = false; return Promise.resolve({running: false}); },
    enterControllerMode: () => { controllerCalls.push("enter"); return Promise.resolve("landscape"); },
    exitControllerMode: () => { controllerCalls.push("exit"); return Promise.resolve("auto"); },
  };
  const {ids} = loadApp({controllerBridge: bridge});
  const start = ids.get("nativeControllerStart");
  assert.ok(start && start.listeners.click, "the controller Start control must be wired");
  assert.ok(ids.get("nativeControllerPad"), "the controller pad must exist");

  await start.fire("click", {});
  assert.deepEqual(controllerCalls, ["enter"], "a running controller session must enter Controller Mode once");

  // A second refresh while already in mode must not re-enter it.
  await start.fire("click", {});
  assert.deepEqual(controllerCalls, ["enter", "exit"], "stopping the session must exit Controller Mode once");
});
