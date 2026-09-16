import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { cp, mkdtemp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);
const scriptDirectory = resolve(fileURLToPath(new URL(".", import.meta.url)));
const nativeRoot = resolve(scriptDirectory, "..");
const destination = resolve(nativeRoot, "vendor", "libretro", "linux-x86_64");
const sha256 = data => createHash("sha256").update(data).digest("hex");

// Buildbot URLs are mutable, so both the archive and the unpacked core are
// pinned to the exact bytes inspected for this staging train. A changed
// nightly fails closed instead of silently changing the Linux package.
const cores = [
  {
    system: "gba", engine: "mGBA libretro", version: "nightly-20260911",
    archiveName: "mgba_libretro.so.zip",
    archiveUrl: "https://buildbot.libretro.com/nightly/linux/x86_64/latest/mgba_libretro.so.zip",
    archiveSha256: "983a23879249bb7727a4a0665e28a3a8e98c1ba4da8ff1fa83ff35722cd4e466",
    coreName: "mgba_libretro.so",
    coreSha256: "768921964037e0a40e8eab9e0d6eccad1b8a13d74bc37e9cae5543bb167d18c4",
    licenseName: "mGBA-MPL-2.0.txt", license: "MPL-2.0",
    sourceUrl: "https://github.com/mgba-emu/mgba",
  },
  {
    system: "nds", engine: "melonDS DS libretro", version: "nightly-20260911",
    archiveName: "melondsds_libretro.so.zip",
    archiveUrl: "https://buildbot.libretro.com/nightly/linux/x86_64/latest/melondsds_libretro.so.zip",
    archiveSha256: "db02d78068ef72e797468136471763892f3cf954ea216ef349a0eb092e4c48b3",
    coreName: "melondsds_libretro.so",
    coreSha256: "a217ebd98a68745591cf68bdf35342d73b9044f2a3e6a6071c165dc632ae7cf9",
    licenseName: "melonDS-DS-GPL-3.0-or-later.txt", license: "GPL-3.0-or-later",
    sourceUrl: "https://github.com/JesseTG/melonds-ds",
  },
];

const verified = async (path, expected) => {
  try { return sha256(await readFile(path)) === expected; } catch { return false; }
};

const download = async (url, expected, label) => {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${label} download returned HTTP ${response.status}`);
  const bytes = Buffer.from(await response.arrayBuffer());
  const actual = sha256(bytes);
  if (actual !== expected) throw new Error(`${label} SHA-256 mismatch: expected ${expected}, got ${actual}; refusing changed nightly bytes.`);
  return bytes;
};

const licenseVerified = async core => {
  // The same core license texts are already hash-verified in the macOS vendor
  // tree; compare exact bytes instead of downloading a separate mutable URL.
  const source = await readFile(join(nativeRoot, "vendor", "libretro", "macos-arm64", core.licenseName));
  return verified(join(destination, core.licenseName), sha256(source));
};

const artifactsReady = async () => (await Promise.all(cores.flatMap(core => [
  verified(join(destination, core.coreName), core.coreSha256),
  licenseVerified(core),
]))).every(Boolean);

if (process.platform !== "linux" || process.arch !== "x64") {
  console.log("LINUX_GBA_NDS_LIBRETRO=SKIPPED (requires Linux x86_64 packaging host)");
  process.exit(0);
}

if (!await artifactsReady()) {
  const temporary = await mkdtemp(join(tmpdir(), "an3-linux-libretro-"));
  try {
    const staged = join(temporary, "staged"); await mkdir(staged, { recursive: true });
    for (const core of cores) {
      const archive = join(temporary, core.archiveName);
      await writeFile(archive, await download(core.archiveUrl, core.archiveSha256, `${core.engine} archive`));
      const result = await execFileAsync("/usr/bin/unzip", ["-p", archive, core.coreName], { encoding: "buffer", maxBuffer: 16 * 1024 * 1024 });
      await writeFile(join(staged, core.coreName), result.stdout);
      if (!await verified(join(staged, core.coreName), core.coreSha256)) throw new Error(`${core.engine} extracted core failed SHA-256 verification.`);
      await cp(join(nativeRoot, "vendor", "libretro", "macos-arm64", core.licenseName), join(staged, core.licenseName));
    }
    await rm(destination, { recursive: true, force: true }); await mkdir(destination, { recursive: true });
    for (const entry of await readdir(staged)) await cp(join(staged, entry), join(destination, entry));
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}

await writeFile(join(destination, "manifest.json"), `${JSON.stringify({
  platform: "Linux x86_64", presentation: "Vulkan preferred -> desktop OpenGL fallback", cores,
}, null, 2)}\n`);
console.log(`LINUX_GBA_NDS_LIBRETRO=${destination}`);
