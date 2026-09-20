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
          syncStatus.textContent = status.error || (connected ? String(connected) + " direct peer" + (connected === 1 ? "" : "s") + " connected" : connecting ? "Authenticating direct peer" : status.running ? "Hosting / ready to pair" : "Off");
        }
        if (syncCode) syncCode.textContent = status.running && status.code ? status.code : "—";
        renderPeers(status);
        if (status.running) {
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
        try { setMessage("Finding the peer directly on the local network…"); await window.AN3NativeSync.join(code); await refresh(); setMessage("Device paired over the direct LAN session."); }
        catch (error) { setMessage(error.message || String(error)); }
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
          button.addEventListener("click", async () => {
            button.disabled = true;
            try {
              const result = await window.AN3NativeSync.syncGame(system, romId, "save");
              renderConflicts(result, system, romId);
              setMessage("Save set sync complete: " + result.counts.uploaded + " sent, " + result.counts.downloaded + " received" + (result.counts.conflicts ? "; conflict needs a choice" : "") + ".");
            } catch (error) { setMessage(error.message || String(error)); }
            finally { button.disabled = false; }
          });
          actions.appendChild(button);
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

    const multiplayerCard = document.getElementById("nativeMultiplayerCard");
    if (multiplayerCard && window.AN3NativeMultiplayer) {
      const support = document.getElementById("nativeMultiplayerSupport");
      const statusNode = document.getElementById("nativeMultiplayerStatus");
      const messageNode = document.getElementById("nativeMultiplayerMessage");
      const address = document.getElementById("nativeMultiplayerAddress");
      const port = document.getElementById("nativeMultiplayerPort");
      const hostButton = document.getElementById("nativeMultiplayerHost");
      const joinButton = document.getElementById("nativeMultiplayerJoin");
      const stopButton = document.getElementById("nativeMultiplayerStop");
      const setMessage = message => { if (messageNode) messageNode.textContent = message || ""; };
      const render = state => {
        if (!state) return;
        if (support) support.textContent = state.available === false ? "Unavailable" : "melonDS DS only";
        if (statusNode) statusNode.textContent = state.configured ? (state.role === "host" ? "Host configured" : "Join configured") : "Off";
        if (state.address && address && !address.value) address.value = state.address;
        if (state.port && port) port.value = String(state.port);
        if (state.detail && !state.error) setMessage(state.detail);
      };
      const configure = async role => {
        const selectedPort = Number(String(port?.value || "47834").trim());
        const selectedAddress = String(address?.value || "").trim();
        if (!Number.isInteger(selectedPort) || selectedPort < 1 || selectedPort > 65535) {
          setMessage("Enter a valid LAN port.");
          port?.focus();
          return;
        }
        if (role === "join" && !selectedAddress) {
          setMessage("Enter the host's current LAN address.");
          address?.focus();
          return;
        }
        try {
          setMessage(role === "host" ? "Preparing a direct melonDS LAN host…" : "Preparing a direct melonDS LAN join…");
          render(await window.AN3NativeMultiplayer.configure(role, selectedAddress, selectedPort));
          setMessage("Configuration saved. Launch the same NDS game on both devices.");
        } catch (error) { setMessage(error?.message || "LAN multiplayer configuration failed."); }
      };
      hostButton?.addEventListener("click", () => configure("host"));
      joinButton?.addEventListener("click", () => configure("join"));
      stopButton?.addEventListener("click", async () => {
        try { render(await window.AN3NativeMultiplayer.stop()); setMessage("LAN multiplayer left."); }
        catch (error) { setMessage(error?.message || "Could not leave LAN multiplayer."); }
      });
      const refreshMultiplayer = async () => {
        try { render(await window.AN3NativeMultiplayer.status()); } catch (error) { setMessage(error?.message || "LAN multiplayer status unavailable."); }
      };
      refreshMultiplayer();
      const multiplayerTimer = setInterval(refreshMultiplayer, 2500);
      addEventListener("pagehide", () => clearInterval(multiplayerTimer), {once: true});
    }

    show("play");
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once: true});
  else start();
})();
