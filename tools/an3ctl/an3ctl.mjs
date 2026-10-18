#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// an3ctl — the project-local, agent-native control plane. One consistent,
// machine-readable interface to every target, so an agent can launch, inspect,
// drive, and verify the application without screenshots or coordinates.
//
// Design rules (see docs/agent-control-plane.md):
//   * every command returns a JSON envelope and a meaningful exit status
//   * errors carry stable machine-readable codes
//   * structured UI (DOM/accessibility/test IDs) is the primary interface
//   * screenshots are an optional diagnostic fallback, never the decision path
//   * debug/control surfaces are test-only and never ship in production

import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { An3Error, EXIT, emit, failure, ok, requireSelector, parseSelector } from "./lib/core.mjs";
import { WebAdapter } from "./adapters/web.mjs";
import { AndroidAdapter } from "./adapters/android.mjs";
import { EmulatorAdapter } from "./adapters/emulator.mjs";
import { DesktopAdapter } from "./adapters/desktop.mjs";
import { SwitchAdapter } from "./adapters/switch.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

function parseArgv(argv) {
  const positionals = [];
  const flags = {};
  let json = false;
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--json") {
      json = true;
      continue;
    }
    if (token.startsWith("--")) {
      const key = token.slice(2);
      const next = argv[index + 1];
      if (next === undefined || next.startsWith("--")) {
        flags[key] = true;
      } else {
        flags[key] = next;
        index += 1;
      }
      continue;
    }
    positionals.push(token);
  }
  return { positionals, flags, json };
}

function selectorFromFlags(flags) {
  return parseSelector(flags);
}

function requireTarget(flags) {
  const target = flags.target ?? flags.t;
  if (!target) throw new An3Error("E_USAGE", "--target is required (web, android, macos, linux, windows)");
  return String(target);
}

function buildAdapters(root) {
  return {
    web: new WebAdapter(root),
    android: new AndroidAdapter(root),
    emulator: new EmulatorAdapter(root),
    desktop: new DesktopAdapter(root),
    switch: new SwitchAdapter(root),
  };
}

async function dispatch(adapters, { positionals, flags }) {
  const [group, action] = positionals;

  switch (group) {
    case "targets":
      return targets(adapters);
    case "app":
      return appCommand(adapters, action, flags);
    case "ui":
      return uiCommand(adapters, action, flags);
    case "logs":
      return logsCommand(adapters, flags);
    case "rom":
      return romCommand(adapters, action, flags, positionals);
    case "emulator":
      return emulatorCommand(adapters, action, flags);
    case "switch":
      return switchCommand(adapters, action, flags);
    case "test":
      return testCommand(adapters, action, flags);
    case "help":
    case undefined:
      return { help: usage() };
    default:
      throw new An3Error("E_USAGE", `Unknown command group: ${group}`);
  }
}

async function targets(adapters) {
  const [web, android, desktop] = await Promise.all([
    adapters.web.available(),
    adapters.android.available().catch((error) => ({ available: false, error: error.message })),
    adapters.desktop.available().catch((error) => ({ available: false, error: error.message })),
  ]);
  const emulator = adapters.emulator.available();
  const switchTarget = adapters.switch.available();
  return {
    targets: {
      web,
      android,
      emulator,
      switch: switchTarget,
      macos: desktop.targets?.macos ?? { available: false },
      linux: desktop.targets?.linux ?? { available: false },
      windows: desktop.targets?.windows ?? { available: false },
    },
  };
}

async function appCommand(adapters, action, flags) {
  const target = requireTarget(flags);
  if (target === "web") {
    if (action === "start") return adapters.web.appStart({ port: flags.port, environment: flags.environment });
    if (action === "stop") return adapters.web.appStop();
    if (action === "state") return adapters.web.appState();
    throw new An3Error("E_USAGE", `Unknown app action for web: ${action}`);
  }
  if (target === "android") {
    if (action === "start") return adapters.android.appStart({ serial: flags.serial });
    if (action === "stop") return adapters.android.appStop({ serial: flags.serial });
    if (action === "state") return adapters.android.appState({ serial: flags.serial });
    throw new An3Error("E_USAGE", `Unknown app action for android: ${action}`);
  }
  if (target === "macos") {
    const opts = { app: flags.app, testRom: flags.rom, home: flags.home, controlFile: flags["control-file"] };
    if (action === "start") return adapters.desktop.appStart(opts);
    if (action === "stop") return adapters.desktop.appStop(opts);
    if (action === "state") return adapters.desktop.available(opts);
    throw new An3Error("E_USAGE", `Unknown app action for macos: ${action}`);
  }
  throw new An3Error("E_TARGET_UNAVAILABLE", `app ${action} is not supported for ${target}. Desktop shells are launched by their platform tooling; see docs/agent-control-plane.md.`);
}

function webOrAndroid(adapters, target) {
  if (target === "web") return adapters.web;
  if (target === "android") return adapters.android;
  if (target === "windows" || target === "macos" || target === "linux") return adapters.desktop;
  throw new An3Error("E_USAGE", `Unknown UI target: ${target}`);
}

async function uiCommand(adapters, action, flags) {
  const target = requireTarget(flags);
  const adapter = webOrAndroid(adapters, target);
  const opts = {
    selector: selectorFromFlags(flags),
    nth: flags.nth !== undefined ? Number(flags.nth) : 0,
    url: flags.url,
    path: flags.path,
    limit: flags.limit !== undefined ? Number(flags.limit) : undefined,
    value: flags.value,
    key: flags.key,
    testid: flags.testid,
    controlFile: flags["control-file"],
    timeout: flags.timeout !== undefined ? Number(flags.timeout) : undefined,
    serial: flags.serial,
    target,
    windows: { host: flags.windowsHost, port: flags.port !== undefined ? Number(flags.port) : undefined },
  };
  switch (action) {
    case "tree":
      return adapter.uiTree(opts);
    case "query":
      return adapter.uiQuery(opts);
    case "click":
      return adapter.uiClick(opts);
    case "fill":
      if (flags.value === undefined) throw new An3Error("E_USAGE", "ui fill requires --value");
      return adapter.uiFill(opts);
    case "press":
      if (!flags.key) throw new An3Error("E_USAGE", "ui press requires --key");
      return adapter.uiPress(opts);
    case "select":
      if (flags.value === undefined) throw new An3Error("E_USAGE", "ui select requires --value");
      return adapter.uiSelect(opts);
    case "check":
      return adapter.uiCheck({ ...opts, checked: flags.checked !== "false" });
    case "wait":
      return adapter.uiWait(opts);
    case "text":
      return adapter.uiText(opts);
    case "native":
      return adapter.uiNative(opts);
    case "value":
      return adapter.uiValue(opts);
    default:
      throw new An3Error("E_USAGE", `Unknown ui action: ${action}`);
  }
}

async function logsCommand(adapters, flags) {
  const target = requireTarget(flags);
  if (target === "web") return adapters.web.logs({ tail: flags.tail });
  if (target === "android") return adapters.android.logs({ tail: flags.tail, filter: flags.filter, serial: flags.serial });
  throw new An3Error("E_TARGET_UNAVAILABLE", `logs is not implemented for ${target} yet. Use ssh/an3-player for platform logs; see docs/agent-control-plane.md.`);
}

async function romCommand(adapters, action, flags, positionals) {
  const path = flags.path ?? positionals[2];
  if (action === "load") {
    const target = requireTarget(flags);
    if (!path) throw new An3Error("E_USAGE", "rom load requires a path");
    if (target === "android") return adapters.android.romLoad({ path, system: flags.system, serial: flags.serial, romId: flags.romId });
    if (target === "emulator" || target === "linux" || target === "windows") {
      return adapters.emulator.runBounded({ rom: path, system: flags.system ?? "gba", frames: flags.frames ?? 1, playerTarget: flags["player-target"] });
    }
    throw new An3Error("E_TARGET_UNAVAILABLE", `rom load is not implemented for ${target}. The GUI and this CLI must share one application command; use the emulator/android paths today.`);
  }
  throw new An3Error("E_USAGE", `Unknown rom action: ${action}`);
}

async function emulatorCommand(adapters, action, flags) {
  const common = {
    rom: flags.rom,
    system: flags.system,
    renderer: flags.renderer,
    layout: flags.layout,
    frames: flags.frames !== undefined ? Number(flags.frames) : undefined,
    inputSeq: flags.seq ?? flags["input-seq"],
    loadState: flags["load-state"],
    saveState: flags["save-state"],
    player: flags.player,
    playerTarget: flags["player-target"],
    libdir: flags.libdir,
    storage: flags.storage,
  };
  switch (action) {
    case "status":
      return adapters.emulator.status(common);
    case "run":
      return adapters.emulator.runBounded(common);
    case "snapshot":
      return adapters.emulator.snapshot(common);
    case "baseline": {
      const name = flags.name;
      if (!name) throw new An3Error("E_USAGE", "emulator baseline requires --name");
      const snapshot = await adapters.emulator.snapshot(common);
      const record = adapters.emulator.saveBaseline(name, snapshot);
      return { saved: true, baseline: record, snapshot };
    }
    case "diff": {
      const name = flags.name;
      if (!name) throw new An3Error("E_USAGE", "emulator diff requires --name");
      const baseline = adapters.emulator.loadBaseline(name);
      const snapshot = await adapters.emulator.snapshot(common);
      const result = adapters.emulator.diffRaw(baseline.rawPath, snapshot.rawPath);
      return { baseline: name, baselineHash: baseline.rawHash, candidateHash: snapshot.rawHash, ...result, candidate: snapshot.pngPath };
    }
    case "state":
      return emulatorState(adapters, flags, common);
    case "input":
      return adapters.emulator.runBounded(common);
    default:
      throw new An3Error("E_USAGE", `Unknown emulator action: ${action}`);
  }
}

async function emulatorState(adapters, flags, common) {
  const mode = flags.mode ?? (flags.save ? "save" : flags.load ? "load" : null);
  if (!common.rom) throw new An3Error("E_USAGE", "emulator state requires --rom");
  if (!flags.path) throw new An3Error("E_USAGE", "emulator state requires --path");
  if (mode === "save") return adapters.emulator.runBounded({ ...common, saveState: flags.path, frames: common.frames ?? 60 });
  if (mode === "load") return adapters.emulator.runBounded({ ...common, loadState: flags.path, frames: common.frames ?? 1 });
  throw new An3Error("E_USAGE", "emulator state requires --save or --load");
}

async function switchCommand(adapters, action, flags) {
  const opts = {
    rom: flags.rom,
    frames: flags.frames !== undefined ? Number(flags.frames) : undefined,
    seconds: flags.seconds !== undefined ? Number(flags.seconds) : undefined,
    harness: flags.harness,
  };
  const requireRom = (label) => {
    if (!opts.rom) throw new An3Error("E_USAGE", `${label} requires --rom <legal-homebrew.nro>`);
  };
  switch (action) {
    case "detect":
      return adapters.switch.detect();
    case "status":
      requireRom("switch status");
      return adapters.switch.status({ ...opts, frames: opts.frames ?? 1 });
    case "run":
      requireRom("switch run");
      return adapters.switch.runBounded({ ...opts, frames: opts.frames ?? 1 });
    case "input":
      requireRom("switch input");
      return adapters.switch.input({ ...opts, frames: opts.frames ?? 5 });
    case "sustained":
      requireRom("switch sustained");
      return adapters.switch.runBounded({ ...opts, seconds: opts.seconds ?? 60 });
    case "companion":
      requireRom("switch companion");
      return adapters.switch.companion({ ...opts, visible: flags.visible === true, seconds: opts.seconds ?? 10 });
    case "e2e":
      requireRom("switch e2e");
      return adapters.switch.e2e(opts);
    default:
      throw new An3Error("E_USAGE", `Unknown switch action: ${action}`);
  }
}

async function testCommand(adapters, action, flags) {  const target = requireTarget(flags);
  if (action === "smoke") return smokeTest(adapters, target, flags);
  if (action === "e2e") return smokeTest(adapters, target, flags);
  throw new An3Error("E_USAGE", `Unknown test action: ${action}`);
}

async function smokeTest(adapters, target, flags) {
  const steps = [];
  const record = (name, fn) =>
    fn()
      .then((value) => steps.push({ step: name, ok: true, value }))
      .catch((error) => steps.push({ step: name, ok: false, code: error.code ?? "E_INTERNAL", message: error.message }));

  if (target === "web") {
    await record("app start", () => adapters.web.appStart({ port: flags.port }));
    await record("health", () => adapters.web.appState());
    await record("ui tree", () => adapters.web.uiTree({ limit: 40 }));
    return { target, passed: steps.every((step) => step.ok), steps };
  }
  if (target === "android") {
    await record("device", () => adapters.android.available());
    await record("app start", () => adapters.android.appStart({ serial: flags.serial }));
    await record("ui tree", () => adapters.android.uiTree({ serial: flags.serial, limit: 40 }));
    return { target, passed: steps.every((step) => step.ok), steps };
  }
  if (target === "emulator") {
    await record("status", () => adapters.emulator.status({ rom: flags.rom, system: flags.system, frames: flags.frames ?? 1, player: flags.player, playerTarget: flags["player-target"] }));
    return { target, passed: steps.every((step) => step.ok), steps };
  }
  throw new An3Error("E_TARGET_UNAVAILABLE", `No smoke flow for ${target} yet.`);
}

function usage() {
  return [
    "an3ctl — agent-native control plane",
    "",
    "Targets:",
    "  an3ctl targets --json",
    "",
    "App:",
    "  an3ctl app start|stop|state --target web [--port N]",
    "  an3ctl app start|stop|state --target android [--serial S]",
    "",
    "Structured UI (works for web and android):",
    "  an3ctl ui tree   --target web [--path /games] [--limit N]",
    "  an3ctl ui query  --target android --testid open-rom",
    "  an3ctl ui query  --target web --role button --name 'Open ROM'",
    "  an3ctl ui click  --target web --testid open-rom",
    "  an3ctl app start  --target macos   # automation build (ui-control)",
    "  an3ctl ui tree   --target macos --json",
    "  an3ctl ui click  --target macos --testid switch-launch",
    "  an3ctl ui wait   --target macos --testid switch-status --state running",
    "  an3ctl ui fill   --target web --id nativeSearch --value emerald",
    "  an3ctl ui wait   --target android --testid offlineGameGrid --timeout 8000",
    "  an3ctl ui text|value --target <t> --testid <id>",
    "  an3ctl ui press  --target web --key Enter",
    "",
    "Logs:",
    "  an3ctl logs --target web|android [--tail N] [--filter PACKAGE]",
    "",
    "ROM:",
    "  an3ctl rom load <path> --target android [--system 3ds]",
    "",
    "Emulator control plane (deterministic, no screenshots):",
    "  an3ctl emulator status   --rom fixture.gba [--player-target linux]",
    "  an3ctl emulator snapshot --rom fixture.gba --frames 120",
    "  an3ctl emulator baseline --name gba-boot --rom fixture.gba --frames 120",
    "  an3ctl emulator diff     --name gba-boot --rom fixture.gba --frames 120",
    "  an3ctl emulator state    --rom fixture.gba --path save.state --save|--load",
    "  an3ctl emulator input    --rom fixture.gba --seq 'A@0-30;Start@40-45' --frames 60",
    "",
    "Switch (Eden bridge harness; legal homebrew only):",
    "  an3ctl switch detect --json",
    "  an3ctl switch status --rom hbmenu.nro --frames 1",
    "  an3ctl switch run    --rom hbmenu.nro --frames 60",
    "  an3ctl switch input  --rom hbmenu.nro",
    "  an3ctl switch sustained --rom hbmenu.nro --seconds 60",
    "  an3ctl switch companion --rom hbmenu.nro --seconds 10 [--visible]",
    "  an3ctl switch e2e --rom hbmenu.nro   # full lifecycle with input",
    "",
    "Tests:",
    "  an3ctl test smoke --target web|android|emulator",
  ].join("\n");
}

async function main() {
  const parsed = parseArgv(process.argv.slice(2));
  const adapters = buildAdapters(ROOT);
  const command = `${parsed.positionals[0] ?? "help"}${parsed.positionals[1] ? " " + parsed.positionals[1] : ""}`;
  const target = parsed.flags.target ?? parsed.flags.t ?? null;
  try {
    const data = await dispatch(adapters, parsed);
    return emit(ok(command, target, data), { json: parsed.json });
  } catch (error) {
    const an3 = error instanceof An3Error ? error : new An3Error("E_INTERNAL", error.message ?? String(error));
    return emit(failure(command, target, an3), { json: parsed.json });
  }
}

main().then((code) => process.exit(code ?? EXIT.OK));
