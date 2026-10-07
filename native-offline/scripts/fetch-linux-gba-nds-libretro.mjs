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
    system: "gba", engine: "mGBA libretro", version: "nightly-20261007",
    archiveName: "mgba_libretro.so.zip",
    archiveUrl: "https://buildbot.libretro.com/nightly/linux/x86_64/latest/mgba_libretro.so.zip",
    archiveSha256: "ff9a625528180b9bb9cc5b9726c772188653325783232e7f15490f64305f406a",
    coreName: "mgba_libretro.so",
    coreSha256: "c840f305825d07c9bec7a6ec18841073c4b539fd234f73623474f97c507f1cdc",
    sourceRevision: "7a12d6d4b9acb14c0ae62c9166b6a2f3d08007f6",
    licenseName: "mGBA-MPL-2.0.txt", license: "MPL-2.0",
    sourceUrl: "https://github.com/mgba-emu/mgba",
  },
  {
    system: "nds", engine: "melonDS DS libretro", version: "nightly-20261007 (1.4.0)",
    archiveName: "melondsds_libretro.so.zip",
    archiveUrl: "https://buildbot.libretro.com/nightly/linux/x86_64/latest/melondsds_libretro.so.zip",
    archiveSha256: "ce01e5a9a1794093d516c1835487494e23c4c1ba4c3ad1b3bc68bb898e6521ba",
    coreName: "melondsds_libretro.so",
    coreSha256: "3a2533677b458e1f2199748a001465a95c7a2e5f8b725ba054e1db93ebe39b77",
    sourceRevision: "v1.4.0",
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
