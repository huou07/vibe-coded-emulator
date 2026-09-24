// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Track B1 behavioral test: the phone page stamps every gameplay frame with its
// own monotonic capture time (`t0`) and computes controller RTT by subtracting
// the host's echo of that same value from the same phone clock. This asserts
// real client behavior in a VM with a minimal DOM/adapter stub, not source
// strings: if the stamp or the echo handling regress, a frame would carry no
// `t0` or the phone would fall back to mixing two different clocks.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "static", "controller.js"), "utf8");

const makeElement = (attributes = {}) => {
  const listeners = {};
  const element = {
    hidden: false,
    value: "",
    textContent: "",
    href: "",
    src: "",
    dataset: {},
    style: {setProperty() {}},
    children: [],
    classList: {add() {}, remove() {}, contains() { return false; }},
    attributes,
    addEventListener(type, handler) { (listeners[type] = listeners[type] || []).push(handler); },
    dispatch(type, event) { (listeners[type] || []).forEach((handler) => handler(event)); },
    setAttribute(name, value) { element.attributes[name] = value; },
    removeAttribute(name) { delete element.attributes[name]; },
    getAttribute(name) { return Object.prototype.hasOwnProperty.call(element.attributes, name) ? element.attributes[name] : null; },
    querySelectorAll() { return []; },
    querySelector() { return null; },
    getBoundingClientRect() { return {left: 0, top: 0, width: 100, height: 100}; },
    appendChild(child) { element.children.push(child); return child; },
    setPointerCapture() {},
  };
  return element;
};

// Load the phone page with a controlled clock and a recording dev adapter.
const loadPhone = (now) => {
  const frames = [];
  const elements = new Map();
  const byId = (id) => {
    if (!elements.has(id)) elements.set(id, makeElement());
    return elements.get(id);
  };
  byId("ctrlJoinPanel");
  byId("ctrlCode").value = "ABC123";

  const adapter = {
    link: {paired: true, inputActive: true, lastSequence: 1, ackSequence: 1},
    request: async (url, options) => {
      if (/\/api\/controller\/state/.test(url)) {
        frames.push(JSON.parse(options.body));
        return {ok: true, json: async () => ({ok: true})};
      }
      if (/\/api\/controller\/link/.test(url)) {
        return {ok: true, json: async () => adapter.link};
      }
      if (/\/api\/controller\/pair/.test(url)) {
        return {ok: true, json: async () => ({token: "guest", code: "ABC123"})};
      }
      if (/\/api\/controller\/join/.test(url)) {
        return {ok: true, json: async () => ({token: "guest"})};
      }
      return {ok: true, json: async () => ({})};
    },
  };

  // A single gameplay button the page binds through bindButtons().
  const button = makeElement({"data-btn": "a"});
  const queryAll = (selector) => {
    if (selector === "#ctrlPad [data-btn]") return [button];
    return [];
  };

  const document = {
    getElementById: byId,
    querySelectorAll: queryAll,
    createElement: () => makeElement(),
    addEventListener() {},
    body: makeElement(),
  };
  const window = {
    performance: {now: () => now()},
    AN3ControllerDevAdapter: adapter,
    AN3InputActions: {utilityWireToAction: {}},
    localStorage: {getItem() { return null; }, setItem() {}},
    addEventListener() {},
    navigator: {vibrate() {}},
    document,
    setTimeout,
    clearTimeout,
    setInterval() { return 0; },
    clearInterval() {},
    Date,
  };
  const context = {
    window,
    document,
    console,
    JSON,
    Math,
    Object,
    Array,
    Set,
    Promise,
    Error,
    Date,
    setTimeout,
    clearTimeout,
    setInterval() { return 0; },
    clearInterval() {},
    addEventListener() {},
    removeEventListener() {},
  };
  window.window = window;
  window.setInterval = context.setInterval;
  vm.runInNewContext(source, context);
  return {frames, adapter, button, elements};
};

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

(async () => {
  // 1. A real gameplay press produces a frame carrying the phone's own capture
  //    time from the monotonic clock, not wall time.
  {
    let clock = 5_000;
    const {frames, button} = loadPhone(() => clock);
    await tick();
    button.dispatch("pointerdown", {preventDefault() {}, pointerId: 1});
    await tick();
    assert.ok(frames.length >= 1, "a button press must send a frame");
    const pressFrame = frames.find((frame) => frame.b.includes("a"));
    assert.ok(pressFrame, "the pressed button must be in the frame");
    assert.equal(pressFrame.t0, 5_000, "the frame must carry the phone's capture time");
  }

  // 2. Controller RTT is computed from the echoed capture time on the phone's
  //    own clock: no cross-device subtraction and no wall-clock fallback.
  {
    let clock = 1_020;
    const {adapter, elements} = loadPhone(() => clock);
    // The host echoes the capture time of the frame it applied. The phone's own
    // clock reads 1020, so controller RTT is exactly 40 ms — a value only the
    // echo (not any wall clock) can produce.
    adapter.link = {paired: true, inputActive: true, lastSequence: 1, ackSequence: 1, echoCaptureMs: 980};
    await tick();
    await tick();
    await tick();
    await tick();
    const status = elements.get("ctrlStatus");
    const rtt = status.attributes["data-rtt-ms"];
    assert.equal(rtt, "40", "RTT must be the echo subtracted from the phone clock");
  }

  process.exit(0);
})();
