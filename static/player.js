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
  const threadedCore = ["psp","3ds"].includes(config.system);
  const webgl2Required = ["psp","3ds"].includes(config.system);
  const stage = document.querySelector(".player-stage");
  const loading = document.getElementById("loading");
  const loadingText = document.getElementById("loadingText");
  const loadingBar = document.getElementById("loadingBar");
  const loadingPct = document.getElementById("loadingPct");
  const notice = document.getElementById("playerNotice");
  const showNotice = (message, error = false) => {
    notice.textContent = message;
    notice.className = error ? "player-notice show error" : "player-notice show";
    clearTimeout(showNotice.timer);
    showNotice.timer = setTimeout(() => { notice.className = "player-notice"; }, 2800);
  };
  const setProgress = (value, text) => {
    const pct = Math.max(0, Math.min(100, Math.round(value)));
    loadingBar.style.width = `${pct}%`;
    loadingPct.textContent = `${pct}%`;
    if (text) loadingText.textContent = text;
  };
  let preloadReported = false;
  const reportPreload = (ok, error = "") => {
    if (config.mode !== "preload" || preloadReported) return;
    preloadReported = true;
    window.parent?.postMessage({type:"an3-core-preload", system:config.system, ok, error}, location.origin);
  };
  const finishLoading = () => { setProgress(100, config.lang === "en" ? "Ready" : "Sẵn sàng"); reportPreload(true); setTimeout(() => loading.classList.add("done"), 350); };
  const failLoading = error => { const message=error.message || String(error);loadingText.textContent=message;loadingText.style.color="#ef6a67";reportPreload(false,message); };

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
      const coreUsesWebgl2=webgl2 && Boolean(report?.options?.defaultWebGL2 || webgl2Required);
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
    else stage.requestFullscreen?.();
  });

  if (config.mode === "html5") {
    document.querySelector(".custom-frame")?.addEventListener("load", finishLoading);
    document.getElementById("playerControls")?.remove();
    setProgress(50, config.lang === "en" ? "Loading game" : "Đang tải game");
    return;
  }

  const customPad = ["gba", "gb", "nds"].includes(config.system);
  const ndsPad = config.system === "nds";
  document.documentElement.classList.toggle("custom-pad", customPad);
  stage.classList.toggle("nds-stage", ndsPad);

  const dispatchNdsMouse = (canvas, type, source, buttons) => {
    const rect=canvas.getBoundingClientRect(),width=canvas.width||rect.width,height=canvas.height||rect.height;
    const clientX=Number.isFinite(source.clientX) ? source.clientX : source.pageX-window.scrollX;
    const clientY=Number.isFinite(source.clientY) ? source.clientY : source.pageY-window.scrollY;
    const cssX=Math.max(0,Math.min(rect.width,clientX-rect.left)),cssY=Math.max(0,Math.min(rect.height,clientY-rect.top));
    const offsetX=rect.width ? cssX*width/rect.width : 0,offsetY=rect.height ? cssY*height/rect.height : 0;
    const event=new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX,clientY,screenX:source.screenX||clientX,screenY:source.screenY||clientY,button:0,buttons});
    // EmulatorJS reads local canvas coordinates. Synthetic MouseEvents otherwise
    // expose offsetX/offsetY as 0, which traps the DS pointer in the top-left.
    for (const [name,value] of [["offsetX",offsetX],["offsetY",offsetY],["layerX",offsetX],["layerY",offsetY]]) {
      try { Object.defineProperty(event,name,{value,writable:false,enumerable:true}); } catch (_) {}
    }
    canvas.dispatchEvent(event);
  };
  const bindNdsTouch = canvas => {
    if (!ndsPad || canvas.dataset.an3NdsTouch === "1") return;
    canvas.dataset.an3NdsTouch="1";
    let pointerId=null;
    let touchId=null;
    const isTouchPointer=event=>event.pointerType==="touch" || event.pointerType==="";
    const findTouch=event=>[...(event.changedTouches||[])].find(touch=>touch.identifier===touchId);
    if ("PointerEvent" in window) {
      canvas.addEventListener("pointerdown",event=>{if(!isTouchPointer(event) || pointerId!==null)return;pointerId=event.pointerId;canvas.focus?.({preventScroll:true});try{canvas.setPointerCapture(pointerId);}catch(_){}dispatchNdsMouse(canvas,"mousedown",event,1);},true);
      canvas.addEventListener("pointermove",event=>{if(!isTouchPointer(event) || event.pointerId!==pointerId)return;event.preventDefault();dispatchNdsMouse(canvas,"mousemove",event,1);},true);
      const release=event=>{if(!isTouchPointer(event) || event.pointerId!==pointerId)return;dispatchNdsMouse(canvas,"mouseup",event,0);try{canvas.releasePointerCapture(pointerId);}catch(_){}pointerId=null;};
      canvas.addEventListener("pointerup",release,true);canvas.addEventListener("pointercancel",release,true);
    }
    // Keep a direct TouchEvent fallback even on browsers exposing PointerEvent.
    // Some Android WebViews expose PointerEvent but omit pointer dispatch for canvas.
    canvas.addEventListener("touchstart",event=>{if(pointerId!==null || touchId!==null || !event.changedTouches?.length)return;const touch=event.changedTouches[0];touchId=touch.identifier;event.preventDefault();dispatchNdsMouse(canvas,"mousedown",touch,1);},{capture:true,passive:false});
    canvas.addEventListener("touchmove",event=>{const touch=findTouch(event);if(!touch || pointerId!==null)return;event.preventDefault();dispatchNdsMouse(canvas,"mousemove",touch,1);},{capture:true,passive:false});
    const releaseTouch=event=>{const touch=findTouch(event);if(!touch || pointerId!==null)return;event.preventDefault();dispatchNdsMouse(canvas,"mouseup",touch,0);touchId=null;};
    canvas.addEventListener("touchend",releaseTouch,{capture:true,passive:false});canvas.addEventListener("touchcancel",releaseTouch,{capture:true,passive:false});
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
    new MutationObserver(protectNdsCanvas).observe(gameRoot,{subtree:true,childList:true,attributes:true,attributeFilter:["class"]});
    protectNdsCanvas();
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

  async function boot() {
    try {
      if (webgl2Required && !document.createElement("canvas").getContext("webgl2")) throw new Error(config.lang === "en" ? "This core requires WebGL 2." : "Core này cần WebGL 2.");
      if (threadedCore && (!crossOriginIsolated || typeof SharedArrayBuffer !== "function")) throw new Error(config.lang === "en" ? "This core requires SharedArrayBuffer support." : "Core này cần trình duyệt hỗ trợ SharedArrayBuffer an toàn.");
      const file = await fetchGame();
      setProgress(86, config.lang === "en" ? "Loading emulator" : "Đang tải giả lập");
      let gameStarted = false;
      window.EJS_player = "#game";
      window.EJS_core = emulatorSystem;
      window.EJS_defaultOptions = ndsPad ? {retroarch_core:"melonds"} : undefined;
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
      window.EJS_onGameStart = () => { gameStarted=true;protectNdsCanvas();finishLoading(); };
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
        else if (!ndsPad && window.EJS_emulator?.gameManager) { clearInterval(ready);finishLoading(); }
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
    await Promise.all([...slotPanel.querySelectorAll("[data-slot]")].map(async row => {
      const slot = Number(row.dataset.slot);
      const state = await slotGet(slot);
      row.querySelector("small").textContent = state ? slotStamp(state.updatedAt) : (config.lang === "en" ? "Empty" : "Trống");
      row.querySelector("[data-load-slot]").disabled = !state;
    })).catch(error => showNotice(error.message || String(error), true));
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
    slotPanel.hidden = !slotPanel.hidden;
    if (!slotPanel.hidden) refreshSlots();
  });
  document.getElementById("closeSlots")?.addEventListener("click", () => { if (slotPanel) slotPanel.hidden = true; });
  slotPanel?.querySelectorAll("[data-save-slot]").forEach(button => button.addEventListener("click", () => saveSlot(Number(button.dataset.saveSlot)).catch(error => showNotice(error.message || String(error), true))));
  slotPanel?.querySelectorAll("[data-load-slot]").forEach(button => button.addEventListener("click", () => loadSlot(Number(button.dataset.loadSlot)).catch(error => showNotice(error.message || String(error), true))));
  refreshSlots();

  const padRoot = document.getElementById("tvPad");
  const panel = document.getElementById("padPanel");
  const hints = document.getElementById("playerHints");
  const showHints = () => {
    if (!hints) return;
    hints.classList.add("show");
    clearTimeout(showHints.timer);
    showHints.timer = setTimeout(() => hints.classList.remove("show"), 3000);
  };
  const isTouch = matchMedia("(pointer:coarse)").matches || navigator.maxTouchPoints > 0;
  const defaults = {
    portrait:{dpad:{x:19,y:79},a:{x:86,y:73},b:{x:73,y:82},x:{x:89,y:60},y:{x:74,y:63},l:{x:15,y:52},r:{x:85,y:52},start:{x:39,y:61},select:{x:62,y:61}},
    landscape:{dpad:{x:13,y:69},a:{x:92,y:57},b:{x:82,y:73},x:{x:92,y:42},y:{x:81,y:44},l:{x:13,y:33},r:{x:87,y:33},start:{x:39,y:84},select:{x:61,y:84}}
  };
  const ndsDefaults = {
    portrait:{dpad:{x:19,y:76},a:{x:57,y:78},b:{x:83,y:78},x:{x:83,y:64},y:{x:57,y:64},l:{x:15,y:52},r:{x:85,y:52},start:{x:39,y:61},select:{x:62,y:61}},
    landscape:{dpad:{x:13,y:69},a:{x:90,y:62},b:{x:80,y:76},x:{x:90,y:46},y:{x:80,y:46},l:{x:13,y:31},r:{x:87,y:31},start:{x:40,y:84},select:{x:60,y:84}}
  };
  const padDefaults = ndsPad ? ndsDefaults : defaults;
  let orientation = innerWidth > innerHeight ? "landscape" : "portrait";
  const key = () => `an3-pad-v${ndsPad ? 4 : 3}:${config.system}:${orientation}`;
  const read = (name, fallback={}) => { try { return JSON.parse(localStorage.getItem(name)) || fallback; } catch (_) { return fallback; } };
  let positions = {...padDefaults[orientation], ...read(key())};
  const settingsKey = ndsPad ? "an3-pad-settings-v2:nds" : "an3-pad-settings-v1";
  const defaultSettings = ndsPad ? {scale:1,opacity:.48,visible:true} : {scale:1,opacity:.82,visible:true};
  const settings = {...defaultSettings,...read(settingsKey)};
  const clamp = (value,min,max) => Math.max(min,Math.min(max,value));
  const saveLayout = () => localStorage.setItem(key(),JSON.stringify(positions));
  const saveSettings = () => localStorage.setItem(settingsKey,JSON.stringify(settings));
  const input = (index,value) => {
    try { window.EJS_emulator?.gameManager?.simulateInput(0,index,value); } catch (_) {}
  };
  const place = element => { const point=positions[element.dataset.id]; element.style.left=`${point.x}%`; element.style.top=`${point.y}%`; };
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
  const makeDpad=()=>{const wrap=document.createElement("div");wrap.className="tvCtrl";wrap.dataset.id="dpad";wrap.innerHTML='<div class="tvDpad"><button class="up">▲</button><button class="down">▼</button><button class="left">◀</button><button class="right">▶</button></div>';bindDrag(wrap);[[".up",4],[".down",5],[".left",6],[".right",7]].forEach(([selector,index])=>bindInput(wrap.querySelector(selector),index));return wrap;};
  const applySettings=()=>{padRoot.style.setProperty("--pad-scale",clamp(Number(settings.scale)||defaultSettings.scale,.7,1.35));padRoot.style.setProperty("--pad-opacity",clamp(Number(settings.opacity)||defaultSettings.opacity,.3,1));padRoot.classList.toggle("show",customPad&&(isTouch||innerWidth<=900)&&settings.visible!==false);document.getElementById("padSize").value=Math.round(settings.scale*100);document.getElementById("padOpacity").value=Math.round(settings.opacity*100);};
  if (customPad) {
    const controls=[makeDpad(),makeButton("a","A",8),makeButton("b","B",0),makeButton("start","Start",3),makeButton("select","Select",2)];
    if(config.system==="gba")controls.push(makeButton("l","L",10),makeButton("r","R",11));
    if(ndsPad)controls.push(makeButton("x","X",9),makeButton("y","Y",1),makeButton("l","L",10),makeButton("r","R",11));
    controls.forEach(control=>{padRoot.appendChild(control);place(control);});applySettings();
  }
  document.getElementById("emulatorMenu")?.addEventListener("click",()=>{showHints();try{window.EJS_emulator?.menu?.toggle()}catch(_){}});
  document.getElementById("playerControls")?.addEventListener("click",()=>{showHints();if(customPad)panel.classList.toggle("open");else try{window.EJS_emulator?.menu?.toggle()}catch(_){}});
  document.getElementById("closePad")?.addEventListener("click",()=>{padRoot.classList.remove("edit");saveLayout();panel.classList.remove("open")});
  document.getElementById("editPad")?.addEventListener("click",event=>{const editing=padRoot.classList.toggle("edit");event.currentTarget.textContent=editing?(config.lang==="en"?"Done":"Xong"):(config.lang==="en"?"Move":"Kéo thả");if(!editing)saveLayout();});
  document.getElementById("togglePad")?.addEventListener("click",()=>{settings.visible=settings.visible===false;saveSettings();applySettings();});
  document.getElementById("padSize")?.addEventListener("input",event=>{settings.scale=Number(event.target.value)/100;saveSettings();applySettings();});
  document.getElementById("padOpacity")?.addEventListener("input",event=>{settings.opacity=Number(event.target.value)/100;saveSettings();applySettings();});
  document.getElementById("resetPad")?.addEventListener("click",()=>{localStorage.removeItem(key());positions={...padDefaults[orientation]};Object.assign(settings,defaultSettings);saveSettings();padRoot.querySelectorAll(".tvCtrl").forEach(place);applySettings();});
  let resizeTimer;addEventListener("resize",()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{const next=innerWidth>innerHeight?"landscape":"portrait";if(next!==orientation){saveLayout();orientation=next;positions={...padDefaults[orientation],...read(key())};}padRoot.querySelectorAll(".tvCtrl").forEach(place);},160)});
  document.addEventListener("visibilitychange",()=>{if(document.hidden)[0,2,3,4,5,6,7,8,10,11].forEach(index=>input(index,0))});
  boot();
})();
