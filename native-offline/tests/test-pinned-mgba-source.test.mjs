import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { fetchVerifiedBytes } from "../scripts/build-mgba-core.mjs";

const lock = JSON.parse(await readFile(new URL("../shared/libretro-source-lock.json", import.meta.url), "utf8")).mgba;
const melonds = JSON.parse(await readFile(new URL("../shared/libretro-source-lock.json", import.meta.url), "utf8")).melondsdsMacos;
const macCoreBuilder = await readFile(new URL("../scripts/fetch-gba-nds-libretro.mjs", import.meta.url), "utf8");

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
