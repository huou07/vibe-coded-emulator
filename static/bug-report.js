// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Bug report client: collects local diagnostics, sanitizes them in the browser,
// shows an explicit preview, and only uploads after the user consents. The
// server re-sanitizes every report; this pass exists so nothing sensitive ever
// leaves the device in the first place.
(function () {
  "use strict";

  var MAX_LOGS = 40;
  var MAX_LOG_LINE = 500;
  var MAX_DESCRIPTION = 4000;

  var FORBIDDEN_KEYS = {
    rom: 1, rompath: 1, romdata: 1, romfile: 1, romname: 1, rombytes: 1,
    save: 1, savefile: 1, savedata: 1, savestate: 1, state: 1, statefile: 1,
    token: 1, accesstoken: 1, refreshtoken: 1, pairingtoken: 1, pairingcode: 1,
    csrf: 1, cookiesecret: 1, password: 1, secret: 1, apikey: 1, privatekey: 1,
    accesskey: 1, githubtoken: 1, credential: 1, credentials: 1, env: 1,
    envvars: 1, environment: 1, ip: 1, ipaddress: 1, mac: 1, macaddress: 1,
    deviceid: 1, devicekey: 1, sessiontoken: 1, authorization: 1, sshid: 1,
    sshkey: 1, adbkey: 1
  };
  var FORBIDDEN_SUBSTRINGS = ["token", "password", "secret", "credential", "privatekey", "apikey"];

  var PATTERNS = [
    [/-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g, "[redacted-private-key]"],
    [/\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b/g, "[redacted]"],
    [/\bgithub_pat_[A-Za-z0-9_]{20,}\b/g, "[redacted]"],
    [/\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g, "[redacted]"],
    [/\bxox[baprs]-[A-Za-z0-9-]{10,}\b/g, "[redacted]"],
    [/\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b/g, "[redacted]"],
    [/\bBearer\s+[A-Za-z0-9._~+/-]{10,}=*/gi, "Bearer [redacted]"],
    [/\b(access_token|refresh_token|pairing_token|pairing_code|token|password|secret|api_key|apikey|key)=([^&\s"']+)/gi, "$1=[redacted]"],
    [/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g, "[redacted-email]"],
    [/\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b/g, "[redacted-mac]"],
    [/\b(?:[0-9A-Fa-f]{1,4}:){3,7}[0-9A-Fa-f]{1,4}\b/g, "[redacted-ip]"],
    [/\b(?:\d{1,3}\.){3}\d{1,3}\b/g, "[redacted-ip]"],
    [/([A-Za-z]:\\+Users\\+|\/Users\/|\/home\/)([^\\/\s"']+)/gi, "[user-path]"],
    [/(?:\/(?:srv|opt|var|tmp|private|etc|root|mnt|media|Volumes|Applications|System)|[A-Za-z]:\\\\)(?:[^\s"']*)?/gi, "[path]"],
    [/\.(?:gba|gbc|gb|nds|3ds|cia|cci|n64|z64|v64|sfc|smc|nes|iso|chd|cso|rvz|wbfs|wad|zip|7z|rar|sav|srm|state|dsv|ss[0-9])/gi, ""]
  ];

  function normalizeKey(key) {
    return String(key).toLowerCase().replace(/[^a-z0-9]/g, "");
  }

  function isForbiddenKey(key) {
    var normalized = normalizeKey(key);
    if (Object.prototype.hasOwnProperty.call(FORBIDDEN_KEYS, normalized)) return true;
    return FORBIDDEN_SUBSTRINGS.some(function (marker) { return normalized.indexOf(marker) !== -1; });
  }

  function sanitizeText(value) {
    var text = String(value == null ? "" : value);
    text = Array.prototype.filter.call(text, function (ch) {
      var code = ch.charCodeAt(0);
      return ch === "\n" || ch === "\t" || code >= 32;
    }).join("");
    for (var index = 0; index < PATTERNS.length; index += 1) {
      text = text.replace(PATTERNS[index][0], PATTERNS[index][1]);
    }
    return text.trim();
  }

  function sanitizeValue(value) {
    if (Array.isArray(value)) return value.map(sanitizeValue);
    if (value && typeof value === "object") {
      var result = {};
      Object.keys(value).forEach(function (key) {
        if (isForbiddenKey(key)) return;
        result[key] = sanitizeValue(value[key]);
      });
      return result;
    }
    if (typeof value === "string") return sanitizeText(value);
    return value;
  }

  function sanitizeReport(report) {
    var clean = sanitizeValue(report);
    if (clean && typeof clean === "object") {
      if (typeof clean.description === "string") clean.description = clean.description.slice(0, MAX_DESCRIPTION);
      if (Array.isArray(clean.logs)) {
        clean.logs = clean.logs.slice(-MAX_LOGS).map(function (line) { return String(line).slice(0, MAX_LOG_LINE); });
      }
    }
    return clean;
  }

  function configFromPage() {
    var output = document.getElementById("bugPreviewOutput");
    return {
      buildId: (output && output.dataset.build) || "",
      appVersion: (output && output.dataset.appVersion) || ""
    };
  }

  function platformName() {
    try {
      if (navigator.userAgentData && navigator.userAgentData.platform) return navigator.userAgentData.platform;
    } catch (_) {}
    return navigator.platform || "";
  }

  function osVersion() {
    var ua = navigator.userAgent || "";
    var patterns = [
      [/Windows NT [0-9.]+/i, 0],
      [/Mac OS X [0-9_.]+/i, 0],
      [/Android [0-9.]+/i, 0],
      [/iPhone OS [0-9_.]+/i, 0],
      [/Linux/i, 0]
    ];
    for (var index = 0; index < patterns.length; index += 1) {
      var match = ua.match(patterns[index][0]);
      if (match) return match[0];
    }
    return "";
  }

  function deviceModel() {
    var ua = navigator.userAgent || "";
    var match = ua.match(/\(([^)]*)\)/);
    if (!match) return "";
    return match[1].replace(/;\s*[^;]*Build[^;]*/i, "").split(";").slice(0, 3).join("; ");
  }

  function cpuArch() {
    var ua = navigator.userAgent || "";
    if (/arm64|aarch64/i.test(ua)) return "arm64";
    if (/x86_64|Win64|x64/i.test(ua)) return "x86_64";
    if (/arm/i.test(ua)) return "arm";
    return "";
  }

  function gpuInfo() {
    try {
      var canvas = document.createElement("canvas");
      var gl = canvas.getContext("webgl2") || canvas.getContext("webgl");
      if (!gl) return {};
      var ext = gl.getExtension("WEBGL_debug_renderer_info");
      return {
        renderer: String((ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)) || ""),
        vendor: String((ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR)) || ""),
        driver: String(gl.getParameter(gl.VERSION) || "")
      };
    } catch (_) {
      return {};
    }
  }

  function rendererState() {
    var requested = "auto";
    try { requested = localStorage.getItem("an3-presentation-renderer-v1") || "auto"; } catch (_) {}
    var status = globalThis.AN3RendererStatus || {};
    return {requested: requested, effective: String(status.effective || status.selected || "")};
  }

  function gameContext() {
    var context = {system: "", identifier: ""};
    try {
      var params = new URLSearchParams(location.search);
      if (params.get("system")) context.system = params.get("system");
      if (params.get("slug")) context.identifier = params.get("slug").toLowerCase().replace(/[^a-z0-9-]/g, "");
      var referrer = document.referrer || "";
      var match = referrer.match(/\/(?:play|game)\/([a-z0-9-]+)/i);
      if (match) context.identifier = match[1].toLowerCase();
    } catch (_) {}
    return context;
  }

  var logBuffer = [];
  var lastCrash = {};

  function pushLog(entry) {
    logBuffer.push(String(entry == null ? "" : entry).slice(0, MAX_LOG_LINE));
    if (logBuffer.length > MAX_LOGS) logBuffer.shift();
  }

  function installLogCapture() {
    if (typeof window === "undefined" || window.__an3BugCapture) return;
    window.__an3BugCapture = true;
    var originalError = console.error;
    console.error = function () {
      pushLog(Array.prototype.map.call(arguments, function (item) {
        return item && item.message ? item.message : String(item);
      }).join(" "));
      return originalError.apply(console, arguments);
    };
    window.addEventListener("error", function (event) {
      pushLog("error: " + (event.message || ""));
      lastCrash = {stage: "window.onerror", message: String(event.message || ""), stack: String((event.error && event.error.stack) || "")};
    });
    window.addEventListener("unhandledrejection", function (event) {
      var reason = event.reason || {};
      pushLog("rejection: " + (reason.message || String(reason)));
      lastCrash = {stage: "unhandledrejection", message: String(reason.message || reason), stack: String(reason.stack || "")};
    });
  }

  function buildReport() {
    var config = configFromPage();
    var context = gameContext();
    var gpu = gpuInfo();
    var renderer = rendererState();
    var gameInput = document.getElementById("bugGame");
    var descriptionInput = document.getElementById("bugDescription");
    return {
      reportSchemaVersion: 1,
      appVersion: config.appVersion,
      buildId: config.buildId,
      platform: platformName(),
      osVersion: osVersion(),
      deviceModel: deviceModel(),
      cpu: cpuArch(),
      cpuCores: navigator.hardwareConcurrency || null,
      deviceMemoryGb: navigator.deviceMemory || null,
      gpu: gpu.renderer || "",
      gpuDriver: gpu.driver || "",
      rendererRequested: renderer.requested,
      rendererEffective: renderer.effective,
      emulatorSystem: context.system || "",
      coreName: "",
      coreVersion: "",
      gameTitle: gameInput ? gameInput.value : "",
      gameIdentifier: context.identifier || "",
      settings: {renderer: renderer.requested, language: navigator.language},
      logs: logBuffer.slice(),
      crash: lastCrash,
      description: descriptionInput ? descriptionInput.value : "",
      language: navigator.language,
      userAgent: navigator.userAgent,
      screen: screen.width + "x" + screen.height,
      viewport: window.innerWidth + "x" + window.innerHeight,
      online: navigator.onLine,
      timestamp: Date.now()
    };
  }

  // Expose the pure helpers for tests before any DOM wiring runs. The native
  // support surface reuses the same sanitizer and log buffer, so there is one
  // sanitizer contract and one bounded log capture on every shell.
  globalThis.AN3BugReport = {
    sanitizeText: sanitizeText,
    sanitizeReport: sanitizeReport,
    buildReport: buildReport,
    isForbiddenKey: isForbiddenKey,
    getLogs: function () { return logBuffer.slice(); },
    getLastCrash: function () { return lastCrash; },
    clearLogs: function () { logBuffer.length = 0; lastCrash = {}; }
  };

  if (typeof document === "undefined" || !document.getElementById) return;

  installLogCapture();

  var byId = function (id) { return document.getElementById(id); };
  var output = byId("bugPreviewOutput");
  var preview = byId("bugPreview");
  var submit = byId("bugSubmit");
  var consent = byId("bugConsent");
  var status = byId("bugStatus");
  var description = byId("bugDescription");

  function refreshPreview() {
    var sanitized = sanitizeReport(buildReport());
    if (output) output.textContent = JSON.stringify(sanitized, null, 2);
    if (submit) submit.disabled = !(consent && consent.checked);
  }

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  async function send() {
    if (!consent || !consent.checked) return;
    submit.disabled = true;
    if (status) status.textContent = "Sending…";
    try {
      var response = await fetch("/api/bug-reports", {
        method: "POST",
        credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": csrfToken()},
        body: JSON.stringify(sanitizeReport(buildReport()))
      });
      var data = await response.json().catch(function () { return {}; });
      if (!response.ok) throw new Error(data.error || ("HTTP " + response.status));
      if (status) status.textContent = "Report sent (id " + data.id + ").";
      if (output) output.dataset.reportId = data.id;
    } catch (error) {
      if (status) status.textContent = "Could not send: " + (error.message || error);
    } finally {
      submit.disabled = !(consent && consent.checked);
    }
  }

  if (preview) preview.addEventListener("click", refreshPreview);
  if (consent) consent.addEventListener("change", refreshPreview);
  if (description) description.addEventListener("input", refreshPreview);
  if (submit) submit.addEventListener("click", send);
  refreshPreview();
})();
