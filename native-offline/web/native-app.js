// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Compact offline-first app shell around the existing local-ROM library.
// It only switches sections, filters rendered cards and forwards the obvious
// "Open ROM" action to the import controls that static/offline.js already
// owns. It never touches the player rendering pipeline.
(() => {
  const SECTION_TITLES = {play: "Play", library: "Library", settings: "Settings", help: "Help", about: "About"};

  const start = () => {
    const app = document.getElementById("nativeApp");
    // When a ROM launch query is present, offline.js replaces the body with the
    // player, so there is no shell to wire.
    if (!app) return;

    const panels = [...document.querySelectorAll("[data-panel]")];
    const navButtons = [...document.querySelectorAll("[data-nav]")];
    const title = document.querySelector("[data-section-title]");
    const back = document.querySelector(".native-back");
    const searchWrap = document.getElementById("nativeSearchWrap");
    const search = document.getElementById("nativeSearch");
    const grid = document.getElementById("offlineGameGrid");

    let current = "play";

    const filter = () => {
      if (!search || !grid) return;
      const query = search.value.trim().toLowerCase();
      for (const card of grid.querySelectorAll(".offline-game-card")) {
        const label = card.querySelector("h4")?.textContent?.toLowerCase() || "";
        card.hidden = Boolean(query) && !label.includes(query);
      }
    };

    const show = name => {
      if (!SECTION_TITLES[name]) return;
      current = name;
      for (const panel of panels) panel.hidden = panel.dataset.panel !== name;
      for (const button of navButtons) button.classList.toggle("active", button.dataset.nav === name);
      if (title) title.textContent = SECTION_TITLES[name];
      if (back) back.hidden = name === "play";
      if (searchWrap) searchWrap.hidden = name !== "library";
      document.body.dataset.section = name;
      if (name === "library") {
        filter();
        search?.focus({preventScroll: true});
      }
    };

    const openRom = () => {
      show("library");
      const details = document.getElementById("nativeAddRom");
      if (details) details.open = true;
      const picker = document.getElementById("offlineNativePicker");
      const file = document.getElementById("offlineFile");
      if (picker && !picker.hidden) picker.click();
      else file?.click();
    };

    for (const button of navButtons) {
      button.addEventListener("click", () => show(button.dataset.nav));
    }
    for (const button of document.querySelectorAll("[data-open-rom]")) {
      button.addEventListener("click", openRom);
    }
    search?.addEventListener("input", filter);
    // offline.js renders the library asynchronously and on every import/remove.
    if (grid) new MutationObserver(filter).observe(grid, {childList: true, subtree: true});

    // Preserve the platform-specific staging label used during Android QA.
    const envLabel = document.getElementById("nativeEnvLabel");
    if (envLabel && /Android/i.test(navigator.userAgent)) envLabel.textContent = "Android";

    show("play");
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once: true});
  else start();
})();
