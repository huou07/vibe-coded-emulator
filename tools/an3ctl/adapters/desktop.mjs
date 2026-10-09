// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Desktop structured adapters. The macOS and Linux Tauri shells expose a
// test-only, token-gated loopback bridge (cargo feature `ui-control`) that
// dispatches DOM events on `data-testid` elements. Windows uses WebView2 CDP.
// None uses coordinates, OCR or screenshots.

import { existsSync, readFileSync, rmSync } from "node:fs";
import { homedir } from "node:os";
import { An3Error, httpJson, run } from "../lib/core.mjs";

// The native ui-control bridge may wait ten seconds for WebView JavaScript.
const MACOS_UI_CONTROL_TIMEOUT_MS = 12_000;

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

  controlFile(opts = {}, target = "macos") {
    const envFile = target === "linux"
      ? process.env.AN3_LINUX_UI_CONTROL_FILE
      : process.env.AN3_UI_CONTROL_FILE;
    const fallback = target === "macos"
      ? `${homedir()}/.an3/ui-control.json`
      : `${homedir()}/.an3/linux-ui-control.json`;
    return opts.controlFile ?? envFile ?? fallback;
  }

  readControl(opts = {}, target = "macos") {
    const file = this.controlFile(opts, target);
    const label = target === "linux" ? "Linux" : "macOS";
    if (!existsSync(file)) {
      throw new An3Error(
        "E_TARGET_UNAVAILABLE",
        `No ${label} UI control file at ${file}. Launch a ui-control automation build and set its ${target === "linux" ? "AN3_LINUX_UI_CONTROL_FILE" : "AN3_UI_CONTROL_FILE"} path.`,
      );
    }
    try {
      const parsed = JSON.parse(readFileSync(file, "utf8"));
      if (!parsed?.port || !parsed?.token) throw new Error("missing port/token");
      return { file, port: parsed.port, token: parsed.token };
    } catch (error) {
      throw new An3Error("E_TARGET_UNAVAILABLE", `Invalid ${label} UI control file ${file}: ${error.message}`);
    }
  }

  async controlCall(opts, target, route, params = {}) {
    const { port, token } = this.readControl(opts, target);
    const query = new URLSearchParams(params).toString();
    const path = `${route}${query ? `?${query}` : ""}`;
    return httpJson(port, path, {
      timeout: MACOS_UI_CONTROL_TIMEOUT_MS,
      headers: { "x-an3-token": token },
    }).then(result => {
      if (typeof result?.error === "string") {
        const code = result.error.includes("did not answer in time") ? "E_TIMEOUT" : "E_ACTION_FAILED";
        throw new An3Error(code, result.error);
      }
      return result;
    }).catch(error => {
      if (error instanceof An3Error) throw error;
      throw new An3Error("E_ACTION_FAILED", `${target} UI bridge call failed (${path}): ${error.message}`);
    });
  }

  async appStart(opts = {}) {
    const appPath = opts.app ?? process.env.AN3_MACOS_APP;
    if (!appPath || !existsSync(appPath)) {
      throw new An3Error("E_USAGE", "app start --target macos requires AN3_MACOS_APP (or --app) pointing at the built .app");
    }
    const executable = `${appPath}/Contents/MacOS/an3-offline-native`;
    if (!existsSync(executable) || !readFileSync(executable).includes("AN3_UI_CONTROL_FILE")) {
      throw new An3Error(
        "E_TARGET_UNAVAILABLE",
        "app start --target macos requires the ui-control automation build; --home does not isolate WebKit data for a packaged app, so use a copy with a unique bundle identifier",
      );
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
    const controlFile = this.controlFile(opts, "macos");
    const linuxControlFile = this.controlFile(opts, "linux");
    const macosReachable = existsSync(controlFile);
    const linuxReachable = existsSync(linuxControlFile);
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
        linux: linuxReachable
          ? { available: true, via: "ui-control", controlFile: linuxControlFile, reason: null, next: null }
          : {
              available: false,
              reason: "No Linux UI control file is configured. Use a test-only ui-control build and a loopback/SSH-forwarded bridge.",
              next: "Set AN3_LINUX_UI_CONTROL_FILE to the local control file.",
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
      const result = await this.controlCall(opts, target, "/tree");
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
    if (target === "macos" || target === "linux") {
      const testid = opts.testid ?? (typeof opts.selector === "string" ? opts.selector : null);
      if (!testid) throw new An3Error("E_USAGE", `ui query --target ${target} requires --testid <id>`);
      const result = await this.controlCall(opts, target, "/query", { testid });
      return { target, via: "ui-control", node: result.node };
    }
    return this.uiTree({ target, windows: opts.windows });
  }

  async uiClick(opts = {}) {
    const target = opts.target ?? "windows";
    if (target === "macos" || target === "linux") {
      const testid = opts.testid ?? (typeof opts.selector === "string" ? opts.selector : null);
      if (!testid) throw new An3Error("E_USAGE", `ui click --target ${target} requires --testid <id>`);
      const result = await this.controlCall(opts, target, "/click", { testid });
      if (!result.clicked) throw new An3Error("E_SELECTOR_NOT_FOUND", `no element with data-testid=${testid}`);
      return { target, via: "ui-control", clicked: true, testid };
    }
    await this.requireStructured(target);
  }

  async uiText(opts = {}) {
    const target = opts.target ?? "windows";
    if (target === "macos" || target === "linux") {
      const testid = opts.testid ?? (typeof opts.selector === "string" ? opts.selector : null);
      if (!testid) throw new An3Error("E_USAGE", `ui text --target ${target} requires --testid <id>`);
      const result = await this.controlCall(opts, target, "/text", { testid });
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
    if (target === "linux") {
      throw new An3Error("E_TARGET_UNAVAILABLE", "Linux ui-control exposes DOM actions but not native-process or presented-frame diagnostics.");
    }
    if (target !== "macos") await this.requireStructured(target);
    const result = await this.controlCall(opts, target, "/native");
    return {
      target,
      via: "ui-control",
      running: result.running === true,
      presentedFrames: Number(result.presentedFrames ?? 0),
    };
  }

  async uiWait(opts = {}) {
    const target = opts.target ?? "windows";
    if (target !== "macos" && target !== "linux") await this.requireStructured(target);
    const testid = opts.testid ?? (typeof opts.selector === "string" ? opts.selector : null);
    if (!testid) throw new An3Error("E_USAGE", `ui wait --target ${target} requires --testid <id>`);
    const timeout = Number(opts.timeout ?? 30_000);
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const result = await this.controlCall(opts, target, "/query", { testid });
      if (result.node && (opts.state ? result.node.state === opts.state : true)) {
        return { target, via: "ui-control", found: true, node: result.node };
      }
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    throw new An3Error("E_TIMEOUT", `ui wait timed out for data-testid=${testid}${opts.state ? ` state=${opts.state}` : ""}`);
  }
}
