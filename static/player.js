(() => {
  const shell = document.querySelector("[data-player]");
  if (!shell) return;
  const config = JSON.parse(shell.dataset.player);
  const emulatorSystem = config.system === "doom" ? "prboom" : config.system;
  const primaryCores = {
    gb:"gambatte",gba:"mgba",nds:"melonds","3ds":"azahar",nes:"fceumm",snes:"snes9x",n64:"mupen64plus_next",psx:"pcsx_rearmed",psp:"ppsspp",
    segaMD:"genesis_plus_gx",segaMS:"smsplus",segaGG:"genesis_plus_gx",sega32x:"picodrive",segaCD:"genesis_plus_gx",segaSaturn:"yabause",
    arcade:"fbneo","3do":"opera",atari2600:"stella2014",atari7800:"prosystem",jaguar:"virtualjaguar",lynx:"handy",pce:"mednafen_pce",
    amiga:"puae",c64:"vice_x64sc",doom:"prboom"
  };
  const ndsPad = config.system === "nds";
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
  const savePerformanceSettings = () => { try { localStorage.setItem(performanceStorageKey,JSON.stringify(performanceSettings)); } catch (_) {} };
  const threadedCore = ["psp","3ds"].includes(config.system);
  const webgl2Required = ["psp","3ds"].includes(config.system);
  const stage = document.querySelector(".player-stage");
  const loading = document.getElementById("loading");
  const loadingText = document.getElementById("loadingText");
  const loadingBar = document.getElementById("loadingBar");
  const loadingProgress = loadingBar?.closest('[role="progressbar"]');
  const loadingPct = document.getElementById("loadingPct");
  const notice = document.getElementById("playerNotice");
  const statusText = document.getElementById("playerStatusText");
  const saveStatus = document.getElementById("playerSaveStatus");
  const setRuntimeStatus = (state, text) => {
    if (statusText) statusText.textContent = text;
    stage?.classList.toggle("is-ready", state === "ready");
    stage?.classList.toggle("has-error", state === "error");
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
  const reportPreload = (ok, error = "") => {
    if (config.mode !== "preload" || preloadReported) return;
    preloadReported = true;
    window.parent?.postMessage({type:"an3-core-preload", system:config.system, ok, error}, location.origin);
  };
  const finishLoading = () => { setProgress(100, config.lang === "en" ? "Ready" : "Sẵn sàng");setRuntimeStatus("ready",config.lang === "en" ? "Playing" : "Đang chơi");reportPreload(true);setTimeout(() => loading.classList.add("done"), 350); };
  const failLoading = error => { const message=error.message || String(error);loadingText.textContent=message;loadingText.style.color="#ef6a67";loadingProgress?.setAttribute("aria-invalid","true");loadingProgress?.setAttribute("aria-valuetext",message);setRuntimeStatus("error",config.lang === "en" ? "Could not start" : "Không thể khởi động");reportPreload(false,message); };

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
      if (webgl2Required && !webgl2) throw new Error(config.lang === "en" ? "This core requires WebGL 2." : "Core này cần trình duyệt hỗ trợ WebGL 2.");
      if (threadedCore && (!crossOriginIsolated || typeof SharedArrayBuffer !== "function")) throw new Error(config.lang === "en" ? "This core requires cross-origin isolation and SharedArrayBuffer." : "Core này cần trình duyệt hỗ trợ SharedArrayBuffer an toàn.");
      const root = `/emulatorjs/${config.channel}/data/`;
      const runtimeCache="caches" in globalThis ? await caches.open("an3-arcade-cores-v1") : null;
      const reportUrl=`${root}cores/reports/${core}.json`,reportResponse=await fetch(reportUrl,{credentials:"same-origin"});
      if (!reportResponse.ok) throw new Error(`cores/reports/${core}.json (${reportResponse.status})`);
      if (runtimeCache) await runtimeCache.put(reportUrl,reportResponse.clone());
      const report=await reportResponse.json();
      const coreUsesWebgl2=!performancePlan.forceLegacyNds && webgl2 && Boolean(report?.options?.defaultWebGL2 || webgl2Required);
      const coreFile = `${core}${threadedCore?"-thread":""}${coreUsesWebgl2?"":"-legacy"}-wasm.data`;
      const assets = [
        "loader.js","emulator.min.js","emulator.min.css","localization/en-US.json","compression/extract7z.js","compression/extractzip.js",
        `cores/${coreFile}`
      ];
      if (core === "ppsspp") assets.push("cores/ppsspp-assets.zip");
      let coreData=null;
      for (let index=0; index<assets.length; index+=1) {
        const asset = assets[index], url = root + asset;
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

  if (config.mode === "html5") {
    document.querySelector(".custom-frame")?.addEventListener("load", finishLoading);
    document.getElementById("playerControls")?.remove();
    setProgress(50, config.lang === "en" ? "Loading game" : "Đang tải game");
    return;
  }

  const customPad = ["gba", "gb", "nds"].includes(config.system);
  const touchFirst = Boolean(window.matchMedia?.("(pointer:coarse)")?.matches || (navigator.maxTouchPoints > 0 && !window.matchMedia?.("(hover:hover)")?.matches));
  const touchVariant = ndsPad ? new URLSearchParams(location.search).get("touch") || "geometry-mapped" : "baseline";
  const isolatedNdsMovement = ["geometry-only","geometry-mapped"].includes(touchVariant);
  const ndsDebugEnabled = ndsPad && config.ndsDebugAllowed === true && new URLSearchParams(location.search).get("ndsdebug") === "1";
  document.documentElement.classList.toggle("custom-pad", customPad);
  stage.classList.toggle("nds-stage", ndsPad);

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
      pointerId,
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
      const canvas=path.find(node=>node?.nodeName === "CANVAS") || event.target?.closest?.("#game canvas") || gameRoot.querySelector("canvas");
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
    const videoWidth=Number(manager?.getVideoDimensions?.("width"))||256;
    const videoHeight=Number(manager?.getVideoDimensions?.("height"))||384;
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
    const frameX=source.clientX-rect.left-viewport.left;
    const touchY=source.clientY-rect.top-viewport.top-(viewport.height/2);
    const x=Math.round(Math.max(0,Math.min(viewport.videoWidth-1,frameX*viewport.videoWidth/viewport.width)));
    const y=Math.round(Math.max(0,Math.min((viewport.videoHeight/2)-1,touchY*viewport.videoHeight/viewport.height)));
    return {x,y};
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
      movementX=mapped.x-ndsMappedCursor.x;
      movementY=mapped.y-ndsMappedCursor.y;
      ndsMappedCursor=mapped;
    }
    canvas[pointKey]=type === "mouseup" ? null : {x:cssX,y:cssY};
    const event=new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:source.clientX,clientY:source.clientY,screenX:source.screenX||source.clientX,screenY:source.screenY||source.clientY,button:0,buttons});
    // EmulatorJS reads local canvas coordinates. Synthetic MouseEvents otherwise
    // expose offsetX/offsetY as 0, which traps the DS pointer in the top-left.
    for (const [name,value] of [["offsetX",offsetX],["offsetY",offsetY],["layerX",offsetX],["layerY",offsetY]]) {
      try { Object.defineProperty(event,name,{value,writable:false,enumerable:true}); } catch (_) {}
    }
    if (["delta","geometry-only","geometry-mapped"].includes(touchVariant)) for (const [name,value] of [["movementX",movementX],["movementY",movementY]]) {
      try { Object.defineProperty(event,name,{value,writable:false,enumerable:true}); } catch (_) {}
    }
    canvas.dispatchEvent(event);
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
  };
  const dispatchNdsEvent = (canvas, type, source, buttons) => {
    if (touchVariant === "pointer-touch") return dispatchNdsPointer(canvas, `pointer${type.slice(5)}`, source, buttons);
    if (["hybrid","hybrid-root","geometry-only","geometry-mapped"].includes(touchVariant)) {
      dispatchNdsPointer(canvas, `pointer${type.slice(5)}`, source, buttons);
      dispatchNdsMouse(canvas, type, source, buttons);
      return;
    }
    dispatchNdsMouse(canvas, type, source, buttons);
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
  const bindRootNdsTouch = gameRoot => {
    if (!["root","root-touch","overlay","hybrid-root","core-touch","geometry-only","geometry-mapped"].includes(touchVariant) || gameRoot.dataset.an3RootTouch === "1") return;
    gameRoot.dataset.an3RootTouch="1";
    let active=null;
    const isTouch=event=>event.pointerType === "touch" || event.pointerType === "";
    const resolveCanvas=event=>{
      const hit=document.elementFromPoint(event.clientX,event.clientY);
      return hit?.closest?.("#game canvas") || gameRoot.querySelector("canvas");
    };
    if (["root-touch","hybrid-root","geometry-only","geometry-mapped"].includes(touchVariant) || touchVariant === "core-touch") {
      let touchId=null;
      const findTouch=event=>[...(event.touches||[]),...(event.changedTouches||[])].find(touch=>touch.identifier===touchId);
      const start=event=>{if(touchId!==null||!event.changedTouches?.length)return;const touch=event.changedTouches[0],canvas=resolveCanvas(touch);if(!canvas)return;touchId=touch.identifier;event.preventDefault();dispatchNdsEvent(canvas,"mousedown",touch,1);};
      const move=event=>{const touch=findTouch(event);if(!touch)return;const canvas=resolveCanvas(touch);if(!canvas)return;event.preventDefault();dispatchNdsEvent(canvas,"mousemove",touch,1);};
      const end=event=>{const touch=findTouch(event);if(!touch)return;const canvas=resolveCanvas(touch);if(canvas)dispatchNdsEvent(canvas,"mouseup",touch,0);event.preventDefault();touchId=null;};
      gameRoot.addEventListener("touchstart",start,{capture:true,passive:false});
      document.addEventListener("touchmove",move,{capture:true,passive:false});
      document.addEventListener("touchend",end,{capture:true,passive:false});
      document.addEventListener("touchcancel",end,{capture:true,passive:false});
      return;
    }
    gameRoot.addEventListener("pointerdown",event=>{if(!isTouch(event)||active)return;const canvas=resolveCanvas(event);if(!canvas)return;active={id:event.pointerId,canvas};event.preventDefault();canvas.focus?.({preventScroll:true});try{gameRoot.setPointerCapture(event.pointerId);}catch(_){}dispatchNdsMouse(canvas,"mousedown",event,1);},true);
    gameRoot.addEventListener("pointermove",event=>{if(!isTouch(event)||!active||event.pointerId!==active.id)return;event.preventDefault();dispatchNdsMouse(active.canvas,"mousemove",event,1);},true);
    const release=event=>{if(!isTouch(event)||!active||event.pointerId!==active.id)return;event.preventDefault();dispatchNdsMouse(active.canvas,"mouseup",event,0);try{gameRoot.releasePointerCapture(active.id);}catch(_){}active=null;};
    gameRoot.addEventListener("pointerup",release,true);gameRoot.addEventListener("pointercancel",release,true);
  };
  const protectNdsCanvas = () => {
    if (!ndsPad) return;
    document.querySelectorAll("#game .ejs_canvas,#game canvas").forEach(canvas=>{
      if (canvas.classList.contains("ejs-canvas-no-pointer")) canvas.classList.remove("ejs-canvas-no-pointer");
      canvas.style.setProperty("pointer-events","auto","important");
      canvas.style.setProperty("touch-action","none","important");
      bindNdsTouch(canvas);
    });
  };
  if (ndsPad) {
    const gameRoot=document.getElementById("game");
    bindNdsDebug(gameRoot);
    new MutationObserver(protectNdsCanvas).observe(gameRoot,{subtree:true,childList:true,attributes:true,attributeFilter:["class"]});
    protectNdsCanvas();
    bindRootNdsTouch(gameRoot);
  }

  async function fetchGame() {
    if (config.offlineId) {
      setProgress(18, config.lang === "en" ? "Opening local game" : "Đang mở game trên máy");
      const local = await window.AN3OfflineLibrary?.get(config.offlineId);
      if (!local?.file) throw new Error(config.lang === "en" ? "Local game file is unavailable" : "Không tìm thấy game ngoại tuyến trên máy này");
      return new File([local.file], local.name || config.downloadName, {type: "application/octet-stream"});
    }
    if (!config.romUrl) throw new Error(config.lang === "en" ? "Game URL is unavailable" : "Không tìm thấy đường dẫn game");
    setProgress(18, config.lang === "en" ? "Starting game stream" : "Đang mở luồng game");
    return config.romUrl;
  }

  let gameStarted = false;
  async function boot() {
    try {
      if (webgl2Required && !document.createElement("canvas").getContext("webgl2")) throw new Error(config.lang === "en" ? "This core requires WebGL 2." : "Core này cần WebGL 2.");
      if (threadedCore && (!crossOriginIsolated || typeof SharedArrayBuffer !== "function")) throw new Error(config.lang === "en" ? "This core requires SharedArrayBuffer support." : "Core này cần trình duyệt hỗ trợ SharedArrayBuffer an toàn.");
      const file = await fetchGame();
      setProgress(86, config.lang === "en" ? "Loading emulator" : "Đang tải giả lập");
      window.EJS_player = "#game";
      window.EJS_core = emulatorSystem;
      window.EJS_defaultOptions = ndsPad ? {
        retroarch_core:"melonds",
        ...(touchVariant === "core-touch" ? {melonds_touch_mode:"Touch"} : {})
      } : undefined;
      window.EJS_disableLocalStorage = ndsPad;
      window.EJS_gameName = config.slug;
      window.EJS_gameUrl = file;
      window.EJS_pathtodata = `/emulatorjs/${config.channel}/data/`;
      window.EJS_startOnLoaded = true;
      window.EJS_controlScheme = config.system;
      window.EJS_language = config.lang === "en" ? "en-US" : "vi-VN";
      window.EJS_disableDatabases = false;
      window.EJS_fixedSaveInterval = 60000;
      window.EJS_browserMode = customPad ? 2 : undefined;
      window.EJS_noAutoFocus = ndsPad;
      window.EJS_mouseLock = false;
      window.EJS_threads = threadedCore;
      window.EJS_forceLegacyCores = performancePlan.forceLegacyNds;
      window.EJS_hideSettings = ["fastForward","ff-ratio","slowMotion","sm-ratio"];
      window.EJS_onGameStart = () => { gameStarted=true;protectNdsCanvas();applySpeed(1);syncSpeedControls();finishLoading(); };
      const script = document.createElement("script");
      script.src = `${window.EJS_pathtodata}loader.js`;
      script.onload = () => setProgress(92, config.lang === "en" ? "Starting core" : "Đang khởi động core");
      script.onerror = () => failLoading(new Error(config.lang === "en" ? "Emulator files are unavailable. Connect once and preload this core." : "Không tải được tệp giả lập. Hãy kết nối mạng và tải trước core này."));
      document.body.appendChild(script);
      let checks = 0;
      const ready = setInterval(() => {
        protectNdsCanvas();
        if (gameStarted) clearInterval(ready);
        else if (window.EJS_emulator?.failedToStart) {
          clearInterval(ready);
          failLoading(new Error(window.EJS_emulator?.textElem?.innerText || (config.lang === "en" ? "The NDS core failed to start." : "Core NDS khởi động thất bại.")));
        }
        else if (!ndsPad && window.EJS_emulator?.gameManager) { clearInterval(ready);gameStarted=true;applySpeed(1);syncSpeedControls();finishLoading(); }
        else if (++checks > 720) { clearInterval(ready); failLoading(new Error(ndsPad ? (config.lang === "en" ? "The NDS game did not start after 3 minutes." : "Game NDS chưa khởi động sau 3 phút.") : (config.lang === "en" ? "The emulator did not start." : "Giả lập chưa khởi động."))); }
      }, 250);
      if (customPad) {
        const guard = setInterval(() => {
          document.querySelectorAll(".ejs_virtualGamepad_parent,.ejs_virtualGamepad_open").forEach(element => element.style.setProperty("display", "none", "important"));
          protectNdsCanvas();
          try { window.EJS_emulator?.toggleVirtualGamepad?.(false); } catch (_) {}
          if (gameStarted) clearInterval(guard);
        }, 250);
      }
    } catch (error) { failLoading(error); }
  }

  document.getElementById("saveState")?.addEventListener("click", () => {
    try {
      const state = window.EJS_emulator?.gameManager?.getState();
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
      const manager = window.EJS_emulator?.gameManager;
      if (!manager) throw new Error(config.lang === "en" ? "Emulator is not ready" : "Giả lập chưa sẵn sàng");
      manager.loadState(new Uint8Array(await file.arrayBuffer()));
      event.target.value = "";
      showNotice(config.lang === "en" ? "Save state loaded" : "Đã nạp save state");
    } catch (error) { showNotice(error.message || String(error), true); }
  });

  const slotPanel = document.getElementById("slotPanel");
  const slotDatabase = () => new Promise((resolve, reject) => {
    const request = indexedDB.open("an3-arcade-save-slots", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("states", {keyPath: "id"});
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("save slot storage unavailable"));
  });
  const slotTransaction = async (mode, action) => {
    const database = await slotDatabase();
    return new Promise((resolve, reject) => {
      const request = action(database.transaction("states", mode).objectStore("states"));
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error("save slot storage failed"));
    }).finally(() => database.close());
  };
  const slotId = slot => `${config.slug}:slot:${slot}`;
  const slotGet = slot => slotTransaction("readonly", store => store.get(slotId(slot)));
  const slotPut = item => slotTransaction("readwrite", store => store.put(item));
  const slotStamp = time => new Intl.DateTimeFormat(config.lang === "en" ? "en-GB" : "vi-VN", {dateStyle:"short", timeStyle:"short"}).format(new Date(time));
  const refreshSlots = async () => {
    if (!slotPanel) return;
    const states = await Promise.all([...slotPanel.querySelectorAll("[data-slot]")].map(async row => {
      const slot = Number(row.dataset.slot);
      const state = await slotGet(slot);
      row.querySelector("small").textContent = state ? slotStamp(state.updatedAt) : (config.lang === "en" ? "Empty" : "Trống");
      row.querySelector("[data-load-slot]").disabled = !state;
      return state;
    })).catch(error => { showNotice(error.message || String(error), true); return []; });
    const latest = states.filter(Boolean).sort((a,b) => b.updatedAt-a.updatedAt)[0];
    if (saveStatus) saveStatus.textContent = latest ? (config.lang === "en" ? "Saved on this device" : "Đã lưu trên thiết bị") : (config.lang === "en" ? "No save on this device" : "Chưa có save trên thiết bị");
  };
  const saveSlot = async slot => {
    const state = window.EJS_emulator?.gameManager?.getState();
    if (!state?.byteLength) throw new Error(config.lang === "en" ? "Save state is not ready" : "Save state chưa sẵn sàng");
    const bytes = state instanceof Uint8Array ? state : new Uint8Array(state);
    await slotPut({id: slotId(slot), state: new Blob([bytes], {type:"application/octet-stream"}), updatedAt: Date.now()});
    await refreshSlots();
    showNotice(config.lang === "en" ? `Saved to slot ${slot}` : `Đã lưu vào slot ${slot}`);
  };
  const loadSlot = async slot => {
    const saved = await slotGet(slot);
    const manager = window.EJS_emulator?.gameManager;
    if (!saved?.state || !manager) throw new Error(config.lang === "en" ? "Save slot is unavailable" : "Save slot chưa sẵn sàng");
    manager.loadState(new Uint8Array(await saved.state.arrayBuffer()));
    showNotice(config.lang === "en" ? `Loaded slot ${slot}` : `Đã nạp slot ${slot}`);
  };
  document.getElementById("slotMenu")?.addEventListener("click", () => {
    if (!slotPanel) return;
    panel?.classList.remove("open");
    document.getElementById("playerControls")?.setAttribute("aria-expanded","false");
    slotPanel.hidden = !slotPanel.hidden;
    document.getElementById("slotMenu")?.setAttribute("aria-expanded", String(!slotPanel.hidden));
    if (!slotPanel.hidden) { refreshSlots();document.getElementById("closeSlots")?.focus(); }
  });
  document.getElementById("closeSlots")?.addEventListener("click", () => { if (slotPanel) slotPanel.hidden = true;const trigger=document.getElementById("slotMenu");trigger?.setAttribute("aria-expanded","false");trigger?.focus(); });
  slotPanel?.querySelectorAll("[data-save-slot]").forEach(button => button.addEventListener("click", () => saveSlot(Number(button.dataset.saveSlot)).catch(error => showNotice(error.message || String(error), true))));
  slotPanel?.querySelectorAll("[data-load-slot]").forEach(button => button.addEventListener("click", () => loadSlot(Number(button.dataset.loadSlot)).catch(error => showNotice(error.message || String(error), true))));
  refreshSlots();

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
  const padDefaults = ndsPad ? ndsDefaults : defaults;
  let orientation = innerWidth > innerHeight ? "landscape" : "portrait";
  const key = () => `an3-pad-v${ndsPad ? 4 : 3}:${config.system}:${orientation}`;
  const read = (name, fallback={}) => { try { return JSON.parse(localStorage.getItem(name)) || fallback; } catch (_) { return fallback; } };
  let positions = {...padDefaults[orientation], ...read(key())};
  const settingsKey = ndsPad ? "an3-pad-settings-v2:nds" : "an3-pad-settings-v1";
  const defaultSettings = ndsPad ? {scale:1,opacity:.48,visible:true,sizes:{dpad:1.4,start:.7,select:.7}} : {scale:1,opacity:.82,visible:true,sizes:{}};
  const storedSettings = read(settingsKey);
  const settings = {...defaultSettings,...storedSettings,sizes:{...defaultSettings.sizes,...(storedSettings.sizes || {})}};
  const clamp = (value,min,max) => Math.max(min,Math.min(max,value));
  const controlScale = id => clamp(Number(settings.sizes[id] ?? settings.scale) || 1,.7,1.4);
  const saveLayout = () => localStorage.setItem(key(),JSON.stringify(positions));
  const saveSettings = () => localStorage.setItem(settingsKey,JSON.stringify(settings));
  const input = (index,value) => {
    try { window.EJS_emulator?.gameManager?.simulateInput(0,index,value); } catch (_) {}
  };
  const place = element => {
    const point=positions[element.dataset.id];let x=point.x,y=point.y;
    if(padRoot.clientWidth<=480&&element.firstElementChild){const scale=controlScale(element.dataset.id),halfWidth=(element.firstElementChild.offsetWidth*scale/2)+1,halfHeight=(element.firstElementChild.offsetHeight*scale/2)+1;x=clamp(x,halfWidth/padRoot.clientWidth*100,100-halfWidth/padRoot.clientWidth*100);y=clamp(y,halfHeight/padRoot.clientHeight*100,100-halfHeight/padRoot.clientHeight*100);}
    element.style.left=`${x}%`;element.style.top=`${y}%`;
  };
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
    const move=e=>{const rect=padRoot.getBoundingClientRect();const mx=Math.min(16,700/rect.width),my=Math.min(16,700/rect.height);positions[element.dataset.id]={x:Math.round(clamp((e.clientX-rect.left)/rect.width*100,mx,100-mx)*10)/10,y:Math.round(clamp((e.clientY-rect.top)/rect.height*100,my,100-my)*10)/10};place(element);};
    const up=()=>{saveLayout();element.removeEventListener("pointermove",move);element.removeEventListener("pointerup",up);element.removeEventListener("pointercancel",up);};
    element.addEventListener("pointermove",move);element.addEventListener("pointerup",up);element.addEventListener("pointercancel",up);
  });
  const makeButton=(id,label,index)=>{const wrap=document.createElement("div");wrap.className="tvCtrl";wrap.dataset.id=id;wrap.innerHTML=`<div class="tvBtn ${label.length>1?"small":""}">${label}</div>`;bindDrag(wrap);bindInput(wrap,index);return wrap;};
  const makeDpad=()=>{const wrap=document.createElement("div"),labels=config.lang==="en"?{up:"Up",down:"Down",left:"Left",right:"Right"}:{up:"Lên",down:"Xuống",left:"Trái",right:"Phải"};wrap.className="tvCtrl";wrap.dataset.id="dpad";wrap.innerHTML=`<div class="tvDpad"><button class="up" aria-label="${labels.up}"><img src="/static/ui-chevron-up.svg" alt=""></button><button class="down" aria-label="${labels.down}"><img src="/static/ui-chevron-down.svg" alt=""></button><button class="left" aria-label="${labels.left}"><img src="/static/ui-chevron-left.svg" alt=""></button><button class="right" aria-label="${labels.right}"><img src="/static/ui-chevron-right.svg" alt=""></button></div>`;bindDrag(wrap);[[".up",4],[".down",5],[".left",6],[".right",7]].forEach(([selector,index])=>bindInput(wrap.querySelector(selector),index));return wrap;};
  const padTarget = document.getElementById("padTarget");
  const padSize = document.getElementById("padSize");
  const padSizeValue = document.getElementById("padSizeValue");
  const touchToggle = document.getElementById("toggleTouch");
  const applyControlSizes = () => padRoot.querySelectorAll(".tvCtrl").forEach(control => control.style.setProperty("--control-scale",controlScale(control.dataset.id)));
  const syncPadSize = () => {
    if (!padTarget || !padSize) return;
    const value=Math.round(controlScale(padTarget.value)*100);
    padSize.value=value;
    if(padSizeValue){padSizeValue.value=`${value}%`;padSizeValue.textContent=`${value}%`;}
  };
  const applySettings=()=>{
    padRoot.style.setProperty("--pad-scale",clamp(Number(settings.scale)||defaultSettings.scale,.7,1.4));
    padRoot.style.setProperty("--pad-opacity",clamp(Number(settings.opacity)||defaultSettings.opacity,.3,1));
    const visible=customPad&&settings.visible!==false;
    padRoot.classList.toggle("show",visible);
    stage?.classList.toggle("pad-overlay",visible);
    document.body.classList.toggle("pad-overlay",visible);
    applyControlSizes();padRoot.querySelectorAll(".tvCtrl").forEach(place);syncPadSize();
    const opacity=document.getElementById("padOpacity");if(opacity)opacity.value=Math.round(settings.opacity*100);
    if(touchToggle){touchToggle.setAttribute("aria-pressed",String(visible));touchToggle.classList.toggle("is-on",visible);touchToggle.title=visible?(config.lang==="en"?"Hide virtual controls":"Ẩn phím ảo"):(config.lang==="en"?"Show virtual controls":"Hiện phím ảo");}
  };
  if (customPad) {
    const controls=[makeDpad(),makeButton("a","A",8),makeButton("b","B",0),makeButton("start","Start",3),makeButton("select","Select",2)];
    if(config.system==="gba")controls.push(makeButton("l","L",10),makeButton("r","R",11));
    if(ndsPad)controls.push(makeButton("x","X",9),makeButton("y","Y",1),makeButton("l","L",10),makeButton("r","R",11));
    controls.forEach(control=>{padRoot.appendChild(control);place(control);});applySettings();
  }
  document.getElementById("emulatorMenu")?.addEventListener("click",()=>{showHints();panel?.classList.remove("open");document.getElementById("playerControls")?.setAttribute("aria-expanded","false");try{window.EJS_emulator?.menu?.toggle()}catch(_){}});
  document.getElementById("playerControls")?.addEventListener("click",event=>{showHints();if(customPad){if(slotPanel){slotPanel.hidden=true;document.getElementById("slotMenu")?.setAttribute("aria-expanded","false");}const open=panel.classList.toggle("open");event.currentTarget.setAttribute("aria-expanded",String(open));if(open)document.getElementById("closePad")?.focus();}else try{window.EJS_emulator?.menu?.toggle()}catch(_){}});
  document.getElementById("closePad")?.addEventListener("click",()=>{padRoot.classList.remove("edit");saveLayout();panel.classList.remove("open");const trigger=document.getElementById("playerControls");trigger?.setAttribute("aria-expanded","false");trigger?.focus()});
  document.getElementById("editPad")?.addEventListener("click",event=>{const editing=padRoot.classList.toggle("edit");event.currentTarget.textContent=editing?(config.lang==="en"?"Done":"Xong"):(config.lang==="en"?"Move":"Kéo thả");if(!editing)saveLayout();});
  const togglePad=()=>{settings.visible=settings.visible===false;saveSettings();applySettings();};
  touchToggle?.addEventListener("click",togglePad);
  document.getElementById("togglePad")?.addEventListener("click",togglePad);
  padTarget?.addEventListener("change",syncPadSize);
  padSize?.addEventListener("input",event=>{if(!padTarget)return;settings.sizes[padTarget.value]=Number(event.target.value)/100;saveSettings();applyControlSizes();padRoot.querySelectorAll(".tvCtrl").forEach(place);syncPadSize();});
  document.getElementById("padOpacity")?.addEventListener("input",event=>{settings.opacity=Number(event.target.value)/100;saveSettings();applySettings();});
  document.getElementById("resetPad")?.addEventListener("click",()=>{localStorage.removeItem(key());positions={...padDefaults[orientation]};settings.scale=defaultSettings.scale;settings.opacity=defaultSettings.opacity;settings.visible=true;settings.sizes={...defaultSettings.sizes};saveSettings();padRoot.querySelectorAll(".tvCtrl").forEach(place);applySettings();});
  document.addEventListener("keydown",event=>{if(event.key!=="Escape")return;if(panel?.classList.contains("open")){event.preventDefault();document.getElementById("closePad")?.click();}else if(slotPanel&&!slotPanel.hidden){event.preventDefault();document.getElementById("closeSlots")?.click();}});
  let resizeTimer;addEventListener("resize",()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{const next=innerWidth>innerHeight?"landscape":"portrait";if(next!==orientation){saveLayout();orientation=next;positions={...padDefaults[orientation],...read(key())};}padRoot.querySelectorAll(".tvCtrl").forEach(place);applySettings();},160)});
  document.addEventListener("visibilitychange",()=>{if(document.hidden)[0,2,3,4,5,6,7,8,10,11].forEach(index=>input(index,0))});
  boot();
})();
