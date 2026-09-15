from pathlib import Path
p=Path('static/renderer-worker.js');s=p.read_text()
s=s.replace('  class WebGPUBackend {','''  const failure = (stage, error) => Object.assign(new Error(`${stage}: ${error?.message || String(error)}`), {
    stage, exception: error?.name || "Error",
  });

  class WebGPUBackend {''')
s=s.replace('''      this.height = 0;
    }

    async init''','''      this.height = 0;
      this.stage = "requestAdapter";
      this.firstFrame = true;
      this.fatalError = null;
      this.stages = [];
    }

    mark(stage) {
      this.stage = stage;
      if (!this.stages.includes(stage) && this.stages.length < 16) this.stages.push(stage);
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

    async init''',1)
s=s.replace('const adapter = await gpu.requestAdapter({powerPreference: "high-performance"});','const adapter = await this.checked("requestAdapter", () => gpu.requestAdapter({powerPreference: "high-performance"}));')
s=s.replace('this.device = await adapter.requestDevice();','''this.device = await this.checked("requestDevice", () => adapter.requestDevice());
      this.device.addEventListener?.("uncapturederror", event => {
        this.fatalError = failure(this.stage, event.error);
      });
      this.device.lost.then(info => { this.fatalError = failure("device-lost", new Error(info.message || info.reason)); });
      this.mark("context");''')
s=s.replace('this.context.configure({device: this.device, format: this.format, alphaMode: "opaque"});','await this.checked("configure", () => this.context.configure({device: this.device, format: this.format, alphaMode: "opaque"}));')
s=s.replace('const shader = this.device.createShaderModule({code:', 'const shader = await this.checked("shader", () => this.device.createShaderModule({code:')
s=s.replace('''      `});
      this.pipeline = this.device.createRenderPipeline({''','''      `}));
      this.pipeline = await this.checked("pipeline", () => this.device.createRenderPipelineAsync({''',1)
s=s.replace('''        primitive: {topology: "triangle-list"},
      });
      this.resize(width, height);''','''        primitive: {topology: "triangle-list"},
      }));
      await this.checked("texture", () => this.resize(width, height));''',1)
s=s.replace('(globalThis.GPUTextureUsage?.COPY_DST || 2);','(globalThis.GPUTextureUsage?.COPY_DST || 2) |\n        (globalThis.GPUTextureUsage?.RENDER_ATTACHMENT || 16);',1)
s=s.replace('''    render(bitmap, width, height) {
      const started = performance.now();
      this.resize(width, height);
      this.device.queue.copyExternalImageToTexture(''','''    async render(bitmap, width, height) {
      const started = performance.now();
      if (this.fatalError) throw this.fatalError;
      const validate = this.firstFrame || width !== this.width || height !== this.height;
      if (validate) this.device.pushErrorScope("validation");
      try {
      this.mark("texture");
      this.resize(width, height);
      this.mark("copyExternalImageToTexture");
      this.device.queue.copyExternalImageToTexture(''',1)
s=s.replace('''      const encoder = this.device.createCommandEncoder();
      const pass = encoder.beginRenderPass({''','''      this.mark("encoder");
      const encoder = this.device.createCommandEncoder();
      this.mark("render pass");
      const pass = encoder.beginRenderPass({''',1)
s=s.replace('''      this.device.queue.submit([encoder.finish()]);
      return performance.now() - started;''','''      this.mark("submit");
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
      return performance.now() - started;''',1)
s=s.replace('''      this.device = null;
      this.context = null;
    }
  }

  class WebGL2Backend''','''      this.context?.unconfigure?.();
      this.device?.destroy?.();
      this.device = null;
      this.context = null;
    }
  }

  class WebGL2Backend''',1)
s=s.replace('''    let lastError = null;
    for (const candidate of candidates) {
      try {
        const backend = candidate === WEBGPU ? new WebGPUBackend(canvas, scope) : new WebGL2Backend(canvas, scope);''','''    let lastError = null;
    for (const candidate of candidates) {
      const backend = candidate === WEBGPU ? new WebGPUBackend(canvas, scope) : new WebGL2Backend(canvas, scope);
      try {''')
s=s.replace('return {backend, effective: candidate};','return {backend, effective: candidate, reason: lastError?.message || "", stages: backend.stages || []};')
s=s.replace('''        lastError = error;
      }
    }
    throw lastError''','''        lastError = error.stage ? error : failure(backend.stage || candidate, error);
        backend.destroy();
        // A canvas is permanently bound to its first context type. The bridge
        // retries WebGL2 on a fresh presentation canvas after this failure.
        if (candidate === WEBGPU && backend.format) throw lastError;
      }
    }
    throw lastError''')
s=s.replace('const elapsed = backend.render(frame.bitmap, frame.width, frame.height);','const elapsed = await backend.render(frame.bitmap, frame.width, frame.height);')
s=s.replace('''      } catch (_) {
        droppedFrames += 1;
        publishResult(frame, false);''','''      } catch (error) {
        droppedFrames += 1;
        publishResult(frame, false);
        self.postMessage({type: "status", state: "failed", stage: error.stage || "render", exception: error.exception || error.name, reason: error.message || String(error)});''',1)
s=s.replace('''          self.postMessage({type: "status", state: "ready", ...snapshot()});''','''          self.postMessage({type: "status", state: "ready", reason: result.reason, stages: ["worker", "OffscreenCanvas", ...result.stages], ...snapshot()});''')
s=s.replace('''effective: EXTERNAL, reason: error?.message || String(error)''','''effective: EXTERNAL, stage: error.stage || "worker", exception: error.exception || error.name, reason: error?.message || String(error)''',1)
s=s.replace('''      this.previousSourceStyle = {
        opacity:''','''      this.previousSourceStyle ||= {
        opacity:''')
s=s.replace('''          const ready = new Promise((resolve, reject) => {
            this.worker.onmessage''','''          let timer;
          const ready = new Promise((resolve, reject) => {
            timer = setTimeout(() => reject(failure("worker initialization timeout", new Error("No ready response within 10 seconds."))), 10000);
            this.worker.onmessage''')
s=s.replace('''                  this.source.style.opacity = "0";
                  resolve(this.status);''','''                  clearTimeout(timer);
                  resolve(this.status);''',1)
s=s.replace('''                  reject(new Error(message.reason || "Render worker initialization failed."));''','''                  clearTimeout(timer);
                  const error = Object.assign(new Error(message.reason || "Render worker initialization failed."), {stage: message.stage, exception: message.exception});
                  if (this.active) void this.recoverWebGL2(error);
                  else reject(error);''',1)
s=s.replace('''                  this.renderedFrames += 1;
                  if (Number.isFinite(message.renderTimeMs))''','''                  this.renderedFrames += 1;
                  this.source.style.opacity = "0";
                  if (Number.isFinite(message.renderTimeMs))''',1)
s=s.replace('''            this.worker.onerror = event => reject(new Error(event.message || "Render worker failed."));''','''            this.worker.onerror = event => {
              clearTimeout(timer);
              const error = failure("worker", new Error(event.message || "Render worker failed."));
              if (this.active) void this.recoverWebGL2(error);
              else reject(error);
            };''')
start=s.index('''        } catch (error) {
          this.worker?.terminate''');end=s.index('\n      }\n\n      try {',start)
s=s[:start]+'''        } catch (error) {
          return this.recoverWebGL2(error);
        }'''+s[end:]
s=s.replace('''        this.source.style.opacity = "0";
        this.publish({state: "ready", effective: result.effective, offscreen: false});''','''        this.publish({state: "ready", effective: result.effective, reason: result.reason, offscreen: false});''')
s=s.replace('''      } catch (error) {
        this.publish({state: "fallback", effective: EXTERNAL, reason: error.message || String(error), offscreen: false});
        this.target.remove();
        this.target = null;
        return this.status;
      }
    }

    scheduleCapture''','''      } catch (error) {
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

    scheduleCapture''')
s=s.replace('''            const elapsed = this.backend.render(bitmap, size.width, size.height);''','''            const elapsed = await this.backend.render(bitmap, size.width, size.height);
            this.source.style.opacity = "0";''')
s=s.replace('''          } catch (_) {
            this.droppedFrames += 1;
            this.outstanding = Math.max(0, this.outstanding - 1);
          } finally''','''          } catch (error) {
            this.droppedFrames += 1;
            this.outstanding = Math.max(0, this.outstanding - 1);
            await this.recoverWebGL2(error);
          } finally''')
s=s.replace('''      } catch (_) {
        this.pendingCapture = false;
      }
    }

    snapshot''','''      } catch (error) {
        this.pendingCapture = false;
        await this.recoverWebGL2(failure("first bitmap", error));
      }
    }

    snapshot''')
p.write_text(s)
