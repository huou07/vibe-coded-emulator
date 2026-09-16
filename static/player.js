// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
(() => {
  const shell = document.querySelector("[data-player]");
  if (!shell) return;
  const config = JSON.parse(shell.dataset.player);
  const emulatorSystem = config.system === "doom" ? "prboom" : config.system;
  const debug3ds = config.system === "3ds" && new URLSearchParams(location.search).get("debug3ds") === "1";
  const debugEvents = [];
  const debugStart = performance.now();
  const safeDebugUrl = value => {
    try {
      const parsed = new URL(String(value), location.href);
      return `${parsed.origin}${parsed.pathname}`.slice(0, 512);
    } catch (_) { return "unknown"; }
  };
  const debugMilestone = (name, detail = {}) => {
    if (!debug3ds) return;
    const event = Object.freeze({name, atMs:Math.round(performance.now() - debugStart), ...detail});
    debugEvents.push(event);
    if (debugEvents.length > 64) debugEvents.shift();
    globalThis.AN3ThreeDsDiagnostics = Object.freeze({events:debugEvents.slice(), latest:event});
  };
  debugMilestone("PLAYER_DOCUMENT_READY", {secureContext:Boolean(window.isSecureContext)});
  debugMilestone("SECURE_CONTEXT_OK", {ok:Boolean(window.isSecureContext)});
  debugMilestone("CROSS_ORIGIN_ISOLATED_OK", {ok:Boolean(window.crossOriginIsolated)});
  debugMilestone("SAB_AVAILABLE", {ok:typeof SharedArrayBuffer === "function"});
  if (debug3ds && !window.__AN3DebugFetchWrapped) {
    window.__AN3DebugFetchWrapped = true;
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      const requestUrl = typeof input === "string" || input instanceof URL ? input : input?.url;
      const started = performance.now();
      debugMilestone("CORE_ASSET_REQUEST_START", {path:safeDebugUrl(requestUrl), method:init?.method || input?.method || "GET", serviceWorker:Boolean(navigator.serviceWorker?.controller)});
      try {
        const response = await originalFetch(input, init);
        debugMilestone("CORE_ASSET_REQUEST_COMPLETE", {
          path:safeDebugUrl(requestUrl), status:response.status, contentLength:response.headers.get("content-length"),
          contentRange:response.headers.get("content-range"), acceptRanges:response.headers.get("accept-ranges"),
          etag:Boolean(response.headers.get("etag")), lastModified:Boolean(response.headers.get("last-modified")),
          cache:response.headers.get("cache-control"), durationMs:Math.round(performance.now() - started)
        });
        return response;
      } catch (error) {
        debugMilestone("CORE_ASSET_REQUEST_COMPLETE", {path:safeDebugUrl(requestUrl), errorName:error?.name || "Error", error:String(error?.message || error).slice(0, 256), durationMs:Math.round(performance.now() - started)});
        throw error;
      }
    };
  }
  const primaryCores = {
    gb:"gambatte",gba:"mgba",nds:"melonds","3ds":"azahar",nes:"fceumm",snes:"snes9x",n64:"mupen64plus_next",psx:"pcsx_rearmed",psp:"ppsspp",
    segaMD:"genesis_plus_gx",segaMS:"smsplus",segaGG:"genesis_plus_gx",sega32x:"picodrive",segaCD:"genesis_plus_gx",segaSaturn:"yabause",
    arcade:"fbneo","3do":"opera",atari2600:"stella2014",atari7800:"prosystem",jaguar:"virtualjaguar",lynx:"handy",pce:"mednafen_pce",
    amiga:"puae",c64:"vice_x64sc",doom:"prboom"
  };
  const ndsPad = config.system === "nds";
  const threeDsPad = config.system === "3ds";
  // The order below is a player contract: the toolbar/menu remains above the
  // custom pad, the custom pad only owns its visible buttons, then the
  // system touchscreen/canvas receives the remaining touch input, while the
  // browser's physical keyboard keeps reaching EmulatorJS unchanged.
  const dualScreenLayout = () => innerWidth > innerHeight ? "Left/Right" : "Top/Bottom";
  const coreCapabilityError = () => {
    if (rendererPlan?.selected === "unsupported") return config.lang === "en" ? "This player needs WebGL 2." : "Trình phát này cần WebGL 2.";
    if (webgl2Required && !capabilityProbe.webgl2) return config.lang === "en" ? "This core requires WebGL 2." : "Core này cần WebGL 2.";
    if (threadedCore && (!window.crossOriginIsolated || typeof SharedArrayBuffer !== "function")) {
      return config.lang === "en"
        ? "This core needs an isolated player page with SharedArrayBuffer. Open the normal player link, not an embedded or browser-preview page."
        : "Core này cần trang player được cô lập với SharedArrayBuffer. Hãy mở liên kết player bình thường, không dùng trang nhúng hoặc preview của trình duyệt.";
    }
    return "";
  };
  const performanceStorageKey = "an3-player-performance-v1";
  const profileIds = ["auto","low","balanced","quality","custom"];
  const readPlayerStorage = (name, fallback={}) => {
    try { return JSON.parse(localStorage.getItem(name)) || fallback; } catch (_) { return fallback; }
  };
  const numericCapability = value => Number.isFinite(Number(value)) && Number(value) > 0 ? Number(value) : null;
  const capabilityProbe = Object.freeze({
    hardwareConcurrency:numericCapability(navigator.hardwareConcurrency),
    deviceMemory:numericCapability(navigator.deviceMemory),
    devicePixelRatio:numericCapability(window.devicePixelRatio),
    viewport:{width:window.innerWidth||0,height:window.innerHeight||0},
    screen:{width:window.screen?.width||0,height:window.screen?.height||0},
    webgl:Boolean(document.createElement("canvas").getContext("webgl")),
    webgl2:Boolean(document.createElement("canvas").getContext("webgl2")),
    wasm:typeof WebAssembly === "object",
    threads:Boolean(window.crossOriginIsolated && typeof SharedArrayBuffer === "function")
  });
  const recommendPerformanceProfile = probe => {
    const clearlyLowEnd=Boolean(probe.deviceMemory && probe.deviceMemory<=2 && probe.hardwareConcurrency && probe.hardwareConcurrency<=4);
    if (clearlyLowEnd || (ndsPad && !probe.webgl2)) return "low";
    return "balanced";
  };
  const normalizeProfileId = value => profileIds.includes(value) ? value : "auto";
  const storedPerformance = readPlayerStorage(performanceStorageKey);
  const performanceSettings = {
    version:1,
    selectedProfile:normalizeProfileId(storedPerformance.selectedProfile),
    customOverrides:{
      ndsRenderer:storedPerformance.customOverrides?.ndsRenderer === "legacy" ? "legacy" : "native"
    }
  };
  const recommendedProfile = recommendPerformanceProfile(capabilityProbe);
  const activeProfile = performanceSettings.selectedProfile === "auto" ? recommendedProfile : performanceSettings.selectedProfile;
  const forceLegacyNds = ndsPad && (activeProfile === "low" || (activeProfile === "custom" && performanceSettings.customOverrides.ndsRenderer === "legacy"));
  const performancePlan = Object.freeze({recommendedProfile,activeProfile,forceLegacyNds});
  const playerRuntime = globalThis.AN3PlayerRuntime;
  const rendererPreference = playerRuntime?.queryRendererPreference?.() || "auto";
  const playerSession = playerRuntime?.createEmulatorSession?.({slug:config.slug,rendererPreference}) || null;
  globalThis.AN3PlayerTelemetry = Object.freeze({snapshot: () => playerSession?.snapshot?.() || null});
  const rendererPlan = playerSession?.videoBackend || Object.freeze({requested:"auto",selected:capabilityProbe.webgl2 ? "webgl2" : (capabilityProbe.webgl ? "webgl" : "unsupported"),fallback:false,reason:""});
  const savePerformanceSettings = () => { try { localStorage.setItem(performanceStorageKey,JSON.stringify(performanceSettings)); } catch (_) {} };
  const threadedCore = ["psp","3ds"].includes(config.system);
  const webgl2Required = ["psp","3ds"].includes(config.system);
  const stage = document.querySelector(".player-stage");
  stage?.classList.toggle("lang-en",config.lang === "en");
  const loading = document.getElementById("loading");
  const loadingText = document.getElementById("loadingText");
  const loadingBar = document.getElementById("loadingBar");
  const loadingProgress = loadingBar?.closest('[role="progressbar"]');
  const loadingPct = document.getElementById("loadingPct");
  const notice = document.getElementById("playerNotice");
  const statusText = document.getElementById("playerStatusText");
  const saveStatus = document.getElementById("playerSaveStatus");
  let coreBooted = false;
  let runtimeFailed = false;
  const diagnosticsSnapshot = () => playerRuntime?.playerDiagnostics?.({
    system: config.system, core: globalThis.EJS_emulator?.gameManager?.core || globalThis.EJS_emulator?.core || null,
    renderer: globalThis.AN3RendererStatus || {}, pacing: playerSession?.framePacing?.snapshot?.() || {},
  }) || {};
  const updateDiagnostics = () => {
    const data = diagnosticsSnapshot();
    for (const [id, value] of [["rendererRequestedValue", data.requested], ["rendererEffectiveValue", data.effective], ["rendererFallbackValue", data.fallbackReason]]) {
      const output = document.getElementById(id);
      if (output) output.textContent = value ?? "—";
    }
    const details = document.getElementById("playerDiagnostics");
    const output = document.getElementById("playerDiagnosticsText");
    if (details?.open && output) output.textContent = JSON.stringify(data, null, 2);
  };
  const presentationSelect = document.getElementById("presentationRenderer");
  if (presentationSelect) presentationSelect.value = rendererPreference;
  presentationSelect?.addEventListener("change", () => {
    const saved = playerRuntime.saveRendererPreference(presentationSelect.value);
    const hint = document.getElementById("presentationRendererHint");
    if (hint) hint.textContent = saved
      ? (config.lang === "en" ? "Saved on this device. Restart to apply." : "Đã lưu trên thiết bị. Khởi động lại để áp dụng.")
      : (config.lang === "en" ? "Storage unavailable. Apply and restart to use this choice." : "Không thể lưu. Áp dụng và khởi động lại để dùng lựa chọn này.");
  });
  document.getElementById("applyPresentationRenderer")?.addEventListener("click", () => {
    const value = presentationSelect?.value || "auto";
    playerRuntime.saveRendererPreference(value);
    const url = new URL(location.href);
    url.searchParams.set("renderer", value);
    location.assign(url.href);
  });
  document.getElementById("playerDiagnostics")?.addEventListener("toggle", updateDiagnostics);
  document.getElementById("copyPlayerDiagnostics")?.addEventListener("click", async () => {
    const status = document.getElementById("copyPlayerDiagnosticsStatus");
    try {
      await navigator.clipboard.writeText(JSON.stringify(diagnosticsSnapshot(), null, 2));
      if (status) status.textContent = config.lang === "en" ? "Copied" : "Đã sao chép";
    } catch (_) {
      if (status) status.textContent = config.lang === "en" ? "Copy unavailable. Select and copy the diagnostics text." : "Không thể sao chép. Hãy chọn và sao chép văn bản chẩn đoán.";
    }
  });
  const publishPerformanceTelemetry = rendererSnapshot => {
    if (!stage || !playerSession) return;
    const pacing = playerSession.framePacing.snapshot();
    const renderer = rendererSnapshot || pacing.renderer || {};
    const values = {
      coreFrameNumber: pacing.coreFrameNumber,
      coreSourceFps: pacing.coreSourceFps,
      coreSourceWindowMs: pacing.coreSourceWindowMs,
      coreCounterRegressions: pacing.coreCounterRegressions,
      uiFrameP50Ms: pacing.uiFrameP50Ms,
      uiFrameP95Ms: pacing.uiFrameP95Ms,
      uiFrameP99Ms: pacing.uiFrameP99Ms,
      longTasks: pacing.longTasks,
      longTaskTotalMs: pacing.longTaskTotalMs,
      longTaskMaxMs: pacing.longTaskMaxMs,
      rendererP50Ms: renderer.renderP50Ms,
      workerRenderP50Ms: renderer.workerRenderP50Ms,
      workerRenderP95Ms: renderer.workerRenderP95Ms,
      workerRenderP99Ms: renderer.workerRenderP99Ms,
      imageBitmapP50Ms: renderer.imageBitmapP50Ms,
      imageBitmapP95Ms: renderer.imageBitmapP95Ms,
      imageBitmapP99Ms: renderer.imageBitmapP99Ms,
      presentationFps: renderer.presentationFps,
      presentationSampleCount: renderer.presentationSampleCount,
      renderedFrames: renderer.renderedFrames,
      droppedFrames: renderer.droppedFrames,
      replacedFrames: renderer.replacedFrames,
      captureSkippedFrames: renderer.captureSkippedFrames,
      inFlightFrames: renderer.inFlightFrames,
      sourceWidth: renderer.sourceWidth,
      sourceHeight: renderer.sourceHeight,
      presentationWidth: renderer.presentationWidth,
      presentationHeight: renderer.presentationHeight,
      presentationPixels: renderer.presentationPixels,
      devicePixelRatio: renderer.devicePixelRatio,
    };
    for (const [name, value] of Object.entries(values)) {
      stage.dataset[`p2${name[0].toUpperCase()}${name.slice(1)}`] = value == null ? "" : String(value);
    }
    stage.dataset.p2CoreFrameSource = pacing.coreFrameSource || "";
  };
  const publishRendererStatus = status => {
    const snapshot = status || rendererPlan?.snapshot?.() || rendererPlan;
    if (stage) {
      stage.dataset.rendererRequested = snapshot.requested || rendererPreference;
      stage.dataset.rendererEffective = snapshot.effective || snapshot.selected || "pending";
      stage.dataset.rendererOffscreen = String(Boolean(snapshot.offscreen));
      stage.dataset.rendererRenderedFrames = String(snapshot.renderedFrames ?? 0);
      stage.dataset.rendererDroppedFrames = String(snapshot.droppedFrames ?? 0);
      stage.dataset.rendererP95Ms = snapshot.renderP95Ms == null ? "" : String(snapshot.renderP95Ms);
      stage.dataset.rendererP99Ms = snapshot.renderP99Ms == null ? "" : String(snapshot.renderP99Ms);
      stage.dataset.rendererPresentationFps = snapshot.presentationFps == null ? "" : String(snapshot.presentationFps);
      stage.dataset.rendererImageBitmapP95Ms = snapshot.imageBitmapP95Ms == null ? "" : String(snapshot.imageBitmapP95Ms);
      stage.dataset.rendererImageBitmapP99Ms = snapshot.imageBitmapP99Ms == null ? "" : String(snapshot.imageBitmapP99Ms);
      stage.dataset.rendererSourceSize = snapshot.sourceWidth && snapshot.sourceHeight ? `${snapshot.sourceWidth}x${snapshot.sourceHeight}` : "";
      stage.dataset.rendererPresentationSize = snapshot.presentationWidth && snapshot.presentationHeight ? `${snapshot.presentationWidth}x${snapshot.presentationHeight}` : "";
    }
    globalThis.AN3RendererStatus = Object.freeze({...snapshot});
    publishPerformanceTelemetry(snapshot);
    updateDiagnostics();
    if (coreBooted && !runtimeFailed) updatePlaybackReadiness(snapshot);
  };
  rendererPlan?.subscribe?.(publishRendererStatus);
  publishRendererStatus(rendererPlan?.snapshot?.() || rendererPlan);
  const setRuntimeStatus = (state, text) => {
    if (statusText) statusText.textContent = text;
    stage?.classList.toggle("is-ready", state === "ready");
    stage?.classList.toggle("has-error", state === "error");
  };
  const updatePlaybackReadiness = (renderer = globalThis.AN3RendererStatus || {}) => {
    const readiness = playerRuntime.playbackReadiness({booted: coreBooted, failed: runtimeFailed, renderer});
    globalThis.AN3PlaybackReadiness = readiness;
    if (stage) stage.dataset.playbackMilestone = readiness.milestone;
    if (runtimeFailed) return;
    const labels = config.lang === "en" ? {
      starting: "Starting core",
      "core-started": "Core started · gameplay unverified",
      "video-submitted": "Video active · gameplay unverified",
      "external-video": "Core display fallback · gameplay unverified",
    } : {
      starting: "Đang khởi động core",
      "core-started": "Core đã khởi động · chưa xác minh gameplay",
      "video-submitted": "Có khung hình · chưa xác minh gameplay",
      "external-video": "Dùng màn hình core · chưa xác minh gameplay",
    };
    setRuntimeStatus("loading", labels[readiness.milestone] || labels.starting);
  };
  const showNotice = (message, error = false) => {
    notice.textContent = message;
    notice.className = error ? "player-notice show error" : "player-notice show";
    clearTimeout(showNotice.timer);
    showNotice.timer = setTimeout(() => { notice.className = "player-notice"; }, 2800);
  };
  const setProgress = (value, text) => {
    const pct = Math.max(0, Math.min(100, Math.round(value)));
    loadingBar.style.width = `${pct}%`;
    loadingProgress?.setAttribute("aria-valuenow", String(pct));
    loadingPct.textContent = `${pct}%`;
    if (text) {
      loadingText.textContent = text;
      loadingProgress?.setAttribute("aria-valuetext", text);
      setRuntimeStatus("loading", text);
    }
  };
  let preloadReported = false;
  let bootstrapReadyTimer = 0;
  let virtualPadGuardTimer = 0;
  const clearBootstrapTimers = () => {
    if (bootstrapReadyTimer) clearInterval(bootstrapReadyTimer);
    if (virtualPadGuardTimer) clearInterval(virtualPadGuardTimer);
    bootstrapReadyTimer = 0;
    virtualPadGuardTimer = 0;
  };
  const reportPreload = (ok, error = "") => {
    if (config.mode !== "preload" || preloadReported) return;
    preloadReported = true;
    window.parent?.postMessage({type:"an3-core-preload", system:config.system, ok, error}, location.origin);
  };
  const finishLoading = () => {
    clearBootstrapTimers();
    debugMilestone("WASM_COMPILE_COMPLETE", {system:config.system});
    setProgress(100, config.lang === "en" ? "Ready" : "Sẵn sàng");
    coreBooted = true;
    updatePlaybackReadiness();
    debugMilestone("CORE_STARTED", {system:config.system, gameplayVerified:false});
    playerSession?.framePacing.start();
    if (config.mode === "emulator") {
      playerSession?.startVideoRenderer?.().then(status => {
        publishRendererStatus(status);
        if (status?.fallback) showNotice(config.lang === "en"
          ? `WebGPU was requested; the effective backend is ${status.effective}.`
          : `Đã yêu cầu WebGPU; backend thực tế là ${status.effective}.`);
      }).catch(error => showNotice(error.message || String(error), true));
    }
    if (config.mode !== "preload") queueTvDiscovery();
    reportPreload(true);
    setTimeout(() => loading.classList.add("done"), 350);
  };
  const failLoading = error => { runtimeFailed=true;clearBootstrapTimers();const message=error.message || String(error);loadingText.textContent=message;loadingText.style.color="#ef6a67";loadingProgress?.setAttribute("aria-invalid","true");loadingProgress?.setAttribute("aria-valuetext",message);setRuntimeStatus("error",config.lang === "en" ? "Could not start" : "Không thể khởi động");reportPreload(false,message); };
  addEventListener("pagehide", () => { clearBootstrapTimers();playerSession?.framePacing.stop(); }, {once:true});
  addEventListener("pagehide", () => { playerSession?.stop?.(); }, {once:true});

  const openCoreDatabase = () => new Promise((resolve,reject) => {
    const request=indexedDB.open("EmulatorJS-core",1);
    request.onupgradeneeded=()=>{if(!request.result.objectStoreNames.contains("core"))request.result.createObjectStore("core");};
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(request.error || new Error("EmulatorJS core storage is unavailable"));
  });
  const putCoreRecord = async (key,data,version) => {
    const database=await openCoreDatabase();
    try {
      await new Promise((resolve,reject) => {
        const tx=database.transaction("core","readwrite"),store=tx.objectStore("core"),keysRequest=store.get("?EJS_KEYS!");
        keysRequest.onsuccess=()=>{const keys=Array.isArray(keysRequest.result)?keysRequest.result.slice():[];if(!keys.includes(key))keys.push(key);store.put({version,data},key);store.put(keys,"?EJS_KEYS!");};
        keysRequest.onerror=()=>reject(keysRequest.error || new Error("Could not read the EmulatorJS core index"));
        tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error || new Error("Could not save the EmulatorJS core"));tx.onabort=()=>reject(tx.error || new Error("Could not save the EmulatorJS core"));
      });
    } finally { database.close(); }
  };
  const getCoreRecord = async key => {
    const database=await openCoreDatabase();
    try {
      return await new Promise((resolve,reject) => {
        const request=database.transaction("core","readonly").objectStore("core").get(key);
        request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error || new Error("Could not verify the EmulatorJS core"));
      });
    } finally { database.close(); }
  };

  const preloadCoreAssets = async () => {
    try {
      const core = primaryCores[config.system];
      if (!core) throw new Error(config.lang === "en" ? "This system does not have an offline core manifest." : "Hệ máy này chưa có danh sách core ngoại tuyến.");
      const webgl2 = Boolean(document.createElement("canvas").getContext("webgl2"));
      const capabilityError=coreCapabilityError();
      if (capabilityError) throw new Error(capabilityError);
      // A core data path is immutable once cached for offline use. Azahar
      // received a repaired WebAssembly build, so only 3DS uses a new path;
      // existing downloads for every other system remain untouched.
      const emulatorDataPath = config.system === "3ds" ? "data-v2" : "data";
      const configuredOrigin=typeof config.emulatorOrigin === "string" ? config.emulatorOrigin.trim().replace(/\/+$/, "") : "";
      const root = configuredOrigin ? `${configuredOrigin}/${config.channel}/${emulatorDataPath}/` : `/emulatorjs/${config.channel}/${emulatorDataPath}/`;
      // `latest/data-v2` carries the repaired 3DS core but no duplicated
      // locale directory. Locales are shared by stable EmulatorJS data.
      const localizationRoot = configuredOrigin ? `${configuredOrigin}/stable/data/` : "/emulatorjs/stable/data/";
      // A controlling worker already writes EmulatorJS assets to the dedicated
      // core cache. Avoid a second clone/write on the offline preload path;
      // the manual cache remains the first-control fallback.
      const runtimeCache="caches" in globalThis && !navigator.serviceWorker?.controller ? await caches.open("an3-arcade-cores-v1") : null;
      const reportUrl=`${root}cores/reports/${core}.json`,reportResponse=await fetch(reportUrl,{credentials:"same-origin"});
      if (!reportResponse.ok) throw new Error(`cores/reports/${core}.json (${reportResponse.status})`);
      if (runtimeCache) await runtimeCache.put(reportUrl,reportResponse.clone());
      const report=await reportResponse.json();
      // Azahar declares `requiresWebgl2`, not `defaultWebGL2`.  Reading both
      // report forms is important: otherwise the offline preloader requests
      // a non-existent `azahar-thread-legacy` binary and makes 3DS look like
      // a broken core even when the checked WebGL2 bundle is present.
      const coreUsesWebgl2=!performancePlan.forceLegacyNds && webgl2 && Boolean(report?.options?.defaultWebGL2 || report?.options?.requiresWebgl2 || webgl2Required);
      const coreFile = `${core}${threadedCore?"-thread":""}${coreUsesWebgl2?"":"-legacy"}-wasm.data`;
      const localization = config.lang === "en" ? "en-US.json" : "vi-VN.json";
      const assets = [
        {label:"loader.js",url:`${root}loader.js`},
        {label:"emulator.min.js",url:`${root}emulator.min.js`},
        {label:"emulator.min.css",url:`${root}emulator.min.css`},
        {label:`localization/${localization}`,url:`${localizationRoot}localization/${localization}`},
        {label:"compression/extract7z.js",url:`${root}compression/extract7z.js`},
        {label:"compression/extractzip.js",url:`${root}compression/extractzip.js`},
        {label:`cores/${coreFile}`,url:`${root}cores/${coreFile}`}
      ];
      if (core === "ppsspp") assets.push({label:"cores/ppsspp-assets.zip",url:`${root}cores/ppsspp-assets.zip`});
      let coreData=null;
      for (let index=0; index<assets.length; index+=1) {
        const {label:asset,url} = assets[index];
        setProgress(8 + ((index + 1) / assets.length) * 82, config.lang === "en" ? `Downloading ${asset}` : `Đang tải ${asset}`);
        const response = await fetch(url, {credentials:"same-origin"});
        if (!response.ok) throw new Error(`${asset} (${response.status})`);
        if (runtimeCache) await runtimeCache.put(url,response.clone());
        const data=await response.arrayBuffer();
        if (asset===`cores/${coreFile}`) coreData=data;
      }
      if (!coreData?.byteLength || !report?.buildStart) throw new Error(config.lang === "en" ? "The downloaded core is incomplete." : "Core tải về không đầy đủ.");
      setProgress(94,config.lang === "en" ? "Saving and verifying core" : "Đang lưu và kiểm tra core");
      await putCoreRecord(coreFile,coreData,report.buildStart);
      const saved=await getCoreRecord(coreFile);
      if (saved?.data?.byteLength!==coreData.byteLength) throw new Error(config.lang === "en" ? "Could not verify the saved core." : "Không xác minh được core đã lưu.");
      finishLoading();
    } catch (error) { failLoading(error); }
  };

  if (config.mode === "preload") {
    preloadCoreAssets();
    return;
  }

  document.getElementById("fullscreen")?.addEventListener("click", () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else shell.requestFullscreen?.();
  });

  const castButton=document.getElementById("castScreen");
  let castPreview=null;
  let castDiscoveryVideo=null;
  let castAvailabilityWatch=null;
  let castDiscoveryFrame=0;
  let castConsoleAutoPad=false;
  const castText = state => {
    const vi={idle:"Dò TV & phát màn hình",searching:"Đang dò TV cùng mạng…",available:"TV cùng mạng sẵn sàng · Phát",connecting:"Đang kết nối TV…",connected:"Đang phát trên TV"};
    const en={idle:"Find TV & cast game",searching:"Looking for TVs on this network…",available:"TV on this network · Cast",connecting:"Connecting to TV…",connected:"Casting to TV"};
    return (config.lang === "en" ? en : vi)[state] || (config.lang === "en" ? en.idle : vi.idle);
  };
  const setCastState=(state,{disabled=false}={})=>{
    if(!castButton) return;
    const text=castText(state);
    castButton.textContent=text;
    castButton.disabled=disabled;
    castButton.dataset.castState=state;
    castButton.setAttribute("aria-label",text);
  };
  const releaseTvDiscovery=()=>{
    if(castDiscoveryVideo?.remote && castAvailabilityWatch!==null) {
      try { castDiscoveryVideo.remote.cancelWatchAvailability(castAvailabilityWatch); } catch (_) {}
    }
    castAvailabilityWatch=null;
    const stream=castDiscoveryVideo?.srcObject;
    if(stream?.getTracks) stream.getTracks().forEach(track=>track.stop());
    castDiscoveryVideo?.remove();
    castDiscoveryVideo=null;
  };
  const leaveTvConsoleMode=()=>{
    stage?.classList.remove("tv-console-mode");
    if(castConsoleAutoPad) padRoot?.classList.remove("cast-console-show");
    castConsoleAutoPad=false;
    if(gameStarted) updatePlaybackReadiness();
  };
  const enterTvConsoleMode=()=>{
    stage?.classList.add("tv-console-mode");
    if(customPad && padRoot && !padVisible()) {
      padRoot.classList.add("cast-console-show");
      castConsoleAutoPad=true;
    }
    updatePlaybackReadiness();
    showNotice(config.lang === "en" ? "TV is showing the game. This device is now the console controller." : "TV đang hiển thị game. Thiết bị này hiện là tay cầm console.");
  };
  const stopCastPreview=()=>{
    leaveTvConsoleMode();
    const stream=castPreview?.srcObject;
    if(stream?.getTracks) stream.getTracks().forEach(track=>track.stop());
    castPreview?.remove();
    castPreview=null;
    releaseTvDiscovery();
    queueTvDiscovery();
  };
  const queueTvDiscovery=()=>{
    if(!castButton || castPreview || castDiscoveryVideo || castDiscoveryFrame) return;
    if(!("remote" in HTMLVideoElement.prototype)) { setCastState("idle");return; }
    castDiscoveryFrame=requestAnimationFrame(()=>{
      castDiscoveryFrame=0;
      if(castPreview || castDiscoveryVideo) return;
      const canvas=document.querySelector("#game canvas");
      if(!canvas?.captureStream) { setCastState("idle");return; }
      const video=document.createElement("video");
      video.muted=true;
      video.playsInline=true;
      video.className="an3-cast-preview";
      video.srcObject=canvas.captureStream(1);
      document.body.appendChild(video);
      castDiscoveryVideo=video;
      if(typeof video.remote?.watchAvailability !== "function") { setCastState("idle");return; }
      setCastState("searching");
      video.remote.watchAvailability(available=>setCastState(available ? "available" : "idle")).then(watchId=>{
        if(castDiscoveryVideo===video) castAvailabilityWatch=watchId;
        else try { video.remote.cancelWatchAvailability(watchId); } catch (_) {}
      }).catch(()=>setCastState("idle"));
    });
  };
  const castGameToTv=async()=>{
    try {
      const canvas=document.querySelector("#game canvas");
      if(!canvas?.captureStream) throw new Error(config.lang === "en" ? "The current game canvas cannot be cast by this browser." : "Trình duyệt này không thể phát canvas game hiện tại.");
      if(!("remote" in HTMLVideoElement.prototype)) throw new Error(config.lang === "en" ? "No TV receiver is available here. Use your browser's Cast tab command instead." : "Trình duyệt chưa có bộ nhận TV. Hãy dùng lệnh Phát tab (Cast tab) của trình duyệt.");
      releaseTvDiscovery();
      stopCastPreview();
      const video=document.createElement("video");
      video.className="an3-cast-preview";
      video.muted=true;
      video.playsInline=true;
      video.srcObject=canvas.captureStream(60);
      document.body.appendChild(video);
      castPreview=video;
      await video.play();
      if(typeof video.remote?.prompt !== "function") throw new Error(config.lang === "en" ? "No TV receiver is available here. Use your browser's Cast tab command instead." : "Trình duyệt chưa có bộ nhận TV. Hãy dùng lệnh Phát tab (Cast tab) của trình duyệt.");
      video.remote.addEventListener("connect",()=>{enterTvConsoleMode();setCastState("connected");},{once:true});
      video.remote.addEventListener("disconnect",stopCastPreview,{once:true});
      setCastState("connecting",{disabled:true});
      await video.remote.prompt();
      castButton && (castButton.disabled=false);
      if(video.remote.state === "connected") { enterTvConsoleMode();setCastState("connected"); }
      else { setCastState("idle");showNotice(config.lang === "en" ? "Choose a TV in your browser's receiver list." : "Hãy chọn TV trong danh sách bộ nhận của trình duyệt."); }
    } catch(error) { stopCastPreview();showNotice(error.message || String(error),true); }
  };
  castButton?.addEventListener("click",castGameToTv);
  addEventListener("pagehide",()=>{if(castDiscoveryFrame)cancelAnimationFrame(castDiscoveryFrame);stopCastPreview();},{once:true});

  if (config.mode === "html5") {
    document.querySelector(".custom-frame")?.addEventListener("load", finishLoading);
    document.getElementById("playerControls")?.remove();
    setProgress(50, config.lang === "en" ? "Loading game" : "Đang tải game");
    return;
  }

  const customPad = ["gba", "gb", "nds", "3ds"].includes(config.system);
  const touchFirst = Boolean(!window.matchMedia?.("(hover:hover)")?.matches && (window.matchMedia?.("(pointer:coarse)")?.matches || navigator.maxTouchPoints > 0));
  const touchVariant = ndsPad ? new URLSearchParams(location.search).get("touch") || "geometry-mapped" : "baseline";
  const isolatedNdsMovement = ["geometry-only","geometry-mapped"].includes(touchVariant);
  const ndsDebugEnabled = ndsPad && config.ndsDebugAllowed === true && new URLSearchParams(location.search).get("ndsdebug") === "1";
  document.documentElement.classList.toggle("custom-pad", customPad);
  stage.classList.toggle("nds-stage", ndsPad);
  stage.classList.toggle("three-ds-stage", threeDsPad);
  const syncDualScreenStage=()=>stage?.classList.toggle("dual-screen-landscape",(ndsPad || threeDsPad) && innerWidth>innerHeight);
  syncDualScreenStage();
  let appliedNdsScreenLayout=dualScreenLayout();
  let appliedThreeDsScreenLayout=dualScreenLayout();

  const NDS_DEBUG_LIMIT = 160;
  const ndsDebugEvents = [];
  let ndsDebugSequence = 0;
  const describeNdsDebugNode = node => {
    if (!node?.nodeName) return null;
    const id=node.id ? `#${node.id}` : "";
    const classes=typeof node.className === "string" && node.className.trim() ? `.${node.className.trim().split(/\s+/).join(".")}` : "";
    return `${node.nodeName.toLowerCase()}${id}${classes}`;
  };
  const ndsDebugPoint = event => {
    const touch=[...(event?.touches||[]),...(event?.changedTouches||[])][0];
    return touch || event;
  };
  const finiteNdsDebugValue = value => Number.isFinite(value) ? Number(value) : null;
  let ndsDebugGeometryCache = new WeakMap();
  let ndsDebugGeometryResetPending = false;
  const ndsDebugGeometry = canvas => {
    if (!canvas) return null;
    const now=performance.now(),cached=ndsDebugGeometryCache.get(canvas);
    if (cached && now-cached.recordedAt<20) return cached;
    const source=canvas.getBoundingClientRect();
    const geometry={
      recordedAt:now,
      rect:{left:source.left,top:source.top,right:source.right,bottom:source.bottom,width:source.width,height:source.height},
      backingWidth:canvas.width||source.width||0,
      backingHeight:canvas.height||source.height||0
    };
    ndsDebugGeometryCache.set(canvas,geometry);
    if (!ndsDebugGeometryResetPending) {
      ndsDebugGeometryResetPending=true;
      requestAnimationFrame(()=>{ndsDebugGeometryCache=new WeakMap();ndsDebugGeometryResetPending=false;});
    }
    return geometry;
  };
  const configuredNdsDebugCore = () => window.EJS_defaultOptions?.retroarch_core || primaryCores[config.system] || null;
  const runtimeNdsDebugCore = () => window.EJS_emulator?.gameManager?.core || window.EJS_emulator?.core || null;
  const recordNdsDebugEvent = (event, canvas, gameRoot) => {
    if (!ndsDebugEnabled) return;
    const point=ndsDebugPoint(event),geometry=ndsDebugGeometry(canvas),rect=geometry?.rect;
    const clientX=finiteNdsDebugValue(point?.clientX),clientY=finiteNdsDebugValue(point?.clientY);
    const backingWidth=geometry?.backingWidth ?? null;
    const backingHeight=geometry?.backingHeight ?? null;
    const cssX=rect && clientX!==null ? Math.max(0,Math.min(rect.width,clientX-rect.left)) : null;
    const cssY=rect && clientY!==null ? Math.max(0,Math.min(rect.height,clientY-rect.top)) : null;
    const mappedX=rect?.width && cssX!==null ? cssX*backingWidth/rect.width : null;
    const mappedY=rect?.height && cssY!==null ? cssY*backingHeight/rect.height : null;
    const pointerId=finiteNdsDebugValue(event?.pointerId);
    const captureOwner=pointerId===null ? null : [canvas,gameRoot].find(node=>{
      try { return Boolean(node?.hasPointerCapture?.(pointerId)); } catch (_) { return false; }
    });
    const type=event?.type || "unknown";
    const viewportOrientation=innerWidth>innerHeight ? "landscape" : "portrait";
    const entry={
      sequence:++ndsDebugSequence,
      timestampMs:Date.now(),
      phase:event?.isTrusted ? "native" : "forwarded",
      eventType:type,
      isTrusted:Boolean(event?.isTrusted),
      pointerType:event?.pointerType || (type.startsWith("touch") ? "touch" : (type.startsWith("mouse") || type === "click" ? "mouse" : null)),
      clientX,
      clientY,
      pageX:finiteNdsDebugValue(point?.pageX),
      pageY:finiteNdsDebugValue(point?.pageY),
      movementX:finiteNdsDebugValue(event?.movementX),
      movementY:finiteNdsDebugValue(event?.movementY),
      buttons:finiteNdsDebugValue(event?.buttons),
      pressure:finiteNdsDebugValue(event?.pressure),
      target:describeNdsDebugNode(event?.target),
      composedPath:(event?.composedPath?.() || []).slice(0,12).map(describeNdsDebugNode).filter(Boolean),
      pointerId,
      touchesLength:event?.touches?.length ?? 0,
      targetTouchesLength:event?.targetTouches?.length ?? 0,
      changedTouchesLength:event?.changedTouches?.length ?? 0,
      pointerCaptureOwner:describeNdsDebugNode(captureOwner),
      defaultPreventedAtCapture:Boolean(event?.defaultPrevented),
      canvas:describeNdsDebugNode(canvas),
      canvasRect:rect || null,
      canvasBackingWidth:backingWidth,
      canvasBackingHeight:backingHeight,
      canvasCssWidth:rect?.width ?? null,
      canvasCssHeight:rect?.height ?? null,
      devicePixelRatio:window.devicePixelRatio || 1,
      cssX,
      cssY,
      mappedX,
      mappedY,
      normalizedX:backingWidth && mappedX!==null ? mappedX/backingWidth : null,
      normalizedY:backingHeight && mappedY!==null ? mappedY/backingHeight : null,
      orientation:viewportOrientation,
      viewportOrientation,
      screenOrientation:screen.orientation?.type || null,
      screenOrientationAngle:finiteNdsDebugValue(screen.orientation?.angle),
      fullscreen:Boolean(document.fullscreenElement),
      fullscreenElement:describeNdsDebugNode(document.fullscreenElement),
      touchVariant,
      activeCore:configuredNdsDebugCore(),
      configuredCore:configuredNdsDebugCore(),
      runtimeCore:runtimeNdsDebugCore(),
      activeSystem:window.EJS_core || emulatorSystem
    };
    ndsDebugEvents.push(entry);
    if (ndsDebugEvents.length>NDS_DEBUG_LIMIT) ndsDebugEvents.splice(0,ndsDebugEvents.length-NDS_DEBUG_LIMIT);
  };
  const ndsDebugSnapshot = () => JSON.parse(JSON.stringify({
    schema:"an3-nds-touch-debug-v1",
    generatedAt:new Date().toISOString(),
    url:location.href,
    touchVariant,
    activeCore:configuredNdsDebugCore(),
    configuredCore:configuredNdsDebugCore(),
    runtimeCore:runtimeNdsDebugCore(),
    eventLimit:NDS_DEBUG_LIMIT,
    eventCount:ndsDebugEvents.length,
    events:ndsDebugEvents
  }));
  const bindNdsDebug = gameRoot => {
    if (!ndsDebugEnabled || gameRoot.dataset.an3NdsDebug === "1") return;
    gameRoot.dataset.an3NdsDebug="1";
    const activeTouchIds=new Set(),activePointerIds=new Set();
    const observe=event=>{
      const path=event.composedPath?.() || [];
      const inside=path.includes(gameRoot) || Boolean(event.target?.nodeType && gameRoot.contains(event.target));
      const changedTouchIds=[...(event.changedTouches||[])].map(touch=>touch.identifier);
      const allTouchIds=[...(event.touches||[]),...(event.changedTouches||[])].map(touch=>touch.identifier);
      const pointerId=finiteNdsDebugValue(event.pointerId);
      if (event.type === "touchstart" && inside) changedTouchIds.forEach(id=>activeTouchIds.add(id));
      if (event.type === "pointerdown" && inside && pointerId!==null) activePointerIds.add(pointerId);
      const trackedTouch=allTouchIds.some(id=>activeTouchIds.has(id));
      const trackedPointer=pointerId!==null && activePointerIds.has(pointerId);
      if (!inside && !trackedTouch && !trackedPointer) return;
      const protectedUi=globalThis.AN3NdsTouchBridge?.isProtectedUiTarget?.(gameRoot,event.target,path);
      if (protectedUi) return;
      const hit=path.find(node=>node?.nodeName === "CANVAS") || event.target?.closest?.("#game canvas") || null;
      const canvas=globalThis.AN3NdsTouchBridge?.resolveSourceCanvas?.(gameRoot,hit,path) || gameRoot.querySelector("#game canvas:not(.an3-render-canvas)");
      recordNdsDebugEvent(event,canvas,gameRoot);
      if (["touchend","touchcancel"].includes(event.type)) changedTouchIds.forEach(id=>activeTouchIds.delete(id));
      if (["pointerup","pointercancel"].includes(event.type) && pointerId!==null) activePointerIds.delete(pointerId);
    };
    ["pointerdown","pointermove","pointerup","pointercancel","touchstart","touchmove","touchend","touchcancel","mousedown","mousemove","mouseup","click","gotpointercapture","lostpointercapture"].forEach(type=>{
      document.addEventListener(type,observe,{capture:true,passive:true});
    });
    const exportJSON=()=>{
      const json=JSON.stringify(ndsDebugSnapshot(),null,2);
      const url=URL.createObjectURL(new Blob([json],{type:"application/json"}));
      const anchor=document.createElement("a");
      anchor.href=url;
      anchor.download=`an3-nds-touch-${Date.now()}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(()=>URL.revokeObjectURL(url),2000);
      return json;
    };
    window.AN3NdsDebug=Object.freeze({snapshot:ndsDebugSnapshot,clear:()=>{ndsDebugEvents.length=0;},exportJSON});
  };

  const ndsViewportCache = new WeakMap();
  let ndsMappedCursor = {x:0,y:0};
  const resolveNdsVideoViewport = (canvas, rect) => {
    const backingWidth=canvas.width||rect.width,backingHeight=canvas.height||rect.height;
    const cached=ndsViewportCache.get(canvas);
    if (cached && cached.rectWidth===rect.width && cached.rectHeight===rect.height && cached.backingWidth===backingWidth && cached.backingHeight===backingHeight) return cached;
    const manager=window.EJS_emulator?.gameManager;
    const fallbackDimensions=appliedNdsScreenLayout === "Left/Right" ? {width:512,height:192} : {width:256,height:384};
    const videoWidth=Number(manager?.getVideoDimensions?.("width"))||fallbackDimensions.width;
    const videoHeight=Number(manager?.getVideoDimensions?.("height"))||fallbackDimensions.height;
    let left=0,top=0,width=0,height=0;
    try {
      const gl=canvas.getContext("webgl2")||canvas.getContext("webgl");
      const raw=gl?.getParameter(gl.VIEWPORT);
      const viewportInBounds=raw?.[0]>=0 && raw?.[1]>=0 && raw?.[2]>0 && raw?.[3]>0 &&
        raw[0]+raw[2]<=backingWidth && raw[1]+raw[3]<=backingHeight;
      if (viewportInBounds && backingWidth>0 && backingHeight>0) {
        const scaleX=rect.width/backingWidth,scaleY=rect.height/backingHeight;
        left=raw[0]*scaleX;
        top=rect.height-(raw[1]+raw[3])*scaleY;
        width=raw[2]*scaleX;
        height=raw[3]*scaleY;
      }
    } catch (_) {}
    if (!(width>0 && height>0)) {
      const scale=Math.min(rect.width/videoWidth,rect.height/videoHeight)||1;
      width=videoWidth*scale;
      height=videoHeight*scale;
      left=(rect.width-width)/2;
      top=innerWidth<=innerHeight ? 0 : (rect.height-height)/2;
    }
    const viewport={rectWidth:rect.width,rectHeight:rect.height,backingWidth,backingHeight,left,top,width,height,videoWidth,videoHeight};
    ndsViewportCache.set(canvas,viewport);
    return viewport;
  };
  const mapNdsCursor = (canvas, rect, source) => {
    const viewport=resolveNdsVideoViewport(canvas,rect);
    return globalThis.AN3NdsTouchBridge?.mapPoint?.({
      clientX:source.clientX,
      clientY:source.clientY,
      viewport:{left:rect.left+viewport.left,top:rect.top+viewport.top,width:viewport.width,height:viewport.height},
      layout:appliedNdsScreenLayout
    }) || null;
  };
  const recordNdsDebugAction = (action, {source, canvas, mapped=null, accepted=true, reason=null, family=null, state=null, bridgePrevented=false, releaseState=null}={}) => {
    if (!ndsDebugEnabled) return;
    const point=source || state?.lastTouch || null;
    ndsDebugEvents.push({
      sequence:++ndsDebugSequence,
      timestampMs:Date.now(),
      phase:"logical",
      action,
      eventFamily:family || (point?.identifier !== undefined ? "touch" : "pointer"),
      pointerId:point?.identifier ?? point?.pointerId ?? null,
      mappedX:mapped?.x ?? state?.mapped?.x ?? null,
      mappedY:mapped?.y ?? state?.mapped?.y ?? null,
      sourceCanvas:describeNdsDebugNode(canvas),
      accepted:Boolean(accepted),
      ignoreReason:accepted ? null : reason,
      duplicateSuppressionReason:reason === "active-gesture" || reason === "non-owner-touch" ? reason : null,
      durationMs:state?.startedAt ? Math.max(0,Math.round(performance.now()-state.startedAt)) : null,
      moveCount:state?.moveCount ?? 0,
      pressedState:action === "logical-down" ? true : action === "logical-up" || action === "logical-cancel" ? false : null,
      bridgePrevented:Boolean(bridgePrevented),
      releaseState:releaseState || state?.releaseState || null
    });
    if (ndsDebugEvents.length>NDS_DEBUG_LIMIT) ndsDebugEvents.splice(0,ndsDebugEvents.length-NDS_DEBUG_LIMIT);
  };
  const dispatchNdsMouse = (canvas, type, source, buttons) => {
    const rect=canvas.getBoundingClientRect(),width=canvas.width||rect.width,height=canvas.height||rect.height;
    const cssX=Math.max(0,Math.min(rect.width,source.clientX-rect.left)),cssY=Math.max(0,Math.min(rect.height,source.clientY-rect.top));
    const offsetX=rect.width ? cssX*width/rect.width : 0,offsetY=rect.height ? cssY*height/rect.height : 0;
    const pointKey=isolatedNdsMovement ? "__an3NdsLastMousePoint" : "__an3NdsLastPoint";
    const previous=canvas[pointKey];
    let movementX=previous ? cssX-previous.x : 0,movementY=previous ? cssY-previous.y : 0;
    if (touchVariant === "geometry-mapped") {
      if (type === "mousedown") ndsViewportCache.delete(canvas);
      const mapped=mapNdsCursor(canvas,rect,source);
      if (!mapped && type !== "mouseup") return false;
      if (mapped) {
        movementX=mapped.x-ndsMappedCursor.x;
        movementY=mapped.y-ndsMappedCursor.y;
        ndsMappedCursor=mapped;
      } else {
        // A captured gesture can end outside the DS touchscreen. Always send
        // the release so the core cannot retain a stuck touch button.
        movementX=0;
        movementY=0;
      }
    }
    canvas[pointKey]=type === "mouseup" ? null : {x:cssX,y:cssY};
    const event=new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:source.clientX,clientY:source.clientY,screenX:source.screenX||source.clientX,screenY:source.screenY||source.clientY,button:0,buttons});
    // EmulatorJS reads local canvas coordinates. Synthetic MouseEvents otherwise
    // expose offsetX/offsetY as 0, which traps the DS pointer in the top-left.
    for (const [name,value] of [["offsetX",offsetX],["offsetY",offsetY],["layerX",offsetX],["layerY",offsetY]]) {
      try { Object.defineProperty(event,name,{value,writable:false,enumerable:true}); } catch (_) {}
    }
    // EmulatorJS uses pointerType to distinguish a real desktop mouse from a
    // touchscreen.  This compatibility MouseEvent is one half of the proven
    // geometry-mapped input contract, not a desktop-menu gesture.
    try { Object.defineProperty(event,"pointerType",{value:"touch",writable:false,enumerable:true}); } catch (_) {}
    if (["delta","geometry-only","geometry-mapped"].includes(touchVariant)) for (const [name,value] of [["movementX",movementX],["movementY",movementY]]) {
      try { Object.defineProperty(event,name,{value,writable:false,enumerable:true}); } catch (_) {}
    }
    canvas.dispatchEvent(event);
    recordNdsDebugAction(`synthetic-${type}`,{source,canvas,mapped:touchVariant === "geometry-mapped" ? mapNdsCursor(canvas,rect,source) : null,family:"mouse",releaseState:type === "mouseup" ? "released" : null});
    return true;
  };
  const dispatchNdsPointer = (canvas, type, source, buttons) => {
    const rect=canvas.getBoundingClientRect(),width=canvas.width||rect.width,height=canvas.height||rect.height;
    const cssX=Math.max(0,Math.min(rect.width,source.clientX-rect.left)),cssY=Math.max(0,Math.min(rect.height,source.clientY-rect.top));
    const offsetX=rect.width ? cssX*width/rect.width : 0,offsetY=rect.height ? cssY*height/rect.height : 0;
    const pointKey=isolatedNdsMovement ? "__an3NdsLastPointerPoint" : "__an3NdsLastPoint";
    const previous=canvas[pointKey];
    const movementX=previous ? cssX-previous.x : 0,movementY=previous ? cssY-previous.y : 0;
    canvas[pointKey]=type === "pointerup" || type === "pointercancel" ? null : {x:cssX,y:cssY};
    const event=new PointerEvent(type,{bubbles:true,cancelable:true,view:window,clientX:source.clientX,clientY:source.clientY,screenX:source.screenX||source.clientX,screenY:source.screenY||source.clientY,button:0,buttons,pointerId:source.identifier ?? source.pointerId ?? 1,pointerType:"touch",isPrimary:true,width:1,height:1,pressure:buttons?0.5:0});
    for (const [name,value] of [["offsetX",offsetX],["offsetY",offsetY],["layerX",offsetX],["layerY",offsetY],["movementX",movementX],["movementY",movementY]]) {
      try { Object.defineProperty(event,name,{value,writable:false,enumerable:true}); } catch (_) {}
    }
    canvas.dispatchEvent(event);
    recordNdsDebugAction(`synthetic-${type}`,{source,canvas,family:"pointer"});
    return true;
  };
  const dispatchNdsEvent = (canvas, type, source, buttons) => {
    if (touchVariant === "pointer-touch") return dispatchNdsPointer(canvas, `pointer${type.slice(5)}`, source, buttons);
    if (["hybrid","hybrid-root","geometry-only","geometry-mapped"].includes(touchVariant)) {
      dispatchNdsPointer(canvas, `pointer${type.slice(5)}`, source, buttons);
      // The root touch lifecycle uses this result to decide whether it owns
      // the physical finger.  Returning the mapped mouse result is essential:
      // an accepted zero-move touchstart must become a logical press rather
      // than being discarded before its matching touchend can release it.
      return dispatchNdsMouse(canvas, type, source, buttons);
    }
    return dispatchNdsMouse(canvas, type, source, buttons);
  };
  const shieldSyntheticNdsMouseFromMenu = canvas => {
    if (!canvas || canvas.dataset.an3NdsSyntheticMouseShield === "1") return;
    canvas.dataset.an3NdsSyntheticMouseShield="1";
    // The EmulatorJS core listens on its source canvas, while its desktop menu
    // observer listens on the parent. Let the historical compatibility mouse
    // events reach the core, but prevent a synthetic touch move from bubbling
    // into that desktop-only observer and cancelling the logical gesture.
    const shield=event=>{
      if (!event.isTrusted && event.pointerType === "touch") event.stopPropagation();
    };
    ["mousedown","mousemove","mouseup"].forEach(type=>canvas.addEventListener(type,shield,false));
  };
  const bindNdsTouch = canvas => {
    if (!ndsPad || canvas.dataset.an3NdsTouch === "1") return;
    canvas.dataset.an3NdsTouch="1";
    if (["native","root","root-touch","overlay","hybrid-root","geometry-only","geometry-mapped"].includes(touchVariant)) return;
    const touchNoPrevent=touchVariant === "touch-passive";
    const pointerNoCapture=touchVariant === "pointer-no-capture";
    if ("PointerEvent" in window && !["touch","touch-passive","pointer-touch","hybrid"].includes(touchVariant)) {
      let pointerId=null;
      canvas.addEventListener("pointerdown",event=>{if(event.pointerType!=="touch" || pointerId!==null)return;pointerId=event.pointerId;if(!pointerNoCapture)event.preventDefault();canvas.focus?.({preventScroll:true});try{if(!pointerNoCapture)canvas.setPointerCapture(pointerId);}catch(_){}dispatchNdsMouse(canvas,"mousedown",event,1);},true);
      canvas.addEventListener("pointermove",event=>{if(event.pointerType!=="touch" || event.pointerId!==pointerId)return;if(!pointerNoCapture)event.preventDefault();dispatchNdsMouse(canvas,"mousemove",event,1);},true);
      const release=event=>{if(event.pointerType!=="touch" || event.pointerId!==pointerId)return;if(!pointerNoCapture)event.preventDefault();dispatchNdsMouse(canvas,"mouseup",event,0);try{if(!pointerNoCapture)canvas.releasePointerCapture(pointerId);}catch(_){}pointerId=null;};
      canvas.addEventListener("pointerup",release,true);canvas.addEventListener("pointercancel",release,true);
    } else {
      let touchId=null;
      const findTouch=event=>[...(event.touches||[]),...(event.changedTouches||[])].find(touch=>touch.identifier===touchId);
      canvas.addEventListener("touchstart",event=>{if(touchId!==null || !event.changedTouches?.length)return;const touch=event.changedTouches[0];touchId=touch.identifier;if(!touchNoPrevent)event.preventDefault();dispatchNdsEvent(canvas,"mousedown",touch,1);},{capture:true,passive:false});
      const move=event=>{const touch=findTouch(event);if(!touch)return;if(!touchNoPrevent)event.preventDefault();dispatchNdsEvent(canvas,"mousemove",touch,1);};
      const release=event=>{const touch=findTouch(event);if(!touch)return;if(!touchNoPrevent)event.preventDefault();dispatchNdsEvent(canvas,"mouseup",touch,0);touchId=null;};
      // Track movement on document: Android can retarget a touch after the
      // finger leaves the canvas even though the gesture is still active.
      document.addEventListener("touchmove",move,{capture:true,passive:false});
      document.addEventListener("touchend",release,{capture:true,passive:false});
      document.addEventListener("touchcancel",release,{capture:true,passive:false});
    }
  };
  let releaseRootNdsTouch=()=>{};
  const bindRootNdsTouch = gameRoot => {
    if (!["root","root-touch","overlay","hybrid-root","core-touch","geometry-only","geometry-mapped"].includes(touchVariant) || gameRoot.dataset.an3RootTouch === "1") return;
    gameRoot.dataset.an3RootTouch="1";
    let active=null;
    const isTouch=event=>event.pointerType === "touch" || event.pointerType === "";
    const isProtectedUiEvent=event=>Boolean(globalThis.AN3NdsTouchBridge?.isProtectedUiTarget?.(gameRoot,event.target,event.composedPath?.()));
    const resolveCanvas=event=>{
      if (isProtectedUiEvent(event)) return null;
      const hit=document.elementFromPoint(event.clientX,event.clientY);
      return globalThis.AN3NdsTouchBridge?.resolveSourceCanvas?.(gameRoot,hit,event.composedPath?.()) || null;
    };
    addEventListener("blur",()=>releaseRootNdsTouch("window-blur"),{capture:true});
    document.addEventListener("visibilitychange",()=>{if(document.hidden)releaseRootNdsTouch("document-hidden");},{capture:true});
    document.addEventListener("fullscreenchange",()=>releaseRootNdsTouch("fullscreen-change"),{capture:true});
    if (["root-touch","hybrid-root","geometry-only","geometry-mapped"].includes(touchVariant) || touchVariant === "core-touch") {
      const tapRelease=globalThis.AN3NdsTouchBridge?.createTapReleaseLatch?.();
      const sendRelease=state=>{
        state.releaseState="released";
        dispatchNdsEvent(state.canvas,"mouseup",state.lastTouch,0);
      };
      const owner=globalThis.AN3NdsTouchBridge?.createTouchGestureOwner?.({
        begin:touch=>{tapRelease?.flush?.();const canvas=resolveCanvas(touch),mapped=canvas ? mapNdsCursor(canvas,canvas.getBoundingClientRect(),touch) : null;return canvas && mapped && dispatchNdsEvent(canvas,"mousedown",touch,1) ? {canvas,lastTouch:touch,mapped,startedAt:performance.now(),moveCount:0,releaseState:"pressed"} : null;},
        move:(touch,state)=>{state.lastTouch=touch;state.mapped=mapNdsCursor(state.canvas,state.canvas.getBoundingClientRect(),touch) || state.mapped;state.moveCount+=1;dispatchNdsEvent(state.canvas,"mousemove",touch,1);},
        end:(touch,state,cancelled)=>{state.lastTouch=touch||state.lastTouch;if(cancelled || state.moveCount>0 || !tapRelease){sendRelease(state);return;}state.releaseState="latched-next-input-frame";tapRelease.defer(state,()=>sendRelease(state));}
      });
      const activeTouchId=()=>owner?.active?.()?.id ?? null;
      const findTouch=event=>[...(event.touches||[]),...(event.changedTouches||[])].find(touch=>touch.identifier===activeTouchId());
      const release=(releaseReason="forced-release")=>{const result=owner?.release?.();const flushed=tapRelease?.flush?.();if(result)recordNdsDebugAction(result.reason,{canvas:result.state?.canvas,accepted:result.accepted,reason:releaseReason,state:result.state,family:"touch",releaseState:flushed ? "released" : null});return result;};
      releaseRootNdsTouch=release;
      const start=event=>{if(!owner||!event.changedTouches?.length||isProtectedUiEvent(event))return;const touch=event.changedTouches[0],result=owner.start(touch);if(result.accepted)event.preventDefault();recordNdsDebugAction(result.reason,{source:touch,canvas:result.state?.canvas,accepted:result.accepted,reason:result.reason,state:result.state,family:"touch",bridgePrevented:result.accepted});};
      const move=event=>{if(isProtectedUiEvent(event))return;const touch=findTouch(event);if(!touch)return;const result=owner.move(touch);if(result.accepted)event.preventDefault();recordNdsDebugAction(result.reason,{source:touch,canvas:result.state?.canvas,accepted:result.accepted,reason:result.reason,state:result.state,family:"touch",bridgePrevented:result.accepted});};
      const end=event=>{if(isProtectedUiEvent(event))return;const touch=findTouch(event);if(!touch)return;const result=owner.end(touch,event.type==="touchcancel");if(result.accepted)event.preventDefault();recordNdsDebugAction(result.reason,{source:touch,canvas:result.state?.canvas,accepted:result.accepted,reason:result.reason,state:result.state,family:"touch",bridgePrevented:result.accepted});};
      gameRoot.addEventListener("touchstart",start,{capture:true,passive:false});
      document.addEventListener("touchmove",move,{capture:true,passive:false});
      document.addEventListener("touchend",end,{capture:true,passive:false});
      document.addEventListener("touchcancel",end,{capture:true,passive:false});
      return;
    }
    const release=event=>{if(!active)return;const current=event || active.lastEvent;dispatchNdsMouse(active.canvas,"mouseup",current,0);try{gameRoot.releasePointerCapture(active.id);}catch(_){}active=null;};
    releaseRootNdsTouch=()=>release();
    gameRoot.addEventListener("pointerdown",event=>{if(!isTouch(event)||active||isProtectedUiEvent(event))return;const canvas=resolveCanvas(event);if(!canvas || !dispatchNdsMouse(canvas,"mousedown",event,1))return;active={id:event.pointerId,canvas,lastEvent:event};event.preventDefault();canvas.focus?.({preventScroll:true});try{gameRoot.setPointerCapture(event.pointerId);}catch(_){}},true);
    gameRoot.addEventListener("pointermove",event=>{if(!isTouch(event)||!active||event.pointerId!==active.id||isProtectedUiEvent(event))return;active.lastEvent=event;event.preventDefault();dispatchNdsMouse(active.canvas,"mousemove",event,1);},true);
    const pointerRelease=event=>{if(!isTouch(event)||!active||event.pointerId!==active.id||isProtectedUiEvent(event))return;event.preventDefault();release(event);};
    gameRoot.addEventListener("pointerup",pointerRelease,true);gameRoot.addEventListener("pointercancel",pointerRelease,true);
  };
  const protectNdsCanvas = () => {
    if (!ndsPad) return;
    document.querySelectorAll("#game canvas:not(.an3-render-canvas)").forEach(canvas=>{
      if (canvas.classList.contains("ejs-canvas-no-pointer")) canvas.classList.remove("ejs-canvas-no-pointer");
      canvas.style.setProperty("pointer-events","auto","important");
      canvas.style.setProperty("touch-action","none","important");
      shieldSyntheticNdsMouseFromMenu(canvas);
      bindNdsTouch(canvas);
    });
  };
  const bindThreeDsTouch = canvas => {
    if (!threeDsPad || canvas.dataset.an3ThreeDsTouch === "1") return;
    canvas.dataset.an3ThreeDsTouch="1";
    if ("PointerEvent" in window) {
      let pointerId=null;
      canvas.addEventListener("pointerdown",event=>{
        if(event.pointerType!=="touch" || pointerId!==null)return;
        pointerId=event.pointerId;event.preventDefault();canvas.focus?.({preventScroll:true});
        try{canvas.setPointerCapture(pointerId);}catch(_){}
        dispatchNdsMouse(canvas,"mousedown",event,1);
      },true);
      canvas.addEventListener("pointermove",event=>{
        if(event.pointerType!=="touch" || event.pointerId!==pointerId)return;
        event.preventDefault();dispatchNdsMouse(canvas,"mousemove",event,1);
      },true);
      const release=event=>{
        if(event.pointerType!=="touch" || event.pointerId!==pointerId)return;
        event.preventDefault();dispatchNdsMouse(canvas,"mouseup",event,0);
        try{canvas.releasePointerCapture(pointerId);}catch(_){}
        pointerId=null;
      };
      canvas.addEventListener("pointerup",release,true);canvas.addEventListener("pointercancel",release,true);
      return;
    }
    let touchId=null;
    const findTouch=event=>[...(event.touches||[]),...(event.changedTouches||[])].find(touch=>touch.identifier===touchId);
    canvas.addEventListener("touchstart",event=>{
      if(touchId!==null || !event.changedTouches?.length)return;
      const touch=event.changedTouches[0];touchId=touch.identifier;event.preventDefault();dispatchNdsMouse(canvas,"mousedown",touch,1);
    },{capture:true,passive:false});
    const move=event=>{const touch=findTouch(event);if(!touch)return;event.preventDefault();dispatchNdsMouse(canvas,"mousemove",touch,1);};
    const release=event=>{const touch=findTouch(event);if(!touch)return;event.preventDefault();dispatchNdsMouse(canvas,"mouseup",touch,0);touchId=null;};
    document.addEventListener("touchmove",move,{capture:true,passive:false});
    document.addEventListener("touchend",release,{capture:true,passive:false});
    document.addEventListener("touchcancel",release,{capture:true,passive:false});
  };
  const protectThreeDsCanvas = () => {
    if (!threeDsPad) return;
    document.querySelectorAll("#game canvas:not(.an3-render-canvas)").forEach(canvas=>{
      if (canvas.classList.contains("ejs-canvas-no-pointer")) canvas.classList.remove("ejs-canvas-no-pointer");
      canvas.style.setProperty("pointer-events","auto","important");
      canvas.style.setProperty("touch-action","none","important");
      bindThreeDsTouch(canvas);
    });
  };
  let emulatorMenuFrame=0;
  let emulatorMenuTimer=0;
  const customPadUsesEmulatorMenuLayer=ndsPad || threeDsPad;
  const emulatorMenuSelector=".ejs_menu_bar,.ejs_popup_body,.ejs_context_menu";
  const visibleEmulatorMenu = element => {
    const style=getComputedStyle(element),rect=element.getBoundingClientRect();
    return !element.classList.contains("ejs_menu_bar_hidden") && style.display!=="none" && style.visibility!=="hidden" && Number(style.opacity)>0 && rect.width>0 && rect.height>0;
  };
  const syncEmulatorMenuLayer = () => {
    emulatorMenuFrame=0;
    if (!customPadUsesEmulatorMenuLayer) return;
    const gameRoot=document.getElementById("game");
    const menuOpen=Boolean(gameRoot && [...gameRoot.querySelectorAll(emulatorMenuSelector)].some(visibleEmulatorMenu));
    if (menuOpen) releaseRootNdsTouch("emulator-menu-open");
    stage?.classList.toggle("emulator-menu-open",menuOpen);
  };
  const scheduleEmulatorMenuLayer = () => {
    if (!customPadUsesEmulatorMenuLayer || emulatorMenuFrame) return;
    emulatorMenuFrame=requestAnimationFrame(syncEmulatorMenuLayer);
  };
  const queueEmulatorMenuLayer = () => {
    scheduleEmulatorMenuLayer();
    clearTimeout(emulatorMenuTimer);
    emulatorMenuTimer=setTimeout(syncEmulatorMenuLayer,250);
  };
  const mutationTouchesEmulatorMenu = mutation => {
    if (mutation.target?.closest?.(emulatorMenuSelector)) return true;
    return [...mutation.addedNodes,...mutation.removedNodes].some(node=>node.nodeType===1 && (node.matches?.(emulatorMenuSelector) || node.querySelector?.(emulatorMenuSelector)));
  };
  const gameRoot=document.getElementById("game");
  // Core boot mutates several wrapper classes in a burst.  Coalesce those
  // mutations into one canvas query per animation frame so the touch bridge
  // never competes with the emulator's render loop.
  let canvasProtectionFrame=0;
  const queueCanvasProtection=()=>{
    if(canvasProtectionFrame) return;
    canvasProtectionFrame=requestAnimationFrame(()=>{
      canvasProtectionFrame=0;
      protectNdsCanvas();
      protectThreeDsCanvas();
    });
  };
  addEventListener("pagehide",()=>{if(canvasProtectionFrame)cancelAnimationFrame(canvasProtectionFrame);canvasProtectionFrame=0;},{once:true});
  if (ndsPad) {
    bindNdsDebug(gameRoot);
    new MutationObserver(queueCanvasProtection).observe(gameRoot,{subtree:true,childList:true,attributes:true,attributeFilter:["class"]});
    queueCanvasProtection();
    bindRootNdsTouch(gameRoot);
  }
  if (threeDsPad) {
    new MutationObserver(queueCanvasProtection).observe(gameRoot,{subtree:true,childList:true,attributes:true,attributeFilter:["class"]});
    queueCanvasProtection();
  }
  if (customPadUsesEmulatorMenuLayer) {
    new MutationObserver(mutations=>{if(mutations.some(mutationTouchesEmulatorMenu))queueEmulatorMenuLayer();}).observe(gameRoot,{subtree:true,childList:true,attributes:true,attributeFilter:["class","style"]});
    syncEmulatorMenuLayer();
    document.addEventListener("click",event=>{if(event.target?.closest?.("#game .ejs_menu_bar,#game .ejs_popup_body,#game .ejs_context_menu"))queueEmulatorMenuLayer();},true);
  }

  async function fetchGame() {
    if (config.offlineId) {
      debugMilestone("ROM_REQUEST_START", {path:"offline-library", method:"indexeddb"});
      setProgress(18, config.lang === "en" ? "Opening local game" : "Đang mở game trên máy");
      const file = await window.AN3OfflineLibrary?.getFile?.(config.offlineId);
      if (!file) throw new Error(config.lang === "en" ? "Local game file is unavailable" : "Không tìm thấy game ngoại tuyến trên máy này");
      debugMilestone("ROM_DOWNLOAD_COMPLETE", {path:"offline-library", bytes:file.size || null});
      return file;
    }
    if (!config.romUrl) throw new Error(config.lang === "en" ? "Game URL is unavailable" : "Không tìm thấy đường dẫn game");
    debugMilestone("ROM_REQUEST_START", {path:safeDebugUrl(config.romUrl), method:"GET"});
    setProgress(18, config.lang === "en" ? "Starting game stream" : "Đang mở luồng game");
    debugMilestone("ROM_HEADERS_RECEIVED", {path:safeDebugUrl(config.romUrl), note:"EmulatorJS owns the streaming body"});
    return config.romUrl;
  }

  let gameStarted = false;
  let threeDsGateStarted = false;
  const threeDsAudioContext = () => {
    const candidates = [window.EJS_emulator?.audioContext, window.EJS_emulator?.audio?.context, window.EJS_audioContext];
    return candidates.find(context => context && typeof context.state === "string") || null;
  };
  const waitForThreeDsPlayable = () => {
    if (!threeDsPad || threeDsGateStarted) return;
    threeDsGateStarted = true;
    let attempts = 0;
    let sourceCanvasSeen = false;
    let firstFrameSeen = false;
    let audioSeen = false;
    const check = () => {
      const canvas = document.querySelector("#game canvas");
      if (canvas && !sourceCanvasSeen) {
        sourceCanvasSeen = true;
        debugMilestone("SOURCE_CANVAS_AVAILABLE", {width:canvas.width || 0, height:canvas.height || 0});
      }
      const frame = playerSession?.core?.frameNumber?.();
      if (sourceCanvasSeen && Number.isFinite(frame) && frame > 0 && !firstFrameSeen) {
        firstFrameSeen = true;
        debugMilestone("FIRST_VIDEO_FRAME", {frame});
      }
      const audioContext = threeDsAudioContext();
      if (audioContext?.state === "running" && !audioSeen) {
        audioSeen = true;
        debugMilestone("AUDIO_STARTED", {state:audioContext.state});
      }
      if (sourceCanvasSeen && firstFrameSeen && audioSeen) {
        debugMilestone("THREAD_POOL_READY", {isolated:Boolean(window.crossOriginIsolated)});
        finishLoading();
        return;
      }
      attempts += 1;
      if (attempts > 1200) {
        failLoading(new Error(config.lang === "en"
          ? "3DS did not reach a verified source canvas, first frame, and running audio output."
          : "3DS chưa đạt đủ canvas nguồn, frame đầu tiên và audio đang chạy để xác nhận."));
        return;
      }
      requestAnimationFrame(check);
    };
    check();
  };
  async function boot() {
    try {
      const capabilityError=coreCapabilityError();
      if (capabilityError) throw new Error(capabilityError);
      const file = await fetchGame();
      setProgress(86, config.lang === "en" ? "Loading emulator" : "Đang tải giả lập");
      window.EJS_player = "#game";
      window.EJS_core = emulatorSystem;
      // EmulatorJS exposes the FPS HUD and frame pacing as native settings.
      // VSync is deliberately off by default so the core is not made to wait
      // for the shell compositor; players can still re-enable it in the
      // EmulatorJS menu. NDS and 3DS use a clean per-launch core config: NDS
      // needs a fixed touchscreen geometry, and 3DS must not inherit a stale
      // Direct Keyboard Input choice that prevents the core's physical-key
      // handler from receiving events.
      window.EJS_defaultOptions = {
        fps:"show",
        vsync:"disabled",
        ...(threeDsPad ? {
          // Azahar's libretro core names this option citra_layout_option.
          // Set it before boot so the core's touchscreen mapping follows the
          // Side by Side framebuffer on wide screens.
          citra_layout_option:dualScreenLayout()==="Left/Right"?"side_by_side":"default",
          // Azahar declares useKeyboard=true. Explicitly retain that native
          // default after clearing stale EmulatorJS settings for 3DS.
          keyboardInput:"enabled"
        } : {}),
        ...(ndsPad ? {
          retroarch_core:"melonds",
          // melonDS exposes a real Left/Right core layout.  Choose it before
          // boot on wide displays, preserving Top/Bottom in portrait without
          // rotating or intercepting either DS touchscreen.
          melonds_screen_layout:dualScreenLayout(),
          // melonDS libretro accepts "16-bit" (not a numeric value). This
          // preserves the requested audio precision and avoids the old
          // automatic 10-bit DS default.
          melonds_audio_bitrate:"16-bit",
          ...(touchVariant === "core-touch" ? {melonds_touch_mode:"Touch"} : {})
        } : {})
      };
      window.EJS_disableLocalStorage = ndsPad || threeDsPad;
      window.EJS_gameName = config.slug;
      window.EJS_gameID = config.netplayGameId || config.slug;
      window.EJS_netplayServer = config.netplayServer || undefined;
      window.EJS_netplayICEServers = config.netplayServer ? [] : undefined;
      window.EJS_gameUrl = file;
      const configuredOrigin=typeof config.emulatorOrigin === "string" ? config.emulatorOrigin.trim().replace(/\/+$/, "") : "";
      window.EJS_pathtodata = configuredOrigin ? `${configuredOrigin}/${config.channel}/${config.system === "3ds" ? "data-v2" : "data"}/` : `/emulatorjs/${config.channel}/${config.system === "3ds" ? "data-v2" : "data"}/`;
      const localizationRoot = configuredOrigin ? `${configuredOrigin}/stable/data/` : "/emulatorjs/stable/data/";
      const emulatorLanguage = config.lang === "en" ? "en-US" : "vi-VN";
      window.EJS_paths = {[emulatorLanguage]:`${localizationRoot}localization/${emulatorLanguage}.json`};
      window.EJS_startOnLoaded = true;
      window.EJS_controlScheme = config.system;
      window.EJS_language = emulatorLanguage;
      window.EJS_disableDatabases = false;
      window.EJS_fixedSaveInterval = 60000;
      window.EJS_browserMode = customPad ? 2 : undefined;
      window.EJS_noAutoFocus = ndsPad && touchFirst;
      window.EJS_mouseLock = false;
      window.EJS_threads = threadedCore;
      window.EJS_forceLegacyCores = performancePlan.forceLegacyNds;
      window.EJS_hideSettings = ["fastForward","ff-ratio","slowMotion","sm-ratio"];
      window.EJS_onGameStart = () => {
        gameStarted = true;
        protectNdsCanvas();
        protectThreeDsCanvas();
        applySpeed(1);
        syncSpeedControls();
        syncAutoSaveTimer();
        debugMilestone("CORE_LOAD_GAME_SUCCESS", {system:config.system});
        if (threeDsPad) waitForThreeDsPlayable();
        else finishLoading();
      };
      const script = document.createElement("script");
      script.src = `${window.EJS_pathtodata}loader.js`;
      script.onload = () => {
        debugMilestone("EJS_LOADER_READY", {path:safeDebugUrl(script.src)});
        debugMilestone("WASM_COMPILE_START", {source:"EmulatorJS loader"});
        setProgress(92, config.lang === "en" ? "Starting core" : "Đang khởi động core");
      };
      script.onerror = () => failLoading(new Error(globalThis.AN3NativeOfflineApp === true
        ? (config.lang === "en" ? "The bundled emulator files are unavailable. Reinstall the verified VibeCodedEmulator app." : "Không tìm thấy tệp giả lập đã đóng gói. Hãy cài lại bản VibeCodedEmulator đã kiểm tra.")
        : (config.lang === "en" ? "Emulator files are unavailable. Connect once and preload this core." : "Không tải được tệp giả lập. Hãy kết nối mạng và tải trước core này.")));
      debugMilestone("CORE_LOAD_GAME_START", {system:config.system});
      document.body.appendChild(script);
      let checks = 0;
      bootstrapReadyTimer = setInterval(() => {
        protectNdsCanvas();protectThreeDsCanvas();
        if (gameStarted) clearBootstrapTimers();
        else if (window.EJS_emulator?.failedToStart) {
          const fallback=threeDsPad ? (config.lang === "en" ? "The 3DS core failed to start." : "Core 3DS khởi động thất bại.") : (ndsPad ? (config.lang === "en" ? "The NDS core failed to start." : "Core NDS khởi động thất bại.") : (config.lang === "en" ? "The emulator failed to start." : "Core giả lập khởi động thất bại."));
          failLoading(new Error(window.EJS_emulator?.textElem?.innerText || fallback));
        }
        else if (!ndsPad && window.EJS_emulator?.gameManager) { gameStarted=true;applySpeed(1);syncSpeedControls();syncAutoSaveTimer();finishLoading(); }
        else if (++checks > 720) { failLoading(new Error(ndsPad ? (config.lang === "en" ? "The NDS game did not start after 3 minutes." : "Game NDS chưa khởi động sau 3 phút.") : (config.lang === "en" ? "The emulator did not start." : "Giả lập chưa khởi động."))); }
      }, 250);
      if (customPad) {
        virtualPadGuardTimer = setInterval(() => {
          document.querySelectorAll(".ejs_virtualGamepad_parent,.ejs_virtualGamepad_open").forEach(element => element.style.setProperty("display", "none", "important"));
          protectNdsCanvas();protectThreeDsCanvas();
          try { window.EJS_emulator?.toggleVirtualGamepad?.(false); } catch (_) {}
          if (gameStarted) clearBootstrapTimers();
        }, 250);
      }
    } catch (error) { failLoading(error); }
  }

  document.getElementById("saveState")?.addEventListener("click", () => {
    try {
      const state = playerSession?.saveStateManager.exportBytes() || window.EJS_emulator?.gameManager?.getState();
      if (!state?.byteLength) throw new Error("Save state is not ready");
      const url = URL.createObjectURL(new Blob([state], {type: "application/octet-stream"}));
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = `${config.slug}-${new Date().toISOString().replace(/[:.]/g,"-")}.state`;
      anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 2000);
      showNotice(config.lang === "en" ? "Save state downloaded" : "Đã tải save state");
    } catch (error) { showNotice(error.message || String(error), true); }
  });
  document.getElementById("loadState")?.addEventListener("click", () => document.getElementById("stateFile").click());
  document.getElementById("stateFile")?.addEventListener("change", async event => {
    try {
      const file = event.target.files[0];
      if (!file) return;
      const bytes = new Uint8Array(await file.arrayBuffer());
      if (playerSession) playerSession.saveStateManager.importBytes(bytes);
      else {
        const manager = window.EJS_emulator?.gameManager;
        if (!manager) throw new Error(config.lang === "en" ? "Emulator is not ready" : "Giả lập chưa sẵn sàng");
        manager.loadState(bytes);
      }
      event.target.value = "";
      showNotice(config.lang === "en" ? "Save state loaded" : "Đã nạp save state");
    } catch (error) { showNotice(error.message || String(error), true); }
  });

  const slotPanel = document.getElementById("slotPanel");
  const quickSaves = playerSession?.quickSaveManager;
  const requireQuickSaves = () => {
    if (!quickSaves) throw new Error(config.lang === "en" ? "Save slot runtime is unavailable" : "Không thể mở runtime save slot");
    return quickSaves;
  };
  const slotGet = slot => requireQuickSaves().get(slot);
  const slotGetMany = slots => requireQuickSaves().getMany(slots);
  const slotStamp = time => new Intl.DateTimeFormat(config.lang === "en" ? "en-GB" : "vi-VN", {dateStyle:"short", timeStyle:"short"}).format(new Date(time));
  const refreshSlots = async () => {
    if (!slotPanel) return;
    const rows=[...slotPanel.querySelectorAll("[data-slot]")];
    const states = await slotGetMany(rows.map(row=>Number(row.dataset.slot))).then(states => {
      rows.forEach((row,index) => {
        const state=states[index];
      row.querySelector("small").textContent = state ? slotStamp(state.updatedAt) : (config.lang === "en" ? "Empty" : "Trống");
      row.querySelector("[data-load-slot]").disabled = !state;
      });
      return states;
    }).catch(error => { showNotice(error.message || String(error), true); return []; });
    const latest = states.filter(Boolean).sort((a,b) => b.updatedAt-a.updatedAt)[0];
    if (saveStatus) saveStatus.textContent = latest ? (config.lang === "en" ? "Saved on this device" : "Đã lưu trên thiết bị") : (config.lang === "en" ? "No save on this device" : "Chưa có save trên thiết bị");
  };
  const saveSlot = async slot => {
    const state = playerSession?.saveStateManager.exportBytes() || window.EJS_emulator?.gameManager?.getState();
    if (!state?.byteLength) throw new Error(config.lang === "en" ? "Save state is not ready" : "Save state chưa sẵn sàng");
    const bytes = state instanceof Uint8Array ? state : new Uint8Array(state);
    await requireQuickSaves().put(slot, bytes, Date.now());
    await refreshSlots();
    showNotice(config.lang === "en" ? `Saved to slot ${slot}` : `Đã lưu vào slot ${slot}`);
  };
  const loadSlot = async slot => {
    const saved = await slotGet(slot);
    if (!saved?.state) throw new Error(config.lang === "en" ? "Save slot is unavailable" : "Save slot chưa sẵn sàng");
    const bytes = new Uint8Array(await saved.state.arrayBuffer());
    if (playerSession) playerSession.saveStateManager.importBytes(bytes);
    else window.EJS_emulator?.gameManager?.loadState?.(bytes);
    showNotice(config.lang === "en" ? `Loaded slot ${slot}` : `Đã nạp slot ${slot}`);
  };
  document.getElementById("slotMenu")?.addEventListener("click", () => {
    if (!slotPanel) return;
    panel?.classList.remove("open");
    document.getElementById("playerControls")?.setAttribute("aria-expanded","false");
    slotPanel.hidden = !slotPanel.hidden;
    document.getElementById("slotMenu")?.setAttribute("aria-expanded", String(!slotPanel.hidden));
    if (!slotPanel.hidden) { refreshSlots();refreshAutoSlot();document.getElementById("closeSlots")?.focus(); }
  });
  document.getElementById("closeSlots")?.addEventListener("click", () => { if (slotPanel) slotPanel.hidden = true;const trigger=document.getElementById("slotMenu");trigger?.setAttribute("aria-expanded","false");trigger?.focus(); });
  slotPanel?.querySelectorAll("[data-save-slot]").forEach(button => button.addEventListener("click", () => saveSlot(Number(button.dataset.saveSlot)).catch(error => showNotice(error.message || String(error), true))));
  slotPanel?.querySelectorAll("[data-load-slot]").forEach(button => button.addEventListener("click", () => loadSlot(Number(button.dataset.loadSlot)).catch(error => showNotice(error.message || String(error), true))));
  refreshSlots();

  // ---- Autosave + Exit Game (Phase A) -------------------------------------
  // Autosave preference is per device and validated on read so a hand-edited
  // localStorage value can never enable an unknown cadence.
  const AUTOSAVE_KEY="vibe-autosave-v1";
  const AUTOSAVE_MODES=["off","exit","30","10","5"];
  const readAutosaveMode=()=>{try{const value=localStorage.getItem(AUTOSAVE_KEY);return AUTOSAVE_MODES.includes(value)?value:"off";}catch(_){return "off";}};
  const writeAutosaveMode=mode=>{try{localStorage.setItem(AUTOSAVE_KEY,AUTOSAVE_MODES.includes(mode)?mode:"off");}catch(_){}};
  let autosaveMode=readAutosaveMode();
  let autosaveTimer=0;
  let lastAutosaveDigest=null;
  const readStateBytes=()=>{
    const state=playerSession?.saveStateManager.exportBytes()||window.EJS_emulator?.gameManager?.getState?.();
    if(!state?.byteLength)return null;
    return state instanceof Uint8Array?state:new Uint8Array(state);
  };
  const digestBytes=async bytes=>{
    try{
      if(globalThis.crypto?.subtle?.digest){
        const hash=await crypto.subtle.digest("SHA-256",bytes);
        return [...new Uint8Array(hash)].map(byte=>byte.toString(16).padStart(2,"0")).join("");
      }
    }catch(_){}
    // Bounded fallback: length plus byte samples, never a full O(n) scan.
    let hash=bytes.length>>>0;
    const step=Math.max(1,Math.floor(bytes.length/256));
    for(let index=0;index<bytes.length;index+=step)hash=(hash*31+bytes[index])>>>0;
    return `s${bytes.length}:${hash.toString(16)}`;
  };
  const runAutosave=async()=>{
    const bytes=readStateBytes();
    if(!bytes)return false;
    const digest=await digestBytes(bytes);
    // Nothing changed since the last autosave: skip the write entirely so the
    // emulator thread and IndexedDB are not touched needlessly.
    if(digest===lastAutosaveDigest)return false;
    await requireQuickSaves().putAuto(bytes,Date.now(),digest);
    lastAutosaveDigest=digest;
    if(saveStatus)saveStatus.textContent=config.lang==="en"?"Autosaved on this device":"Đã tự động lưu trên thiết bị";
    return true;
  };
  function syncAutoSaveTimer(){
    if(autosaveTimer){clearInterval(autosaveTimer);autosaveTimer=0;}
    if(!gameStarted||!/^(30|10|5)$/.test(autosaveMode))return;
    autosaveTimer=setInterval(()=>{runAutosave().catch(()=>{});},Number(autosaveMode)*1000);
  }
  function exitGame(){
    const back=document.querySelector(".player-back")?.getAttribute("href")||"/";
    const finish=()=>{window.location.href=back;};
    if(autosaveMode!=="off"){
      // Bounded best-effort final autosave; Exit never hangs on storage.
      Promise.race([runAutosave().catch(()=>false),new Promise(resolve=>setTimeout(resolve,1500))]).then(finish,finish);
    }else finish();
  }
  const refreshAutoSlot=async()=>{
    const row=document.querySelector("[data-auto-slot]");
    if(!row)return;
    try{
      const saved=await requireQuickSaves().getAuto();
      row.querySelector("small").textContent=saved?slotStamp(saved.updatedAt):(config.lang==="en"?"Empty":"Trống");
      const loadButton=row.querySelector("[data-load-auto]");
      if(loadButton)loadButton.disabled=!saved;
    }catch(_){}
  };
  const autosaveSelect=document.getElementById("autosaveMode");
  if(autosaveSelect){
    autosaveSelect.value=autosaveMode;
    autosaveSelect.addEventListener("change",()=>{
      autosaveMode=AUTOSAVE_MODES.includes(autosaveSelect.value)?autosaveSelect.value:"off";
      writeAutosaveMode(autosaveMode);
      syncAutoSaveTimer();
    });
  }
  document.querySelector("[data-save-auto]")?.addEventListener("click",()=>{
    runAutosave().then(changed=>showNotice(changed?(config.lang==="en"?"Autosave saved":"Đã lưu autosave"):(config.lang==="en"?"Autosave is already current":"Autosave đã là bản mới nhất"))).then(refreshAutoSlot).catch(error=>showNotice(error.message||String(error),true));
  });
  document.querySelector("[data-load-auto]")?.addEventListener("click",async()=>{
    try{
      const saved=await requireQuickSaves().getAuto();
      if(!saved?.state)throw new Error(config.lang==="en"?"Autosave is unavailable":"Autosave chưa sẵn sàng");
      const bytes=new Uint8Array(await saved.state.arrayBuffer());
      if(playerSession)playerSession.saveStateManager.importBytes(bytes);
      else window.EJS_emulator?.gameManager?.loadState?.(bytes);
      showNotice(config.lang==="en"?"Autosave loaded":"Đã nạp autosave");
    }catch(error){showNotice(error.message||String(error),true);}
  });
  document.getElementById("exitGame")?.addEventListener("click",exitGame);
  document.querySelector(".player-back")?.addEventListener("click",event=>{event.preventDefault();exitGame();});
  // Last-chance flush for tab close/navigation while an autosave mode is on.
  document.addEventListener("pagehide",()=>{if(autosaveMode!=="off")runAutosave().catch(()=>{});});
  refreshAutoSlot();
  // ------------------------------------------------------------------------

  const profileLabel = profile => {
    const labels=config.lang === "en" ? {auto:"Use recommended settings",low:"Low-end / Battery",balanced:"Balanced",quality:"Quality",custom:"Custom"} : {auto:"Dùng cài đặt khuyến nghị",low:"Máy yếu / Tiết kiệm pin",balanced:"Cân bằng",quality:"Chất lượng",custom:"Tùy chỉnh"};
    return labels[profile] || labels.balanced;
  };
  const profileHint = profile => {
    const isLow=profile === "low";
    const isCustom=profile === "custom";
    if (config.lang === "en") {
      if (isLow && ndsPad) return "Uses melonDS compatibility rendering on the next launch. No image scaling or frame skipping is applied.";
      if (isCustom && ndsPad) return "Choose the NDS renderer override below. It applies on the next launch.";
      if (profile === "quality") return "No unverified shader is enabled. This profile keeps the core’s native renderer default.";
      return "The selected renderer applies when the player restarts. Your choice is stored only on this device.";
    }
    if (isLow && ndsPad) return "Dùng trình dựng tương thích của melonDS ở lần mở tiếp theo. Không giảm độ phân giải hoặc bỏ khung hình.";
    if (isCustom && ndsPad) return "Chọn trình dựng NDS bên dưới. Thay đổi có hiệu lực khi mở lại.";
    if (profile === "quality") return "Không bật shader chưa được xác minh. Hồ sơ này giữ trình dựng mặc định của core.";
    return "Trình dựng được chọn có hiệu lực khi mở lại player. Lựa chọn chỉ lưu trên thiết bị này.";
  };
  const syncPerformanceControls = () => {
    const selected=performanceSettings.selectedProfile;
    const effective=selected === "auto" ? recommendedProfile : selected;
    document.querySelectorAll('input[name="performanceProfile"]').forEach(input=>{input.checked=input.value===selected;});
    const recommendation=document.getElementById("recommendedPerformanceProfile");
    if (recommendation) recommendation.textContent=profileLabel(recommendedProfile);
    const current=document.getElementById("performanceRecommendation");
    if (current) current.textContent=config.lang === "en" ? `Current: ${profileLabel(performancePlan.activeProfile)}` : `Đang dùng: ${profileLabel(performancePlan.activeProfile)}`;
    const custom=document.getElementById("performanceCustomOptions");
    const renderer=document.getElementById("performanceRenderer");
    if (renderer) renderer.value=performanceSettings.customOverrides.ndsRenderer;
    if (custom) custom.hidden=selected !== "custom" || !renderer;
    const hint=document.getElementById("performanceProfileHint");
    if (hint) hint.textContent=profileHint(effective);
  };
  document.querySelectorAll('input[name="performanceProfile"]').forEach(input=>input.addEventListener("change",event=>{
    performanceSettings.selectedProfile=normalizeProfileId(event.currentTarget.value);
    savePerformanceSettings();
    syncPerformanceControls();
  }));
  document.getElementById("performanceRenderer")?.addEventListener("change",event=>{
    performanceSettings.customOverrides.ndsRenderer=event.currentTarget.value === "legacy" ? "legacy" : "native";
    savePerformanceSettings();
    syncPerformanceControls();
  });
  document.getElementById("useRecommended")?.addEventListener("click",()=>{
    performanceSettings.selectedProfile="auto";
    performanceSettings.customOverrides.ndsRenderer="native";
    savePerformanceSettings();
    syncPerformanceControls();
  });
  document.getElementById("applyPerformanceProfile")?.addEventListener("click",()=>{
    savePerformanceSettings();
    location.reload();
  });
  syncPerformanceControls();

  const speedSteps=Object.freeze([.5,1,1.5,2]);
  let selectedSpeed=1;
  const speedLabel = value => `${value}×`;
  const speedManager = () => {
    const manager=window.EJS_emulator?.gameManager;
    const required=["setFastForwardRatio","toggleFastForward","setSlowMotionRatio","toggleSlowMotion"];
    return gameStarted && manager && required.every(method=>typeof manager[method] === "function") ? manager : null;
  };
  const syncSpeedControls = () => {
    const manager=speedManager();
    const index=speedSteps.indexOf(selectedSpeed);
    const down=document.getElementById("speedDown"),up=document.getElementById("speedUp"),value=document.getElementById("speedValue"),hint=document.getElementById("speedHint");
    if (value) value.textContent=speedLabel(selectedSpeed);
    if (down) down.disabled=!manager || index<=0;
    if (up) up.disabled=!manager || index>=speedSteps.length-1;
    if (hint) hint.textContent=manager ? (config.lang === "en" ? "Session only. Returning to 1× turns off fast-forward and slow motion." : "Chỉ trong phiên chơi này. Trở về 1× sẽ tắt tua nhanh và quay chậm.") : (config.lang === "en" ? "Speed controls become available after the game starts." : "Điều chỉnh tốc độ hoạt động sau khi game khởi động.");
  };
  const applySpeed = nextSpeed => {
    const manager=speedManager();
    if (!manager) return syncSpeedControls();
    const value=speedSteps.includes(nextSpeed) ? nextSpeed : 1;
    try {
      if (value===1) {
        manager.toggleFastForward(0);
        manager.toggleSlowMotion(0);
      } else if (value>1) {
        manager.toggleSlowMotion(0);
        manager.setFastForwardRatio(value);
        manager.toggleFastForward(1);
      } else {
        manager.toggleFastForward(0);
        manager.setSlowMotionRatio(1/value);
        manager.toggleSlowMotion(1);
      }
      selectedSpeed=value;
    } catch (error) {
      try { manager.toggleFastForward(0);manager.toggleSlowMotion(0); } catch (_) {}
      selectedSpeed=1;
      showNotice(error.message || String(error),true);
    }
    syncSpeedControls();
  };
  const shiftSpeed = direction => {
    const index=speedSteps.indexOf(selectedSpeed);
    applySpeed(speedSteps[Math.max(0,Math.min(speedSteps.length-1,index+direction))]);
  };
  document.getElementById("speedDown")?.addEventListener("click",()=>shiftSpeed(-1));
  document.getElementById("speedUp")?.addEventListener("click",()=>shiftSpeed(1));
  syncSpeedControls();

  const padRoot = document.getElementById("tvPad");
  const panel = document.getElementById("padPanel");
  const hints = document.getElementById("playerHints");
  const showHints = () => {
    if (!hints) return;
    hints.classList.add("show");
    clearTimeout(showHints.timer);
    showHints.timer = setTimeout(() => hints.classList.remove("show"), 3000);
  };
  const defaults = {
    portrait:{dpad:{x:19,y:79},a:{x:86,y:73},b:{x:73,y:82},x:{x:89,y:60},y:{x:74,y:63},l:{x:15,y:52},r:{x:85,y:52},start:{x:39,y:61},select:{x:62,y:61}},
    landscape:{dpad:{x:13,y:69},a:{x:92,y:57},b:{x:82,y:73},x:{x:92,y:42},y:{x:81,y:44},l:{x:13,y:33},r:{x:87,y:33},start:{x:39,y:84},select:{x:61,y:84}}
  };
  const ndsDefaults = {
    portrait:{dpad:{x:23.4,y:81.6},a:{x:89,y:80},b:{x:78.2,y:89.7},x:{x:78,y:70.2},y:{x:67.3,y:79.9},l:{x:8.1,y:63.3},r:{x:91.2,y:62.5},start:{x:47.4,y:62.1},select:{x:57.9,y:62}},
    landscape:{dpad:{x:13,y:69},a:{x:90,y:65},b:{x:80,y:76},x:{x:90,y:38},y:{x:80,y:50},l:{x:13,y:18},r:{x:87,y:18},start:{x:40,y:90},select:{x:60,y:90}}
  };
  // 3DS originally inherited the GBA geometry. On a narrow portrait stage
  // several controls overlapped the four-pixel safety gap, which made a valid
  // drag impossible to finish. Keep the proven GBA layout intact and give 3DS
  // a separate, fully non-overlapping portrait placement.
  const threeDsDefaults = {
    portrait:{dpad:{x:19,y:79},a:{x:87,y:78.5},b:{x:73,y:88.5},x:{x:89,y:55},y:{x:74,y:69},l:{x:15,y:52},r:{x:85,y:45},start:{x:39,y:61},select:{x:62,y:61}},
    landscape:{...defaults.landscape,r:{x:87,y:20}}
  };
  const padDefaults = ndsPad ? ndsDefaults : threeDsPad ? threeDsDefaults : defaults;
  let orientation = innerWidth > innerHeight ? "landscape" : "portrait";
  // Version the NDS/3DS keys rather than deleting a user's former layout.
  // Previous records remain in local storage as recovery references.
  const key = () => `an3-pad-v${ndsPad ? 5 : threeDsPad ? 7 : 3}:${config.system}:${orientation}`;
  const clamp = (value,min,max) => Math.max(min,Math.min(max,value));
  const isRecord = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);
  const read = (name, fallback={}) => { try { const value=JSON.parse(localStorage.getItem(name));return isRecord(value) ? value : fallback; } catch (_) { return fallback; } };
  let positions = {...padDefaults[orientation], ...read(key())};
  const settingsVersion = ndsPad ? 4 : 2;
  const settingsKey = ndsPad ? "an3-pad-settings-v4:nds" : threeDsPad ? "an3-pad-settings-v1:3ds" : "an3-pad-settings-v2";
  const defaultSettings = ndsPad ? {version:4,globalScale:1,opacity:.48,visibilityMode:"auto",buttonScales:{}} : {version:2,globalScale:1,opacity:.82,visible:true,buttonScales:{}};
  defaultSettings.directionalControl = threeDsPad ? "joystick" : "dpad";
  const legacyDefaults = ndsPad ? {scale:1,opacity:.48,visibilityMode:"auto",sizes:{dpad:1.4,start:.7,select:.7}} : {scale:1,opacity:.82,visible:true,sizes:{}};
  const controlIds=["dpad","a","b","x","y","l","r","start","select"];
  const baseControlScale = id => ndsPad ? ({dpad:1.4,start:.7,select:.7}[id] || 1) : 1;
  const normalizeLegacyVisibility = source => {
    const result={...source};
    if (ndsPad && result.visible===false && !["auto","shown","hidden"].includes(result.visibilityMode)) result.visibilityMode="hidden";
    if (ndsPad) delete result.visible;
    return result;
  };
  const mergeLegacySettings = (...sources) => sources.reduce((result,source)=>{
    if (!isRecord(source)) return result;
    return {...result,...normalizeLegacyVisibility(source),sizes:{...(result.sizes || {}),...(isRecord(source.sizes) ? source.sizes : {})}};
  },{});
  const legacySettings = ndsPad ? mergeLegacySettings(read("an3-pad-settings-v2:nds"),read("an3-pad-settings-v3:nds")) : mergeLegacySettings(read("an3-pad-settings-v1"));
  const hasLegacySettings = Object.keys(legacySettings).some(name=>name!=="sizes" || Object.keys(legacySettings.sizes || {}).length);
  const normalizeButtonScale = value => clamp(Number(value) || 1,.5,2);
  const normalizeSettings = source => {
    const buttons=isRecord(source.buttonScales) ? source.buttonScales : {};
    const result={...defaultSettings,globalScale:clamp(Number(source.globalScale) || 1,.7,1),opacity:clamp(Number(source.opacity) || defaultSettings.opacity,.3,1),buttonScales:{}};
    result.directionalControl = ["dpad", "joystick"].includes(source.directionalControl) ? source.directionalControl : defaultSettings.directionalControl;
    if (ndsPad) result.visibilityMode=["auto","shown","hidden"].includes(source.visibilityMode) ? source.visibilityMode : "auto";
    else result.visible=source.visible!==false;
    controlIds.forEach(id=>{
      const scale=normalizeButtonScale(buttons[id]);
      if (scale!==1) result.buttonScales[id]=scale;
    });
    return result;
  };
  const migrateSettings = source => {
    const old={...legacyDefaults,...source,sizes:{...legacyDefaults.sizes,...(isRecord(source.sizes) ? source.sizes : {})}};
    const result={...defaultSettings,opacity:clamp(Number(old.opacity) || defaultSettings.opacity,.3,1),buttonScales:{}};
    if (ndsPad) result.visibilityMode=["auto","shown","hidden"].includes(old.visibilityMode) ? old.visibilityMode : "auto";
    else result.visible=old.visible!==false;
    controlIds.forEach(id=>{
      const oldScale=clamp(Number(old.sizes[id] ?? old.scale) || 1,.7,1.4);
      const scale=normalizeButtonScale(oldScale/baseControlScale(id));
      if (scale!==1) result.buttonScales[id]=scale;
    });
    return result;
  };
  const storedSettings = read(settingsKey);
  const hasCurrentSettings = Number(storedSettings.version) === settingsVersion;
  const settings = hasCurrentSettings ? normalizeSettings(storedSettings) : migrateSettings(legacySettings);
  const globalScale = () => clamp(Number(settings.globalScale) || 1,.7,1);
  const buttonScale = id => normalizeButtonScale(settings.buttonScales[id]);
  const controlScale = id => globalScale()*baseControlScale(id)*buttonScale(id);
  const saveLayout = () => { try { localStorage.setItem(key(),JSON.stringify(positions)); } catch (_) {} };
  const saveSettings = () => { try { localStorage.setItem(settingsKey,JSON.stringify(settings)); } catch (_) {} };
  if (!hasCurrentSettings && hasLegacySettings) saveSettings();
  const input = (index,value) => {
    if (playerSession) playerSession.inputRouter.setVirtualButton(index, value);
    else { try { window.EJS_emulator?.gameManager?.simulateInput(0,index,value); } catch (_) {} }
  };
  const analogInput = (x,y) => {
    if (playerSession) playerSession.inputRouter.setVirtualAxis(x,y);
    else for (const [index,value] of [[16,x],[17,-x],[18,y],[19,-y]]) {
      try { window.EJS_emulator?.gameManager?.simulateInput(0,index,Math.round(Math.max(0,Math.min(1,value))*32767)); } catch (_) {}
    }
    if (!threeDsPad) for (const [index,pressed] of [[4,y<-.35],[5,y>.35],[6,x<-.35],[7,x>.35]]) input(index,pressed?1:0);
  };
  let releaseStick = () => {};
  const PAD_EDGE_GAP=4;
  const PAD_CONTROL_GAP=4;
  const controlBounds = element => {
    const root=padRoot?.getBoundingClientRect(),control=element.getBoundingClientRect();
    if (!root?.width || !root?.height || !control?.width || !control?.height) return null;
    const halfWidth=Math.min(root.width/2,(control.width/2)+PAD_EDGE_GAP),halfHeight=Math.min(root.height/2,(control.height/2)+PAD_EDGE_GAP);
    return {minX:halfWidth/root.width*100,maxX:100-halfWidth/root.width*100,minY:halfHeight/root.height*100,maxY:100-halfHeight/root.height*100};
  };
  const constrainedPosition = (element,point) => {
    const bounds=controlBounds(element);
    return bounds ? {x:clamp(point.x,bounds.minX,bounds.maxX),y:clamp(point.y,bounds.minY,bounds.maxY)} : point;
  };
  const place = element => {
    const point=constrainedPosition(element,positions[element.dataset.id]);
    element.style.left=`${point.x}%`;element.style.top=`${point.y}%`;
  };
  const renderedControlScale = element => {
    const value=Number(element.style.getPropertyValue("--control-scale"));
    return Number.isFinite(value) && value>0 ? value : controlScale(element.dataset.id);
  };
  const predictedControlRect = (element, multiplier=buttonScale(element.dataset.id), options={}) => {
    const root=padRoot?.getBoundingClientRect(),current=renderedControlScale(element),measured=element.getBoundingClientRect();
    if (!root?.width || !root?.height || !current || !measured.width || !measured.height) return null;
    const requestedGlobal=clamp(Number(options.globalScale) || globalScale(),.7,1);
    const effective=requestedGlobal*baseControlScale(element.dataset.id)*normalizeButtonScale(multiplier);
    const width=measured.width/current*effective,height=measured.height/current*effective;
    const halfWidth=width/2+PAD_EDGE_GAP,halfHeight=height/2+PAD_EDGE_GAP;
    if (root.width<halfWidth*2 || root.height<halfHeight*2) return null;
    const point=(options.positions || positions)[element.dataset.id];
    if (!point) return null;
    const x=clamp(point.x,halfWidth/root.width*100,100-halfWidth/root.width*100);
    const y=clamp(point.y,halfHeight/root.height*100,100-halfHeight/root.height*100);
    const centerX=root.left+root.width*x/100,centerY=root.top+root.height*y/100;
    return {left:centerX-width/2,top:centerY-height/2,right:centerX+width/2,bottom:centerY+height/2};
  };
  const rectsConflict = (first,second) => first.left<second.right+PAD_CONTROL_GAP && first.right+PAD_CONTROL_GAP>second.left && first.top<second.bottom+PAD_CONTROL_GAP && first.bottom+PAD_CONTROL_GAP>second.top;
  const inspectButtonScales = (overrides={}, options={}) => {
    const controls=Array.from(padRoot.querySelectorAll(".tvCtrl"));
    const rects=[];
    for (const control of controls) {
      const id=control.dataset.id;
      const multiplier=Object.prototype.hasOwnProperty.call(overrides,id) ? overrides[id] : buttonScale(id);
      const rect=predictedControlRect(control,multiplier,options);
      if (!rect) return {safe:false,reason:padRoot?.getBoundingClientRect().width ? "fit" : "hidden"};
      rects.push({id,rect});
    }
    for (let index=0;index<rects.length;index+=1) for (let other=index+1;other<rects.length;other+=1) {
      if (rectsConflict(rects[index].rect,rects[other].rect)) return {safe:false,reason:"overlap"};
    }
    return {safe:true};
  };
  const inspectButtonScale = (id, multiplier, options={}) => inspectButtonScales({[id]:multiplier},options);
  const inspectCurrentButtonScales = options => inspectButtonScales({},options);
  const bindInput = (element,index) => element.addEventListener("pointerdown",event => {
    if (padRoot.classList.contains("edit")) return;
    event.preventDefault(); try{element.setPointerCapture(event.pointerId)}catch(_){}
    element.closest(".tvCtrl").classList.add("pressed"); input(index,1);
    const up=()=>{input(index,0);element.closest(".tvCtrl").classList.remove("pressed");["pointerup","pointercancel","lostpointercapture"].forEach(name=>element.removeEventListener(name,up));};
    ["pointerup","pointercancel","lostpointercapture"].forEach(name=>element.addEventListener(name,up));
  });
  const bindDrag = element => element.addEventListener("pointerdown",event => {
    if (!padRoot.classList.contains("edit")) return;
    event.preventDefault(); try{element.setPointerCapture(event.pointerId)}catch(_){}
    const move=e=>{const rect=padRoot.getBoundingClientRect(),bounds=controlBounds(element);if(!rect.width||!rect.height)return;positions[element.dataset.id]={x:Math.round(clamp((e.clientX-rect.left)/rect.width*100,bounds?.minX ?? 0,bounds?.maxX ?? 100)*10)/10,y:Math.round(clamp((e.clientY-rect.top)/rect.height*100,bounds?.minY ?? 0,bounds?.maxY ?? 100)*10)/10};place(element);};
    // Drag placement is deliberately free-form. Players may intentionally
    // overlap controls; the position is persisted exactly as released.
    const up=()=>{saveLayout();element.removeEventListener("pointermove",move);["pointerup","pointercancel","lostpointercapture"].forEach(name=>element.removeEventListener(name,up));};
    element.addEventListener("pointermove",move);["pointerup","pointercancel","lostpointercapture"].forEach(name=>element.addEventListener(name,up));
  });
  const makeButton=(id,label,index)=>{const wrap=document.createElement("div");wrap.className="tvCtrl";wrap.dataset.id=id;wrap.innerHTML=`<div class="tvBtn ${label.length>1?"small":""}">${label}</div>`;bindDrag(wrap);bindInput(wrap,index);return wrap;};
  const makeDpad=()=>{const wrap=document.createElement("div"),labels=config.lang==="en"?{up:"Up",down:"Down",left:"Left",right:"Right"}:{up:"Lên",down:"Xuống",left:"Trái",right:"Phải"};wrap.className="tvCtrl";wrap.dataset.id="dpad";wrap.innerHTML=`<div class="tvDpad"><button class="up" aria-label="${labels.up}"><img src="/static/ui-chevron-up.svg" alt=""></button><button class="down" aria-label="${labels.down}"><img src="/static/ui-chevron-down.svg" alt=""></button><button class="left" aria-label="${labels.left}"><img src="/static/ui-chevron-left.svg" alt=""></button><button class="right" aria-label="${labels.right}"><img src="/static/ui-chevron-right.svg" alt=""></button></div>`;bindDrag(wrap);[[".up",4],[".down",5],[".left",6],[".right",7]].forEach(([selector,index])=>bindInput(wrap.querySelector(selector),index));return wrap;};
  const addAnalogStick = wrap => {
    const ui = globalThis.AN3PlayerUI;
    if (!ui) return;
    const stick = document.createElement("div"), thumb = document.createElement("span");
    stick.className = "tvStick"; stick.setAttribute("role","group"); stick.setAttribute("aria-label","Analog Joystick");
    thumb.className = "tvStickThumb"; thumb.setAttribute("aria-hidden","true");
    thumb.style.width = thumb.style.height = `${ui.model.joystick.thumbRadiusRatio*100}%`;
    stick.appendChild(thumb); wrap.appendChild(stick);
    let owner = null;
    const update = event => {
      if (event.pointerId !== owner) return;
      const rect = stick.getBoundingClientRect();
      const travel = Math.max(1, Math.min(rect.width,rect.height)*.5*ui.model.joystick.travelRatio);
      const axis = ui.normalize((event.clientX-rect.left-rect.width/2)/travel,(event.clientY-rect.top-rect.height/2)/travel);
      thumb.style.left = `${50+axis.x*ui.model.joystick.travelRatio*50}%`;
      thumb.style.top = `${50+axis.y*ui.model.joystick.travelRatio*50}%`;
      analogInput(axis.x,axis.y);
    };
    releaseStick = () => {
      const pointer = owner; owner = null;
      thumb.style.left = thumb.style.top = "50%"; analogInput(0,0);
      if (pointer !== null) try { stick.releasePointerCapture(pointer); } catch (_) {}
    };
    stick.addEventListener("pointerdown",event=>{
      if (owner !== null || padRoot.classList.contains("edit") || stage?.classList.contains("emulator-menu-open")) return;
      event.preventDefault(); event.stopPropagation(); owner=event.pointerId;
      try { stick.setPointerCapture(owner); } catch (_) {}
      update(event);
    });
    stick.addEventListener("pointermove",update);
    for (const name of ["pointerup","pointercancel","lostpointercapture"]) stick.addEventListener(name,event=>{
      if (event.pointerId === owner) releaseStick();
    });
    window.addEventListener("blur",releaseStick);
    document.addEventListener("visibilitychange",()=>{ if(document.hidden) releaseStick(); });
    if (stage) new MutationObserver(()=>{
      if (stage.classList.contains("emulator-menu-open") || !padRoot.classList.contains("show")) releaseStick();
    }).observe(stage,{attributes:true,attributeFilter:["class"]});
  };
  const padTarget = document.getElementById("padTarget");
  const padSize = document.getElementById("padSize");
  const padSizeValue = document.getElementById("padSizeValue");
  const padSizeHint = document.getElementById("padSizeHint");
  const padAdvanced = document.querySelector(".player-pad-advanced");
  const padGlobalScale = document.getElementById("padGlobalScale");
  const padGlobalScaleValue = document.getElementById("padGlobalScaleValue");
  const touchToggle = document.getElementById("toggleTouch");
  const panelTouchToggle = document.getElementById("togglePad");
  const applyControlSizes = overrides => padRoot.querySelectorAll(".tvCtrl").forEach(control => {
    const id=control.dataset.id;
    const multiplier=overrides && Object.prototype.hasOwnProperty.call(overrides,id) ? normalizeButtonScale(overrides[id]) : buttonScale(id);
    control.style.setProperty("--control-scale",globalScale()*baseControlScale(id)*multiplier);
  });
  const syncGlobalScale = () => {
    const value=Math.round(globalScale()*100);
    if (padGlobalScale) padGlobalScale.value=value;
    if (padGlobalScaleValue) { padGlobalScaleValue.value=`${value}%`;padGlobalScaleValue.textContent=`${value}%`; }
  };
  const padSizeMessage = reason => {
    if (config.lang === "en") {
      if (reason === "hidden") return "Show virtual controls before increasing an individual size safely.";
      if (reason === "fit") return "This control would not fit inside the play area.";
      if (reason === "overlap") return "This size would overlap another control.";
      if (reason === "unsafe") return "Current control sizes do not fit this screen. Reduce individual sizes or reset controls.";
      return "100% is this control’s approved default. Overall size applies too.";
    }
    if (reason === "hidden") return "Bật phím ảo trước khi tăng kích thước từng phím một cách an toàn.";
    if (reason === "fit") return "Phím này sẽ không vừa trong vùng chơi.";
    if (reason === "overlap") return "Kích thước này sẽ chồng lên phím khác.";
    if (reason === "unsafe") return "Kích thước phím hiện tại không vừa màn hình này. Hãy giảm kích thước từng phím hoặc đặt lại điều khiển.";
    return "100% là kích thước mặc định đã duyệt của phím này. Kích thước chung cũng được áp dụng.";
  };
  const setPadSizeHint = (reason="") => {
    if (!padSizeHint) return;
    padSizeHint.textContent=padSizeMessage(reason);
    padSizeHint.classList.toggle("is-error",Boolean(reason && reason !== "hidden"));
  };
  const reportPadSafety = check => {
    if (!check || check.safe) return;
    setPadSizeHint(check.reason);
    showNotice(padSizeMessage(check.reason),true);
  };
  const maxSafeButtonScale = id => {
    const current=Math.round(buttonScale(id)*100);
    if (!padVisible()) return current;
    let maximum=50;
    for (let percent=50;percent<=200;percent+=1) if (inspectButtonScale(id,percent/100).safe) maximum=percent;
    return Math.max(current,maximum);
  };
  const syncPadSize = (refreshLimit=false) => {
    if (!padTarget || !padSize) return;
    const value=Math.round(buttonScale(padTarget.value)*100);
    if (refreshLimit) padSize.max=maxSafeButtonScale(padTarget.value);
    else if (Number(padSize.max)<value) padSize.max=value;
    padSize.value=value;
    if(padSizeValue){padSizeValue.value=`${value}%`;padSizeValue.textContent=`${value}%`;}
    setPadSizeHint(padSafetyBlocked ? "unsafe" : (padVisible() ? "" : "hidden"));
  };
  let padSafetyBlocked=false;
  const padVisible = () => {
    if (!customPad) return false;
    if (!ndsPad) return settings.visible!==false;
    return settings.visibilityMode==="shown" || (settings.visibilityMode!=="hidden" && touchFirst);
  };
  const checkCurrentPadSafety = () => {
    if (!padVisible()) { padSafetyBlocked=false;return {safe:true}; }
    const check=inspectCurrentButtonScales();
    padSafetyBlocked=!check.safe;
    return check;
  };
  const applySettings=()=>{
    releaseStick();
    padRoot.classList.toggle("analog-mode",settings.directionalControl==="joystick" && Boolean(globalThis.AN3PlayerUI));
    const directionChoice=document.getElementById("padDirectionalControl");
    if(directionChoice) directionChoice.value=settings.directionalControl;
    padRoot.style.setProperty("--pad-scale",globalScale());
    padRoot.style.setProperty("--pad-opacity",settings.opacity);
    const visible=padVisible();
    padRoot.classList.toggle("show",visible);
    applyControlSizes();padRoot.querySelectorAll(".tvCtrl").forEach(place);
    const safety=checkCurrentPadSafety();
    // Geometry checks remain the guard for enlarging or moving controls, but
    // must never remove the existing playable pad on a short mobile stage.
    // Fullscreen changes its measured bounds, so hiding it here made the pad
    // appear only after entering fullscreen on both GBA and NDS.
    padRoot.classList.remove("safety-blocked");
    stage?.classList.toggle("pad-overlay",visible);
    document.body.classList.toggle("pad-overlay",visible);
    syncGlobalScale();syncPadSize();
    const opacity=document.getElementById("padOpacity");if(opacity)opacity.value=Math.round(settings.opacity*100);
    if(touchToggle){touchToggle.setAttribute("aria-pressed",String(visible));touchToggle.classList.toggle("is-on",visible);touchToggle.title=visible?(config.lang==="en"?"Hide virtual controls":"Ẩn phím ảo"):(config.lang==="en"?"Show virtual controls":"Hiện phím ảo");}
    if(panelTouchToggle){panelTouchToggle.setAttribute("aria-pressed",String(visible));panelTouchToggle.textContent=visible?(config.lang==="en"?"Hide virtual controls":"Ẩn phím ảo"):(config.lang==="en"?"Show virtual controls":"Hiện phím ảo");}
    return safety;
  };
  if (customPad) {
    const controls=[makeDpad(),makeButton("a","A",8),makeButton("b","B",0),makeButton("start","Start",3),makeButton("select","Select",2)];
    if(config.system==="gba")controls.push(makeButton("l","L",10),makeButton("r","R",11));
    if(ndsPad || threeDsPad)controls.push(makeButton("x","X",9),makeButton("y","Y",1),makeButton("l","L",10),makeButton("r","R",11));
    controls.forEach(control=>{padRoot.appendChild(control);place(control);});
    addAnalogStick(controls[0]);
    applySettings();
  }
  document.getElementById("padDirectionalControl")?.addEventListener("change",event=>{
    releaseStick();
    settings.directionalControl=event.target.value==="joystick"?"joystick":"dpad";
    saveSettings(); applySettings();
  });
  const setPadEditing = (editing,{force=false}={}) => {
    if (editing && !padVisible()) {
      setPadSizeHint("hidden");
      showNotice(config.lang === "en" ? "Show virtual controls before moving them." : "Bật phím ảo trước khi di chuyển.",true);
      return false;
    }
    // On a phone the options sheet covers the controller.  Close it as the
    // user enters NDS/3DS edit mode so the first drag can reach the control.
    if (editing && (ndsPad || threeDsPad)) {
      panel?.classList.remove("open");
      document.getElementById("playerControls")?.setAttribute("aria-expanded","false");
    }
    padRoot.classList.toggle("edit",editing);
    const button=document.getElementById("editPad");
    if (button) {button.textContent=editing ? (config.lang==="en"?"Done":"Xong") : (config.lang==="en"?"Move":"Kéo thả");button.setAttribute("aria-pressed",String(editing));}
    if(editing) showNotice(config.lang==="en"?"Drag controls, then reopen the player menu and choose Done to lock their positions.":"Kéo các phím, rồi mở lại menu player và bấm Xong để cố định vị trí.");
    if (!editing) saveLayout();
    return true;
  };
  const resetCurrentLayout = () => {
    const candidate={...padDefaults[orientation]};
    if (padVisible()) {
      const check=inspectCurrentButtonScales({positions:candidate});
      if (!check.safe) { reportPadSafety(check);return false; }
    }
    try { localStorage.removeItem(key()); } catch (_) {}
    positions=candidate;
    const safety=applySettings();if(!safety.safe)reportPadSafety(safety);
    if (padAdvanced?.open) syncPadSize(true);
    return true;
  };
  const commitButtonScale = (id, next) => {
    const requested=normalizeButtonScale(next),current=buttonScale(id);
    if (requested>current+.0001) {
      const check=inspectButtonScale(id,requested);
      if (!check.safe) {
        syncPadSize();
        reportPadSafety(check);
        return false;
      }
    }
    if (requested===1) delete settings.buttonScales[id];
    else settings.buttonScales[id]=requested;
    saveSettings();
    const safety=applySettings();if(!safety.safe)reportPadSafety(safety);
    return true;
  };
  const resetAllButtonScales = () => {
    const controls=Array.from(padRoot.querySelectorAll(".tvCtrl"));
    const increases=controls.some(control=>buttonScale(control.dataset.id)<1);
    if (increases) {
      const check=inspectButtonScales(Object.fromEntries(controls.map(control=>[control.dataset.id,1])));
      if (!check.safe) {
        syncPadSize();
        reportPadSafety(check);
        return false;
      }
    }
    settings.buttonScales={};
    saveSettings();
    const safety=applySettings();if(!safety.safe)reportPadSafety(safety);
    return true;
  };
  const closePlayerOptions = () => { panel?.classList.remove("open");document.getElementById("playerControls")?.setAttribute("aria-expanded","false"); };
  const closeSlotOptions = () => { if(slotPanel)slotPanel.hidden=true;document.getElementById("slotMenu")?.setAttribute("aria-expanded","false"); };
  if (ndsPad && stage) new MutationObserver(()=>{if(stage.classList.contains("emulator-menu-open"))closePlayerOptions();}).observe(stage,{attributes:true,attributeFilter:["class"]});
  document.getElementById("emulatorMenu")?.addEventListener("click",()=>{showHints();closePlayerOptions();try{window.EJS_emulator?.menu?.toggle()}catch(_){}queueEmulatorMenuLayer();});
  document.getElementById("playerControls")?.addEventListener("click",event=>{showHints();if(!panel)return;if(stage?.classList.contains("emulator-menu-open")){showNotice(config.lang==="en"?"Close the EmulatorJS menu before opening player options." : "Hãy đóng menu EmulatorJS trước khi mở tùy chọn trình phát.",true);return;}closeSlotOptions();const open=panel.classList.toggle("open");event.currentTarget.setAttribute("aria-expanded",String(open));if(open)document.getElementById("closePad")?.focus();});
   document.getElementById("closePad")?.addEventListener("click",()=>{if(!setPadEditing(false))return;closePlayerOptions();document.getElementById("playerControls")?.focus()});

  // ---- Remote phone controller (staging-only) -----------------------------
  // The player page is the pairing host: it creates a session, shows a QR, and
  // polls the host-state endpoint, applying the phone's latest frame through the
  // same virtual-input path the on-screen pad uses. Input is applied only while
  // gameplay is running and no EmulatorJS menu owns input, so a phone can never
  // drive a stopped session or leak a touch past an open menu.
  const controllerPanel = document.getElementById("ctrlPhonePanel");
  const controllerButtonIndex = {b:0,y:1,select:2,start:3,up:4,down:5,left:6,right:7,a:8,x:9,l:10,r:11};
  const controller = {code:"",hostToken:"",timer:0,applied:new Set(),axes:false};
  const controllerRunning = () => Boolean(gameStarted) && !runtimeFailed && !stage?.classList.contains("emulator-menu-open");
  const controllerRelease = () => {
    for (const name of controller.applied) input(controllerButtonIndex[name],0);
    controller.applied = new Set();
    if (controller.axes) { analogInput(0,0); controller.axes = false; }
  };
  const controllerApply = payload => {
    const frame = payload?.state || {};
    const pressed = new Set((frame.b || []).filter(name=>Object.prototype.hasOwnProperty.call(controllerButtonIndex,name)));
    for (const name of controller.applied) if (!pressed.has(name)) input(controllerButtonIndex[name],0);
    for (const name of pressed) if (!controller.applied.has(name)) input(controllerButtonIndex[name],1);
    controller.applied = pressed;
    const axes = frame.a || [0,0,0,0];
    const leftX = Number(axes[0]) || 0, leftY = Number(axes[1]) || 0;
    const engaged = Math.abs(leftX) > 0.35 || Math.abs(leftY) > 0.35;
    if (engaged) { analogInput(leftX,leftY); controller.axes = true; }
    else if (controller.axes) { analogInput(0,0); controller.axes = false; }
  };
  const controllerStatus = text => { const node=document.getElementById("ctrlPhoneStatus"); if(node)node.textContent=text; };
  const controllerStop = message => {
    controllerRelease();
    if (controller.timer) clearInterval(controller.timer);
    controller.timer = 0; controller.code = ""; controller.hostToken = "";
    if (message) controllerStatus(message);
  };
  const controllerPoll = async () => {
    if (!controller.code || !controller.hostToken) return;
    try {
      const response = await fetch("/api/controller/state?code=" + encodeURIComponent(controller.code) + "&hostToken=" + encodeURIComponent(controller.hostToken));
      if (response.status === 403 || response.status === 404) { controllerStop(config.lang==="en"?"Session ended.":"Phiên đã kết thúc."); return; }
      if (!response.ok) return;
      const payload = await response.json();
      if (controllerRunning()) controllerApply(payload); else controllerRelease();
      const buttons = payload?.state?.b?.join(",") || "";
      controllerStatus((payload.paired ? (config.lang==="en"?"Phone connected":"Điện thoại đã kết nối") : (config.lang==="en"?"Waiting for a phone…":"Đang chờ điện thoại…")) + (buttons ? " · " + buttons : "") + " · " + payload.expiresInSeconds + "s");
    } catch (_) { /* transient; the next poll retries */ }
  };
  const controllerStart = async () => {
    if (!config.controllerEnabled) return;
    controllerStop();
    controllerStatus(config.lang==="en"?"Creating session…":"Đang tạo phiên…");
    try {
      const response = await fetch("/api/controller/session", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({deviceId:"host-player"})});
      if (!response.ok) throw new Error("HTTP " + response.status);
      const data = await response.json();
      controller.code = data.code; controller.hostToken = data.hostToken;
      const codeNode = document.getElementById("ctrlPhoneCode"); if (codeNode) codeNode.textContent = data.code;
      const linkNode = document.getElementById("ctrlPhoneLink");
      if (linkNode) { linkNode.href = data.joinPath; linkNode.textContent = location.origin + data.joinPath; }
      const qrNode = document.getElementById("ctrlPhoneQr");
      if (qrNode) { qrNode.src = "/api/controller/qr.svg?code=" + encodeURIComponent(data.code); qrNode.hidden = false; }
      controllerStatus((config.lang==="en"?"Waiting for a phone… ":"Đang chờ điện thoại… ") + data.ttlSeconds + "s");
      controller.timer = setInterval(controllerPoll, 250);
    } catch (error) { controllerStatus(error.message || String(error)); }
  };
  const controllerOpen = () => { if (!controllerPanel) return; controllerPanel.hidden = false; controllerStart(); document.getElementById("closeCtrlPhone")?.focus(); };
  document.getElementById("phoneController")?.addEventListener("click",()=>{showHints();closePlayerOptions();closeSlotOptions();controllerOpen();});
  document.getElementById("closeCtrlPhone")?.addEventListener("click",()=>{if(controllerPanel)controllerPanel.hidden=true;controllerStop();document.getElementById("phoneController")?.focus();});
  addEventListener("pagehide",()=>controllerStop(),{once:true});

  // ---- Multiplayer room -> EmulatorJS relay bridge (staging-only) ---------
  // The player creates the AN3 room (the server enforces the system+core+ROM
  // hash compatibility check) and then hands the invite code to the EmulatorJS
  // netplay client as the relay room name. Hosting and joining both go through
  // the official netplay object; nothing is re-implemented here.
  const mpPanel = document.getElementById("mpPlayerPanel");
  const mpPost = async (url, payload) => {
    const response = await fetch(url, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    let data = {}; try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data.error || ("HTTP " + response.status));
    return data;
  };
  const mpStatus = text => { const node=document.getElementById("mpPlayerStatus"); if(node)node.textContent=text; };
  const mpNetplay = () => { try { return globalThis.EJS_emulator?.netplay || null; } catch (_) { return null; } };
  const mpEnsureNetplay = () => {
    const emulator = globalThis.EJS_emulator;
    if (!emulator) throw new Error("Emulator is not ready");
    if (typeof emulator.openNetplayMenu !== "function") throw new Error("This core has no netplay menu");
    if (!emulator.netplay) {
      emulator.openNetplayMenu();
      // openNetplayMenu also reveals its own panel; keep AN3's surface clean.
      try { if (emulator.netplayMenu) emulator.netplayMenu.style.display = "none"; } catch (_) {}
    }
    const netplay = emulator.netplay;
    if (!netplay) throw new Error("Netplay is unavailable");
    if (!netplay.name) netplay.name = "AN3 player";
    return netplay;
  };
  const mpShowRoom = data => {
    const codeNode = document.getElementById("mpPlayerCode"); if (codeNode) codeNode.textContent = data.code;
    const linkNode = document.getElementById("mpPlayerLink");
    if (linkNode) { linkNode.href = `/play/${encodeURIComponent(config.slug)}?room=${encodeURIComponent(data.code)}`; linkNode.textContent = linkNode.href; }
    const joinInput = document.getElementById("mpPlayerJoinCode"); if (joinInput && !joinInput.value) joinInput.value = data.code;
    const qrNode = document.getElementById("mpPlayerQr");
    if (qrNode) { qrNode.src = `/api/multiplayer/qr.svg?slug=${encodeURIComponent(config.slug)}&code=${encodeURIComponent(data.code)}`; qrNode.hidden = false; }
  };
  const mpSignature = () => Object.assign({}, config.roomSignature || {}, {deviceId: "web-player"});
  const mpCreateRoom = async () => {
    if (!config.multiplayerEnabled) return "";
    mpStatus(config.lang==="en"?"Creating room…":"Đang tạo phòng…");
    const data = await mpPost("/api/multiplayer/room", mpSignature());
    mpShowRoom(data);
    mpStatus((config.lang==="en"?"Room ready: ":"Phòng đã sẵn sàng: ") + data.code + " · " + Math.round(data.expiresInSeconds/60) + " min");
    return data.code;
  };
  const mpHostOnRelay = async () => {
    try {
      let code = document.getElementById("mpPlayerCode")?.textContent || "";
      if (!code || code === "—") code = await mpCreateRoom();
      if (!code || code === "—") return;
      const netplay = mpEnsureNetplay();
      mpStatus((config.lang==="en"?"Hosting on relay: ":"Đang mở phòng trên relay: ") + code);
      netplay.openRoom(code, 2, "");
    } catch (error) { mpStatus(error.message || String(error)); }
  };
  const mpFindRoomKey = async netplay => {
    const rooms = await netplay.getOpenRooms();
    return Object.keys(rooms || {}).find(key => (rooms[key]?.room_name || "") === (document.getElementById("mpPlayerJoinCode")?.value || "").trim().toUpperCase()) || "";
  };
  const mpJoinRelay = async () => {
    try {
      const code = (document.getElementById("mpPlayerJoinCode")?.value || "").trim().toUpperCase();
      if (!code) throw new Error(config.lang==="en"?"Enter an invite code.":"Hãy nhập mã mời.");
      // The AN3 service enforces the compatibility check before any relay join.
      const data = await mpPost("/api/multiplayer/join", Object.assign(mpSignature(), {code}));
      mpShowRoom(data);
      const netplay = mpEnsureNetplay();
      const key = await mpFindRoomKey(netplay);
      if (!key) throw new Error(config.lang==="en"?"That relay room is not open yet.":"Phòng relay chưa mở.");
      mpStatus((config.lang==="en"?"Joining relay room: ":"Đang vào phòng relay: ") + data.code);
      netplay.joinRoom(key, data.code);
    } catch (error) { mpStatus(error.message || String(error)); }
  };
  const mpLeaveRelay = () => { try { mpNetplay()?.leaveRoom?.(); mpStatus(config.lang==="en"?"Left the relay room.":"Đã rời phòng relay."); } catch (error) { mpStatus(error.message || String(error)); } };
  const mpOpen = () => {
    if (!mpPanel) return;
    mpPanel.hidden = false;
    const prefill = new URLSearchParams(location.search).get("room");
    const joinInput = document.getElementById("mpPlayerJoinCode");
    if (prefill && joinInput && !joinInput.value) joinInput.value = prefill.trim().toUpperCase();
    document.getElementById("closeMpPanel")?.focus();
  };
  document.getElementById("playerMultiplayer")?.addEventListener("click",()=>{showHints();closePlayerOptions();closeSlotOptions();mpOpen();});
  document.getElementById("closeMpPanel")?.addEventListener("click",()=>{mpLeaveRelay();if(mpPanel)mpPanel.hidden=true;document.getElementById("playerMultiplayer")?.focus();});
  document.getElementById("mpPlayerCreate")?.addEventListener("click",()=>mpCreateRoom().catch(error=>mpStatus(error.message||String(error))));
  document.getElementById("mpPlayerHost")?.addEventListener("click",()=>mpHostOnRelay());
  document.getElementById("mpPlayerJoin")?.addEventListener("click",()=>mpJoinRelay());
  document.getElementById("mpPlayerLeave")?.addEventListener("click",()=>mpLeaveRelay());
  addEventListener("pagehide",()=>mpLeaveRelay(),{once:true});

  document.getElementById("editPad")?.addEventListener("click",()=>setPadEditing(!padRoot.classList.contains("edit")));
  const togglePad=()=>{if(castConsoleAutoPad){padRoot.classList.remove("cast-console-show");castConsoleAutoPad=false;}const wasVisible=padVisible();if(ndsPad)settings.visibilityMode=wasVisible?"hidden":"shown";else settings.visible=settings.visible===false;if(wasVisible)setPadEditing(false,{force:true});saveSettings();const safety=applySettings();if(!safety.safe)reportPadSafety(safety);if(padAdvanced?.open)syncPadSize(true);};
  touchToggle?.addEventListener("click",togglePad);
  document.getElementById("togglePad")?.addEventListener("click",togglePad);
  padAdvanced?.addEventListener("toggle",()=>syncPadSize(true));
  padTarget?.addEventListener("change",()=>syncPadSize(true));
  const commitGlobalScale = next => {
    const requested=clamp(Number(next) || 1,.7,1),current=globalScale();
    if (requested>current+.0001) {
      const check=padVisible() ? inspectCurrentButtonScales({globalScale:requested}) : {safe:false,reason:"hidden"};
      if (!check.safe) { syncGlobalScale();reportPadSafety(check);return false; }
    }
    settings.globalScale=requested;
    saveSettings();
    const safety=applySettings();if(!safety.safe)reportPadSafety(safety);
    return safety.safe;
  };
  padGlobalScale?.addEventListener("input",event=>{commitGlobalScale(Number(event.target.value)/100);if(padAdvanced?.open)syncPadSize(true);});
  document.getElementById("resetPadGlobalScale")?.addEventListener("click",()=>{commitGlobalScale(1);if(padAdvanced?.open)syncPadSize(true);});
  padSize?.addEventListener("input",event=>{if(!padTarget)return;commitButtonScale(padTarget.value,clamp(Number(event.target.value)/100,.5,2));});
  document.getElementById("resetPadTarget")?.addEventListener("click",()=>{if(padTarget)commitButtonScale(padTarget.value,1);});
  document.getElementById("resetPadSizes")?.addEventListener("click",resetAllButtonScales);
  document.getElementById("padOpacity")?.addEventListener("input",event=>{settings.opacity=Number(event.target.value)/100;saveSettings();applySettings();});
  document.getElementById("resetPadLayout")?.addEventListener("click",resetCurrentLayout);
  document.getElementById("resetPad")?.addEventListener("click",()=>{["portrait","landscape"].forEach(nextOrientation=>{try{localStorage.removeItem(`an3-pad-v${ndsPad ? 5 : threeDsPad ? 7 : 3}:${config.system}:${nextOrientation}`);}catch(_){}});positions={...padDefaults[orientation]};settings.globalScale=1;settings.opacity=defaultSettings.opacity;if(ndsPad)settings.visibilityMode="auto";else settings.visible=true;settings.buttonScales={};setPadEditing(false,{force:true});saveSettings();const safety=applySettings();if(!safety.safe)reportPadSafety(safety);if(padAdvanced?.open)syncPadSize(true);});
  document.addEventListener("keydown",event=>{if(event.key!=="Escape")return;if(panel?.classList.contains("open")){event.preventDefault();document.getElementById("closePad")?.click();}else if(slotPanel&&!slotPanel.hidden){event.preventDefault();document.getElementById("closeSlots")?.click();}});
  let resizeTimer;const queuePadLayout=()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{const next=innerWidth>innerHeight?"landscape":"portrait";if(next!==orientation){saveLayout();orientation=next;positions={...padDefaults[orientation],...read(key())};}syncDualScreenStage();const desiredNdsLayout=dualScreenLayout();if(ndsPad && gameStarted && desiredNdsLayout!==appliedNdsScreenLayout){showNotice(config.lang==="en"?`Restart the player to apply the ${desiredNdsLayout} DS screen layout.`:`Khởi động lại player để áp dụng bố cục màn hình DS ${desiredNdsLayout === "Left/Right" ? "trái/phải" : "trên/dưới"}.`);appliedNdsScreenLayout=desiredNdsLayout;}if(threeDsPad && gameStarted && desiredNdsLayout!==appliedThreeDsScreenLayout){showNotice(config.lang==="en"?`Restart the player to apply the ${desiredNdsLayout} 3DS screen layout.`:`Khởi động lại player để áp dụng bố cục màn hình 3DS ${desiredNdsLayout === "Left/Right" ? "trái/phải" : "trên/dưới"}.`);appliedThreeDsScreenLayout=desiredNdsLayout;}const safety=applySettings();if(!safety.safe)reportPadSafety(safety);if(padAdvanced?.open)syncPadSize(true);},160)};addEventListener("resize",queuePadLayout);document.addEventListener("fullscreenchange",queuePadLayout);
  document.addEventListener("visibilitychange",()=>{if(document.hidden)[0,2,3,4,5,6,7,8,10,11].forEach(index=>input(index,0))});
  boot();
})();
