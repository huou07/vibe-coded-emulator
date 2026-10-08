// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Behavioral tests for the native bug report
// collection/sanitize/preview/consent/upload path. The shared sanitizer is the
// JavaScript port of bug_report.py already exercised by
// tests/bug_report_client.test.js; this suite proves the native surface reuses
// it and never leaks credentials, paths, addresses, or device identifiers.
import { test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const root = new URL("../", import.meta.url);
const read = relative => readFileSync(new URL(relative, root), "utf8");
const sanitizerSource = read("static/bug-report.js");
const nativeSource = read("native-offline/web/native-support.js");
const indexHtml = read("native-offline/web/index.html");
const FAKE_TOKEN = "ghp_" + "A".repeat(36);

const makeDom = () => {
  const ids = [
    "nativeBugReportCard", "nativeBugDescription", "nativeBugGame", "nativeBugPreview",
    "nativeBugPreviewOutput", "nativeBugConsent", "nativeBugSubmit", "nativeBugCancel",
    "nativeBugCopy", "nativeBugStatus",
  ];
  const map = new Map();
  for (const id of ids) {
    map.set(id, {
      id, hidden: false, checked: false, value: "", textContent: "",
      disabled: false, dataset: {}, listeners: {},
      addEventListener(type, handler) { (this.listeners[type] = this.listeners[type] || []).push(handler); },
      async fire(type, event = {}) { for (const handler of this.listeners[type] || []) await handler(event); },
    });
  }
  return {
    readyState: "complete",
    getElementById: id => map.get(id) || null,
    querySelector: () => null,
    createElement: () => ({getContext: () => null, style: {}}),
    addEventListener() {},
    element: id => map.get(id),
  };
};

const createHarness = (options = {}) => {
  const sandbox = {
    console,
    document: options.dom || makeDom(),
    navigator: {
      userAgent: options.userAgent || "Mozilla/5.0 (Linux; Android 14) WebView",
      language: "en-US", platform: "Linux armv8l", hardwareConcurrency: 8,
      onLine: false, clipboard: {writeText: async () => {}},
    },
    screen: {width: 1080, height: 2400},
    location: {search: "", href: "https://appassets.androidplatform.net/index.html", referrer: ""},
    localStorage: (() => {
      const store = new Map();
      return {getItem: key => (store.has(key) ? store.get(key) : null), setItem: (key, value) => store.set(key, String(value)), removeItem: key => store.delete(key)};
    })(),
    fetch: options.fetch || (async () => ({ok: false, status: 0, json: async () => ({})})),
    addEventListener() {},
    dispatchEvent() { return true; },
    CustomEvent: class CustomEvent { constructor(type, init) { this.type = type; this.detail = init && init.detail; } },
  };
  sandbox.window = sandbox;
  vm.runInNewContext(sanitizerSource, sandbox);
  vm.runInNewContext(nativeSource, sandbox);
  return sandbox;
};

const json = value => JSON.parse(JSON.stringify(value));

test("native settings and runtime no longer expose Sync controls", () => {
  const schema = JSON.parse(read("native-offline/shared/native-settings-schema.json"));
  const kotlinSchema = read("native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativeSettingsSchema.kt");
  const jsModel = read("native-offline/web/native-settings.js");
  assert.equal(schema.global.some(item => item.id === "lan-sync"), false);
  assert.doesNotMatch(kotlinSchema, /lan-sync|LAN Sync/);
  assert.doesNotMatch(jsModel, /lan-sync|LAN Sync/);
  assert.doesNotMatch(indexHtml, /data-settings-(?:tab|pane)="sync"|nativeSync|LAN Sync|Google Sync/);
  assert.doesNotMatch(indexHtml, /native-sync\.js|sync-transfer\.js/);
});

test("the Bug Report entry is present in the native Settings surface", () => {
  assert.match(indexHtml, /data-testid="bug-report"/);
  for (const id of ["nativeBugDescription", "nativeBugPreview", "nativeBugConsent", "nativeBugSubmit", "nativeBugCancel"]) {
    assert.match(indexHtml, new RegExp(`id="${id}"`), `${id} must be wired`);
  }
  assert.match(indexHtml, /native-support\.js/);
  assert.match(indexHtml, /static\/bug-report\.js/);
});

test("collection is allowlist-first and sanitizes credentials, paths, MACs and IPs", () => {
  const sandbox = createHarness();
  const api = sandbox.AN3NativeSupport;
  const report = api.collectDiagnostics({
    description: `token=${FAKE_TOKEN} mac de:ad:be:ef:00:11 ip 10.1.2.3 path ~/<REDACTED_PATH> mail a@b.invalid`,
    gameTitle: "Clean title"
  });
  const serialized = JSON.stringify(report);
  assert.doesNotMatch(serialized, /ghp_/);
  assert.doesNotMatch(serialized, /de:ad:be:ef:00:11/);
  assert.doesNotMatch(serialized, /10\.1\.2\.3/);
  assert.doesNotMatch(serialized, /developer/);
  assert.doesNotMatch(serialized, /a@b\.invalid/);
  assert.doesNotMatch(serialized, /\.gba/);
  assert.equal(api.collectDiagnostics({description: "keep me"}).description, "keep me");
});

test("allowlist drops unknown and forbidden top-level fields", () => {
  const sandbox = createHarness();
  const clean = sandbox.AN3NativeSupport.allowlistReport({
    description: "ok", rendererRequested: "vulkan", romPath: "/secret.gba",
    accessToken: FAKE_TOKEN, saveState: "AAE=", SharedPreferences: "dump"
  });
  assert.equal(clean.description, "ok");
  assert.equal(clean.rendererRequested, "vulkan");
  assert.equal("romPath" in clean, false);
  assert.equal("accessToken" in clean, false);
  assert.equal("saveState" in clean, false);
  assert.equal("SharedPreferences" in clean, false);
});

test("cancelling never uploads and clears the form", async () => {
  const dom = makeDom();
  const fetchCalls = [];
  const sandbox = createHarness({dom, fetch: async (...args) => { fetchCalls.push(args); return {ok: true, status: 200, json: async () => ({})}; }});
  const element = id => dom.element(id);
  element("nativeBugDescription").value = "something broke with token " + FAKE_TOKEN;
  element("nativeBugConsent").checked = true;
  element("nativeBugConsent").addEventListener("change", () => {});
  // The module wired its listener during load; drive it directly.
  await element("nativeBugCancel").fire("click");
  assert.equal(element("nativeBugDescription").value, "");
  assert.equal(element("nativeBugConsent").checked, false);
  assert.equal(element("nativeBugSubmit").disabled, true);
  assert.match(element("nativeBugStatus").textContent, /cancelled/i);
  assert.equal(fetchCalls.length, 0);
  assert.ok(sandbox.AN3NativeSupport);
});

test("an unavailable backend does not crash and keeps the user's description", async () => {
  const dom = makeDom();
  const sandbox = createHarness({dom, fetch: async () => { throw new Error("network down"); }});
  sandbox.AN3SupportOrigin = "http://127.0.0.1:9";
  const element = id => dom.element(id);
  element("nativeBugDescription").value = "kept text";
  element("nativeBugConsent").checked = true;
  await element("nativeBugConsent").fire("change");
  await element("nativeBugSubmit").fire("click");
  assert.equal(element("nativeBugDescription").value, "kept text");
  assert.match(element("nativeBugStatus").textContent, /Could not reach|no configured support server/i);
  assert.ok(sandbox.AN3NativeSupport);
});

test("a successful submit posts a sanitized payload to /api/bug-reports", async () => {
  let received = null;
  let receivedPath = "";
  let receivedCapability = null;
  const server = http.createServer((request, response) => {
    receivedPath = request.url;
    let body = "";
    request.on("data", chunk => { body += chunk; });
    request.on("end", () => {
      if (request.url === "/api/support/capability") {
        response.writeHead(200, {"Content-Type": "application/json"});
        response.end(JSON.stringify({capability: "cap-test", expiresAt: Date.now() + 60000}));
        return;
      }
      received = JSON.parse(body);
      receivedCapability = request.headers["x-an3-support-capability"];
      response.writeHead(201, {"Content-Type": "application/json"});
      response.end(JSON.stringify({ok: true, id: 42, issue: {attempted: true, created: false, reason: "not configured"}}));
    });
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  try {
    const origin = `http://127.0.0.1:${server.address().port}`;
    const sandbox = createHarness({fetch: globalThis.fetch});
    const api = sandbox.AN3NativeSupport;
    const report = api.collectDiagnostics({description: "crash with token " + FAKE_TOKEN});
    const result = await api.submitReport(report, {origin});
    assert.equal(result.ok, true);
    assert.equal(result.id, 42);
    assert.equal(receivedPath, "/api/bug-reports");
    assert.equal(receivedCapability, "cap-test");
    assert.ok(received.description.includes("crash"));
    assert.doesNotMatch(JSON.stringify(received), /ghp_/);
    assert.equal("romPath" in received, false);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
});

test("another session's submit gets no credentials and no token from the client", () => {
  const combined = nativeSource + sanitizerSource;
  // A real token literal (prefix plus 20+ body characters) must never appear.
  assert.doesNotMatch(combined, /\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b/);
  assert.doesNotMatch(combined, /\bgithub_pat_[A-Za-z0-9_]{20,}\b/);
  assert.doesNotMatch(combined, /GITHUB_ISSUES_TOKEN|GITHUB_TOKEN|AN3_GITHUB/);
  assert.doesNotMatch(nativeSource, /Authorization/);
});
