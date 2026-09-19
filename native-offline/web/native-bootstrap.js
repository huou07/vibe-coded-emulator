// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Consumed by static/offline.js to remain in the installed local-ROM flow.
window.AN3NativeOfflineApp = true;
// Desktop streams private ROMs from Rust to its bundled native libretro
// player. Android lists only the systems its
// in-app portable host supports.
const an3MobileNativeShell = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
window.AN3NativeRomStreaming = !an3MobileNativeShell;
// This is set from the shell platform, rather than the timing of Tauri's
// injected bridge. The launcher itself still resolves the bridge at click
// time, so the library cannot briefly advertise an external native player on
// macOS while WebKit finishes injection.
// Android now advertises 3DS only after the frozen release candidate passed
// the required native Vulkan video, input, audio-delivery, save, and stable-play
// device run. The capability declaration still describes the bundled host, not
// a speculative device feature.
window.AN3NativeIntegratedSystems = /Android/i.test(navigator.userAgent) ? ["gba", "nds", "3ds"] : (an3MobileNativeShell ? [] : ["gba", "nds", "3ds"]);
// Compatibility signal for pre-generic library assets. New code reads the
// systems list above so GBA and NDS can use the same in-process launch path.
window.AN3NativeIntegratedThreeDs = !an3MobileNativeShell;
// Keep this empty so player.js uses the packaged relative `/emulatorjs/...`
// path, whether the renderer is desktop loopback or Tauri's mobile HTTPS URL.
window.AN3OfflineEmulatorOrigin = "";

(() => {
  const desktopSystems = new Set(["gba", "nds", "3ds"]);
  const nativeInvoke = () => {
    const tauri = window.__TAURI__;
    const internals = window.__TAURI_INTERNALS__;
    return tauri?.core?.invoke || internals?.invoke;
  };
  // The desktop command starts our bundled native player: the existing Mac
  // view or the owned portable Windows runtime. It never searches for an
  // external emulator app. Resolve the bridge at click time for async injection.
  if (!an3MobileNativeShell) {
    window.AN3NativeLaunchGame = (romId, system, layout) => {
      const nativeSystem = String(system || "").toLowerCase();
      const invoke = nativeInvoke();
      if (typeof invoke !== "function") return Promise.reject(new Error("The native VibeCodedEmulator bridge is unavailable."));
      // Switch runs in the separate companion process, not the libretro host.
      if (nativeSystem === "switch") return invoke("switch_companion_launch_rom", {romId, visible: true});
      if (!desktopSystems.has(nativeSystem)) return Promise.reject(new Error("Unsupported native system."));
      return invoke("start_native_game", {romId, system: nativeSystem, layout: layout || "preserve"});
    };
    // Keep old desktop library assets working during an app update.
    window.AN3NativeLaunchThreeDs = (romId, _title, layout) => window.AN3NativeLaunchGame(romId, "3ds", layout);
    // Switch companion control surface (launched-not-linked). Availability is
    // resolved at runtime; nothing here claims support before detect() answers.
    const switchInvoke = (name, payload) => {
      const invoke = nativeInvoke();
      if (typeof invoke !== "function") return Promise.reject(new Error("The native VibeCodedEmulator bridge is unavailable."));
      return invoke(name, payload);
    };
    window.AN3NativeSwitch = {
      detect: () => switchInvoke("switch_companion_detect", {}),
      launch: romId => switchInvoke("switch_companion_launch_rom", {romId}),
      status: () => switchInvoke("switch_companion_status", {}),
      stop: () => switchInvoke("switch_companion_stop", {}),
      focus: () => switchInvoke("switch_companion_focus", {}),
      input: (button, pressed) => switchInvoke("switch_companion_input", {button, pressed}),
      analog: (stick, x, y) => switchInvoke("switch_companion_analog", {stick, x, y}),
      audio: () => switchInvoke("switch_companion_audio", {})
    };
    // Advertise Switch only once the companion is actually present, then let
    // the library re-render so the capability is not a static claim. Tauri
    // injects its bridge after this script evaluates, so retry until it exists.
    // The scheduler lookup keeps this file evaluable in a bare sandbox.
    const schedule = (fn, ms) => {
      const timer = (typeof window !== "undefined" && window.setTimeout) || (typeof setTimeout === "function" ? setTimeout : null);
      if (timer) timer(fn, ms);
    };
    const advertiseSwitch = (attempt = 0) => {
      if (typeof nativeInvoke() !== "function") {
        if (attempt < 40) schedule(() => advertiseSwitch(attempt + 1), 250);
        return;
      }
      window.AN3NativeSwitch.detect().then(info => {
        window.AN3SwitchDetect = { ok: true, available: info?.available === true, detail: info?.detail, path: info?.path };
        if (info?.available) {
          const systems = window.AN3NativeIntegratedSystems;
          if (Array.isArray(systems) && !systems.includes("switch")) {
            window.AN3NativeIntegratedSystems = [...systems, "switch"];
          }
          if (typeof globalThis.AN3RerenderLibrary === "function") globalThis.AN3RerenderLibrary();
        }
      }).catch(error => {
        window.AN3SwitchDetect = { ok: false, error: String(error) };
        if (attempt < 40) schedule(() => advertiseSwitch(attempt + 1), 250);
      });
    };
    advertiseSwitch();
    // Staging-only phone controller. The Rust host owns the session, the
    // polling, and the input injection; this bridge only starts/stops it.
    const controllerInvoke = name => payload => {
      const invoke = nativeInvoke();
      if (typeof invoke !== "function") return Promise.reject(new Error("The native VibeCodedEmulator bridge is unavailable."));
      return invoke(name, payload);
    };
    window.AN3NativeController = {
      start: baseUrl => controllerInvoke("native_controller_start")({baseUrl: String(baseUrl || "")}),
      stop: () => controllerInvoke("native_controller_stop")({}),
      status: () => controllerInvoke("native_controller_status")({})
    };
  }
  if (/Android/i.test(navigator.userAgent)) {
    // Library Settings -> Phone Controller uses the same app-scoped host the
    // in-game menu uses, so a session started before a game keeps working.
    const androidController = window.AN3AndroidNativeController;
    if (androidController?.start && androidController?.status) {
      const parse = value => { try { return JSON.parse(value || "{}"); } catch (_) { return {}; } };
      window.AN3NativeController = {
        start: baseUrl => Promise.resolve(parse(androidController.start(String(baseUrl || "")))),
        stop: () => { const result = parse(androidController.stop()); return Promise.resolve(result); },
        status: () => Promise.resolve(parse(androidController.status()))
      };
    }
    window.AN3NativeLaunchGame = async (romId, system, _layout, size) => {
      if (!["gba", "nds", "3ds"].includes(system)) throw new Error("Native hardware core unavailable.");
      const bridge = window.AN3AndroidNative;
      if (!bridge?.launchNative && !bridge?.launchNativeSized) throw new Error("Native Android runtime unavailable.");
      const expectedSize = Number.isFinite(Number(size)) && Number(size) > 0 ? Number(size) : -1;
      // Prefer the size-aware bridge so a record whose stored id changed (for
      // example after an app data restore) can still find its ROM by the exact
      // byte size instead of failing with a dead-end re-import prompt.
      const error = typeof bridge.launchNativeSized === "function"
        ? bridge.launchNativeSized(romId, system, expectedSize)
        : bridge.launchNative(romId, system);
      if (error) throw new Error(error);
      return {detail: "Native game surface opened; initialization status is shown there."};
    };
  }
  const bridge = window.AN3AndroidNative;
  if (!bridge?.pickAndImportRom) return;
  const pending = new Map();
  window.AN3AndroidNativeImport = romId => new Promise((resolve, reject) => {
    pending.set(romId, {resolve, reject});
    try { bridge.pickAndImportRom(romId); }
    catch (error) { pending.delete(romId); reject(error); }
  });
  window.__AN3NativeRomImportResult = result => {
    const entry = pending.get(result?.id) || pending.values().next().value;
    if (!entry) return;
    for (const [id, value] of pending) if (value === entry) pending.delete(id);
    if (result?.ok) entry.resolve(result);
    else entry.reject(new Error(result?.error || "Could not import the ROM."));
  };
  window.AN3AndroidRemoveRom = romId => bridge.removeRom?.(romId);
})();
