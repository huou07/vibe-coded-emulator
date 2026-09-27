// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Source contracts for the local Android touchscreen/gamepad input model.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = relative => readFileSync(new URL(relative, import.meta.url), "utf8");
const schema = JSON.parse(read("../native-offline/shared/input-actions-schema.json"));
const kotlin = read("../native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeInputActions.kt");
const overlay = read("../native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeGameOverlay.kt");
const gameActivity = read("../native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeGameActivity.kt");

test("local gameplay buttons keep their libretro ids", () => {
  const buttons = Object.entries(schema.buttons);
  assert.equal(buttons.length, 12);
  assert.equal(new Set(buttons.map(([, item]) => item.libretro)).size, buttons.length);
  for (const [action, id] of Object.entries({UP: 4, DOWN: 5, LEFT: 6, RIGHT: 7, A: 8, B: 0, START: 3, SELECT: 2})) {
    assert.equal(schema.buttons[action].libretro, id);
    assert.match(kotlin, new RegExp(`const val ${action} = ${id}`));
  }
  assert.doesNotMatch(JSON.stringify(schema), /utility|wire/i);
  assert.doesNotMatch(kotlin, /utilityActions|wireToId/);
});

test("Android local controls retain all directional modes and eight circular sectors", () => {
  assert.deepEqual(schema.directionalControls.map(item => item.id), ["dpad", "joystick", "circular"]);
  assert.deepEqual(schema.speeds, ["0.5", "1", "2", "4", "8"]);
  assert.equal(schema.circular.sectors.length, 8);
  assert.equal(schema.circular.sectors.filter(item => item.actions.length === 1).length, 4);
  assert.equal(schema.circular.sectors.filter(item => item.actions.length === 2).length, 4);
  for (const sector of schema.circular.sectors) {
    for (const action of sector.actions) assert.ok(schema.buttons[action], `${sector.id} references ${action}`);
  }
  assert.match(kotlin, /fun circularDirections\(dx: Float, dy: Float, previous: String\?\)/);
  assert.match(kotlin, /fun pressedCardinals\(actions: Set<String>\): Set<Int>/);
  assert.match(overlay, /NativeCircularDpad\(activity\)/);
  assert.match(overlay, /NativeInputActions\.directionalControls/);
  assert.match(gameActivity, /surface\.setOnTouchListener/);
  assert.match(gameActivity, /override fun onGenericMotionEvent/);
});
