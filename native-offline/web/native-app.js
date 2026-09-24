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
    // Settings tabs: Emulator / Sync / Phone Controller. Only the panes are
    // switched; every card keeps its own IDs and behaviour so the sync and bug
    // report wiring is unaffected. A phone-controller session that is already
    // running may draw the user to its tab without changing the section.
    const settingsTabs = [...document.querySelectorAll("[data-settings-tab]")];
    const settingsPanes = [...document.querySelectorAll("[data-settings-pane]")];
    const showSettingsTab = name => {
      if (!settingsTabs.some(tab => tab.dataset.settingsTab === name)) return;
      for (const tab of settingsTabs) {
        const active = tab.dataset.settingsTab === name;
        tab.classList.toggle("active", active);
        tab.setAttribute("aria-selected", String(active));
      }
      for (const pane of settingsPanes) pane.hidden = pane.dataset.settingsPane !== name;
      // A body-level marker for the active tab. Deliberately NOT data-settings-tab,
      // which would add a fourth match to the [data-settings-tab] tab selector.
      document.body.dataset.settingsActive = name;
    };
    for (const tab of settingsTabs) {
      tab.addEventListener("click", () => showSettingsTab(tab.dataset.settingsTab));
    }
    window.AN3ShowSettingsTab = showSettingsTab;
    showSettingsTab("emulator");
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
    const controllerPadHead = document.getElementById("nativeControllerPadHead");
    const controllerLayout = document.getElementById("nativeControllerLayout");
    const controllerMovement = document.getElementById("nativeControllerMovement");
    const controllerPadState = document.getElementById("nativeControllerPadState");
    const controllerDisconnect = document.getElementById("nativeControllerDisconnect");
    const controllerTouchscreen = document.getElementById("nativeControllerTouchscreen");
    const controllerCircular = document.getElementById("nativeControllerCircular");
    const controllerSaveSlot = document.getElementById("nativeControllerSaveSlot");
    const controllerDpad = controllerPad ? controllerPad.querySelector(".ctrl-dpad") : null;
    const controllerPadButtons = [...document.querySelectorAll("[data-native-controller-button]")];
    const controllerSticks = [...document.querySelectorAll("[data-native-controller-stick]")];
    const controllerUtilities = [...document.querySelectorAll("[data-native-controller-util]")];
    if (controllerCard && controllerButton && window.AN3NativeController) {
      controllerCard.hidden = false;
      // The pad reuses the web Phone Controller structure and the shared
      // canonical input action model, so the packaged app and the web pad
      // cannot drift. Only the transport differs (direct LAN frames here).
      const inputActions = window.AN3InputActions || null;
      let timer = 0;
      let sequence = 0;
      let utilitySequence = 0;
      let utilitySessionId = "";
      const newUtilitySession = () => {
        try { if (window.crypto && typeof window.crypto.randomUUID === "function") return `native-${window.crypto.randomUUID()}`; } catch (_) {}
        return `native-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
      };
      const resetUtilitySession = () => { utilitySequence = 0; utilitySessionId = newUtilitySession(); };
      resetUtilitySession();
      let controllerMode = false;
      let system = "auto";
      let manualLayout = false;
      let movement = "dpad";
      let circularRegion = null;
      const pressed = new Set();
      const axes = {lx: 0, ly: 0, rx: 0, ry: 0};
      const touch = {active: false, x: 0, y: 0};
      try {
        const storedMovement = localStorage.getItem("an3-controller-movement");
        if (storedMovement) movement = storedMovement;
      } catch (_) {}
      if (controllerMovement) controllerMovement.value = movement;
      const setStatus = text => { if (controllerStatus) controllerStatus.textContent = text; };
      const setPadState = text => { if (controllerPadState) controllerPadState.textContent = text; };
      const words = status => {
        if (!status.running) return "Off";
        if (status.state === "connecting") return "Connecting directly to host…";
        if (status.state === "error") return status.error || "Connection failed";
        if (status.role === "controller") return status.inputActive ? "Connected to host" : "Connected — waiting for host";        if (!status.paired) return "Waiting for device";
        return status.inputActive ? "Connected" : "Connected — input unavailable";
      };
      const layoutFor = value => {
        if (value !== "auto") return value;
        if (system === "nds" || system === "3ds" || system === "switch") return system;
        if (system === "gba" || system === "gbc") return "gba";
        return "custom";
      };
      const applyLayout = () => {
        const layout = layoutFor(manualLayout && controllerLayout ? controllerLayout.value : "auto");
        if (controllerPad) controllerPad.dataset.layout = layout;
        if (controllerTouchscreen) controllerTouchscreen.hidden = !(layout === "nds" || layout === "3ds" || layout === "custom");
        if (controllerLayout && !manualLayout) controllerLayout.value = layoutFor("auto");
      };
      const releaseCircular = () => {
        let changed = false;
        ["up", "down", "left", "right"].forEach(dir => { if (pressed.delete(dir)) changed = true; });
        circularRegion = null;
        if (controllerCircular) controllerCircular.removeAttribute("data-active");
        if (changed) sendSnapshot();
      };
      const applyMovement = () => {
        if (controllerMovement) movement = controllerMovement.value;
        if (controllerDpad) controllerDpad.hidden = movement !== "dpad";
        if (controllerCircular) controllerCircular.hidden = movement !== "circular";
        if (movement !== "circular") releaseCircular();
      };
      const sendState = payload => {
        if (!controllerMode || !window.AN3NativeController?.send) return;
        sequence += 1;
        const frame = Object.assign({s: sequence, b: [...pressed], a: [axes.lx, axes.ly, axes.rx, axes.ry]}, payload || {});
        if (touch.active) frame.t = [touch.x, touch.y];
        Promise.resolve(window.AN3NativeController.send(frame)).catch(error => {
          setStatus(error?.message || "Direct controller session ended");
        });
      };
      const sendSnapshot = () => sendState();
      const sendUtility = action => {
        if (!controllerMode || !action) return;
        utilitySequence += 1;
        const command = {action, sequence: utilitySequence, command_id: `${utilitySessionId}-${utilitySequence}`};
        const slot = Number(controllerSaveSlot?.value);
        if ((action === "QUICK_SAVE" || action === "QUICK_LOAD") && Number.isInteger(slot) && slot >= 1 && slot <= 10) command.slot = slot;
        sendState({u: [command]});
      };
      const releaseAll = () => {
        pressed.clear();
        axes.lx = 0; axes.ly = 0; axes.rx = 0; axes.ry = 0;
        touch.active = false; touch.x = 0; touch.y = 0;
        circularRegion = null;
        if (controllerCircular) controllerCircular.removeAttribute("data-active");
        controllerSticks.forEach(stick => {
          stick.classList.remove("active");
          stick.style.setProperty("--sx", "0px");
          stick.style.setProperty("--sy", "0px");
        });
        sendSnapshot();
      };
      const renderPad = status => {
        const visible = status?.role === "controller" && status.running;
        const entering = visible && !controllerMode;
        const leaving = !visible && controllerMode;
        controllerMode = visible;
        if (controllerPad) controllerPad.hidden = !visible;
        if (controllerPadHead) controllerPadHead.hidden = !visible;
        if (status && status.system) system = status.system;
        if (visible) {
          applyLayout();
          applyMovement();
          setPadState(words(status));
        } else {
          releaseAll();
          controllerPadButtons.forEach(button => button.dataset.active = "false");
        }
        // Controller Mode: a phone-controller pad that is the active surface
        // asks the host to present in landscape. Best-effort and presentation
        // only; a missing bridge or a desktop host is a no-op.
        if (entering) {
          try { window.AN3NativeController?.enterControllerMode?.(); } catch (_) {}
        } else if (leaving) {
          try { window.AN3NativeController?.exitControllerMode?.(); } catch (_) {}
        }
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
        button.addEventListener("contextmenu", event => event.preventDefault());
      });
      controllerSticks.forEach(stick => {
        const side = stick.dataset.nativeControllerStick;
        let pointerId = null;
        const update = event => {
          const rect = stick.getBoundingClientRect();
          const radius = Math.max(1, Math.min(rect.width, rect.height) / 2);
          let dx = event.clientX - (rect.left + rect.width / 2);
          let dy = event.clientY - (rect.top + rect.height / 2);
          const distance = Math.hypot(dx, dy);
          if (distance > radius) { dx = dx * radius / distance; dy = dy * radius / distance; }
          stick.style.setProperty("--sx", dx.toFixed(1) + "px");
          stick.style.setProperty("--sy", dy.toFixed(1) + "px");
          const nx = dx / radius, ny = dy / radius;
          if (side === "left") { axes.lx = nx; axes.ly = ny; } else { axes.rx = nx; axes.ry = ny; }
          sendSnapshot();
        };
        stick.addEventListener("pointerdown", event => {
          event.preventDefault();
          pointerId = event.pointerId;
          stick.classList.add("active");
          try { stick.setPointerCapture(pointerId); } catch (_) {}
          update(event);
        });
        stick.addEventListener("pointermove", event => {
          if (pointerId === null || event.pointerId !== pointerId) return;
          event.preventDefault();
          update(event);
        });
        const releaseStick = event => {
          if (pointerId === null || (event && event.pointerId !== pointerId)) return;
          pointerId = null;
          stick.classList.remove("active");
          stick.style.setProperty("--sx", "0px");
          stick.style.setProperty("--sy", "0px");
          if (side === "left") { axes.lx = 0; axes.ly = 0; } else { axes.rx = 0; axes.ry = 0; }
          sendSnapshot();
        };
        stick.addEventListener("pointerup", releaseStick);
        stick.addEventListener("pointercancel", releaseStick);
      });
      if (controllerCircular && inputActions) {
        let pointerId = null;
        const update = event => {
          const rect = controllerCircular.getBoundingClientRect();
          const radius = Math.max(1, Math.min(rect.width, rect.height) / 2);
          const dx = (event.clientX - (rect.left + rect.width / 2)) / radius;
          const dy = (event.clientY - (rect.top + rect.height / 2)) / radius;
          const result = inputActions.circularDirections(dx, dy, circularRegion);
          circularRegion = result.region;
          const next = result.actions.map(action => action.toLowerCase());
          let changed = false;
          ["up", "down", "left", "right"].forEach(dir => {
            const want = next.indexOf(dir) >= 0;
            const has = pressed.has(dir);
            if (want && !has) { pressed.add(dir); changed = true; }
            else if (!want && has) { pressed.delete(dir); changed = true; }
          });
          if (next.length) controllerCircular.setAttribute("data-active", next.join(" "));
          else controllerCircular.removeAttribute("data-active");
          if (changed) sendSnapshot();
        };
        controllerCircular.addEventListener("pointerdown", event => {
          event.preventDefault();
          pointerId = event.pointerId;
          controllerCircular.classList.add("active");
          try { controllerCircular.setPointerCapture(pointerId); } catch (_) {}
          update(event);
        });
        controllerCircular.addEventListener("pointermove", event => {
          if (pointerId === null || event.pointerId !== pointerId) return;
          event.preventDefault();
          update(event);
        });
        const release = event => {
          if (pointerId === null || (event && event.pointerId !== pointerId)) return;
          pointerId = null;
          controllerCircular.classList.remove("active");
          releaseCircular();
        };
        controllerCircular.addEventListener("pointerup", release);
        controllerCircular.addEventListener("pointercancel", release);
      }
      if (controllerTouchscreen) {
        let pointerId = null;
        const map = event => {
          const rect = controllerTouchscreen.getBoundingClientRect();
          if (!(rect.width > 0 && rect.height > 0)) return null;
          return {
            x: Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)),
            y: Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height))
          };
        };
        controllerTouchscreen.addEventListener("pointerdown", event => {
          event.preventDefault();
          if (pointerId !== null) return;
          pointerId = event.pointerId;
          controllerTouchscreen.classList.add("active");
          try { controllerTouchscreen.setPointerCapture(pointerId); } catch (_) {}
          const point = map(event);
          if (point) { touch.active = true; touch.x = point.x; touch.y = point.y; sendSnapshot(); }
        });
        controllerTouchscreen.addEventListener("pointermove", event => {
          if (pointerId === null || event.pointerId !== pointerId) return;
          event.preventDefault();
          const point = map(event);
          if (point) { touch.active = true; touch.x = point.x; touch.y = point.y; sendSnapshot(); }
        });
        const release = event => {
          if (pointerId === null || (event && event.pointerId !== pointerId)) return;
          pointerId = null;
          controllerTouchscreen.classList.remove("active");
          touch.active = false; touch.x = 0; touch.y = 0;
          sendSnapshot();
        };
        controllerTouchscreen.addEventListener("pointerup", release);
        controllerTouchscreen.addEventListener("pointercancel", release);
      }
      controllerUtilities.forEach(button => {
        button.addEventListener("pointerdown", event => {
          event.preventDefault();
          const wire = button.dataset.nativeControllerUtil;
          const action = inputActions && inputActions.utilityWireToAction ? inputActions.utilityWireToAction[wire] : null;
          if (!action) return;
          button.dataset.active = "true";
          sendUtility(action);
          setTimeout(() => { button.dataset.active = "false"; }, 120);
        });
        button.addEventListener("contextmenu", event => event.preventDefault());
      });
      window.addEventListener("blur", () => { if (controllerMode) releaseAll(); });
      if (controllerMovement) controllerMovement.addEventListener("change", () => {
        movement = controllerMovement.value;
        try { localStorage.setItem("an3-controller-movement", movement); } catch (_) {}
        applyMovement();
      });
      if (controllerLayout) controllerLayout.addEventListener("change", () => { manualLayout = true; applyLayout(); });
      if (controllerDisconnect) controllerDisconnect.addEventListener("click", async () => {
        try { await window.AN3NativeController.stop(); } catch (_) {}
        resetUtilitySession();
        clearInterval(timer);
        renderPad(null);
        if (controllerCode) controllerCode.textContent = "\u2014";
        setStatus("Off");
      });
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
            resetUtilitySession();
            clearInterval(timer);
            if (controllerCode) controllerCode.textContent = "\u2014";
            renderPad(null);
            setStatus("Off");
            return;
          }
          resetUtilitySession();
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
          resetUtilitySession();
          const session = await window.AN3NativeController.join(code);
          if (controllerCode) controllerCode.textContent = session.code || "—";
          renderPad(session);
          setStatus(words(session));
          poll();
        } catch (error) {
          setStatus(error?.message || "Could not join the direct LAN host.");
        }
      });
      refresh();
    }

    const syncCard = document.getElementById("nativeAccountSyncCard");
    if (syncCard && window.AN3NativeSync) {
      const guestMode = document.getElementById("nativeSyncGuestMode");
      const accountMode = document.getElementById("nativeSyncAccountMode");
      const loginForm = document.getElementById("nativeAccountLogin");
      const accountName = document.getElementById("nativeAccountName");
      const accountPassword = document.getElementById("nativeAccountPassword");
      const logoutButton = document.getElementById("nativeAccountLogoutButton");
      const accountStatus = document.getElementById("nativeAccountStatus");
      const syncStatus = document.getElementById("nativeSyncStatus");
      const syncCode = document.getElementById("nativeSyncCode");
      const syncMessage = document.getElementById("nativeSyncMessage");
      const peersNode = document.getElementById("nativeSyncPeers");
      const conflictsNode = document.getElementById("nativeSyncConflicts");
      const libraryButton = document.getElementById("nativeSyncLibrary");
      const libraryStatus = document.getElementById("nativeSyncLibraryStatus");
      const pairCode = document.getElementById("nativeSyncPairCode");
      const background = document.getElementById("nativeSyncBackground");
      let discovery = [];
      let pollTimer = 0;
      let discoveryTimer = 0;
      const reconnectAttempts = new Map();
      const reconnectNextAt = new Map();
      const reconnectPending = new Set();

      const setMessage = message => { if (syncMessage) syncMessage.textContent = message || ""; };
      const renderConflicts = (result, system, romId) => {
        if (!conflictsNode) return;
        conflictsNode.replaceChildren();
        for (const conflict of result?.conflicts || []) {
          const row = document.createElement("div");
          row.className = "native-sync-peer";
          const label = document.createElement("strong");
          const set = conflict.local || conflict.remote || {};
          label.textContent = "Save set conflict · " + (set.memberCount || (set.members || []).length) + " member(s)";
          const actions = document.createElement("div");
          actions.className = "native-sync-peer-actions";
          for (const choice of ["local", "remote", "both"]) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "button";
            button.textContent = choice === "local" ? "Keep this device" : choice === "remote" ? "Use other device" : "Keep Both";
            button.addEventListener("click", async () => {
              actions.querySelectorAll("button").forEach(item => { item.disabled = true; });
              try {
                await window.AN3NativeSync.resolveGameConflict(system, romId, conflict, choice);
                row.remove();
                setMessage("Save set conflict resolved.");
              } catch (error) {
                setMessage(error.message || String(error));
                actions.querySelectorAll("button").forEach(item => { item.disabled = false; });
              }
            });
            actions.appendChild(button);
          }
          row.append(label, actions);
          conflictsNode.appendChild(row);
        }
      };
      const renderLibraryConflicts = result => {
        if (!conflictsNode) return;
        for (const conflict of result?.conflicts || []) {
          const row = document.createElement("div");
          row.className = "native-sync-peer";
          const label = document.createElement("strong");
          label.textContent = "Library conflict · " + conflict.key;
          const detail = document.createElement("small");
          detail.textContent = "Both devices changed this ROM; no file was overwritten.";
          row.append(label, detail);
          conflictsNode.appendChild(row);
        }
      };
      const stateText = peer => ({
        paired: "Paired / Remembered",
        available: "Available on this LAN",
        connecting: "Connecting",
        connected: "Connected",
        offline: "Offline / Disconnected",
        error: "Error / Re-pair required",
      }[peer.state] || "Available");
      const renderPeers = status => {
        if (!peersNode) return;
        peersNode.replaceChildren();
        const remembered = new Map((status?.peers || []).map(peer => [peer.deviceId, {...peer, remembered: true}]));
        for (const peer of discovery || []) {
          if (!remembered.has(peer.deviceId)) remembered.set(peer.deviceId, {...peer, state: "available", remembered: false});
        }
        if (!remembered.size) {
          peersNode.textContent = "No remembered or available LAN peers.";
          return;
        }
        for (const peer of remembered.values()) {
          const row = document.createElement("div");
          row.className = "native-sync-peer";
          const text = document.createElement("div");
          const title = document.createElement("strong");
          title.textContent = peer.name || peer.deviceId;
          const detail = document.createElement("small");
          detail.textContent = stateText(peer) + (peer.mode ? " · " + peer.mode : "");
          text.append(title, detail);
          const actions = document.createElement("div");
          actions.className = "native-sync-peer-actions";
          if (peer.remembered && peer.state !== "connected") {
            const reconnect = document.createElement("button");
            reconnect.type = "button";
            reconnect.className = "button";
            reconnect.textContent = "Reconnect";
            reconnect.addEventListener("click", async () => {
              reconnect.disabled = true;
              try { await window.AN3NativeSync.reconnect(peer.deviceId); setMessage("Connecting directly to " + (peer.name || "peer") + "…"); }
              catch (error) { setMessage(error.message || String(error)); }
              finally { reconnect.disabled = false; }
            });
            actions.appendChild(reconnect);
          }
          if (peer.remembered) {
            const forget = document.createElement("button");
            forget.type = "button";
            forget.className = "button danger";
            forget.textContent = "Forget";
            forget.addEventListener("click", async () => {
              forget.disabled = true;
              try { await window.AN3NativeSync.forget(peer.deviceId); reconnectAttempts.delete(peer.deviceId); reconnectNextAt.delete(peer.deviceId); setMessage("Peer forgotten."); }
              catch (error) { setMessage(error.message || String(error)); }
              finally { forget.disabled = false; }
            });
            actions.appendChild(forget);
          }
          row.append(text, actions);
          peersNode.appendChild(row);
        }
      };
      const renderStatus = async status => {
        if (!status) return;
        if (syncStatus) {
          const connected = (status.peers || []).filter(peer => peer.state === "connected").length;
          const connecting = (status.peers || []).filter(peer => peer.state === "connecting").length;
          syncStatus.textContent = status.error || status.state === "connecting"
            ? (status.error || "Finding the peer directly on the local network…")
            : (connected ? String(connected) + " direct peer" + (connected === 1 ? "" : "s") + " connected" : connecting ? "Authenticating direct peer" : status.running ? "Hosting / ready to pair" : "Off");
        }
        if (syncCode) syncCode.textContent = status.running && status.code ? status.code : "—";
        renderPeers(status);
        if (status.running && window.AN3NativeSync.backgroundEnabled()) {
          for (const peer of status.peers || []) {
            if (peer.state !== "offline" || reconnectPending.has(peer.deviceId)) continue;
            const nextAt = reconnectNextAt.get(peer.deviceId) || 0;
            if (Date.now() < nextAt) continue;
            const attempt = reconnectAttempts.get(peer.deviceId) || 0;
            reconnectPending.add(peer.deviceId);
            reconnectNextAt.set(peer.deviceId, Date.now() + Math.min(60000, 2000 * (2 ** attempt)));
            window.AN3NativeSync.reconnect(peer.deviceId).then(() => {
              reconnectAttempts.delete(peer.deviceId);
              reconnectNextAt.delete(peer.deviceId);
            }).catch(() => {
              reconnectAttempts.set(peer.deviceId, Math.min(5, attempt + 1));
            }).finally(() => reconnectPending.delete(peer.deviceId));
          }
        }
      };
      const refreshAccount = async () => {
        const selected = window.AN3NativeSync.mode();
        if (guestMode) guestMode.checked = selected === "guest";
        if (accountMode) accountMode.checked = selected === "account";
        if (selected === "guest") {
          if (accountStatus) accountStatus.textContent = "Guest · local device identity";
          if (loginForm) loginForm.hidden = true;
          if (logoutButton) logoutButton.hidden = true;
          return;
        }
        if (loginForm) loginForm.hidden = false;
        try { await window.AN3Account?.load?.(); } catch (_) {}
        const user = window.AN3Account?.state?.user;
        if (accountStatus) accountStatus.textContent = user ? "Signed in as " + user.name : "Sign in required";
        if (logoutButton) logoutButton.hidden = !user;
      };
      const refresh = async () => {
        try {
          const current = await window.AN3NativeSync.status();
          await renderStatus(current);
          // Exchange account proofs while the direct session is provisional,
          // regardless of which side initiated the connection.  This only
          // authenticates the peer; the user still starts a save sync
          // explicitly from a game card.
          if (window.AN3NativeSync.mode() === "account"
            && window.AN3Account?.state?.user
            && (current.peers || []).some(peer => peer.state === "connecting")) {
            try { await window.AN3NativeSync.authenticateAccount(); } catch (_) {}
            await renderStatus(await window.AN3NativeSync.status());
          }
        } catch (error) { setMessage(error.message || String(error)); }
      };
      const startHosting = async () => {
        try {
          setMessage("Starting direct LAN hosting…");
          await window.AN3NativeSync.start(window.AN3NativeSync.mode());
          await refresh();
          setMessage("Waiting for a direct LAN peer.");
        } catch (error) { setMessage(error.message || String(error)); }
      };
      guestMode?.addEventListener("change", async () => {
        if (!guestMode.checked) return;
        window.AN3NativeSync.setMode("guest");
        await refreshAccount();
        try { await window.AN3NativeSync.start("guest"); await refresh(); } catch (error) { setMessage(error.message || String(error)); }
      });
      accountMode?.addEventListener("change", async () => {
        if (!accountMode.checked) return;
        window.AN3NativeSync.setMode("account");
        await refreshAccount();
        try { await window.AN3NativeSync.start("account"); await refresh(); } catch (error) { setMessage(error.message || String(error)); }
      });
      loginForm?.addEventListener("submit", async event => {
        event.preventDefault();
        const button = document.getElementById("nativeAccountLoginButton");
        if (button) button.disabled = true;
        try {
          await window.AN3Account.login(accountName?.value, accountPassword?.value);
          if (accountPassword) accountPassword.value = "";
          await window.AN3NativeSync.start("account");
          await refreshAccount();
          await refresh();
          setMessage("Signed in. Direct LAN account verification is required before sync.");
        } catch (error) { setMessage(error.message || String(error)); }
        finally { if (button) button.disabled = false; }
      });
      logoutButton?.addEventListener("click", async () => {
        try { await window.AN3Account.logout(); window.AN3NativeSync.setMode("guest"); await window.AN3NativeSync.start("guest"); await refreshAccount(); await refresh(); setMessage("Signed out. Guest pairing remains available."); }
        catch (error) { setMessage(error.message || String(error)); }
      });
      document.getElementById("nativeSyncStart")?.addEventListener("click", startHosting);
      document.getElementById("nativeSyncStop")?.addEventListener("click", async () => {
        try { const invoke = window.AN3NativeInvoke?.(); if (typeof invoke === "function") await invoke("native_sync_stop", {}); }
        catch (error) { setMessage(error.message || String(error)); }
        await refresh();
      });
      document.getElementById("nativeSyncJoin")?.addEventListener("click", async () => {
        const code = String(pairCode?.value || "").trim();
        if (!/^\d{6}$/.test(code)) { setMessage("Enter exactly six decimal digits."); pairCode?.focus(); return; }
        try { setMessage("Finding the peer directly on the local network…"); const session = await window.AN3NativeSync.join(code); await refresh(); setMessage(session?.state === "connecting" ? "Pairing started; waiting for direct peer verification." : "Device paired over the direct LAN session."); }
        catch (error) { setMessage(error.message || String(error)); }
      });
      let libraryController = null;
      libraryButton?.addEventListener("click", async () => {
        if (libraryController) {
          libraryController.abort();
          return;
        }
        libraryController = new AbortController();
        libraryButton.textContent = "Cancel library sync";
        libraryButton.setAttribute("aria-busy", "true");
        if (libraryStatus) libraryStatus.textContent = "Checking peer…";
        try {
          const result = await window.AN3NativeSync.syncLibrary({
            signal: libraryController.signal,
            onState: state => {
              if (!libraryStatus) return;
              const phase = String(state?.phase || "");
              if (phase === "checking-peer") libraryStatus.textContent = "Checking peer…";
              else if (phase === "scanning") libraryStatus.textContent = "Scanning library…";
              else if (phase === "uploading" || phase === "downloading") {
                const total = Number(state.totalBytes || 0);
                const complete = Number(state.completedBytes || 0);
                libraryStatus.textContent = (phase === "uploading" ? "Uploading " : "Downloading ") + Math.min(100, total ? Math.round(complete / total * 100) : 0) + "%";
              } else if (phase === "syncing-data" || phase === "syncing-save" || phase === "syncing-state") libraryStatus.textContent = "Syncing saves and states…";
              else if (phase === "complete") libraryStatus.textContent = "Library sync complete.";
            },
          });
          renderLibraryConflicts(result);
          if (window.AN3RerenderLibrary) await window.AN3RerenderLibrary();
          const summary = result.counts.uploaded + " ROM sent, " + result.counts.downloaded + " ROM received" + (result.counts.conflicts ? "; conflict needs a choice" : "");
          setMessage("Full library sync complete: " + summary + ".");
        } catch (error) {
          if (error?.code === "ABORT_ERR") {
            if (libraryStatus) libraryStatus.textContent = "Library sync canceled; resumable work was kept private.";
            setMessage("Library sync canceled. No visible ROM was replaced.");
          } else {
            if (libraryStatus) libraryStatus.textContent = "Error: " + (error.message || String(error));
            setMessage(error.message || String(error));
          }
        } finally {
          libraryController = null;
          libraryButton.textContent = "Sync library";
          libraryButton.removeAttribute("aria-busy");
        }
      });
      background?.addEventListener("change", () => {
        window.AN3NativeSync.setBackgroundEnabled(background.checked);
        setMessage(background.checked ? "Foreground reconnection is enabled; OS background networking is not promised." : "Foreground reconnection remains available.");
      });
      const decorateSyncButtons = () => {
        for (const card of document.querySelectorAll(".offline-game-card[data-rom-id]")) {
          const actions = card.querySelector(".card-actions");
          const romId = card.dataset.romId;
          const system = card.dataset.system;
          if (!actions || !romId || !system || actions.querySelector("[data-native-sync-game]")) continue;
          const button = document.createElement("button");
          button.type = "button";
          button.className = "button";
          button.dataset.nativeSyncGame = "1";
          button.textContent = "Sync save";
          const status = document.createElement("span");
          status.className = "muted";
          status.setAttribute("role", "status");
          status.setAttribute("aria-live", "polite");
          status.style.flexBasis = "100%";
          const say = text => { status.textContent = text || ""; };
          button.addEventListener("click", async () => {
            button.disabled = true;
            say("Checking peer…");
            try {
              const result = await window.AN3NativeSync.syncGame(system, romId, "save", state => {
                say(state === "checking-peer" ? "Checking peer…"
                  : state === "scanning" ? "Scanning…"
                  : state === "syncing" ? "Syncing…" : "");
              });
              renderConflicts(result, system, romId);
              const summary = result.counts.uploaded + " sent, " + result.counts.downloaded + " received" + (result.counts.conflicts ? "; conflict needs a choice" : "");
              say("Complete: " + summary);
              setMessage("Save set sync complete: " + summary + ".");
            } catch (error) {
              // Surface the failure on the card that started the operation, not
              // only in the Sync settings card the user may not be looking at.
              say("Error: " + (error.message || String(error)));
              setMessage(error.message || String(error));
            } finally { button.disabled = false; }
          });
          actions.appendChild(button);
          actions.appendChild(status);
        }
      };
      if (grid) new MutationObserver(decorateSyncButtons).observe(grid, {childList: true, subtree: true});
      decorateSyncButtons();
      refreshAccount();
      window.AN3NativeSync.init().then(refresh).catch(error => setMessage(error.message || String(error)));
      pollTimer = setInterval(refresh, 2500);
      discoveryTimer = setInterval(async () => { try { discovery = await window.AN3NativeSync.discover(); await refresh(); } catch (_) {} }, 8000);
      background.checked = window.AN3NativeSync.backgroundEnabled();
      addEventListener("pagehide", () => { clearInterval(pollTimer); clearInterval(discoveryTimer); }, {once: true});
    }

    show("play");
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once: true});
  else start();
})();
