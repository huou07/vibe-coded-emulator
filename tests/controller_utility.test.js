// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Behavioral tests for the shared Phone Controller utility dispatcher used by
// the browser player host (and mirrored by the native hosts' own dedup).
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "static", "controller-utility.js"), "utf8");
const context = {module: {exports: {}}};
vm.runInNewContext(source, context);
const {ACTIONS, createDispatcher} = context.module.exports;

const operations = () => {
  const calls = {quick: 0, up: 0, down: 0, menu: 0};
  return {
    calls,
    ops: {
      QUICK_SAVE: () => { calls.quick += 1; return "saved"; },
      SPEED_UP: () => { calls.up += 1; return 2; },
      SPEED_DOWN: () => { calls.down += 1; return 1; },
      OPEN_MENU: () => { calls.menu += 1; return true; },
    },
  };
};

assert.equal(ACTIONS.join(","), "QUICK_SAVE,SPEED_UP,SPEED_DOWN,OPEN_MENU", "canonical utility actions");

// A single press runs the corresponding existing operation exactly once.
{
  const {calls, ops} = operations();
  const dispatcher = createDispatcher(ops);
  const results = dispatcher.dispatch([{action: "QUICK_SAVE", sequence: 1}]);
  assert.equal(calls.quick, 1);
  assert.equal(results[0].ok, true);
}
assert.ok(true, "utilities dispatch once");

// Duplicate / retried sequences never repeat the side effect.
{
  const {calls, ops} = operations();
  const dispatcher = createDispatcher(ops);
  dispatcher.dispatch([{action: "QUICK_SAVE", sequence: 5}]);
  dispatcher.dispatch([{action: "QUICK_SAVE", sequence: 5}]); // retry
  dispatcher.dispatch([{action: "QUICK_SAVE", sequence: 4}]); // stale
  assert.equal(calls.quick, 1, "quick save must run once per deliberate press");
  assert.equal(dispatcher.lastSequence, 5);
}

// Speed uses the host's own operations and both directions work.
{
  const {calls, ops} = operations();
  const dispatcher = createDispatcher(ops);
  dispatcher.dispatch([{action: "SPEED_UP", sequence: 1}, {action: "SPEED_DOWN", sequence: 2}]);
  assert.equal(calls.up, 1);
  assert.equal(calls.down, 1);
}

// Menu opens through the host operation.
{
  const {calls, ops} = operations();
  const dispatcher = createDispatcher(ops);
  dispatcher.dispatch([{action: "OPEN_MENU", sequence: 1}]);
  assert.equal(calls.menu, 1);
}

// Unknown actions are reported, never silently treated as success.
{
  const {ops} = operations();
  const dispatcher = createDispatcher(ops);
  const results = dispatcher.dispatch([{action: "FORMAT_DISK", sequence: 1}]);
  assert.equal(results[0].ok, false);
  assert.equal(results[0].reason, "unsupported");
}

// A failing host operation is surfaced instead of pretending success.
{
  const dispatcher = createDispatcher({QUICK_SAVE: () => { throw new Error("Save state is not ready"); }});
  const results = dispatcher.dispatch([{action: "QUICK_SAVE", sequence: 1}]);
  assert.equal(results[0].ok, false);
  assert.match(results[0].reason, /not ready/);
}

// Malformed / empty utility lists are safe.
{
  const dispatcher = createDispatcher({});
  assert.equal(dispatcher.dispatch(undefined).length, 0);
  assert.equal(dispatcher.dispatch([]).length, 0);
  assert.equal(dispatcher.dispatch([{sequence: 3}])[0].ok, false);
}

// Reconnect resets the guard so a fresh session's sequence 1 can run again.
{
  const {calls, ops} = operations();
  const dispatcher = createDispatcher(ops);
  dispatcher.dispatch([{action: "QUICK_SAVE", sequence: 1}]);
  dispatcher.reset();
  dispatcher.dispatch([{action: "QUICK_SAVE", sequence: 1}]);
  assert.equal(calls.quick, 2, "a new session may reuse sequence numbers");
}

console.log("controller utility behavior: ok");
