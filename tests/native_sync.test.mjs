import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {test} from "node:test";
import vm from "node:vm";

const source = await readFile(new URL("../native-offline/web/native-sync.js", import.meta.url), "utf8");

const loadSync = (calls = [], statusPayload = null, overrides = {}, account = null) => {
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
    AN3NativeInvoke: () => invoke,
    AN3SyncTransfer: {sync: async () => ({counts: {uploaded: 0, downloaded: 0, conflicts: 0}})},
    AN3Account: account,
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
  await sync.init();
  assert.equal(calls[0].name, "native_sync_start");
  assert.equal(calls[0].args.mode, "guest");
  assert.equal(calls.some(call => String(call.name).includes("account")), false);
});

test("guest pairing requires exactly six decimal digits unless reconnecting by identity", async () => {
  const sync = loadSync();
  assert.throws(() => sync.join("12"), /six decimal digits/);
  assert.doesNotThrow(() => sync.join("123456", "an3-peer-1234"));
});

test("guest connected status is eligible while an unverified account peer is not", async () => {
  const sync = loadSync([], {
    running: true,
    role: "host",
    mode: "guest",
    deviceId: "an3-local",
    peers: [{deviceId: "an3-remote", mode: "guest", state: "connected", accountVerified: false}],
  });
  assert.equal(await sync.sameAccount({capability: "sync"}), true);
});

test("save sync rejects a missing peer before hashing the ROM", async () => {
  const calls = [];
  const sync = loadSync(calls);
  await assert.rejects(sync.syncGame("gba", "game-1"), /Connect a compatible sync peer/);
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
    peers: [{deviceId: "an3-remote", mode: "guest", state: "connected", accountVerified: false}],
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

test("account peer remains fail-closed until the encrypted-session proof is verified", async () => {
  const calls = [];
  const status = {
    running: true,
    role: "host",
    mode: "account",
    deviceId: "an3-local",
    peers: [{deviceId: "an3-remote", mode: "account", state: "connecting", accountVerified: false}],
  };
  const account = {
    state: {user: {id: 101, name: "test101"}},
    async load() { return this.state.user; },
    async proof() { return "local-proof"; },
    async verify() { return true; },
  };
  const unverified = loadSync(calls, status, {
    native_sync_account_context: {peerId: "an3-remote", challenge: "challenge", remoteProof: "", accountVerified: false},
    native_sync_set_account_proof: {},
  }, account);
  unverified.setMode("account");
  assert.equal(await unverified.authenticateAccount(), false);
  assert.equal(calls.some(call => call.name === "native_sync_mark_account_verified"), false);

  const verifiedCalls = [];
  const verified = loadSync(verifiedCalls, status, {
    native_sync_account_context: {peerId: "an3-remote", challenge: "challenge", remoteProof: "remote-proof", accountVerified: false},
    native_sync_set_account_proof: {},
    native_sync_mark_account_verified: {},
  }, account);
  verified.setMode("account");
  assert.equal(await verified.authenticateAccount(), true);
  assert.equal(verifiedCalls.at(-1).name, "native_sync_mark_account_verified");
});
