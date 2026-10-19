// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Deterministic out-of-order test for the library render generation guard.
// The library can start overlapping async reads (navigation, return-from-game,
// native capability re-render, import/remove); a slow older read must never
// commit after a newer one or whole system sections disappear. This evaluates
// the real guard source and forces adversarial completion orders.
import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../static/offline.js", import.meta.url), "utf8");

const marker = "const libraryRenderState = {generation: 0};";
const endMarker = "const isCurrentLibraryRender = generation => generation === libraryRenderState.generation;";
const start = source.indexOf(marker);
const end = source.indexOf(endMarker);
assert.ok(start >= 0 && end > start, "the render guard block must exist in static/offline.js");
const guardSource = source.slice(start, end + endMarker.length) + "\nthis.guard = {beginLibraryRender, isCurrentLibraryRender};";
const sandbox = {};
vm.runInNewContext(guardSource, sandbox);

test("the real guard block evaluates and starts at generation zero", () => {
  assert.equal(typeof sandbox.guard.beginLibraryRender, "function");
  assert.equal(typeof sandbox.guard.isCurrentLibraryRender, "function");
});

test("a newer render always invalidates every older in-flight render", () => {
  for (let i = 0; i < 500; i += 1) {
    const inFlight = [];
    const renders = 2 + (i % 5);
    for (let r = 0; r < renders; r += 1) inFlight.push(sandbox.guard.beginLibraryRender());
    const newest = inFlight[inFlight.length - 1];
    // Randomize completion order: only the newest token may commit.
    const order = inFlight.map((token, index) => ({token, index}));
    for (let s = order.length - 1; s > 0; s -= 1) {
      const j = (i * 7 + s * 13) % (s + 1);
      [order[s], order[j]] = [order[j], order[s]];
    }
    const committed = order.filter(entry => sandbox.guard.isCurrentLibraryRender(entry.token));
    assert.equal(committed.length, 1, "exactly one render may commit");
    assert.equal(committed[0].token, newest, "the newest render must be the one that commits");
  }
});

test("renderLibrary consults the guard before it touches the DOM", () => {
  const body = source.slice(source.indexOf("const renderLibrary = async () =>"));
  const awaited = body.indexOf("const games=await all();");
  const guardCheck = body.indexOf("if(!isCurrentLibraryRender(generation))return;");
  const firstDomWrite = body.indexOf("grid.replaceChildren();");
  assert.ok(awaited >= 0 && guardCheck > awaited && firstDomWrite > guardCheck);
});
