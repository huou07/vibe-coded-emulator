// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Behavioral tests for static/multiplayer.js. The script is loaded in a VM with
// a minimal DOM/fetch/storage stub so the real client code runs: it must send a
// stable device identity, persist the room, resume it through the reconnect
// endpoint, and close it on a real unload. These assert client behavior, not
// source strings.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(here, "..", "static", "multiplayer.js"), "utf8");

function makeElement(id) {
  return {
    id,
    hidden: false,
    value: "",
    textContent: "",
    href: "",
    src: "",
    className: "",
    options: [],
    selectedIndex: 0,
    handlers: {},
    addEventListener(type, handler) { this.handlers[type] = handler; },
    getAttribute() { return null; },
    focus() {},
  };
}

function makeStorage(seed = {}) {
  const data = new Map(Object.entries(seed));
  return {
    getItem: key => (data.has(key) ? data.get(key) : null),
    setItem: (key, value) => { data.set(key, String(value)); },
    removeItem: key => { data.delete(key); },
    _data: data,
  };
}

function makeSandbox(routes, {seed = {}, search = ""} = {}) {
  const elements = new Map();
  const calls = [];
  const windowHandlers = {};
  const document = {
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, makeElement(id));
      return elements.get(id);
    },
  };
  const localStorage = makeStorage();
  const sessionStorage = makeStorage(seed);
  const fetch = async (url, options = {}) => {
    calls.push({url, method: options.method || "GET", body: options.body, keepalive: !!options.keepalive});
    const route = routes[url.split("?")[0]] || {status: 200, body: {}};
    return {
      ok: route.status >= 200 && route.status < 300,
      status: route.status,
      json: async () => route.body,
    };
  };
  const sandbox = {
    document,
    location: {search},
    localStorage,
    sessionStorage,
    navigator: {clipboard: {writeText: async () => {}}},
    fetch,
    addEventListener(type, handler) { windowHandlers[type] = handler; },
    setInterval: () => 1,
    clearInterval: () => {},
    console,
    URLSearchParams,
    crypto: {randomUUID: () => "11111111-2222-3333-4444-555555555555"},
  };
  return {sandbox, document, elements, calls, windowHandlers, localStorage, sessionStorage};
}

function run(sandbox) {
  vm.runInNewContext(source, sandbox, {filename: "multiplayer.js"});
}

const signatureRoute = {
  "/api/multiplayer/room": {status: 201, body: {code: "ABC123", token: "host-token", role: "host", expiresInSeconds: 900}},
  "/api/multiplayer/join": {status: 200, body: {code: "ABC123", token: "guest-token", role: "guest"}},
  "/api/multiplayer/reconnect": {status: 200, body: {code: "ROOM01", token: "fresh-token", role: "host"}},
  "/api/multiplayer/leave": {status: 200, body: {ok: true}},
};

test("create posts a stable device id and persists the room", async () => {
  const context = makeSandbox(signatureRoute);
  run(context.sandbox);
  context.document.getElementById("mpSystem").value = "gba";
  context.document.getElementById("mpHash").value = "sha256:" + "a".repeat(64);

  await context.document.getElementById("mpCreateBtn").handlers.click();

  const create = context.calls.find(call => call.url === "/api/multiplayer/room");
  assert.ok(create, "the create request is sent");
  const payload = JSON.parse(create.body);
  assert.match(payload.deviceId, /^web-/);
  assert.equal(payload.deviceId, context.localStorage.getItem("an3-mp-device"));
  assert.equal(context.document.getElementById("mpRoomCode").textContent, "ABC 123");
  assert.equal(context.document.getElementById("mpRoomBox").hidden, false);

  const saved = JSON.parse(context.sessionStorage.getItem("an3-mp-room"));
  assert.equal(saved.code, "ABC123");
  assert.equal(saved.token, "host-token");
  assert.equal(saved.role, "host");
});

test("join shows the room and a play link for the guest", async () => {
  const context = makeSandbox(signatureRoute);
  run(context.sandbox);
  context.document.getElementById("mpSystem").value = "gba";
  context.document.getElementById("mpHash").value = "sha256:" + "a".repeat(64);
  context.document.getElementById("mpCode").value = "abc123";

  await context.document.getElementById("mpJoinBtn").handlers.click();

  const join = context.calls.find(call => call.url === "/api/multiplayer/join");
  assert.ok(join, "the join request is sent");
  assert.equal(JSON.parse(join.body).code, "ABC123");
  const link = context.document.getElementById("mpRoomLink");
  assert.equal(link.hidden, false);
  assert.match(link.href, /room=ABC123/);
  assert.equal(JSON.parse(context.sessionStorage.getItem("an3-mp-room")).role, "guest");
});

test("resume re-admits a persisted member through reconnect", async () => {
  const saved = JSON.stringify({code: "ROOM01", token: "old-token", role: "host", slug: "pokemon"});
  const context = makeSandbox(signatureRoute, {seed: {"an3-mp-room": saved}});
  run(context.sandbox);
  await new Promise(resolve => setImmediate(resolve));

  const reconnect = context.calls.find(call => call.url === "/api/multiplayer/reconnect");
  assert.ok(reconnect, "the reconnect request is sent");
  assert.equal(JSON.parse(reconnect.body).token, "old-token");
  assert.equal(context.document.getElementById("mpRoomCode").textContent, "ROO M01");
  const persisted = JSON.parse(context.sessionStorage.getItem("an3-mp-room"));
  assert.equal(persisted.token, "fresh-token");
});

test("a real unload leaves the room while a bfcache hide keeps it", async () => {
  const context = makeSandbox(signatureRoute);
  run(context.sandbox);
  context.document.getElementById("mpSystem").value = "gba";
  context.document.getElementById("mpHash").value = "sha256:" + "a".repeat(64);
  await context.document.getElementById("mpCreateBtn").handlers.click();

  // A bfcache hide must not destroy the room: the user can come back.
  context.windowHandlers.pagehide({persisted: true});
  assert.equal(context.calls.some(call => call.url === "/api/multiplayer/leave"), false);
  assert.ok(context.sessionStorage.getItem("an3-mp-room"));

  // A real unload closes it and clears the persisted membership.
  context.windowHandlers.pagehide({persisted: false});
  const leave = context.calls.find(call => call.url === "/api/multiplayer/leave");
  assert.ok(leave, "leave is sent on a real unload");
  assert.equal(leave.keepalive, true);
  assert.equal(context.sessionStorage.getItem("an3-mp-room"), null);
});
