import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);
const scriptDirectory = resolve(fileURLToPath(new URL(".", import.meta.url)));
const nativeRoot = resolve(scriptDirectory, "..");
const destination = resolve(nativeRoot, "vendor", "libretro", "macos-arm64");

const mgba = {
  system: "gba",
  engine: "mGBA libretro",
  version: "0.11-219-e31759b",
  archiveName: "mgba_libretro.dylib.zip",
  archiveUrl: "https://buildbot.libretro.com/nightly/apple/osx/arm64/latest/mgba_libretro.dylib.zip",
  archiveSha256: "1c1679f1f62c5c1bef6e9f5de111555f7600976b8a67df4d960e41e189ef9d96",
  coreName: "mgba_libretro.dylib",
  coreSha256: "085350861044d9d2ef37634a7c201f57b4816fd343bdf29cdcd09bfb754b9218",
  licenseName: "mGBA-MPL-2.0.txt",
  licenseUrl: "https://raw.githubusercontent.com/mgba-emu/mgba/e31759b24e7a4e3899285ff720d7b573ac328ae7/LICENSE",
  licenseSha256: "fab3dd6bdab226f1c08630b1dd917e11fcb4ec5e1e020e2c16f83a0a13863e85",
  sourceUrl: "https://github.com/mgba-emu/mgba/tree/e31759b24e7a4e3899285ff720d7b573ac328ae7",
  license: "MPL-2.0",
};

const melonds = {
  system: "nds",
  engine: "melonDS DS libretro",
  version: "1.3.1",
  // The creator's v1.3.1 macOS release was built with macOS 26 as its
  // deployment target. This compatible arm64 buildbot artifact reports the
  // same 1.3.1 core, targets macOS 11, and is pinned below so it can never be
  // silently upgraded by the nightly URL.
  archiveName: "melondsds_libretro.dylib.zip",
  archiveUrl: "https://buildbot.libretro.com/nightly/apple/osx/arm64/latest/melondsds_libretro.dylib.zip",
  archiveSha256: "cc1667f1f0e50a06fcb2c5583d9ea38cfb8e1457cab247ee2c21c943b3275486",
  archiveCorePath: "melondsds_libretro.dylib",
  coreName: "melondsds_libretro.dylib",
  coreSha256: "028c1d65db6eeafef33b29a90018fe037fcf0f643965031f3eb4a8b1ca23b57a",
  licenseName: "melonDS-DS-GPL-3.0-or-later.txt",
  licenseUrl: "https://raw.githubusercontent.com/JesseTG/melonds-ds/bc4e4b67d2d470d7c682810a1e892cafd6f9082b/LICENSE",
  licenseSha256: "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986",
  sourceUrl: "https://github.com/JesseTG/melonds-ds/tree/bc4e4b67d2d470d7c682810a1e892cafd6f9082b",
  license: "GPL-3.0-or-later",
};

const sha256 = data => createHash("sha256").update(data).digest("hex");

async function verifiedFile(path, expectedHash) {
  try {
    return sha256(await readFile(path)) === expectedHash;
  } catch {
    return false;
  }
}

async function extractFile(archivePath, destinationPath, relativePath) {
  await execFileAsync("/usr/bin/unzip", ["-p", archivePath, relativePath], { encoding: "buffer", maxBuffer: 16 * 1024 * 1024 })
    .then(({ stdout }) => writeFile(destinationPath, stdout));
}

async function fetchVerified(url, expectedHash, label) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${label} download returned HTTP ${response.status}`);
  const data = Buffer.from(await response.arrayBuffer());
  const actual = sha256(data);
  if (actual !== expectedHash) {
    throw new Error(`${label} SHA-256 mismatch: expected ${expectedHash}, received ${actual}. Refusing an unpinned core update.`);
  }
  return data;
}

async function hasVerifiedArtifacts() {
  return (await Promise.all([
    verifiedFile(join(destination, mgba.coreName), mgba.coreSha256),
    verifiedFile(join(destination, mgba.licenseName), mgba.licenseSha256),
    verifiedFile(join(destination, melonds.coreName), melonds.coreSha256),
    verifiedFile(join(destination, melonds.licenseName), melonds.licenseSha256),
  ])).every(Boolean);
}

if (process.platform !== "darwin") {
  console.log("GBA_NDS_LIBRETRO=SKIPPED (native macOS cores are not needed on this host)");
  process.exit(0);
}

if (process.arch !== "arm64") {
  throw new Error(`GBA/NDS native cores are pinned for macOS arm64; received ${process.arch}. Add and verify matching upstream cores before packaging this architecture.`);
}

if (!await hasVerifiedArtifacts()) {
  const temporaryDirectory = await mkdtemp(join(tmpdir(), "emulatorrust-gba-nds-"));
  try {
    const mgbaArchive = join(temporaryDirectory, mgba.archiveName);
    const melondsArchive = join(temporaryDirectory, melonds.archiveName);
    await writeFile(mgbaArchive, await fetchVerified(mgba.archiveUrl, mgba.archiveSha256, "mGBA libretro archive"));
    await writeFile(melondsArchive, await fetchVerified(melonds.archiveUrl, melonds.archiveSha256, "melonDS DS libretro archive"));

    const staged = join(temporaryDirectory, "staged");
    await mkdir(staged, { recursive: true });
    await extractFile(mgbaArchive, join(staged, mgba.coreName), mgba.coreName);
    await extractFile(melondsArchive, join(staged, melonds.coreName), melonds.archiveCorePath);
    await writeFile(join(staged, mgba.licenseName), await fetchVerified(mgba.licenseUrl, mgba.licenseSha256, "mGBA license"));
    await writeFile(join(staged, melonds.licenseName), await fetchVerified(melonds.licenseUrl, melonds.licenseSha256, "melonDS DS license"));

    for (const [path, expectedHash, label] of [
      [join(staged, mgba.coreName), mgba.coreSha256, "mGBA core"],
      [join(staged, mgba.licenseName), mgba.licenseSha256, "mGBA license"],
      [join(staged, melonds.coreName), melonds.coreSha256, "melonDS DS core"],
      [join(staged, melonds.licenseName), melonds.licenseSha256, "melonDS DS license"],
    ]) {
      if (!await verifiedFile(path, expectedHash)) throw new Error(`${label} failed its pinned SHA-256 verification.`);
    }

    await rm(destination, { recursive: true, force: true });
    await mkdir(destination, { recursive: true });
    for (const entry of await readdir(staged)) {
      await writeFile(join(destination, entry), await readFile(join(staged, entry)));
    }
  } finally {
    await rm(temporaryDirectory, { recursive: true, force: true });
  }
}

const manifest = {
  platform: "macOS arm64",
  presentation: "Vulkan 1.1 -> bundled MoltenVK -> Metal",
  cores: [mgba, melonds],
};
await writeFile(join(destination, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`GBA_NDS_LIBRETRO=${destination}`);
