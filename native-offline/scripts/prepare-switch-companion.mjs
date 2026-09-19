// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Stages the Nintendo Switch companion for packaging:
//   1. copies the built `an3_switch_companion`
//   2. bundles every non-system dylib it depends on
//   3. rewrites install names so the bundle is self-contained (no Homebrew
//      paths, no development-machine paths)
//   4. records a manifest (Eden pin, hashes) and Eden's license text
//
// Source build: set AN3_SWITCH_COMPANION_BUILD to the compiled binary (default
// /tmp/eden-build/bin/an3_switch_companion). The binary is built out-of-tree
// from Eden at a pinned commit; see native/eden-bridge/README.md.

import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  chmodSync,
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_SOURCE = "/tmp/eden-build/bin/an3_switch_companion";
const SOURCE = process.env.AN3_SWITCH_COMPANION_BUILD ?? DEFAULT_SOURCE;
const EDEN_ROOT = process.env.AN3_EDEN_ROOT ?? "/tmp/eden";
const EDEN_COMMIT = process.env.AN3_EDEN_COMMIT ?? "7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c";
const EDEN_UPSTREAM = "https://git.eden-emu.dev/eden-emu/eden";
const BRIDGE_ABI = 3;

const DEST_DIR = join(ROOT, "vendor/switch/macos-arm64");
const LIB_DIR = join(DEST_DIR, "lib");
const DEST_BIN = join(DEST_DIR, "an3_switch_companion");

const isExternal = (path) => path.startsWith("/opt/homebrew/") || path.startsWith("/usr/local/");

function fail(message) {
  console.error(`prepare-switch-companion: ${message}`);
  process.exit(1);
}

function dependencies(file, { includeId = false } = {}) {
  const output = execFileSync("otool", ["-L", file], { encoding: "utf8" });
  const entries = output
    .split("\n")
    .slice(1)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.split(" (")[0].trim())
    .filter((path) => path.startsWith("/"));
  // A dylib's first entry is its own LC_ID_DYLIB (same basename); an
  // executable has no such entry.
  const id = entries.length > 0 && basename(entries[0]) === basename(file) ? entries[0] : null;
  if (!includeId && id !== null) {
    return entries.slice(1);
  }
  return entries;
}

function sha256(file) {
  return createHash("sha256").update(readFileSync(file)).digest("hex");
}

if (!existsSync(SOURCE)) {
  fail(`the companion binary is missing at ${SOURCE}.\nBuild native/eden-bridge (see its README) or set AN3_SWITCH_COMPANION_BUILD.`);
}
if (process.platform !== "darwin") {
  fail("the companion is currently built for macOS only");
}

// 1. Collect the transitive closure of non-system dependencies.
const closure = new Map(); // basename -> absolute source path
const queue = dependencies(SOURCE).filter(isExternal);
while (queue.length > 0) {
  const path = queue.shift();
  const name = basename(path);
  if (closure.has(name)) continue;
  if (!existsSync(path)) fail(`a dependency is missing: ${path}`);
  closure.set(name, path);
  for (const nested of dependencies(path)) {
    if (isExternal(nested) && !closure.has(basename(nested))) queue.push(nested);
  }
}

// 2. Lay out the bundle.
rmSync(DEST_DIR, { recursive: true, force: true });
mkdirSync(LIB_DIR, { recursive: true });
copyFileSync(SOURCE, DEST_BIN);
chmodSync(DEST_BIN, 0o755);
for (const [name, path] of closure) {
  copyFileSync(path, join(LIB_DIR, name));
  chmodSync(join(LIB_DIR, name), 0o755);
}

// 3. Rewrite install names so nothing points at a development path.
//    companion deps -> @loader_path/lib/<name>; bundled dylib deps -> @loader_path/<name>.
function rewrite(referencer, prefix) {
  for (const dep of dependencies(referencer)) {
    if (!isExternal(dep)) continue;
    const name = basename(dep);
    if (!closure.has(name)) fail(`unbundled dependency ${dep} in ${basename(referencer)}`);
    execFileSync("install_name_tool", ["-change", dep, `${prefix}${name}`, referencer]);
  }
}
rewrite(DEST_BIN, "@loader_path/lib/");
for (const name of closure.keys()) {
  const lib = join(LIB_DIR, name);
  rewrite(lib, "@loader_path/");
  // Drop the Homebrew identity so no development path remains in the bundle.
  execFileSync("install_name_tool", ["-id", `@rpath/${name}`, lib]);
}

// 4. Verify the rewrite removed every external path.
function externalRemaining() {
  const files = [DEST_BIN, ...[...closure.keys()].map((name) => join(LIB_DIR, name))];
  const leftovers = [];
  for (const file of files) {
    for (const dep of dependencies(file)) {
      if (isExternal(dep)) leftovers.push(`${basename(file)} -> ${dep}`);
    }
  }
  return leftovers;
}
const leftovers = externalRemaining();
if (leftovers.length > 0) {
  fail(`install-name rewrite left external paths:\n  ${leftovers.join("\n  ")}`);
}

// 5. Ship Eden's license text and a manifest recording the pinned source.
let licenseNote = "Eden license text was not found at the expected path; see THIRD_PARTY_NOTICES.md.";
const licensePath = join(EDEN_ROOT, "LICENSE.txt");
if (existsSync(licensePath)) {
  copyFileSync(licensePath, join(DEST_DIR, "EDEN-GPL-3.0-or-later.txt"));
  licenseNote = "EDEN-GPL-3.0-or-later.txt";
}
const manifest = {
  name: "an3_switch_companion",
  bridgeAbi: BRIDGE_ABI,
  source: "native/eden-bridge (compiled inside Eden's build tree)",
  eden: { upstream: EDEN_UPSTREAM, commit: EDEN_COMMIT },
  license: "GPL-3.0-or-later",
  licenseText: licenseNote,
  sha256: sha256(DEST_BIN),
  size: readFileSync(DEST_BIN).length,
  bundledLibraries: [...closure.keys()].sort(),
};
writeFileSync(join(DEST_DIR, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);

console.log(`SWITCH_COMPANION_STAGED=${DEST_BIN}`);
console.log(`SWITCH_COMPANION_SHA256=${manifest.sha256}`);
console.log(`SWITCH_COMPANION_LIBS=${closure.size}`);
