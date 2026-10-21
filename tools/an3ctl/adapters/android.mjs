// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Android adapter. Reuses the verified adb + WebView Chrome DevTools Protocol
// path discovered in the capability audit. It performs the whole sequence
// (detect device -> resolve PID -> find the devtools socket -> adb forward ->
// connect CDP -> control/read -> clean up) so agents never reproduce it by hand.
//
// Emulator-first; the same code targets a physical device when a test/debug
// build exposes the WebView devtools socket.

import { randomUUID } from "node:crypto";
import { An3Error, CdpSession, httpJson, run } from "../lib/core.mjs";
import { domTreeExpression, locateExpression, INTERACTIVE_SELECTOR } from "../lib/domtree.mjs";

const PACKAGE = "space.an3tocom.offline";
const MAIN_ACTIVITY = `${PACKAGE}/.MainActivity`;
const GAME_ACTIVITY = `${PACKAGE}/.NativeGameActivity`;
const DEFAULT_PORT = Number(process.env.AN3_ANDROID_CDP_PORT ?? 9222);

export class AndroidAdapter {
  constructor(root) {
    this.root = root;
    this.name = "android";
    this.forwardedPort = null;
  }

  async adb(args, opts = {}) {
    const serialArgs = opts.serial ? ["-s", opts.serial] : [];
    const result = await run("adb", [...serialArgs, ...args], { timeoutMs: opts.timeoutMs ?? 60000 });
    if (result.code !== 0 && !opts.allowFailure) {
      throw new An3Error("E_TARGET_UNAVAILABLE", `adb ${args.join(" ")} failed: ${(result.stderr || "").trim().slice(0, 300)}`);
    }
    return result;
  }

  async devices() {
    const result = await run("adb", ["devices", "-l"]).catch(() => null);
    if (!result || result.code !== 0) return [];
    return result.stdout
      .split("\n")
      .slice(1)
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith("*"))
      .map((line) => {
        const [serial, , ...rest] = line.split(/\s+/);
        const attrs = Object.fromEntries(rest.map((pair) => pair.split(":")));
        return { serial, state: line.split(/\s+/)[1], model: attrs.model ?? null, product: attrs.product ?? null };
      });
  }

  async device(opts = {}) {
    if (opts.serial) return opts.serial;
    const devices = await this.devices();
    const ready = devices.filter((device) => device.state === "device");
    if (!ready.length) {
      throw new An3Error("E_TARGET_UNAVAILABLE", "No Android device/emulator is connected (adb devices is empty).");
    }
    const emulator = ready.find((device) => device.serial.startsWith("emulator-"));
    return (emulator ?? ready[0]).serial;
  }

  async available() {
    const devices = await this.devices();
    return {
      available: devices.length > 0,
      devices,
      kind: devices.some((device) => device.serial.startsWith("emulator-")) ? "emulator" : devices.length ? "physical" : null,
    };
  }

  async sh(command, opts = {}) {
    return this.adb(["shell", ...String(command).split(" ")], opts);
  }

  async appStart(opts = {}) {
    const serial = await this.device(opts);
    const result = await this.adb(["shell", "am", "start", "-n", MAIN_ACTIVITY], { serial, allowFailure: true });
    if (!/Starting:|Warning: Activity not started/.test(result.stdout)) {
      throw new An3Error("E_ACTION_FAILED", `Could not launch ${MAIN_ACTIVITY}: ${(result.stdout || result.stderr).trim().slice(0, 200)}`);
    }
    await sleep(Number(opts.settleMs ?? 2000));
    return { started: true, serial, activity: MAIN_ACTIVITY, state: await this.appState({ serial }) };
  }

  async appStop(opts = {}) {
    const serial = await this.device(opts);
    await this.adb(["shell", "am", "force-stop", PACKAGE], { serial });
    return { stopped: true, serial, package: PACKAGE };
  }

  async appState(opts = {}) {
    const serial = await this.device(opts);
    const pid = (await this.adb(["shell", "pidof", PACKAGE], { serial, allowFailure: true })).stdout.trim();
    const focus = (await this.adb(["shell", "dumpsys", "window"], { serial, allowFailure: true })).stdout
      .split("\n")
      .find((line) => line.includes("mCurrentFocus"));
    const version = (await this.adb(["shell", "dumpsys", "package", PACKAGE], { serial, allowFailure: true })).stdout
      .split("\n")
      .find((line) => line.includes("versionName"));
    return {
      running: Boolean(pid),
      pid: pid || null,
      serial,
      package: PACKAGE,
      focus: focus ? focus.trim() : null,
      versionName: version ? version.trim().split("=").pop() : null,
    };
  }

  // --- CDP session ---------------------------------------------------------

  async openSession(opts = {}) {
    const serial = await this.device(opts);
    const isRoot = (await this.adb(["shell", "id"], { serial, allowFailure: true })).stdout.trim();
    const pid = (await this.adb(["shell", "pidof", PACKAGE], { serial, allowFailure: true })).stdout.trim();
    if (!pid) {
      throw new An3Error("E_STATE", "The app is not running. Run `an3ctl app start --target android` first.");
    }
    const sockets = (await this.adb(["shell", "cat", "/proc/net/unix"], { serial, allowFailure: true })).stdout
      .split("\n")
      .filter((line) => line.includes("webview_devtools_remote"));
    const socket = sockets.find((line) => line.endsWith(`@webview_devtools_remote_${pid}`));
    if (!socket) {
      throw new An3Error(
        "E_TARGET_UNAVAILABLE",
        `No WebView devtools socket for pid ${pid}. A release build only exposes it when the app enables WebView debugging; try \`adb root\` (currently: ${isRoot}).`,
      );
    }
    const port = opts.port ?? DEFAULT_PORT;
    await this.adb(["forward", `tcp:${port}`, `localabstract:webview_devtools_remote_${pid}`], { serial });
    this.forwardedPort = port;
    const list = await httpJson(port, "/json/list");
    const page = list.find((entry) => entry.webSocketDebuggerUrl && entry.type === "page") ?? list[0];
    if (!page?.webSocketDebuggerUrl) {
      throw new An3Error("E_TARGET_UNAVAILABLE", "The WebView devtools target did not expose a page.");
    }
    const cdp = await CdpSession.connect(page.webSocketDebuggerUrl);
    return { cdp, serial, port, pid, page: { title: page.title, url: page.url } };
  }

  async closeSession(session, opts = {}) {
    try {
      session?.cdp?.close();
    } catch {
      /* ignore */
    }
    if (this.forwardedPort) {
      await this.adb(["forward", "--remove", `tcp:${this.forwardedPort}`], { serial: session?.serial, allowFailure: true });
      this.forwardedPort = null;
    }
  }

  async withSession(opts, fn) {
    const session = await this.openSession(opts);
    try {
      return await fn(session);
    } finally {
      await this.closeSession(session, opts);
    }
  }

  // --- structured UI (CDP) -------------------------------------------------

  async uiTree(opts = {}) {
    return this.withSession(opts, async ({ cdp, page }) => {
      const limit = Number(opts.limit ?? 120);
      const tree = await cdp.evaluateJson(domTreeExpression(limit));
      return { ...tree, page, limit };
    });
  }

  async locate(opts = {}) {
    return this.withSession(opts, async ({ cdp }) => cdp.evaluateJson(locateExpression(opts.selector, { nth: opts.nth ?? 0 })));
  }

  async uiQuery(opts = {}) {
    const result = await this.locate(opts);
    if (!result?.found) {
      throw new An3Error("E_NOT_FOUND", `No element matched ${describeSelector(opts.selector)}`, { selector: opts.selector });
    }
    return result;
  }

  async uiAction(opts = {}, action) {
    return this.withSession(opts, async ({ cdp }) => {
      const located = await cdp.evaluateJson(locateExpression(opts.selector, { nth: opts.nth ?? 0 }));
      if (!located?.found) {
        throw new An3Error("E_NOT_FOUND", `No element matched ${describeSelector(opts.selector)}`, { selector: opts.selector });
      }
      const expression = androidActionExpression(action, opts, located.index);
      const result = await cdp.evaluateJson(expression);
      if (!result?.performed) {
        throw new An3Error("E_ACTION_FAILED", `Action ${action} did not run`, { selector: opts.selector, result });
      }
      return result;
    });
  }

  uiClick(opts) {
    return this.uiAction(opts, "click");
  }
  uiFill(opts) {
    return this.uiAction(opts, "fill");
  }
  uiSelect(opts) {
    return this.uiAction(opts, "select");
  }
  uiCheck(opts) {
    return this.uiAction(opts, "check");
  }

  async uiPress(opts = {}) {
    return this.withSession(opts, async ({ cdp }) => {
      const key = String(opts.key ?? "Enter");
      const expr = `(() => {
        const el = document.activeElement || document.body;
        const opts = { key: ${JSON.stringify(key)}, bubbles: true, cancelable: true };
        el.dispatchEvent(new KeyboardEvent('keydown', opts));
        el.dispatchEvent(new KeyboardEvent('keyup', opts));
        return JSON.stringify({ performed: true, key: ${JSON.stringify(key)} });
      })()`;
      return cdp.evaluateJson(expr);
    });
  }

  async uiText(opts = {}) {
    const located = await this.uiQuery(opts);
    if (!located?.found) throw new An3Error("E_NOT_FOUND", `No element matched ${describeSelector(opts.selector)}`);
    return { text: located.node?.name ?? null, node: located.node };
  }

  async uiValue(opts = {}) {
    return this.withSession(opts, async ({ cdp }) => {
      const located = await cdp.evaluateJson(locateExpression(opts.selector, { nth: opts.nth ?? 0 }));
      if (!located?.found) throw new An3Error("E_NOT_FOUND", `No element matched ${describeSelector(opts.selector)}`);
      const expr = `(() => {
        const all = Array.from(document.querySelectorAll(${JSON.stringify(INTERACTIVE_SELECTOR)}));
        const el = all[${located.index}];
        return JSON.stringify({ found: !!el, value: el ? (el.value !== undefined ? String(el.value) : (el.innerText || '').trim()) : null });
      })()`;
      return cdp.evaluateJson(expr);
    });
  }

  async uiWait(opts = {}) {
    const timeoutMs = Number(opts.timeout ?? 10000);
    const deadline = Date.now() + timeoutMs;
    let last = null;
    while (Date.now() < deadline) {
      last = await this.locate(opts);
      if (last?.found) return { appeared: true, node: last.node, visible: last.node?.visible ?? null };
      await sleep(300);
    }
    throw new An3Error("E_TIMEOUT", `Element ${describeSelector(opts.selector)} did not appear within ${timeoutMs}ms`, { last });
  }

  async logs(opts = {}) {
    const serial = await this.device(opts);
    const tail = Number(opts.tail ?? 200);
    const filter = opts.filter ?? PACKAGE;
    // Fetch a wider window than requested so the package filter still has
    // matches even when unrelated system lines dominate the most recent lines.
    const window = Math.max(tail * 40, 1500);
    const result = await this.adb(["logcat", "-d", "-t", String(window)], { serial, allowFailure: true });
    const filtered = result.stdout
      .split("\n")
      .filter((line) => (filter ? line.includes(filter) || /FATAL|AndroidRuntime/.test(line) : true));
    return { lines: filtered.slice(-tail), serial, filter, scanned: window };
  }

  // --- direct ROM load (no native file dialog) -----------------------------

  async romLoad(opts = {}) {
    const path = opts.path;
    if (!path) throw new An3Error("E_USAGE", "rom load requires a path.");
    const serial = await this.device(opts);
    const system = opts.system ?? guessSystem(path);
    const remote = `/data/local/tmp/an3ctl-${Date.now()}${extensionOf(path)}`;
    await this.adb(["push", path, remote], { serial, timeoutMs: 300000 });
    const romId = opts.romId ?? randomUUID();
    const romsDir = `/data/data/${PACKAGE}/an3-roms`;
    await this.adb(["shell", "mkdir", "-p", romsDir], { serial, allowFailure: true });
    await this.adb(["shell", "cp", remote, `${romsDir}/${romId}${extensionOf(path)}`], { serial, allowFailure: true });
    const result = await this.adb(
      ["shell", "am", "start", "-n", GAME_ACTIVITY, "--es", "romId", romId, "--es", "system", system, "--es", "romFilename", `${romId}${extensionOf(path)}`],
      { serial, allowFailure: true },
    );
    return { loaded: /Starting:/.test(result.stdout), serial, system, romId, remote };
  }
}

function androidActionExpression(action, opts, index) {
  const list = JSON.stringify(INTERACTIVE_SELECTOR);
  const idx = Number(index);
  switch (action) {
    case "click":
      return `(() => {
        const all = Array.from(document.querySelectorAll(${list}));
        const el = all[${idx}]; if (!el) return JSON.stringify({ performed: false });
        el.scrollIntoView({ block: 'center' });
        el.click();
        return JSON.stringify({ performed: true, action: 'click' });
      })()`;
    case "fill":
      return `(() => {
        const all = Array.from(document.querySelectorAll(${list}));
        const el = all[${idx}]; if (!el) return JSON.stringify({ performed: false });
        el.focus();
        el.value = ${JSON.stringify(String(opts.value ?? ""))};
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return JSON.stringify({ performed: true, action: 'fill', value: el.value });
      })()`;
    case "select":
      return `(() => {
        const all = Array.from(document.querySelectorAll(${list}));
        const el = all[${idx}]; if (!el) return JSON.stringify({ performed: false });
        el.value = ${JSON.stringify(String(opts.value ?? ""))};
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return JSON.stringify({ performed: true, action: 'select', value: el.value });
      })()`;
    case "check":
      return `(() => {
        const all = Array.from(document.querySelectorAll(${list}));
        const el = all[${idx}]; if (!el) return JSON.stringify({ performed: false });
        const want = ${opts.checked === false ? "false" : "true"};
        if (el.checked !== want) el.click();
        return JSON.stringify({ performed: true, action: 'check', checked: el.checked });
      })()`;
    default:
      return `JSON.stringify({ performed: false, reason: 'unknown-action' })`;
  }
}

function describeSelector(selector) {
  if (!selector) return "(no selector)";
  if (selector.kind === "role") return `role=${selector.value.role}${selector.value.name ? ` name~${selector.value.name}` : ""}`;
  return `${selector.kind}=${selector.value}`;
}

function extensionOf(path) {
  const match = String(path).match(/(\.[A-Za-z0-9]+)$/);
  return match ? match[1].toLowerCase() : "";
}

function guessSystem(path) {
  const ext = extensionOf(path);
  if (ext === ".gba") return "gba";
  if (ext === ".nds" || ext === ".dsi") return "nds";
  if (ext === ".3ds" || ext === ".3dsx" || ext === ".cci" || ext === ".cxi") return "3ds";
  return "unknown";
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
