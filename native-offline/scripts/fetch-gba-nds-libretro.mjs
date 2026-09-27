import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import { buildPinnedMgbaCore, fetchVerifiedBytes, mgbaSourceLock } from "./build-mgba-core.mjs";

const execFileAsync = promisify(execFile);
const scriptDirectory = resolve(fileURLToPath(new URL(".", import.meta.url)));
const nativeRoot = resolve(scriptDirectory, "..");
const destination = resolve(nativeRoot, "vendor", "libretro", "macos-arm64");

const mgba = {
  system: "gba",
  engine: "mGBA libretro",
  ...mgbaSourceLock,
  coreName: "mgba_libretro.dylib",
};

const melonds = {
  system: "nds",
  engine: "melonDS DS libretro",
  version: "1.3.1",
  // The creator's v1.3.1 macOS release was built with macOS 26 as its
  // deployment target. This compatible arm64 buildbot artifact reports the
  // same 1.3.1 core and targets macOS 11. The buildbot ZIP envelope changes
  // while the core payload stays byte-identical; verify the extracted core
  // SHA-256 below instead of pinning incidental ZIP metadata.
  archiveName: "melondsds_libretro.dylib.zip",
  archiveUrl: "https://buildbot.libretro.com/nightly/apple/osx/arm64/latest/melondsds_libretro.dylib.zip",
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

async function hasVerifiedArtifacts() {
  let mgbaVerified = false;
  try {
    const manifest = JSON.parse(await readFile(join(destination, "manifest.json"), "utf8"));
    const entry = manifest.cores.find(core => core.system === "gba");
    mgbaVerified = entry?.sourceRevision === mgba.sourceRevision
      && entry?.sourceSha256 === mgba.sourceSha256
      && await verifiedFile(join(destination, mgba.coreName), entry.coreSha256);
  } catch {}
  return mgbaVerified && (await Promise.all([
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

let mgbaBuild;
if (!await hasVerifiedArtifacts()) {
  const temporaryDirectory = await mkdtemp(join(tmpdir(), "emulatorrust-gba-nds-"));
  try {
    const melondsArchive = join(temporaryDirectory, melonds.archiveName);
    const melondsResponse = await fetch(melonds.archiveUrl);
    if (!melondsResponse.ok) throw new Error(`melonDS DS libretro archive download returned HTTP ${melondsResponse.status}`);
    await writeFile(melondsArchive, Buffer.from(await melondsResponse.arrayBuffer()));

    const staged = join(temporaryDirectory, "staged");
    await mkdir(staged, { recursive: true });
    mgbaBuild = await buildPinnedMgbaCore(staged, "darwin");
    await extractFile(melondsArchive, join(staged, melonds.coreName), melonds.archiveCorePath);
    await writeFile(join(staged, melonds.licenseName), await fetchVerifiedBytes(melonds.licenseUrl, melonds.licenseSha256, "melonDS DS license"));

    for (const [path, expectedHash, label] of [
      [join(staged, mgba.coreName), mgbaBuild.coreSha256, "mGBA core"],
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
} else {
  const previous = JSON.parse(await readFile(join(destination, "manifest.json"), "utf8"));
  mgbaBuild = previous.cores.find(core => core.system === "gba");
}

const manifest = {
  platform: "macOS arm64",
  presentation: "Vulkan 1.1 -> bundled MoltenVK -> Metal",
  cores: [{ ...mgba, ...mgbaBuild }, melonds],
};
await writeFile(join(destination, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`GBA_NDS_LIBRETRO=${destination}`);
