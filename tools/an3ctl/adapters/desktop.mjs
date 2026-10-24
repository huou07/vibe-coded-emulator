// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Desktop structured adapters. The macOS Tauri/WebKit shell exposes a
// test-only, token-gated loopback bridge (cargo feature `ui-control`) that
// dispatches real DOM events on `data-testid` elements, so a UI click exercises
// the same frontend handler a user would. Windows uses WebView2 CDP. Neither
// path uses coordinates, OCR or screenshots.

import { existsSync, readFileSync, rmSync } from "node:fs";
import { homedir } from "node:os";
import { An3Error, CdpSession, httpJson, run } from "../lib/core.mjs";
import { domTreeExpression, locateExpression } from "../lib/domtree.mjs";

export class DesktopAdapter {
  constructor(root) {
    this.root = root;
    this.name = "desktop";
  }

  targets() {
    return ["macos", "linux", "windows"];
  }

  async windowsDebugProbe({ host = "windows-build-host", port = 9222 } = {}) {
    // An already-forwarded test/debug socket is inspected on loopback only.
    if (process.env.AN3_WINDOWS_CDP_LOCAL === "1") {
      try {
        const targets = await httpJson(port, "/json/list", { timeout: 1000 });
        if (!Array.isArray(targets)) throw new Error("unexpected WebView2 target list");
        return { host: "127.0.0.1", port, reachable: true, via: "local-cdp" };
      } catch (error) {
        return {
          host: "127.0.0.1",
          port,
          reachable: false,
          via: "local-cdp",
          instruction: "A test/debug build must expose WebView2 CDP on loopback port " + port + " only.",
        };
      }
    }
    // The Windows shell is a WebView2 host. WebView2 only opens a DevTools
    // socket when the app opts in for a test/debug build; a release build keeps
    // it closed. We check reachability without changing anything.
    const result = await run("ssh", ["-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, `powershell -NoProfile -Command "(Test-NetConnection 127.0.0.1 -Port ${port} -WarningAction SilentlyContinue).TcpTestSucceeded"`]).catch(() => null);
    const reachable = result && /True/i.test(result.stdout);
    return {
      host,
      port,
      reachable,
      instruction: reachable
        ? `forward with: ssh -L ${port}:127.0.0.1:${port} ${host}`
        : "A test/debug build must enable WebView2 remote debugging on 127.0.0.1 only (see docs/agent-control-plane.md).",
    };
  }

  controlFile(opts = {}) {
    return opts.controlFile ?? process.env.AN3_UI_CONTROL_FILE ?? `${homedir()}/.an3/ui-control.json`;
  }

  readControl(opts = {}) {
    const target = opts.target ?? "macos";
    const file = this.controlFile(opts);
    if (!existsSync(file)) {
      throw new An3Error(
        "E_TARGET_UNAVAILABLE",
        `No ${target} UI control file at ${file}. Launch a test automation build with AN3_UI_CONTROL_FILE set (see \`an3ctl app start --target macos\`).`,
      );
    }
    try {
      const parsed = JSON.parse(readFileSync(file, "utf8"));
      if (!parsed?.port || !parsed?.token) throw new Error("missing port/token");
      return { file, port: parsed.port, token: parsed.token };
    } catch (error) {
      throw new An3Error("E_TARGET_UNAVAILABLE", `Invalid ${target} UI control file ${file}: ${error.message}`);
    }
  }

  async uiControlCall(opts, route, params = {}) {
    const { port, token } = this.readControl(opts);
    const query = new URLSearchParams(params).toString();
    const path = `${route}${query ? `?${query}` : ""}`;
    return httpJson(port, path, { timeout: 15_000, headers: { "x-an3-token": token } }).catch(error => {
      if (error instanceof An3Error) throw error;
      throw new An3Error("E_ACTION_FAILED", `${opts.target ?? "macos"} UI bridge call failed (${path}): ${error.message}`);
    });
  }

  async withWindowsCdp(opts = {}, callback) {
    const port = Number(opts.windows?.port ?? opts.port ?? 9222);
    let targets;
    try {
      targets = await httpJson(port, "/json/list", { timeout: 1500 });
    } catch (error) {
      throw new An3Error(
        "E_TARGET_UNAVAILABLE",
        "Windows WebView2 CDP is not reachable on 127.0.0.1:" + port + "; forward the test-only loopback endpoint over SSH first.",
        { cause: error.message },
      );
    }
    const page = Array.isArray(targets)
      ? targets.find(target => target.type === "page") ?? targets[0]
      : null;
    if (!page?.webSocketDebuggerUrl) {
      throw new An3Error("E_TARGET_UNAVAILABLE", "Windows WebView2 did not expose a page CDP endpoint.");
    }
    const session = await CdpSession.connect(page.webSocketDebuggerUrl);
    try {
      return await callback(session);
    } finally {
      session.close();
    }
  }

  async appStart(opts = {}) {
    if (process.platform !== "darwin") {
      throw new An3Error("E_TARGET_UNAVAILABLE", "macOS app start requires a macOS ui-control automation build.");
    }
    const appPath = opts.app ?? process.env.AN3_MACOS_APP;
    if (!appPath || !existsSync(appPath)) {
      throw new An3Error("E_USAGE", "app start --target macos requires AN3_MACOS_APP (or --app) pointing at the built .app");
    }
    const controlFile = this.controlFile(opts);
    rmSync(controlFile, { force: true });
    const env = [
      ...(opts.testRom ? ["--env", `AN3_UI_TEST_ROM=${opts.testRom}`] : []),
      ...(opts.home ? ["--env", `HOME=${opts.home}`] : []),
      "--env", `AN3_UI_CONTROL_FILE=${controlFile}`,
    ];
    await run("open", ["-n", appPath, "--stdout", "/tmp/an3-macos-app.out", "--stderr", "/tmp/an3-macos-app.err", ...env]);
    const deadline = Date.now() + 60_000;
    while (Date.now() < deadline) {
      if (existsSync(controlFile)) {
        const control = JSON.parse(readFileSync(controlFile, "utf8"));
        return { started: true, app: appPath, port: control.port, controlFile };
      }
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    throw new An3Error("E_TIMEOUT", "the macOS app did not expose its UI control bridge in time");
  }

  async appStop(opts = {}) {
    const appPath = opts.app ?? process.env.AN3_MACOS_APP ?? "";
    const pattern = appPath ? appPath.replace(/.*\//, "") : "an3-offline-native";
    await run("pkill", ["-f", pattern]).catch(() => null);
    return { stopped: true, pattern };
  }

  async available(opts = {}) {
    const macosControlFile = this.controlFile({ ...opts, ...(opts.macos ?? {}), target: "macos" });
    const linuxControlFile = this.controlFile({ ...opts, ...(opts.linux ?? {}), target: "linux" });
    const macosReachable = existsSync(macosControlFile);
    const linuxReachable = existsSync(linuxControlFile);
    return {
      available: macosReachable || linuxReachable,
      targets: {
        macos: macosReachable
          ? { available: true, via: "ui-control", controlFile: macosControlFile, reason: null, next: null }
          : {
              available: false,
              reason: "No macOS UI control bridge is active. Build the automation app (cargo feature `ui-control`) and start it with AN3_UI_CONTROL_FILE.",
              next: "an3ctl app start --target macos",
            },
        linux: linuxReachable
          ? { available: true, via: "ui-control", controlFile: linuxControlFile, reason: null, next: null }
          : {
              available: false,
              reason: "No Linux UI control bridge is active. Build with the test-only ui-control feature and set AN3_UI_CONTROL_FILE.",
              next: "Start the Linux automation build with AN3_UI_CONTROL_FILE set.",
            },
        windows: await this.windowsDebugProbe(opts.windows ?? {}),
      },
    };
  }

  async requireStructured(target) {
    const caps = await this.available();
    throw new An3Error(
      "E_TARGET_UNAVAILABLE",
      `No structured UI bridge is enabled for the ${target} desktop shell yet. ${caps.targets[target]?.reason ?? ""} ${caps.targets[target]?.next ?? ""}`.trim(),
      { target },
    );
  }

  async uiTree(opts = {}) {
    const target = opts.target ?? "windows";
    if (target === "macos" || target === "linux") {
      const result = await this.uiControlCall(opts, "/tree");
      return { target, via: "ui-control", nodes: result.nodes };
    }
    if (target === "windows") {
      return this.withWindowsCdp(opts, async session => {
        const tree = await session.evaluateJson(domTreeExpression(Number(opts.limit ?? 120)));
        return { target, via: "cdp", ...tree };
      });
    }
    await this.requireStructured(target);
  }

  async uiQuery(opts = {}) {
    const target = opts.target ?? "windows";
    if (target === "macos" || target === "linux") {
      const testid = opts.testid ?? (typeof opts.selector === "string" ? opts.selector : opts.selector?.kind === "testid" ? opts.selector.value : null);
      if (!testid) throw new An3Error("E_USAGE", "ui query --target " + target + " requires --testid <id>");
      const result = await this.uiControlCall(opts, "/query", { testid });
      return { target, via: "ui-control", node: result.node };
    }
    if (target === "windows") {
      return this.withWindowsCdp(opts, async session => {
        const result = await session.evaluateJson(locateExpression(opts.selector, { nth: opts.nth ?? 0 }));
        if (!result?.found) throw new An3Error("E_NOT_FOUND", "No Windows UI element matched the selector.", { selector: opts.selector });
        return { target, via: "cdp", ...result };
      });
    }
    return this.uiTree({ target, windows: opts.windows });
  }

  async uiClick(opts = {}) {
    const target = opts.target ?? "windows";
    if (target === "macos" || target === "linux") {
      const testid = opts.testid ?? (typeof opts.selector === "string" ? opts.selector : opts.selector?.kind === "testid" ? opts.selector.value : null);
      if (!testid) throw new An3Error("E_USAGE", "ui click --target " + target + " requires --testid <id>");
      const result = await this.uiControlCall(opts, "/click", { testid });
      if (!result.clicked) throw new An3Error("E_SELECTOR_NOT_FOUND", "no element with data-testid=" + testid);
      return { target, via: "ui-control", clicked: true, testid };
    }
    if (target === "windows") {
      return this.withWindowsCdp(opts, async session => {
        const located = await session.evaluateJson(locateExpression(opts.selector, { nth: opts.nth ?? 0 }));
        if (!located?.found) throw new An3Error("E_NOT_FOUND", "No Windows UI element matched the selector.", { selector: opts.selector });
        const hitTest = await session.evaluateJson("(() => {"
          + "const all=Array.from(document.querySelectorAll('a,button,input,select,textarea,[role],[data-testid],[onclick],[tabindex]'));"
          + "const el=all[" + Number(located.index) + "];"
          + "if(!el)return {performed:false,reason:'missing'};"
          + "el.scrollIntoView({block:'center',inline:'center'});"
          + "const r=el.getBoundingClientRect(),s=getComputedStyle(el),x=r.left+r.width/2,y=r.top+r.height/2,hit=document.elementFromPoint(x,y);"
          + "if(!r.width||!r.height||s.display==='none'||s.visibility==='hidden'||el.disabled||(hit!==el&&!el.contains(hit)){"
          + "const blocker=hit&&hit.closest('[data-testid]');"
          + "return {performed:false,reason:'obstructed',hit:{testId:blocker&&blocker.getAttribute('data-testid'),tag:hit&&hit.tagName.toLowerCase()}};"
          + "}"
          + "return {performed:true,x,y};"
          + "})()");
        if (!hitTest?.performed) {
          throw new An3Error("E_ACTION_FAILED", "Windows UI target is not actionable.", { selector: opts.selector, hitTest });
        }
        const { x, y } = hitTest;
        await session.send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
        await session.send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", buttons: 1, clickCount: 1 });
        await session.send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", buttons: 0, clickCount: 1 });
        return { target, via: "cdp", performed: true, action: "click" };
      });
    }
    await this.requireStructured(target);
  }

  async uiText(opts = {}) {
    const target = opts.target ?? "windows";
    if (target === "macos" || target === "linux") {
      const testid = opts.testid ?? (typeof opts.selector === "string" ? opts.selector : opts.selector?.kind === "testid" ? opts.selector.value : null);
      if (!testid) throw new An3Error("E_USAGE", "ui text --target " + target + " requires --testid <id>");
      const result = await this.uiControlCall(opts, "/text", { testid });
      return { target, via: "ui-control", text: result.text, present: result.present };
    }
    if (target === "windows") {
      const result = await this.uiQuery(opts);
      return { target, via: "cdp", text: result.node?.name ?? null, present: true };
    }
    await this.requireStructured(target);
  }

  // Native-runtime diagnostics for the packaged macOS app: whether an
  // integrated core is running and how many frames its renderer has presented.
  // Read from the Rust host through the test-only bridge, so an E2E can prove
  // rendered output (an advancing counter) without screenshots or coordinates.
  async uiNative(opts = {}) {
    const target = opts.target ?? "macos";
    if (target !== "macos") await this.requireStructured(target);
    const result = await this.uiControlCall(opts, "/native");
    return {
      target,
      via: "ui-control",
      running: result.running === true,
      presentedFrames: Number(result.presentedFrames ?? 0),
    };
  }

  async uiWait(opts = {}) {
    const target = opts.target ?? "windows";
    if (target !== "macos" && target !== "linux" && target !== "windows") await this.requireStructured(target);
    const testid = opts.testid ?? (typeof opts.selector === "string" ? opts.selector : opts.selector?.kind === "testid" ? opts.selector.value : null);
    if (!testid) throw new An3Error("E_USAGE", "ui wait --target " + target + " requires --testid <id>");
    const timeout = Number(opts.timeout ?? 30_000);
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const result = target === "windows"
        ? await this.uiQuery(opts)
        : await this.uiControlCall(opts, "/query", { testid });
      const node = result.node ?? null;
      if (node && (opts.state ? node.state === opts.state : true)) {
        return { target, via: target === "windows" ? "cdp" : "ui-control", found: true, node };
      }
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    throw new An3Error("E_TIMEOUT", `ui wait timed out for data-testid=${testid}${opts.state ? ` state=${opts.state}` : ""}`);
  }
}
