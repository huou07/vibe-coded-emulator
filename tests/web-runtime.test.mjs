// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Explicit runtime lane: AN3_WEB_RUNTIME=1 node --test tests/web-runtime.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { createServer } from "node:net";
import { WebAdapter } from "../tools/an3ctl/adapters/web.mjs";

const ROOT = resolve(import.meta.dirname, "..");

test("Playwright actions, actual library search/recovery, narrow and desktop evidence", {
  skip: process.env.AN3_WEB_RUNTIME !== "1" ? "explicit Web runtime lane not requested" : false,
  timeout: 180000,
}, async (t) => {
  const scratch = mkdtempSync(resolve(tmpdir(), "vce-web-runtime-"));
  const artifacts = resolve(ROOT, "work/ui-runtime");
  mkdirSync(artifacts, { recursive: true });
  const adapter = new WebAdapter(scratch);
  let server;
  t.after(async () => {
    await adapter.playwright(["close"]).catch(() => {});
    if (server && server.exitCode === null) {
      server.kill("SIGTERM");
      await new Promise(done => {
        const timer = setTimeout(() => { server.kill("SIGKILL"); done(); }, 3000);
        server.once("exit", () => { clearTimeout(timer); done(); });
      });
    }
    rmSync(scratch, { recursive: true, force: true });
  });
  const config = resolve(scratch, "browser.json");
  writeFileSync(config, JSON.stringify({ browser: {
    browserName: "chromium", isolated: true,
    launchOptions: { channel: "chromium", headless: true },
  }}));
  const opened = await adapter.playwright(["open", `--config=${config}`, "about:blank"]);
  assert.equal(opened.code, 0, opened.stderr + opened.stdout);
  assert.doesNotMatch(opened.stdout, /### Error/);
  await adapter.runCode("async page => { await page.context().tracing.start({ screenshots: true, snapshots: true }); return true; }");
  try {
    // Reproduces the old mismatch between the discovery and action DOM lists.
    await adapter.runCode("async page => { await page.setContent(\"<div tabindex=\\\"0\\\">Before</div><span id=\\\"label\\\">Confirm import</span><button aria-labelledby=\\\"label\\\" onclick=\\\"this.removeAttribute('aria-labelledby'); this.textContent='Imported'\\\">Go</button><label for=\\\"q\\\">Project name</label><input id=\\\"q\\\"><button disabled>Blocked</button>\"); return true; }");
    adapter.ensureOpen = async () => {};
    const role = { kind: "role", value: { role: "button", name: "Confirm import" } };
    assert.equal((await adapter.uiQuery({ selector: role })).node.name, "Confirm import");
    await adapter.uiClick({ selector: role });
    assert.equal(await adapter.runCode('async page => page.getByRole("button", { name: "Imported" }).count()'), 1);
    await adapter.uiFill({ selector: { kind: "name", value: "Project name" }, value: "Fixture project" });
    assert.equal((await adapter.uiValue({ selector: { kind: "id", value: "q" } })).value, "Fixture project");
    await assert.rejects(adapter.uiClick({
      selector: { kind: "role", value: { role: "button", name: "Blocked" } }, timeout: 500,
    }), /Timeout|timeout/);

    const listener = createServer();
    await new Promise(done => listener.listen(0, "127.0.0.1", done));
    const port = listener.address().port;
    await new Promise(done => listener.close(done));
    const env = { ...process.env, AN3_HOST: "127.0.0.1", AN3_PORT: String(port),
      AN3_DATA_DIR: resolve(scratch, "data"), AN3_ENVIRONMENT: "staging",
      AN3_ADMIN_NAME: "fixture-admin", AN3_ADMIN_PASSWORD: "synthetic-fixture-only", AN3_COOKIE_SECURE: "0" };
    const seeded = spawnSync("python3", ["-c", `
import app
app.init_db()
app.bootstrap_admin()
with app.db() as conn:
    for slug, title in [("fixture-gba", "Fixture GBA"), ("fixture-nds", "Fixture NDS")]:
        conn.execute("INSERT INTO games (slug,title_vi,title_en,system,published,created_at,updated_at) VALUES (?,?,?,?,1,0,0)", (slug,title,title,"gba" if "gba" in slug else "nds"))
    admin = conn.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
    game = conn.execute("SELECT id FROM games WHERE slug='fixture-gba'").fetchone()
    conn.execute("INSERT INTO comments(user_id,game_id,body,created_at) VALUES(?,?,?,?)", (admin["id"], game["id"], "Synthetic comment to moderate.", 0))
`], { cwd: ROOT, env, encoding: "utf8" });
    assert.equal(seeded.status, 0, seeded.stderr);
    server = spawn("python3", ["app.py"], { cwd: ROOT, env, stdio: "ignore" });
    const url = `http://127.0.0.1:${port}/games`;
    const deadline = Date.now() + 15000;
    let ready = false;
    while (Date.now() < deadline && server.exitCode === null) {
      try { if ((await fetch(url)).ok) { ready = true; break; } } catch {}
      await new Promise(done => setTimeout(done, 100));
    }
    assert.ok(ready, "fixture server must become ready");
    const evidence = await adapter.runCode(`async page => {
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.goto(${JSON.stringify(url)});
      const search = page.getByRole("searchbox", { name: "Search games", exact: true });
      await search.fill("no-such-fixture");
      await page.locator("#libraryNoResults").waitFor({ state: "visible" });
      await page.getByRole("button", { name: "Clear search and filters", exact: true }).click();
      if (await search.inputValue() !== "") throw new Error("search recovery did not clear input");
      await search.fill("Fixture GBA");
      await page.locator('[data-game-slug="fixture-nds"]').first().waitFor({ state: "hidden" });
      const searchTree = await page.locator("#gameSearch").ariaSnapshot();
      if (!searchTree.startsWith(\'- searchbox "Search games"\')) throw new Error("Search name changed after typing: " + searchTree);
      await search.press("Tab");
      if (!(await page.locator("#clearSearch").evaluate(el => el === document.activeElement))) throw new Error("clear button not keyboard reachable");
      await page.keyboard.press("Enter");
      if (await search.inputValue() !== "") throw new Error("keyboard clear did not restore query");
      const geometry = [];
      for (const width of [360, 390, 1440]) {
        await page.setViewportSize({ width, height: 900 });
        await page.screenshot({ path: ${JSON.stringify(artifacts)} + "/library-" + width + ".png", fullPage: true });
        const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
        if (scrollWidth > width) throw new Error("horizontal overflow at " + width + ": " + scrollWidth);
        geometry.push({ width, scrollWidth });
      }
      const ariaSnapshot = await page.locator("main").ariaSnapshot();
      await page.getByRole("link", { name: "Details: Fixture GBA", exact: true }).first().click();
      await page.getByRole("heading", { name: "Fixture GBA", exact: true }).waitFor();
      // Admin comment moderation: the seeded comment is deletable from the real
      // admin detail page, dismissing the confirm keeps it, and accepting the
      // delete reaches the server.
      const origin = new URL(${JSON.stringify(url)}).origin;
      const commentBody = "Synthetic comment to moderate.";
      await page.goto(origin + "/login");
      await page.locator('#authForm input[name="name"]').fill("fixture-admin");
      await page.locator('#authForm input[name="password"]').fill("synthetic-fixture-only");
      await Promise.all([
        page.waitForURL(target => !target.pathname.startsWith("/login")),
        page.locator('#authForm button[type="submit"]').click(),
      ]);
      await page.goto(origin + "/game/fixture-gba");
      const deleteComment = page.getByRole("button", { name: "Delete comment", exact: true });
      if (await deleteComment.count() !== 1) throw new Error("expected one comment delete control");
      if (await page.getByText(commentBody, { exact: true }).count() !== 1) throw new Error("seeded comment not visible to admin");
      // playwright-cli surfaces native dialogs as modal state instead of firing
      // page listeners, so spy on window.confirm to assert the app's own
      // moderation control flow: it must ask, honour a dismiss, and delete on
      // accept. Native dialog chrome is the browser's, not the app's.
      await page.evaluate(() => {
        window.__an3Confirm = { calls: [], result: false };
        window.confirm = message => { window.__an3Confirm.calls.push(message); return window.__an3Confirm.result; };
      });
      await deleteComment.click();
      await page.waitForTimeout(250);
      const confirmState = await page.evaluate(() => window.__an3Confirm);
      if (JSON.stringify(confirmState.calls) !== JSON.stringify(["Delete this comment?"])) {
        throw new Error("unexpected confirm calls: " + JSON.stringify(confirmState.calls));
      }
      if (await page.getByText(commentBody, { exact: true }).count() !== 1) throw new Error("dismissing the confirm deleted the comment");
      await page.evaluate(() => { window.__an3Confirm.result = true; });
      await deleteComment.click();
      await page.locator("article.comment", { hasText: commentBody }).waitFor({ state: "detached" });
      await page.goto(origin + "/game/fixture-gba");
      if (await page.getByText(commentBody, { exact: true }).count() !== 0) throw new Error("comment persisted after delete");
      // Real IndexedDB round-trip: RG-150 asked for the ten-slot/autosave model
      // to be exercised against the browser's own IndexedDB engine, not only the
      // in-memory model. This loads the real QuickSaveManager and checks raw
      // byte round-trips, a fresh manager (restart), slot rejection, and
      // autosave isolation.
      const quickSave = await page.evaluate(async () => {
        if (!window.AN3PlayerRuntime?.QuickSaveManager) {
          await new Promise((resolve, reject) => {
            const script = document.createElement("script");
            script.src = "/static/player-runtime.js";
            script.onload = resolve;
            script.onerror = () => reject(new Error("player-runtime.js did not load"));
            document.head.appendChild(script);
          });
        }
        const {QuickSaveManager, QUICK_SAVE_SLOTS} = window.AN3PlayerRuntime;
        const manager = new QuickSaveManager("browser-save-fixture");
        const bytesFor = slot => new Uint8Array([slot, 0xa5, 0x5a, 200 - slot]).buffer;
        const decode = async record => record ? Array.from(new Uint8Array(await record.state.arrayBuffer())) : null;
        for (const slot of QUICK_SAVE_SLOTS) await manager.put(slot, bytesFor(slot), 1000 + slot);
        const roundTrip = [];
        for (const slot of QUICK_SAVE_SLOTS) roundTrip.push(await decode(await manager.get(slot)));
        const expected = QUICK_SAVE_SLOTS.map(slot => Array.from(new Uint8Array(bytesFor(slot))));
        const rangeErrors = [];
        for (const bad of [0, 11]) {
          try { manager.assertSlot(bad); rangeErrors.push(false); } catch (error) { rangeErrors.push(error instanceof RangeError); }
        }
        const restarted = new QuickSaveManager("browser-save-fixture");
        const restartedSlot7 = await decode(await restarted.get(7));
        await manager.put(1, new Uint8Array([9, 9]).buffer, 5000);
        await manager.putAuto(new Uint8Array([7, 7, 7]).buffer, 6000, "digest-auto");
        const auto = await manager.getAuto();
        const autoBytes = await decode(auto);
        const slot1AfterAuto = await decode(await manager.get(1));
        return {
          slots: QUICK_SAVE_SLOTS,
          roundTripMatches: JSON.stringify(roundTrip) === JSON.stringify(expected),
          restartedSlot7Matches: JSON.stringify(restartedSlot7) === JSON.stringify(Array.from(new Uint8Array(bytesFor(7)))),
          rangeRejected: rangeErrors.every(Boolean),
          autoMatches: JSON.stringify(autoBytes) === JSON.stringify([7, 7, 7]),
          autoIsSeparate: JSON.stringify(slot1AfterAuto) === JSON.stringify([9, 9]),
          autoFlag: auto?.auto === true,
        };
      });
      if (!quickSave.roundTripMatches || !quickSave.restartedSlot7Matches || !quickSave.rangeRejected
          || !quickSave.autoMatches || !quickSave.autoIsSeparate || !quickSave.autoFlag) {
        throw new Error("quick-save IndexedDB round-trip failed: " + JSON.stringify(quickSave));
      }
      if (errors.length) throw new Error(errors.join("\\n"));
      return { geometry, ariaSnapshot, errors, commentModeration: "confirm prompt, dismiss keeps, accept deletes and persists", quickSave, outcome: "search, no-results recovery, keyboard clear, detail navigation, admin comment moderation, real IndexedDB quick saves" };
    }`);
    writeFileSync(resolve(artifacts, "evidence.json"), JSON.stringify({
      source: spawnSync("git", ["rev-parse", "HEAD"], { cwd: ROOT, encoding: "utf8" }).stdout.trim(),
      dirty: spawnSync("git", ["status", "--porcelain"], { cwd: ROOT, encoding: "utf8" }).stdout.trim(),
      classes: ["VERIFIED_SEMANTIC", "VERIFIED_BEHAVIORAL", "VERIFIED_VISUAL"],
      runtime: "Playwright Chromium; synthetic catalog, no ROM/gameplay/native acceptance",
      ...evidence,
    }, null, 2));
    await adapter.runCode("async page => { await page.context().tracing.stop(); return true; }");
  } catch (error) {
    await adapter.runCode(`async page => { await page.context().tracing.stop({ path: ${JSON.stringify(resolve(artifacts, "failure-trace.zip"))} }); return true; }`).catch(() => {});
    throw error;
  }
});
