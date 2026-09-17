// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Switch / Eden control plane. Drives the Eden bridge's deterministic harness
// (`native/eden-bridge/tests/bridge_smoke.c`), which emits one machine-readable
// `AN3CTL_STATUS {"target":"switch",...}` line. No window, screenshot or manual
// click is required for a PASS/FAIL decision.
//
// The harness is the single control boundary: the same commands work for a
// locally built Eden bridge and (over SSH) for a remote builder.

import { existsSync } from "node:fs";
import { An3Error, run } from "../lib/core.mjs";

const HARNESS_CANDIDATES = [
  "/tmp/eden-build/bin/an3_eden_bridge_smoke",
];

const COMPANION_CANDIDATES = [
  "/tmp/eden-build/bin/an3_switch_companion",
];

const MOLTENVK_CANDIDATES = [
  "/tmp/eden/.cache/cpm/moltenvk/v1.4.1-ryujinx/MoltenVK/dynamic/dylib/macOS/libMoltenVK.dylib",
];

export class SwitchAdapter {
  constructor(root) {
    this.root = root;
    this.name = "switch";
  }

  resolveHarness(opts = {}) {
    const fromFlag = opts.harness ?? process.env.AN3_SWITCH_HARNESS ?? process.env.AN3_EDEN_SMOKE;
    if (fromFlag) return fromFlag;
    for (const candidate of HARNESS_CANDIDATES) {
      if (existsSync(candidate)) return candidate;
    }
    return null;
  }

  resolveMoltenVk() {
    if (process.env.LIBVULKAN_PATH) return process.env.LIBVULKAN_PATH;
    for (const candidate of MOLTENVK_CANDIDATES) {
      if (existsSync(candidate)) return candidate;
    }
    return null;
  }

  resolveCompanion(opts = {}) {
    const explicit = opts.companion ?? process.env.AN3_SWITCH_COMPANION;
    if (explicit && existsSync(explicit)) return explicit;
    for (const candidate of COMPANION_CANDIDATES) {
      if (existsSync(candidate)) return candidate;
    }
    return null;
  }

  available() {
    const harness = this.resolveHarness();
    return {
      available: harness !== null,
      harness,
      moltenvk: this.resolveMoltenVk(),
      note: harness === null
        ? "No Eden bridge harness found; build native/eden-bridge (see its README) or set AN3_SWITCH_HARNESS."
        : null,
    };
  }

  buildArgs(opts) {
    const args = ["--json"];
    if (opts.seconds && Number(opts.seconds) > 0) {
      args.push("--seconds", String(Number(opts.seconds)));
    } else {
      args.push("--frames", String(Number(opts.frames ?? 1)));
    }
    if (opts.rom) args.push(opts.rom);
    return args;
  }

  parseStatus(stdout) {
    // Eden's console backend can prefix the line with control bytes, so search
    // for the marker inside each line rather than requiring it at position 0.
    const line = stdout
      .split("\n")
      .reverse()
      .find((entry) => entry.includes("AN3CTL_STATUS "));
    if (!line) return null;
    const marker = "AN3CTL_STATUS ";
    try {
      return JSON.parse(line.slice(line.indexOf(marker) + marker.length));
    } catch {
      return null;
    }
  }

  async invoke(opts = {}) {
    const harness = this.resolveHarness(opts);
    if (!harness) {
      throw new An3Error(
        "E_TARGET_UNAVAILABLE",
        "No Eden bridge harness is available. Build native/eden-bridge or set AN3_SWITCH_HARNESS.",
      );
    }
    const env = { ...process.env };
    const moltenvk = this.resolveMoltenVk();
    if (moltenvk) env.LIBVULKAN_PATH = moltenvk;
    const timeoutMs = Number(opts.timeoutMs ?? ((Number(opts.seconds ?? 0) + 60) * 1000));
    const result = await run(harness, this.buildArgs(opts), { env, timeoutMs });
    const status = this.parseStatus(result.stdout);
    if (result.code !== 0 && !status) {
      throw new An3Error(
        "E_ACTION_FAILED",
        `Switch harness exited ${result.code}: ${(result.stderr || result.stdout).trim().slice(0, 400)}`,
      );
    }
    return { harness, status, code: result.code, stdout: result.stdout, stderr: result.stderr };
  }

  async detect() {
    const probe = await this.invoke({});
    return {
      available: probe.status?.result === "PASS" || probe.status !== null,
      harness: probe.harness,
      backend: probe.status?.backend ?? null,
      moltenvk: this.resolveMoltenVk(),
      probe: probe.status,
    };
  }

  async status(opts = {}) {
    const { harness, status } = await this.invoke(opts);
    return { harness, ...(status ?? {}) };
  }

  async runBounded(opts = {}) {
    const { harness, status } = await this.invoke(opts);
    if (status === null) {
      throw new An3Error("E_ACTION_FAILED", "The Switch harness produced no AN3CTL_STATUS line.");
    }
    return { harness, status };
  }

  // The harness performs the input acceptance test as part of a loaded run:
  // press/release a button and move/reset an analog stick, then read Eden's own
  // emulated-controller state back. This surfaces that verdict structurally.
  async input(opts = {}) {
    const { harness, status } = await this.runBounded({ ...opts, frames: opts.frames ?? 5 });
    return {
      harness,
      inputSupported: status.inputSupported === true,
      result: status.result,
      backend: status.backend,
      verified: status.inputSupported === true && status.result === "PASS",
      status,
    };
  }

  // Launches the separate-process companion for a bounded run. This is the
  // production path (AN3 launches the companion; Eden is never linked in).
  async companion(opts = {}) {
    const companion = this.resolveCompanion(opts);
    if (!companion) {
      throw new An3Error(
        "E_TARGET_UNAVAILABLE",
        "No Switch companion built. Build native/eden-bridge or set AN3_SWITCH_COMPANION.",
      );
    }
    const args = [opts.rom, "--no-stdin"];
    if (opts.visible) args.push("--visible");
    const seconds = Number(opts.seconds ?? 10);
    args.push("--seconds", String(seconds));
    const env = { ...process.env };
    const moltenvk = this.resolveMoltenVk();
    if (moltenvk) env.LIBVULKAN_PATH = moltenvk;
    const result = await run(companion, args, { env, timeoutMs: (seconds + 120) * 1000 });
    const status = this.parseStatus(result.stdout);
    if (status === null) {
      throw new An3Error(
        "E_ACTION_FAILED",
        `Companion exited ${result.code}: ${(result.stderr || result.stdout).trim().slice(0, 400)}`,
      );
    }
    return { companion, code: result.code, status };
  }
}
