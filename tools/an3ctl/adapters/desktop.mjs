// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Desktop structured adapters (Phase 3). The desktop shells are Tauri apps, so
// the structured control surface must come from WebView2/WebKit DevTools (CDP)
// or the WebDriver bridge, never from coordinates or PrintWindow.
//
// This module reports the verified state of each path and performs the checks
// that are safe today. It intentionally refuses to fall back to coordinate
// automation; when the debug surface is not exposed it returns a precise,
// machine-readable instruction instead of guessing.

import { An3Error, httpJson, run } from "../lib/core.mjs";

export class DesktopAdapter {
  constructor(root) {
    this.root = root;
    this.name = "desktop";
  }

  targets() {
    return ["macos", "linux", "windows"];
  }

  async windowsDebugProbe({ host = "an3-win11-build", port = 9222 } = {}) {
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

  async available(opts = {}) {
    return {
      available: false,
      targets: {
        macos: {
          available: false,
          reason: "The macOS shell is a Tauri/WebKit app. Structured control requires the Tauri WebDriver path or a test-only in-app automation bridge (loopback/Unix socket).",
          next: "See docs/agent-control-plane.md#phase-3-desktop-adapters.",
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
    return this.uiTree({ target: opts.target ?? "windows", windows: opts.windows });
  }
}
