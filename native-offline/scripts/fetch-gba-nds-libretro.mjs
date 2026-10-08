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
const melondsSourceLock = JSON.parse(await readFile(join(nativeRoot, "shared/libretro-source-lock.json"), "utf8")).melondsdsMacos;

const mgba = {
  system: "gba",
  engine: "mGBA libretro",
  ...mgbaSourceLock,
  coreName: "mgba_libretro.dylib",
};

const melonds = {
  system: "nds",
  engine: "melonDS DS libretro",
  ...melondsSourceLock,
  coreName: "melondsds_libretro.dylib",
};

const sha256 = data => createHash("sha256").update(data).digest("hex");

async function verifiedFile(path, expectedHash) {
  try {
    return sha256(await readFile(path)) === expectedHash;
  } catch {
    return false;
  }
}

async function hasVerifiedArtifacts() {
  let manifest;
  try {
    manifest = JSON.parse(await readFile(join(destination, "manifest.json"), "utf8"));
  } catch {
    return false;
  }
  const mgbaEntry = manifest.cores.find(core => core.system === "gba");
  const melondsEntry = manifest.cores.find(core => core.system === "nds");
  const mgbaVerified = mgbaEntry?.sourceRevision === mgba.sourceRevision
    && mgbaEntry?.sourceSha256 === mgba.sourceSha256
    && await verifiedFile(join(destination, mgba.coreName), mgbaEntry.coreSha256);
  const melondsVerified = melondsEntry?.version === melonds.version
    && await verifiedFile(join(destination, melonds.coreName), melondsEntry.coreSha256)
    && ((melondsEntry.sourceRevision === melonds.sourceRevision && melondsEntry.sourceSha256 === melonds.sourceSha256)
      || melondsEntry.coreSha256 === melonds.cachedCoreSha256);
  return mgbaVerified && melondsVerified && (await Promise.all([
    verifiedFile(join(destination, mgba.licenseName), mgba.licenseSha256),
    verifiedFile(join(destination, melonds.licenseName), melonds.licenseSha256),
  ])).every(Boolean);
}

async function buildPinnedMelondsDsCore(stagingDirectory, temporaryDirectory) {
  const sourceArchive = join(temporaryDirectory, "melondsds-source.tar.gz");
  const sourceDirectory = join(temporaryDirectory, "melondsds-source");
  const buildDirectory = join(temporaryDirectory, "melondsds-build");
  await mkdir(sourceDirectory);
  await writeFile(sourceArchive, await fetchVerifiedBytes(
    melonds.sourceArchiveUrl,
    melonds.sourceSha256,
    "melonDS DS source archive",
  ));
  await execFileAsync("tar", ["-xzf", sourceArchive, "-C", sourceDirectory, "--strip-components=1"]);

  await execFileAsync("cmake", [
    "-S", sourceDirectory, "-B", buildDirectory, "-G", "Ninja",
    "-DCMAKE_BUILD_TYPE=Release",
    "-DCMAKE_OSX_ARCHITECTURES=arm64",
    `-DCMAKE_OSX_DEPLOYMENT_TARGET=${melonds.deploymentTarget}`,
    "-DENABLE_OPENGL=ON",
    "-DENABLE_JIT=ON",
    "-DBUILD_TESTING=OFF",
  ], { maxBuffer: 4 * 1024 * 1024 });
  await execFileAsync("cmake", ["--build", buildDirectory, "--target", "melondsds_libretro", "--parallel", "2"], {
    maxBuffer: 4 * 1024 * 1024,
  });

  const corePath = join(buildDirectory, "src", "libretro", melonds.coreName);
  const coreBytes = await readFile(corePath);
  if (coreBytes.length < 4096) throw new Error("Pinned melonDS DS build produced an implausibly small libretro core");
  const fileDescription = (await execFileAsync("file", [corePath])).stdout;
  if (!/Mach-O 64-bit.*arm64/.test(fileDescription)) throw new Error(`Unexpected melonDS DS binary: ${fileDescription.trim()}`);
  const loadCommands = (await execFileAsync("otool", ["-l", corePath])).stdout;
  const minimumVersion = /cmd LC_BUILD_VERSION[\s\S]*?\bminos\s+([0-9.]+)/.exec(loadCommands)?.[1];
  if (minimumVersion !== melonds.deploymentTarget) {
    throw new Error(`melonDS DS deployment target mismatch: expected ${melonds.deploymentTarget}, received ${minimumVersion ?? "unknown"}`);
  }
  const info = await readFile(join(buildDirectory, "melondsds_libretro.info"), "utf8");
  if (!info.includes(`display_version = "${melonds.version}"`)) {
    throw new Error(`melonDS DS source did not build the pinned ${melonds.version} version`);
  }

  await writeFile(join(stagingDirectory, melonds.coreName), coreBytes);
  await writeFile(join(stagingDirectory, melonds.licenseName), await fetchVerifiedBytes(
    melonds.licenseUrl,
    melonds.licenseSha256,
    "melonDS DS license",
  ));
  const { cachedCoreSha256, ...sourceMetadata } = melonds;
  return { ...sourceMetadata, coreSha256: sha256(coreBytes), buildMethod: "pinned-source" };
}

if (process.platform !== "darwin") {
  console.log("GBA_NDS_LIBRETRO=SKIPPED (native macOS cores are not needed on this host)");
  process.exit(0);
}

if (process.arch !== "arm64") {
  throw new Error(`GBA/NDS native cores are pinned for macOS arm64; received ${process.arch}. Add and verify matching upstream cores before packaging this architecture.`);
}

let mgbaBuild;
let melondsBuild;
if (!await hasVerifiedArtifacts()) {
  const temporaryDirectory = await mkdtemp(join(tmpdir(), "emulatorrust-gba-nds-"));
  try {
    const staged = join(temporaryDirectory, "staged");
    await mkdir(staged, { recursive: true });
    mgbaBuild = await buildPinnedMgbaCore(staged, "darwin");
    melondsBuild = await buildPinnedMelondsDsCore(staged, temporaryDirectory);

    for (const [path, expectedHash, label] of [
      [join(staged, mgba.coreName), mgbaBuild.coreSha256, "mGBA core"],
      [join(staged, mgba.licenseName), mgba.licenseSha256, "mGBA license"],
      [join(staged, melonds.coreName), melondsBuild.coreSha256, "melonDS DS core"],
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
  melondsBuild = previous.cores.find(core => core.system === "nds");
}

const manifest = {
  platform: "macOS arm64",
  presentation: "Vulkan 1.1 -> bundled MoltenVK -> Metal",
  cores: [{ ...mgba, ...mgbaBuild }, melondsBuild],
};
await writeFile(join(destination, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`GBA_NDS_LIBRETRO=${destination}`);
