// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Drift guard for the packaged app's Phone Controller pad.
//
// The app pad must reuse the same shared web pad structure (.ctrl-* classes
// from static/site.css) and the same canonical input action model
// (shared/input-actions-schema.json -> static/input-actions.js) as the web
// Phone Controller page. These tests fail if the app pad diverges from the
// web pad or renames the wire identifiers.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const read = path => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

const appHtml = read("native-offline/web/index.html");
const appJs = read("native-offline/web/native-app.js");
const siteCss = read("static/site.css");
const schema = JSON.parse(read("native-offline/shared/input-actions-schema.json"));

const loadInputActions = () => {
  const sandbox = { module: { exports: {} } };
  vm.runInNewContext(read("static/input-actions.js"), sandbox);
  return sandbox.module.exports;
};

const attrValues = (html, attribute) => {
  const pattern = new RegExp(`${attribute}="([^"]+)"`, "g");
  const values = [];
  let match;
  while ((match = pattern.exec(html)) !== null) values.push(match[1]);
  return values;
};

test("the app pad reuses the shared web pad structure classes", () => {
  for (const className of [
    "ctrl-pad", "ctrl-padbar", "ctrl-state", "ctrl-touchscreen", "ctrl-shoulders",
    "ctrl-main", "ctrl-dpad", "ctrl-circular", "ctrl-sticks", "ctrl-stick",
    "ctrl-face", "ctrl-system", "ctrl-utility", "ctrl-key", "ctrl-layout-picker",
  ]) {
    assert.ok(appHtml.includes(className), `app pad is missing the shared class ${className}`);
  }
});

test("the obsolete native-only pad markup is gone", () => {
  assert.ok(!appHtml.includes("native-controller-pad"), "legacy native pad markup must be removed");
  assert.ok(!appHtml.includes("data-native-controller-button=\"up\">Up"), "legacy labelled D-pad must be removed");
  assert.ok(!read("native-offline/web/native.css").includes(".native-controller-pad"), "legacy native pad CSS must be removed");
});

test("every canonical gameplay button wire is present exactly once", () => {
  const wires = Object.values(schema.buttons).map(button => button.wire).sort();
  const present = attrValues(appHtml, "data-native-controller-button").sort();
  assert.deepEqual(present, wires);
});

test("the utility row exposes the canonical utility wires", () => {
  const wires = Object.values(schema.utility).map(entry => entry.wire).sort();
  const present = attrValues(appHtml, "data-native-controller-util").sort();
  assert.deepEqual(present, wires);
});

test("utility wires map to canonical actions through the shared model", () => {
  const model = loadInputActions();
  for (const entry of Object.values(schema.utility)) {
    assert.equal(model.utilityWireToAction[entry.wire], Object.keys(schema.utility).find(key => schema.utility[key].wire === entry.wire),
      `${entry.wire} must resolve through AN3InputActions.utilityWireToAction`);
  }
});

test("the layout and movement selectors offer the canonical options", () => {
  const layoutBlock = appHtml.match(/<select id="nativeControllerLayout">([\s\S]*?)<\/select>/);
  assert.ok(layoutBlock, "layout selector must exist");
  const layoutValues = [...layoutBlock[1].matchAll(/value="([^"]+)"/g)].map(match => match[1]);
  assert.deepEqual(layoutValues, ["auto", "gba", "nds", "3ds", "custom"]);

  const movementBlock = appHtml.match(/<select id="nativeControllerMovement">([\s\S]*?)<\/select>/);
  assert.ok(movementBlock, "movement selector must exist");
  const movementValues = [...movementBlock[1].matchAll(/value="([^"]+)"/g)].map(match => match[1]);
  assert.deepEqual(movementValues, schema.directionalControls.map(control => control.id));
});

test("the app shell loads the shared input action model before the pad wiring", () => {
  const actions = appHtml.indexOf("/static/input-actions.js");
  const app = appHtml.indexOf("/native-app.js");
  assert.ok(actions > 0, "input-actions.js must be loaded");
  assert.ok(app > actions, "input-actions.js must load before native-app.js");
  assert.ok(appJs.includes("AN3InputActions"), "the pad must consume the shared action model");
  assert.ok(appJs.includes("utilityWireToAction"), "the pad must resolve utility wires canonically");
});

test("the shared stylesheet still defines every class the app pad depends on", () => {
  for (const selector of [".ctrl-pad{", ".ctrl-key{", ".ctrl-dpad{", ".ctrl-face{", ".ctrl-stick{", ".ctrl-circular{"]) {
    assert.ok(siteCss.includes(selector), `static/site.css must define ${selector}`);
  }
});
