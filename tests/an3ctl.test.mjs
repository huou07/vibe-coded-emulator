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

import { test, after } from "node:test";
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir, homedir } from "node:os";
import { createServer } from "node:net";
import { canCreateUnder, daemonCacheOverride } from "../tools/an3ctl/adapters/web.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const CLI = `${ROOT}/tools/an3ctl/bin/an3ctl`;
const GENERATOR = `${ROOT}/tools/make-synthetic-gba-fixture.py`;
// A caller-supplied lawful fixture wins. Otherwise use the synthetic GBA ROM the
// repository can build from its own source (tools/make-synthetic-gba-fixture.py,
// git-ignored, never bundled), so the emulator lane is reproducible on any host
// instead of depending on a machine-specific owner-home path.
const SYNTHETIC_FIXTURE = `${ROOT}/work/fixtures/an3-synthetic-gba.gba`;
const FIXTURE = process.env.AN3_FIXTURE ?? SYNTHETIC_FIXTURE;

// Keep every pid file, log and Playwright session this test creates out of the
// shared work/an3ctl directory, so a concurrent agent lane or a leftover manual
// session can never make this self-test observe foreign state.
const STATE = mkdtempSync(resolve(tmpdir(), "an3ctl-self-test-"));
process.env.AN3_STATE_DIR = STATE;
after(() => rmSync(STATE, { recursive: true, force: true }));

function freePort() {
  return new Promise((resolvePort, reject) => {
    const listener = createServer();
    listener.on("error", reject);
    listener.listen(0, "127.0.0.1", () => {
      const { port } = listener.address();
      listener.close(() => resolvePort(String(port)));
    });
  });
}

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
    child.on("error", (error) => {
      clearTimeout(timer);
      resolvePromise({ code: 127, stdout, stderr: stderr + error.message });
    });
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
  assert.equal(typeof envelope.data.targets.web.hasPlaywright, "boolean");
});

test("usage: an unknown command is a usage error (exit 2)", async () => {
  const result = await cli(["nonsense", "--json"]);
  const envelope = parse(result);
  assert.equal(result.code, 2);
  assert.equal(envelope.error.code, "E_USAGE");
});

test("web: the Playwright daemon cache moves only when the shared one cannot host it", () => {
  // Synthetic, host-neutral paths: a literal home-directory path here would be a
  // finding against the published snapshot (tools/publication-check.sh).
  const base = { dir: "/state", platform: "linux", env: {}, home: "/opt/agent-home", creatable: () => true };

  // Hosted runner: the default cache base is writable, so playwright-cli is left
  // exactly as it was. This is the case that must not regress: overriding
  // XDG_CACHE_HOME unconditionally also moved the installed-browser registry and
  // hid a Chromium that CI had installed in the default location.
  assert.equal(daemonCacheOverride(base), undefined);

  // Worker: the shared cache cannot host the daemon, so the daemon moves beside
  // this run's state and the browser registry is pinned so it is still found.
  assert.deepEqual(daemonCacheOverride({ ...base, creatable: () => false }), {
    XDG_CACHE_HOME: "/state/playwright-cache",
    PLAYWRIGHT_BROWSERS_PATH: "/opt/agent-home/.cache/ms-playwright",
  });

  // An explicit caller choice always wins.
  assert.equal(daemonCacheOverride({ ...base, env: { XDG_CACHE_HOME: "/custom" }, creatable: () => false }), undefined);
  assert.equal(daemonCacheOverride({ ...base, env: { PWTEST_DAEMON_SESSION_DIR: "/sessions" }, creatable: () => false }), undefined);
  assert.equal(
    daemonCacheOverride({ ...base, env: { PLAYWRIGHT_BROWSERS_PATH: "/opt/browsers" }, creatable: () => false }).PLAYWRIGHT_BROWSERS_PATH,
    "/opt/browsers",
  );

  // Other platforms resolve the daemon base somewhere else, so they are untouched.
  assert.equal(daemonCacheOverride({ ...base, platform: "darwin", creatable: () => false }), undefined);
  assert.equal(daemonCacheOverride({ ...base, platform: "win32", creatable: () => false }), undefined);
});

test("web: launch, inspect, act, read back, and shut down cleanly", async (t) => {
  const targets = parse(await cli(["targets", "--json"]));
  if (!targets.data.targets.web.hasPlaywright) {
    t.skip("playwright-cli is not installed");
    return;
  }
  const port = process.env.AN3_TEST_PORT ?? (await freePort());
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

  // playwright-cli keeps its daemon and browser profile under
  // $XDG_CACHE_HOME/ms-playwright. Opening the page must have used a base this
  // run could actually write: an unwritable daemon directory otherwise surfaced
  // here as an EACCES browser-cache error reported as if the page had failed.
  // The decision itself is pinned by the unit test below; here we assert its
  // observable effect on this host.
  const override = daemonCacheOverride({ dir: STATE, platform: process.platform, env: process.env, home: homedir(), creatable: canCreateUnder });
  if (override) {
    assert.ok(
      existsSync(`${override.XDG_CACHE_HOME}/ms-playwright/daemon`),
      "when the shared cache cannot host the daemon, the private base must be the one used",
    );
  }

  const query = parse(await cli(["ui", "query", "--target", "web", "--path", "/games", "--id", "gameSearch", "--json"]));
  assert.equal(query.data.found, true);
  assert.equal(query.data.node.role, "searchbox");

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
  if (!playerTarget && !process.env.AN3_FIXTURE && !existsSync(FIXTURE)) {
    // Reproduce the synthetic fixture instead of skipping: it is pure source
    // output, contains no bundled ROM or copyrighted data, and lands in the
    // git-ignored work tree.
    spawnSync("python3", [GENERATOR, "--output", FIXTURE], { cwd: ROOT, stdio: "ignore" });
  }
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
