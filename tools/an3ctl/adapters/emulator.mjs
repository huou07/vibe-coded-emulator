// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Emulator control plane. Drives the native player's deterministic test mode
// (`--headless --frames N --capture ... --status-json`), which the player emits
// as JSON on stdout and as PNG/RGBA artifacts. No screenshot interpretation and
// no window are required for a PASS/FAIL decision.
//
// The player binary is a shared control boundary: the same commands work for a
// locally built player and for the packaged Linux/Windows players over SSH.

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { An3Error, run, runChecked, sha256, stateDir } from "../lib/core.mjs";

const REMOTE_TARGETS = {
  linux: {
    host: "build-host",
    player: "/usr/lib/VibeCodedEmulator/runtime/linux-x86_64/an3-offline-native",
    libdir: "/usr/lib/VibeCodedEmulator/runtime/linux-x86_64",
  },
  windows: {
    host: "windows-build-host",
    player: "C:/AN3/app220/runtime/windows-x64/an3-native-runtime.exe",
    libdir: "C:/AN3/app220/runtime/windows-x64",
  },
};

export class EmulatorAdapter {
  constructor(root) {
    this.root = root;
    this.name = "emulator";
    this.dir = stateDir(root);
    this.baselines = `${this.dir}/baselines`;
  }

  resolveTarget(opts = {}) {
    const target = opts.playerTarget ?? process.env.AN3_PLAYER_TARGET ?? null;
    if (target && REMOTE_TARGETS[target]) {
      const base = REMOTE_TARGETS[target];
      return { kind: "remote", name: target, ...base, player: opts.player ?? base.player, libdir: opts.libdir ?? base.libdir };
    }
    if (opts.player) return { kind: "local", player: opts.player, libdir: opts.libdir ?? process.env.AN3_OFFLINE_LIBDIR ?? null };
    const envPlayer = process.env.AN3_PLAYER;
    if (envPlayer) return { kind: "local", player: envPlayer, libdir: process.env.AN3_OFFLINE_LIBDIR ?? null };
    const localCandidates = [
      `${this.root}/native-offline/work/linux-build/an3-offline-native`,
    ];
    for (const candidate of localCandidates) {
      if (existsSync(candidate)) return { kind: "local", player: candidate, libdir: `${this.root}/native-offline/vendor/libretro/linux-x86_64` };
    }
    return { kind: "unavailable" };
  }

  available() {
    const target = this.resolveTarget();
    return {
      available: target.kind !== "unavailable" || Object.keys(REMOTE_TARGETS).length > 0,
      localPlayer: target.kind !== "unavailable" ? target.player : null,
      remoteTargets: Object.keys(REMOTE_TARGETS),
      note: target.kind === "unavailable" ? "No local player found; use --player-target linux|windows or set AN3_PLAYER." : null,
    };
  }

  // --- one-shot execution --------------------------------------------------

  buildArgs(opts) {
    const args = ["--rom", opts.rom, "--system", opts.system];
    if (opts.renderer) args.push("--renderer", opts.renderer);
    if (opts.layout) args.push("--layout", opts.layout);
    if (opts.headless !== false) args.push("--headless", "--no-audio", "--no-controls");
    args.push("--frames", String(opts.frames ?? 1));
    if (opts.capture) args.push("--capture", opts.capture);
    if (opts.captureRaw) args.push("--capture-raw", opts.captureRaw);
    if (opts.loadState) args.push("--load-state", opts.loadState);
    if (opts.saveState) args.push("--save-state", opts.saveState);
    if (opts.inputSeq) args.push("--input-seq", opts.inputSeq);
    if (opts.storage) args.push("--storage", opts.storage);
    args.push("--status-json");
    return args;
  }

  async invoke(target, opts) {
    const args = this.buildArgs(opts);
    if (target.kind === "local") {
      const result = await run(target.player, args, { timeoutMs: Number(opts.timeoutMs ?? 180000) });
      return { code: result.code, stdout: result.stdout, stderr: result.stderr };
    }
    if (target.kind === "remote") {
      const shell = [
        target.libdir ? `AN3_OFFLINE_LIBDIR='${target.libdir}'` : "",
        `'${target.player}'`,
        ...args.map((value) => `'${String(value).replace(/'/g, `'\\''`)}'`),
      ]
        .filter(Boolean)
        .join(" ");
      const result = await run("ssh", ["-o", "BatchMode=yes", target.host, shell], { timeoutMs: Number(opts.timeoutMs ?? 180000) });
      return { code: result.code, stdout: result.stdout, stderr: result.stderr };
    }
    throw new An3Error("E_TARGET_UNAVAILABLE", "No native player is available. Set AN3_PLAYER or AN3_PLAYER_TARGET=linux|windows.");
  }

  parseStatus(stdout) {
    const line = stdout.split("\n").reverse().find((entry) => entry.startsWith("AN3CTL_STATUS "));
    if (!line) return null;
    try {
      return JSON.parse(line.slice("AN3CTL_STATUS ".length));
    } catch {
      return null;
    }
  }

  async runBounded(opts) {
    const target = this.resolveTarget(opts);
    if (target.kind === "unavailable") {
      throw new An3Error("E_TARGET_UNAVAILABLE", "No native player is available. Set AN3_PLAYER or AN3_PLAYER_TARGET=linux|windows.");
    }
    const result = await this.invoke(target, opts);
    const status = this.parseStatus(result.stdout);
    if (result.code !== 0 && !status) {
      throw new An3Error("E_ACTION_FAILED", `Player exited ${result.code}: ${(result.stderr || result.stdout).trim().slice(0, 400)}`);
    }
    return { target: target.name ?? target.kind, status, stdout: result.stdout };
  }

  async status(opts = {}) {
    if (!opts.rom) throw new An3Error("E_USAGE", "emulator status requires --rom");
    const { status, target } = await this.runBounded({ ...opts, frames: opts.frames ?? 1 });
    return { target, ...status };
  }

  async snapshot(opts = {}) {
    if (!opts.rom) throw new An3Error("E_USAGE", "emulator snapshot requires --rom");
    const target = this.resolveTarget(opts);
    if (target.kind === "unavailable") {
      throw new An3Error("E_TARGET_UNAVAILABLE", "No native player is available. Set AN3_PLAYER or AN3_PLAYER_TARGET=linux|windows.");
    }
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    const localDir = `${this.dir}/frames`;
    mkdirSync(localDir, { recursive: true });
    const remoteBase = target.kind === "remote" ? `/tmp/an3ctl-${stamp}` : localDir;
    if (target.kind === "remote") {
      await runChecked("ssh", ["-o", "BatchMode=yes", target.host, `mkdir -p '${remoteBase}'`], { errorCode: "E_TARGET_UNAVAILABLE" });
    } else {
      mkdirSync(remoteBase, { recursive: true });
    }
    const pngPath = `${remoteBase}/frame.png`;
    const rawPath = `${remoteBase}/frame.rgba`;
    const { status } = await this.runBounded({
      ...opts,
      capture: pngPath,
      captureRaw: rawPath,
      frames: opts.frames ?? 120,
    });
    const localPng = `${localDir}/frame-${stamp}.png`;
    const localRaw = `${localDir}/frame-${stamp}.rgba`;
    if (target.kind === "remote") {
      await runChecked("scp", ["-o", "BatchMode=yes", `${target.host}:${pngPath}`, localPng], { errorCode: "E_ACTION_FAILED" });
      await runChecked("scp", ["-o", "BatchMode=yes", `${target.host}:${rawPath}`, localRaw], { errorCode: "E_ACTION_FAILED" });
      await run("ssh", ["-o", "BatchMode=yes", target.host, `rm -f '${pngPath}' '${rawPath}'`]);
    } else {
      await run("cp", [pngPath, localPng]);
      await run("cp", [rawPath, localRaw]);
    }
    const pngBytes = readFileSync(localPng);
    const rawBytes = readFileSync(localRaw);
    return {
      target: target.name ?? target.kind,
      status,
      pngHash: sha256(pngBytes),
      rawHash: sha256(rawBytes),
      pngPath: localPng,
      rawPath: localRaw,
      bytes: { png: pngBytes.length, raw: rawBytes.length },
    };
  }

  baselinePath(name) {
    return `${this.baselines}/${name}.json`;
  }

  saveBaseline(name, snapshot) {
    mkdirSync(this.baselines, { recursive: true });
    const record = {
      name,
      savedAt: new Date().toISOString(),
      rawHash: snapshot.rawHash,
      pngHash: snapshot.pngHash,
      width: snapshot.status?.width ?? null,
      height: snapshot.status?.height ?? null,
      system: snapshot.status?.system ?? null,
      rawPath: snapshot.rawPath,
    };
    writeFileSync(this.baselinePath(name), JSON.stringify(record, null, 2));
    return record;
  }

  loadBaseline(name) {
    if (!existsSync(this.baselinePath(name))) {
      throw new An3Error("E_NOT_FOUND", `No baseline named "${name}"`, { path: this.baselinePath(name) });
    }
    return JSON.parse(readFileSync(this.baselinePath(name), "utf8"));
  }

  // Deterministic pixel diff between two raw RGBA buffers.
  diffRaw(aPath, bPath) {
    const a = readFileSync(aPath);
    const b = readFileSync(bPath);
    const length = Math.min(a.length, b.length);
    if (a.length !== b.length) {
      return { match: false, reason: "size-mismatch", sizeA: a.length, sizeB: b.length, differentPixels: null, differentPercent: 100, maxChannelError: 255 };
    }
    const pixels = Math.floor(length / 4);
    let differentPixels = 0;
    let maxChannelError = 0;
    for (let index = 0; index < pixels; index += 1) {
      const offset = index * 4;
      const dr = Math.abs(a[offset] - b[offset]);
      const dg = Math.abs(a[offset + 1] - b[offset + 1]);
      const db = Math.abs(a[offset + 2] - b[offset + 2]);
      const da = Math.abs(a[offset + 3] - b[offset + 3]);
      const worst = Math.max(dr, dg, db, da);
      if (worst > 0) differentPixels += 1;
      if (worst > maxChannelError) maxChannelError = worst;
    }
    const differentPercent = pixels ? Number(((differentPixels / pixels) * 100).toFixed(4)) : 0;
    return { match: differentPixels === 0, differentPixels, differentPercent, maxChannelError, pixels };
  }
}
