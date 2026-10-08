// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
(() => {
  "use strict";

  // This file contains both sides of the browser presentation bridge. The
  // EmulatorJS canvas remains the source of truth because the current
  // EmulatorJS integration does not expose a raw framebuffer. AN3 therefore
  // copies completed canvas frames as ImageBitmap objects into a bounded
  // presentation path; it never pretends that this is a WASM/SAB framebuffer
  // ring.
  const FRAME_RING_SIZE = 2;
  const MAX_TIMING_SAMPLES = 128;
  const WEBGPU = "webgpu";
  const WEBGL2 = "webgl2";
  const EXTERNAL = "external-core-canvas";

  class TimingSeries {
    constructor(limit = MAX_TIMING_SAMPLES) {
      this.limit = limit;
      this.values = [];
    }

    add(value) {
      if (!Number.isFinite(value)) return;
      this.values.push(value);
      if (this.values.length > this.limit) this.values.shift();
    }

    percentile(ratio) {
      if (!this.values.length) return null;
      const sorted = [...this.values].sort((left, right) => left - right);
      return sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * ratio) - 1))];
    }
  }

  const setCanvasSize = (canvas, width, height) => {
    const nextWidth = Math.max(1, Math.floor(Number(width) || 1));
    const nextHeight = Math.max(1, Math.floor(Number(height) || 1));
    if (canvas.width !== nextWidth) canvas.width = nextWidth;
    if (canvas.height !== nextHeight) canvas.height = nextHeight;
    return {width: nextWidth, height: nextHeight};
  };

  const failure = (stage, error) => Object.assign(new Error(`${stage}: ${error?.message || String(error)}`), {
    stage, exception: error?.name || "Error",
  });

  class WebGPUBackend {
    constructor(canvas, scope) {
      this.canvas = canvas;
      this.scope = scope;
      this.device = null;
      this.context = null;
      this.format = null;
      this.pipeline = null;
      this.sampler = null;
      this.texture = null;
      this.bindGroup = null;
      this.width = 0;
      this.height = 0;
      this.stage = "requestAdapter";
      this.firstFrame = true;
      this.fatalError = null;
      this.stages = [];
    }

    mark(stage) {
      this.stage = stage;
      if (!this.stages.includes(stage) && this.stages.length < 16) {
        this.stages.push(stage);
        if (typeof window === "undefined") this.scope.postMessage({type: "stage", stage, stages: ["worker", "OffscreenCanvas", ...this.stages]});
      }
    }

    async checked(stage, action) {
      this.mark(stage);
      const device = this.device;
      device?.pushErrorScope("validation");
      try {
        const result = await action();
        const error = await device?.popErrorScope();
        if (error) throw failure(stage, error);
        return result;
      } catch (error) {
        // A synchronous API exception still needs to release its scope.
        if (device && !error.stage) await device.popErrorScope();
        throw error.stage ? error : failure(stage, error);
      }
    }

    async init(width, height) {
      const gpu = this.scope?.navigator?.gpu;
      if (!gpu?.requestAdapter) throw new Error("WebGPU is unavailable in this rendering scope.");
      const adapter = await this.checked("requestAdapter", () => gpu.requestAdapter({powerPreference: "high-performance"}));
      if (!adapter) throw new Error("WebGPU adapter request failed.");
      this.device = await this.checked("requestDevice", () => adapter.requestDevice());
      this.device.addEventListener?.("uncapturederror", event => {
        this.fatalError = failure(this.stage, event.error);
      });
      this.device.lost.then(info => { this.fatalError = failure("device-lost", new Error(info.message || info.reason)); });
      this.mark("context");
      this.context = this.canvas.getContext("webgpu");
      if (!this.context) throw new Error("WebGPU canvas context creation failed.");
      this.format = gpu.getPreferredCanvasFormat?.() || "bgra8unorm";
      await this.checked("configure", () => this.context.configure({device: this.device, format: this.format, alphaMode: "opaque"}));
      this.sampler = this.device.createSampler({magFilter: "nearest", minFilter: "nearest"});
      const shader = await this.checked("shader", () => this.device.createShaderModule({code: `
        struct VertexOutput {
          @builtin(position) position: vec4f,
          @location(0) uv: vec2f,
        };
        @vertex fn vs(@builtin(vertex_index) index: u32) -> VertexOutput {
          var positions = array<vec2f, 6>(
            vec2f(-1.0, -1.0), vec2f(1.0, -1.0), vec2f(-1.0, 1.0),
            vec2f(-1.0, 1.0), vec2f(1.0, -1.0), vec2f(1.0, 1.0)
          );
          var uvs = array<vec2f, 6>(
            vec2f(0.0, 1.0), vec2f(1.0, 1.0), vec2f(0.0, 0.0),
            vec2f(0.0, 0.0), vec2f(1.0, 1.0), vec2f(1.0, 0.0)
          );
          var output: VertexOutput;
          output.position = vec4f(positions[index], 0.0, 1.0);
          output.uv = uvs[index];
          return output;
        }
        @group(0) @binding(0) var frameTexture: texture_2d<f32>;
        @group(0) @binding(1) var frameSampler: sampler;
        @fragment fn fs(input: VertexOutput) -> @location(0) vec4f {
          return textureSample(frameTexture, frameSampler, input.uv);
        }
      `}));
      this.pipeline = await this.checked("pipeline", () => this.device.createRenderPipelineAsync({
        layout: "auto",
        vertex: {module: shader, entryPoint: "vs"},
        fragment: {module: shader, entryPoint: "fs", targets: [{format: this.format}]},
        primitive: {topology: "triangle-list"},
      }));
      await this.checked("texture", () => this.resize(width, height));
    }

    resize(width, height) {
      const size = setCanvasSize(this.canvas, width, height);
      if (this.width === size.width && this.height === size.height && this.texture) return;
      this.texture?.destroy?.();
      this.width = size.width;
      this.height = size.height;
      const usage = (globalThis.GPUTextureUsage?.TEXTURE_BINDING || 4) |
        (globalThis.GPUTextureUsage?.COPY_DST || 2) |
        (globalThis.GPUTextureUsage?.RENDER_ATTACHMENT || 16);
      this.texture = this.device.createTexture({
        size: [this.width, this.height, 1],
        format: "rgba8unorm",
        usage,
      });
      this.bindGroup = this.device.createBindGroup({
        layout: this.pipeline.getBindGroupLayout(0),
        entries: [
          {binding: 0, resource: this.texture.createView()},
          {binding: 1, resource: this.sampler},
        ],
      });
    }

    async render(bitmap, width, height) {
      const started = performance.now();
      if (this.fatalError) throw this.fatalError;
      const validate = this.firstFrame || width !== this.width || height !== this.height;
      if (validate) this.device.pushErrorScope("validation");
      try {
      this.mark("texture");
      this.resize(width, height);
      this.mark("copyExternalImageToTexture");
      this.device.queue.copyExternalImageToTexture(
        {source: bitmap},
        {texture: this.texture},
        {width: this.width, height: this.height},
      );
      this.mark("encoder");
      const encoder = this.device.createCommandEncoder();
      this.mark("render pass");
      const pass = encoder.beginRenderPass({
        colorAttachments: [{
          view: this.context.getCurrentTexture().createView(),
          clearValue: {r: 0, g: 0, b: 0, a: 1},
          loadOp: "clear",
          storeOp: "store",
        }],
      });
      pass.setPipeline(this.pipeline);
      pass.setBindGroup(0, this.bindGroup);
      pass.draw(6);
      pass.end();
      this.mark("submit");
      this.device.queue.submit([encoder.finish()]);
      } catch (error) {
        if (validate) await this.device.popErrorScope();
        throw failure(this.stage, error);
      }
      if (validate) {
        const error = await this.device.popErrorScope();
        if (error) throw failure("first frame validation", error);
      }
      this.firstFrame = false;
      this.mark("first frame");
      return performance.now() - started;
    }

    destroy() {
      this.texture?.destroy?.();
      this.texture = null;
      this.bindGroup = null;
      this.context?.unconfigure?.();
      this.device?.destroy?.();
      this.device = null;
      this.context = null;
    }
  }

  class WebGL2Backend {
    constructor(canvas, scope) {
      this.canvas = canvas;
      this.scope = scope;
      this.gl = null;
      this.texture = null;
      this.program = null;
      this.width = 0;
      this.height = 0;
    }

    init(width, height) {
      this.gl = this.canvas.getContext("webgl2", {alpha: false, antialias: false, preserveDrawingBuffer: false});
      if (!this.gl) throw new Error("WebGL2 canvas context creation failed.");
      const vertex = this.gl.createShader(this.gl.VERTEX_SHADER);
      this.gl.shaderSource(vertex, `#version 300 es
        const vec2 positions[6] = vec2[6](
          vec2(-1.0, -1.0), vec2(1.0, -1.0), vec2(-1.0, 1.0),
          vec2(-1.0, 1.0), vec2(1.0, -1.0), vec2(1.0, 1.0)
        );
        const vec2 uvs[6] = vec2[6](
          vec2(0.0, 1.0), vec2(1.0, 1.0), vec2(0.0, 0.0),
          vec2(0.0, 0.0), vec2(1.0, 1.0), vec2(1.0, 0.0)
        );
        out vec2 uv;
        void main() { gl_Position = vec4(positions[gl_VertexID], 0.0, 1.0); uv = uvs[gl_VertexID]; }
      `);
      this.gl.compileShader(vertex);
      if (!this.gl.getShaderParameter(vertex, this.gl.COMPILE_STATUS)) {
        throw new Error(this.gl.getShaderInfoLog(vertex) || "WebGL2 vertex shader compilation failed.");
      }
      const fragment = this.gl.createShader(this.gl.FRAGMENT_SHADER);
      this.gl.shaderSource(fragment, `#version 300 es
        precision mediump float;
        in vec2 uv;
        uniform sampler2D frameTexture;
        out vec4 color;
        void main() { color = texture(frameTexture, uv); }
      `);
      this.gl.compileShader(fragment);
      if (!this.gl.getShaderParameter(fragment, this.gl.COMPILE_STATUS)) {
        throw new Error(this.gl.getShaderInfoLog(fragment) || "WebGL2 fragment shader compilation failed.");
      }
      this.program = this.gl.createProgram();
      this.gl.attachShader(this.program, vertex);
      this.gl.attachShader(this.program, fragment);
      this.gl.linkProgram(this.program);
      if (!this.gl.getProgramParameter(this.program, this.gl.LINK_STATUS)) throw new Error("WebGL2 pipeline link failed.");
      this.gl.deleteShader(vertex);
      this.gl.deleteShader(fragment);
      this.gl.useProgram(this.program);
      this.gl.uniform1i(this.gl.getUniformLocation(this.program, "frameTexture"), 0);
      this.texture = this.gl.createTexture();
      this.gl.bindTexture(this.gl.TEXTURE_2D, this.texture);
      this.gl.texParameteri(this.gl.TEXTURE_2D, this.gl.TEXTURE_MIN_FILTER, this.gl.NEAREST);
      this.gl.texParameteri(this.gl.TEXTURE_2D, this.gl.TEXTURE_MAG_FILTER, this.gl.NEAREST);
      this.gl.texParameteri(this.gl.TEXTURE_2D, this.gl.TEXTURE_WRAP_S, this.gl.CLAMP_TO_EDGE);
      this.gl.texParameteri(this.gl.TEXTURE_2D, this.gl.TEXTURE_WRAP_T, this.gl.CLAMP_TO_EDGE);
      this.resize(width, height);
    }

    resize(width, height) {
      const size = setCanvasSize(this.canvas, width, height);
      if (this.width === size.width && this.height === size.height) return;
      this.width = size.width;
      this.height = size.height;
      const gl = this.gl;
      gl.deleteTexture(this.texture);
      this.texture = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, this.texture);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      if (typeof gl.texStorage2D === "function") gl.texStorage2D(gl.TEXTURE_2D, 1, gl.RGBA8, this.width, this.height);
      else gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, this.width, this.height, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
      gl.viewport(0, 0, this.width, this.height);
    }

    render(bitmap, width, height) {
      const started = performance.now();
      this.resize(width, height);
      const gl = this.gl;
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, this.texture);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
      gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, gl.RGBA, gl.UNSIGNED_BYTE, bitmap);
      gl.useProgram(this.program);
      gl.drawArrays(gl.TRIANGLES, 0, 6);
      return performance.now() - started;
    }

    destroy() {
      this.gl?.deleteTexture?.(this.texture);
      this.gl?.deleteProgram?.(this.program);
      this.texture = null;
      this.program = null;
      this.gl = null;
    }
  }

  const createBackend = async (canvas, requested, scope) => {
    const candidates = requested === WEBGL2 ? [WEBGL2] : [WEBGPU, WEBGL2];
    let lastError = null;
    for (const candidate of candidates) {
      const backend = candidate === WEBGPU ? new WebGPUBackend(canvas, scope) : new WebGL2Backend(canvas, scope);
      try {
        await backend.init(canvas.width || 1, canvas.height || 1);
        return {backend, effective: candidate, reason: lastError?.message || "", stages: backend.stages || []};
      } catch (error) {
        lastError = error.stage ? error : failure(backend.stage || candidate, error);
        backend.destroy();
        // A canvas is permanently bound to its first context type. The bridge
        // retries WebGL2 on a fresh presentation canvas after this failure.
        if (candidate === WEBGPU && backend.format) throw lastError;
      }
    }
    throw lastError || new Error("No supported presentation backend is available.");
  };

  const workerMain = () => {
    let backend = null;
    let pending = null;
    let rendering = false;
    let effective = EXTERNAL;
    let droppedFrames = 0;
    let renderedFrames = 0;
    const renderTimes = new TimingSeries();

    const snapshot = () => ({
      effective,
      stages: ["worker", "OffscreenCanvas", ...(backend?.stages || [])],
      renderedFrames,
      droppedFrames,
      renderP50Ms: renderTimes.percentile(.50),
      renderP95Ms: renderTimes.percentile(.95),
      renderP99Ms: renderTimes.percentile(.99),
      transport: "bounded-latest-frame-wins",
      frameRingSize: FRAME_RING_SIZE,
      offscreen: true,
    });
    const publishResult = (frame, rendered, renderTimeMs = null, replaced = false) => {
      self.postMessage({type: "frame-result", frameId: frame.frameId, rendered, replaced, renderTimeMs, ...snapshot()});
    };
    const drain = async () => {
      if (rendering || !pending || !backend) return;
      rendering = true;
      const frame = pending;
      pending = null;
      try {
        if (renderedFrames === 0) backend.mark?.("first bitmap");
        const elapsed = await backend.render(frame.bitmap, frame.width, frame.height);
        renderTimes.add(elapsed);
        renderedFrames += 1;
        publishResult(frame, true, elapsed);
      } catch (error) {
        droppedFrames += 1;
        publishResult(frame, false);
        self.postMessage({type: "status", state: "failed", stage: error.stage || "render", exception: error.exception || error.name, reason: error.message || String(error)});
      } finally {
        frame.bitmap.close?.();
        rendering = false;
        if (pending) void drain();
      }
    };

    self.onmessage = async event => {
      const message = event.data || {};
      if (message.type === "init") {
        self.postMessage({type: "status", state: "initializing", requested: message.requested});
        try {
          const result = await createBackend(message.canvas, message.requested, self);
          backend = result.backend;
          effective = result.effective;
          self.postMessage({type: "status", state: "ready", reason: result.reason, stages: ["worker", "OffscreenCanvas", ...result.stages], ...snapshot()});
        } catch (error) {
          self.postMessage({type: "status", state: "failed", effective: EXTERNAL, stage: error.stage || "worker", exception: error.exception || error.name, reason: error?.message || String(error)});
        }
        return;
      }
      if (message.type === "resize") {
        try { backend?.resize(message.width, message.height); } catch (_) {}
        return;
      }
      if (message.type === "frame") {
        if (!backend || !message.bitmap) {
          message.bitmap?.close?.();
          return;
        }
        if (pending) {
          pending.bitmap.close?.();
          droppedFrames += 1;
          publishResult(pending, false, null, true);
        }
        pending = message;
        void drain();
        return;
      }
      if (message.type === "stop") {
        pending?.bitmap?.close?.();
        pending = null;
        backend?.destroy?.();
        backend = null;
        self.close();
      }
    };
  };

  if (typeof window === "undefined" && typeof self !== "undefined") {
    workerMain();
    return;
  }

  class RendererBridge {
    constructor({requested = "auto", source, parent, workerUrl, onStatus} = {}) {
      this.requested = requested;
      this.source = source;
      this.parent = parent || source?.parentElement;
      this.workerUrl = workerUrl;
      this.onStatus = onStatus;
      this.worker = null;
      this.backend = null;
      this.target = null;
      this.frame = 0;
      this.pendingCapture = false;
      this.outstanding = 0;
      this.sourceDrops = 0;
      this.frameId = 0;
      this.renderedFrames = 0;
      this.droppedFrames = 0;
      this.replacedFrames = 0;
      this.renderTimes = new TimingSeries();
      this.captureTimes = new TimingSeries();
      this.presentationIntervals = new TimingSeries();
      this.lastPresentationAt = 0;
      this.active = false;
      this.stopped = false;
      this.lastStatusPublishAt = 0;
      this.status = {requested, effective: "pending", offscreen: false, frameRingSize: FRAME_RING_SIZE};
      this.previousSourceStyle = null;
      this.transferred = false;
    }

    publish(extra = {}) {
      const sourceSize = this.sourceSize();
      // Every backend sizes its backing store from sourceSize. The DOM canvas
      // retains its default width after transferControlToOffscreen, so reading
      // target.width here would report a false 300x150 worker resolution.
      const presentationWidth = sourceSize.width;
      const presentationHeight = sourceSize.height;
      const presentationIntervalMean = this.presentationIntervals.values.length
        ? this.presentationIntervals.values.reduce((total, value) => total + value, 0) / this.presentationIntervals.values.length
        : null;
      this.status = Object.freeze({
        ...this.status,
        requested: this.requested,
        ...extra,
        renderedFrames: this.renderedFrames,
        droppedFrames: this.droppedFrames + this.sourceDrops,
        replacedFrames: this.replacedFrames,
        captureSkippedFrames: this.sourceDrops,
        inFlightFrames: this.outstanding,
        imageBitmapP50Ms: this.captureTimes.percentile(.50),
        imageBitmapP95Ms: this.captureTimes.percentile(.95),
        imageBitmapP99Ms: this.captureTimes.percentile(.99),
        renderP50Ms: this.renderTimes.percentile(.50),
        renderP95Ms: this.renderTimes.percentile(.95),
        renderP99Ms: this.renderTimes.percentile(.99),
        workerRenderP50Ms: this.worker ? this.renderTimes.percentile(.50) : null,
        workerRenderP95Ms: this.worker ? this.renderTimes.percentile(.95) : null,
        workerRenderP99Ms: this.worker ? this.renderTimes.percentile(.99) : null,
        presentationFps: presentationIntervalMean ? 1000 / presentationIntervalMean : null,
        presentationSampleCount: this.presentationIntervals.values.length,
        sourceWidth: sourceSize.width,
        sourceHeight: sourceSize.height,
        presentationWidth,
        presentationHeight,
        presentationPixels: presentationWidth * presentationHeight,
        devicePixelRatio: Number(globalThis.devicePixelRatio) || 1,
        transport: "bounded-latest-frame-wins",
        frameRingSize: FRAME_RING_SIZE,
      });
      // Frame completion updates the bounded counters on every frame, but
      // publishing across the worker/UI boundary is throttled. This keeps
      // telemetry observable without turning DOM/global status propagation
      // into a per-frame hot-path side effect.
      const now = typeof globalThis.performance?.now === "function" ? globalThis.performance.now() : Date.now();
      const isFrameResult = extra.type === "frame-result";
      const isLifecycle = extra.type === "status" || extra.state === "fallback" || extra.state === "initializing";
      if (!isFrameResult || isLifecycle || now - this.lastStatusPublishAt >= 500) {
        this.lastStatusPublishAt = now;
        this.onStatus?.(this.status);
      }
    }

    sourceSize() {
      const width = this.source?.width || this.source?.getBoundingClientRect?.().width || 1;
      const height = this.source?.height || this.source?.getBoundingClientRect?.().height || 1;
      return {width: Math.max(1, Math.floor(width)), height: Math.max(1, Math.floor(height))};
    }

    prepareTarget() {
      if (!this.source || !this.parent) throw new Error("EmulatorJS source canvas is unavailable.");
      this.target = document.createElement("canvas");
      this.target.className = "an3-render-canvas";
      this.target.setAttribute("aria-hidden", "true");
      this.target.style.pointerEvents = "none";
      this.target.style.position = "absolute";
      this.target.style.inset = "0";
      this.target.style.width = "100%";
      this.target.style.height = "100%";
      this.target.style.zIndex = "2";
      this.parent.appendChild(this.target);
      this.previousSourceStyle ||= {
        opacity: this.source.style.opacity,
        position: this.source.style.position,
        zIndex: this.source.style.zIndex,
      };
      this.source.style.position = "relative";
      this.source.style.zIndex = "1";
    }

    async start() {
      const size = this.sourceSize();
      this.prepareTarget();
      this.publish({state: "initializing", effective: "pending"});
      const canTransfer = typeof this.target.transferControlToOffscreen === "function" && typeof Worker === "function";
      if (canTransfer && this.workerUrl) {
        try {
          this.worker = new Worker(this.workerUrl);
          let timer;
          const ready = new Promise((resolve, reject) => {
            timer = setTimeout(() => reject(failure("worker initialization timeout", new Error("No ready response within 10 seconds."))), 10000);
            this.worker.onmessage = event => {
              const message = event.data || {};
              if (this.stopped) return;
              if (message.type === "stage") { this.publish(message); return; }
              if (message.type === "status") {
                if (message.state === "ready") {
                  this.active = true;
                  this.publish({state: "ready", ...message, offscreen: true});
                  clearTimeout(timer);
                  resolve(this.status);
                } else if (message.state === "failed") {
                  clearTimeout(timer);
                  const error = Object.assign(new Error(message.reason || "Render worker initialization failed."), {stage: message.stage, exception: message.exception});
                  if (this.active) void this.recoverWebGL2(error);
                  else reject(error);
                }
                return;
              }
              if (message.type === "frame-result") {
                this.outstanding = Math.max(0, this.outstanding - 1);
                if (message.rendered) {
                  const presentedAt = typeof globalThis.performance?.now === "function" ? globalThis.performance.now() : Date.now();
                  if (this.lastPresentationAt) this.presentationIntervals.add(presentedAt - this.lastPresentationAt);
                  this.lastPresentationAt = presentedAt;
                  this.renderedFrames += 1;
                  this.source.style.opacity = "0";
                  if (Number.isFinite(message.renderTimeMs)) this.renderTimes.add(message.renderTimeMs);
                } else {
                  this.droppedFrames += 1;
                  if (message.replaced) this.replacedFrames += 1;
                }
                this.publish(message);
              }
            };
            this.worker.onerror = event => {
              clearTimeout(timer);
              const error = failure("worker", new Error(event.message || "Render worker failed."));
              if (this.active) void this.recoverWebGL2(error);
              else reject(error);
            };
          });
          const offscreen = this.target.transferControlToOffscreen();
          this.transferred = true;
          this.worker.postMessage({type: "init", canvas: offscreen, requested: this.requested, ...size}, [offscreen]);
          await ready;
          this.scheduleCapture();
          return this.status;
        } catch (error) {
          return this.recoverWebGL2(error);
        }
      }

      try {
        const result = await createBackend(this.target, this.requested, window);
        this.backend = result.backend;
        this.active = true;
        this.publish({state: "ready", effective: result.effective, reason: result.reason, offscreen: false});
        this.scheduleCapture();
        return this.status;
      } catch (error) {
        return this.recoverWebGL2(error);
      }
    }

    async recoverWebGL2(error) {
      if (this.stopped || this.recovering) return this.status;
      this.recovering = true;
      this.active = false;
      this.worker?.terminate?.();
      this.worker = null;
      this.backend?.destroy?.();
      this.backend = null;
      this.outstanding = 0;
      this.source.style.opacity = this.previousSourceStyle?.opacity || "";
      this.target?.remove();
      this.target = null;
      try {
        if (this.webgl2Retried) throw error;
        this.webgl2Retried = true;
        this.prepareTarget();
        const result = await createBackend(this.target, WEBGL2, window);
        if (this.stopped) { result.backend.destroy(); this.target?.remove(); return this.status; }
        this.backend = result.backend;
        this.active = true;
        this.publish({state: "ready", effective: WEBGL2, offscreen: false, stage: error.stage || "worker", exception: error.exception || error.name, reason: error.message || String(error)});
        this.scheduleCapture();
      } catch (fallbackError) {
        this.target?.remove();
        this.target = null;
        this.publish({state: "fallback", effective: EXTERNAL, offscreen: false, reason: `${error.message}; WebGL2: ${fallbackError.message}`, stage: fallbackError.stage || "webgl2"});
      } finally { this.recovering = false; }
      return this.status;
    }

    scheduleCapture() {
      if (this.stopped || this.frame) return;
      this.frame = requestAnimationFrame(() => {
        this.frame = 0;
        void this.captureLatestFrame();
        this.scheduleCapture();
      });
    }

    async captureLatestFrame() {
      if (!this.active || this.pendingCapture || (this.backend && this.outstanding > 0) || this.outstanding >= FRAME_RING_SIZE || !this.source) {
        if (this.active && this.outstanding >= FRAME_RING_SIZE) this.sourceDrops += 1;
        return;
      }
      const size = this.sourceSize();
      this.pendingCapture = true;
      const captureStartedAt = typeof globalThis.performance?.now === "function" ? globalThis.performance.now() : Date.now();
      try {
        const bitmap = await createImageBitmap(this.source);
        const captureEndedAt = typeof globalThis.performance?.now === "function" ? globalThis.performance.now() : Date.now();
        this.captureTimes.add(captureEndedAt - captureStartedAt);
        this.pendingCapture = false;
        if (!this.active || this.stopped) {
          bitmap.close?.();
          return;
        }
        const message = {type: "frame", bitmap, frameId: ++this.frameId, ...size};
        this.outstanding += 1;
        if (this.worker) this.worker.postMessage(message, [bitmap]);
        else {
          try {
            const elapsed = await this.backend.render(bitmap, size.width, size.height);
            this.source.style.opacity = "0";
            this.renderTimes.add(elapsed);
            const presentedAt = typeof globalThis.performance?.now === "function" ? globalThis.performance.now() : Date.now();
            if (this.lastPresentationAt) this.presentationIntervals.add(presentedAt - this.lastPresentationAt);
            this.lastPresentationAt = presentedAt;
            this.renderedFrames += 1;
            this.outstanding = Math.max(0, this.outstanding - 1);
            this.publish({type: "frame-result", state: "ready", effective: this.status.effective, rendered: true, renderTimeMs: elapsed});
          } catch (error) {
            this.droppedFrames += 1;
            this.outstanding = Math.max(0, this.outstanding - 1);
            await this.recoverWebGL2(error);
          } finally {
            bitmap.close?.();
          }
        }
      } catch (error) {
        this.pendingCapture = false;
        await this.recoverWebGL2(failure("first bitmap", error));
      }
    }

    snapshot() {
      return this.status;
    }

    stop() {
      this.stopped = true;
      this.active = false;
      if (this.frame) cancelAnimationFrame(this.frame);
      this.frame = 0;
      this.worker?.postMessage({type: "stop"});
      this.worker?.terminate?.();
      this.worker = null;
      this.backend?.destroy?.();
      this.backend = null;
      this.target?.remove?.();
      this.target = null;
      if (this.source && this.previousSourceStyle) {
        this.source.style.opacity = this.previousSourceStyle.opacity;
        this.source.style.position = this.previousSourceStyle.position;
        this.source.style.zIndex = this.previousSourceStyle.zIndex;
      }
    }
  }

  const workerUrlFromRuntime = () => {
    const script = [...document.scripts].find(item => /player-runtime\.js(?:[?#]|$)/.test(item.src));
    return script ? new URL("renderer-worker.js", script.src).href : "/static/renderer-worker.js";
  };

  globalThis.AN3WebRenderer = Object.freeze({
    FRAME_RING_SIZE,
    WEBGPU,
    WEBGL2,
    EXTERNAL,
    RendererBridge,
    createRendererBridge: options => new RendererBridge({...options, workerUrl: options?.workerUrl || workerUrlFromRuntime()}),
  });
})();
