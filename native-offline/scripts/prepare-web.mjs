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

// Inject the canonical app version into the packaged shell so the About panel
// can never drift from the real build. Android passes its own version field
// (AN3_APP_VERSION) because tauri.android.conf.json overrides it; desktop
// builds fall back to package.json. Only the generated copy is rewritten — the
// tracked source keeps the __AN3_VERSION__ token.
const packageVersion = JSON.parse(await readFile(resolve(nativeRoot, "package.json"), "utf8")).version;
const appVersion = String(process.env.AN3_APP_VERSION || packageVersion || "").trim();
if (!/^\d+\.\d+\.\d+$/.test(appVersion)) {
  throw new Error(`prepare-web requires a valid injected app version, received: ${JSON.stringify(appVersion)}`);
}
const generatedIndex = resolve(destination, "index.html");
// Anonymous support origin: plain configuration, never a secret. An empty or
// invalid value disables the anonymous path and leaves the copy fallback.
const supportOrigin = String(process.env.AN3_SUPPORT_ORIGIN || "").trim().replace(/\/+$/, "");
if (supportOrigin && !/^https?:\/\/[^\s/]+$/i.test(supportOrigin)) {
  throw new Error(`AN3_SUPPORT_ORIGIN must be a scheme and authority, received: ${JSON.stringify(supportOrigin)}`);
}
await writeFile(
  generatedIndex,
  (await readFile(generatedIndex, "utf8"))
    .replaceAll("__AN3_VERSION__", appVersion)
    .replaceAll("__AN3_SUPPORT_ORIGIN__", supportOrigin),
);

// The installed app cannot rely on a browser tab's origin to deliver cores.
// Package only the reviewed GBA, NDS and 3DS runtime files from staging, then
// let the Rust loopback server deliver them with COOP/COEP.  `data-v2` is the
// staging-only repaired Azahar path; the public EmulatorJS CDN has no such
// path, which is why the former native 3DS launcher always failed. A source
// must be provided by the local build/test environment when the frozen cache
// is incomplete; the installed app never uses this origin at runtime.
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
    if (requireDependencyCache) throw new Error(`Frozen dependency cache is missing or corrupt: ${relativePath}`);
    const response = await fetch(`${origin}/${sourcePath}`);
    if (!response.ok) throw new Error(`Native runtime asset ${relativePath} returned HTTP ${response.status}`);
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
// Remove only obsolete generated macOS resources from the Android build tree.
// Android uses its bundled web cores; these dylibs cannot run on Android.
for (const obsolete of ["azahar", "libretro"]) {
  await rm(resolve(androidAssets, obsolete), { recursive: true, force: true });
}
for (const entry of await readdir(destination)) {
  await cp(resolve(destination, entry), resolve(androidAssets, entry), { recursive: true, force: true });
}
await cp(resolve(nativeRoot, "shared", "native-layout-schema.json"), resolve(androidAssets, "native-layout-schema.json"), { force: true });
