import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { fetchVerifiedBytes } from "../scripts/build-mgba-core.mjs";

const lock = JSON.parse(await readFile(new URL("../shared/libretro-source-lock.json", import.meta.url), "utf8")).mgba;
const melonds = JSON.parse(await readFile(new URL("../shared/libretro-source-lock.json", import.meta.url), "utf8")).melondsdsMacos;
const macCoreBuilder = await readFile(new URL("../scripts/fetch-gba-nds-libretro.mjs", import.meta.url), "utf8");
const linuxCoreBuilder = await readFile(new URL("../scripts/fetch-linux-gba-nds-libretro.mjs", import.meta.url), "utf8");
const macEdenBuilder = await readFile(new URL("../scripts/build-macos-eden-companion.sh", import.meta.url), "utf8");
const macAutomationBuilder = await readFile(new URL("../scripts/build-macos-automation.sh", import.meta.url), "utf8");
const prepareEdenSource = await readFile(new URL("../scripts/prepare-eden-source.sh", import.meta.url), "utf8");
const tauriConfig = JSON.parse(await readFile(new URL("../src-tauri/tauri.conf.json", import.meta.url), "utf8"));

test("mGBA source and license pins identify immutable upstream content", () => {
  assert.equal(lock.sourceUrl, `https://codeload.github.com/mgba-emu/mgba/tar.gz/${lock.sourceRevision}`);
  assert.ok(!lock.sourceUrl.includes("/latest/"));
  for (const digest of [lock.sourceSha256, lock.licenseSha256]) assert.match(digest, /^[a-f0-9]{64}$/);
});

test("pinned fetch accepts exact bytes and fails closed on changed bytes", async () => {
  const bytes = Buffer.from("pinned fixture bytes");
  const digest = createHash("sha256").update(bytes).digest("hex");
  const fetcher = async url => ({
    ok: true,
    arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
  });
  assert.deepEqual(await fetchVerifiedBytes("https://example.test/pinned", digest, "fixture", fetcher), bytes);
  await assert.rejects(
    fetchVerifiedBytes("https://example.test/pinned", "0".repeat(64), "fixture", fetcher),
    /SHA-256 mismatch/,
  );
});

test("macOS melonDS DS uses the pinned 1.3.1 source at AN3's supported deployment target", () => {
  assert.equal(melonds.version, "1.3.1");
  assert.equal(melonds.sourceUrl, `https://github.com/JesseTG/melonds-ds/tree/${melonds.sourceRevision}`);
  assert.equal(melonds.sourceArchiveUrl, `https://codeload.github.com/JesseTG/melonds-ds/tar.gz/${melonds.sourceRevision}`);
  assert.match(melonds.sourceRevision, /^[a-f0-9]{40}$/);
  assert.match(melonds.sourceSha256, /^[a-f0-9]{64}$/);
  assert.equal(melonds.deploymentTarget, "13.4");
  assert.match(macCoreBuilder, /--target", "melondsds_libretro"/);
  assert.match(macCoreBuilder, /CMAKE_OSX_DEPLOYMENT_TARGET=\$\{melonds\.deploymentTarget\}/);
  assert.doesNotMatch(macCoreBuilder, /buildbot\.libretro\.com\/nightly\/apple\/osx\/arm64\/latest/);
});

test("macOS Eden companion build targets the app's declared minimum", () => {
  const minimum = tauriConfig.bundle?.macOS?.minimumSystemVersion;
  assert.ok(minimum);
  assert.ok(macEdenBuilder.includes(`-DCMAKE_OSX_DEPLOYMENT_TARGET=${minimum}`));
  assert.ok(macEdenBuilder.includes(`export MACOSX_DEPLOYMENT_TARGET=${minimum}`));
  assert.match(macEdenBuilder, /export CARGO_PROFILE_RELEASE_STRIP=none/);
  for (const setting of [
    "-DYUZU_STATIC_BUILD=ON",
    "-DYUZU_USE_BUNDLED_OPENSSL=OFF",
    "-DCPMUTIL_FORCE_BUNDLED=ON",
    "-DHTTPLIB_USE_BROTLI_IF_AVAILABLE=OFF",
    "-framework Carbon -framework AppKit -framework UniformTypeIdentifiers",
  ]) assert.ok(macEdenBuilder.includes(setting), `missing macOS Eden build setting: ${setting}`);
  assert.match(prepareEdenSource, /Pinned Eden Apple static-build OpenSSL default has changed/);
  assert.match(prepareEdenSource, /if\(NOT DEFINED YUZU_USE_BUNDLED_OPENSSL\)/);
});

test("macOS automation build preserves proc-macro metadata and an isolated output bundle", () => {
  assert.match(macAutomationBuilder, /export CARGO_PROFILE_RELEASE_STRIP=none/);
  assert.ok(macAutomationBuilder.includes('mkdir -p "$(dirname "$OUT")"'));
  assert.match(macAutomationBuilder, /CFBundleIdentifier/);
  assert.match(macAutomationBuilder, /\.automation/);
});

test("Linux melonDS DS uses an immutable official v1.3.1 release asset", () => {
  assert.match(linuxCoreBuilder, /github\.com\/JesseTG\/melonds-ds\/releases\/download\/v1\.3\.1\/melondsds_libretro-linux-x86_64-Release\.zip/);
  assert.doesNotMatch(linuxCoreBuilder, /buildbot\.libretro\.com\/nightly\/linux\/x86_64\/latest/);
  assert.match(linuxCoreBuilder, /archiveSha256: "[a-f0-9]{64}"/);
  assert.match(linuxCoreBuilder, /archiveCorePath: "\*\/cores\/melondsds_libretro\.so"/);
  assert.match(linuxCoreBuilder, /coreSha256: "c58d933c6e4d36f5b7a5732325408a6777034d67c227190fbc08fa9c8347071d"/);
});
