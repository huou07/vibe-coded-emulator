// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
import assert from "node:assert/strict";
import {createHash, webcrypto} from "node:crypto";
import {readFile} from "node:fs/promises";
import {test} from "node:test";
import vm from "node:vm";

const source = await readFile(new URL("../static/local-save-recovery.js", import.meta.url), "utf8");
const savePath = "/data/saves/game.srm";
const romHash = "a".repeat(64);
const key = `save:mgba:emerald:${romHash}:game.srm`;
const storageKey = "vibe-sync-save-backup-v1:" + encodeURIComponent(key);
const bytes = Uint8Array.from([1, 2, 3, 4]);
const hash = value => createHash("sha256").update(value).digest("hex");

const loadRecovery = (backup = null) => {
  const values = new Map();
  if (backup) values.set(storageKey, JSON.stringify(backup));
  const sandbox = {
    Uint8Array,
    ArrayBuffer,
    Promise,
    JSON,
    String,
    Number,
    Math,
    encodeURIComponent,
    crypto: webcrypto,
    atob: value => Buffer.from(value, "base64").toString("binary"),
    localStorage: {
      getItem: name => values.get(name) || null,
      setItem: (name, value) => values.set(name, String(value)),
    },
  };
  sandbox.globalThis = sandbox;
  vm.runInNewContext(source, sandbox, {filename: "local-save-recovery.js"});
  return sandbox.AN3LocalSaveRecovery;
};

const makeManager = (initial = null) => {
  const files = new Map();
  if (initial) files.set(savePath, Uint8Array.from(initial));
  const writes = [];
  let saveLoads = 0;
  const directories = new Set();
  return {
    files,
    writes,
    get saveLoads() { return saveLoads; },
    getSaveFilePath: () => savePath,
    getSaveFile: () => files.get(savePath) || null,
    loadSaveFiles: () => { saveLoads += 1; },
    FS: {
      analyzePath: path => ({exists: directories.has(path)}),
      mkdir: path => directories.add(path),
      writeFile(path, value) { writes.push(path); files.set(path, Uint8Array.from(value)); },
      syncfs(_populate, callback) { callback(null); },
    },
  };
};

const makeBackup = data => ({
  version: 1,
  key,
  contentHash: hash(data),
  size: data.byteLength,
  data: Buffer.from(data).toString("base64"),
});

test("restores a verified legacy save backup only when the local save is empty", async () => {
  const manager = makeManager();
  const restored = await loadRecovery(makeBackup(bytes)).restore({
    manager,
    identity: {core: "mgba", gameId: "emerald", romHash},
  });

  assert.equal(restored, true);
  assert.deepEqual([...manager.files.get(savePath)], [...bytes]);
  assert.deepEqual(manager.writes, [savePath]);
  assert.equal(manager.saveLoads, 1);
});

test("keeps an existing local save without writing the legacy backup", async () => {
  const existing = Uint8Array.from([9, 8, 7]);
  const manager = makeManager(existing);
  const restored = await loadRecovery(makeBackup(bytes)).restore({
    manager,
    identity: {core: "mgba", gameId: "emerald", romHash},
  });

  assert.equal(restored, false);
  assert.deepEqual([...manager.files.get(savePath)], [...existing]);
  assert.deepEqual(manager.writes, []);
});

test("rejects a corrupt legacy backup and an unsafe core-selected path", async () => {
  const corrupt = {...makeBackup(bytes), contentHash: "0".repeat(64)};
  const manager = makeManager();
  assert.equal(await loadRecovery(corrupt).restore({
    manager,
    identity: {core: "mgba", gameId: "emerald", romHash},
  }), false);
  assert.deepEqual(manager.writes, []);

  manager.getSaveFilePath = () => "/data/saves/../outside.srm";
  await assert.rejects(() => loadRecovery(makeBackup(bytes)).restore({
    manager,
    identity: {core: "mgba", gameId: "emerald", romHash},
  }), /unsafe save-file path/);
  assert.deepEqual(manager.writes, []);
});
