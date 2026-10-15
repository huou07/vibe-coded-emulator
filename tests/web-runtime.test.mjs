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
with app.db() as conn:
    for slug, title in [("fixture-gba", "Fixture GBA"), ("fixture-nds", "Fixture NDS")]:
        conn.execute("INSERT INTO games (slug,title_vi,title_en,system,published,created_at,updated_at) VALUES (?,?,?,?,1,0,0)", (slug,title,title,"gba" if "gba" in slug else "nds"))
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
      if (errors.length) throw new Error(errors.join("\\n"));
      return { geometry, ariaSnapshot, errors, outcome: "search, no-results recovery, keyboard clear, detail navigation" };
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
