import { createHash } from "node:crypto";
import { cp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import "./generate-player-ui.mjs";
import "./generate-native-settings.mjs";
import "./generate-input-actions.mjs";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const nativeRoot = resolve(scriptDirectory, "..");
const repositoryRoot = resolve(nativeRoot, "..");
const destination = resolve(nativeRoot, "dist");

// Copy only client assets into the native app. Server pages, runtime data, and
// ROM catalogues are outside this packaging boundary.
await rm(destination, { recursive: true, force: true });
await mkdir(destination, { recursive: true });
await cp(resolve(repositoryRoot, "static"), resolve(destination, "static"), { recursive: true });
await cp(resolve(nativeRoot, "web"), destination, { recursive: true });
// The installed app cannot rely on a browser tab's origin to deliver cores.
// Package only the reviewed GBA, NDS and 3DS runtime files from staging, then
// let the Rust loopback server deliver them with COOP/COEP.  `data-v2` is the
// staging-only repaired Azahar path; the public EmulatorJS CDN has no such
// path, which is why the former native 3DS launcher always failed. The repaired
// runtime is vendored in-tree (see `vendoredRuntime` below), so a fresh
// checkout builds from what the repository already ships; the frozen cache and
// `AN3_OFFLINE_RUNTIME_SOURCE` remain the sources for the public `stable` files
// and for a seeded mirror. The installed app never uses this origin at runtime.
const patchedRuntimeOrigin = (process.env.AN3_OFFLINE_RUNTIME_SOURCE || "http://127.0.0.1:8092/emulatorjs").replace(/\/+$/, "");
const standardRuntimeOrigin = "https://cdn.emulatorjs.org";
const runtimeFiles = [
  "stable/data/loader.js", "stable/data/emulator.min.js", "stable/data/emulator.min.css",
  "stable/data/localization/vi-VN.json", "stable/data/localization/en-US.json",
  "stable/data/compression/extract7z.js", "stable/data/compression/extractzip.js",
  // mGBA has no `defaultWebGL2` report flag, so EmulatorJS intentionally
  // selects its legacy variant even on a WebGL2-capable WebView.  Include both
  // variants for GBA and NDS: the runtime can make the fast choice when the
  // GPU supports it, while a compatible fallback remains truly offline.
  "stable/data/cores/reports/mgba.json", "stable/data/cores/mgba-wasm.data", "stable/data/cores/mgba-legacy-wasm.data",
  "stable/data/cores/reports/melonds.json", "stable/data/cores/melonds-wasm.data", "stable/data/cores/melonds-legacy-wasm.data",
  "latest/data-v2/loader.js", "latest/data-v2/emulator.min.js", "latest/data-v2/emulator.min.css",
  "latest/data-v2/localization/vi.json", "latest/data-v2/localization/en.json",
  "latest/data-v2/compression/extract7z.js", "latest/data-v2/compression/extractzip.js",
  "latest/data-v2/cores/reports/azahar.json", "latest/data-v2/cores/azahar-thread-wasm.data",
];

const runtimeHashes = JSON.parse(await readFile(resolve(nativeRoot, "shared/web-runtime-lock.json"), "utf8"));
const dependencyCache = resolve(process.env.AN3_DEPENDENCY_CACHE || resolve(nativeRoot, "work/dependency-cache"));
const requireDependencyCache = process.env.AN3_REQUIRE_DEPENDENCY_CACHE === "1";
// Tauri's generated Android project is where the repository vendors the nine
// locked `latest/data-v2` files (4.9 MB): the public CDN has no such path, so
// they are committed rather than fetched. Reading them here is what lets a
// fresh checkout build without a seeded runtime source or a pre-populated
// cache; the lock still decides, so a vendored file whose bytes drift from
// `web-runtime-lock.json` is rejected exactly like a downloaded one.
const vendoredRuntime = resolve(nativeRoot, "src-tauri", "gen", "android", "app", "src", "main", "assets", "emulatorjs");
await mkdir(dependencyCache, {recursive:true});

for (const relativePath of runtimeFiles) {
  const sourcePath = relativePath;
  const origin = sourcePath.startsWith("latest/data-v2/") ? patchedRuntimeOrigin : standardRuntimeOrigin;
  const cachedPath = resolve(dependencyCache, runtimeHashes[relativePath]);
  let payload;
  try {
    const cached = await readFile(cachedPath);
    if (createHash("sha256").update(cached).digest("hex") === runtimeHashes[relativePath]) payload = cached;
  } catch {}
  if (!payload) {
    try {
      const vendored = await readFile(resolve(vendoredRuntime, relativePath));
      if (createHash("sha256").update(vendored).digest("hex") === runtimeHashes[relativePath]) payload = vendored;
    } catch {}
  }
  if (!payload) {
    if (requireDependencyCache) throw new Error(`Frozen dependency cache is missing or corrupt: ${relativePath}, and the in-tree vendored runtime does not supply it either`);
    // Fail with the boundary named. A bare `TypeError: fetch failed` here reads
    // like a broken build host, but the real precondition is a configured
    // runtime source: every latest/data-v2 asset (the repaired Azahar runtime)
    // is published only by a seeded local AN3 runtime source, never by the
    // public EmulatorJS CDN.
    let response;
    try {
      response = await fetch(`${origin}/${sourcePath}`);
    } catch (error) {
      throw new Error(
        `Native runtime asset ${relativePath} is neither in the frozen dependency cache (${dependencyCache}), nor vendored at ${vendoredRuntime}, nor fetchable from ${origin} (${error.message}). ` +
        `The latest/data-v2 runtime (repaired Azahar) comes from a seeded local runtime source: set AN3_OFFLINE_RUNTIME_SOURCE to one (default ${patchedRuntimeOrigin}), ` +
        `or pre-populate the dependency cache with the pinned downloaded files, then re-run.`,
      );
    }
    if (!response.ok) {
      throw new Error(
        `Native runtime asset ${relativePath} returned HTTP ${response.status} from ${origin}. ` +
        `The standard assets come from ${standardRuntimeOrigin}; the latest/data-v2 assets come from AN3_OFFLINE_RUNTIME_SOURCE (currently ${patchedRuntimeOrigin}), from the frozen dependency cache, or from the tracked vendored runtime at ${vendoredRuntime}.`,
      );
    }
    payload = new Uint8Array(await response.arrayBuffer());
  }
  if (!payload.byteLength) throw new Error(`Native runtime asset ${relativePath} is empty`);
  const actualHash = createHash("sha256").update(payload).digest("hex");
  if (actualHash !== runtimeHashes[relativePath]) throw new Error(`Native runtime asset ${relativePath} differs from the frozen dependency lock; refusing an implicit core/runtime update.`);
  await writeFile(cachedPath, payload);
  const target = resolve(destination, "emulatorjs", relativePath);
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, payload);
}

// Android WebView recognises WebViewAssetLoader's HTTPS origin as a secure
// local origin.  Ship the exact same prepared runtime into Android's assets so
// that GBA/NDS/3DS all use one offline client bundle; no request is sent to a
// LAN host or the public internet at runtime.  Keep Tauri's generated
// `tauri.conf.json` intact and only replace the prepared application entries.
const androidAssets = resolve(nativeRoot, "src-tauri", "gen", "android", "app", "src", "main", "assets");
await mkdir(androidAssets, { recursive: true });
// Account login and server-backed identity were removed from installed apps.
await rm(resolve(androidAssets, "native-account.js"), { force: true });
// Remove only obsolete generated macOS resources from the Android build tree.
// Android uses its bundled web cores; these dylibs cannot run on Android.
for (const obsolete of ["azahar", "libretro"]) {
  await rm(resolve(androidAssets, obsolete), { recursive: true, force: true });
}
for (const entry of await readdir(destination)) {
  await cp(resolve(destination, entry), resolve(androidAssets, entry), { recursive: true, force: true });
}
await cp(resolve(nativeRoot, "shared", "native-layout-schema.json"), resolve(androidAssets, "native-layout-schema.json"), { force: true });
