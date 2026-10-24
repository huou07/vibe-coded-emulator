// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Eden/Switch, LAN Sync and Phone Controller are optional: a user who only
// wants GBA, NDS and 3DS must be able to keep them entirely out of the way.
// The three switches default to off, each surface is gated on its switch rather
// than merely disabled, and the Settings card that writes them is present on
// every platform — that card is the only way back in for a user who turned them
// off, so it must never depend on a platform settings adapter.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const read = path => readFileSync(resolve(root, path), "utf8");
const schema = JSON.parse(read("native-offline/shared/native-settings-schema.json"));
const shell = read("native-offline/web/native-app.js");
const index = read("native-offline/web/index.html");
const settings = read("native-offline/web/game-settings.js");
const flags = read("native-offline/web/native-flags.js");
const nativeSync = read("native-offline/web/native-sync.js");
const ids = ["experimental-switch-eden", "experimental-lan-sync", "experimental-phone-controller"];

test("the three optional features are declared, off by default and explained", () => {
  for (const id of ids) {
    const definition = schema.global.find(item => item.id === id);
    assert.ok(definition, `${id} must be declared in the shared settings model`);
    assert.equal(definition.type, "bool", `${id} is a switch`);
    assert.equal(definition.default, "false", `${id} must default to off`);
    assert.equal(definition.category, "experimental");
    assert.ok(definition.note && definition.note.length > 20, `${id} must explain itself`);
  }
});

test("the shell owns the decision so every platform can reach it", () => {
  assert.match(flags, /AN3ShellFlags/, "the store must publish a shell-level API");
  assert.match(flags, /an3-shell-flags-v1/, "the store persists under one versioned key");
  assert.match(shell, /window\.AN3ShellFlags/, "the shell must read the store");
  assert.doesNotMatch(shell, /window\.AN3AndroidSettings/, "the gate must not depend on an Android-only adapter");
  // The card is rendered from the store on every platform, including a desktop
  // build whose settings adapter is absent.
  assert.match(index, /id="nativeExperimentalCard"/, "Settings must carry the optional-features card");
  assert.match(index, /id="nativeExperimentalBody"/);
  assert.match(shell, /dataset\.experimentalToggle/, "each switch is a real control");
  // A native checkbox carries the state and the keyboard behaviour, and a drawn
  // track shows it: WebKitGTK paints `appearance:none` checkboxes with the GTK
  // theme, so styling the input itself rendered a ring in the installed app.
  assert.match(shell, /input\.type = "checkbox"/, "the control must stay a checkbox");
  assert.match(shell, /native-flag-input/);
  assert.match(shell, /native-flag-track/);
  assert.match(shell, /track\.setAttribute\("aria-hidden", "true"\)/, "the drawn track must not be announced");
  assert.match(shell, /field\.dataset\.testid = definition\.id/, "each switch must be addressable by the control plane");
  assert.match(shell, /field\.dataset\.state = input\.checked \? "on" : "off"/, "the row must expose its state to the control plane");
  // Android ships no Eden companion and a host without the controller bridge
  // cannot host a phone, so a switch is offered only where its adapter exists.
  assert.match(shell, /surfaceAdapters/, "each switch must declare the adapter it needs");
  assert.match(shell, /Boolean\(window\.AN3NativeSwitch\)/, "the Eden switch needs the companion bridge");
  assert.match(shell, /Boolean\(window\.AN3NativeController\)/, "the controller switch needs the controller bridge");
  assert.match(shell, /all\[id\] === true && surfaceAvailable\(id\)/, "an unavailable surface must not count as on");
  assert.match(read("native-offline/web/native.css"), /\.native-flag-input:checked\+\.native-flag-track/, "the track must show the checked state without :has");

  assert.match(shell, /native-flags|AN3ShellFlags\.definitions/, "labels and notes come from the shared model");
});

test("each surface is gated on its own switch, not merely disabled", () => {
  for (const card of ["nativeSwitchCard", "nativeLanSyncCard", "nativeControllerCard"]) {
    assert.match(shell, new RegExp(`${card}[\\s\\S]{0,400}?hidden`), `${card} must be hidden when its switch is off`);
  }
  assert.match(shell, /experimental-switch-eden/);
  assert.match(shell, /experimental-lan-sync/);
  assert.match(shell, /experimental-phone-controller/);
});

test("the Devices destination disappears when nothing on it is enabled", () => {
  assert.match(shell, /\[data-nav="devices"\]/, "the destination is addressed by data-nav");
  assert.match(shell, /anyOn/, "the destination is hidden when no optional feature is on");
  // It must also be hidden before the first script runs, so a host with every
  // switch off cannot flash an empty destination during startup.
  for (const match of index.matchAll(/<button[^>]*data-nav="devices"[^>]*>/g)) {
    assert.match(match[0], /\bhidden\b/, "the destination must start hidden in the markup");
  }
});

test("a change applies immediately and never strands the user", () => {
  assert.match(shell, /subscribe\(/, "the shell must react to a change instead of requiring a restart");
  assert.match(shell, /refreshSwitchSurface/, "turning the Eden switch on must reveal its row in the same session");
  assert.match(shell, /current === "devices"[\s\S]{0,80}show\("play"\)/, "turning everything off while on Devices must leave the page");
});

test("the generic settings panel does not duplicate the switches", () => {
  // One control per feature: the Optional features card writes the shell store,
  // and the per-platform settings list must not render a second, dead checkbox.
  assert.match(settings, /externalGlobal\(\)[\s\S]{0,120}experimental/, "the settings list must exclude the optional-feature category");
});

test("LAN service, polling and discovery follow the optional feature lifecycle", () => {
  assert.match(shell, /flags\?\.subscribe\(\(\) => \{[\s\S]{0,120}refreshSyncLifecycle\(\);/);
  assert.match(shell, /const enabled = experimentalStates\.sync/);
  assert.match(shell, /AN3NativeSync\.setEnabled\(true/);
  assert.match(shell, /AN3NativeSync\.setEnabled\(false/);
  assert.match(shell, /native_sync_stop|\.setEnabled\(false\)/);
  assert.doesNotMatch(shell, /setInterval\(refresh, 2500\)/);
  assert.match(nativeSync, /const setEnabled = \(enabled/);
  assert.match(nativeSync, /clearLifecycleTimers/);
  assert.match(nativeSync, /globalThis\.setInterval/);
  assert.match(nativeSync, /call\("native_sync_stop"\)/);
});

test("the shell and the committed Android mirror stay identical", () => {
  for (const name of ["native-app.js", "native-settings.js", "game-settings.js", "native-flags.js", "native.css", "index.html"]) {
    const source = read(`native-offline/web/${name}`);
    const mirror = read(`native-offline/src-tauri/gen/android/app/src/main/assets/${name}`);
    assert.equal(mirror, source, `re-copy native-offline/web/${name} into the Android mirror`);
  }
});
