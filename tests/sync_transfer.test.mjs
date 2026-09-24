import assert from "node:assert/strict";
import {createHash, webcrypto} from "node:crypto";
import {readFile} from "node:fs/promises";
import {test} from "node:test";
import vm from "node:vm";

const source = await readFile(new URL("../static/sync-transfer.js", import.meta.url), "utf8");

const loadTransfer = ({cryptoValue = webcrypto, localStorageValue = null} = {}) => {
  const context = {
    ArrayBuffer,
    Blob,
    Map,
    Set,
    Uint32Array,
    Uint8Array,
    crypto: cryptoValue,
    atob: value => Buffer.from(value, "base64").toString("binary"),
    console,
  };
  if (localStorageValue) context.localStorage = localStorageValue;
  context.globalThis = context;
  vm.runInNewContext(source, context, {filename: "sync-transfer.js"});
  return context.AN3SyncTransfer;
};

const response = (payload, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  async json() { return payload; },
  async arrayBuffer() { return payload; },
});

const sha256 = bytes => createHash("sha256").update(bytes).digest("hex");

const makeGameManager = (initialBytes, companionFiles = {}) => {
  const files = new Map([["/data", null], ["/data/saves", null]]);
  let current = initialBytes;
  let syncCount = 0;
  let loadCount = 0;
  const path = "/data/saves/emerald.srm";
  for (const [memberPath, bytes] of Object.entries(companionFiles)) files.set(memberPath, new Uint8Array(bytes));
  const manager = {
    FS: {
      analyzePath(candidate) { return {exists: files.has(candidate)}; },
      mkdir(candidate) { files.set(candidate, null); },
      writeFile(candidate, bytes) { files.set(candidate, new Uint8Array(bytes)); },
      readFile(candidate) {
        if (!files.has(candidate) || !files.get(candidate)) throw new Error("missing file");
        return new Uint8Array(files.get(candidate));
      },
      readdir(directory) {
        const prefix = directory.endsWith("/") ? directory : `${directory}/`;
        const entries = new Set();
        for (const candidate of files.keys()) {
          if (!candidate.startsWith(prefix)) continue;
          const suffix = candidate.slice(prefix.length);
          if (suffix && !suffix.includes("/")) entries.add(suffix);
        }
        return [".", "..", ...entries];
      },
      stat(candidate) { return {mode: files.get(candidate) === null ? "dir" : "file"}; },
      isDir(mode) { return mode === "dir"; },
      unlink(candidate) { files.delete(candidate); },
      syncfs(_populate, callback) { syncCount += 1; callback(null); },
    },
    getSaveFilePath() { return path; },
    saveSaveFiles() {},
    getSaveFile() { return current; },
    loadSaveFiles() {
      loadCount += 1;
      const saved = files.get(path);
      if (saved) current = new Uint8Array(saved);
    },
    inspect() { return {current, files, syncCount, loadCount, path}; },
  };
  return manager;
};

test("digestBytes keeps SHA-256 verification on an insecure LAN origin", async () => {
  const transfer = loadTransfer({cryptoValue: undefined});
  const bytes = new Uint8Array(Buffer.from("android-lan-save"));
  assert.equal(await transfer.digestBytes(bytes), sha256(bytes));
});

test("restoreGameSave rehydrates an empty EmulatorJS save from its verified local backup", async () => {
  const values = new Map();
  const localStorageValue = {
    getItem(key) { return values.get(key) ?? null; },
    setItem(key, value) { values.set(key, String(value)); },
  };
  const transfer = loadTransfer({localStorageValue});
  const identity = {core: "mgba", gameId: "emerald", romHash: "d".repeat(64)};
  const bytes = new Uint8Array(Buffer.from("persisted-browser-save"));
  const sourceManager = makeGameManager(bytes);
  await transfer.gameSaveStorage({manager: sourceManager, identity}).readAll();

  const targetManager = makeGameManager(null);
  assert.equal(await transfer.restoreGameSave({manager: targetManager, identity}), true);
  assert.deepEqual(new Uint8Array(targetManager.inspect().current), bytes);
  assert.equal(targetManager.inspect().syncCount, 1);
  assert.equal(targetManager.inspect().loadCount, 1);
  assert.equal(await transfer.restoreGameSave({manager: targetManager, identity}), false);
});

test("syncState publishes and downloads raw save-state bytes", async () => {
  const transfer = loadTransfer();
  const localBytes = new Uint8Array(Buffer.from("local-state"));
  const remoteBytes = new Uint8Array(Buffer.from("remote-state"));
  const remoteHash = sha256(remoteBytes);
  const writes = [];
  const published = [];
  const storage = {
    async readAll() {
      return [{id: "gba/emerald:slot:1", state: new Blob([localBytes]), updatedAt: 10}];
    },
    async put(record) { writes.push(record); },
  };
  const fetcher = async (url, options = {}) => {
    if (url === "/api/sync/lan/manifest?kind=state") {
      return response({items: [{key: "gba/remote:slot:1", contentHash: remoteHash, size: remoteBytes.byteLength, deviceId: "device-remote"}]});
    }
    if (url === "/api/sync/plan") {
      const records = JSON.parse(options.body).records;
      return response({transfers: records.map(record => ({
        key: record.key,
        kind: "state",
        direction: record.local ? "upload" : "download",
        reason: record.local ? "local-only" : "remote-only",
      }))});
    }
    if (url === "/api/sync/lan/publish") {
      published.push(JSON.parse(options.body));
      return response({ok: true, stored: 1});
    }
    if (url.startsWith("/api/sync/lan/blob?")) return response(remoteBytes.buffer);
    throw new Error(`unexpected request: ${url}`);
  };

  const result = await transfer.syncState({
    deviceId: "device-local",
    mode: "lan",
    storage,
    fetch: fetcher,
  });

  assert.equal(result.counts.uploaded, 1);
  assert.equal(result.counts.downloaded, 1);
  assert.equal(result.counts.conflicts, 0);
  assert.equal(published.length, 1);
  const sent = Buffer.from(published[0].items[0].data, "base64");
  assert.deepEqual(sent, Buffer.from(localBytes));
  assert.equal(writes.length, 1);
  assert.equal(writes[0].id, "gba/remote:slot:1");
  assert.deepEqual(new Uint8Array(await writes[0].state.arrayBuffer()), remoteBytes);
});

test("direct peer state manifests preserve the native blob path", async () => {
  const transfer = loadTransfer();
  const remoteBytes = new Uint8Array(Buffer.from("native-peer-state"));
  const remoteKey = "state:mgba:emerald:" + "a".repeat(64) + ":slot1";
  const calls = [];
  const writes = [];
  const storage = {
    async readAll() { return []; },
    async put(record) { writes.push(record); },
  };
  const transport = {
    development: false,
    async sameAccount() { return true; },
    async manifest() {
      return {items: [{
        key: remoteKey,
        path: "/data/states/slot1",
        contentHash: sha256(remoteBytes),
        size: remoteBytes.byteLength,
        deviceId: "peer-1234",
      }]};
    },
    async plan() { return {transfers: [{key: remoteKey, direction: "download"}]}; },
    async blob(kind, item) {
      calls.push({kind, item});
      return remoteBytes;
    },
    async publish() {},
    async resolve() {},
  };
  await transfer.syncState({
    transport,
    storage,
    identity: {core: "mgba", gameId: "emerald", romHash: "a".repeat(64)},
    deviceId: "device-local",
    context: {kind: "state"},
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].kind, "state");
  assert.equal(calls[0].item.path, "/data/states/slot1");
  assert.equal(writes.length, 1);
});

test("resolveConflict keep-both preserves local bytes and installs verified remote bytes", async () => {
  const transfer = loadTransfer();
  const localBytes = new Uint8Array(Buffer.from("local-conflict"));
  const remoteBytes = new Uint8Array(Buffer.from("remote-conflict"));
  const writes = [];
  const published = [];
  const local = {key: "gba/emerald:slot:1", bytes: localBytes, contentHash: sha256(localBytes), size: localBytes.byteLength};
  const remote = {key: local.key, contentHash: sha256(remoteBytes), size: remoteBytes.byteLength, deviceId: "device-remote"};
  const storage = {async put(record) { writes.push(record); }};
  const fetcher = async (url, options = {}) => {
    if (url === "/api/sync/resolve") return response({direction: "upload", copyKey: local.key + ".conflict"});
    if (url === "/api/sync/lan/publish") { published.push(JSON.parse(options.body)); return response({ok: true, stored: 1}); }
    if (url.startsWith("/api/sync/lan/blob?")) return response(remoteBytes.buffer);
    throw new Error(`unexpected request: ${url}`);
  };

  await transfer.resolveConflict({
    conflict: {key: local.key, local, remote, copyKey: local.key + ".conflict"},
    resolution: "both",
    deviceId: "device-local",
    storage,
    fetch: fetcher,
  });

  assert.equal(published[0].items[0].key, local.key + ".conflict");
  assert.equal(writes.length, 2);
  assert.equal(writes[0].id, local.key + ".conflict");
  assert.equal(writes[1].id, local.key);
  assert.deepEqual(new Uint8Array(await writes[0].state.arrayBuffer()), localBytes);
  assert.deepEqual(new Uint8Array(await writes[1].state.arrayBuffer()), remoteBytes);
});

test("syncSave transfers EmulatorJS save bytes into the real IDBFS adapter", async () => {
  const transfer = loadTransfer();
  const identity = {core: "mgba", gameId: "emerald", romHash: "a".repeat(64)};
  const localBytes = new Uint8Array(Buffer.from("browser-a-save"));
  const remoteBytes = new Uint8Array(Buffer.from("browser-b-save"));
  const remoteHash = sha256(remoteBytes);
  const managerA = makeGameManager(localBytes);
  const managerB = makeGameManager(null);
  const published = [];
  let serverItem = null;
  const fetcher = async (url, options = {}) => {
    if (url === "/api/sync/lan/manifest?kind=save") {
      return response({items: serverItem ? [serverItem] : []});
    }
    if (url === "/api/sync/plan") {
      const records = JSON.parse(options.body).records;
      return response({transfers: records.map(record => ({
        key: record.key,
        kind: "save",
        direction: record.local ? "upload" : "download",
      }))});
    }
    if (url === "/api/sync/lan/publish") {
      const payload = JSON.parse(options.body);
      const item = payload.items[0];
      const bytes = new Uint8Array(Buffer.from(item.data, "base64"));
      published.push(payload);
      serverItem = {key: item.key, contentHash: item.contentHash, size: bytes.byteLength, deviceId: payload.deviceId};
      return response({ok: true, stored: 1});
    }
    if (url.startsWith("/api/sync/lan/blob?")) return response(remoteBytes.buffer);
    throw new Error(`unexpected request: ${url}`);
  };

  const uploaded = await transfer.syncSave({deviceId: "device-local", mode: "lan", manager: managerA, identity, fetch: fetcher});
  assert.equal(uploaded.counts.uploaded, 1);
  assert.equal(published[0].kind, "save");
  assert.match(published[0].items[0].key, /^save:mgba:emerald:/);
  assert.ok(published[0].items[0].key.includes(identity.romHash));
  assert.match(published[0].items[0].key, /:emerald\.srm$/);

  serverItem = {key: transfer.saveArtifactKey(identity, managerA.inspect().path), contentHash: remoteHash, size: remoteBytes.byteLength, deviceId: "device-remote"};
  const downloaded = await transfer.syncSave({deviceId: "device-remote", mode: "lan", manager: managerB, identity, fetch: fetcher});
  assert.equal(downloaded.counts.downloaded, 1);
  assert.deepEqual(new Uint8Array(managerB.inspect().current), remoteBytes);
  assert.deepEqual(new Uint8Array(managerB.inspect().files.get(managerB.inspect().path)), remoteBytes);
  assert.equal(managerB.inspect().syncCount, 1);
  assert.equal(managerB.inspect().loadCount, 1);
});

test("save-set manifests are deterministic and preserve member identity", async () => {
  const transfer = loadTransfer();
  const identity = {core: "mgba", gameId: "emerald", romHash: "e".repeat(64)};
  const primary = new Uint8Array(Buffer.from("primary-save"));
  const companion = new Uint8Array(Buffer.from("rtc-companion"));
  const first = await transfer.buildSaveSet(identity, [
    {path: "/data/saves/emerald.rtc", bytes: companion},
    {path: "/data/saves/emerald.srm", bytes: primary},
  ]);
  const second = await transfer.buildSaveSet(identity, [
    {path: "/data/saves/emerald.srm", bytes: primary},
    {path: "/data/saves/emerald.rtc", bytes: companion},
  ]);
  assert.equal(first.setId, `save:mgba:emerald:${identity.romHash}`);
  assert.deepEqual(Array.from(first.members, member => member.memberId), ["emerald.rtc", "emerald.srm"]);
  assert.equal(first.totalSize, primary.byteLength + companion.byteLength);
  assert.equal(first.memberCount, 2);
  assert.equal(first.manifestHash, second.manifestHash);
  assert.equal(first.members[0].key, `${first.setId}:emerald.rtc`);
});

test("multi-member save downloads validate the complete set before persistence", async () => {
  const transfer = loadTransfer();
  const identity = {core: "mgba", gameId: "emerald", romHash: "f".repeat(64)};
  const localPrimary = new Uint8Array(Buffer.from("old-primary"));
  const localCompanion = new Uint8Array(Buffer.from("old-companion"));
  const remotePrimary = new Uint8Array(Buffer.from("new-primary"));
  const remoteCompanion = new Uint8Array(Buffer.from("new-companion"));
  const manager = makeGameManager(localPrimary, {"/data/saves/emerald.rtc": localCompanion});
  const transferApi = loadTransfer();
  const remoteSet = await transferApi.buildSaveSet(identity, [
    {path: "/data/saves/emerald.srm", bytes: remotePrimary},
    {path: "/data/saves/emerald.rtc", bytes: remoteCompanion},
  ]);
  const publicSet = {
    ...remoteSet,
    members: remoteSet.members.map(({bytes, ...member}) => member),
  };
  const fetcher = async (url, options = {}) => {
    if (url === "/api/sync/lan/manifest?kind=save") return response({sets: [publicSet], items: []});
    if (url === "/api/sync/plan") return response({transfers: [{key: remoteSet.setId, direction: "download"}]});
    if (url.startsWith("/api/sync/lan/blob?")) {
      const key = decodeURIComponent(url.match(/key=([^&]+)/)[1]);
      const member = remoteSet.members.find(item => item.key === key);
      return response(member.bytes.buffer);
    }
    throw new Error(`unexpected request: ${url} ${JSON.stringify(options)}`);
  };
  const result = await transferApi.syncSave({deviceId: "device-local", mode: "lan", manager, identity, fetch: fetcher});
  assert.equal(result.counts.downloaded, 1);
  assert.deepEqual(new Uint8Array(manager.inspect().files.get("/data/saves/emerald.srm")), remotePrimary);
  assert.deepEqual(new Uint8Array(manager.inspect().files.get("/data/saves/emerald.rtc")), remoteCompanion);
  assert.equal(manager.inspect().syncCount, 1);
  assert.equal(manager.inspect().loadCount, 1);
});

test("multi-member save failure leaves every previous member untouched", async () => {
  const transfer = loadTransfer();
  const identity = {core: "mgba", gameId: "emerald", romHash: "1".repeat(64)};
  const originalPrimary = new Uint8Array(Buffer.from("keep-primary"));
  const originalCompanion = new Uint8Array(Buffer.from("keep-companion"));
  const remotePrimary = new Uint8Array(Buffer.from("incoming-primary"));
  const remoteCompanion = new Uint8Array(Buffer.from("incoming-companion"));
  const manager = makeGameManager(originalPrimary, {"/data/saves/emerald.rtc": originalCompanion});
  const remoteSet = await transfer.buildSaveSet(identity, [
    {path: "/data/saves/emerald.srm", bytes: remotePrimary},
    {path: "/data/saves/emerald.rtc", bytes: remoteCompanion},
  ]);
  const publicSet = {...remoteSet, members: remoteSet.members.map(({bytes, ...member}) => member)};
  const fetcher = async url => {
    if (url === "/api/sync/lan/manifest?kind=save") return response({sets: [publicSet], items: []});
    if (url === "/api/sync/plan") return response({transfers: [{key: remoteSet.setId, direction: "download"}]});
    if (url.startsWith("/api/sync/lan/blob?")) {
      const key = decodeURIComponent(url.match(/key=([^&]+)/)[1]);
      const member = remoteSet.members.find(item => item.key === key);
      return response(key.endsWith(".rtc") ? new Uint8Array(Buffer.from("tampered")) .buffer : member.bytes.buffer);
    }
    throw new Error(`unexpected request: ${url}`);
  };
  await assert.rejects(
    transfer.syncSave({deviceId: "device-local", mode: "lan", manager, identity, fetch: fetcher}),
    /hash verification/,
  );
  assert.deepEqual(new Uint8Array(manager.inspect().current), originalPrimary);
  assert.deepEqual(new Uint8Array(manager.inspect().files.get("/data/saves/emerald.rtc")), originalCompanion);
  assert.equal(manager.inspect().syncCount, 0);
  assert.equal(manager.inspect().loadCount, 0);
});

test("save-set conflicts resolve once for the logical set and keep both safely", async () => {
  const transfer = loadTransfer();
  const identity = {core: "mgba", gameId: "emerald", romHash: "3".repeat(64)};
  const localPrimary = new Uint8Array(Buffer.from("local-primary"));
  const localCompanion = new Uint8Array(Buffer.from("local-companion"));
  const remotePrimary = new Uint8Array(Buffer.from("remote-primary"));
  const remoteCompanion = new Uint8Array(Buffer.from("remote-companion"));
  const manager = makeGameManager(localPrimary, {"/data/saves/emerald.rtc": localCompanion});
  const localSet = await transfer.buildSaveSet(identity, [
    {path: "/data/saves/emerald.srm", bytes: localPrimary},
    {path: "/data/saves/emerald.rtc", bytes: localCompanion},
  ]);
  const remoteSet = await transfer.buildSaveSet(identity, [
    {path: "/data/saves/emerald.srm", bytes: remotePrimary},
    {path: "/data/saves/emerald.rtc", bytes: remoteCompanion},
  ]);
  const published = [];
  const fetcher = async (url, options = {}) => {
    if (url === "/api/sync/resolve") return response({direction: "upload", copyKey: `${localSet.setId}.conflict`});
    if (url === "/api/sync/lan/publish") {
      published.push(JSON.parse(options.body));
      return response({ok: true, stored: 2});
    }
    if (url.startsWith("/api/sync/lan/blob?")) {
      const key = decodeURIComponent(url.match(/key=([^&]+)/)[1]);
      return response(remoteSet.members.find(item => item.key === key).bytes.buffer);
    }
    throw new Error(`unexpected request: ${url}`);
  };
  await transfer.resolveConflict({
    conflict: {key: localSet.setId, setId: localSet.setId, local: localSet, remote: remoteSet, copyKey: `${localSet.setId}.conflict`},
    kind: "save",
    resolution: "both",
    deviceId: "device-local",
    manager,
    identity,
    fetch: fetcher,
  });
  assert.equal(published.length, 1);
  assert.equal(published[0].set.setId, `${localSet.setId}.conflict`);
  assert.deepEqual(new Uint8Array(manager.inspect().current), remotePrimary);
  assert.deepEqual(new Uint8Array(manager.inspect().files.get("/data/saves/emerald.rtc")), remoteCompanion);
  assert.deepEqual(new Uint8Array(manager.inspect().files.get(`/data/saves/emerald.srm.an3-conflict-${localSet.manifestHash.slice(0, 16)}`)), localPrimary);
  assert.deepEqual(new Uint8Array(manager.inspect().files.get(`/data/saves/emerald.rtc.an3-conflict-${localSet.manifestHash.slice(0, 16)}`)), localCompanion);
  assert.equal(manager.inspect().syncCount, 1);
  assert.equal(manager.inspect().loadCount, 1);
});

test("save-set validation rejects missing, unexpected, duplicate, hash, and size members", async () => {
  const transfer = loadTransfer();
  const identity = {core: "mgba", gameId: "emerald", romHash: "2".repeat(64)};
  const base = await transfer.buildSaveSet(identity, [
    {path: "/data/saves/emerald.rtc", bytes: new Uint8Array(Buffer.from("rtc"))},
    {path: "/data/saves/emerald.srm", bytes: new Uint8Array(Buffer.from("srm"))},
  ]);
  const publicSet = set => ({...set, members: set.members.map(({bytes, ...member}) => member)});
  const invalid = [
    {...publicSet(base), members: [publicSet(base).members[0]]},
    {...publicSet(base), members: [publicSet(base).members[0], publicSet(base).members[0]]},
    {...publicSet(base), members: publicSet(base).members.map((member, index) => index ? {...member, contentHash: "0".repeat(64)} : member)},
    {...publicSet(base), members: publicSet(base).members.map((member, index) => index ? {...member, size: member.size + 1} : member)},
    {...publicSet(base), members: [...publicSet(base).members, {key: `${base.setId}:unexpected`, memberId: "unexpected.sav", path: "/data/saves/unexpected.sav", size: 1, contentHash: "3".repeat(64)}]},
  ];
  for (const candidate of invalid) await assert.rejects(transfer.validateSaveSet(candidate, identity));
});

test("syncSave refuses hash-mismatched bytes before EmulatorJS persistence", async () => {
  const transfer = loadTransfer();
  const identity = {core: "mgba", gameId: "emerald", romHash: "b".repeat(64)};
  const original = new Uint8Array(Buffer.from("untouched-save"));
  const manager = makeGameManager(original);
  const declared = new Uint8Array(Buffer.from("declared-bytes"));
  const wrong = new Uint8Array(Buffer.from("tampered-bytes"));
  const key = transfer.saveArtifactKey(identity, manager.inspect().path);
  const fetcher = async (url, options = {}) => {
    if (url === "/api/sync/lan/manifest?kind=save") return response({items: [{key, contentHash: sha256(declared), size: declared.byteLength, deviceId: "device-remote"}]});
    if (url === "/api/sync/plan") return response({transfers: [{key, kind: "save", direction: "download"}]});
    if (url.startsWith("/api/sync/lan/blob?")) return response(wrong.buffer);
    throw new Error(`unexpected request: ${url}`);
  };
  await assert.rejects(
    transfer.syncSave({deviceId: "device-local", mode: "lan", manager, identity, fetch: fetcher}),
    /failed hash verification/,
  );
  assert.deepEqual(new Uint8Array(manager.inspect().current), original);
  assert.equal(manager.inspect().syncCount, 0);
  assert.equal(manager.inspect().loadCount, 0);
});

test("generic save conflicts support local, remote, and both without crossing identities", async () => {
  const transfer = loadTransfer();
  const identity = {core: "mgba", gameId: "emerald", romHash: "c".repeat(64)};
  const localBytes = new Uint8Array(Buffer.from("local-save"));
  const remoteBytes = new Uint8Array(Buffer.from("remote-save"));
  const manager = makeGameManager(localBytes);
  const key = transfer.saveArtifactKey(identity, manager.inspect().path);
  const local = {key, bytes: localBytes, contentHash: sha256(localBytes), size: localBytes.byteLength};
  const remote = {key, contentHash: sha256(remoteBytes), size: remoteBytes.byteLength, deviceId: "device-remote"};
  const published = [];
  const fetcher = async (url, options = {}) => {
    if (url === "/api/sync/resolve") return response({direction: "upload", copyKey: key + ".conflict"});
    if (url === "/api/sync/lan/publish") { published.push(JSON.parse(options.body)); return response({ok: true, stored: 1}); }
    if (url.startsWith("/api/sync/lan/blob?")) return response(remoteBytes.buffer);
    throw new Error(`unexpected request: ${url}`);
  };

  await transfer.resolveConflict({conflict: {key, kind: "save", local, remote}, kind: "save", resolution: "local", deviceId: "device-local", manager, identity, fetch: fetcher});
  assert.equal(published.at(-1).items[0].key, key);

  await transfer.resolveConflict({conflict: {key, kind: "save", local, remote}, kind: "save", resolution: "remote", deviceId: "device-local", manager, identity, fetch: fetcher});
  assert.deepEqual(new Uint8Array(manager.inspect().current), remoteBytes);

  const managerBoth = makeGameManager(localBytes);
  await transfer.resolveConflict({conflict: {key, kind: "save", local, remote}, kind: "save", resolution: "both", deviceId: "device-local", manager: managerBoth, identity, fetch: fetcher});
  const files = managerBoth.inspect().files;
  const conflictFiles = [...files.entries()].filter(([name]) => name.includes(".an3-conflict-"));
  assert.equal(conflictFiles.length, 1);
  assert.deepEqual(new Uint8Array(conflictFiles[0][1]), localBytes);
  assert.deepEqual(new Uint8Array(files.get(managerBoth.inspect().path)), remoteBytes);
  assert.ok(published.at(-1).items[0].key.endsWith(".conflict"));
});

test("direct LAN transport carries sync payloads without an HTTP fallback", async () => {
  const transfer = loadTransfer();
  const localBytes = new Uint8Array(Buffer.from("direct-peer-state"));
  const sent = [];
  let manifestCalls = 0;
  const storage = {
    async readAll() {
      return [{id: "gba/emerald:slot:direct", state: new Blob([localBytes]), updatedAt: 10}];
    },
    async put() {},
  };
  const transport = {
    async sameAccount(context) {
      assert.equal(context.capability, "sync");
      return true;
    },
    async manifest() {
      manifestCalls += 1;
      return {items: []};
    },
    async plan(payload) {
      assert.equal(payload.kind, "state");
      return {transfers: [{key: payload.records[0].key, direction: "upload"}]};
    },
    async publish(payload) { sent.push(payload); return {ok: true}; },
    async blob() { throw new Error("blob must not be requested for an upload"); },
    async resolve() { return {direction: "upload"}; },
  };
  const result = await transfer.syncState({deviceId: "device-local", mode: "lan", storage, transport});
  assert.equal(result.counts.uploaded, 1);
  assert.equal(manifestCalls, 1);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].kind, "state");
  assert.deepEqual(new Uint8Array(Buffer.from(sent[0].items[0].data, "base64")), localBytes);
});

test("direct LAN sync refuses a peer without same-account proof before reading data", async () => {
  const transfer = loadTransfer();
  let manifestCalls = 0;
  const transport = {
    async sameAccount() { return false; },
    async manifest() { manifestCalls += 1; return {items: []}; },
    async plan() { throw new Error("plan must not run"); },
    async publish() { throw new Error("publish must not run"); },
    async blob() { throw new Error("blob must not run"); },
    async resolve() { throw new Error("resolve must not run"); },
  };
  await assert.rejects(
    transfer.syncState({deviceId: "device-local", mode: "lan", storage: {async readAll() { return []; }}, transport}),
    /account/,
  );
  assert.equal(manifestCalls, 0);
});
