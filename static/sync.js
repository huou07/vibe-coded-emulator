// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
(function () {
  "use strict";
  var byId = function (id) { return document.getElementById(id); };
  var panel = byId("syncPanel");
  if (!panel) return;

  var status = byId("syncStatus");
  var list = byId("syncPeers");
  var select = byId("syncMode");
  var setStatus = function (text) { status.textContent = text; };

  var json = async function (url, options) {
    var response = await fetch(url, options);
    var data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data.error || ("HTTP " + response.status));
    return data;
  };

  // A stable, non-identifying device key for LAN presence. It lives only in
  // this browser's local storage and is never sent anywhere but the local app.
  var deviceId = (function () {
    try {
      var existing = localStorage.getItem("vibe-sync-device-v1");
      if (existing && /^[A-Za-z0-9_-]{8,64}$/.test(existing)) return existing;
      var created = typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : "sync" + Date.now() + Math.random().toString(36).slice(2, 10);
      localStorage.setItem("vibe-sync-device-v1", created);
      return created;
    } catch (_) {
      return "sync" + Date.now();
    }
  })();

  var renderModes = function (data) {
    select.innerHTML = "";
    (data.modes || []).forEach(function (mode) {
      var option = document.createElement("option");
      option.value = mode.id;
      option.textContent = mode.available ? mode.label : mode.label + " (unavailable)";
      option.disabled = !mode.available;
      option.selected = mode.id === data.mode;
      select.appendChild(option);
    });
    byId("syncAvailability").textContent = data.driveConfigured
      ? "Google Drive: configured"
      : "Google Drive: not configured (owner credentials required)";
  };

  var renderPeers = function (data) {
    list.innerHTML = "";
    var peers = (data.peers || []).filter(function (peer) { return peer.deviceId !== deviceId; });
    peers.forEach(function (peer) {
      var item = document.createElement("li");
      item.textContent = (peer.name || peer.deviceId) + " · " + peer.address + (peer.port ? ":" + peer.port : "");
      list.appendChild(item);
    });
    return peers.length;
  };

  var load = async function () {
    try {
      var data = await json("/api/sync/settings");
      renderModes(data);
      setStatus("Mode: " + data.mode);
    } catch (error) { setStatus(error.message); }
  };

  var save = async function () {
    try {
      var data = await json("/api/sync/settings", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({mode: select.value})
      });
      renderModes(data);
      setStatus("Saved: " + data.mode);
    } catch (error) { setStatus(error.message); }
  };

  var announce = async function () {
    try {
      var data = await json("/api/sync/lan/announce", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({deviceId: deviceId, name: "Vibe Coded Emulator (web)", port: 0})
      });
      setStatus("LAN peers: " + renderPeers(data));
    } catch (error) { setStatus(error.message); }
  };

  byId("syncSave").addEventListener("click", save);
  byId("syncRefreshPeers").addEventListener("click", announce);
  load();
  announce();
})();
