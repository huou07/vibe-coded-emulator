import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { fetchVerifiedBytes } from "../scripts/build-mgba-core.mjs";

const lock = JSON.parse(await readFile(new URL("../shared/libretro-source-lock.json", import.meta.url), "utf8")).mgba;

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
