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
import { domTreeExpression, locateExpression } from "../lib/domtree.mjs";

const SESSION = "an3-web";
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
    const playwright = await run("bash", ["-lc", "command -v playwright-cli"]).catch(() => null);
    const hasPlaywright = playwright?.code === 0;
    const state = this.readState();
    return {
      available: true,
      url: state ? `http://127.0.0.1:${state.port}` : null,
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
    return run("playwright-cli", full, { timeoutMs, cwd: this.dir });
  }

  async runCode(script) {
    const dir = `${this.dir}/scripts`;
    mkdirSync(dir, { recursive: true });
    const file = `${dir}/an3ctl-${Date.now()}.mjs`;
    writeFileSync(file, script);
    const result = await this.playwright(["run-code", `--filename=${file}`]);
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
    const open = await this.playwright(["open", "--browser=chrome", target], { timeoutMs });
    if (open.code !== 0 || /### Error/.test(open.stdout)) {
      throw new An3Error("E_TARGET_UNAVAILABLE", `Could not open the web target: ${(open.stderr || open.stdout).trim().slice(0, 300)}`);
    }
  }

  // --- app lifecycle -------------------------------------------------------

  async appStart({ port, environment } = {}) {
    const existing = this.readState();
    if (existing && isAlive(existing.pid)) {
      return { started: false, alreadyRunning: true, ...existing };
    }
    const resolvedPort = Number(port ?? DEFAULT_PORT);
    const env = environment ?? DEFAULT_ENV;
    mkdirSync(this.dir, { recursive: true });
    const logPath = `${this.dir}/web.log`;
    writeFileSync(logPath, "");
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
      const tail = existsSync(logPath) ? readFileSync(logPath, "utf8").split("\n").slice(-6).join("\n") : "";
      this.clearState();
      throw new An3Error("E_TARGET_UNAVAILABLE", `Web target did not start on :${resolvedPort}${health ? " (recorded process exited; the port may already be in use)" : ""}`, { logTail: tail });
    }
    this.writeState(state);
    return { started: true, ...state, health };
  }

  async appStop() {
    const state = this.readState();
    if (!state) return { stopped: false, reason: "no recorded web target" };
    this.playwright(["close"]).catch(() => {});
    if (isAlive(state.pid)) {
      try {
        process.kill(state.pid, "SIGTERM");
      } catch {
        /* ignore */
      }
      await sleep(500);
      if (isAlive(state.pid)) {
        try {
          process.kill(state.pid, "SIGKILL");
        } catch {
          /* ignore */
        }
      }
    }
    this.clearState();
    return { stopped: true, pid: state.pid };
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
    return { ...tree, limit };
  }

  async locate(opts) {
    const url = this.ensureUrlPath(opts);
    await this.ensureOpen(url);
    const selector = opts.selector;
    return this.runCode(
      `async (page) => {\n  return await page.evaluate(() => ${locateExpression(selector, { nth: opts.nth ?? 0 })});\n}`,
    );
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
    const body = actionBody(action, opts);
    const script = `async (page) => {\n  const located = JSON.parse(await page.evaluate(() => ${locateExpression(opts.selector, { nth: opts.nth ?? 0 })}));\n  if (!located.found) return JSON.stringify({ performed: false, reason: 'not-found' });\n  return await (async () => { ${body} })();\n}`;
    const result = await this.runCode(script);
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
    const script = `async (page) => {\n  const located = JSON.parse(await page.evaluate(() => ${locateExpression(opts.selector, { nth: opts.nth ?? 0 })}));\n  if (!located.found) return JSON.stringify({ found: false });\n  return await page.evaluate((idx) => {\n    const all = Array.from(document.querySelectorAll(${JSON.stringify("a,button,input,select,textarea,[role],[data-testid]")}));\n    const el = all[idx];\n    return JSON.stringify({ found: !!el, value: el ? (el.value !== undefined ? String(el.value) : (el.innerText || '').trim()) : null });\n  }, located.index);\n}`;
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

function actionBody(action, opts) {
  const common = `const idx = located.index;\n  `;
  switch (action) {
    case "click":
      return `${common}await page.evaluate((idx) => {\n    const all = Array.from(document.querySelectorAll('a,button,input,select,textarea,[role],[data-testid]'));\n    const el = all[idx]; if (!el) throw new Error('element vanished');\n    el.scrollIntoView({block:'center'});\n    el.click();\n  }, idx);\n  return JSON.stringify({ performed: true, action: 'click' });`;
    case "fill":
      return `${common}await page.evaluate((idx) => {\n    const all = Array.from(document.querySelectorAll('a,button,input,select,textarea,[role],[data-testid]'));\n    const el = all[idx]; if (!el) throw new Error('element vanished');\n    el.focus();\n    el.value = ${JSON.stringify(String(opts.value ?? ""))};\n    el.dispatchEvent(new Event('input', { bubbles: true }));\n    el.dispatchEvent(new Event('change', { bubbles: true }));\n  }, idx);\n  return JSON.stringify({ performed: true, action: 'fill', value: ${JSON.stringify(String(opts.value ?? ""))} });`;
    case "press":
      return `${common}await page.evaluate((idx) => {\n    const all = Array.from(document.querySelectorAll('a,button,input,select,textarea,[role],[data-testid]'));\n    const el = all[idx]; if (!el) throw new Error('element vanished');\n    el.focus();\n  }, idx);\n  await page.keyboard.press(${JSON.stringify(String(opts.key ?? "Enter"))});\n  return JSON.stringify({ performed: true, action: 'press', key: ${JSON.stringify(String(opts.key ?? "Enter"))} });`;
    case "select":
      return `${common}await page.evaluate((idx) => {\n    const all = Array.from(document.querySelectorAll('a,button,input,select,textarea,[role],[data-testid]'));\n    const el = all[idx]; if (!el) throw new Error('element vanished');\n    el.value = ${JSON.stringify(String(opts.value ?? ""))};\n    el.dispatchEvent(new Event('change', { bubbles: true }));\n  }, idx);\n  return JSON.stringify({ performed: true, action: 'select', value: ${JSON.stringify(String(opts.value ?? ""))} });`;
    case "check":
      return `${common}await page.evaluate((idx) => {\n    const all = Array.from(document.querySelectorAll('a,button,input,select,textarea,[role],[data-testid]'));\n    const el = all[idx]; if (!el) throw new Error('element vanished');\n    const want = ${opts.checked === false ? "false" : "true"};\n    if (el.checked !== want) { el.click(); }\n  }, idx);\n  return JSON.stringify({ performed: true, action: 'check' });`;
    default:
      return `${common}return JSON.stringify({ performed: false, reason: 'unknown-action' });`;
  }
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
