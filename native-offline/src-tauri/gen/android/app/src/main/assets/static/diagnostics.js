// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
(function () {
  "use strict";
  var byId = function (id) { return document.getElementById(id); };
  var output = byId("diagOutput");
  if (!output) return;

  var load = async function () {
    try {
      var response = await fetch("/api/diagnostics", {cache: "no-store"});
      var data = await response.json();
      if (!response.ok) throw new Error(data.error || ("HTTP " + response.status));
      output.textContent = JSON.stringify(data, null, 2);
    } catch (error) {
      output.textContent = error.message || String(error);
    }
  };

  byId("diagRefresh").addEventListener("click", load);
  byId("diagCopy").addEventListener("click", async function () {
    try { await navigator.clipboard.writeText(output.textContent); } catch (_) {}
  });
  load();
  setInterval(load, 5000);
})();
