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
  var transferButton = byId("syncTransfer");
  var contentIds = {save: "syncContentSave", state: "syncContentState", library: "syncContentLibrary", rom: "syncContentRom"};
  var state = {mode: "off", content: {}, modes: [], contentOptions: [], peers: [], conflicts: [], lanSyncEnabled: true};

  var setStatus = function (text) { statusNode.textContent = text; };
  // Only an explicit development adapter may speak to the legacy web server.
  // Installed clients get their transport from the native LAN peer layer.
  var devJson = async function (url, options) {
    var adapter = globalThis.AN3SyncDevAdapter;
    if (!adapter || typeof adapter.json !== "function") throw new Error("Direct LAN sync is available in the installed AN3 app.");
    return adapter.json(url, options);
  };
  var directTransport = function () { return globalThis.AN3LanPeerTransport || null; };
  var json = async function (url, options) {
    return devJson(url, options);
  };

  var fallbackDeviceId = (function () {
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
  var deviceId = globalThis.AN3SyncTransfer?.deviceId?.() || fallbackDeviceId;

  var modeById = function (id) {
    for (var index = 0; index < state.modes.length; index += 1) if (state.modes[index].id === id) return state.modes[index];
    return null;
  };
  var modeSummary = function (mode) {
    if (mode === "auto") return "Automatic sync is unavailable outside the installed app.";
    if (mode === "lan") return "Transfers go directly between nearby installed AN3 apps.";
    if (mode === "drive") return "Cloud sync is not part of LAN features.";
    return "Sync is off. Nothing is transferred.";
  };

  var renderModes = function (data) {
    state.mode = data.mode || "off";
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
      : "Google Drive sync unavailable in this build.";
    updateTransferButton();
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
    updateTransferButton();
  };

  var updateTransferButton = function () {
    if (transferButton) transferButton.disabled = state.mode === "off" || state.mode === "drive" || !state.content.state || !globalThis.AN3SyncTransfer || !directTransport();
  };

  var renderDevices = function (peers) {
    state.peers = peers || [];
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

  var drawConflicts = function () {
    if (!conflictBox) return;
    conflictBox.innerHTML = "";
    if (!state.conflicts.length) { conflictBox.hidden = true; return; }
    var title = document.createElement("h3");
    title.textContent = "Save Conflict";
    conflictBox.appendChild(title);
    state.conflicts.forEach(function (conflict) {
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
          button.disabled = true;
          try {
            await globalThis.AN3SyncTransfer.resolveConflict({
              conflict: conflict,
              deviceId: deviceId,
              resolution: choice[0],
            });
            setStatus("Conflict resolved.");
            state.conflicts = state.conflicts.filter(function (item) { return item !== conflict; });
            drawConflicts();
          } catch (error) { setStatus(error.message); }
          finally { button.disabled = false; }
        });
        actions.appendChild(button);
      });
      card.appendChild(actions);
      conflictBox.appendChild(card);
    });
    conflictBox.hidden = false;
  };
  var renderConflicts = function (transfers, context) {
    var localByKey = context && context.local ? new Map(context.local.map(function (item) { return [item.key, item]; })) : new Map();
    var remoteByKey = context && context.remote ? new Map(context.remote.map(function (item) { return [item.key, item]; })) : new Map();
    state.conflicts = (transfers || []).filter(function (transfer) { return transfer.direction === "conflict"; }).map(function (transfer) {
      return {
        key: transfer.key,
        kind: transfer.kind || "state",
        copyKey: transfer.copyKey || transfer.key + ".conflict",
        local: localByKey.get(transfer.key) || null,
        remote: remoteByKey.get(transfer.key) || null,
        reason: transfer.reason || "both-changed",
      };
    });
    drawConflicts();
  };

  var syncSaveStates = async function () {
    if (!globalThis.AN3SyncTransfer) throw new Error("LAN save-state transfer is unavailable.");
    if (state.mode === "off") throw new Error("Turn on LAN or Automatic sync first.");
    if (!state.content.state) throw new Error("Enable Save states before syncing.");
    var result = await globalThis.AN3SyncTransfer.syncState({
      deviceId: deviceId,
      mode: state.mode,
      transport: directTransport(),
      sameLan: true,
    });
    renderConflicts((result.plan || {}).transfers, result);
    setStatus("Sent " + result.counts.uploaded + ", received " + result.counts.downloaded + "." + (result.counts.conflicts ? " " + result.counts.conflicts + " conflict(s) need a choice." : ""));
    return result;
  };
  window.AN3Sync = {
    renderPlan: function (plan) { if (plan && plan.transfers) renderConflicts(plan.transfers); },
    syncSaveStates: syncSaveStates,
  };

  var load = async function () {
    try {
      if (globalThis.AN3SyncDevAdapter) {
        var data = await json("/api/sync/settings");
        renderModes(data);
        renderContent(data);
        renderSyncSwitches(data);
        setStatus("");
      } else {
        var available = Boolean(directTransport());
        renderModes({
          mode: available ? "lan" : "off",
          modes: [
            {id: "off", label: "Off", available: true},
            {id: "lan", label: "Direct LAN", available: available},
          ],
          content: {save: true, state: true, library: false, rom: false},
          driveConfigured: false,
        });
        renderSyncSwitches({lanSyncEnabled: true});
        setStatus(directTransport() ? "Direct LAN peer ready." : "Install the AN3 app to use direct LAN sync.");
      }
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
      if (globalThis.AN3SyncDevAdapter) {
        var data = await json("/api/sync/settings", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({mode: select.value, content: collectContent()})
        });
        renderModes(data);
        renderContent(data);
      } else {
        state.mode = select.value;
        state.content = collectContent();
        try { localStorage.setItem("an3-direct-sync-settings-v1", JSON.stringify({mode: state.mode, content: state.content})); } catch (_) {}
        updateTransferButton();
      }
      setStatus("Saved.");
    } catch (error) { setStatus(error.message); }
  };

  var announce = async function () {
    if (!state.lanSyncEnabled) { renderDevices([]); return; }
    try {
      if (directTransport()?.discover) {
        renderDevices(await directTransport().discover());
        setStatus("");
      } else if (globalThis.AN3SyncDevAdapter) {
        var data = await json("/api/sync/lan/announce", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({deviceId: deviceId, name: "Vibe Coded Emulator", port: 0})
        });
        renderDevices(data.peers || []);
        setStatus("");
      } else {
        renderDevices([]);
        setStatus("Direct LAN discovery is available in the installed AN3 app.");
      }
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
  transferButton?.addEventListener("click", function () {
    transferButton.disabled = true;
    setStatus("Syncing save-state bytes…");
    syncSaveStates().catch(function (error) { setStatus(error.message || String(error)); }).finally(updateTransferButton);
  });
  load().then(function () { if (state.lanSyncEnabled) announce(); });
})();
