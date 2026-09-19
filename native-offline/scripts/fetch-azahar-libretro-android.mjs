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
const version = "2126.1.1";
const assetName = "azahar-libretro-android-arm64-v8a-2126.1.1.zip";
const assetUrl = `https://github.com/azahar-emu/azahar/releases/download/${version}/${assetName}`;
const sourceUrl = `https://github.com/azahar-emu/azahar/releases/download/${version}/azahar-unified-source-${version}.tar.xz`;
const licenseUrl = `https://raw.githubusercontent.com/azahar-emu/azahar/${version}/license.txt`;
const expectedArchiveSha256 = "9b13b40be733cd182c24be45f59b382660b516d03aca73a4d3549232b91ff70c";
const expectedCoreSha256 = "de4364104250bd6f7b61b06ef4286a4835924382936b89cf4836e0462305c2c3";
const expectedLicenseSha256 = "a77e81713ddfe05f9f7f3a3c46de4147f82b5fe9d6e5e24af96e36a6de53f613";
const destination = resolve(nativeRoot, "vendor", "azahar", "android-arm64");
const coreName = "azahar_libretro_android.so";
const archiveCoreName = "azahar_libretro.so";
const corePath = join(destination, coreName);
const licensePath = join(destination, "LICENSE");
const sha256 = data => createHash("sha256").update(data).digest("hex");

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

async function verified() {
  try { return sha256(await readFile(corePath)) === expectedCoreSha256 && sha256(await readFile(licensePath)) === expectedLicenseSha256; }
  catch { return false; }
}

if (!await verified()) {
  const response = await fetch(assetUrl);
  if (!response.ok) throw new Error(`Azahar Android core download returned HTTP ${response.status}`);
  const archive = Buffer.from(await response.arrayBuffer());
  if (sha256(archive) !== expectedArchiveSha256) throw new Error("Azahar Android archive SHA-256 mismatch");
  const temporaryDirectory = await mkdtemp(join(tmpdir(), "an3-azahar-android-"));
  try {
    const archivePath = join(temporaryDirectory, assetName), unpackedDirectory = join(temporaryDirectory, "unpacked");
    await writeFile(archivePath, archive); await mkdir(unpackedDirectory, { recursive: true });
    await execFileAsync("/usr/bin/unzip", ["-q", archivePath, "-d", unpackedDirectory]);
    const unpackedCore = await findFile(unpackedDirectory, archiveCoreName);
    if (!unpackedCore) throw new Error(`The verified ${assetName} archive has no ${archiveCoreName}`);
    const core = await readFile(unpackedCore);
    if (!core.byteLength || sha256(core) !== expectedCoreSha256) throw new Error("Azahar Android core SHA-256 mismatch");
    const licenseResponse = await fetch(licenseUrl);
    if (!licenseResponse.ok) throw new Error(`Azahar license download returned HTTP ${licenseResponse.status}`);
    const license = Buffer.from(await licenseResponse.arrayBuffer());
    if (sha256(license) !== expectedLicenseSha256) throw new Error("Azahar license SHA-256 mismatch");
    await rm(destination, { recursive: true, force: true }); await mkdir(destination, { recursive: true });
    await writeFile(corePath, core); await writeFile(licensePath, license);
  } finally { await rm(temporaryDirectory, { recursive: true, force: true }); }
}

await writeFile(join(destination, "manifest.json"), `${JSON.stringify({
  engine: "Azahar libretro", version, platform: "Android arm64-v8a", core: coreName,
  sha256: expectedCoreSha256, archiveSha256: expectedArchiveSha256, sourceUrl, licenseUrl,
  licenseSha256: expectedLicenseSha256, license: "GPL-2.0-or-later", upstream: "https://github.com/azahar-emu/azahar"
}, null, 2)}\n`);
console.log(`AZAHAR_ANDROID_LIBRETRO=${corePath}`);
