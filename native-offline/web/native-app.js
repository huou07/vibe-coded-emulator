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

    // Phone controller: the platform host (Rust on desktop, Kotlin on Android)
    // owns the session and the input injection; this panel only starts/stops it
    // and reports the truthful state. No token, countdown, or address is shown.
    const controllerCard = document.getElementById("nativeControllerCard");
    const controllerButton = document.getElementById("nativeControllerStart");
    const controllerJoinButton = document.getElementById("nativeControllerJoin");
    const controllerPairCode = document.getElementById("nativeControllerPairCode");
    const controllerCode = document.getElementById("nativeControllerCode");
    const controllerStatus = document.getElementById("nativeControllerStatus");
    const controllerPad = document.getElementById("nativeControllerPad");
    const controllerPadButtons = [...document.querySelectorAll("[data-native-controller-button]")];
    if (controllerCard && controllerButton && window.AN3NativeController) {
      controllerCard.hidden = false;
      let timer = 0;
      let sequence = 0;
      const pressed = new Set();
      let controllerMode = false;
      const setStatus = text => { if (controllerStatus) controllerStatus.textContent = text; };
      const words = status => {
        if (!status.running) return "Off";
        if (status.role === "controller") return status.inputActive ? "Connected to host" : "Connected — waiting for host";
        if (!status.paired) return "Waiting for device";
        return status.inputActive ? "Connected" : "Connected — input unavailable";
      };
      const renderPad = status => {
        const visible = status?.role === "controller" && status.running;
        controllerMode = visible;
        if (controllerPad) controllerPad.hidden = !visible;
        if (!visible) {
          pressed.clear();
          controllerPadButtons.forEach(button => button.dataset.active = "false");
        }
      };
      const sendSnapshot = async () => {
        if (!controllerMode || !window.AN3NativeController?.send) return;
        sequence += 1;
        try {
          await window.AN3NativeController.send({s: sequence, b: [...pressed], a: [0, 0, 0, 0]});
        } catch (error) { setStatus(error?.message || "Direct controller session ended"); }
      };
      const releaseButton = button => {
        const name = button.dataset.nativeControllerButton;
        if (!pressed.delete(name)) return;
        button.dataset.active = "false";
        sendSnapshot();
      };
      controllerPadButtons.forEach(button => {
        button.addEventListener("pointerdown", event => {
          event.preventDefault();
          try { button.setPointerCapture(event.pointerId); } catch (_) {}
          const name = button.dataset.nativeControllerButton;
          if (pressed.has(name)) return;
          pressed.add(name);
          button.dataset.active = "true";
          sendSnapshot();
        });
        button.addEventListener("pointerup", event => { event.preventDefault(); releaseButton(button); });
        button.addEventListener("pointercancel", () => releaseButton(button));
        button.addEventListener("pointerleave", () => releaseButton(button));
      });
      window.addEventListener("blur", () => controllerPadButtons.forEach(releaseButton));
      const refresh = async () => {
        try {
          const status = await window.AN3NativeController.status();
          controllerButton.textContent = status.running ? "Stop" : "Start Hosting";
          if (controllerCode) controllerCode.textContent = status.running && status.code ? status.code : "\u2014";
          renderPad(status);
          setStatus(status.error ? status.error : words(status));
        } catch (error) {
          setStatus("Error");
          if (controllerCode) controllerCode.textContent = "\u2014";
          renderPad(null);
        }
      };
      const poll = () => { clearInterval(timer); timer = setInterval(refresh, 1000); refresh(); };
      controllerButton.addEventListener("click", async () => {
        try {
          const running = (await window.AN3NativeController.status()).running;
          if (running) {
            await window.AN3NativeController.stop();
            clearInterval(timer);
            if (controllerCode) controllerCode.textContent = "\u2014";
            renderPad(null);
            setStatus("Off");
            return;
          }
          const session = await window.AN3NativeController.start();
          if (controllerCode) controllerCode.textContent = session.code || "\u2014";
          renderPad(session);
          setStatus("Waiting for device");
          poll();
        } catch (error) {
          setStatus("Error");
          if (controllerCode) controllerCode.textContent = "\u2014";
          renderPad(null);
        }
      });
      controllerJoinButton?.addEventListener("click", async () => {
        const code = String(controllerPairCode?.value || "").trim();
        if (!/^\d{6}$/.test(code)) {
          setStatus("Enter exactly six decimal digits.");
          controllerPairCode?.focus();
          return;
        }
        if (typeof window.AN3NativeController.join !== "function") {
          setStatus("Direct LAN joining is not available in this build.");
          return;
        }
        try {
          setStatus("Finding host on the local network…");
          const session = await window.AN3NativeController.join(code);
          if (controllerCode) controllerCode.textContent = session.code || "—";
          renderPad(session);
          setStatus("Connected directly to host");
          poll();
        } catch (error) {
          setStatus(error?.message || "Could not join the direct LAN host.");
        }
      });
      refresh();
    }

    show("play");
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once: true});
  else start();
})();
