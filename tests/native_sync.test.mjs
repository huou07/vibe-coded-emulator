import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {test} from "node:test";
import vm from "node:vm";

const source = await readFile(new URL("../native-offline/web/native-sync.js", import.meta.url), "utf8");

test("Android packaged sync scripts match their source files", async () => {
  const androidAssets = new URL("../native-offline/src-tauri/gen/android/app/src/main/assets/", import.meta.url);
  const [packagedSync, appSource, packagedApp, bootstrapSource, packagedBootstrap] = await Promise.all([
    readFile(new URL("native-sync.js", androidAssets), "utf8"),
    readFile(new URL("../native-offline/web/native-app.js", import.meta.url), "utf8"),
    readFile(new URL("native-app.js", androidAssets), "utf8"),
    readFile(new URL("../native-offline/web/native-bootstrap.js", import.meta.url), "utf8"),
    readFile(new URL("native-bootstrap.js", androidAssets), "utf8"),
  ]);
  assert.equal(packagedSync, source);
  assert.equal(packagedApp, appSource);
  assert.equal(packagedBootstrap, bootstrapSource);
});

const loadSync = (calls = [], statusPayload = null, overrides = {}, timers = {scheduled: [], cleared: []}) => {
  const storageValues = new Map();
  const invoke = async (name, args) => {
    calls.push({name, args});
    if (Object.prototype.hasOwnProperty.call(overrides, name)) {
      const value = overrides[name];
      return typeof value === "function" ? value(args) : value;
    }
    if (name === "native_sync_start") return {running: true, role: "host", mode: args.mode, deviceId: "an3-local", code: "123456", peers: [], error: ""};
    if (name === "native_sync_status") return statusPayload || {running: true, role: "host", mode: "guest", deviceId: "an3-local", code: "123456", peers: [], error: ""};
    if (name === "native_sync_identity") return {deviceId: "an3-local"};
    return {records: []};
  };
  const context = {
    Map,
    Set,
    Uint8Array,
    Blob,
    Promise,
    atob: value => Buffer.from(value, "base64").toString("binary"),
    btoa: value => Buffer.from(value, "binary").toString("base64"),
    localStorage: {
      getItem(key) { return storageValues.get(key) ?? null; },
      setItem(key, value) { storageValues.set(key, String(value)); },
    },
    setInterval(callback, delay) {
      const handle = {callback, delay};
      timers.scheduled.push(handle);
      return handle;
    },
    clearInterval(handle) { timers.cleared.push(handle); },
    AN3NativeInvoke: () => invoke,
    AN3SyncTransfer: {sync: async () => ({counts: {uploaded: 0, downloaded: 0, conflicts: 0}})},
    globalThis: null,
  };
  context.globalThis = context;
  vm.runInNewContext(source, context, {filename: "native-sync.js"});
  return context.AN3NativeSync;
};

test("guest mode starts without an account or server request", async () => {
  const calls = [];
  const sync = loadSync(calls);
  assert.equal(sync.mode(), "guest");
  await sync.setEnabled(true);
  assert.equal(calls[0].name, "native_sync_start");
  assert.equal(calls[0].args.mode, "guest");
  assert.equal(calls.some(call => String(call.name).includes("account")), false);
});

test("disabled sync lifecycle does not start sockets and always cleans stale runtime", async () => {
  const calls = [];
  const timers = {scheduled: [], cleared: []};
  const sync = loadSync(calls, null, {}, timers);

  await sync.setEnabled(false);

  assert.deepEqual(calls.map(call => call.name), ["native_sync_stop"]);
  assert.equal(timers.scheduled.length, 0);
  assert.equal(timers.cleared.length, 0);
  assert.throws(() => sync.start(), /disabled in this app/);
  assert.throws(() => sync.join("123456"), /disabled in this app/);
  assert.throws(() => sync.reconnect("an3-peer"), /disabled in this app/);
});

test("enabled sync lifecycle starts once and disabling closes timers and native runtime", async () => {
  const calls = [];
  const timers = {scheduled: [], cleared: []};
  const sync = loadSync(calls, null, {native_sync_discover: []}, timers);
  let refreshes = 0;
  let discovered = null;

  await sync.setEnabled(true, {
    refresh: () => { refreshes += 1; },
    onDiscovery: peers => { discovered = peers; },
  });

  assert.equal(calls[0].name, "native_sync_start");
  assert.equal(calls.filter(call => call.name === "native_sync_start").length, 1);
  assert.deepEqual(timers.scheduled.map(timer => timer.delay), [2500, 8000]);
  assert.equal(refreshes, 1);
  await timers.scheduled[1].callback();
  assert.deepEqual(discovered, []);
  assert.equal(refreshes, 2);

  await sync.setEnabled(false);

  assert.deepEqual(timers.cleared, timers.scheduled);
  assert.equal(calls.at(-1).name, "native_sync_stop");
});

test("rapid disable and re-enable serializes native listener transitions", async () => {
  const calls = [];
  const timers = {scheduled: [], cleared: []};
  let releaseFirstStart;
  let starts = 0;
  const sync = loadSync(calls, null, {
    native_sync_start: args => {
      starts += 1;
      if (starts === 1) return new Promise(resolve => { releaseFirstStart = resolve; });
      return {running: true, mode: args.mode, peers: []};
    },
  }, timers);

  const enabling = sync.setEnabled(true);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(typeof releaseFirstStart, "function");
  const disabling = sync.setEnabled(false);
  const reEnabling = sync.setEnabled(true);
  releaseFirstStart({running: true, mode: "guest", peers: []});
  await Promise.all([enabling, disabling, reEnabling]);

  assert.deepEqual(calls.map(call => call.name), ["native_sync_start", "native_sync_stop", "native_sync_start"]);
  assert.deepEqual(timers.scheduled.map(timer => timer.delay), [2500, 8000]);
  await sync.setEnabled(false);
  assert.deepEqual(timers.cleared, timers.scheduled);
});

test("a queued reconnect cannot reopen the listener after disable", async () => {
  const calls = [];
  const sync = loadSync(calls);
  await sync.setEnabled(true);
  const reconnecting = sync.reconnect("an3-peer");
  const disabling = sync.setEnabled(false);

  await assert.rejects(reconnecting, /disabled in this app/);
  await disabling;

  assert.deepEqual(calls.map(call => call.name), ["native_sync_start", "native_sync_stop"]);
});

test("guest pairing requires exactly six decimal digits unless reconnecting by identity", async () => {
  const sync = loadSync();
  await sync.setEnabled(true);
  assert.throws(() => sync.join("12"), /six decimal digits/);
  await assert.doesNotReject(sync.join("123456", "an3-peer-1234"));
});

test("a directly paired peer is eligible without account verification", async () => {
  const sync = loadSync([], {
    running: true,
    role: "host",
    mode: "guest",
    deviceId: "an3-local",
    peers: [{deviceId: "an3-remote", mode: "guest", state: "connected"}],
  });
  assert.equal(await sync.peerAuthorized(), true);
});

test("save sync rejects a missing peer before hashing the ROM", async () => {
  const calls = [];
  const sync = loadSync(calls);
  await assert.rejects(sync.syncGame("gba", "game-1"), /Pair with a direct LAN peer/);
  assert.equal(calls.some(call => call.name === "native_sync_game_identity"), false);
});

test("save sync reports ROM verification and transfer progress after peer preflight", async () => {
  const calls = [];
  const messages = [];
  const sync = loadSync(calls, {
    running: true,
    role: "host",
    mode: "guest",
    deviceId: "an3-local",
    peers: [{deviceId: "an3-remote", mode: "guest", state: "connected"}],
  }, {
    native_sync_game_identity: {system: "gba", core: "mgba", gameId: "rom-123", romHash: "a".repeat(64), romId: "game-1"},
  });

  await sync.syncGame("gba", "game-1", "save", message => messages.push(message));

  assert.deepEqual(messages, [
    "Reading the game file to verify its identity. Large files can take a while.",
    "Comparing and syncing save data…",
  ]);
  assert.ok(calls.findIndex(call => call.name === "native_sync_status") < calls.findIndex(call => call.name === "native_sync_game_identity"));
});

test("legacy account mode cannot enable account-dependent sync", async () => {
  const calls = [];
  const sync = loadSync(calls);
  assert.equal(sync.mode(), "guest");
  assert.equal(sync.setMode, undefined);
  assert.equal(sync.authenticateAccount, undefined);
  await sync.setEnabled(true);
  assert.equal(calls[0].name, "native_sync_start");
  assert.equal(calls[0].args.mode, "guest");
  assert.equal(calls.some(call => String(call.name).includes("account")), false);
});

test("large save publishes use bounded chunks and commit only after all chunks", async () => {
  const calls = [];
  const received = [];
  let receivedSize = 0;
  const sync = loadSync(calls, null, {
    native_sync_request: ({method, payload}) => {
      if (method === "ping") return {chunkedTransfers: 1};
      if (method === "publish-begin") {
        assert.equal(payload.payload.items[0].data, undefined);
        return {transferId: "transfer-1"};
      }
      if (method === "publish-chunk") {
        const bytes = Buffer.from(payload.data, "base64");
        assert.ok(bytes.length <= 768 * 1024);
        assert.equal(payload.offset, receivedSize);
        received.push(bytes);
        receivedSize += bytes.length;
        return {nextOffset: receivedSize};
      }
      if (method === "publish-commit") return {ok: true, accepted: 1};
      throw new Error(`Unexpected sync method: ${method}`);
    },
  });
  const bytes = Buffer.alloc(4 * 1024 * 1024 + 13, 0x5a);
  const result = await sync.transport.publish({
    kind: "save",
    items: [{key: "save:test", path: "/data/saves/test.srm", size: bytes.length, contentHash: "a".repeat(64), data: bytes.toString("base64")}],
  });

  assert.deepEqual(result, {ok: true, accepted: 1});
  assert.deepEqual(Buffer.concat(received), bytes);
  assert.equal(calls.at(-1).args.method, "publish-commit");
});

test("large save downloads assemble bounded range responses in order", async () => {
  const calls = [];
  const sync = loadSync(calls, null, {
    native_sync_request: ({method, payload}) => {
      if (method === "ping") return {chunkedTransfers: 1};
      assert.equal(method, "blob");
      const offset = payload.offset;
      const bytes = Buffer.alloc(Math.min(768 * 1024, payload.item.size - offset), 0x36);
      return {
        offset,
        size: payload.item.size,
        contentHash: payload.item.contentHash,
        data: bytes.toString("base64"),
      };
    },
  });
  const expected = Buffer.alloc(4 * 1024 * 1024 + 29, 0x36);
  const item = {key: "save:test", path: "/data/saves/test.srm", size: expected.length, contentHash: "b".repeat(64)};
  const result = await sync.transport.blob("save", item, {kind: "save"});

  assert.deepEqual(Buffer.from(result), expected);
  const blobCalls = calls.filter(call => call.args.method === "blob");
  assert.equal(blobCalls.length, 6);
  assert.deepEqual(blobCalls.map(call => call.args.payload.offset), [0, 768 * 1024, 1536 * 1024, 2304 * 1024, 3072 * 1024, 3840 * 1024]);
});
