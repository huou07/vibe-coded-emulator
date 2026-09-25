import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { validateArchiveMembers, validateManifest, verifyCorePayload } from "../scripts/fetch-android-libretro.mjs";

const nativeRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const manifest = JSON.parse(await readFile(resolve(nativeRoot, "vendor/libretro/android-arm64/manifest.json"), "utf8"));
const digest = bytes => createHash("sha256").update(bytes).digest("hex");

test("Android core bootstrap pins the accepted APK and both ABI-specific core entries", () => {
  const cores = validateManifest(manifest);
  assert.equal(manifest.bootstrapArtifact.releaseTag, "v3.3.0");
  assert.equal(manifest.bootstrapArtifact.sha256, "3fba0a93bca648d6f1d45df23b9838849fedafdae74da4de66b656d36a5c9c29");
  assert.deepEqual(cores.map(core => core.system), ["gba", "nds"]);
  assert.deepEqual(cores.map(core => core.apkEntry), [
    "lib/arm64-v8a/libmgba_libretro_android.so",
    "lib/arm64-v8a/libmelondsds_libretro_android.so",
  ]);
});

test("Android core license files remain byte-identical to their SHA-256 pins", async () => {
  for (const core of manifest.cores) {
    const license = await readFile(resolve(nativeRoot, "vendor/libretro/android-arm64", core.licenseFile));
    assert.equal(digest(license), core.licenseSha256, `${core.system} license digest`);
  }
});

test("bootstrap archive must contain each locked Android core exactly once", () => {
  const core = { system: "gba", apkEntry: "lib/arm64-v8a/libmgba.so" };
  assert.deepEqual(validateArchiveMembers([core], [core.apkEntry]), [core.apkEntry]);
  assert.throws(() => validateArchiveMembers([core], []), /found 0/);
  assert.throws(() => validateArchiveMembers([core], [core.apkEntry, core.apkEntry]), /found 2/);
});

test("bootstrap core payloads fail closed on size or SHA-256 mismatch", () => {
  const bytes = Buffer.from("locked android core fixture");
  const core = { system: "gba", coreSizeBytes: bytes.length, coreSha256: digest(bytes) };
  assert.equal(verifyCorePayload(core, bytes), bytes);
  assert.throws(() => verifyCorePayload(core, Buffer.from("wrong size")), /unexpected size/);
  assert.throws(() => verifyCorePayload({ ...core, coreSha256: "0".repeat(64) }, bytes), /SHA-256 mismatch/);
});
