// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Native support surface for sanitized bug reports. Collection is allowlist-
// first; a report is previewed and sent only after explicit user consent.
//
// The support origin is a plain configuration value injected at package time
// (a meta tag), never a secret. Anonymous submission uses a server-issued
// opaque capability with a finite lifetime and use count: the client requests
// one from the allowlisted origin, holds it in memory only, and sends it as a
// bearer header. It never ships or reads a GitHub token, never sends cookies,
// and never fabricates a MAC or device-fingerprint identity. The Phone
// Native support sharing is independent of local game input and account state.
(() => {
  const SUPPORT_PATH = "/api/bug-reports";
  const CAPABILITY_PATH = "/api/support/capability";
  const CAPABILITY_HEADER = "X-AN3-Support-Capability";
  const SUPPORT_ORIGIN_META = "an3-support-origin";

  // Mirrors the server allowlist in bug_report.py ALLOWED_FIELDS. Collection is
  // allowlist-first: a field the server does not know can never be attached.
  const ALLOWED_FIELDS = new Set([
    "reportSchemaVersion", "appVersion", "buildId", "platform", "osVersion",
    "deviceModel", "cpu", "cpuCores", "deviceMemoryGb", "gpu", "gpuDriver",
    "rendererRequested", "rendererEffective", "emulatorSystem", "coreName",
    "coreVersion", "gameTitle", "gameIdentifier", "settings", "logs", "crash",
    "description", "language", "userAgent", "screen", "viewport", "online",
    "timestamp"
  ]);

  const parse = value => { try { return JSON.parse(value || "{}"); } catch (_) { return {}; } };

  const platformLabel = () => {
    if (/Android/i.test(navigator.userAgent)) return "android";
    if (/iPhone|iPad|iPod/i.test(navigator.userAgent)) return "ios";
    return "desktop";
  };

  const appVersion = () => {
    const fromGlobal = globalThis.AN3NativeAppVersion;
    if (typeof fromGlobal === "string" && fromGlobal) return fromGlobal;
    const node = document.querySelector("[data-app-version]");
    return node ? String(node.dataset.appVersion || "") : "";
  };

  const buildId = () => {
    const fromGlobal = globalThis.AN3NativeBuildId;
    return typeof fromGlobal === "string" ? fromGlobal : "";
  };

  // Only a small, explicitly chosen subset of settings is ever collected. The
  // full SharedPreferences snapshot is never serialized into a report.
  const settingsSnapshot = () => {
    const status = globalThis.AN3RendererStatus || {};
    return {
      language: navigator.language,
      rendererRequested: status.requested || status.effective || "auto",
      emulatorSystems: Array.isArray(globalThis.AN3NativeIntegratedSystems)
        ? globalThis.AN3NativeIntegratedSystems.slice()
        : []
    };
  };

  const allowlistReport = raw => {
    const report = {};
    for (const key of Object.keys(raw)) if (ALLOWED_FIELDS.has(key)) report[key] = raw[key];
    return report;
  };

  // The existing client sanitizer (static/bug-report.js) is the JavaScript port
  // of bug_report.py's scrub rules; reuse it instead of adding a third copy.
  const sanitizeReport = report => {
    const api = globalThis.AN3BugReport;
    if (api && typeof api.sanitizeReport === "function") return api.sanitizeReport(report);
    return report;
  };

  const collectDiagnostics = ({description = "", gameTitle = ""} = {}) => {
    const api = globalThis.AN3BugReport;
    const base = api && typeof api.buildReport === "function" ? api.buildReport() : {};
    const raw = Object.assign({}, base, {
      reportSchemaVersion: 1,
      appVersion: appVersion(),
      buildId: buildId(),
      platform: platformLabel(),
      gameTitle: String(gameTitle || ""),
      description: String(description || ""),
      settings: settingsSnapshot(),
      logs: api && typeof api.getLogs === "function" ? api.getLogs() : [],
      crash: api && typeof api.getLastCrash === "function" ? api.getLastCrash() : {},
      timestamp: Date.now()
    });
    return sanitizeReport(allowlistReport(raw));
  };

  // The support origin is configuration, not a secret. It is resolved from an
  // injected meta tag (the packaged shell) or an explicit global (tests/dev),
  // and normalized to a scheme + authority with no trailing slash.
  const supportOrigin = (explicit, doc = typeof document !== "undefined" ? document : null) => {
    let raw = explicit != null ? explicit : globalThis.AN3SupportOrigin;
    if (!raw && doc && typeof doc.querySelector === "function") {
      const node = doc.querySelector('meta[name="' + SUPPORT_ORIGIN_META + '"]');
      raw = node ? node.getAttribute("content") : "";
    }
    const value = String(raw || "").trim().replace(/\/+$/, "");
    if (!/^https?:\/\/[^\s/]+$/i.test(value)) return "";
    return value;
  };

  // Ask the allowlisted server for a short-lived opaque capability. It carries
  // no identity, no account, and no secret, and it is kept in memory only.
  const requestCapability = async (origin, fetchImpl) => {
    const response = await fetchImpl(origin + CAPABILITY_PATH, {
      method: "GET",
      credentials: "omit",
      headers: {"Accept": "application/json"}
    });
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok || !data.capability) {
      return {ok: false, status: response.status, error: data.error || ("HTTP " + response.status)};
    }
    return {ok: true, capability: String(data.capability), expiresAt: Number(data.expiresAt) || 0};
  };

  // POST only to the existing backend route. The native shell has no session,
  // so a server response of 401/403 is surfaced verbatim: the report is never
  // silently dropped and never retried without the user. `credentials: "omit"`
  // is deliberate: the offline shell has no cookie to send and must never
  // attach one to a cross-origin support request.
  const submitReport = async (report, options = {}) => {
    const origin = supportOrigin(options.origin);
    if (!origin) return {ok: false, unavailable: true, reason: "no-support-server", report};
    const fetchImpl = options.fetch || globalThis.fetch;
    if (typeof fetchImpl !== "function") return {ok: false, unavailable: true, reason: "fetch-unavailable", report};
    try {
      const issued = await requestCapability(origin, fetchImpl);
      if (!issued.ok) {
        return {ok: false, status: issued.status, error: issued.error, report};
      }
      const response = await fetchImpl(origin + SUPPORT_PATH, {
        method: "POST",
        credentials: "omit",
        headers: {"Content-Type": "application/json", [CAPABILITY_HEADER]: issued.capability},
        body: JSON.stringify(report)
      });
      let data = {};
      try { data = await response.json(); } catch (_) {}
      if (!response.ok) {
        return {ok: false, status: response.status, error: data.error || ("HTTP " + response.status), report};
      }
      return {ok: true, status: response.status, id: data.id, issue: data.issue, report};
    } catch (error) {
      return {ok: false, network: true, error: String(error && error.message || error), report};
    }
  };

  globalThis.AN3NativeSupport = {
    SUPPORT_PATH,
    CAPABILITY_PATH,
    CAPABILITY_HEADER,
    SUPPORT_ORIGIN_META,
    ALLOWED_FIELDS,
    collectDiagnostics,
    sanitizeReport,
    allowlistReport,
    supportOrigin,
    requestCapability,
    submitReport
  };

  if (typeof document === "undefined" || !document.getElementById) return;

  const start = () => {
    const report = document.getElementById("nativeBugReportCard");
    if (!report) return;

    const description = document.getElementById("nativeBugDescription");
    const game = document.getElementById("nativeBugGame");
    const previewButton = document.getElementById("nativeBugPreview");
    const output = document.getElementById("nativeBugPreviewOutput");
    const consent = document.getElementById("nativeBugConsent");
    const submit = document.getElementById("nativeBugSubmit");
    const cancel = document.getElementById("nativeBugCancel");
    const copy = document.getElementById("nativeBugCopy");
    const status = document.getElementById("nativeBugStatus");

    const collect = () => collectDiagnostics({
      description: description ? description.value : "",
      gameTitle: game ? game.value : "",
    });

    const refresh = () => {
      const clean = collect();
      if (output) output.textContent = JSON.stringify(clean, null, 2);
      if (submit) submit.disabled = !(consent && consent.checked);
      return clean;
    };

    previewButton?.addEventListener("click", () => { refresh(); if (status) status.textContent = "Preview updated."; });
    consent?.addEventListener("change", refresh);
    description?.addEventListener("input", () => { if (submit) submit.disabled = !(consent && consent.checked); });

    cancel?.addEventListener("click", () => {
      if (description) description.value = "";
      if (game) game.value = "";
      if (consent) consent.checked = false;
      if (submit) submit.disabled = true;
      if (status) status.textContent = "Report cancelled. Nothing was sent.";
      refresh();
    });

    copy?.addEventListener("click", async () => {
      const text = output ? output.textContent : "";
      try {
        await navigator.clipboard.writeText(text);
        if (status) status.textContent = "Sanitized report copied.";
      } catch (_) {
        if (status) status.textContent = "Copy is unavailable; select the preview text instead.";
      }
    });

    submit?.addEventListener("click", async () => {
      if (!consent || !consent.checked) return;
      submit.disabled = true;
      if (status) status.textContent = "Sending…";
      const clean = refresh();
      const result = await submitReport(clean);
      if (result.ok) {
        if (status) status.textContent = "Report sent (id " + result.id + ").";
        return;
      }
      // The description, game name and consent stay in the form so a retry or a
      // manual handoff never loses the user's text.
      if (result.unavailable && result.reason === "no-support-server") {
        if (status) status.textContent = "This offline build has no configured support server. Nothing was sent; use Copy to send the sanitized report manually.";
      } else if (result.network) {
        if (status) status.textContent = "Could not reach the support server. Your text is kept; try again.";
      } else {
        if (status) status.textContent = "Could not send: " + (result.error || "unknown error") + ". Your text is kept; try again.";
      }
    });

    refresh();
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once: true});
  else start();
})();
