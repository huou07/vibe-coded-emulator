import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, writeFile, copyFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);
const scripts = resolve(fileURLToPath(new URL(".", import.meta.url)));
const nativeRoot = resolve(scripts, "..");
export const mgbaSourceLock = JSON.parse(await readFile(join(nativeRoot, "shared/libretro-source-lock.json"), "utf8")).mgba;
const lock = mgbaSourceLock;
const sha256 = bytes => createHash("sha256").update(bytes).digest("hex");

export async function fetchVerifiedBytes(url, expectedHash, label, fetcher = fetch) {
  if (!/^https:\/\//.test(url)) throw new Error(`${label} URL must use HTTPS`);
  if (!/^[a-f0-9]{64}$/.test(expectedHash)) throw new Error(`${label} SHA-256 pin is invalid`);
  const response = await fetcher(url);
  if (!response.ok) throw new Error(`${label} download returned HTTP ${response.status}`);
  const bytes = Buffer.from(await response.arrayBuffer());
  const actual = sha256(bytes);
  if (actual !== expectedHash) throw new Error(`${label} SHA-256 mismatch: expected ${expectedHash}, received ${actual}`);
  return bytes;
}

export async function buildPinnedMgbaCore(stagingDirectory, platform = process.platform) {
  if (platform !== "darwin" && platform !== "linux") throw new Error(`Unsupported mGBA build platform: ${platform}`);
  if (platform === "darwin" && process.arch !== "arm64") throw new Error(`mGBA macOS build requires arm64; received ${process.arch}`);
  if (platform === "linux" && process.arch !== "x64") throw new Error(`mGBA Linux build requires x64; received ${process.arch}`);

  const temporary = await mkdtemp(join(tmpdir(), "an3-pinned-mgba-"));
  try {
    const archivePath = join(temporary, "mgba-source.tar.gz");
    const sourceDirectory = join(temporary, "source");
    const buildDirectory = join(temporary, "build");
    await mkdir(sourceDirectory);
    await writeFile(archivePath, await fetchVerifiedBytes(lock.sourceUrl, lock.sourceSha256, "mGBA source archive"));
    await execFileAsync("tar", ["-xzf", archivePath, "-C", sourceDirectory, "--strip-components=1"]);

    const cmakeArgs = [
      "-S", sourceDirectory, "-B", buildDirectory,
      "-DCMAKE_BUILD_TYPE=Release",
      "-DLIBMGBA_ONLY=ON", "-DBUILD_LIBRETRO=ON",
      "-DBUILD_QT=OFF", "-DBUILD_SDL=OFF",
      "-DUSE_FFMPEG=OFF", "-DUSE_LIBZIP=OFF", "-DUSE_MINIZIP=OFF",
      "-DUSE_EPOXY=OFF", "-DENABLE_SCRIPTING=OFF",
    ];
    if (platform === "darwin") cmakeArgs.push("-DCMAKE_OSX_ARCHITECTURES=arm64", "-DCMAKE_OSX_DEPLOYMENT_TARGET=13.4");
    await execFileAsync("cmake", cmakeArgs, { maxBuffer: 4 * 1024 * 1024 });
    await execFileAsync("cmake", ["--build", buildDirectory, "--target", "mgba_libretro", "--parallel", "2"], { maxBuffer: 4 * 1024 * 1024 });

    const coreName = `mgba_libretro.${platform === "darwin" ? "dylib" : "so"}`;
    const corePath = join(buildDirectory, coreName);
    const coreBytes = await readFile(corePath);
    if (coreBytes.length < 4096) throw new Error("Pinned mGBA build produced an implausibly small libretro core");
    await mkdir(stagingDirectory, { recursive: true });
    await copyFile(corePath, join(stagingDirectory, coreName));
    const license = await fetchVerifiedBytes(lock.licenseUrl, lock.licenseSha256, "mGBA license");
    await writeFile(join(stagingDirectory, lock.licenseName), license);
    return {
      coreName,
      coreSha256: sha256(coreBytes),
      sourceRevision: lock.sourceRevision,
      sourceUrl: lock.sourceUrl,
      sourceSha256: lock.sourceSha256,
      licenseName: lock.licenseName,
      licenseSha256: lock.licenseSha256,
      version: lock.version,
    };
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}
