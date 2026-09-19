// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
(function () {
  "use strict";
  var byId = function (id) { return document.getElementById(id); };
  var panel = byId("syncPanel");
  if (!panel) return;

  var statusNode = byId("syncStatus");
  var list = byId("syncPeers");
  var select = byId("syncMode");
  var detail = byId("syncModeDetail");
  var availability = byId("syncAvailability");
  var conflictBox = byId("syncConflicts");
  var romWarning = byId("syncRomWarning");
  var lanToggle = byId("syncLanEnabled");
  var lanDetail = byId("syncLanDetail");
  var googleToggle = byId("syncGoogleEnabled");
  var googleDetail = byId("syncGoogleDetail");
  var contentIds = {save: "syncContentSave", state: "syncContentState", library: "syncContentLibrary", rom: "syncContentRom"};
  var state = {mode: "off", content: {}, modes: [], contentOptions: [], lanSyncEnabled: true};

  var setStatus = function (text) { statusNode.textContent = text; };
  var json = async function (url, options) {
    var response = await fetch(url, options);
    var data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data.error || ("HTTP " + response.status));
    return data;
  };

  var deviceId = (function () {
    try {
      var existing = localStorage.getItem("vibe-sync-device-v1");
      if (existing && /^[A-Za-z0-9_-]{8,64}$/.test(existing)) return existing;
      var created = typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : "sync" + Date.now() + Math.random().toString(36).slice(2, 10);
      localStorage.setItem("vibe-sync-device-v1", created);
      return created;
    } catch (_) { return "sync" + Date.now(); }
  })();

  var modeById = function (id) {
    for (var index = 0; index < state.modes.length; index += 1) if (state.modes[index].id === id) return state.modes[index];
    return null;
  };
  var modeSummary = function (mode) {
    if (mode === "auto") return "Uses the local network first, then Google Drive when needed.";
    if (mode === "lan") return "Transfers stay on this local network.";
    if (mode === "drive") return "Transfers go through Google Drive.";
    return "Sync is off. Nothing is transferred.";
  };

  var renderModes = function (data) {
    state.modes = data.modes || [];
    select.innerHTML = "";
    state.modes.forEach(function (mode) {
      var option = document.createElement("option");
      option.value = mode.id;
      option.textContent = mode.detail ? mode.label + " — " + mode.detail : mode.label;
      option.disabled = !mode.available;
      option.selected = mode.id === data.mode;
      select.appendChild(option);
    });
    var selected = modeById(data.mode);
    detail.textContent = selected ? modeSummary(selected.id) : "";
    availability.textContent = data.driveConfigured
      ? "Google Drive is connected for this build."
      : "Google Sync is coming later.";
  };

  var renderSyncSwitches = function (data) {
    state.lanSyncEnabled = data.lanSyncEnabled !== false;
    if (lanToggle) lanToggle.checked = state.lanSyncEnabled;
    if (lanDetail) {
      lanDetail.textContent = state.lanSyncEnabled
        ? "LAN sync is on. Devices on this network can exchange supported saves and states."
        : "LAN sync is off. No discovery or transfer runs.";
    }
    if (googleToggle) {
      googleToggle.checked = false;
      googleToggle.disabled = true;
    }
    if (googleDetail) {
      googleDetail.textContent = (data.googleSync && data.googleSync.message) || "Coming later";
    }
    select.disabled = !state.lanSyncEnabled;
    Object.keys(contentIds).forEach(function (key) {
      var node = byId(contentIds[key]);
      if (node) node.disabled = !state.lanSyncEnabled;
    });
    var saveButton = byId("syncSave");
    if (saveButton) saveButton.disabled = !state.lanSyncEnabled;
    var refreshButton = byId("syncRefreshPeers");
    if (refreshButton) refreshButton.disabled = !state.lanSyncEnabled;
  };

  var renderContent = function (data) {
    state.content = data.content || {};
    Object.keys(contentIds).forEach(function (key) {
      var node = byId(contentIds[key]);
      if (node) node.checked = Boolean(state.content[key]);
    });
    if (romWarning) romWarning.hidden = !state.content.rom;
  };

  var renderDevices = function (peers) {
    list.innerHTML = "";
    var self = document.createElement("li");
    self.className = "sync-device sync-device-self";
    var selfName = document.createElement("strong");
    selfName.textContent = "This device";
    var selfState = document.createElement("span");
    selfState.textContent = modeById(state.mode) ? "Synced" : "Off";
    self.appendChild(selfName); self.appendChild(selfState);
    list.appendChild(self);

    (peers || []).filter(function (peer) { return peer.deviceId !== deviceId; }).forEach(function (peer) {
      var item = document.createElement("li");
      item.className = "sync-device";
      var name = document.createElement("strong");
      name.textContent = peer.name || "Nearby device";
      var status = document.createElement("span");
      status.textContent = "Nearby · Synced";
      item.appendChild(name); item.appendChild(status);
      list.appendChild(item);
    });
  };

  // Real conflict resolution wiring. The web build has no wired local store
  // yet, so this stays hidden until a plan returns an actual conflict; native
  // clients and the future store integration call the same endpoint.
  var renderConflicts = function (transfers) {
    if (!conflictBox) return;
    var conflicts = (transfers || []).filter(function (transfer) { return transfer.direction === "conflict"; });
    conflictBox.innerHTML = "";
    if (!conflicts.length) { conflictBox.hidden = true; return; }
    var title = document.createElement("h3");
    title.textContent = "Save Conflict";
    conflictBox.appendChild(title);
    conflicts.forEach(function (conflict) {
      var card = document.createElement("div");
      card.className = "sync-conflict";
      var label = document.createElement("strong");
      label.textContent = conflict.key;
      card.appendChild(label);
      var actions = document.createElement("div");
      actions.className = "form-actions";
      [["local", "Keep this device"], ["remote", "Keep other device"], ["both", "Keep Both"]].forEach(function (choice) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "button";
        button.textContent = choice[1];
        button.addEventListener("click", async function () {
          try {
            await json("/api/sync/resolve", {
              method: "POST",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify({kind: conflict.kind, key: conflict.key, resolution: choice[0]})
            });
            setStatus("Conflict resolved.");
            renderConflicts(transfers.filter(function (item) { return item !== conflict; }));
          } catch (error) { setStatus(error.message); }
        });
        actions.appendChild(button);
      });
      card.appendChild(actions);
      conflictBox.appendChild(card);
    });
    conflictBox.hidden = false;
  };
  window.AN3Sync = {renderPlan: function (plan) { if (plan && plan.transfers) renderConflicts(plan.transfers); }};

  var load = async function () {
    try {
      var data = await json("/api/sync/settings");
      renderModes(data);
      renderContent(data);
      renderSyncSwitches(data);
      setStatus("");
    } catch (error) { setStatus(error.message); }
  };

  var collectContent = function () {
    var content = {};
    Object.keys(contentIds).forEach(function (key) {
      var node = byId(contentIds[key]);
      if (node) content[key] = Boolean(node.checked);
    });
    return content;
  };

  var save = async function () {
    try {
      var data = await json("/api/sync/settings", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({mode: select.value, content: collectContent()})
      });
      renderModes(data);
      renderContent(data);
      setStatus("Saved.");
    } catch (error) { setStatus(error.message); }
  };

  var announce = async function () {
    if (!state.lanSyncEnabled) { renderDevices([]); return; }
    try {
      var data = await json("/api/sync/lan/announce", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({deviceId: deviceId, name: "Vibe Coded Emulator", port: 0})
      });
      renderDevices(data.peers || []);
      setStatus("");
    } catch (error) { setStatus(error.message); }
  };

  // The global LAN Sync switch only gates sync. Phone Controller networking is
  // a separate service and keeps running regardless of this value.
  var toggleLanSync = async function () {
    var desired = Boolean(lanToggle && lanToggle.checked);
    try {
      var data = await json("/api/sync/settings", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({lanSyncEnabled: desired})
      });
      renderModes(data);
      renderContent(data);
      renderSyncSwitches(data);
      setStatus(state.lanSyncEnabled ? "LAN sync is on." : "LAN sync is off.");
      if (state.lanSyncEnabled) announce();
      else renderDevices([]);
    } catch (error) {
      if (lanToggle) lanToggle.checked = state.lanSyncEnabled;
      setStatus(error.message);
    }
  };

  select.addEventListener("change", function () {
    var mode = modeById(select.value);
    detail.textContent = mode ? modeSummary(mode.id) : "";
  });
  Object.keys(contentIds).forEach(function (key) {
    var node = byId(contentIds[key]);
    if (node && key === "rom") node.addEventListener("change", function () { if (romWarning) romWarning.hidden = !node.checked; });
  });
  byId("syncSave").addEventListener("click", save);
  byId("syncRefreshPeers").addEventListener("click", announce);
  if (lanToggle) lanToggle.addEventListener("change", toggleLanSync);
  load().then(function () { if (state.lanSyncEnabled) announce(); });
})();
