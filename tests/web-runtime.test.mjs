// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Explicit runtime lane: AN3_WEB_RUNTIME=1 node --test tests/web-runtime.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, statSync } from "node:fs";
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
      // System filter: a real library journey with no ROM. Selecting a system
      // must hide the other system's cards, update the live count, and All must
      // restore them.
      await page.locator('[data-system-filter="gba"]').click();
      if (!(await page.locator('[data-game-slug="fixture-gba"]').first().isVisible())) throw new Error("GBA filter hid the GBA game");
      if (await page.locator('[data-game-slug="fixture-nds"]').first().isVisible()) throw new Error("GBA filter left the NDS game visible");
      const gbaStatus = (await page.locator("#libraryStatus").textContent()) || "";
      if (!gbaStatus.includes("1 matching game")) throw new Error("GBA filter count was: " + JSON.stringify(gbaStatus));
      await page.locator('[data-system-filter="nds"]').click();
      if (!(await page.locator('[data-game-slug="fixture-nds"]').first().isVisible())) throw new Error("NDS filter hid the NDS game");
      if (await page.locator('[data-game-slug="fixture-gba"]').first().isVisible()) throw new Error("NDS filter left the GBA game visible");
      await page.locator('[data-system-filter="all"]').click();
      if (!(await page.locator('[data-game-slug="fixture-gba"]').first().isVisible())) throw new Error("All filter did not restore the GBA game");
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
      // docs/design-system.md contract, asserted in a real browser rather than
      // read by hand: documented token values, the 42px minimum shared-shell
      // control height, and no document-level overflow at 360px. The protected
      // player boundary is excluded, exactly as the design system says.
      await page.setViewportSize({ width: 360, height: 900 });
      await page.goto(${JSON.stringify(url)});
      const design = await page.evaluate(() => {
        // The refresh tokens are declared on the shared shell
        // (body:not(.player-page)), not on :root, so read them from the body.
        const root = getComputedStyle(document.body);
        const token = name => root.getPropertyValue(name).trim().toLowerCase();
        const controls = Array.from(document.querySelectorAll("button, a.button, .icon-button"))
          .filter(element => !element.closest(".player-page") && element.getClientRects().length > 0)
          .map(element => ({
            label: (element.textContent || element.getAttribute("aria-label") || "").trim().slice(0, 40),
            tag: element.tagName.toLowerCase(),
            className: String(element.className || "").slice(0, 60),
            id: element.id || null,
            height: Math.round(element.getBoundingClientRect().height * 100) / 100,
            // docs/design-system.md defines two tiers: primary actions at 42px
            // and a deliberately dense compact tier (chips, table actions,
            // range selector, nav toggle) with a 28px floor.
            tier: element.matches("[data-system-filter], .nav-toggle, .range-option")
              || element.closest(".table-actions, .library-update-notice, .admin-report") ? "compact" : "primary",
          }));
        return {
          tokens: {
            page: token("--ui-bg"), surface: token("--ui-surface"),
            surfaceStrong: token("--ui-surface-strong"), border: token("--ui-border"),
            text: token("--ui-text"), muted: token("--ui-muted"), lime: token("--ui-lime"),
            cyan: token("--ui-cyan"), amber: token("--ui-amber"), danger: token("--ui-danger"),
          },
          controls,
          scrollWidth: document.documentElement.scrollWidth,
          viewport: window.innerWidth,
        };
      });
      const documentedTokens = {
        page: "#07060c", surface: "#131020", surfaceStrong: "#191532", border: "#282238",
        text: "#f3f1fa", muted: "#a5a0b6", lime: "#a855f7", cyan: "#8b5cf6",
        amber: "#c4b5fd", danger: "#f87171",
      };
      for (const [name, value] of Object.entries(documentedTokens)) {
        if (design.tokens[name] !== value) {
          throw new Error("design token " + name + " is " + JSON.stringify(design.tokens[name]) + ", docs/design-system.md documents " + value);
        }
      }
      if (design.scrollWidth > design.viewport) {
        throw new Error("horizontal overflow at " + design.viewport + "px: " + design.scrollWidth);
      }
      const primary = design.controls.filter(control => control.tier === "primary");
      const compact = design.controls.filter(control => control.tier === "compact");
      // A control set that measured nothing would make every bound below pass
      // vacuously. The shared shell always renders primary and compact controls
      // on the library page, so an empty tier is a broken measurement, not a pass.
      if (!primary.length || !compact.length) {
        throw new Error(
          "design contract measured no " + (primary.length ? "compact" : "primary")
          + " controls, so its bounds would pass vacuously",
        );
      }
      const shortPrimary = primary.filter(control => control.height < 42);
      if (shortPrimary.length) {
        throw new Error("primary controls below the documented 42px minimum: " + JSON.stringify(shortPrimary));
      }
      const shortCompact = compact.filter(control => control.height < 28);
      if (shortCompact.length) {
        throw new Error("compact controls below their 28px floor: " + JSON.stringify(shortCompact));
      }
      // The recorded accessibility gap is published as a measurement rather than
      // a sentence: which compact controls sit below the 42px guidance and by how
      // much, so a change in that set is visible in the evidence artifact instead
      // of being re-described by hand. docs/QUALITY.md, docs/design-system.md.
      const compactBelow42 = compact
        .filter(control => control.height < 42)
        .map(control => ({
          height: control.height, tag: control.tag, label: control.label,
          id: control.id, className: control.className,
        }))
        .sort((left, right) => left.height - right.height);
      const designContract = {
        tokens: design.tokens,
        primaryControls: primary.length,
        compactControls: compact.length,
        minPrimaryHeight: Math.min(...primary.map(c => c.height)),
        minCompactHeight: Math.min(...compact.map(c => c.height)),
        compactBelow42,
        scrollWidth: design.scrollWidth,
      };
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
      return { geometry, designContract, ariaSnapshot, errors, commentModeration: "confirm prompt, dismiss keeps, accept deletes and persists", quickSave, outcome: "search, no-results recovery, keyboard clear, system filtering, detail navigation, admin comment moderation, real IndexedDB quick saves, design tokens, control height, 360px no-overflow" };
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

// Browser 3DS: the repaired data-v2 Azahar runtime declares a threaded core and
// WebGL2, and the player keeps its own playable gate (source canvas, first
// video frame, running audio). This case drives that gate on a real browser.
// It needs a lawful user-owned 3DS fixture, so without one it skips with its
// reason instead of reporting a pass: no ROM, firmware, key or save may enter
// the repository or the evidence.
test("browser 3DS reaches the first presented frame with a lawful fixture", {
  skip: process.env.AN3_WEB_RUNTIME !== "1"
    ? "explicit Web runtime lane not requested"
    : (process.env.AN3_3DS_FIXTURE ? false : "no lawful user-owned 3DS fixture (set AN3_3DS_FIXTURE)"),
  timeout: 240000,
}, async (t) => {
  const fixture = resolve(process.env.AN3_3DS_FIXTURE);
  const scratch = mkdtempSync(resolve(tmpdir(), "vce-web-3ds-"));
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

  const listener = createServer();
  await new Promise(done => listener.listen(0, "127.0.0.1", done));
  const port = listener.address().port;
  await new Promise(done => listener.close(done));
  const env = { ...process.env, AN3_HOST: "127.0.0.1", AN3_PORT: String(port),
    AN3_DATA_DIR: resolve(scratch, "data"), AN3_ENVIRONMENT: "staging",
    AN3_ADMIN_NAME: "fixture-admin", AN3_ADMIN_PASSWORD: "synthetic-fixture-only",
    AN3_COOKIE_SECURE: "0", AN3_3DS_FIXTURE: fixture };
  const seeded = spawnSync("python3", ["-c", `
import os, shutil, app
app.init_db(); app.bootstrap_admin()
os.makedirs(app.ROM_DIR, exist_ok=True)
name = "an3-lawful-3ds-homebrew.3dsx"
target = os.path.join(app.ROM_DIR, name)
shutil.copyfile(os.environ["AN3_3DS_FIXTURE"], target)
with app.db() as conn:
    conn.execute("INSERT INTO games (slug,title_vi,title_en,system,rom_path,rom_name,file_size,published,experimental,created_at,updated_at) VALUES (?,?,?,?,?,?,?,1,1,0,0)",
                 ("fixture-3ds-homebrew","Lawful 3DS fixture","Lawful 3DS fixture","3ds",name,name,os.path.getsize(target)))
`], { cwd: ROOT, env, encoding: "utf8" });
  assert.equal(seeded.status, 0, seeded.stderr);
  server = spawn("python3", ["app.py"], { cwd: ROOT, env, stdio: "ignore" });
  const url = `http://127.0.0.1:${port}`;
  const deadline = Date.now() + 20000;
  let ready = false;
  while (Date.now() < deadline && server.exitCode === null) {
    try { if ((await fetch(url + "/health")).ok) { ready = true; break; } } catch {}
    await new Promise(done => setTimeout(done, 150));
  }
  assert.ok(ready, "fixture server must become ready");

  const evidence = await adapter.runCode(`async page => {
    const pageErrors = [];
    page.on("pageerror", error => pageErrors.push(String(error && error.message || error)));
    const badResponses = [];
    page.on("response", response => {
      if (response.url().includes("/emulatorjs/") && response.status() >= 400) {
        badResponses.push(response.status() + " " + response.url().slice(0, 160));
      }
    });
    await page.setViewportSize({ width: 900, height: 900 });
    await page.goto(${JSON.stringify(url)} + "/play/fixture-3ds-homebrew?debug3ds=1");
    // The player clears its own loading overlay only once it has seen the
    // source canvas, a presented frame and a running audio context. Waiting on
    // that is the product's verdict, not a harness guess.
    await page.locator("#loading").waitFor({ state: "hidden", timeout: 90000 });
    const diagnostics = await page.evaluate(() => globalThis.AN3ThreeDsDiagnostics || null);
    const events = (diagnostics?.events || []).map(event => event.name);
    const canvas = page.locator("#game canvas").first();
    await canvas.screenshot({ path: ${JSON.stringify(artifacts)} + "/3ds-frame-a.png" });
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(2500);
    await canvas.screenshot({ path: ${JSON.stringify(artifacts)} + "/3ds-frame-b.png" });
    return { events, pageErrors, badResponses,
      notice: (await page.locator("#playerNotice").textContent()) || "" };
  }`);
  for (const stage of ["SOURCE_CANVAS_AVAILABLE", "FIRST_VIDEO_FRAME", "AUDIO_STARTED", "THREAD_POOL_READY"]) {
    assert.ok(evidence.events.includes(stage), `3DS gate never reached ${stage}: ${JSON.stringify(evidence.events)}`);
  }
  assert.deepEqual(evidence.pageErrors, [], "the 3DS player raised a page error");
  assert.deepEqual(evidence.badResponses, [], "an emulator asset failed to load");
  const [frameA, frameB] = ["3ds-frame-a.png", "3ds-frame-b.png"].map(name => {
    const raw = spawnSync("ffmpeg", ["-v", "error", "-i", resolve(artifacts, name), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
      { maxBuffer: 1 << 28 });
    assert.equal(raw.status, 0, `${name} could not be decoded: ${raw.stderr}`);
    const bytes = raw.stdout;
    const colours = new Set();
    let sum = 0;
    for (let i = 0; i + 2 < bytes.length; i += 3) {
      colours.add((bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2]);
      sum += bytes[i] + bytes[i + 1] + bytes[i + 2];
    }
    return { distinctColours: colours.size, meanLuma: sum / (bytes.length || 1) };
  });
  // A black or uniform rectangle is not a presented frame.
  assert.ok(frameA.distinctColours > 64, `the 3DS canvas presented ${frameA.distinctColours} colours`);
  assert.ok(frameA.meanLuma > 4 && frameA.meanLuma < 251, `the 3DS canvas mean luma was ${frameA.meanLuma}`);
  assert.ok(frameB.distinctColours > 64, `the second 3DS capture presented ${frameB.distinctColours} colours`);
  writeFileSync(resolve(artifacts, "3ds-evidence.json"), JSON.stringify({
    fixture: { name: process.env.AN3_3DS_FIXTURE.split("/").pop(), bytes: statSync(fixture).size },
    gate: evidence.events.filter(name => ["SOURCE_CANVAS_AVAILABLE", "FIRST_VIDEO_FRAME", "AUDIO_STARTED", "THREAD_POOL_READY"].includes(name)),
    frames: { a: frameA, b: frameB },
    notice: evidence.notice,
  }, null, 2));
});
