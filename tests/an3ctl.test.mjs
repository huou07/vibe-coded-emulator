// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Self-tests for the an3ctl control plane. They exercise the CLI the same way
// an agent does: spawn the real launcher, parse the JSON envelope, and assert
// the exit code. Run with:  node --test tests/an3ctl.test.mjs
//
// Web tests need `playwright-cli` and a free port. Emulator tests need a native
// player (set AN3_PLAYER / AN3_PLAYER_TARGET) and a legal fixture; they skip
// cleanly when that is absent so the suite never reports a false failure.

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { existsSync } from "node:fs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const CLI = `${ROOT}/tools/an3ctl/bin/an3ctl`;
const FIXTURE = process.env.AN3_FIXTURE ?? "/home/YOUR_GITHUB_USER/an3-verify/legal-gba.gba";

function cli(args, { timeoutMs = 180000 } = {}) {
  return new Promise((resolvePromise) => {
    const child = spawn(CLI, args, { cwd: ROOT });
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      resolvePromise({ code: 124, stdout, stderr: stderr + "\n(timeout)" });
    }, timeoutMs);
    child.stdout.on("data", (chunk) => (stdout += chunk));
    child.stderr.on("data", (chunk) => (stderr += chunk));
    child.on("close", (code) => {
      clearTimeout(timer);
      resolvePromise({ code, stdout, stderr });
    });
  });
}

function parse(result) {
  const line = result.stdout.trim().split("\n").find((entry) => entry.startsWith("{"));
  assert.ok(line, `no JSON envelope. stdout=${result.stdout.slice(0, 200)} stderr=${result.stderr.slice(0, 200)}`);
  return JSON.parse(line);
}

test("targets: discovery returns an envelope with every target", async () => {
  const result = await cli(["targets", "--json"]);
  const envelope = parse(result);
  assert.equal(result.code, 0);
  assert.equal(envelope.ok, true);
  for (const name of ["web", "android", "emulator", "macos", "linux", "windows"]) {
    assert.ok(name in envelope.data.targets, `missing target ${name}`);
  }
  assert.equal(envelope.data.targets.web.hasPlaywright, true);
});

test("usage: an unknown command is a usage error (exit 2)", async () => {
  const result = await cli(["nonsense", "--json"]);
  const envelope = parse(result);
  assert.equal(result.code, 2);
  assert.equal(envelope.error.code, "E_USAGE");
});

test("web: launch, inspect, act, read back, and shut down cleanly", async (t) => {
  const port = process.env.AN3_TEST_PORT ?? "8097";
  const started = parse(await cli(["app", "start", "--target", "web", "--port", port, "--json"]));
  if (!started.ok) {
    t.skip(`web target unavailable: ${started.error.message}`);
    return;
  }
  t.after(async () => {
    await cli(["app", "stop", "--target", "web", "--json"]);
  });

  const state = parse(await cli(["app", "state", "--target", "web", "--json"]));
  assert.equal(state.data.running, true);

  const tree = parse(await cli(["ui", "tree", "--target", "web", "--path", "/games", "--limit", "40", "--json"]));
  assert.equal(tree.ok, true);
  assert.ok(Array.isArray(tree.data.nodes) && tree.data.nodes.length > 0);
  assert.ok(tree.data.nodes.every((node) => typeof node.role === "string" && typeof node.name === "string"));

  const query = parse(await cli(["ui", "query", "--target", "web", "--path", "/games", "--id", "gameSearch", "--json"]));
  assert.equal(query.data.found, true);
  assert.equal(query.data.node.role, "textbox");

  const fill = parse(await cli(["ui", "fill", "--target", "web", "--path", "/games", "--id", "gameSearch", "--value", "emerald", "--json"]));
  assert.equal(fill.data.performed, true);

  const value = parse(await cli(["ui", "value", "--target", "web", "--path", "/games", "--id", "gameSearch", "--json"]));
  assert.equal(value.data.value, "emerald");

  const waited = parse(await cli(["ui", "wait", "--target", "web", "--path", "/games", "--id", "gameSearch", "--timeout", "4000", "--json"]));
  assert.equal(waited.data.appeared, true);

  const missing = await cli(["ui", "query", "--target", "web", "--path", "/games", "--testid", "definitely-not-here", "--json"]);
  assert.equal(missing.code, 4, "a missing element must exit 4");
  assert.equal(parse(missing).error.code, "E_NOT_FOUND");

  const timeout = await cli(["ui", "wait", "--target", "web", "--path", "/games", "--testid", "definitely-not-here", "--timeout", "1500", "--json"]);
  assert.equal(timeout.code, 5, "a wait timeout must exit 5");
  assert.equal(parse(timeout).error.code, "E_TIMEOUT");

  const logs = parse(await cli(["logs", "--target", "web", "--tail", "20", "--json"]));
  assert.equal(logs.ok, true);
  assert.ok(Array.isArray(logs.data.lines));
});

test("android: structured tree and a semantic click", async (t) => {
  const targets = parse(await cli(["targets", "--json"]));
  if (!targets.data.targets.android.available) {
    t.skip("no Android device/emulator connected");
    return;
  }
  const started = parse(await cli(["app", "start", "--target", "android", "--json"]));
  assert.equal(started.ok, true, `app start failed: ${JSON.stringify(started.error)}`);

  const tree = parse(await cli(["ui", "tree", "--target", "android", "--limit", "30", "--json"]));
  // A release APK intentionally exposes no WebView devtools socket, so the
  // structured DOM tree only exists on a debug/test build. Skip with a clear
  // reason instead of leaving an unexplained red test; never enable WebView
  // debugging in production just to satisfy automation.
  if (!tree.ok && tree.error && tree.error.code === "E_TARGET_UNAVAILABLE") {
    t.skip(`Android automation bridge unavailable: ${tree.error.message}`);
    return;
  }
  assert.equal(tree.ok, true);
  assert.ok(tree.data.nodes.length > 0);

  const click = parse(await cli(["ui", "click", "--target", "android", "--role", "button", "--name", "Settings", "--json"]));
  assert.equal(click.data.performed, true);

  const missing = await cli(["ui", "query", "--target", "android", "--testid", "definitely-not-here", "--json"]);
  assert.equal(missing.code, 4);
});

test("emulator: deterministic status, and diff detects a frame change", async (t) => {
  const playerTarget = process.env.AN3_PLAYER_TARGET;
  const player = process.env.AN3_PLAYER;
  if (!playerTarget && !player) {
    t.skip("set AN3_PLAYER or AN3_PLAYER_TARGET to exercise the emulator plane");
    return;
  }
  // A local player needs the fixture locally; a remote player resolves --rom on
  // its own host, so the local file need not exist.
  if (!playerTarget && !existsSync(FIXTURE)) {
    t.skip(`fixture not present locally: ${FIXTURE}`);
    return;
  }
  const base = ["--rom", FIXTURE, "--system", "gba"];
  const selection = [];
  if (playerTarget) selection.push("--player-target", playerTarget);
  const playerPath = player ?? process.env.AN3_PLAYER_REMOTE;
  if (playerPath) selection.push("--player", playerPath);
  if (process.env.AN3_PLAYER_LIBDIR) selection.push("--libdir", process.env.AN3_PLAYER_LIBDIR);

  const status = parse(await cli(["emulator", "status", ...selection, ...base, "--frames", "120", "--json"]));
  assert.equal(status.ok, true, `status failed: ${JSON.stringify(status.error)}`);
  assert.equal(status.data.system, "gba");
  assert.equal(status.data.frames, 120);
  assert.ok(status.data.width > 0 && status.data.height > 0);

  const name = `self-test-${Date.now()}`;
  const baseline = parse(await cli(["emulator", "baseline", ...selection, ...base, "--frames", "120", "--name", name, "--json"]));
  assert.equal(baseline.ok, true, `baseline failed: ${JSON.stringify(baseline.error)}`);
  assert.match(baseline.data.baseline.rawHash, /^[0-9a-f]{64}$/);

  const same = parse(await cli(["emulator", "diff", ...selection, ...base, "--frames", "120", "--name", name, "--json"]));
  assert.equal(same.data.match, true, "identical runs must match");
  assert.equal(same.data.differentPixels, 0);

  const changed = parse(await cli(["emulator", "diff", ...selection, ...base, "--frames", "1", "--name", name, "--json"]));
  assert.equal(changed.data.match, false, "a different frame must not match");
  assert.ok(changed.data.differentPixels > 0);
  assert.ok(changed.data.maxChannelError > 0);
});
