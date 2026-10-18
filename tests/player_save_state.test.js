// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Behavioral guards for the web player's save-state storage. These run the
// real `static/player-runtime.js` against an in-memory IndexedDB fake so the
// transaction semantics, the autosave/manual separation, the size cap and the
// autosave digest verification are exercised as code, not as source strings.
//
// The fake models the parts of IndexedDB the manager relies on: one object
// store keyed by `id`, per-transaction atomic commit, and injectable failures.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');

const runtime = fs.readFileSync('static/player-runtime.js', 'utf8');

// A minimal structured-clone stand-in: the manager only ever stores plain
// records whose `state` is a Blob, so a shallow copy is faithful here.
const clone = value => (value && typeof value === 'object' ? {...value} : value);

function createIndexedDbFake() {
  const databases = new Map();
  const state = {failNextPut: false, failNextOpen: false, putCount: 0};

  const makeRequest = () => {
    const request = {result: undefined, error: null, onsuccess: null, onerror: null, onupgradeneeded: null};
    return request;
  };

  const open = (name, version) => {
    const request = makeRequest();
    queueMicrotask(() => {
      if (state.failNextOpen) {
        state.failNextOpen = false;
        request.error = new Error('injected open failure');
        request.onerror?.();
        return;
      }
      let database = databases.get(name);
      if (!database) {
        database = {
          name,
          version,
          stores: new Map(),
          objectStoreNames: {contains: storeName => database.stores.has(storeName)},
          createObjectStore(storeName) {
            if (!database.stores.has(storeName)) database.stores.set(storeName, new Map());
            return {name: storeName};
          },
          close() {},
        };
        database.transaction = (storeName, mode) => transaction(database, storeName, mode);
        databases.set(name, database);
        request.result = database;
        request.onupgradeneeded?.();
      } else {
        request.result = database;
      }
      request.onsuccess?.();
    });
    return request;
  };

  const transaction = (database, storeName, mode) => {
    const store = database.stores.get(storeName) || new Map();
    database.stores.set(storeName, store);
    const tx = {error: null, oncomplete: null, onerror: null, onabort: null};
    const pending = [];
    const objectStore = {
      get: key => {
        const request = makeRequest();
        pending.push(() => {
          request.result = store.has(key) ? clone(store.get(key)) : undefined;
          request.onsuccess?.();
        });
        return request;
      },
      put: record => {
        const request = makeRequest();
        pending.push(() => {
          if (state.failNextPut) {
            state.failNextPut = false;
            tx.error = new Error('injected write failure');
            tx.onerror?.();
            return;
          }
          store.set(record.id, clone(record));
          state.putCount += 1;
          request.onsuccess?.();
        });
        return request;
      },
    };
    // Commit on a macrotask so callers can attach oncomplete/onerror first.
    setTimeout(() => {
      for (const step of pending) step();
      if (!tx.error) tx.oncomplete?.();
    }, 0);
    tx.objectStore = () => objectStore;
    return tx;
  };

  return {
    state,
    indexedDB: {open},
    transaction,
    databases,
  };
}

function loadRuntime(fake) {
  const context = {
    indexedDB: fake.indexedDB,
    crypto: globalThis.crypto,
    Blob,
    Uint8Array,
    Date,
    console,
  };
  vm.runInNewContext(runtime, context);
  return context.AN3PlayerRuntime;
}

const bytes = length => new Uint8Array(Array.from({length}, (_, index) => index & 0xff));

test('manual slots use the v1 key format and reject out-of-range slots', async () => {
  const fake = createIndexedDbFake();
  const api = loadRuntime(fake);
  const manager = new api.QuickSaveManager('pokemon-emerald');
  assert.equal(manager.id(1), 'pokemon-emerald:slot:1');
  assert.equal(manager.id(10), 'pokemon-emerald:slot:10');
  assert.equal(manager.autoId(), 'pokemon-emerald:auto');
  assert.throws(() => manager.id(0), /1 to 10/);
  assert.throws(() => manager.id(11), /1 to 10/);
  assert.throws(() => manager.id('auto'), /1 to 10/);
});

test('a manual slot round-trips byte-exact and a missing slot reads as null', async () => {
  const fake = createIndexedDbFake();
  const api = loadRuntime(fake);
  const manager = new api.QuickSaveManager('pokemon-emerald');
  const payload = bytes(64);
  await manager.put(3, payload, 1234);
  const saved = await manager.get(3);
  assert.equal(saved.updatedAt, 1234);
  assert.deepEqual(new Uint8Array(await saved.state.arrayBuffer()), payload);
  assert.equal(await manager.get(4), null);
});

test('autosave can never overwrite a manual Quick Save slot', async () => {
  const fake = createIndexedDbFake();
  const api = loadRuntime(fake);
  const manager = new api.QuickSaveManager('pokemon-emerald');
  const manual = bytes(32);
  const auto = bytes(48);
  await manager.put(1, manual, 100);
  await manager.putAuto(auto, 200, await api.stateDigest(auto));
  // The manual slot is untouched by the autosave write.
  const savedManual = await manager.get(1);
  assert.deepEqual(new Uint8Array(await savedManual.state.arrayBuffer()), manual);
  assert.equal(savedManual.updatedAt, 100);
  // And the autosave record is not addressable as a numbered slot.
  const savedAuto = await manager.getAuto();
  assert.deepEqual(new Uint8Array(await savedAuto.state.arrayBuffer()), auto);
  assert.equal(savedAuto.auto, true);
  assert.equal(await manager.get(2), null);
});

test('a failed write leaves the previous valid bytes in place', async () => {
  const fake = createIndexedDbFake();
  const api = loadRuntime(fake);
  const manager = new api.QuickSaveManager('pokemon-emerald');
  const original = bytes(16);
  await manager.put(2, original, 10);
  fake.state.failNextPut = true;
  await assert.rejects(() => manager.put(2, bytes(24), 20), /injected write failure/);
  const saved = await manager.get(2);
  assert.deepEqual(new Uint8Array(await saved.state.arrayBuffer()), original);
  assert.equal(saved.updatedAt, 10);
});

test('empty and oversize states are rejected before any write', async () => {
  const fake = createIndexedDbFake();
  const api = loadRuntime(fake);
  const manager = new api.QuickSaveManager('pokemon-emerald');
  await assert.rejects(() => manager.put(1, new Uint8Array(0)), /empty/);
  await assert.rejects(() => manager.putAuto(new Uint8Array(0)), /empty/);
  const oversize = {byteLength: api.MAX_STATE_BYTES + 1};
  await assert.rejects(() => manager.put(1, oversize), /64 MiB/);
  await assert.rejects(() => manager.putAuto(oversize), /64 MiB/);
  assert.equal(fake.state.putCount, 0);
});

test('autosave verification rejects a truncated or corrupted record', async () => {
  const fake = createIndexedDbFake();
  const api = loadRuntime(fake);
  const manager = new api.QuickSaveManager('pokemon-emerald');
  const payload = bytes(40);
  await manager.putAuto(payload, 1, await api.stateDigest(payload));
  const saved = await manager.getAuto();
  // The intact record verifies and returns the exact bytes.
  assert.deepEqual(await api.verifyAutoRecord(saved), payload);
  // A record whose bytes no longer match its stored digest is rejected.
  const corrupted = {...saved, state: new Blob([bytes(39)], {type: 'application/octet-stream'})};
  await assert.rejects(() => api.verifyAutoRecord(corrupted), /corrupted/);
  // A record with no bytes at all is rejected as unavailable.
  await assert.rejects(() => api.verifyAutoRecord({id: 'x'}), /unavailable/);
});

test('concurrent writes to different slots all commit', async () => {
  const fake = createIndexedDbFake();
  const api = loadRuntime(fake);
  const manager = new api.QuickSaveManager('pokemon-emerald');
  await Promise.all([1, 2, 3, 4, 5].map(slot => manager.put(slot, bytes(slot * 8), slot)));
  const states = await manager.getMany([1, 2, 3, 4, 5]);
  states.forEach((saved, index) => {
    assert.ok(saved, `slot ${index + 1} committed`);
    assert.equal(saved.updatedAt, index + 1);
  });
});

test('getMany resolves an aligned array and reports empty slots as null', async () => {
  const fake = createIndexedDbFake();
  const api = loadRuntime(fake);
  const manager = new api.QuickSaveManager('pokemon-emerald');
  await manager.put(2, bytes(8), 2);
  const states = await manager.getMany([1, 2, 3]);
  assert.equal(states.length, 3);
  assert.equal(states[0], null);
  assert.equal(states[1].updatedAt, 2);
  assert.equal(states[2], null);
});
