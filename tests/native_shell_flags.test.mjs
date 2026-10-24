// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Behaviour of the shell feature-flag store that decides whether the Devices
// destination and its three optional surfaces exist. These are the switches the
// app shows in Settings, so a wrong default or a lost choice is a user-visible
// bug rather than an internal detail.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import vm from "node:vm";

const root = resolve(import.meta.dirname, "..");
const source = readFileSync(resolve(root, "native-offline/web/native-flags.js"), "utf8");
const schema = JSON.parse(readFileSync(resolve(root, "native-offline/shared/native-settings-schema.json"), "utf8"));

// A minimal WebView-shaped sandbox: localStorage plus the globals the module is
// allowed to consult, and nothing else.
const storage = (seed = {}) => {
  const values = {...seed};
  return {
    values,
    getItem: key => (Object.prototype.hasOwnProperty.call(values, key) ? values[key] : null),
    setItem: (key, value) => { values[key] = String(value); },
    removeItem: key => { delete values[key]; },
  };
};

const load = ({localStorage = storage(), model, legacy, failWrites = false} = {}) => {
  const writes = [];
  if (failWrites) localStorage.setItem = () => { throw new Error("quota"); };
  const sandbox = {localStorage, console};
  if (model) sandbox.NativeSettingsModel = model;
  if (legacy) sandbox.AN3AndroidSettings = legacy;
  vm.runInNewContext(source, sandbox);
  return {flags: sandbox.AN3ShellFlags, storage: localStorage, writes};
};

const declaredModel = () => ({
  global: schema.global.filter(entry => entry.category === "experimental"),
});

test("the schema declares all three switches off by default with an explanation", () => {
  const ids = ["experimental-switch-eden", "experimental-lan-sync", "experimental-phone-controller"];
  for (const id of ids) {
    const definition = schema.global.find(entry => entry.id === id);
    assert.ok(definition, `${id} must stay declared in the shared model`);
    assert.equal(definition.type, "bool");
    assert.equal(definition.default, "false", `${id} must default to off`);
    assert.equal(definition.category, "experimental");
    assert.ok(definition.note && definition.note.length > 20, `${id} must explain itself in the UI`);
  }
});

test("a fresh profile has every optional surface off", () => {
  const {flags} = load({model: declaredModel()});
  const all = flags.all();
  assert.deepEqual(Object.keys(all).sort(), [
    "experimental-lan-sync",
    "experimental-phone-controller",
    "experimental-switch-eden",
  ]);
  assert.equal(flags.anyOn(), false);
  for (const id of flags.ids()) assert.equal(flags.get(id), false);
});

test("a choice is written to storage and survives a restart", () => {
  const shared = storage();
  const first = load({localStorage: shared, model: declaredModel()});
  assert.equal(first.flags.set("experimental-lan-sync", true), true);
  assert.equal(first.flags.get("experimental-lan-sync"), true);
  assert.ok(shared.values[first.flags.storageKey], "the store must persist under its versioned key");
  assert.match(shared.values[first.flags.storageKey], /"experimental-lan-sync":true/);

  // A new page view over the same storage is what an app restart looks like.
  const second = load({localStorage: shared, model: declaredModel()});
  assert.equal(second.flags.get("experimental-lan-sync"), true);
  assert.equal(second.flags.get("experimental-phone-controller"), false);
  assert.equal(second.flags.anyOn(), true);
});

test("turning a surface off is remembered, not re-read from the old profile", () => {
  const shared = storage();
  const first = load({localStorage: shared, model: declaredModel()});
  first.flags.set("experimental-phone-controller", true);
  first.flags.set("experimental-phone-controller", false);
  const second = load({localStorage: shared, model: declaredModel()});
  assert.equal(second.flags.get("experimental-phone-controller"), false);
});

test("subscribers see the change once and a no-op write stays silent", () => {
  const {flags} = load({model: declaredModel()});
  const seen = [];
  const unsubscribe = flags.subscribe((snapshot, changed) => seen.push({snapshot: {...snapshot}, changed}));
  flags.set("experimental-switch-eden", true);
  flags.set("experimental-switch-eden", true);
  assert.equal(seen.length, 1, "an unchanged value must not notify");
  assert.equal(seen[0].changed.id, "experimental-switch-eden");
  assert.equal(seen[0].snapshot["experimental-switch-eden"], true);
  unsubscribe();
  flags.set("experimental-switch-eden", false);
  assert.equal(seen.length, 1, "unsubscribe must detach the listener");
});

test("an unknown id is rejected instead of silently stored", () => {
  const {flags, storage: store} = load({model: declaredModel()});
  assert.throws(() => flags.set("experimental-everything", true), /Unknown feature flag/);
  assert.equal(store.values[flags.storageKey], undefined);
});

test("a refused write reports failure and never claims the surface is on", () => {
  const {flags} = load({model: declaredModel(), failWrites: true});
  assert.equal(flags.set("experimental-lan-sync", true), false);
  assert.equal(flags.get("experimental-lan-sync"), false);
});

test("a stored value from the old settings panel is adopted once and owned afterwards", () => {
  // Android 3.6.10 kept these three in its settings store; a user who switched
  // LAN Sync on there must not lose the choice when the store moves here.
  const legacy = {all: () => JSON.stringify({global: {"experimental-lan-sync": "true"}})};
  const shared = storage();
  const first = load({localStorage: shared, model: declaredModel(), legacy});
  assert.equal(first.flags.get("experimental-lan-sync"), true);
  assert.match(shared.values[first.flags.storageKey], /"experimental-lan-sync":true/);

  const second = load({localStorage: shared, model: declaredModel()});
  assert.equal(second.flags.get("experimental-lan-sync"), true, "the adopted value must outlive the old store");
});

test("the declared default is the single source of the off state", () => {
  const model = {
    global: [
      {...schema.global.find(entry => entry.id === "experimental-lan-sync"), default: "true"},
      ...declaredModel().global.filter(entry => entry.id !== "experimental-lan-sync"),
    ],
  };
  const {flags} = load({model});
  assert.equal(flags.get("experimental-lan-sync"), true, "the store must read the declared default");
});

test("labels and notes come from the shared model, not from the store", () => {
  const {flags} = load({model: declaredModel()});
  const definitions = flags.definitions();
  assert.equal(definitions.length, 3);
  for (const definition of definitions) {
    const declared = schema.global.find(entry => entry.id === definition.id);
    assert.equal(definition.label, declared.label);
    assert.equal(definition.note, declared.note);
  }
});

test("the shell loads the store before the code that consumes it", () => {
  const index = readFileSync(resolve(root, "native-offline/web/index.html"), "utf8");
  const flags = index.indexOf("/native-flags.js");
  const shell = index.indexOf("/native-app.js");
  assert.ok(flags > 0, "index.html must load native-flags.js");
  assert.ok(flags < shell, "the store must be parsed before the shell reads it");
});
