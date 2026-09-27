import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { cp, mkdtemp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import { buildPinnedMgbaCore, fetchVerifiedBytes, mgbaSourceLock } from "./build-mgba-core.mjs";

const execFileAsync = promisify(execFile);
const scriptDirectory = resolve(fileURLToPath(new URL(".", import.meta.url)));
const nativeRoot = resolve(scriptDirectory, "..");
const destination = resolve(nativeRoot, "vendor", "libretro", "linux-x86_64");
const sha256 = data => createHash("sha256").update(data).digest("hex");

const cores = [
  {
    system: "gba", engine: "mGBA libretro", ...mgbaSourceLock,
    coreName: "mgba_libretro.so",
  },
  {
    system: "nds", engine: "melonDS DS libretro", version: "1.3.1",
    archiveName: "melondsds_libretro.so.zip",
    // The buildbot ZIP envelope changes while the core payload stays
    // byte-identical; validate the extracted core SHA-256 below.
    archiveUrl: "https://buildbot.libretro.com/nightly/linux/x86_64/latest/melondsds_libretro.so.zip",
    coreName: "melondsds_libretro.so",
    coreSha256: "a217ebd98a68745591cf68bdf35342d73b9044f2a3e6a6071c165dc632ae7cf9",
    licenseName: "melonDS-DS-GPL-3.0-or-later.txt", license: "GPL-3.0-or-later",
    licenseUrl: "https://raw.githubusercontent.com/JesseTG/melonds-ds/bc4e4b67d2d470d7c682810a1e892cafd6f9082b/LICENSE",
    licenseSha256: "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986",
    sourceUrl: "https://github.com/JesseTG/melonds-ds/tree/bc4e4b67d2d470d7c682810a1e892cafd6f9082b",
    sourceRevision: "bc4e4b67d2d470d7c682810a1e892cafd6f9082b",
  },
];

const verified = async (path, expected) => {
  try { return sha256(await readFile(path)) === expected; } catch { return false; }
};

async function previousMgbaBuild() {
  try {
    const manifest = JSON.parse(await readFile(join(destination, "manifest.json"), "utf8"));
    const entry = manifest.cores.find(core => core.system === "gba");
    if (entry?.sourceRevision === mgbaSourceLock.sourceRevision
        && entry?.sourceSha256 === mgbaSourceLock.sourceSha256
        && await verified(join(destination, cores[0].coreName), entry.coreSha256)
        && await verified(join(destination, cores[0].licenseName), cores[0].licenseSha256)) return entry;
  } catch {}
  return null;
}

if (process.platform !== "linux" || process.arch !== "x64") {
  console.log("LINUX_GBA_NDS_LIBRETRO=SKIPPED (requires Linux x86_64 packaging host)");
  process.exit(0);
}

const existingMgba = await previousMgbaBuild();
const artifactsReady = Boolean(existingMgba) && (await Promise.all(cores.slice(1).flatMap(core => [
  verified(join(destination, core.coreName), core.coreSha256),
  verified(join(destination, core.licenseName), core.licenseSha256),
]))).every(Boolean);

let manifestCores;
if (artifactsReady) {
  manifestCores = [existingMgba, cores[1]];
} else {
  const temporary = await mkdtemp(join(tmpdir(), "an3-linux-libretro-"));
  try {
    const staged = join(temporary, "staged");
    await mkdir(staged, { recursive: true });
    const builtMgba = await buildPinnedMgbaCore(staged, "linux");
    const melon = cores[1];
    const archive = join(temporary, melon.archiveName);
    const response = await fetch(melon.archiveUrl);
    if (!response.ok) throw new Error(`${melon.engine} archive download returned HTTP ${response.status}`);
    await writeFile(archive, Buffer.from(await response.arrayBuffer()));
    const extracted = await execFileAsync("/usr/bin/unzip", ["-p", archive, melon.coreName], { encoding: "buffer", maxBuffer: 16 * 1024 * 1024 });
    await writeFile(join(staged, melon.coreName), extracted.stdout);
    if (!await verified(join(staged, melon.coreName), melon.coreSha256)) throw new Error(`${melon.engine} extracted core failed its pinned SHA-256 verification.`);
    await writeFile(join(staged, melon.licenseName), await fetchVerifiedBytes(melon.licenseUrl, melon.licenseSha256, `${melon.engine} license`));

    manifestCores = [{ ...cores[0], ...builtMgba }, melon];
    await writeFile(join(staged, "manifest.json"), `${JSON.stringify({
      platform: "Linux x86_64",
      presentation: "Vulkan preferred -> desktop OpenGL fallback",
      cores: manifestCores,
    }, null, 2)}\n`);
    await rm(destination, { recursive: true, force: true });
    await mkdir(destination, { recursive: true });
    for (const entry of await readdir(staged)) await cp(join(staged, entry), join(destination, entry));
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}

await writeFile(join(destination, "manifest.json"), `${JSON.stringify({
  platform: "Linux x86_64",
  presentation: "Vulkan preferred -> desktop OpenGL fallback",
  cores: manifestCores,
}, null, 2)}\n`);
console.log(`LINUX_GBA_NDS_LIBRETRO=${destination}`);
