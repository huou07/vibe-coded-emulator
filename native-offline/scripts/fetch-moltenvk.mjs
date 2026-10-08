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
const version = "1.4.2";
const assetName = "MoltenVK-macos.tar";
const assetUrl = `https://github.com/KhronosGroup/MoltenVK/releases/download/v${version}/${assetName}`;
const expectedArchiveSha256 = "f95765a6229cb7b915990a2890ce12ebe36a730b021545d3d52ae69ce4c4024e";
const expectedLibrarySha256 = "aef00b13bcc808adf15b85bef9ae67393d92be7ed5dfe41cad16fa809e4a4c5f";
const destination = resolve(nativeRoot, "vendor", "moltenvk", "macos-arm64");
const libraryName = "libMoltenVK.dylib";
const libraryPath = join(destination, libraryName);

const sha256 = data => createHash("sha256").update(data).digest("hex");

async function findDirectory(directory, name) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const candidate = join(directory, entry.name);
    if (entry.isDirectory() && entry.name === name) return candidate;
    if (entry.isDirectory()) {
      const found = await findDirectory(candidate, name);
      if (found) return found;
    }
  }
  return null;
}

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

async function hasVerifiedRuntime() {
  try {
    await Promise.all([
      readFile(join(destination, "include", "vulkan", "vulkan.h")),
      readFile(join(destination, "include", "vk_video", "vulkan_video_codecs_common.h")),
      readFile(join(destination, "LICENSE")),
    ]);
    return sha256(await readFile(libraryPath)) === expectedLibrarySha256;
  } catch {
    return false;
  }
}

if (process.platform !== "darwin") {
  console.log("MOLTENVK=SKIPPED (the macOS Vulkan runtime is not needed on this host)");
  process.exit(0);
}

if (process.arch !== "arm64") {
  throw new Error(`MoltenVK ${version} is pinned here for macOS arm64; received ${process.arch}. Add and verify the matching runtime before packaging this architecture.`);
}

if (!await hasVerifiedRuntime()) {
  const response = await fetch(assetUrl);
  if (!response.ok) throw new Error(`MoltenVK download returned HTTP ${response.status}`);
  const archive = Buffer.from(await response.arrayBuffer());
  const archiveSha256 = sha256(archive);
  if (archiveSha256 !== expectedArchiveSha256) {
    throw new Error(`MoltenVK archive SHA-256 mismatch: expected ${expectedArchiveSha256}, received ${archiveSha256}`);
  }

  const temporaryDirectory = await mkdtemp(join(tmpdir(), "emulatorrust-moltenvk-"));
  try {
    const archivePath = join(temporaryDirectory, assetName);
    const unpackedDirectory = join(temporaryDirectory, "unpacked");
    await writeFile(archivePath, archive);
    await mkdir(unpackedDirectory, { recursive: true });
    await execFileAsync("/usr/bin/tar", ["-xf", archivePath, "-C", unpackedDirectory]);
    const runtime = await findFile(unpackedDirectory, libraryName);
    const headers = await findDirectory(unpackedDirectory, "vulkan");
    const videoHeaders = await findDirectory(unpackedDirectory, "vk_video");
    const license = await findFile(unpackedDirectory, "LICENSE");
    if (!runtime || !headers || !videoHeaders || !license) throw new Error(`The verified ${assetName} archive is missing its runtime, Vulkan headers, video headers, or license.`);
    const library = await readFile(runtime);
    const librarySha256 = sha256(library);
    if (librarySha256 !== expectedLibrarySha256) {
      throw new Error(`MoltenVK library SHA-256 mismatch: expected ${expectedLibrarySha256}, received ${librarySha256}`);
    }
    await rm(destination, { recursive: true, force: true });
    await mkdir(join(destination, "include"), { recursive: true });
    await writeFile(libraryPath, library);
    await cp(headers, join(destination, "include", "vulkan"), { recursive: true });
    await cp(videoHeaders, join(destination, "include", "vk_video"), { recursive: true });
    await cp(license, join(destination, "LICENSE"));
  } finally {
    await rm(temporaryDirectory, { recursive: true, force: true });
  }
}

const manifest = {
  runtime: "MoltenVK",
  version,
  platform: "macOS arm64",
  library: libraryName,
  sha256: expectedLibrarySha256,
  archiveSha256: expectedArchiveSha256,
  license: "Apache-2.0",
  upstream: "https://github.com/KhronosGroup/MoltenVK",
  release: `https://github.com/KhronosGroup/MoltenVK/releases/tag/v${version}`,
};
await writeFile(join(destination, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`MOLTENVK=${libraryPath}`);
