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

test("foreground reconnect is opt-in during initialization", async () => {
  const calls = [];
  const sync = loadSync(calls, {
    running: true,
    role: "host",
    mode: "guest",
    deviceId: "an3-local",
    code: "123456",
    peers: [{deviceId: "an3-remote", state: "offline", mode: "guest"}],
    error: "",
  }, {
    native_sync_start: {
      running: true,
      role: "host",
      mode: "guest",
      deviceId: "an3-local",
      code: "123456",
      peers: [{deviceId: "an3-remote", state: "offline", mode: "guest"}],
      error: "",
    },
  });
  await sync.init();
  assert.equal(calls.some(call => call.name === "native_sync_join"), false);
  sync.setBackgroundEnabled(true);
  await sync.init();
  assert.equal(calls.some(call => call.name === "native_sync_join"), true);
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

test("native blob responses are adapted to transfer-engine bytes", async () => {
  const payload = Uint8Array.from([0, 1, 2, 250, 255]);
  const encoded = Buffer.from(payload).toString("base64");
  const calls = [];
  const sync = loadSync(calls, null, {
    native_sync_request: {data: encoded, size: payload.byteLength, contentHash: "ignored-by-adapter"},
  });
  const bytes = await sync.transport.blob("save", {key: "save:key", path: "/data/saves/key", size: payload.byteLength, contentHash: "hash"}, null);
  assert.deepEqual([...bytes], [...payload]);
  assert.equal(calls.at(-1).name, "native_sync_request");
  assert.equal(calls.at(-1).args.method, "blob");
});

test("syncGame fails fast without a connected peer and never hashes the ROM", async () => {
  const calls = [];
  const states = [];
  const sync = loadSync(calls, {running: true, role: "host", mode: "guest", deviceId: "an3-local", code: "123456", peers: [], error: ""});
  await assert.rejects(
    () => sync.syncGame("3ds", "11111111-1111-1111-1111-111111111111", "save", state => states.push(state)),
    /No LAN peer is connected/,
  );
  assert.deepEqual(states, ["checking-peer"]);
  assert.equal(
    calls.some(call => call.name === "native_sync_game_identity"),
    false,
    "the ROM must not be hashed before a peer exists",
  );
});

test("syncGame reports truthful states once a peer is connected", async () => {
  const calls = [];
  const states = [];
  const sync = loadSync(calls, {
    running: true,
    role: "host",
    mode: "guest",
    deviceId: "an3-local",
    code: "123456",
    peers: [{state: "connected", mode: "guest", deviceId: "an3-remote"}],
    error: "",
  });
  const result = await sync.syncGame("3ds", "11111111-1111-1111-1111-111111111111", "save", state => states.push(state));
  assert.deepEqual(states, ["checking-peer", "scanning", "syncing", "complete"]);
  assert.equal(calls.some(call => call.name === "native_sync_game_identity"), true);
  assert.equal(result.counts.uploaded, 0);
});

test("syncGame fails fast for a peer that is only still connecting", async () => {
  const calls = [];
  const sync = loadSync(calls, {
    running: true,
    role: "host",
    mode: "guest",
    deviceId: "an3-local",
    code: "123456",
    peers: [{state: "connecting", mode: "guest", deviceId: "an3-remote"}],
    error: "",
  });
  await assert.rejects(
    () => sync.syncGame("3ds", "11111111-1111-1111-1111-111111111111", "save", () => {}),
    /No LAN peer is connected/,
  );
  assert.equal(calls.some(call => call.name === "native_sync_game_identity"), false);
});

test("syncLibrary transfers chunked ROMs and leaves divergent identities as conflicts", async () => {
  const calls = [];
  const bytes = Uint8Array.from([1, 2, 3, 4]);
  const hash = "a".repeat(64);
  const item = {
    key: "rom:11111111-1111-1111-1111-111111111111",
    romId: "11111111-1111-1111-1111-111111111111",
    extension: "gba",
    system: "gba",
    name: "fixture.gba",
    size: bytes.byteLength,
    contentHash: hash,
  };
  let remoteManifestCalls = 0;
  const sync = loadSync(calls, {
    running: true,
    role: "host",
    mode: "guest",
    deviceId: "an3-local",
    peers: [{state: "connected", mode: "guest", deviceId: "an3-remote"}],
    error: "",
  }, {
    native_sync_library_manifest: {items: [item]},
    native_sync_library_read_chunk: {offset: 0, data: Buffer.from(bytes).toString("base64")},
    native_sync_request: args => {
      if (args.method === "library-manifest") { remoteManifestCalls += 1; return {items: []}; }
      if (args.method === "library-upload-status") return {complete: false, nextOffset: 0};
      if (args.method === "library-publish-chunk") return {complete: true, nextOffset: bytes.byteLength};
      throw new Error(`unexpected method ${args.method}`);
    },
  });
  const states = [];
  const result = await sync.syncLibrary({onState: state => states.push(state.phase)});
  assert.equal(remoteManifestCalls, 1);
  assert.equal(result.counts.uploaded, 1);
  assert.equal(result.counts.downloaded, 0);
  assert.equal(result.counts.conflicts, 0);
  assert.ok(states.includes("uploading"));
  assert.equal(calls.find(call => call.name === "native_sync_request" && call.args.method === "library-publish-chunk").args.payload.offset, 0);
});

test("syncLibrary cancellation stops before any ROM write", async () => {
  const calls = [];
  const sync = loadSync(calls, {
    running: true,
    role: "host",
    mode: "guest",
    deviceId: "an3-local",
    peers: [{state: "connected", mode: "guest", deviceId: "an3-remote"}],
    error: "",
  });
  const signal = {aborted: true};
  await assert.rejects(() => sync.syncLibrary({signal}), error => error.code === "ABORT_ERR");
  assert.equal(calls.some(call => call.name === "native_sync_library_write_chunk"), false);
});

test("syncLibrary can transfer one selected remote ROM without touching other library items", async () => {
  const calls = [];
  const bytes = Uint8Array.from([9, 8, 7, 6]);
  const item = {
    key: "rom:33333333-3333-3333-3333-333333333333",
    romId: "33333333-3333-3333-3333-333333333333",
    extension: "gba",
    system: "gba",
    name: "synthetic-homebrew.gba",
    size: bytes.byteLength,
    contentHash: "c".repeat(64),
  };
  const unrelated = {
    key: "rom:44444444-4444-4444-4444-444444444444",
    romId: "44444444-4444-4444-4444-444444444444",
    extension: "gba",
    system: "gba",
    name: "unselected-homebrew.gba",
    size: bytes.byteLength,
    contentHash: "d".repeat(64),
  };
  const sync = loadSync(calls, {
    running: true,
    role: "host",
    mode: "guest",
    deviceId: "an3-local",
    peers: [{state: "connected", mode: "guest", deviceId: "an3-remote"}],
    error: "",
  }, {
    native_sync_library_manifest: {items: []},
    native_sync_library_upload_status: {complete: false, nextOffset: 0},
    native_sync_library_write_chunk: {complete: true, nextOffset: bytes.byteLength},
    native_sync_request: args => {
      if (args.method === "library-manifest") return {items: [item, unrelated]};
      if (args.method === "library-blob") {
        assert.equal(args.payload.romId, item.romId);
        return {offset: args.payload.offset, data: Buffer.from(bytes).toString("base64")};
      }
      throw new Error(`unexpected method ${args.method}`);
    },
  });
  const states = [];
  const result = await sync.syncLibrary({keys: [item.key], onState: state => states.push(state.phase)});
  assert.equal(result.transfers.length, 1);
  assert.equal(result.transfers[0].key, item.key);
  assert.equal(result.transfers[0].direction, "download");
  assert.equal(result.counts.downloaded, 1);
  assert.equal(result.counts.uploaded, 0);
  assert.equal(result.counts.conflicts, 0);
  assert.ok(states.includes("downloading"));
  assert.ok(states.includes("complete"));
  assert.equal(calls.filter(call => call.name === "native_sync_library_write_chunk").length, 1);
  assert.equal(calls.some(call => call.name === "native_sync_library_read_chunk"), false);
  const gameIdentityCalls = calls.filter(call => call.name === "native_sync_game_identity");
  assert.equal(gameIdentityCalls.length, 2, "the selected ROM receives save and savestate passes");
  assert.ok(gameIdentityCalls.every(call => call.args.romId === item.romId));
});

test("syncLibrary rejects an absent selected key before writing ROM data", async () => {
  const calls = [];
  const sync = loadSync(calls, {
    running: true,
    role: "host",
    mode: "guest",
    deviceId: "an3-local",
    peers: [{state: "connected", mode: "guest", deviceId: "an3-remote"}],
    error: "",
  }, {
    native_sync_library_manifest: {items: []},
    native_sync_request: args => args.method === "library-manifest" ? {items: []} : {},
  });
  await assert.rejects(
    () => sync.syncLibrary({keys: ["rom:55555555-5555-5555-5555-555555555555"]}),
    /not present on either peer/,
  );
  assert.equal(calls.some(call => call.name === "native_sync_library_write_chunk"), false);
  assert.equal(calls.some(call => call.name === "native_sync_library_read_chunk"), false);
});

test("syncLibrary rejects malformed selected keys before network access", async () => {
  const calls = [];
  const sync = loadSync(calls);
  await assert.rejects(() => sync.syncLibrary({keys: ["../outside"]}), /invalid ROM key/);
  assert.equal(calls.length, 0);
});

test("syncLibrary treats a stable identity metadata change as a conflict", async () => {
  const calls = [];
  const item = {
    key: "rom:22222222-2222-2222-2222-222222222222",
    romId: "22222222-2222-2222-2222-222222222222",
    extension: "gba",
    system: "gba",
    name: "fixture.gba",
    size: 4,
    contentHash: "b".repeat(64),
  };
  const remote = {...item, extension: "raw", name: "fixture.raw"};
  const sync = loadSync(calls, {
    running: true,
    role: "host",
    mode: "guest",
    deviceId: "an3-local",
    peers: [{state: "connected", mode: "guest", deviceId: "an3-remote"}],
    error: "",
  }, {
    native_sync_library_manifest: {items: [item]},
    native_sync_request: args => {
      if (args.method === "library-manifest") return {items: [remote]};
      throw new Error(`unexpected method ${args.method}`);
    },
  });
  const result = await sync.syncLibrary();
  assert.equal(result.counts.conflicts, 1);
  assert.equal(result.transfers[0].direction, "conflict");
  assert.equal(calls.some(call => call.name === "native_sync_game_identity"), false);
});
