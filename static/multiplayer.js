// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
(function () {
  "use strict";
  var byId = function (id) { return document.getElementById(id); };

  var post = async function (url, payload) {
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

  var signature = function (system, core, hash) {
    return {
      system: (system.value || "").trim(),
      core: (core.value || "").trim(),
      romHash: (hash.value || "").trim()
    };
  };

  var createButton = byId("mpCreateBtn");
  if (createButton) {
    createButton.addEventListener("click", async function () {
      var out = byId("mpCreateOut");
      out.textContent = "…";
      try {
        var data = await post("/api/multiplayer/room", Object.assign(
          signature(byId("mpSystem"), byId("mpCore"), byId("mpHash")),
          {deviceId: (byId("mpHost").value || "").trim()}
        ));
        var minutes = Math.round(data.expiresInSeconds / 60);
        out.textContent = "Invite code: " + data.code + " · relay " + data.relay + " · expires in " + minutes + " min";
        byId("mpCode").value = data.code;
      } catch (error) {
        out.textContent = error.message;
      }
    });
  }

  var joinButton = byId("mpJoinBtn");
  if (joinButton) {
    joinButton.addEventListener("click", async function () {
      var out = byId("mpJoinOut");
      out.textContent = "…";
      try {
        var data = await post("/api/multiplayer/join", Object.assign(
          signature(byId("mpJSystem"), byId("mpJCore"), byId("mpJHash")),
          {code: (byId("mpCode").value || "").trim(), deviceId: (byId("mpJDevice").value || "").trim()}
        ));
        out.textContent = "Joined room " + data.code + " · relay " + data.relay;
      } catch (error) {
        out.textContent = error.message;
      }
    });
  }
})();
