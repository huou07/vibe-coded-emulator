// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
(() => {
  "use strict";

  // The bundled EmulatorJS runtime currently creates and owns a WebGL source
  // canvas, WASM core, and audio lifecycle. This module keeps
  // AN3's session, input and persistence concerns on our side of that stable
  // boundary while the presentation bridge handles completed frames without
  // replacing the core runtime or claiming raw framebuffer ownership. Since
  // that ownership is not exposed, this adapter does not allocate a
  // SharedArrayBuffer framebuffer ring and reports the safe ImageBitmap path.
  const MAX_TIMING_SAMPLES = 240;
  const QUICK_SAVE_DATABASE = "an3-arcade-save-slots";
  const QUICK_SAVE_STORE = "states";
  // Keep the IndexedDB v1 database, object store, key format, and raw state
  // Blob payload unchanged. Extending the public range makes previously
  // hidden slot-5 records readable again without deleting or rewriting them.
  const QUICK_SAVE_SLOTS = Object.freeze(Array.from({length: 10}, (_, index) => index + 1));
  // Mirrors the native host's 64 MiB safety limit so one runaway record cannot
  // consume the whole device quota. Empty states are always rejected.
  const MAX_STATE_BYTES = 64 * 1024 * 1024;
  const rendererValues = new Set(["webgpu", "webgl2"]);
  const rendererStorageKey = "an3-presentation-renderer-v1";
  const saveRendererPreference = value => {
    if (value !== "auto" && !rendererValues.has(value)) return false;
    try { globalThis.localStorage.setItem(rendererStorageKey, value); return true; }
    catch (_) { return false; }
  };

  const queryRendererPreference = () => {
    try {
      const value = new URLSearchParams(globalThis.location?.search || "").get("renderer");
      if (value === "auto" || rendererValues.has(value)) return value;
      const stored = globalThis.localStorage?.getItem(rendererStorageKey);
      return rendererValues.has(stored) ? stored : "auto";
    } catch (_) {
      return "auto";
    }
  };

  // Copy only named scalar measurements, never arbitrary status/exception data.
  const playerDiagnostics = ({system, core, renderer = {}, pacing = {}} = {}) => {
    const name = value => typeof value === "string" && /^[a-z0-9_-]{1,48}$/i.test(value) ? value : null;
    const number = value => typeof value === "number" && Number.isFinite(value) ? value : null;
    const stages = ["worker", "OffscreenCanvas", "requestAdapter", "requestDevice", "context", "configure", "shader", "pipeline", "texture", "first bitmap", "copyExternalImageToTexture", "encoder", "render pass", "submit", "first frame"];
    const failureStage = stages.find(stage => renderer.reason?.startsWith?.(`${stage}:`));
    const result = {
      system: name(system), core: name(core),
      requested: name(renderer.requested), effective: name(renderer.effective),
      fallbackReason: !renderer.reason ? null : failureStage ? `Renderer initialization failed at ${failureStage}` : "Requested renderer unavailable; using the reported effective renderer",
      worker: renderer.offscreen === true,
      offscreenCanvas: renderer.offscreen === true,
      secureContext: globalThis.isSecureContext === true,
      crossOriginIsolated: globalThis.crossOriginIsolated === true,
      webgpuAvailable: renderer.webgpuAvailable === true,
      coreSourceFps: number(pacing.coreSourceFps),
    };
    for (const key of ["presentationFps", "renderedFrames", "droppedFrames", "replacedFrames", "renderP95Ms", "renderP99Ms", "sourceWidth", "sourceHeight", "presentationWidth", "presentationHeight", "presentationPixels", "devicePixelRatio"]) result[key] = number(renderer[key]);
    return Object.freeze(result);
  };

  class EmulatorCore {
    manager() {
      return globalThis.EJS_emulator?.gameManager || null;
    }

    getState() {
      const state = this.manager()?.getState?.();
      if (!state?.byteLength) throw new Error("Save state is not ready");
      return state instanceof Uint8Array ? state : new Uint8Array(state);
    }

    loadState(bytes) {
      const manager = this.manager();
      if (!manager?.loadState) throw new Error("Emulator is not ready");
      manager.loadState(bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes));
    }

    frameNumber() {
      const manager = this.manager();
      const candidate = manager?.getFrameNum?.() ?? manager?.frameNumber;
      return Number.isFinite(Number(candidate)) ? Number(candidate) : null;
    }
  }

  class VideoBackend {
    constructor(preference = queryRendererPreference()) {
      const probe = typeof document === "object" ? document.createElement("canvas") : null;
      const webgl2 = Boolean(probe?.getContext?.("webgl2"));
      // A canvas can expose only one WebGL context family reliably. Probe a
      // second canvas so WebGL1 capability is not masked by the WebGL2 probe.
      const webgl = Boolean(typeof document === "object" && document.createElement("canvas").getContext?.("webgl"));
      const webgpu = Boolean(globalThis.navigator?.gpu);
      this.requested = preference;
      this.selected = "pending";
      this.effective = "pending";
      this.webgpuAvailable = webgpu;
      this.webgl2Available = webgl2;
      this.webglAvailable = webgl;
      this.fallback = false;
      this.reason = "";
      this.ownsCoreCanvas = false;
      this.controller = null;
      this.listeners = new Set();
    }

    static resolve(preference = queryRendererPreference()) {
      return new VideoBackend(preference);
    }

    subscribe(listener) {
      if (typeof listener === "function") this.listeners.add(listener);
      return () => this.listeners.delete(listener);
    }

    update(status = {}) {
      this.selected = status.effective || this.selected;
      this.effective = status.effective || this.effective;
      this.fallback = this.requested === "webgpu" && this.effective !== "webgpu";
      this.reason = status.reason || (this.fallback
        ? `WebGPU was requested, but the effective backend is ${this.effective}.`
        : this.reason);
      const snapshot = this.snapshot(status);
      this.listeners.forEach(listener => { try { listener(snapshot); } catch (_) {} });
      return snapshot;
    }

    snapshot(extra = {}) {
      return Object.freeze({
        requested: this.requested,
        selected: this.selected,
        effective: this.effective,
        webgpuAvailable: this.webgpuAvailable,
        webgl2Available: this.webgl2Available,
        webglAvailable: this.webglAvailable,
        fallback: this.fallback,
        reason: this.reason,
        ownsCoreCanvas: this.ownsCoreCanvas,
        ...extra,
      });
    }

    async attach(sourceCanvas, parent) {
      if (this.controller) return this.snapshot(this.controller.snapshot());
      const factory = globalThis.AN3WebRenderer?.createRendererBridge;
      if (typeof factory !== "function") {
        return this.update({effective: "external-core-canvas", state: "fallback", reason: "The renderer bridge is unavailable."});
      }
      this.controller = factory({
        requested: this.requested,
        source: sourceCanvas,
        parent,
        onStatus: status => this.update(status),
      });
      const status = await this.controller.start();
      return this.update(status);
    }

    stop() {
      this.controller?.stop?.();
      this.controller = null;
    }
  }

  class VideoSource {
    constructor(core) {
      this.core = core;
    }

    snapshot() {
      // Both source categories are part of the stable AN3 contract. The
      // present EmulatorJS adapter is canvas-owned; native GPU frames are used
      // by the macOS Vulkan frontend instead of being copied through this API.
      return Object.freeze({
        kind: "external-core-canvas",
        supports: Object.freeze(["SoftwareFramebuffer", "NativeGpuFrame"]),
        canvas: globalThis.document?.querySelector?.("#game canvas") || null,
        rawFramebuffer: false,
        rawFramebufferProvider: null,
      });
    }
  }

  class InputRouter {
    constructor(core) {
      this.core = core;
    }

    setVirtualButton(index, pressed) {
      try {
        this.core.manager()?.simulateInput?.(0, index, pressed ? 1 : 0);
      } catch (_) {}
    }

    setVirtualAxis(x, y) {
      // The pinned EmulatorJS libretro bridge uses unsigned magnitudes for
      // the positive/negative half axes, unlike digital button values.
      const manager = this.core.manager();
      if (!Number.isFinite(x) || !Number.isFinite(y)) { x = 0; y = 0; }
      for (const [index, value] of [[16, x], [17, -x], [18, y], [19, -y]]) {
        try { manager?.simulateInput?.(0, index, Math.round(Math.max(0, Math.min(1, value)) * 32767)); } catch (_) {}
      }
    }
  }

  class SaveStateManager {
    constructor(core) {
      this.core = core;
    }

    exportBytes() {
      return this.core.getState();
    }

    importBytes(bytes) {
      this.core.loadState(bytes);
    }
  }

  // Shared state-byte validation. The native host enforces the same 64 MiB
  // ceiling before it serialises a state, so a core cannot persist a record
  // that the native path would refuse to read back.
  const validateStateBytes = (bytes, label = "Save state") => {
    if (!bytes || !bytes.byteLength) throw new Error(`${label} is empty`);
    if (bytes.byteLength > MAX_STATE_BYTES) throw new Error(`${label} exceeds the 64 MiB safety limit.`);
    return bytes;
  };

  // The autosave record stores this digest beside the bytes so a truncated or
  // otherwise corrupted record can be rejected before it reaches loadState.
  const stateDigest = async bytes => {
    validateStateBytes(bytes, "Save state");
    try {
      if (globalThis.crypto?.subtle?.digest) {
        const hash = await globalThis.crypto.subtle.digest("SHA-256", bytes);
        return [...new Uint8Array(hash)].map(byte => byte.toString(16).padStart(2, "0")).join("");
      }
    } catch (_) {}
    // Bounded fallback: length plus byte samples, never a full O(n) scan.
    let hash = bytes.length >>> 0;
    const step = Math.max(1, Math.floor(bytes.length / 256));
    for (let index = 0; index < bytes.length; index += step) hash = (hash * 31 + bytes[index]) >>> 0;
    return `s${bytes.length}:${hash.toString(16)}`;
  };

  const verifyAutoRecord = async record => {
    if (!record?.state) throw new Error("Autosave is unavailable");
    const bytes = validateStateBytes(new Uint8Array(await record.state.arrayBuffer()), "Autosave");
    if (record.digest) {
      const digest = await stateDigest(bytes);
      if (digest !== record.digest) throw new Error("Autosave is corrupted");
    }
    return bytes;
  };

  class QuickSaveManager {
    constructor(slug, databaseName = QUICK_SAVE_DATABASE, storeName = QUICK_SAVE_STORE) {
      this.slug = String(slug || "");
      this.databaseName = databaseName;
      this.storeName = storeName;
    }

    id(slot) {
      this.assertSlot(slot);
      return `${this.slug}:slot:${slot}`;
    }

    // Autosave lives in its own record so it can never overwrite a manual
    // slot. It shares the same store/transaction semantics but is not a
    // numbered slot, so it does not go through assertSlot.
    autoId() {
      return `${this.slug}:auto`;
    }

    assertSlot(slot) {
      const numericSlot = Number(slot);
      if (!QUICK_SAVE_SLOTS.includes(numericSlot)) throw new RangeError("Quick-save slots range from 1 to 10.");
      return numericSlot;
    }

    open() {
      return new Promise((resolve, reject) => {
        const request = indexedDB.open(this.databaseName, 1);
        request.onupgradeneeded = () => {
          if (!request.result.objectStoreNames.contains(this.storeName)) {
            request.result.createObjectStore(this.storeName, {keyPath: "id"});
          }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error || new Error("save slot storage unavailable"));
      });
    }

    async get(slot) {
      const database = await this.open();
      try {
        return await new Promise((resolve, reject) => {
          const request = database.transaction(this.storeName, "readonly").objectStore(this.storeName).get(this.id(slot));
          request.onsuccess = () => resolve(request.result || null);
          request.onerror = () => reject(request.error || new Error("save slot storage failed"));
        });
      } finally {
        database.close();
      }
    }

    async getMany(slots) {
      slots = slots.map(slot => this.assertSlot(slot));
      const database = await this.open();
      try {
        return await new Promise((resolve, reject) => {
          const states = new Map();
          const transaction = database.transaction(this.storeName, "readonly");
          const store = transaction.objectStore(this.storeName);
          for (const slot of slots) {
            const request = store.get(this.id(slot));
            request.onsuccess = () => states.set(slot, request.result || null);
            request.onerror = () => reject(request.error || new Error("save slot storage failed"));
          }
          transaction.oncomplete = () => resolve(slots.map(slot => states.get(slot) || null));
          transaction.onerror = () => reject(transaction.error || new Error("save slot storage failed"));
          transaction.onabort = () => reject(transaction.error || new Error("save slot storage was interrupted"));
        });
      } finally {
        database.close();
      }
    }

    async put(slot, bytes, updatedAt = Date.now()) {
      slot = this.assertSlot(slot);
      validateStateBytes(bytes);
      const database = await this.open();
      try {
        await new Promise((resolve, reject) => {
          const transaction = database.transaction(this.storeName, "readwrite");
          transaction.objectStore(this.storeName).put({
            id: this.id(slot),
            // Keep the raw libretro/EmulatorJS state bytes unchanged. No
            // wrapper or version conversion is introduced by quick saves.
            state: new Blob([bytes], {type: "application/octet-stream"}),
            updatedAt,
          });
          transaction.oncomplete = resolve;
          transaction.onerror = () => reject(transaction.error || new Error("save slot storage failed"));
          transaction.onabort = () => reject(transaction.error || new Error("save slot storage was interrupted"));
        });
      } finally {
        database.close();
      }
    }

    async getAuto() {
      const database = await this.open();
      try {
        return await new Promise((resolve, reject) => {
          const request = database.transaction(this.storeName, "readonly").objectStore(this.storeName).get(this.autoId());
          request.onsuccess = () => resolve(request.result || null);
          request.onerror = () => reject(request.error || new Error("autosave slot storage failed"));
        });
      } finally {
        database.close();
      }
    }

    // A single IndexedDB put is atomic per record, so the previous valid
    // autosave is only replaced after the new bytes are fully committed.
    async putAuto(bytes, updatedAt = Date.now(), digest = null) {
      validateStateBytes(bytes, "Autosave");
      const database = await this.open();
      try {
        await new Promise((resolve, reject) => {
          const transaction = database.transaction(this.storeName, "readwrite");
          transaction.objectStore(this.storeName).put({
            id: this.autoId(),
            state: new Blob([bytes], {type: "application/octet-stream"}),
            updatedAt,
            digest: digest || null,
            auto: true,
          });
          transaction.oncomplete = resolve;
          transaction.onerror = () => reject(transaction.error || new Error("autosave slot storage failed"));
          transaction.onabort = () => reject(transaction.error || new Error("autosave slot storage was interrupted"));
        });
      } finally {
        database.close();
      }
    }
  }

  class AudioPipeline {
    snapshot() {
      // AudioWorklet ownership remains inside the third-party EmulatorJS core.
      // Do not tie audio scheduling to requestAnimationFrame from the AN3 UI.
      return Object.freeze({owner: "EmulatorJS core", underruns: null, overruns: null, queueDepth: null, clock: "core-owned"});
    }
  }

  class FramePacingMonitor {
    constructor(core) {
      this.core = core;
      this.samples = [];
      this.lastTime = 0;
      this.lastCoreFrame = null;
      this.coreFrames = 0;
      this.raf = 0;
      this.longTasks = 0;
      this.longTaskTotalMs = 0;
      this.longTaskMaxMs = 0;
      this.coreCounterFirst = null;
      this.coreCounterLast = null;
      this.coreCounterFirstAt = 0;
      this.coreCounterLastAt = 0;
      this.coreCounterRegressions = 0;
      this.coreRateSamples = [];
      this.observer = null;
      this.renderer = null;
    }

    attachRenderer(renderer) {
      this.renderer = renderer;
    }

    start() {
      if (this.raf || typeof requestAnimationFrame !== "function") return;
      if (typeof PerformanceObserver === "function") {
        try {
          this.observer = new PerformanceObserver(entries => {
            for (const entry of entries.getEntries()) {
              const duration = Number(entry.duration) || 0;
              this.longTasks += 1;
              this.longTaskTotalMs += duration;
              this.longTaskMaxMs = Math.max(this.longTaskMaxMs, duration);
            }
          });
          this.observer.observe({type: "longtask", buffered: true});
        } catch (_) {}
      }
      const tick = now => {
        if (this.lastTime) {
          this.samples.push(now - this.lastTime);
          if (this.samples.length > MAX_TIMING_SAMPLES) this.samples.shift();
        }
        this.lastTime = now;
        const frame = this.core.frameNumber();
        if (frame !== null && this.coreCounterFirst === null) {
          this.coreCounterFirst = frame;
          this.coreCounterFirstAt = now;
        }
        if (frame !== null && this.lastCoreFrame !== null && frame >= this.lastCoreFrame) {
          this.coreFrames += frame - this.lastCoreFrame;
        } else if (frame !== null && this.lastCoreFrame !== null && frame < this.lastCoreFrame) {
          this.coreCounterRegressions += 1;
        }
        if (frame !== null) {
          this.coreCounterLast = frame;
          this.coreCounterLastAt = now;
          this.coreRateSamples.push({at: now, frame});
          while (this.coreRateSamples.length > 2 && now - this.coreRateSamples[0].at > 2000) this.coreRateSamples.shift();
        }
        this.lastCoreFrame = frame;
        this.raf = requestAnimationFrame(tick);
      };
      this.raf = requestAnimationFrame(tick);
    }

    stop() {
      if (this.raf) cancelAnimationFrame(this.raf);
      this.raf = 0;
      this.observer?.disconnect?.();
      this.observer = null;
    }

    snapshot() {
      const sorted = [...this.samples].sort((left, right) => left - right);
      const percentile = ratio => sorted.length ? sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * ratio) - 1))] : null;
      const rateFirst = this.coreRateSamples[0] || null;
      const rateLast = this.coreRateSamples[this.coreRateSamples.length - 1] || null;
      const coreElapsedMs = rateFirst && rateLast ? rateLast.at - rateFirst.at : 0;
      const coreDelta = rateFirst && rateLast ? rateLast.frame - rateFirst.frame : null;
      return Object.freeze({
        uiFrameP50Ms: percentile(.50),
        uiFrameP95Ms: percentile(.95),
        uiFrameP99Ms: percentile(.99),
        coreFrames: this.lastCoreFrame === null ? null : this.coreFrames,
        coreFrameNumber: this.coreCounterLast,
        coreSourceFps: coreElapsedMs > 0 && coreDelta >= 0 && this.coreCounterRegressions === 0
          ? coreDelta * 1000 / coreElapsedMs
          : null,
        coreSourceWindowMs: coreElapsedMs || null,
        coreFrameSource: "EmulatorJS gameManager.getFrameNum/get_current_frame_count",
        coreCounterRegressions: this.coreCounterRegressions,
        droppedFrames: this.renderer?.snapshot?.()?.droppedFrames ?? null,
        longTasks: this.longTasks,
        longTaskTotalMs: this.longTaskTotalMs,
        longTaskMaxMs: this.longTaskMaxMs,
        renderer: this.renderer?.snapshot?.() || null,
        jsHeapUsedBytes: Number.isFinite(globalThis.performance?.memory?.usedJSHeapSize)
          ? globalThis.performance.memory.usedJSHeapSize : null,
      });
    }
  }

  class EmulatorSession {
    constructor({slug, rendererPreference = queryRendererPreference()} = {}) {
      this.core = new EmulatorCore();
      this.videoSource = new VideoSource(this.core);
      this.videoBackend = VideoBackend.resolve(rendererPreference);
      this.inputRouter = new InputRouter(this.core);
      this.audioPipeline = new AudioPipeline();
      this.saveStateManager = new SaveStateManager(this.core);
      this.quickSaveManager = new QuickSaveManager(slug);
      this.framePacing = new FramePacingMonitor(this.core);
      this.framePacing.attachRenderer(this.videoBackend);
      this.rendererStartPromise = null;
    }

    startVideoRenderer() {
      if (this.rendererStartPromise) return this.rendererStartPromise;
      this.rendererStartPromise = new Promise(resolve => {
        const findCanvas = () => globalThis.document?.querySelector?.("#game canvas:not(.an3-render-canvas)") || null;
        const waitForCanvas = (attempt = 0) => {
          const canvas = findCanvas();
          if (canvas) {
            this.videoBackend.attach(canvas, canvas.parentElement).then(resolve).catch(error => {
              resolve(this.videoBackend.update({effective: "external-core-canvas", state: "fallback", reason: error.message || String(error)}));
            });
          } else if (attempt < 120) {
            globalThis.requestAnimationFrame?.(() => waitForCanvas(attempt + 1));
          } else {
            resolve(this.videoBackend.update({effective: "external-core-canvas", state: "fallback", reason: "EmulatorJS source canvas was not found."}));
          }
        };
        waitForCanvas();
      });
      return this.rendererStartPromise;
    }

    stop() {
      this.framePacing.stop();
      this.videoBackend.stop();
    }

    snapshot() {
      return Object.freeze({
        video: this.videoBackend.snapshot(),
        audio: this.audioPipeline.snapshot(),
        framePacing: this.framePacing.snapshot(),
      });
    }
  }

  // Boot return values and repeated presentation of a frozen canvas do not
  // establish visible or interactive gameplay. Optional FPS telemetry is not
  // a prerequisite for running the core or using its controls.
  const playbackReadiness = ({booted = false, failed = false, renderer = {}} = {}) => Object.freeze({
    milestone: failed ? "failed" : !booted ? "starting"
      : renderer.effective === "external-core-canvas" ? "external-video"
      : renderer.renderedFrames > 0 ? "video-submitted" : "core-started",
    coreStarted: booted,
    presentationSubmitted: renderer.renderedFrames > 0,
    gameplayVerified: false,
  });

  const createEmulatorSession = options => new EmulatorSession(options);
  globalThis.AN3PlayerRuntime = Object.freeze({
    playbackReadiness,
    EmulatorSession,
    EmulatorCore,
    VideoSource,
    VideoBackend,
    InputRouter,
    AudioPipeline,
    SaveStateManager,
    QuickSaveManager,
    QUICK_SAVE_SLOTS,
    MAX_STATE_BYTES,
    validateStateBytes,
    stateDigest,
    verifyAutoRecord,
    FramePacingMonitor,
    queryRendererPreference,
    saveRendererPreference,
    playerDiagnostics,
    createEmulatorSession,
  });
})();
