// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Behavioral tests for the canonical input/action contract generated from
// native-offline/shared/input-actions-schema.json. These exercise the same
// directional geometry the native overlay and the Phone Controller use.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../static/input-actions.js", import.meta.url), "utf8");
const load = () => {
  const sandbox = { module: { exports: {} } };
  vm.runInNewContext(source, sandbox);
  return sandbox.module.exports;
};
const model = load();
const dirs = (dx, dy, previous = null) => model.circularDirections(dx, dy, previous);

test("gameplay actions map to the existing libretro ids", () => {
  assert.equal(model.buttons.UP.libretro, 4);
  assert.equal(model.buttons.DOWN.libretro, 5);
  assert.equal(model.buttons.LEFT.libretro, 6);
  assert.equal(model.buttons.RIGHT.libretro, 7);
  assert.equal(model.buttons.A.libretro, 8);
  assert.equal(model.buttons.B.libretro, 0);
  assert.equal(model.buttons.X.libretro, 9);
  assert.equal(model.buttons.Y.libretro, 1);
  assert.equal(model.buttons.L.libretro, 10);
  assert.equal(model.buttons.R.libretro, 11);
  assert.equal(model.buttons.START.libretro, 3);
  assert.equal(model.buttons.SELECT.libretro, 2);
  assert.equal(model.idToWire[4], "up");
  assert.equal(model.wireToId.quick_save, undefined);
});

test("utility actions are distinct from held buttons", () => {
  assert.equal(model.utilityActions.slice().sort().join(","), "OPEN_MENU,QUICK_LOAD,QUICK_SAVE,SPEED_DOWN,SPEED_UP");
  for (const action of model.utilityActions) assert.equal(model.buttons[action], undefined);
  assert.equal(model.utilityWireToAction.speed_up, "SPEED_UP");
});

test("movement controls include the circular D-pad", () => {
  assert.equal(model.directionalControls.map(control => control.id).join(","), "dpad,joystick,circular");
});

const closeSet = (actions, expected) => assert.equal([...actions].sort().join(","), [...expected].sort().join(","));

test("cardinal directions resolve correctly", () => {
  closeSet(dirs(0, -1).actions, ["UP"]);
  closeSet(dirs(0, 1).actions, ["DOWN"]);
  closeSet(dirs(-1, 0).actions, ["LEFT"]);
  closeSet(dirs(1, 0).actions, ["RIGHT"]);
});

test("each diagonal emits exactly two cardinal digital inputs", () => {
  closeSet(dirs(1, -1).actions, ["UP", "RIGHT"]);
  closeSet(dirs(-1, -1).actions, ["UP", "LEFT"]);
  closeSet(dirs(-1, 1).actions, ["DOWN", "LEFT"]);
  closeSet(dirs(1, 1).actions, ["DOWN", "RIGHT"]);
});

test("center and dead zone are neutral", () => {
  assert.equal(dirs(0, 0).actions.length, 0);
  assert.equal(dirs(0.1, 0.1).actions.length, 0);
  assert.equal(dirs(0.1, 0.1).region, null);
});

// A pointer `degrees` clockwise from straight up (0 = up, 45 = up-right).
const fromNorth = degrees => [Math.sin(degrees * Math.PI / 180), -Math.cos(degrees * Math.PI / 180)];

test("boundary math is deterministic without flicker", () => {
  // 20 degrees from up stays up; past the 22.5 degree half-sector it becomes the diagonal.
  closeSet(dirs(...fromNorth(20)).actions, ["UP"]);
  closeSet(dirs(...fromNorth(24)).actions, ["UP", "RIGHT"]);
  closeSet(dirs(...fromNorth(-24)).actions, ["UP", "LEFT"]);
});

test("hysteresis keeps the previous region near a boundary", () => {
  // 25 degrees from up is inside 22.5 + hysteresis, so the previous region is kept.
  const held = dirs(...fromNorth(25), "N");
  closeSet(held.actions, ["UP"]);
  assert.equal(held.region, "N");
  // Without the previous region the nearest sector (up/right) wins.
  const fresh = dirs(...fromNorth(25));
  closeSet(fresh.actions, ["UP", "RIGHT"]);
  // Far enough past the boundary the region switches even with hysteresis.
  const switched = dirs(...fromNorth(35), "N");
  closeSet(switched.actions, ["UP", "RIGHT"]);
  assert.equal(switched.region, "NE");
});

test("dragging cardinal -> diagonal -> neutral", () => {
  const up = dirs(0, -1, null);
  assert.equal(up.region, "N");
  const diagonal = dirs(1, -1, up.region);
  closeSet(diagonal.actions, ["UP", "RIGHT"]);
  assert.equal(diagonal.region, "NE");
  const neutral = dirs(0, 0, diagonal.region);
  assert.equal(neutral.actions.length, 0);
  assert.equal(neutral.region, null);
});

test("outside the circular control still yields a direction", () => {
  closeSet(dirs(4, -4).actions, ["UP", "RIGHT"]);
  closeSet(dirs(-9, 0).actions, ["LEFT"]);
});

test("geometry is size independent (normalized radius)", () => {
  // A small pointer (0.4 radius) and a large one (1.0) at the same angle agree.
  const small = dirs(0.4 * Math.SQRT1_2, -0.4 * Math.SQRT1_2);
  const large = dirs(Math.SQRT1_2, -Math.SQRT1_2);
  closeSet(small.actions, large.actions);
});

test("non-finite input is neutral instead of throwing", () => {
  assert.equal(dirs(NaN, 0).actions.length, 0);
  assert.equal(dirs(0, Infinity).actions.length, 0);
});
