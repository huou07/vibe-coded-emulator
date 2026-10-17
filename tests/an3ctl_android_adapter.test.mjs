import { test } from "node:test";
import assert from "node:assert/strict";
import { AndroidAdapter } from "../tools/an3ctl/adapters/android.mjs";

function adapterWith(results) {
  const adapter = new AndroidAdapter(".");
  adapter.device = async () => "emulator-5554";
  adapter.adb = async (args) => {
    const result = results.shift();
    assert.ok(result, `unexpected adb call: ${args.join(" ")}`);
    return result;
  };
  return adapter;
}

test("Android ROM load reports app-private copy failures", async () => {
  const adapter = adapterWith([
    { code: 0, stdout: "pushed", stderr: "" },
    { code: 0, stdout: "", stderr: "" },
    { code: 1, stdout: "", stderr: "Permission denied" },
  ]);

  await assert.rejects(adapter.romLoad({ path: "/tmp/game.gba" }), /Could not copy the ROM into app storage/);
});

test("Android ROM load rejects a denied NativeGameActivity launch", async () => {
  const adapter = adapterWith([
    { code: 0, stdout: "pushed", stderr: "" },
    { code: 0, stdout: "", stderr: "" },
    { code: 0, stdout: "copied", stderr: "" },
    { code: 0, stdout: "Starting: Intent { cmp=space.an3tocom.offline/.NativeGameActivity }", stderr: "Permission Denial: not exported" },
  ]);

  await assert.rejects(adapter.romLoad({ path: "/tmp/game.gba" }), /Android rejected the game launch/);
});

test("Android ROM load succeeds only after NativeGameActivity is resumed", async () => {
  const adapter = adapterWith([
    { code: 0, stdout: "pushed", stderr: "" },
    { code: 0, stdout: "", stderr: "" },
    { code: 0, stdout: "copied", stderr: "" },
    { code: 0, stdout: "Starting: Intent { cmp=space.an3tocom.offline/.NativeGameActivity }", stderr: "" },
    { code: 0, stdout: "topResumedActivity=ActivityRecord{1 space.an3tocom.offline/.NativeGameActivity}", stderr: "" },
  ]);

  const result = await adapter.romLoad({ path: "/tmp/game.gba" });
  assert.equal(result.loaded, true);
  assert.equal(result.system, "gba");
});
