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
import { An3Error, httpJson, run } from "../lib/core.mjs";

export class DesktopAdapter {
  constructor(root) {
    this.root = root;
    this.name = "desktop";
  }

  targets() {
    return ["macos", "linux", "windows"];
  }

  async windowsDebugProbe({ host = "windows-build-host", port = 9222 } = {}) {
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
    const file = this.controlFile(opts);
    if (!existsSync(file)) {
      throw new An3Error(
        "E_TARGET_UNAVAILABLE",
        `No macOS UI control file at ${file}. Launch an automation build with AN3_UI_CONTROL_FILE set (see \`an3ctl app start --target macos\`).`,
      );
    }
    try {
      const parsed = JSON.parse(readFileSync(file, "utf8"));
      if (!parsed?.port || !parsed?.token) throw new Error("missing port/token");
      return { file, port: parsed.port, token: parsed.token };
    } catch (error) {
      throw new An3Error("E_TARGET_UNAVAILABLE", `Invalid macOS UI control file ${file}: ${error.message}`);
    }
  }

  async macosCall(opts, route, params = {}) {
    const { port, token } = this.readControl(opts);
    const query = new URLSearchParams(params).toString();
    const path = `${route}${query ? `?${query}` : ""}`;
    return httpJson(port, path, { headers: { "x-an3-token": token } }).catch(error => {
      if (error instanceof An3Error) throw error;
      throw new An3Error("E_ACTION_FAILED", `macOS UI bridge call failed (${path}): ${error.message}`);
    });
  }

  async appStart(opts = {}) {
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
    const controlFile = this.controlFile(opts);
    const macosReachable = existsSync(controlFile);
    return {
      available: macosReachable,
      targets: {
        macos: macosReachable
          ? { available: true, via: "ui-control", controlFile, reason: null, next: null }
          : {
              available: false,
              reason: "No macOS UI control bridge is active. Build the automation app (cargo feature `ui-control`) and start it with AN3_UI_CONTROL_FILE.",
              next: "an3ctl app start --target macos",
            },
        linux: {
          available: false,
          reason: "The Linux shell is a Tauri/WebKitGTK app. Structured control requires WebKitGTK WebDriver (WebKitWebDriver) with a display; xdotool is fallback-only.",
          next: "See docs/agent-control-plane.md#phase-3-desktop-adapters.",
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
    if (target === "macos") {
      const result = await this.macosCall(opts, "/tree");
      return { target, via: "ui-control", nodes: result.nodes };
    }
    if (target === "windows") {
      const probe = await this.windowsDebugProbe(opts.windows ?? {});
      if (!probe.reachable) await this.requireStructured(target);
      try {
        const targets = await httpJson(probe.port, "/json/list");
        return { target, via: "cdp", targets: targets.map((entry) => ({ title: entry.title, url: entry.url })) };
      } catch (error) {
        throw new An3Error("E_TARGET_UNAVAILABLE", `WebView2 DevTools is not reachable on 127.0.0.1:${probe.port}. ${probe.instruction}`, { cause: error.message });
      }
    }
    await this.requireStructured(target);
  }

  async uiQuery(opts = {}) {
    const target = opts.target ?? "windows";
    if (target === "macos") {
      const testid = opts.testid ?? (typeof opts.selector === "string" ? opts.selector : null);
      if (!testid) throw new An3Error("E_USAGE", "ui query --target macos requires --testid <id>");
      const result = await this.macosCall(opts, "/query", { testid });
      return { target, via: "ui-control", node: result.node };
    }
    return this.uiTree({ target, windows: opts.windows });
  }

  async uiClick(opts = {}) {
    const target = opts.target ?? "windows";
    if (target === "macos") {
      const testid = opts.testid ?? (typeof opts.selector === "string" ? opts.selector : null);
      if (!testid) throw new An3Error("E_USAGE", "ui click --target macos requires --testid <id>");
      const result = await this.macosCall(opts, "/click", { testid });
      if (!result.clicked) throw new An3Error("E_SELECTOR_NOT_FOUND", `no element with data-testid=${testid}`);
      return { target, via: "ui-control", clicked: true, testid };
    }
    await this.requireStructured(target);
  }

  async uiText(opts = {}) {
    const target = opts.target ?? "windows";
    if (target === "macos") {
      const testid = opts.testid ?? (typeof opts.selector === "string" ? opts.selector : null);
      if (!testid) throw new An3Error("E_USAGE", "ui text --target macos requires --testid <id>");
      const result = await this.macosCall(opts, "/text", { testid });
      return { target, via: "ui-control", text: result.text, present: result.present };
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
    const result = await this.macosCall(opts, "/native");
    return {
      target,
      via: "ui-control",
      running: result.running === true,
      presentedFrames: Number(result.presentedFrames ?? 0),
    };
  }

  async uiWait(opts = {}) {
    const target = opts.target ?? "windows";
    if (target !== "macos") await this.requireStructured(target);
    const testid = opts.testid ?? (typeof opts.selector === "string" ? opts.selector : null);
    if (!testid) throw new An3Error("E_USAGE", "ui wait --target macos requires --testid <id>");
    const timeout = Number(opts.timeout ?? 30_000);
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const result = await this.macosCall(opts, "/query", { testid });
      if (result.node && (opts.state ? result.node.state === opts.state : true)) {
        return { target, via: "ui-control", found: true, node: result.node };
      }
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    throw new An3Error("E_TIMEOUT", `ui wait timed out for data-testid=${testid}${opts.state ? ` state=${opts.state}` : ""}`);
  }
}
