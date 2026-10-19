// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Eden/Switch, LAN Sync and Phone Controller are experimental: a user who only
// wants GBA, NDS and 3DS must be able to keep them entirely out of the way. The
// switches therefore default to off, and each surface is gated on its switch
// rather than merely disabled. Settings keeps all three switches visible, which
// is the only way back for a user who turned them off.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const read = path => readFileSync(resolve(root, path), "utf8");
const schema = JSON.parse(read("native-offline/shared/native-settings-schema.json"));
const shell = read("native-offline/web/native-app.js");
const model = read("native-offline/web/native-settings.js");
const mirror = read("native-offline/src-tauri/gen/android/app/src/main/assets/native-app.js");
const mirrorModel = read("native-offline/src-tauri/gen/android/app/src/main/assets/native-settings.js");

const ids = ["experimental-switch-eden", "experimental-lan-sync", "experimental-phone-controller"];

test("the three experimental features are declared, off by default and user-editable", () => {
  for (const id of ids) {
    const definition = schema.global.find(item => item.id === id);
    assert.ok(definition, `${id} must be declared in the shared settings model`);
    assert.equal(definition.type, "bool", `${id} is a switch`);
    assert.equal(definition.default, "false", `${id} must default to off`);
    assert.equal(definition.category, "experimental");
    assert.equal(definition.external, true, `${id} must reach the application settings panel`);
    assert.ok(definition.note && definition.note.length > 20, `${id} must explain itself`);
  }
});

test("each experimental surface is gated on its own switch, not merely disabled", () => {
  assert.match(shell, /experimental-switch-eden/, "the shell must read the Eden switch");
  assert.match(shell, /experimental-lan-sync/);
  assert.match(shell, /experimental-phone-controller/);
  for (const card of ["nativeSwitchCard", "nativeAccountSyncCard", "nativeControllerCard"]) {
    assert.match(shell, new RegExp(`${card}[\\s\\S]{0,400}hidden = true`), `${card} must be hidden when its switch is off`);
  }
});

test("the Devices destination disappears when nothing on it is enabled", () => {
  assert.match(shell, /\[data-nav="devices"\]/, "the destination is addressed by data-nav");
  assert.match(shell, /anyOn/, "the destination is hidden when no experimental feature is on");
});

test("the shell and the committed Android mirror stay identical", () => {
  assert.equal(mirror, shell, "re-copy native-offline/web/native-app.js into the mirror");
  assert.equal(mirrorModel, model, "re-copy native-offline/web/native-settings.js into the mirror");
});
