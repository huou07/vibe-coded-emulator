// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
(function () {
  "use strict";
  var byId = function (id) { return document.getElementById(id); };
  var panel = byId("mpPanel");
  if (!panel) return;

  var post = async function (url, payload) {
    var response = await fetch(url, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    var data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) { var error = new Error(data.error || ("HTTP " + response.status)); error.reason = data.reason; throw error; }
    return data;
  };
  var groupCode = function (code) {
    var text = String(code || "").toUpperCase();
    return text.length === 6 ? text.slice(0, 3) + " " + text.slice(3) : text;
  };
  var signature = function (system, core, hash, device) {
    return {
      system: (system.value || "").trim(),
      core: (core.value || "").trim(),
      romHash: (hash.value || "").trim(),
      deviceId: (device && device.value || "").trim()
    };
  };

  var room = {code: "", token: "", timer: 0};
  var slug = (new URLSearchParams(location.search).get("slug") || (byId("mpSlug") ? byId("mpSlug").value : "") || "").trim();

  var setAvailability = function (available) {
    var panel = byId("mpPanel"); if (panel) panel.hidden = !available;
    var unavailable = byId("mpUnavailable"); if (unavailable) unavailable.hidden = available;
  };

  var gameSelect = byId("mpGameSelect");
  if (gameSelect) gameSelect.addEventListener("change", function () {
    var option = gameSelect.options[gameSelect.selectedIndex];
    if (!option || !option.value) { setAvailability(false); if (byId("mpPanel")) byId("mpPanel").hidden = true; if (byId("mpUnavailable")) byId("mpUnavailable").hidden = true; return; }
    var values = {system: option.getAttribute("data-system") || "", core: option.getAttribute("data-core") || "", hash: option.getAttribute("data-hash") || ""};
    ["mpSystem", "mpJSystem"].forEach(function (id) { if (byId(id)) byId(id).value = values.system; });
    ["mpCore", "mpJCore"].forEach(function (id) { if (byId(id)) byId(id).value = values.core; });
    ["mpHash", "mpJHash"].forEach(function (id) { if (byId(id)) byId(id).value = values.hash; });
    if (byId("mpSystemView")) byId("mpSystemView").textContent = values.system;
    if (byId("mpCoreView")) byId("mpCoreView").textContent = values.core;
    if (byId("mpHashView")) byId("mpHashView").textContent = values.hash.replace(/^sha256:/, "").slice(0, 16);
    if (byId("mpSlug")) byId("mpSlug").value = option.value;
    slug = option.value;
    var lead = byId("mpLead"); if (lead) lead.textContent = option.getAttribute("data-title") || "";
    setAvailability(option.getAttribute("data-available") === "1");
  });

  var hasSignature = function () {
    return Boolean((byId("mpSystem") || {}).value) && Boolean((byId("mpHash") || {}).value);
  };

  var stopWait = function () { if (room.timer) clearInterval(room.timer); room.timer = 0; };
  var waitForPlayer = function () {
    var code = room.code, token = room.token;
    if (!code || !token) return;
    stopWait();
    room.timer = setInterval(async function () {
      try {
        var response = await fetch("/api/multiplayer/room?code=" + encodeURIComponent(code) + "&token=" + encodeURIComponent(token));
        if (!response.ok) { stopWait(); return; }
        var state = await response.json();
        var wait = byId("mpWaitState");
        if (state.state === "full") { if (wait) wait.textContent = "Player joined. Connecting…"; stopWait(); }
      } catch (_) { /* transient */ }
    }, 2000);
  };

  var createButton = byId("mpCreateBtn");
  if (createButton) createButton.addEventListener("click", async function () {
    var out = byId("mpCreateOut");
    if (!hasSignature()) { out.textContent = "Select a game first."; return; }
    out.textContent = "Creating room…";
    try {
      var data = await post("/api/multiplayer/room", signature(byId("mpSystem"), byId("mpCore"), byId("mpHash"), byId("mpHost")));
      room.code = data.code; room.token = data.token;
      byId("mpRoomBox").hidden = false;
      byId("mpRoomCode").textContent = groupCode(data.code);
      var wait = byId("mpWaitState"); if (wait) wait.textContent = "Waiting for player…";
      if (slug) {
        var qr = byId("mpRoomQr");
        if (qr) { qr.src = "/api/multiplayer/qr.svg?slug=" + encodeURIComponent(slug) + "&code=" + encodeURIComponent(data.code); qr.hidden = true; }
        var showQr = byId("mpShowQr"); if (showQr) showQr.hidden = false;
      } else {
        var showQrNode = byId("mpShowQr"); if (showQrNode) showQrNode.hidden = true;
      }
      out.textContent = "";
      waitForPlayer();
    } catch (error) { out.textContent = error.message; }
  });

  if (byId("mpCopyCode")) byId("mpCopyCode").addEventListener("click", async function () {
    try { await navigator.clipboard.writeText(room.code); byId("mpCreateOut").textContent = "Room code copied."; }
    catch (_) { byId("mpCreateOut").textContent = "Copy failed — select the code manually."; }
  });
  if (byId("mpShowQr")) byId("mpShowQr").addEventListener("click", function () {
    var qr = byId("mpRoomQr"); if (qr) qr.hidden = !qr.hidden;
  });
  if (byId("mpCancelRoom")) byId("mpCancelRoom").addEventListener("click", async function () {
    stopWait();
    try { if (room.code && room.token) await post("/api/multiplayer/leave", {code: room.code, token: room.token}); } catch (_) {}
    room.code = ""; room.token = "";
    byId("mpRoomBox").hidden = true;
    byId("mpCreateOut").textContent = "";
  });

  var joinButton = byId("mpJoinBtn");
  if (joinButton) joinButton.addEventListener("click", async function () {
    var out = byId("mpJoinOut");
    if (!(byId("mpCode").value || "").trim()) { out.textContent = "Enter a room code."; return; }
    if (!hasSignature()) { out.textContent = "Select a game first."; return; }
    out.textContent = "Checking game…";
    try {
      var payload = signature(byId("mpJSystem"), byId("mpJCore"), byId("mpJHash"), byId("mpJDevice"));
      payload.code = (byId("mpCode").value || "").trim().toUpperCase();
      var data = await post("/api/multiplayer/join", payload);
      out.textContent = "Compatible. Connecting…";
      byId("mpCode").value = data.code;
    } catch (error) {
      if (error.reason === "incompatible") {
        out.textContent = "Cannot join. Your game file does not match the host. Use the same game version on both devices.";
      } else if (error.reason === "expired") {
        out.textContent = "This room is no longer available.";
      } else if (/room not found/i.test(error.message)) {
        out.textContent = "Room not found. Check the room code.";
      } else {
        out.textContent = error.message;
      }
    }
  });
})();
