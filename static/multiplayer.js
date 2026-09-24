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

  // A stable per-browser identity. Reconnect and cross-user isolation both
  // depend on this, so it must never be a shared literal.
  var deviceId = (function () {
    try {
      var existing = localStorage.getItem("an3-mp-device");
      if (existing && /^[A-Za-z0-9_-]{8,64}$/.test(existing)) return existing;
      var fresh = "web-" + (globalThis.crypto && crypto.randomUUID
        ? crypto.randomUUID()
        : Date.now().toString(36) + Math.random().toString(36).slice(2));
      localStorage.setItem("an3-mp-device", fresh);
      return fresh;
    } catch (_) { return "web-player"; }
  })();

  var signature = function (system, core, hash) {
    return {
      system: (system.value || "").trim(),
      core: (core.value || "").trim(),
      romHash: (hash.value || "").trim(),
      deviceId: deviceId
    };
  };

  var room = {code: "", token: "", role: "", timer: 0};
  var slug = (new URLSearchParams(location.search).get("slug") || (byId("mpSlug") ? byId("mpSlug").value : "") || "").trim();
  var STORE_KEY = "an3-mp-room";
  var storeRoom = function () {
    try {
      sessionStorage.setItem(STORE_KEY, JSON.stringify({code: room.code, token: room.token, role: room.role, slug: slug}));
    } catch (_) {}
  };
  var readStore = function () {
    try { return JSON.parse(sessionStorage.getItem(STORE_KEY) || "null"); } catch (_) { return null; }
  };
  var clearStore = function () { try { sessionStorage.removeItem(STORE_KEY); } catch (_) {} };

  var setAvailability = function (available) {
    var node = byId("mpPanel"); if (node) node.hidden = !available;
    var unavailable = byId("mpUnavailable"); if (unavailable) unavailable.hidden = available;
  };

  var playHref = function (code) {
    return (slug ? "/play/" + encodeURIComponent(slug) : "/games") + "?room=" + encodeURIComponent(code);
  };
  var showPlayLink = function (code, text) {
    var link = byId("mpRoomLink");
    if (!link) return;
    link.href = playHref(code);
    link.textContent = text || (slug ? "Open the game to play together" : "Open your game and enter this code");
    link.hidden = false;
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

  var showRoomBox = function (data) {
    room.code = data.code; room.token = data.token; room.role = data.role || "host";
    if (byId("mpRoomBox")) byId("mpRoomBox").hidden = false;
    if (byId("mpRoomCode")) byId("mpRoomCode").textContent = groupCode(data.code);
    if (byId("mpWaitState")) byId("mpWaitState").textContent = "Waiting for player…";
    var link = byId("mpRoomLink"); if (link) link.hidden = true;
    if (slug) {
      var qr = byId("mpRoomQr");
      if (qr) { qr.src = "/api/multiplayer/qr.svg?slug=" + encodeURIComponent(slug) + "&code=" + encodeURIComponent(data.code); qr.hidden = true; }
      if (byId("mpShowQr")) byId("mpShowQr").hidden = false;
    } else if (byId("mpShowQr")) {
      byId("mpShowQr").hidden = true;
    }
    storeRoom();
  };

  var waitForPlayer = function () {
    var code = room.code, token = room.token;
    if (!code || !token) return;
    stopWait();
    room.timer = setInterval(async function () {
      try {
        var response = await fetch("/api/multiplayer/room?code=" + encodeURIComponent(code) + "&token=" + encodeURIComponent(token));
        if (!response.ok) {
          // The room expired or the host closed it: stop polling and reset.
          stopWait(); clearStore();
          var wait = byId("mpWaitState"); if (wait) wait.textContent = "This room is no longer available.";
          return;
        }
        var state = await response.json();
        if (state.state === "full") {
          stopWait();
          var wait = byId("mpWaitState"); if (wait) wait.textContent = "Player joined. Open the game to start.";
          showPlayLink(code);
        }
      } catch (_) { /* transient */ }
    }, 2000);
  };

  var leaveRoom = function (keepalive) {
    stopWait();
    var code = room.code, token = room.token;
    room.code = ""; room.token = ""; room.role = "";
    clearStore();
    if (!code || !token) return Promise.resolve();
    try {
      return fetch("/api/multiplayer/leave", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({code: code, token: token}),
        keepalive: !!keepalive
      }).then(function () {}, function () {});
    } catch (_) { return Promise.resolve(); }
  };

  var resumeRoom = async function () {
    var saved = readStore();
    if (!saved || !saved.code || !saved.token) return;
    try {
      var data = await post("/api/multiplayer/reconnect", {code: saved.code, token: saved.token});
      if (saved.slug) slug = saved.slug;
      showRoomBox(data);
      if (data.role === "host") {
        waitForPlayer();
      } else {
        if (byId("mpWaitState")) byId("mpWaitState").textContent = "Reconnected. Open the game to play.";
        if (byId("mpJoinOut")) byId("mpJoinOut").textContent = "Reconnected to the room.";
        showPlayLink(data.code);
      }
    } catch (_) {
      clearStore();
    }
  };

  var createButton = byId("mpCreateBtn");
  if (createButton) createButton.addEventListener("click", async function () {
    var out = byId("mpCreateOut");
    if (!hasSignature()) { out.textContent = "Select a game first."; return; }
    out.textContent = "Creating room…";
    try {
      var data = await post("/api/multiplayer/room", signature(byId("mpSystem"), byId("mpCore"), byId("mpHash")));
      showRoomBox(data);
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
    await leaveRoom(false);
    if (byId("mpRoomBox")) byId("mpRoomBox").hidden = true;
    if (byId("mpCreateOut")) byId("mpCreateOut").textContent = "";
  });

  var joinButton = byId("mpJoinBtn");
  if (joinButton) joinButton.addEventListener("click", async function () {
    var out = byId("mpJoinOut");
    if (!(byId("mpCode").value || "").trim()) { out.textContent = "Enter a room code."; return; }
    if (!hasSignature()) { out.textContent = "Select a game first."; return; }
    out.textContent = "Checking game…";
    try {
      var payload = signature(byId("mpJSystem"), byId("mpJCore"), byId("mpJHash"));
      payload.code = (byId("mpCode").value || "").trim().toUpperCase();
      var data = await post("/api/multiplayer/join", payload);
      showRoomBox(data);
      if (byId("mpWaitState")) byId("mpWaitState").textContent = "Connected. Open the game to play.";
      out.textContent = "Compatible. Connecting…";
      showPlayLink(data.code);
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

  // Unloading for real closes the room; a back/forward-cache restore resumes it.
  addEventListener("pagehide", function (event) { if (!event.persisted) leaveRoom(true); });
  addEventListener("pageshow", function (event) { if (event.persisted) resumeRoom(); });
  resumeRoom();
})();
