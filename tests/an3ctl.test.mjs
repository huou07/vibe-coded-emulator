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
    // The lane is not claimed. Say so in machine-readable form as well as in the
    // runner's own skip line, so the verify-project skip manifest carries it.
    console.log("AN3_LANE=emulator SKIPPED reason=no-player-configured");
    t.skip("set AN3_PLAYER or AN3_PLAYER_TARGET to exercise the emulator plane");
    return;
  }
  // The caller claimed the emulator lane. From here a missing fixture is a
  // failure, not a skip: a lane that reports success while measuring nothing is
  // exactly the defect this guard exists for.
  const declaredFixture = process.env.AN3_FIXTURE;
  if (!playerTarget && declaredFixture && !existsSync(declaredFixture)) {
    assert.fail(`AN3_FIXTURE was set to a path that does not exist: ${declaredFixture}`);
  }
  // A local player needs the fixture locally; a remote player resolves --rom on
  // its own host, so the local file need not exist.
  if (!playerTarget && !declaredFixture && !existsSync(FIXTURE)) {
    // Reproduce the synthetic fixture: it is pure source output, contains no
    // bundled ROM or copyrighted data, and lands in the git-ignored work tree.
    const generated = spawnSync("python3", [GENERATOR, "--output", FIXTURE], {
      cwd: ROOT,
      encoding: "utf8",
    });
    assert.equal(
      generated.status,
      0,
      `the fixture generator failed while the emulator lane was claimed: ${generated.stderr || generated.error?.message || "unknown error"}`,
    );
  }
  if (!playerTarget && !existsSync(FIXTURE)) {
    assert.fail(`the emulator lane was claimed but its fixture is absent: ${FIXTURE}`);
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

  // Automated emulator-loop budget, in two parts. The whole-run throughput bound
  // alone cannot see a single stalled frame: 600 frames may take 15s because one
  // frame took 14s. `--status-json` now reports a measured frame-time
  // distribution (`frameMs`, wall clock around `run_one`) and a measured
  // `measuredFps`, so the tail is asserted too. These stay emulator-loop timings:
  // they are NOT display frame pacing, and the headless lane runs no audio device
  // (the payload says `audioMeasured:false`), so audio underruns are not
  // established here. docs/QUALITY.md, vce-gameplay-performance.
  const BUDGET_FRAMES = 600;
  const BUDGET_MS = Number(process.env.AN3_EMULATOR_BUDGET_MS ?? 20000);
  // Stall guards. The vendored Linux runtime measures p95 ~0.3ms and max
  // ~0.4ms per emulated frame on this class of host, so these are two orders of
  // magnitude above the measurement: they tolerate shared-runner noise and still
  // catch the gross stalls a whole-run mean hides (a single 200ms frame inside a
  // 600-frame run passes the throughput bound above).
  const BUDGET_P95_MS = Number(process.env.AN3_EMULATOR_FRAME_P95_MS ?? 10);
  const BUDGET_FRAME_MAX_MS = Number(process.env.AN3_EMULATOR_FRAME_MAX_MS ?? 250);
  const budgetStarted = Date.now();
  const sustained = parse(await cli(["emulator", "status", ...selection, ...base, "--frames", String(BUDGET_FRAMES), "--json"]));
  const budgetMs = Date.now() - budgetStarted;
  assert.equal(sustained.ok, true, `sustained status failed: ${JSON.stringify(sustained.error)}`);
  assert.equal(sustained.data.coreFrames, BUDGET_FRAMES, "the core must run every requested frame");
  assert.ok(
    budgetMs <= BUDGET_MS,
    `emulator-loop throughput budget exceeded: ${BUDGET_FRAMES} frames took ${budgetMs}ms (budget ${BUDGET_MS}ms)`,
  );
  const frameMs = sustained.data.frameMs;
  assert.ok(frameMs && typeof frameMs === "object", `status must report a frame-time distribution, got ${JSON.stringify(frameMs)}`);
  assert.equal(frameMs.samples, BUDGET_FRAMES, "every frame must contribute one timing sample");
  for (const field of ["mean", "p50", "p95", "p99", "max"]) {
    assert.ok(
      Number.isFinite(frameMs[field]) && frameMs[field] > 0,
      `frameMs.${field} must be a measured positive number, got ${frameMs[field]}`,
    );
  }
  assert.ok(
    frameMs.p50 <= frameMs.p95 && frameMs.p95 <= frameMs.p99 && frameMs.p99 <= frameMs.max,
    `frame-time distribution must be ordered: ${JSON.stringify(frameMs)}`,
  );
  assert.ok(
    frameMs.p95 <= BUDGET_P95_MS,
    `emulator-loop p95 frame time exceeded: p95=${frameMs.p95}ms (budget ${BUDGET_P95_MS}ms)`,
  );
  assert.ok(
    frameMs.max <= BUDGET_FRAME_MAX_MS,
    `emulator-loop worst frame exceeded: max=${frameMs.max}ms (budget ${BUDGET_FRAME_MAX_MS}ms)`,
  );
  assert.ok(
    Number.isFinite(sustained.data.measuredFps) && sustained.data.measuredFps > 0,
    `status must report a measured fps, got ${sustained.data.measuredFps}`,
  );
  assert.equal(sustained.data.audioMeasured, false, "the headless lane runs no audio device and must say so");
  console.log(`AN3_EMULATOR_BUDGET frames=${BUDGET_FRAMES} elapsedMs=${budgetMs} budgetMs=${BUDGET_MS} result=PASS`);
  console.log(
    `AN3_EMULATOR_FRAME_BUDGET samples=${frameMs.samples} meanMs=${frameMs.mean.toFixed(3)} `
    + `p50Ms=${frameMs.p50.toFixed(3)} p95Ms=${frameMs.p95.toFixed(3)} p99Ms=${frameMs.p99.toFixed(3)} `
    + `maxMs=${frameMs.max.toFixed(3)} measuredFps=${sustained.data.measuredFps.toFixed(1)} `
    + `audioMeasured=${sustained.data.audioMeasured} result=PASS`,
  );

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
