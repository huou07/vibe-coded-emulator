import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {test} from "node:test";
import vm from "node:vm";

const source = await readFile(new URL("../static/lan-peer.js", import.meta.url), "utf8");
const loadPeer = () => {
  const context = {Array, Map, Set, Object, Number, String, Error, Promise, console};
  context.globalThis = context;
  vm.runInNewContext(source, context, {filename: "lan-peer.js"});
  return context.AN3LanPeer;
};

const transport = () => ({
  manifest() {}, plan() {}, publish() {}, blob() {}, resolve() {},
});

test("discovery records contain only public peer metadata", () => {
  const peer = loadPeer();
  const record = peer.normalizeAdvertisement({
    service: "an3-peer", version: 1, id: "device-1234", port: 47832,
    capabilities: ["controller", "sync"], name: "Living room",
  });
  assert.deepEqual(record.capabilities, ["controller", "sync"]);
  assert.equal(record.deviceId, "device-1234");
  assert.throws(() => peer.normalizeAdvertisement({
    service: "an3-peer", version: 1, id: "device-1234", port: 47832,
    capabilities: ["sync"], email: "user@example.test",
  }), /credentials|account data/);
});

test("incompatible protocol and capability are rejected before a session", () => {
  const peer = loadPeer();
  assert.throws(() => peer.normalizeAdvertisement({
    service: "an3-peer", version: 2, id: "device-1234", port: 47832, capabilities: ["sync"],
  }), /incompatible/);
  assert.throws(() => peer.validateHandshake({
    service: "an3-peer", version: 1, id: "device-1234", port: 47832, capabilities: ["sync"],
  }, "controller"), /requested capability/);
});

test("sync engine adapters are explicit and cannot silently become HTTP", () => {
  const peer = loadPeer();
  const adapted = peer.asSyncTransport(transport());
  for (const method of ["manifest", "plan", "publish", "blob", "resolve", "discover", "close"]) {
    assert.equal(typeof adapted[method], "function");
  }
  assert.throws(() => peer.asSyncTransport({}), /missing/);
});
