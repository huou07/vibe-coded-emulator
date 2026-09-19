import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);
const scriptDirectory = resolve(fileURLToPath(new URL(".", import.meta.url)));
const nativeRoot = resolve(scriptDirectory, "..");
const version = "2126.1.1";
const assetName = "azahar-libretro-macos-arm64-2126.1.1.zip";
const assetUrl = `https://github.com/azahar-emu/azahar/releases/download/${version}/${assetName}`;
const sourceUrl = `https://github.com/azahar-emu/azahar/releases/download/${version}/azahar-unified-source-${version}.tar.xz`;
const licenseUrl = `https://raw.githubusercontent.com/azahar-emu/azahar/${version}/license.txt`;
const expectedArchiveSha256 = "9557400c89d463a7d163d925741172173f0c64d8096e5996239fac46eefdffd5";
const expectedCoreSha256 = "90f96cc9b8e6c9570e631fd61d4e8b2ee65de00d2171ffc86068c6eb49b5d5ad";
const expectedLicenseSha256 = "a77e81713ddfe05f9f7f3a3c46de4147f82b5fe9d6e5e24af96e36a6de53f613";
const destination = resolve(nativeRoot, "vendor", "azahar", "macos-arm64");
const coreName = "azahar_libretro.dylib";
const corePath = join(destination, coreName);
const licensePath = join(destination, "LICENSE");

const sha256 = (data) => createHash("sha256").update(data).digest("hex");

async function findFile(directory, name) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const candidate = join(directory, entry.name);
    if (entry.isFile() && entry.name === name) return candidate;
    if (entry.isDirectory()) {
      const found = await findFile(candidate, name);
      if (found) return found;
    }
  }
  return null;
}

async function hasVerifiedArtifacts() {
  try {
    return sha256(await readFile(corePath)) === expectedCoreSha256
      && sha256(await readFile(licensePath)) === expectedLicenseSha256;
  } catch {
    return false;
  }
}

if (process.platform !== "darwin") {
  console.log("AZAHAR_LIBRETRO=SKIPPED (native macOS core is not needed on this host)");
  process.exit(0);
}

if (process.arch !== "arm64") {
  throw new Error(`Azahar ${version} is pinned here for macOS arm64; received ${process.arch}. Add and verify the matching upstream core before packaging this architecture.`);
}

if (!await hasVerifiedArtifacts()) {
  const response = await fetch(assetUrl);
  if (!response.ok) throw new Error(`Azahar core download returned HTTP ${response.status}`);
  const archive = Buffer.from(await response.arrayBuffer());
  const archiveSha256 = sha256(archive);
  if (archiveSha256 !== expectedArchiveSha256) {
    throw new Error(`Azahar archive SHA-256 mismatch: expected ${expectedArchiveSha256}, received ${archiveSha256}`);
  }

  const temporaryDirectory = await mkdtemp(join(tmpdir(), "emulatorrust-azahar-"));
  try {
    const archivePath = join(temporaryDirectory, assetName);
    const unpackedDirectory = join(temporaryDirectory, "unpacked");
    await writeFile(archivePath, archive);
    await mkdir(unpackedDirectory, { recursive: true });
    await execFileAsync("/usr/bin/unzip", ["-q", archivePath, "-d", unpackedDirectory]);
    const unpackedCore = await findFile(unpackedDirectory, coreName);
    if (!unpackedCore) throw new Error(`The verified ${assetName} archive does not contain ${coreName}`);
    const core = await readFile(unpackedCore);
    if (!core.byteLength) throw new Error("The Azahar native core is empty");
    const coreSha256 = sha256(core);
    if (coreSha256 !== expectedCoreSha256) {
      throw new Error(`Azahar core SHA-256 mismatch: expected ${expectedCoreSha256}, received ${coreSha256}`);
    }
    const licenseResponse = await fetch(licenseUrl);
    if (!licenseResponse.ok) throw new Error(`Azahar license download returned HTTP ${licenseResponse.status}`);
    const license = Buffer.from(await licenseResponse.arrayBuffer());
    const licenseSha256 = sha256(license);
    if (licenseSha256 !== expectedLicenseSha256) {
      throw new Error(`Azahar license SHA-256 mismatch: expected ${expectedLicenseSha256}, received ${licenseSha256}`);
    }
    await rm(destination, { recursive: true, force: true });
    await mkdir(destination, { recursive: true });
    await writeFile(corePath, core);
    await writeFile(licensePath, license);
  } finally {
    await rm(temporaryDirectory, { recursive: true, force: true });
  }
}

const manifest = {
  engine: "Azahar libretro",
  version,
  platform: "macOS arm64",
  core: coreName,
  sha256: expectedCoreSha256,
  archiveSha256: expectedArchiveSha256,
  sourceUrl,
  licenseUrl,
  licenseSha256: expectedLicenseSha256,
  license: "GPL-2.0-or-later",
  upstream: "https://github.com/azahar-emu/azahar",
};
await writeFile(join(destination, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`AZAHAR_LIBRETRO=${corePath}`);
