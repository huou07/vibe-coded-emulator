import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {test} from "node:test";

const root = new URL("../", import.meta.url);
const read = path => readFile(new URL(path, root), "utf8");

test("installed client sources do not contain the personal LAN server", async () => {
  const paths = [
    "static/lan-peer.js",
    "static/sync-transfer.js",
    "static/sync.js",
    "static/player.js",
    "static/controller.js",
    "native-offline/web/native-bootstrap.js",
    "native-offline/web/native-app.js",
    "native-offline/src-tauri/src/lan_peer.rs",
    "native-offline/src-tauri/src/lan_host.rs",
    "native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/ControllerClient.kt",
  ];
  for (const path of paths) {
    assert.doesNotMatch(await read(path), /192\.168\.1\.(6|8)/, path);
  }
});

test("legacy HTTP LAN fixtures are opt-in development adapters", async () => {
  const sync = await read("static/sync-transfer.js");
  const syncPage = await read("static/sync.js");
  const controller = await read("static/controller.js");
  const player = await read("static/player.js");
  assert.match(syncPage, /AN3SyncDevAdapter/);
  assert.match(sync, /Direct LAN peer transport is unavailable/);
  assert.match(controller, /AN3ControllerDevAdapter/);
  assert.match(player, /AN3ControllerDevAdapter/);
  assert.doesNotMatch(await read("native-offline/web/native-bootstrap.js"), /api\/controller|api\/sync/);
});

test("production client sync requires an explicit same-account peer proof", async () => {
  const sync = await read("static/sync-transfer.js");
  assert.match(sync, /sameAccount/);
  assert.match(sync, /LAN peer is not verified for this AN3 account/);
  assert.match(await read("static/lan-peer.js"), /sameAccount/);
});
