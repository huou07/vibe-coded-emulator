// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Shared primitives for an3ctl: machine-readable envelope, stable exit codes,
// process execution, semantic selector parsing, and a zero-dependency Chrome
// DevTools Protocol client (Node 24 exposes a global WebSocket).

import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import http from "node:http";

export const EXIT = Object.freeze({
  OK: 0,
  INTERNAL: 1,
  USAGE: 2,
  TARGET_UNAVAILABLE: 3,
  NOT_FOUND: 4,
  TIMEOUT: 5,
  ACTION_FAILED: 6,
  STATE: 7,
});

const CODE_TO_EXIT = {
  E_USAGE: EXIT.USAGE,
  E_TARGET_UNAVAILABLE: EXIT.TARGET_UNAVAILABLE,
  E_NOT_FOUND: EXIT.NOT_FOUND,
  E_TIMEOUT: EXIT.TIMEOUT,
  E_ACTION_FAILED: EXIT.ACTION_FAILED,
  E_STATE: EXIT.STATE,
  E_INTERNAL: EXIT.INTERNAL,
};

export class An3Error extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = "An3Error";
    this.code = code;
    this.details = details;
  }
}

export function exitCodeFor(code) {
  return CODE_TO_EXIT[code] ?? EXIT.INTERNAL;
}

export function ok(command, target, data) {
  return { ok: true, command, target: target ?? null, data };
}

export function failure(command, target, error) {
  return {
    ok: false,
    command,
    target: target ?? null,
    error: {
      code: error.code ?? "E_INTERNAL",
      message: error.message ?? String(error),
      ...(error.details && Object.keys(error.details).length ? { details: error.details } : {}),
    },
  };
}

export function emit(envelope, { json }) {
  if (json) {
    process.stdout.write(JSON.stringify(envelope) + "\n");
  } else if (envelope.ok) {
    process.stdout.write(humanize(envelope) + "\n");
  } else {
    process.stderr.write(`${envelope.error.code}: ${envelope.error.message}\n`);
  }
  return envelope.ok ? EXIT.OK : exitCodeFor(envelope.error.code);
}

function humanize({ command, target, data }) {
  const head = `[${command}${target ? " " + target : ""}]`;
  if (data === undefined || data === null) return `${head} ok`;
  if (typeof data === "string") return `${head} ${data}`;
  return `${head}\n${JSON.stringify(data, null, 2)}`;
}

// ---------------------------------------------------------------------------
// Process execution (no shell; arrays only, so values cannot be injected).
// ---------------------------------------------------------------------------

export function run(command, args, { input, timeoutMs = 120000, env, cwd } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      stdio: ["pipe", "pipe", "pipe"],
      cwd,
      env: env ? { ...process.env, ...env } : process.env,
    });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill("SIGKILL");
      reject(new An3Error("E_TIMEOUT", `${command} timed out after ${timeoutMs}ms`, { command }));
    }, timeoutMs);
    child.stdout.on("data", (chunk) => (stdout += chunk));
    child.stderr.on("data", (chunk) => (stderr += chunk));
    child.on("error", (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(new An3Error("E_TARGET_UNAVAILABLE", `${command} could not be started: ${error.message}`, { command }));
    });
    child.on("close", (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({ code, stdout, stderr });
    });
    if (input !== undefined) {
      child.stdin.end(input);
    } else {
      child.stdin.end();
    }
  });
}

export async function runChecked(command, args, options = {}) {
  const result = await run(command, args, options);
  if (result.code !== 0) {
    throw new An3Error(
      options.errorCode ?? "E_ACTION_FAILED",
      `${command} exited ${result.code}: ${(result.stderr || result.stdout || "").trim().slice(0, 400)}`,
      { command, args, code: result.code },
    );
  }
  return result;
}

export function whichSync(command) {
  const paths = (process.env.PATH ?? "").split(":");
  for (const dir of paths) {
    if (!dir) continue;
    const candidate = `${dir}/${command}`;
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Semantic selectors
// ---------------------------------------------------------------------------

/**
 * Parse selector flags into a single descriptor. Priority: testid > id > role+name > name > text > css.
 * The descriptor is platform neutral; adapters translate it.
 */
export function parseSelector(flags) {
  const testId = flags.testid ?? flags["test-id"] ?? null;
  const id = flags.id ?? null;
  const role = flags.role ?? null;
  const name = flags.name ?? null;
  const text = flags.text ?? null;
  const css = flags.css ?? null;
  const nth = flags.nth !== undefined ? Number(flags.nth) : null;
  if (testId) return { kind: "testid", value: String(testId), nth };
  if (id) return { kind: "id", value: String(id), nth };
  if (role) return { kind: "role", value: { role: String(role), name: name ? String(name) : null }, nth };
  if (name) return { kind: "name", value: String(name), nth };
  if (text) return { kind: "text", value: String(text), nth };
  if (css) return { kind: "css", value: String(css), nth };
  return null;
}

export function requireSelector(flags) {
  const selector = parseSelector(flags);
  if (!selector) {
    throw new An3Error("E_USAGE", "A selector is required: --testid, --id, --role, --name, --text or --css.");
  }
  return selector;
}

export function selectorToCss(selector) {
  switch (selector.kind) {
    case "testid": return `[data-testid="${cssEscape(selector.value)}"]`;
    case "id": return `#${cssEscape(selector.value)}`;
    case "css": return selector.value;
    case "text": return null;
    case "role": return null;
    case "name": return null;
    default: return null;
  }
}

function cssEscape(value) {
  return String(value).replace(/["\\]/g, "\\$&");
}

// ---------------------------------------------------------------------------
// State directory (pid files, logs) — lives under the repo work/ tree.
// ---------------------------------------------------------------------------

export function stateDir(root) {
  return `${root}/work/an3ctl`;
}

// ---------------------------------------------------------------------------
// CDP (Chrome DevTools Protocol) over the native WebSocket.
// ---------------------------------------------------------------------------

export function httpJson(port, path, options = {}) {
  return new Promise((resolve, reject) => {
    const request = http.get({ host: "127.0.0.1", port, path, timeout: options.timeout ?? 5000, headers: options.headers }, (response) => {
      let body = "";
      response.on("data", (chunk) => (body += chunk));
      response.on("end", () => {
        try {
          resolve(JSON.parse(body));
        } catch (error) {
          reject(new An3Error("E_INTERNAL", `Invalid CDP response for ${path}: ${error.message}`));
        }
      });
    });
    request.on("timeout", () => {
      request.destroy();
      reject(new An3Error("E_TIMEOUT", `CDP HTTP request to :${port}${path} timed out`));
    });
    request.on("error", (error) => reject(new An3Error("E_TARGET_UNAVAILABLE", `CDP HTTP error: ${error.message}`)));
  });
}

export class CdpSession {
  constructor(ws) {
    this.ws = ws;
    this.nextId = 1;
    this.pending = new Map();
    ws.addEventListener("message", (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new An3Error("E_ACTION_FAILED", `${message.error.message} (${message.error.code})`));
        else resolve(message.result);
      }
    });
  }

  static async connect(wsUrl, { timeoutMs = 8000 } = {}) {
    const ws = new WebSocket(wsUrl);
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new An3Error("E_TIMEOUT", `CDP connect to ${wsUrl} timed out`)), timeoutMs);
      ws.addEventListener("open", () => {
        clearTimeout(timer);
        resolve();
      });
      ws.addEventListener("error", (event) => {
        clearTimeout(timer);
        reject(new An3Error("E_TARGET_UNAVAILABLE", `CDP socket error: ${event.message ?? "unknown"}`));
      });
    });
    return new CdpSession(ws);
  }

  send(method, params = {}, { timeoutMs = 30000 } = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new An3Error("E_TIMEOUT", `CDP ${method} timed out`));
      }, timeoutMs);
      this.pending.set(id, {
        resolve: (value) => {
          clearTimeout(timer);
          resolve(value);
        },
        reject: (error) => {
          clearTimeout(timer);
          reject(error);
        },
      });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression, { awaitPromise = true } = {}) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise,
    });
    if (result.exceptionDetails) {
      throw new An3Error("E_ACTION_FAILED", `Page evaluation failed: ${result.exceptionDetails.text ?? "unknown"}`);
    }
    return result.result?.value;
  }

  async evaluateJson(expression) {
    const raw = await this.evaluate(expression);
    if (typeof raw !== "string") return raw;
    try {
      return JSON.parse(raw);
    } catch {
      return raw;
    }
  }

  close() {
    try {
      this.ws.close();
    } catch {
      /* ignore */
    }
  }
}

export function sha256(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

export function parseJsonOutput(text) {
  const trimmed = String(text).trim();
  if (!trimmed) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    return null;
  }
}
