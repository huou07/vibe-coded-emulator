// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Native Settings support surface: the global LAN Sync switch, the disabled
// Google Sync placeholder, and the bug report entry for the offline shell.
//
// Architecture honesty: the offline Android/desktop app has no account and no
// HTTP session. It therefore cannot change the server-side per-user LAN sync
// gate in app.py. This module stores the canonical GLOBAL native setting
// `lan-sync` (shared/native-settings-schema.json) through the one existing
// Android SharedPreferences adapter. The bug report collects, sanitizes,
// previews, and only then uploads to the existing /api/bug-reports endpoint
// when a support origin is explicitly configured.
//
// The support origin is a plain configuration value injected at package time
// (a meta tag), never a secret. Anonymous submission uses a server-issued
// opaque capability with a finite lifetime and use count: the client requests
// one from the allowlisted origin, holds it in memory only, and sends it as a
// bearer header. It never ships or reads a GitHub token, never sends cookies,
// and never fabricates a MAC or device-fingerprint identity. The Phone
// Controller host is a separate service and is never gated by this switch.
(() => {
  const LAN_SYNC_KEY = "lan-sync";
  const LAN_SYNC_FALLBACK_KEY = "an3-native-lan-sync-v1";
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

  // The one canonical native setting store. `AN3AndroidSettings` is the
  // generated Android adapter over SharedPreferences; the browser-only dev
  // shell falls back to localStorage under the same logical key.
  const readLanSync = (bridge = globalThis.AN3AndroidSettings) => {
    if (bridge && typeof bridge.all === "function") {
      const snapshot = parse(bridge.all());
      const value = snapshot && snapshot.global ? snapshot.global[LAN_SYNC_KEY] : undefined;
      if (value === true || value === "true") return true;
      if (value === false || value === "false") return false;
      return true;
    }
    try {
      const stored = localStorage.getItem(LAN_SYNC_FALLBACK_KEY);
      if (stored === "0" || stored === "false") return false;
      if (stored === "1" || stored === "true") return true;
    } catch (_) {}
    return true;
  };

  const writeLanSync = (enabled, bridge = globalThis.AN3AndroidSettings) => {
    const value = Boolean(enabled);
    if (bridge && typeof bridge.save === "function") {
      const result = parse(bridge.save(JSON.stringify({[LAN_SYNC_KEY]: value})));
      const rejected = Array.isArray(result.rejected) ? result.rejected : [];
      return {ok: result.ok !== false && !rejected.includes(LAN_SYNC_KEY), value, storage: "native", rejected};
    }
    try {
      localStorage.setItem(LAN_SYNC_FALLBACK_KEY, value ? "1" : "0");
      return {ok: true, value, storage: "local", rejected: []};
    } catch (error) {
      return {ok: false, value, storage: "local", rejected: [], error: String(error && error.message || error)};
    }
  };

  const publishLanSync = value => {
    globalThis.AN3NativeLanSyncEnabled = value;
    try { globalThis.dispatchEvent(new CustomEvent("an3-lan-sync-change", {detail: {enabled: value}})); } catch (_) {}
  };

  // The single predicate every native LAN content-sync path must consult. OFF
  // means no discovery, no advertising, and no automatic transfer for content
  // sync. It never gates the separate Phone Controller service.
  const lanContentSyncAllowed = (bridge = globalThis.AN3AndroidSettings) => readLanSync(bridge) === true;

  // Only a small, explicitly chosen subset of settings is ever collected. The
  // full SharedPreferences snapshot is never serialized into a report.
  const settingsSnapshot = bridge => {
    const status = globalThis.AN3RendererStatus || {};
    return {
      language: navigator.language,
      lanSync: readLanSync(bridge),
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

  const collectDiagnostics = ({description = "", gameTitle = "", bridge = globalThis.AN3AndroidSettings} = {}) => {
    const api = globalThis.AN3BugReport;
    const base = api && typeof api.buildReport === "function" ? api.buildReport() : {};
    const raw = Object.assign({}, base, {
      reportSchemaVersion: 1,
      appVersion: appVersion(),
      buildId: buildId(),
      platform: platformLabel(),
      gameTitle: String(gameTitle || ""),
      description: String(description || ""),
      settings: settingsSnapshot(bridge),
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
    LAN_SYNC_KEY,
    SUPPORT_PATH,
    CAPABILITY_PATH,
    CAPABILITY_HEADER,
    SUPPORT_ORIGIN_META,
    ALLOWED_FIELDS,
    readLanSync,
    writeLanSync,
    publishLanSync,
    lanContentSyncAllowed,
    collectDiagnostics,
    sanitizeReport,
    allowlistReport,
    supportOrigin,
    requestCapability,
    submitReport
  };

  if (typeof document === "undefined" || !document.getElementById) return;

  const start = () => {
    const bridge = globalThis.AN3AndroidSettings;

    // LAN Sync: global (never per-core). OFF stores the switch; the native
    // shell has no LAN content-sync service yet, so nothing local is advertised
    // and the Phone Controller session stays untouched either way.
    const syncCard = document.getElementById("nativeSyncCard");
    const lanToggle = document.getElementById("nativeLanSyncToggle");
    const lanStatus = document.getElementById("nativeLanSyncStatus");
    if (syncCard) {
      syncCard.hidden = false;
      const current = readLanSync(bridge);
      publishLanSync(current);
      if (lanToggle) {
        lanToggle.checked = current;
        lanToggle.addEventListener("change", () => {
          const result = writeLanSync(lanToggle.checked, bridge);
          publishLanSync(result.value);
          if (lanStatus) {
            lanStatus.textContent = result.ok
              ? (lanToggle.checked ? "LAN Sync on. Stored on this device." : "LAN Sync off. No LAN content sync is advertised.")
              : "LAN Sync preference could not be stored.";
          }
        });
      }
      if (lanStatus) lanStatus.textContent = current ? "LAN Sync on" : "LAN Sync off";
    }

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
      bridge
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
