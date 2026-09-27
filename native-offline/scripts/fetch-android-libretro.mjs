import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { mkdir, readFile, rename, unlink, writeFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);
const scriptDirectory = resolve(fileURLToPath(new URL(".", import.meta.url)));
const nativeRoot = resolve(scriptDirectory, "..");
const vendorDirectory = join(nativeRoot, "vendor/libretro/android-arm64");
const manifestPath = join(vendorDirectory, "manifest.json");
const defaultCacheDirectory = join(nativeRoot, "work/dependency-cache");
const sha256 = bytes => createHash("sha256").update(bytes).digest("hex");

async function hashFile(path) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
}

function requireHash(value, label) {
  if (!/^[a-f0-9]{64}$/.test(value ?? "")) throw new Error(`${label} SHA-256 pin is invalid`);
}

export function validateManifest(manifest) {
  const bootstrap = manifest?.bootstrapArtifact;
  if (!/^v\d+\.\d+\.\d+$/.test(bootstrap?.releaseTag ?? "")) throw new Error("Android core bootstrap release tag is invalid");
  if (!/^[A-Za-z0-9._-]+\.apk$/.test(bootstrap?.assetName ?? "")) throw new Error("Android core bootstrap APK filename is invalid");
  requireHash(bootstrap?.sha256, "Android core bootstrap APK");

  const expectedSystems = ["gba", "nds"];
  const cores = expectedSystems.map(system => manifest.cores?.find(core => core.system === system));
  if (cores.some(core => !core) || manifest.cores.filter(core => expectedSystems.includes(core.system)).length !== expectedSystems.length) {
    throw new Error("Android core manifest must define exactly one GBA and one NDS core");
  }

  for (const core of cores) {
    if (!/^[A-Za-z0-9._-]+\.so$/.test(core.coreName ?? "")) throw new Error(`${core.system} core filename is invalid`);
    requireHash(core.coreSha256, `${core.system} core`);
    if (!Number.isSafeInteger(core.coreSizeBytes) || core.coreSizeBytes < 1) throw new Error(`${core.system} core size pin is invalid`);
    const expectedEntry = `lib/${manifest.abi?.androidAbi}/lib${core.coreName}`;
    if (core.apkEntry !== expectedEntry) throw new Error(`${core.system} APK entry does not match its ABI/core filename`);
    if (!/^[A-Za-z0-9._-]+\.txt$/.test(core.licenseFile ?? "")) throw new Error(`${core.system} license filename is invalid`);
    requireHash(core.licenseSha256, `${core.system} license`);
  }
  return cores;
}

export function validateArchiveMembers(cores, archiveMembers) {
  return cores.map(core => {
    const count = archiveMembers.filter(member => member === core.apkEntry).length;
    if (count !== 1) throw new Error(`${core.system} core must occur exactly once in the bootstrap APK; found ${count}`);
    return core.apkEntry;
  });
}

export function verifyCorePayload(core, bytes) {
  if (!Buffer.isBuffer(bytes) || bytes.length !== core.coreSizeBytes) throw new Error(`${core.system} core has an unexpected size`);
  const actual = sha256(bytes);
  if (actual !== core.coreSha256) throw new Error(`${core.system} core SHA-256 mismatch: expected ${core.coreSha256}, received ${actual}`);
  return bytes;
}

async function readOptional(path) {
  try {
    return await readFile(path);
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

async function writeIfMissing(path, bytes, expectedHash, label) {
  const existing = await readOptional(path);
  if (existing) {
    if (sha256(existing) !== expectedHash) throw new Error(`${label} already exists with an unexpected SHA-256: ${path}`);
    return;
  }
  await mkdir(dirname(path), { recursive: true });
  const temporaryPath = `${path}.tmp-${process.pid}`;
  try {
    await writeFile(temporaryPath, bytes, { flag: "wx" });
    await rename(temporaryPath, path);
  } finally {
    await unlink(temporaryPath).catch(() => {});
  }
}

async function readManifest() {
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  return { manifest, cores: validateManifest(manifest) };
}

async function verifyLicenses(cores) {
  for (const core of cores) {
    const path = join(vendorDirectory, core.licenseFile);
    const bytes = await readFile(path);
    if (sha256(bytes) !== core.licenseSha256) throw new Error(`${core.system} license SHA-256 mismatch: ${path}`);
  }
}

async function extractFromApk(apkPath, cacheDirectory, manifest, cores) {
  const { assetName, releaseTag, sha256: expectedApkSha256 } = manifest.bootstrapArtifact;
  const actualApkSha256 = await hashFile(apkPath);
  if (actualApkSha256 !== expectedApkSha256) {
    throw new Error(`Android bootstrap APK SHA-256 mismatch for ${releaseTag}/${assetName}: expected ${expectedApkSha256}, received ${actualApkSha256}`);
  }

  const listing = await execFileAsync("unzip", ["-Z1", apkPath], { maxBuffer: 16 * 1024 * 1024 });
  const members = listing.stdout.split(/\r?\n/).filter(Boolean);
  const coreEntries = validateArchiveMembers(cores, members);
  const extracted = [];
  for (let index = 0; index < cores.length; index += 1) {
    const core = cores[index];
    const result = await execFileAsync("unzip", ["-p", apkPath, coreEntries[index]], { encoding: "buffer", maxBuffer: 32 * 1024 * 1024 });
    extracted.push(verifyCorePayload(core, result.stdout));
  }

  await verifyLicenses(cores);
  for (let index = 0; index < cores.length; index += 1) {
    const core = cores[index];
    await writeIfMissing(join(cacheDirectory, core.coreSha256), extracted[index], core.coreSha256, `${core.system} cache core`);
    await writeIfMissing(join(vendorDirectory, core.coreName), extracted[index], core.coreSha256, `${core.system} vendor core`);
  }
}

async function stageVerifiedCores(cacheDirectory, manifest, cores) {
  await verifyLicenses(cores);
  for (const core of cores) {
    const vendorPath = join(vendorDirectory, core.coreName);
    const vendorBytes = await readOptional(vendorPath);
    if (vendorBytes) {
      verifyCorePayload(core, vendorBytes);
      continue;
    }
    const cachedBytes = await readOptional(join(cacheDirectory, core.coreSha256));
    if (!cachedBytes) {
      throw new Error(`Missing verified ${core.system} Android core. Restore the dependency cache or set AN3_ANDROID_LIBRETRO_BOOTSTRAP_APK to the pinned ${manifest.bootstrapArtifact.releaseTag} APK.`);
    }
    verifyCorePayload(core, cachedBytes);
    await writeIfMissing(vendorPath, cachedBytes, core.coreSha256, `${core.system} vendor core`);
  }
}

function parseArguments(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    if (flag === "--apk" || flag === "--cache-dir") {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error(`${flag} requires a path`);
      options[flag === "--apk" ? "apkPath" : "cacheDirectory"] = resolve(value);
      index += 1;
    } else {
      throw new Error(`Unknown option: ${flag}`);
    }
  }
  return options;
}

async function main(argv = process.argv.slice(2)) {
  const options = parseArguments(argv);
  const { manifest, cores } = await readManifest();
  const cacheDirectory = options.cacheDirectory ?? defaultCacheDirectory;
  const apkPath = options.apkPath ?? process.env.AN3_ANDROID_LIBRETRO_BOOTSTRAP_APK;
  if (apkPath) await extractFromApk(apkPath, cacheDirectory, manifest, cores);
  else await stageVerifiedCores(cacheDirectory, manifest, cores);
  console.log(`ANDROID_LIBRETRO_CORES=VERIFIED systems=${cores.map(core => core.system).join(",")}`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
