// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
(function () {
  "use strict";
  var byId = function (id) { return document.getElementById(id); };

  var postJson = async function (url, payload) {
    var response = await fetch(url, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    var data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data.error || ("HTTP " + response.status));
    return data;
  };

  var hostPanel = byId("ctrlHostPanel");
  if (hostPanel) {
    var status = byId("ctrlStatus");
    var hostCode = "";
    var hostToken = "";
    var timer = 0;
    var poll = async function () {
      try {
        var response = await fetch("/api/controller/state?code=" + encodeURIComponent(hostCode) +
          "&hostToken=" + encodeURIComponent(hostToken));
        if (response.status === 403 || response.status === 404) {
          clearInterval(timer);
          status.textContent = "Session ended.";
          return;
        }
        var state = await response.json();
        if (!state.paired) {
          status.textContent = "Waiting for a phone… " + state.expiresInSeconds + "s";
          return;
        }
        var buttons = state.state && state.state.b ? state.state.b.join(",") : "";
        status.textContent = "Phone connected · " + (buttons || "no input") +
          (state.needsResync ? " · resync requested" : "") + " · " + state.expiresInSeconds + "s";
      } catch (_) { /* transient; the next poll retries */ }
    };
    (async function () {
      try {
        var data = await postJson("/api/controller/session", {deviceId: "host"});
        hostCode = data.code;
        hostToken = data.hostToken;
        byId("ctrlCode").textContent = hostCode;
        var link = byId("ctrlLink");
        link.href = data.joinPath;
        link.textContent = location.origin + data.joinPath;
        var qr = byId("ctrlQr");
        if (qr) {
          qr.src = "/api/controller/qr.svg?code=" + encodeURIComponent(hostCode);
          qr.hidden = false;
        }
        status.textContent = "Waiting for a phone… " + data.ttlSeconds + "s";
        timer = setInterval(poll, 500);
      } catch (error) {
        status.textContent = error.message;
      }
    })();
  }

  var joinPanel = byId("ctrlJoinPanel");
  if (joinPanel) {
    var joinStatus = byId("ctrlStatus");
    var pad = byId("ctrlPad");
    var codeInput = byId("ctrlCode");
    var pairedCode = "";
    var token = "";
    var sequence = 0;
    var pressed = new Set();
    var queued = false;
    var flush = async function () {
      queued = false;
      sequence += 1;
      try {
        await postJson("/api/controller/state", {
          code: pairedCode,
          token: token,
          s: sequence,
          b: Array.from(pressed),
          a: [0, 0, 0, 0]
        });
        joinStatus.textContent = "Connected · sent " + sequence;
      } catch (error) {
        joinStatus.textContent = error.message;
      }
    };
    var queueFlush = function () {
      if (queued) return;
      queued = true;
      setTimeout(flush, 16);
    };
    byId("ctrlConnect").addEventListener("click", async function () {
      joinStatus.textContent = "Pairing…";
      try {
        var data = await postJson("/api/controller/pair", {
          code: codeInput.value.trim(),
          deviceId: "phone"
        });
        token = data.token;
        pairedCode = data.code;
        codeInput.value = data.code;
        pad.hidden = false;
        joinStatus.textContent = "Connected";
      } catch (error) {
        joinStatus.textContent = error.message;
      }
    });
    if (pad) {
      pad.querySelectorAll("[data-btn]").forEach(function (button) {
        var name = button.getAttribute("data-btn");
        var press = function (event) { event.preventDefault(); pressed.add(name); queueFlush(); };
        var release = function (event) { event.preventDefault(); if (pressed.delete(name)) queueFlush(); };
        button.addEventListener("pointerdown", press);
        button.addEventListener("pointerup", release);
        button.addEventListener("pointercancel", release);
        button.addEventListener("pointerleave", release);
        button.addEventListener("contextmenu", function (event) { event.preventDefault(); });
      });
    }
  }
})();
