const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const {test} = require("node:test");

const source = fs.readFileSync("static/player-runtime.js", "utf8");

class MemoryIndexedDB {
  constructor() {
    this.databases = new Map();
    this.abortNextWrite = false;
  }

  open(name) {
    const request = {};
    queueMicrotask(() => {
      let database = this.databases.get(name);
      const created = !database;
      if (!database) {
        database = {stores: new Map()};
        this.databases.set(name, database);
      }
      request.result = {
        objectStoreNames: {contains: storeName => database.stores.has(storeName)},
        createObjectStore: storeName => database.stores.set(storeName, new Map()),
        transaction: (storeName, mode) => {
          const records = database.stores.get(storeName);
          const pending = new Map();
          const transaction = {
            objectStore: () => ({
              get: key => {
                const result = records.get(key) || null;
                const readRequest = {result};
                queueMicrotask(() => readRequest.onsuccess?.({target: {result}}));
                return readRequest;
              },
              put: record => {
                pending.set(record.id, record);
                setImmediate(() => {
                  if (mode !== "readwrite") return;
                  if (this.abortNextWrite) {
                    this.abortNextWrite = false;
                    transaction.onabort?.({target: transaction});
                    return;
                  }
                  for (const [key, value] of pending) records.set(key, value);
                  transaction.oncomplete?.({target: transaction});
                });
              },
            }),
          };
          if (mode === "readonly") setImmediate(() => transaction.oncomplete?.({target: transaction}));
          return transaction;
        },
        close() {},
      };
      if (created) request.onupgradeneeded?.({target: request});
      request.onsuccess?.({target: request});
    });
    return request;
  }
}

function createManager() {
  const indexedDB = new MemoryIndexedDB();
  const context = {indexedDB, Blob, Uint8Array};
  vm.runInNewContext(source, context, {filename: "player-runtime.js"});
  return {indexedDB, Manager: context.AN3PlayerRuntime.QuickSaveManager};
}

async function savedBytes(record) {
  return [...new Uint8Array(await record.state.arrayBuffer())];
}

test("quick saves persist raw bytes in all ten stable slots", async () => {
  const {indexedDB, Manager} = createManager();
  const firstSession = new Manager("lawful-fixture");
  const expected = [];

  for (let slot = 1; slot <= 10; slot += 1) {
    const bytes = [slot, 255 - slot, 0];
    expected.push(bytes);
    await firstSession.put(slot, Uint8Array.from(bytes), slot * 1000);
  }

  assert.equal(indexedDB.databases.get("an3-arcade-save-slots").stores.get("states").size, 10);

  assert.throws(() => firstSession.id(0), /1 to 10/);
  assert.throws(() => firstSession.id(11), /1 to 10/);

  // A new manager represents a player restart while IndexedDB remains local.
  const afterRestart = new Manager("lawful-fixture");
  const records = await afterRestart.getMany([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  assert.deepEqual(await Promise.all(records.map(savedBytes)), expected);
  assert.deepEqual(records.map(record => record.updatedAt), [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000]);
  assert.equal(indexedDB.databases.size, 1);
});

test("autosave has a separate record and failed writes retain the previous bytes", async () => {
  const {indexedDB, Manager} = createManager();
  const manager = new Manager("lawful-fixture");
  await manager.put(1, Uint8Array.from([1, 2, 3]), 1000);
  await manager.putAuto(Uint8Array.from([4, 5, 6]), 2000, "first-digest");

  indexedDB.abortNextWrite = true;
  await assert.rejects(manager.putAuto(Uint8Array.from([7, 8, 9]), 3000, "second-digest"), /interrupted/);

  assert.deepEqual(await savedBytes(await manager.get(1)), [1, 2, 3]);
  const autosave = await manager.getAuto();
  assert.deepEqual(await savedBytes(autosave), [4, 5, 6]);
  assert.equal(autosave.digest, "first-digest");
});
