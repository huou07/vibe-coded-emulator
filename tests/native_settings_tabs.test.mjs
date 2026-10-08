// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Source checks for the simplified local Settings panel and section navigation.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const root = new URL("../", import.meta.url);
const read = relative => readFileSync(new URL(relative, root), "utf8");
const indexHtml = read("native-offline/web/index.html");
const appSource = read("native-offline/web/native-app.js");
const bootstrap = read("native-offline/web/native-bootstrap.js");

const element = (dataset = {}) => {
  const listeners = {};
  const classes = new Set();
  return {
    hidden: false,
    dataset,
    textContent: "",
    listeners,
    classList: {
      toggle(name, force) { if (force) classes.add(name); else classes.delete(name); },
      contains(name) { return classes.has(name); },
    },
    addEventListener(type, handler) { (listeners[type] = listeners[type] || []).push(handler); },
    fire(type, event = {}) { for (const handler of listeners[type] || []) handler(event); },
  };
};

const loadApp = () => {
  const panels = ["play", "library", "settings", "help", "about"].map(name => element({panel: name}));
  const navButtons = ["play", "library", "settings", "help", "about"].map(name => element({nav: name}));
  const title = element();
  const back = element();
  const searchWrap = element();
  const document = {
    readyState: "complete",
    body: element(),
    getElementById: id => id === "nativeApp" ? element() : null,
    querySelector: selector => selector === "[data-section-title]" ? title : selector === ".native-back" ? back : null,
    querySelectorAll: selector => selector === "[data-panel]" ? panels : selector === "[data-nav]" ? navButtons : [],
  };
  const sandbox = {
    console,
    document,
    navigator: {userAgent: "Mozilla/5.0 (Linux; Android 14) WebView"},
    MutationObserver: class { observe() {} },
    addEventListener() {},
  };
  sandbox.window = sandbox;
  vm.runInNewContext(appSource, sandbox);
  return {panels, navButtons, title, sandbox};
};

test("Settings keeps local application and per-core settings without Phone Controller UI", () => {
  assert.match(indexHtml, /data-panel="settings"/);
  for (const id of ["nativeApplicationSettingsCard", "nativeGameSettingsCard", "nativeBugReportCard"]) {
    assert.match(indexHtml, new RegExp(`id="${id}"`));
  }
  assert.doesNotMatch(indexHtml, /nativeControllerCard|settings-tab-controller|Phone Controller/i);
  assert.doesNotMatch(appSource + bootstrap, /AN3NativeController|native_controller|phoneController/i);
});

test("section navigation opens only the requested local settings panel", () => {
  const {panels, navButtons, title, sandbox} = loadApp();
  const settingsButton = navButtons.find(button => button.dataset.nav === "settings");
  settingsButton.fire("click");
  assert.equal(title.textContent, "Settings");
  assert.deepEqual(
    panels.filter(panel => !panel.hidden).map(panel => panel.dataset.panel),
    ["settings"],
  );
  assert.equal(sandbox.AN3NativeController, undefined);
});
