// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Regenerates the committed core-option registry from the vendored macOS cores
// using tools/core_option_probe.cpp. Development-only: the Android build reads
// the committed JSON and never runs this. Host-specific options (network
// interfaces, host paths) are stripped so no machine data is committed.
import { execFileSync } from "node:child_process";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const work = resolve(root, "work/core-option-registry");
const probe = resolve(work, "core_option_probe");
const includeDir = resolve(root, "native-runtime/core");
const source = resolve(root, "tools/core_option_probe.cpp");
const output = resolve(root, "shared/core-option-registry.json");

const cores = {
  gba: { path: resolve(root, "vendor/libretro/macos-arm64/mgba_libretro.dylib"), noGame: false },
  nds: { path: resolve(root, "vendor/libretro/macos-arm64/melondsds_libretro.dylib"), noGame: true },
  "3ds": { path: resolve(root, "vendor/azahar/macos-arm64/azahar_libretro.dylib"), noGame: false },
};

// Options whose value set is bound to the generating machine. Committing these
// would leak host data and offer values the Android core cannot accept.
const HOST_SPECIFIC = {
  nds: [
    "melonds_direct_network_interface",
    "melonds_firmware_nds_path",
    "melonds_firmware_dsi_path",
    "melonds_dsi_nand_path",
    "melonds_dsi_sdcard",
    "melonds_homebrew_sdcard",
  ],
};

const macAddress = /^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$/;
const hostPath = value => value.startsWith("/") || value.startsWith("~") || /^[A-Za-z]:\\/.test(value);
const isHostSpecific = (system, option) => {
  if ((HOST_SPECIFIC[system] || []).includes(option.key)) return true;
  return option.values.some(entry => macAddress.test(entry.value) || hostPath(entry.value));
};

if (process.platform !== "darwin") throw new Error("core-option registry generation requires the vendored macOS cores (darwin)");
await rm(work, { recursive: true, force: true });
await mkdir(resolve(work, "save"), { recursive: true });
await mkdir(resolve(work, "system"), { recursive: true });
const cxx = process.env.CXX || "clang++";
execFileSync(cxx, ["-std=c++20", "-O1", `-I`, includeDir, source, "-o", probe, "-ldl"], { stdio: "inherit" });

const manifest = JSON.parse(await readFile(resolve(root, "vendor/libretro/macos-arm64/manifest.json"), "utf8"));
const expected = {};
for (const core of manifest.cores) expected[core.system] = core.version;
expected["3ds"] = JSON.parse(await readFile(resolve(root, "vendor/azahar/macos-arm64/manifest.json"), "utf8")).version;

const systems = { switch: { engine: null, version: null, noGame: false, options: [] } };
for (const [system, core] of Object.entries(cores)) {
  const args = [core.path, work];
  if (core.noGame) args.push("--nogame");
  const raw = execFileSync(probe, args, { maxBuffer: 64 * 1024 * 1024 }).toString();
  const parsed = JSON.parse(raw);
  const options = parsed.options.filter(option => !isHostSpecific(system, option)).map(option => ({
    key: option.key,
    label: option.label,
    description: option.description,
    category: option.category,
    default: option.default,
    values: option.values,
  }));
  systems[system] = { engine: parsed.engine, version: parsed.version, noGame: core.noGame, options };
  if (expected[system] && parsed.version && parsed.version !== expected[system]) {
    throw new Error(`${system} core version ${parsed.version} differs from the vendored manifest ${expected[system]}`);
  }
}

await writeFile(output, `${JSON.stringify({ version: 1, generatedBy: "native-offline/tools/core_option_probe.cpp", systems }, null, 2)}\n`);
for (const [system, entry] of Object.entries(systems)) console.log(`${system}: ${entry.options.length} options (${entry.engine || "n/a"})`);
console.log(`CORE_OPTION_REGISTRY=${output}`);
