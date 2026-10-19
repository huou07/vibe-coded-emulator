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
    const sessionControls = window.AN3NativeSessionControls;
    const sessionCard = document.getElementById("nativeSessionCard");
    const sessionHeading = document.getElementById("nativeSessionHeading");
    const sessionStatus = document.getElementById("nativeSessionStatus");
    const sessionPause = document.querySelector('[data-native-control="pause"]');
    const sessionLayoutWrap = document.getElementById("nativeSessionLayoutWrap");
    const sessionLayout = document.getElementById("nativeSessionLayout");
    const sessionSlot = document.getElementById("nativeSessionSaveSlot");
    const sessionAutoSave = document.getElementById("nativeSessionAutoSave");
    const sessionVolume = document.getElementById("nativeSessionVolume");
    const sessionMute = document.getElementById("nativeSessionMute");

    let sessionPaused = false;
    let sessionCommandQueue = Promise.resolve();
    let sessionVolumeTimer = 0;
    const heldButtons = new Set();

    const setSessionStatus = value => {
      if (sessionStatus) sessionStatus.textContent = String(value || "");
    };

    const sendSessionControl = (action, value) => {
      if (!sessionControls) return Promise.reject(new Error("Shared session controls are unavailable."));
      const request = sessionCommandQueue.then(() => sessionControls.control(action, value));
      sessionCommandQueue = request.catch(() => {});
      return request;
    };

    const runSessionControl = async (action, value, button = null) => {
      if (button) button.disabled = true;
      try {
        const message = await sendSessionControl(action, value);
        if (message && action !== "button") setSessionStatus(message);
        return message;
      } catch (error) {
        setSessionStatus(error?.message || String(error));
        return null;
      } finally {
        if (button) button.disabled = false;
      }
    };

    const releaseButtons = () => {
      for (const id of [...heldButtons]) setButton(id, false);
    };

    const setButton = (id, pressed) => {
      if (!sessionControls || !sessionCard || sessionCard.hidden) return;
      if (pressed) {
        if (heldButtons.has(id)) return;
        heldButtons.add(id);
      } else {
        if (!heldButtons.has(id)) return;
        heldButtons.delete(id);
      }
      document.querySelector(`[data-native-button="${id}"]`)?.setAttribute("aria-pressed", String(pressed));
      runSessionControl("button", `${id}:${pressed ? 1 : 0}`);
    };

    const showSession = detail => {
      if (!sessionCard || !sessionControls) return;
      const system = String(detail?.system || "").toLowerCase();
      const game = [...(grid?.querySelectorAll(".offline-game-card") || [])]
        .find(card => card.dataset.romId === String(detail?.romId || ""));
      const gameTitle = game?.querySelector("h4")?.textContent?.trim();
      const systemName = {gba: "Game Boy Advance", nds: "Nintendo DS", "3ds": "Nintendo 3DS"}[system] || "Native game";
      if (sessionHeading) sessionHeading.textContent = gameTitle || systemName;
      if (sessionLayoutWrap) sessionLayoutWrap.hidden = system !== "nds" && system !== "3ds";
      sessionPaused = false;
      if (sessionPause) {
        sessionPause.textContent = "Pause";
        sessionPause.setAttribute("aria-pressed", "false");
      }
      for (const speed of document.querySelectorAll("[data-native-speed]")) {
        speed.classList.toggle("selected", speed.dataset.nativeSpeed === "1");
        speed.setAttribute("aria-pressed", speed.dataset.nativeSpeed === "1" ? "true" : "false");
      }
      sessionCard.hidden = false;
      setSessionStatus(detail?.result?.detail || "Game window opened. Controls are available here.");
      show("play");
    };

    const hideSession = (message, release = true) => {
      if (release) releaseButtons();
      else heldButtons.clear();
      if (sessionCard) sessionCard.hidden = true;
      setSessionStatus(message || "");
    };

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

    if (sessionControls && sessionCard) {
      window.addEventListener("an3-native-session-started", event => showSession(event.detail));
      document.querySelectorAll("[data-native-control]").forEach(button => {
        button.addEventListener("click", async () => {
          const action = button.dataset.nativeControl;
          if (action === "pause") {
            const nextPaused = !sessionPaused;
            const result = await runSessionControl("pause", String(nextPaused), button);
            if (result) {
              sessionPaused = nextPaused;
              button.textContent = sessionPaused ? "Resume" : "Pause";
              button.setAttribute("aria-pressed", String(sessionPaused));
            }
            return;
          }
          runSessionControl(action, "", button);
        });
      });
      document.querySelectorAll("[data-native-speed]").forEach(button => {
        button.addEventListener("click", async () => {
          const result = await runSessionControl("speed", button.dataset.nativeSpeed, button);
          if (!result) return;
          document.querySelectorAll("[data-native-speed]").forEach(item => {
            const selected = item === button;
            item.classList.toggle("selected", selected);
            item.setAttribute("aria-pressed", String(selected));
          });
        });
      });
      document.querySelectorAll("[data-native-save]").forEach(button => {
        button.addEventListener("click", () => runSessionControl(button.dataset.nativeSave, sessionSlot?.value || "1", button));
      });
      sessionAutoSave?.addEventListener("change", () => runSessionControl("auto-save", sessionAutoSave.value));
      sessionLayout?.addEventListener("change", () => runSessionControl("layout", sessionLayout.value));
      sessionVolume?.addEventListener("input", () => {
        window.clearTimeout(sessionVolumeTimer);
        sessionVolumeTimer = window.setTimeout(() => runSessionControl("volume", sessionVolume.value), 70);
      });
      sessionVolume?.addEventListener("change", () => {
        window.clearTimeout(sessionVolumeTimer);
        runSessionControl("volume", sessionVolume.value);
      });
      sessionMute?.addEventListener("change", () => runSessionControl("mute", String(sessionMute.checked)));

      document.querySelectorAll("[data-native-button]").forEach(button => {
        const id = Number(button.dataset.nativeButton);
        const press = event => {
          if (event?.type === "pointerdown" && (!event.isPrimary || event.button !== 0)) return;
          if (event) event.preventDefault();
          try { button.setPointerCapture?.(event.pointerId); } catch (_) {}
          setButton(id, true);
        };
        const release = event => {
          if (event) event.preventDefault();
          setButton(id, false);
        };
        button.addEventListener("pointerdown", press);
        button.addEventListener("pointerup", release);
        button.addEventListener("pointercancel", release);
        button.addEventListener("lostpointercapture", release);
        button.addEventListener("keydown", event => {
          if ((event.key === "Enter" || event.key === " ") && !event.repeat) press(event);
        });
        button.addEventListener("keyup", event => {
          if (event.key === "Enter" || event.key === " ") release(event);
        });
        button.addEventListener("click", event => event.preventDefault());
      });

      document.getElementById("nativeSessionReturn")?.addEventListener("click", async event => {
        const button = event.currentTarget;
        button.disabled = true;
        setSessionStatus("Returning to Library…");
        releaseButtons();
        try {
          await sessionControls.stop();
          hideSession("Game stopped.", false);
          show("library");
        } catch (error) {
          setSessionStatus(error?.message || String(error));
        } finally {
          button.disabled = false;
        }
      });

      window.addEventListener("blur", releaseButtons);
      document.addEventListener("visibilitychange", () => {
        if (document.hidden) releaseButtons();
      });
      window.addEventListener("beforeunload", releaseButtons);
      window.setInterval(async () => {
        if (sessionCard.hidden) return;
        try {
          const runtimeState = await sessionControls.status();
          if (!runtimeState?.active) {
            hideSession("Game session ended.", false);
            if (current === "play") show("library");
          }
        } catch (_) {}
      }, 1500);
    }

    show("play");
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once: true});
  else start();
})();
