// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
(function () {
  "use strict";
  var byId = function (id) { return document.getElementById(id); };

  var request = async function (url, options) {
    var response = await fetch(url, options);
    var data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) { var error = new Error(data.error || ("HTTP " + response.status)); error.status = response.status; throw error; }
    return data;
  };
  var postJson = function (url, payload) {
    return request(url, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
  };
  var buzz = function (ms) {
    try { if (navigator.vibrate) navigator.vibrate(ms); } catch (_) {}
  };
  var groupCode = function (code) {
    var text = String(code || "").toUpperCase();
    return text.length === 6 ? text.slice(0, 3) + " " + text.slice(3) : text;
  };

  // ---- Host page: create a session and report truthful state ---------------
  var hostPanel = byId("ctrlHostPanel");
  if (hostPanel) {
    var stateNode = byId("ctrlState");
    var statusNode = byId("ctrlStatus");
    var activeBox = byId("ctrlActive");
    var startButton = byId("ctrlStart");
    var stopButton = byId("ctrlStop");
    var hostCode = "";
    var hostToken = "";
    var timer = 0;
    var failures = 0;

    var setState = function (text) { if (stateNode) stateNode.textContent = text; };

    var poll = async function () {
      if (!hostCode || !hostToken) return;
      try {
        var state = await request("/api/controller/state?code=" + encodeURIComponent(hostCode) +
          "&hostToken=" + encodeURIComponent(hostToken));
        failures = 0;
        if (!state.paired) { setState("Waiting for device"); return; }
        if (!state.lastSequence) { setState("Connected — waiting for input"); return; }
        setState(state.inputActive ? "Connected" : "Connected — input unavailable");
      } catch (error) {
        if (error.status === 403 || error.status === 404) { hostStop("Disconnected"); return; }
        failures += 1;
        setState(failures > 1 ? "Reconnecting…" : "Connected — input unavailable");
      }
    };

    var hostStop = function (message) {
      if (timer) clearInterval(timer);
      timer = 0;
      if (hostCode) { postJson("/api/controller/disconnect", {code: hostCode}).catch(function () {}); }
      hostCode = ""; hostToken = "";
      if (activeBox) activeBox.hidden = true;
      if (startButton) startButton.hidden = false;
      if (stopButton) stopButton.hidden = true;
      if (message) setState(message);
      else setState("Off");
      if (statusNode) statusNode.textContent = "";
    };

    if (startButton) startButton.addEventListener("click", async function () {
      setState("Starting…");
      try {
        var data = await postJson("/api/controller/session", {deviceId: "host", name: "Vibe Coded Emulator", ttlSeconds: 3600});
        hostCode = data.code; hostToken = data.hostToken;
        var codeNode = byId("ctrlCode"); if (codeNode) codeNode.textContent = groupCode(hostCode);
        var link = byId("ctrlLink");
        if (link) { link.href = data.joinPath; }
        var qr = byId("ctrlQr");
        if (qr) { qr.src = "/api/controller/qr.svg?code=" + encodeURIComponent(hostCode); qr.hidden = false; }
        if (activeBox) activeBox.hidden = false;
        startButton.hidden = true;
        if (stopButton) stopButton.hidden = false;
        setState("Waiting for device");
        timer = setInterval(poll, 500);
      } catch (error) { setState("Error"); if (statusNode) statusNode.textContent = error.message; }
    });
    if (stopButton) stopButton.addEventListener("click", function () { hostStop("Off"); });
  }

  // ---- Phone page: nearby hosts, pairing, layouts and input ---------------
  var joinPanel = byId("ctrlJoinPanel");
  if (joinPanel) {
    var statusNodePhone = byId("ctrlStatus");
    var pad = byId("ctrlPad");
    var padState = byId("ctrlPadState");
    var codeInput = byId("ctrlCode");
    var hostsList = byId("ctrlHosts");
    var layoutPicker = byId("ctrlLayout");
    var movementPicker = byId("ctrlMovement");
    var circular = byId("ctrlCircular");
    var touchscreen = byId("ctrlTouchscreen");
    var pairedCode = "";
    var token = "";
    var sequence = 0;
    var pressed = new Set();
    var axes = {lx: 0, ly: 0, rx: 0, ry: 0};
    var touch = {active: false, x: 0, y: 0};
    var lastAck = 0;
    var lastSentAt = 0;
    var lastLatency = 0;
    var reconnects = 0;
    var linkTimer = 0;
    var heartbeatTimer = 0;
    var system = "auto";
    var manualLayout = false;
    var movement = "dpad";
    var circularRegion = null;
    var circularActions = [];
    var utilitySequence = 0;
    try { var storedMovement = localStorage.getItem("an3-controller-movement"); if (storedMovement) movement = storedMovement; } catch (_) {}
    try { if (movementPicker) movementPicker.value = movement; } catch (_) {}

    var setPhoneState = function (text) { if (statusNodePhone) statusNodePhone.textContent = text; };
    var setPadState = function (text) { if (padState) padState.textContent = text; };

    var layoutFor = function (value) {
      if (value !== "auto") return value;
      if (system === "nds" || system === "3ds" || system === "switch") return system;
      if (system === "gba" || system === "gbc") return "gba";
      return "custom";
    };
    var applyLayout = function () {
      var layout = layoutFor(manualLayout && layoutPicker ? layoutPicker.value : "auto");
      if (pad) pad.dataset.layout = layout;
      if (touchscreen) touchscreen.hidden = !(layout === "nds" || layout === "3ds" || layout === "custom");
      if (layoutPicker && !manualLayout) layoutPicker.value = layoutFor("auto");
    };

    // The movement control is chosen on the phone and drives the same canonical
    // digital actions as the in-game overlay. Circular uses shared geometry.
    var applyMovement = function () {
      if (movementPicker) movement = movementPicker.value;
      var dpad = pad && pad.querySelector(".ctrl-dpad");
      if (dpad) dpad.hidden = movement !== "dpad";
      if (circular) circular.hidden = movement !== "circular";
      if (movement !== "circular") releaseCircular();
    };
    var releaseCircular = function () {
      var changed = false;
      ["up", "down", "left", "right"].forEach(function (dir) { if (pressed.delete(dir)) changed = true; });
      circularActions = [];
      circularRegion = null;
      if (circular) circular.removeAttribute("data-active");
      if (changed) signal("button");
    };

    var sendUtility = function (action) {
      if (!pairedCode || !token) return;
      utilitySequence += 1;
      sequence += 1;
      var payload = {s: sequence, b: Array.from(pressed), a: [axes.lx, axes.ly, axes.rx, axes.ry], u: action, us: utilitySequence};
      if (touch.active) payload.t = [touch.x, touch.y];
      outbox.push({payload: payload, move: false});
      if (outbox.length > 24) outbox.splice(0, outbox.length - 24);
      pump();
    };

    var outbox = [];
    var sending = false;
    var snapshot = function () {
      sequence += 1;
      var payload = {s: sequence, b: Array.from(pressed), a: [axes.lx, axes.ly, axes.rx, axes.ry]};
      if (touch.active) payload.t = [touch.x, touch.y];
      return payload;
    };
    // Button and touch down/up transitions must never be collapsed into a
    // later release, or a fast tap would never register. Consecutive
    // analog/touch moves are coalesced (latest-state-wins) to bound traffic.
    var signal = function (kind) {
      if (!pairedCode || !token) return;
      var item = {payload: snapshot(), move: kind === "move"};
      var last = outbox[outbox.length - 1];
      if (item.move && last && last.move) outbox[outbox.length - 1] = item;
      else outbox.push(item);
      if (outbox.length > 24) outbox.splice(0, outbox.length - 24);
      pump();
    };
    var pump = async function () {
      if (sending) return;
      sending = true;
      while (outbox.length) {
        var item = outbox.shift();
        var sentAt = Date.now();
        try {
          await postJson("/api/controller/state", Object.assign({code: pairedCode, token: token}, item.payload));
          lastSentAt = sentAt;
        } catch (error) {
          sending = false;
          if (error.status === 403 || error.status === 404) { disconnect("Disconnected"); return; }
          reconnects += 1;
          setPhoneState("Reconnecting…");
          return;
        }
      }
      sending = false;
    };

    var pollLink = async function () {
      if (!pairedCode || !token) return;
      try {
        var link = await request("/api/controller/link?code=" + encodeURIComponent(pairedCode) + "&token=" + encodeURIComponent(token));
        system = link.system || "auto";
        applyLayout();
        lastAck = link.ackSequence || 0;
        if (lastAck >= (link.lastSequence || 0) && lastAck > 0) {
          var latency = Math.max(0, Date.now() - lastSentAt);
          lastLatency = lastLatency ? Math.round(lastLatency * 0.7 + latency * 0.3) : latency;
        }
        if (!link.paired) setPhoneState("Disconnected");
        else if (link.inputActive) setPhoneState("Connected");
        else if (link.lastSequence) setPhoneState("Connected — input unavailable");
        else setPhoneState("Connected — waiting for input");
        setPadState(messageFor(link.inputActive, link.lastSequence));
      } catch (error) {
        if (error.status === 403 || error.status === 404) { disconnect("Disconnected"); return; }
        setPhoneState("Reconnecting…");
      }
    };
    var messageFor = function (inputActive, lastSequence) {
      if (inputActive) return "Connected";
      if (lastSequence) return "Connected — input unavailable";
      return "Connected — waiting for input";
    };

    var releaseAll = function () {
      pressed.clear();
      axes = {lx: 0, ly: 0, rx: 0, ry: 0};
      touch = {active: false, x: 0, y: 0};
      circularRegion = null;
      circularActions = [];
      if (circular) circular.removeAttribute("data-active");
      document.querySelectorAll(".ctrl-stick.active").forEach(function (node) { node.classList.remove("active"); node.style.setProperty("--sx", "0px"); node.style.setProperty("--sy", "0px"); });
      signal("button");
    };

    var disconnect = function (message) {
      if (linkTimer) clearInterval(linkTimer);
      if (heartbeatTimer) clearInterval(heartbeatTimer);
      linkTimer = 0; heartbeatTimer = 0;
      if (pairedCode && token) { postJson("/api/controller/disconnect", {code: pairedCode}).catch(function () {}); }
      pairedCode = ""; token = "";
      if (pad) pad.hidden = true;
      if (joinPanel) joinPanel.hidden = false;
      if (hostsList) hostsList.hidden = false;
      setPhoneState(message || "Off");
    };

    var connect = async function (code) {
      setPhoneState("Connecting…");
      try {
        var data = await postJson("/api/controller/pair", {code: code, deviceId: "phone"});
        token = data.token;
        pairedCode = data.code;
        if (codeInput) codeInput.value = data.code;
        if (joinPanel) joinPanel.hidden = true;
        if (pad) pad.hidden = false;
        applyLayout();
        setPhoneState("Connected — waiting for input");
        setPadState("Connected — waiting for input");
        linkTimer = setInterval(pollLink, 700);
        heartbeatTimer = setInterval(function () { signal("move"); }, 400);
        pollLink();
      } catch (error) {
        setPhoneState(error.message || "Error");
      }
    };

    var loadHosts = async function () {
      if (!hostsList) return;
      try {
        var data = await request("/api/controller/hosts");
        var hosts = data.hosts || [];
        hostsList.innerHTML = "";
        if (!hosts.length) { hostsList.hidden = true; return; }
        hosts.forEach(function (host) {
          var item = document.createElement("li");
          var button = document.createElement("button");
          button.type = "button";
          button.className = "ctrl-host";
          var label = document.createElement("strong");
          label.textContent = host.name || "Vibe Coded Emulator";
          var detail = document.createElement("span");
          detail.textContent = host.paired ? "Busy" : "Ready to connect";
          button.appendChild(label);
          button.appendChild(detail);
          button.addEventListener("click", function () { connect(host.code); });
          item.appendChild(button);
          hostsList.appendChild(item);
        });
        hostsList.hidden = false;
      } catch (_) { hostsList.hidden = true; }
    };

    var bindButtons = function () {
      document.querySelectorAll("#ctrlPad [data-btn]").forEach(function (button) {
        var name = button.getAttribute("data-btn");
        var press = function (event) {
          event.preventDefault();
          if (button.setPointerCapture && event.pointerId !== undefined) { try { button.setPointerCapture(event.pointerId); } catch (_) {} }
          if (pressed.has(name)) return;
          pressed.add(name); buzz(8); signal("button");
        };
        var release = function (event) {
          if (event) event.preventDefault();
          if (pressed.delete(name)) { buzz(4); signal("button"); }
        };
        button.addEventListener("pointerdown", press);
        button.addEventListener("pointerup", release);
        button.addEventListener("pointercancel", release);
        button.addEventListener("pointerleave", release);
        button.addEventListener("contextmenu", function (event) { event.preventDefault(); });
      });
    };

    var bindSticks = function () {
      document.querySelectorAll("#ctrlPad .ctrl-stick").forEach(function (stick) {
        var side = stick.getAttribute("data-stick");
        var pointerId = null;
        var update = function (event) {
          var rect = stick.getBoundingClientRect();
          var radius = Math.max(1, Math.min(rect.width, rect.height) / 2);
          var dx = event.clientX - (rect.left + rect.width / 2);
          var dy = event.clientY - (rect.top + rect.height / 2);
          var distance = Math.hypot(dx, dy);
          if (distance > radius) { dx = dx * radius / distance; dy = dy * radius / distance; }
          stick.style.setProperty("--sx", dx.toFixed(1) + "px");
          stick.style.setProperty("--sy", dy.toFixed(1) + "px");
          var nx = dx / radius, ny = dy / radius;
          if (side === "left") { axes.lx = nx; axes.ly = ny; } else { axes.rx = nx; axes.ry = ny; }
          signal("move");
        };
        stick.addEventListener("pointerdown", function (event) {
          event.preventDefault();
          pointerId = event.pointerId;
          stick.classList.add("active");
          try { stick.setPointerCapture(pointerId); } catch (_) {}
          update(event);
        });
        stick.addEventListener("pointermove", function (event) {
          if (pointerId === null || event.pointerId !== pointerId) return;
          event.preventDefault();
          update(event);
        });
        var releaseStick = function (event) {
          if (pointerId === null || (event && event.pointerId !== pointerId)) return;
          pointerId = null;
          stick.classList.remove("active");
          stick.style.setProperty("--sx", "0px");
          stick.style.setProperty("--sy", "0px");
          if (side === "left") { axes.lx = 0; axes.ly = 0; } else { axes.rx = 0; axes.ry = 0; }
          signal("button");
        };
        stick.addEventListener("pointerup", releaseStick);
        stick.addEventListener("pointercancel", releaseStick);
      });
    };

    var bindTouchscreen = function () {
      if (!touchscreen) return;
      var pointerId = null;
      var map = function (event) {
        var rect = touchscreen.getBoundingClientRect();
        if (!(rect.width > 0 && rect.height > 0)) return null;
        return {
          x: Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)),
          y: Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height))
        };
      };
      touchscreen.addEventListener("pointerdown", function (event) {
        event.preventDefault();
        if (pointerId !== null) return;
        pointerId = event.pointerId;
        touchscreen.classList.add("active");
        try { touchscreen.setPointerCapture(pointerId); } catch (_) {}
        var point = map(event); if (point) { touch = {active: true, x: point.x, y: point.y}; buzz(6); signal("button"); }
      });
      touchscreen.addEventListener("pointermove", function (event) {
        if (pointerId === null || event.pointerId !== pointerId) return;
        event.preventDefault();
        var point = map(event); if (point) { touch = {active: true, x: point.x, y: point.y}; signal("move"); }
      });
      var release = function (event) {
        if (pointerId === null || (event && event.pointerId !== pointerId)) return;
        pointerId = null;
        touchscreen.classList.remove("active");
        touch = {active: false, x: 0, y: 0};
        signal("button");
      };
      touchscreen.addEventListener("pointerup", release);
      touchscreen.addEventListener("pointercancel", release);
    };

    if (byId("ctrlConnect")) byId("ctrlConnect").addEventListener("click", function () {
      var code = (codeInput && codeInput.value || "").replace(/\s+/g, "").toUpperCase();
      if (!code) { setPhoneState("Enter a pairing code"); return; }
      connect(code);
    });
    if (byId("ctrlDisconnect")) byId("ctrlDisconnect").addEventListener("click", function () { releaseAll(); disconnect("Off"); });
    if (movementPicker) movementPicker.addEventListener("change", function () {
      movement = movementPicker.value;
      try { localStorage.setItem("an3-controller-movement", movement); } catch (_) {}
      applyMovement();
    });
    if (layoutPicker) layoutPicker.addEventListener("change", function () { manualLayout = true; applyLayout(); });
    addEventListener("pagehide", function () { if (pairedCode && token) { releaseAll(); } }, {once: true});

    var bindCircular = function () {
      if (!circular || !window.AN3InputActions) return;
      var pointerId = null;
      var update = function (event) {
        var rect = circular.getBoundingClientRect();
        var radius = Math.max(1, Math.min(rect.width, rect.height) / 2);
        var dx = (event.clientX - (rect.left + rect.width / 2)) / radius;
        var dy = (event.clientY - (rect.top + rect.height / 2)) / radius;
        var result = window.AN3InputActions.circularDirections(dx, dy, circularRegion);
        circularRegion = result.region;
        var next = result.actions.map(function (action) { return action.toLowerCase(); });
        var changed = false;
        ["up", "down", "left", "right"].forEach(function (dir) {
          var want = next.indexOf(dir) >= 0;
          var has = pressed.has(dir);
          if (want && !has) { pressed.add(dir); changed = true; }
          else if (!want && has) { pressed.delete(dir); changed = true; }
        });
        circularActions = next;
        if (next.length) circular.setAttribute("data-active", next.join(" "));
        else circular.removeAttribute("data-active");
        if (changed) signal("button");
      };
      circular.addEventListener("pointerdown", function (event) {
        event.preventDefault();
        pointerId = event.pointerId;
        circular.classList.add("active");
        try { circular.setPointerCapture(pointerId); } catch (_) {}
        update(event);
      });
      circular.addEventListener("pointermove", function (event) {
        if (pointerId === null || event.pointerId !== pointerId) return;
        event.preventDefault();
        update(event);
      });
      var release = function (event) {
        if (pointerId === null || (event && event.pointerId !== pointerId)) return;
        pointerId = null;
        circular.classList.remove("active");
        releaseCircular();
      };
      circular.addEventListener("pointerup", release);
      circular.addEventListener("pointercancel", release);
    };

    var bindUtility = function () {
      document.querySelectorAll("#ctrlPad [data-util]").forEach(function (button) {
        button.addEventListener("pointerdown", function (event) {
          event.preventDefault();
          var wire = button.getAttribute("data-util");
          var action = window.AN3InputActions && window.AN3InputActions.utilityWireToAction[wire];
          if (!action) return;
          buzz(8);
          sendUtility(action);
        });
        button.addEventListener("contextmenu", function (event) { event.preventDefault(); });
      });
    };

    bindButtons();
    bindSticks();
    bindTouchscreen();
    bindCircular();
    bindUtility();
    applyLayout();
    applyMovement();
    if (!codeInput || !codeInput.value) loadHosts();
    else connect(codeInput.value.trim().toUpperCase());
  }
})();
