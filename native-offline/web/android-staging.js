// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Explicit browser compatibility additions; these are not native libretro states.
// Automatic recovery lives in its own database and never consumes slot 1–10.
(() => {
  if (!/Android/i.test(navigator.userAgent)) return;
  addEventListener("DOMContentLoaded", () => {
    const label = document.getElementById("nativeEnvLabel");
    if (label) label.textContent = "Android staging";
    // Use the installed host's declaration, also consumed by offline.js.
    // A second hardcoded list can disable a supported core after cards render.
    const declared = window.AN3NativeIntegratedSystems;
    const supported = new Set(Array.isArray(declared) ? declared : []);
    const coreLabel = document.querySelector("#offlineCoreState")?.previousElementSibling;
    if (coreLabel) coreLabel.textContent = supported.size
      ? `${[...supported].map(system => system.toUpperCase()).join(" / ")} · Native libretro`
      : "Native cores unavailable";
    for (const option of document.querySelectorAll("#offlineSystem option")) {
      if (!supported.has(option.value)) { option.disabled = true; option.textContent += " · Not verified in this APK"; }
    }
    const library = document.getElementById("offlineGameGrid");
    if (library) {
      // Never block a system this APK actually ships a native core for. An
      // existing card stays playable even when its record only carries the
      // legacy `nativePath`/`nativeUrl` (offline.js recovers the ROM id from
      // it). Only a system with no bundled core is disabled.
      const markUnsupported = () => {
        for (const card of library.querySelectorAll(".offline-game-card")) {
          if (supported.has(card.dataset.system)) continue;
          const play = card.querySelector(".primary");
          if (play && !play.disabled) {
            play.disabled = true;
            play.textContent = "Native core unavailable";
          }
        }
      };
      new MutationObserver(markUnsupported).observe(library, {childList:true,subtree:true});
      markUnsupported();
    }
    // Compatibility state helpers run only when this mode was explicitly requested.
    if (new URLSearchParams(location.search).get("mode") !== "browser-compatibility") return;
    const shell = document.querySelector("[data-player]");
    const panel = document.getElementById("slotPanel");
    if (!shell || !panel) return;
    window.__AN3StateExportResult = message => {
      const notice = document.getElementById("playerNotice");
      if (notice) notice.textContent = message;
    };
    document.getElementById("saveState")?.addEventListener("click", async event => {
      event.stopImmediatePropagation();
      try {
        const bytes = window.EJS_emulator?.gameManager?.getState();
        if (!bytes?.byteLength || bytes.byteLength > 64 * 1024 * 1024) throw new Error("State unavailable or too large");
        const dataUrl = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.onerror = reject;
          reader.readAsDataURL(new Blob([bytes]));
        });
        if (!window.AN3AndroidNative?.exportState) throw new Error("Android export unavailable");
        window.AN3AndroidNative.exportState(dataUrl.split(",", 2)[1]);
      } catch (_) { window.__AN3StateExportResult("State export unavailable"); }
    }, true);
    const {slug} = JSON.parse(shell.dataset.player);
    const preference = `an3-android-autosave:${slug}`;
    let enabled = false, busy = false;
    try { enabled = localStorage.getItem(preference) === "1"; } catch (_) {}
    const row = document.createElement("div");
    row.className = "save-slot";
    row.innerHTML = '<strong>Auto Save</strong><small role="status"></small><label><input type="checkbox"> Auto Save (60s)</label><button type="button">Load Auto Save</button>';
    panel.append(row);
    const toggle = row.querySelector("input"), status = row.querySelector("small"), load = row.querySelector("button");
    toggle.checked = enabled;
    const open = () => new Promise((resolve, reject) => {
      const request = indexedDB.open("an3-android-autosave", 1);
      request.onupgradeneeded = () => request.result.createObjectStore("states", {keyPath:"id"});
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    const access = async (mode, value) => {
      const db = await open();
      try { return await new Promise((resolve, reject) => {
        const tx = db.transaction("states", mode), store = tx.objectStore("states");
        const request = mode === "readonly" ? store.get(slug) : store.put(value);
        tx.oncomplete = () => resolve(request.result);
        tx.onerror = tx.onabort = () => reject(tx.error || new Error("Auto Save failed"));
      }); } finally { db.close(); }
    };
    const refresh = async () => {
      const saved = await access("readonly");
      load.disabled = !saved;
      status.textContent = saved ? new Date(saved.updatedAt).toLocaleString() : "No Auto Save";
    };
    const save = async () => {
      if (!enabled || busy) return;
      const manager = window.EJS_emulator?.gameManager;
      if (!manager) return;
      busy = true;
      try {
        const state = manager.getState();
        if (!state?.byteLength) return;
        await access("readwrite", {id:slug,state:new Blob([state]),updatedAt:Date.now()});
        await refresh();
      } catch (_) { status.textContent = "Auto Save failed; previous save retained"; }
      finally { busy = false; }
    };
    toggle.addEventListener("change", () => {
      enabled = toggle.checked;
      try { localStorage.setItem(preference, enabled ? "1" : "0"); }
      catch (_) { status.textContent = "Auto Save preference could not be stored"; }
      if (enabled) save();
    });
    load.addEventListener("click", async () => {
      try {
        const saved = await access("readonly"), manager = window.EJS_emulator?.gameManager;
        if (!saved || !manager) throw new Error("not ready");
        manager.loadState(new Uint8Array(await saved.state.arrayBuffer()));
        status.textContent = "Auto Save loaded";
      } catch (_) { status.textContent = "Auto Save could not be loaded"; }
    });
    const timer = setInterval(save, 60000);
    document.addEventListener("visibilitychange", () => { if (document.hidden) save(); });
    addEventListener("pagehide", () => clearInterval(timer), {once:true});
    refresh().catch(() => { status.textContent = "Auto Save storage unavailable"; });
  });
})();
