// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Web adapter. Reuses the verified Playwright capability (playwright-cli) for
// structured DOM/accessibility interaction. It never uses coordinates and never
// reads screenshots to decide what to click.
//
// The dev server is started/stopped by an3ctl itself so an agent can bring the
// target up and read its state without shelling out manually.

import { existsSync, mkdirSync, readFileSync, writeFileSync, unlinkSync } from "node:fs";
import { An3Error, run, stateDir, httpJson } from "../lib/core.mjs";
import { domTreeExpression } from "../lib/domtree.mjs";
import { locatorExpression, queryScript, actionScript } from "../lib/playwright.mjs";

const SESSION = "an3-web";
// System Chrome is the default and the verified target. AN3_PLAYWRIGHT_BROWSER
// selects another playwright-cli browser (for example "chromium" on a host with
// no branded Chrome and no root to install one); it never changes the default.
// When no browser or config is requested explicitly and Chrome is not installed,
// ensureOpen falls back once to the Playwright-bundled Chromium and records it.
const BROWSER = process.env.AN3_PLAYWRIGHT_BROWSER ?? "chrome";
const BROWSER_CONFIG = process.env.AN3_PLAYWRIGHT_CONFIG;
const DEFAULT_PORT = Number(process.env.AN3_WEB_PORT ?? 8099);
const DEFAULT_ENV = process.env.AN3_WEB_ENVIRONMENT ?? "development";

export class WebAdapter {
  constructor(root) {
    this.root = root;
    this.name = "web";
    this.dir = stateDir(root);
    this.statePath = `${this.dir}/web.json`;
    this.pidPath = `${this.dir}/web.pid`;
  }

  readState() {
    try {
      return JSON.parse(readFileSync(this.statePath, "utf8"));
    } catch {
      return null;
    }
  }

  writeState(state) {
    mkdirSync(this.dir, { recursive: true });
    writeFileSync(this.statePath, JSON.stringify(state, null, 2));
  }

  clearState() {
    try {
      unlinkSync(this.statePath);
    } catch {
      /* ignore */
    }
  }

  async available() {
    const playwright = await run("playwright-cli", ["--version"]).catch(() => null);
    const hasPlaywright = playwright?.code === 0;
    const state = this.readState();
    return {
      available: true,
      url: state ? `http://127.0.0.1:${state.port}` : null,
      browser: this.browser ?? BROWSER,
      hasPlaywright,
      note: hasPlaywright ? "playwright-cli present" : "playwright-cli missing (ui.* unavailable)",
    };
  }

  // --- Playwright plumbing -------------------------------------------------

  async playwright(args, { timeoutMs = 120000 } = {}) {
    // Run from the gitignored work dir so playwright-cli's session artifacts
    // (.playwright-cli/*) never appear in the repository root.
    mkdirSync(this.dir, { recursive: true });
    const full = ["-s=" + SESSION, ...args];
    // playwright-cli keeps its per-session daemon, browser profile and launch
    // logs under $XDG_CACHE_HOME/ms-playwright/daemon (or ~/.cache when unset).
    // On a worker host that shared cache is read-only, and an unwritable daemon
    // directory surfaced as "Could not open the web target: EACCES ... mkdir
    // '~/.cache/ms-playwright/daemon'" — a browser-cache permission error
    // reported as if the page had failed. Own the cache the same way the state
    // dir and the port are owned: default it to a private directory beside this
    // run's state, and honour an explicit XDG_CACHE_HOME as the caller's choice.
    const xdgCache = daemonCacheDir(this.dir);
    return run("playwright-cli", full, {
      timeoutMs,
      cwd: this.dir,
      env: xdgCache ? { XDG_CACHE_HOME: xdgCache } : undefined,
    });
  }

  async runCode(script) {
    const dir = `${this.dir}/scripts`;
    mkdirSync(dir, { recursive: true });
    const file = `${dir}/an3ctl-${Date.now()}.mjs`;
    writeFileSync(file, script);
    let result;
    try {
      result = await this.playwright(["run-code", `--filename=${file}`]);
    } finally {
      unlinkSync(file);
    }
    const output = stripAnsi(result.stdout + result.stderr);
    const marker = "### Result";
    const index = output.indexOf(marker);
    if (index === -1) {
      const errorBlock = output.match(/### Error\n([\s\S]*?)(\n###|$)/);
      throw new An3Error("E_ACTION_FAILED", (errorBlock ? errorBlock[1] : output).trim().slice(0, 400));
    }
    const after = output.slice(index + marker.length);
    const end = after.search(/\n###/);
    const raw = (end === -1 ? after : after.slice(0, end)).trim();
    if (!raw) return null;
    const first = tryParse(raw);
    if (typeof first === "string") {
      const second = tryParse(first);
      if (second !== null) return second;
    }
    return first;
  }

  baseUrl(state = this.readState()) {
    const port = state?.port ?? DEFAULT_PORT;
    return `http://127.0.0.1:${port}`;
  }

  async currentUrl() {
    try {
      const url = await this.runCode("async (page) => page.url()");
      return typeof url === "string" ? url : null;
    } catch {
      return null;
    }
  }

  // Navigates only when the requested page differs from the current one, so a
  // multi-step flow (fill -> value -> click) does not reload and lose state.
  async ensureOpen(url, { timeoutMs = 120000 } = {}) {
    const target = url ?? this.baseUrl();
    const current = await this.currentUrl();
    if (current && sameDocument(current, target)) return;
    if (current) {
      const goto = await this.playwright(["goto", target], { timeoutMs });
      if (goto.code === 0 && !/### Error/.test(goto.stdout)) return;
    }
    let last = null;
    for (const candidate of browserCandidates()) {
      const options = candidate.config ? [`--config=${candidate.config}`] : [`--browser=${candidate.browser}`];
      const open = await this.playwright(["open", ...options, target], { timeoutMs });
      if (open.code === 0 && !/### Error/.test(open.stdout)) {
        this.browser = candidate.label;
        return;
      }
      last = open;
      // Fall back from the default Chrome channel only when it is not installed.
      // An explicit AN3_PLAYWRIGHT_BROWSER or AN3_PLAYWRIGHT_CONFIG is authoritative.
      if (!candidate.allowFallback || !isUnavailableBrowser(open)) break;
      await this.playwright(["close"]).catch(() => {});
    }
    throw new An3Error("E_TARGET_UNAVAILABLE", `Could not open the web target: ${browserErrorDetail(last)}`);
  }

  // --- app lifecycle -------------------------------------------------------

  async appStart({ port, environment } = {}) {
    const existing = this.readState();
    if (existing && isAlive(existing.pid)) {
      return { started: false, alreadyRunning: true, ...existing };
    }
    const resolvedPort = Number(port ?? DEFAULT_PORT);
    const env = environment ?? DEFAULT_ENV;
    // Refuse to start on a port that already serves something this state
    // directory does not own. Starting anyway lets a foreign health response
    // validate the new process while it is still racing to bind, which then
    // reports a false success and leaves two servers competing for the port.
    if (await waitForHealth(resolvedPort, 300)) {
      throw new An3Error("E_STATE", `Web port :${resolvedPort} is already serving a target not recorded in ${this.dir}; stop it or choose another port.`);
    }
    mkdirSync(this.dir, { recursive: true });
    const logPath = `${this.dir}/web.log`;
    writeFileSync(logPath, "");
    // A pid file left by an interrupted run must never be mistaken for the
    // process this call is about to start.
    removeFile(this.pidPath);
    // `echo $$` before `exec` records the PID that becomes the server, so a
    // wrapper shell exiting can never leave a stale PID behind.
    const script = `cd ${shellQuote(this.root)} && echo $$ > ${shellQuote(this.pidPath)} && exec python3 app.py >> ${shellQuote(logPath)} 2>&1`;
    await run("bash", ["-lc", `nohup bash -lc ${shellQuote(script)} >/dev/null 2>&1 & echo $!`], {
      env: { AN3_PORT: String(resolvedPort), AN3_ENVIRONMENT: env },
    });
    let pid = 0;
    for (let attempt = 0; attempt < 20 && !pid; attempt += 1) {
      await sleep(100);
      try {
        pid = Number(readFileSync(this.pidPath, "utf8").trim());
      } catch {
        pid = 0;
      }
    }
    const state = { pid, port: resolvedPort, environment: env, logPath, startedAt: new Date().toISOString() };
    const health = await waitForHealth(resolvedPort, 20000);
    if (!health || !isAlive(pid)) {
      // Never orphan a server this call started but could not validate: a leaked
      // listener owns the port and makes every later run collide or skip.
      await reap(pid);
      removeFile(this.pidPath);
      const tail = existsSync(logPath) ? readFileSync(logPath, "utf8").split("\n").slice(-6).join("\n") : "";
      this.clearState();
      throw new An3Error("E_TARGET_UNAVAILABLE", `Web target did not start on :${resolvedPort}${health ? " (recorded process exited; the port may already be in use)" : ""}`, { logTail: tail });
    }
    this.writeState(state);
    return { started: true, ...state, health };
  }

  async appStop() {
    const state = this.readState();
    // Recover a pid file whose state was cleared by a failed start, so a leaked
    // server can still be stopped by the next `app stop`.
    const recordedPid = state?.pid ?? readPidFile(this.pidPath);
    if (!state && !isAlive(recordedPid)) {
      removeFile(this.pidPath);
      return { stopped: false, reason: "no recorded web target" };
    }
    await this.playwright(["close"]).catch(() => {});
    await reap(recordedPid);
    this.clearState();
    removeFile(this.pidPath);
    return { stopped: true, pid: recordedPid ?? null };
  }

  async appState() {
    const state = this.readState();
    if (!state) return { running: false };
    const health = await waitForHealth(state.port, 2000);
    return { running: isAlive(state.pid), pid: state.pid, port: state.port, url: this.baseUrl(state), health };
  }

  // --- structured UI -------------------------------------------------------

  ensureUrlPath(opts) {
    const base = this.baseUrl();
    if (opts.url) return opts.url;
    if (opts.path) return base + (opts.path.startsWith("/") ? opts.path : `/${opts.path}`);
    return null;
  }

  async uiTree(opts) {
    const url = this.ensureUrlPath(opts);
    await this.ensureOpen(url);
    const limit = Number(opts.limit ?? 120);
    const tree = await this.runCode(`async (page) => {\n  return await page.evaluate(() => ${domTreeExpression(limit)});\n}`);
    const ariaSnapshot = await this.runCode("async (page) => page.locator(\"body\").ariaSnapshot()");
    return { ...tree, limit, browser: this.browser ?? BROWSER, ariaSnapshot, legacyNodes: true, semanticsAuthority: "Playwright ariaSnapshot" };
  }

  async locate(opts) {
    const url = this.ensureUrlPath(opts);
    await this.ensureOpen(url);
    return this.runCode(queryScript(opts.selector, opts.nth ?? 0));
  }

  async uiQuery(opts) {
    const result = await this.locate(opts);
    if (!result?.found) {
      throw new An3Error("E_NOT_FOUND", `No element matched ${describeSelector(opts.selector)}`, { selector: opts.selector });
    }
    return result;
  }

  async uiAction(opts, action) {
    const located = await this.locate(opts);
    if (!located?.found) {
      throw new An3Error("E_NOT_FOUND", `No element matched ${describeSelector(opts.selector)}`, { selector: opts.selector });
    }
    const result = await this.runCode(actionScript(opts.selector, action, opts));
    if (!result?.performed) {
      throw new An3Error("E_ACTION_FAILED", `Action ${action} did not run on ${describeSelector(opts.selector)}`, { selector: opts.selector, result });
    }
    return result;
  }

  async uiClick(opts) {
    return this.uiAction(opts, "click");
  }
  async uiFill(opts) {
    return this.uiAction(opts, "fill");
  }
  async uiPress(opts) {
    const url = this.ensureUrlPath(opts);
    await this.ensureOpen(url);
    const key = opts.key;
    if (!key) throw new An3Error("E_USAGE", "--key is required for ui press");
    if (opts.selector) {
      return this.uiAction({ ...opts, url }, "press");
    }
    const result = await this.runCode(`async (page) => {\n  await page.keyboard.press(${JSON.stringify(key)});\n  return JSON.stringify({ performed: true, key: ${JSON.stringify(key)} });\n}`);
    return result;
  }
  async uiSelect(opts) {
    return this.uiAction(opts, "select");
  }
  async uiCheck(opts) {
    return this.uiAction(opts, "check");
  }

  async uiText(opts) {
    const located = await this.uiQuery(opts);
    if (!located?.found) throw new An3Error("E_NOT_FOUND", `No element matched ${describeSelector(opts.selector)}`);
    return { text: located.node?.name ?? null, node: located.node };
  }

  async uiValue(opts) {
    const located = await this.locate(opts);
    if (!located?.found) {
      throw new An3Error("E_NOT_FOUND", `No element matched ${describeSelector(opts.selector)}`, { selector: opts.selector });
    }
    const { one } = locatorExpression(opts.selector, opts.nth ?? 0);
    const script = `async (page) => {
      const locator = ${one};
      return { found: true, value: await locator.evaluate(el => "value" in el ? String(el.value) : (el.innerText || "").trim()) };
    }`;
    const result = await this.runCode(script);
    if (!result?.found) throw new An3Error("E_NOT_FOUND", `No element matched ${describeSelector(opts.selector)}`);
    return result;
  }

  async uiWait(opts) {
    const timeoutMs = Number(opts.timeout ?? 10000);
    const deadline = Date.now() + timeoutMs;
    const selector = opts.selector;
    let last = null;
    while (Date.now() < deadline) {
      last = await this.locate(opts);
      if (last?.found && last.node?.visible) return { appeared: true, waitedMs: timeoutMs - (deadline - Date.now()), node: last.node };
      await sleep(250);
    }
    throw new An3Error("E_TIMEOUT", `Element ${describeSelector(selector)} did not appear within ${timeoutMs}ms`, { last });
  }

  async logs({ tail = 200 } = {}) {
    const state = this.readState();
    if (!state?.logPath || !existsSync(state.logPath)) {
      return { lines: [], logPath: state?.logPath ?? null };
    }
    const content = readFileSync(state.logPath, "utf8").split("\n");
    return { lines: content.slice(-Number(tail)).filter(Boolean), logPath: state.logPath };
  }
}

// The private XDG cache root for playwright-cli's daemon, or null when the
// caller already selected one. Kept separate from the state dir so `app stop`
// and a later run resolve the same daemon without exposing it as an3ctl state.
function daemonCacheDir(dir) {
  if (process.env.XDG_CACHE_HOME) return null;
  return `${dir}/playwright-cache`;
}

function sameDocument(a, b) {
  try {
    const left = new URL(a);
    const right = new URL(b);
    return left.origin === right.origin && left.pathname === right.pathname && left.search === right.search;
  } catch {
    return a === b;
  }
}

function tryParse(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function describeSelector(selector) {
  if (!selector) return "(no selector)";
  if (selector.kind === "role") return `role=${selector.value.role}${selector.value.name ? ` name~${selector.value.name}` : ""}`;
  return `${selector.kind}=${selector.value}`;
}

function stripAnsi(text) {
  return String(text).replace(/\u001b\[[0-9;]*m/g, "");
}

// Browser attempts in order. An explicit browser/config is authoritative and is
// tried alone; otherwise Chrome is attempted first and, if it is genuinely not
// installed, the Playwright-bundled Chromium is tried once.
function browserCandidates() {
  if (BROWSER_CONFIG) return [{ config: BROWSER_CONFIG, label: "config", allowFallback: false }];
  if (process.env.AN3_PLAYWRIGHT_BROWSER) {
    const browser = process.env.AN3_PLAYWRIGHT_BROWSER;
    return [{ browser, label: browser, allowFallback: false }];
  }
  return [
    { browser: "chrome", label: "chrome", allowFallback: true },
    { browser: "chromium", label: "chromium", allowFallback: false },
  ];
}

// Playwright reports a missing channel as `[PlaywrightError: Chromium
// distribution 'chrome' is not found at ...]`, buried in a daemon stack trace.
// Surface that sentence instead of the unreadable stack head.
function browserErrorDetail(result) {
  const text = stripAnsi(`${result?.stderr ?? ""}\n${result?.stdout ?? ""}`);
  const match = text.match(/\[PlaywrightError:\s*([^\]]*)\]/);
  if (match) return match[1].replace(/\s+/g, " ").trim().slice(0, 300);
  const lines = text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("at ") && !line.startsWith("/") && line !== "^");
  return (lines.slice(0, 3).join(" ") || "unknown browser launch error").slice(0, 300);
}

function isUnavailableBrowser(result) {
  const detail = browserErrorDetail(result);
  return /is not found at|Executable doesn't exist|distribution .*not found|playwright install|run "?npx playwright install/i.test(detail);
}

async function reap(pid) {
  if (!isAlive(pid)) return;
  try {
    process.kill(pid, "SIGTERM");
  } catch {
    return;
  }
  await sleep(500);
  if (isAlive(pid)) {
    try {
      process.kill(pid, "SIGKILL");
    } catch {
      /* ignore */
    }
  }
}

function removeFile(path) {
  try {
    unlinkSync(path);
  } catch {
    /* ignore */
  }
}

function readPidFile(path) {
  try {
    return Number(readFileSync(path, "utf8").trim()) || 0;
  } catch {
    return 0;
  }
}

function shellQuote(value) {
  return `'${String(value).replace(/'/g, `'\\''`)}'`;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isAlive(pid) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function waitForHealth(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      return await httpJson(port, "/health");
    } catch {
      await sleep(250);
    }
  }
  return null;
}
