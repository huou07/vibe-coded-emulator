(() => {
  const systems = {
    gb:{label:"Game Boy / Color",channel:"stable"}, gba:{label:"Game Boy Advance",channel:"stable"}, nds:{label:"Nintendo DS",channel:"stable"}, "3ds":{label:"Nintendo 3DS",channel:"latest"}, nes:{label:"NES / Famicom",channel:"stable"}, snes:{label:"SNES / Super Famicom",channel:"stable"}, n64:{label:"Nintendo 64",channel:"stable"}, psx:{label:"PlayStation",channel:"stable"}, psp:{label:"PSP",channel:"stable"}, segaMD:{label:"Mega Drive / Genesis",channel:"stable"}, segaMS:{label:"Master System",channel:"stable"}, segaGG:{label:"Game Gear",channel:"stable"}, sega32x:{label:"Sega 32X",channel:"stable"}, segaCD:{label:"Sega CD",channel:"stable"}, segaSaturn:{label:"Sega Saturn",channel:"stable"}, arcade:{label:"Arcade / FBNeo",channel:"stable"}, "3do":{label:"3DO",channel:"stable"}, atari2600:{label:"Atari 2600",channel:"stable"}, atari7800:{label:"Atari 7800",channel:"stable"}, jaguar:{label:"Atari Jaguar",channel:"stable"}, lynx:{label:"Atari Lynx",channel:"stable"}, pce:{label:"PC Engine",channel:"stable"}, amiga:{label:"Amiga",channel:"stable"}, c64:{label:"Commodore 64",channel:"stable"}, doom:{label:"DOOM / PrBoom",channel:"stable"}, html5:{label:"HTML5",channel:"native"}
  };
  const extensionMap = {
    ".gb":"gb", ".gbc":"gb", ".gba":"gba", ".raw":"gba", ".nds":"nds", ".3ds":"3ds", ".cci":"3ds", ".cxi":"3ds", ".app":"3ds", ".nes":"nes", ".fds":"nes", ".sfc":"snes", ".smc":"snes", ".fig":"snes", ".swc":"snes", ".n64":"n64", ".z64":"n64", ".v64":"n64", ".psx":"psx", ".cso":"psp", ".sms":"segaMS", ".gg":"segaGG", ".32x":"sega32x", ".md":"segaMD", ".gen":"segaMD", ".smd":"segaMD", ".a26":"atari2600", ".a78":"atari7800", ".j64":"jaguar", ".jag":"jaguar", ".lnx":"lynx", ".pce":"pce", ".sgx":"pce", ".adf":"amiga", ".adz":"amiga", ".dms":"amiga", ".ipf":"amiga", ".hdf":"amiga", ".lha":"amiga", ".d64":"c64", ".g64":"c64", ".t64":"c64", ".tap":"c64", ".crt":"c64", ".prg":"c64", ".wad":"doom", ".iwad":"doom", ".pk3":"doom", ".pk4":"doom", ".html":"html5"
  };
  const hints = {"3ds":["3ds","citra","azahar"],nds:["nds","nintendo-ds","melonds"],gba:["gba","gameboy-advance"],gb:["gbc","gameboy-color","game-boy"],psp:["psp"],psx:["ps1","psx","playstation"],n64:["n64"],snes:["snes","super-nintendo"],nes:["nes","famicom"],segaMD:["genesis","megadrive"],segaSaturn:["saturn"],segaCD:["segacd","mega-cd"],arcade:["arcade","fbneo","mame"]};
  const lang = document.documentElement.lang === "en" ? "en" : "vi";
  const text = (vi,en) => lang === "en" ? en : vi;
  const dbName = "an3-arcade-offline";
  const storeName = "games";
  const normalized = value => String(value || "").toLowerCase().replace(/[_\s]+/g,"-");

  const openDatabase = () => new Promise((resolve,reject) => {
    const request = indexedDB.open(dbName, 1);
    request.onupgradeneeded = () => { const store = request.result.createObjectStore(storeName,{keyPath:"id"}); store.createIndex("addedAt","addedAt"); };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("offline storage unavailable"));
  });
  const transaction = async (mode, action) => {
    const database = await openDatabase();
    return new Promise((resolve,reject) => {
      const tx=database.transaction(storeName,mode),request=action(tx.objectStore(storeName));let result;
      request.onsuccess=()=>{result=request.result;};
      request.onerror=()=>reject(request.error || new Error("offline storage failed"));
      tx.oncomplete=()=>resolve(result);
      tx.onerror=()=>reject(tx.error || new Error("offline storage failed"));
      tx.onabort=()=>reject(tx.error || new Error("offline storage was interrupted"));
    }).finally(() => database.close());
  };
  const get = id => transaction("readonly",store => store.get(id));
  const all = async () => (await transaction("readonly",store => store.getAll())).sort((a,b)=>b.addedAt-a.addedAt);
  const put = item => transaction("readwrite",store => store.put(item));
  const remove = id => transaction("readwrite",store => store.delete(id));
  window.AN3OfflineLibrary = {get};

  const inferName = name => {
    const lower = normalized(name);
    const extension = lower.includes(".") ? lower.slice(lower.lastIndexOf(".")) : "";
    if (extensionMap[extension]) return extensionMap[extension];
    for (const [system, words] of Object.entries(hints)) if (words.some(word => new RegExp(`(^|[-.])${word}($|[-.])`).test(lower))) return system;
    if ([".iso",".cso",".elf"].includes(extension) && /(^|[-.])psp($|[-.])/.test(lower)) return "psp";
    if ([".cue",".chd",".pbp",".img"].includes(extension) && /(^|[-.])(psx|ps1|playstation)($|[-.])/.test(lower)) return "psx";
    return null;
  };
  const zipNames = async file => {
    const start = Math.max(0,file.size - 131072);
    const bytes = new Uint8Array(await file.slice(start).arrayBuffer());
    for (let cursor = bytes.length - 22; cursor >= 0; cursor -= 1) {
      if (bytes[cursor] !== 0x50 || bytes[cursor + 1] !== 0x4b || bytes[cursor + 2] !== 0x05 || bytes[cursor + 3] !== 0x06) continue;
      const view = new DataView(bytes.buffer, bytes.byteOffset + cursor);
      const count = view.getUint16(10,true), directoryOffset = view.getUint32(16,true);
      const directory = new Uint8Array(await file.slice(directoryOffset, directoryOffset + Math.min(file.size-directoryOffset, 4*1024*1024)).arrayBuffer());
      const names = []; let offset = 0;
      for (let index=0; index<count && offset+46<=directory.length; index+=1) {
        if (directory[offset]!==0x50 || directory[offset+1]!==0x4b || directory[offset+2]!==0x01 || directory[offset+3]!==0x02) break;
        const entry = new DataView(directory.buffer,directory.byteOffset+offset);
        const nameLength=entry.getUint16(28,true), extraLength=entry.getUint16(30,true), commentLength=entry.getUint16(32,true);
        names.push(new TextDecoder().decode(directory.slice(offset+46,offset+46+nameLength)));
        offset += 46 + nameLength + extraLength + commentLength;
      }
      return names;
    }
    return [];
  };
  const inferFile = async file => {
    if (file.name.toLowerCase().endsWith(".zip")) {
      const names = await zipNames(file).catch(() => []);
      if (names.some(name => /(^|\/)index\.html$/i.test(name))) return "html5";
      const detected = [...new Set(names.map(inferName).filter(Boolean))];
      if (detected.length === 1) return detected[0];
    }
    return inferName(file.name);
  };
  const cleanTitle = name => name.replace(/\.[^.]+$/,"").replace(/[_-]+/g," ").trim().slice(0,120) || text("Game ngoại tuyến","Offline game");
  const formatSize = bytes => bytes < 1024*1024 ? `${Math.max(1,Math.round(bytes/1024))} KB` : `${(bytes/1024/1024).toFixed(1)} MB`;
  const showToast = (message,error=false) => { const toast=document.getElementById("toast"); if(!toast)return; toast.className=error?"show error":"show";toast.textContent=message;clearTimeout(showToast.timer);showToast.timer=setTimeout(()=>{toast.className="";},3500); };
  const createOfflineId = () => {
    const secureCrypto=globalThis.crypto;
    if (typeof secureCrypto?.randomUUID === "function") return secureCrypto.randomUUID();
    if (typeof secureCrypto?.getRandomValues === "function") {
      const bytes=secureCrypto.getRandomValues(new Uint8Array(16));
      bytes[6]=(bytes[6]&0x0f)|0x40;bytes[8]=(bytes[8]&0x3f)|0x80;
      const hex=[...bytes].map(value=>value.toString(16).padStart(2,"0"));
      return `${hex.slice(0,4).join("")}-${hex.slice(4,6).join("")}-${hex.slice(6,8).join("")}-${hex.slice(8,10).join("")}-${hex.slice(10).join("")}`;
    }
    return `an3-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
  };

  const slotRows = () => Array.from({length:5},(_,index) => { const slot=index+1; return `<div class="save-slot" data-slot="${slot}"><strong>${text("Slot","Slot")} ${slot}</strong><small>${text("Trống","Empty")}</small><button data-save-slot="${slot}">${text("Lưu","Save")}</button><button data-load-slot="${slot}" disabled>${text("Nạp","Load")}</button></div>`; }).join("");
  const playerMarkup = () => `<div class="player-toolbar" role="toolbar" aria-label="${text("Điều khiển trình phát","Player controls")}">
    <a href="/offline" title="${text("Quay lại","Back")}" aria-label="${text("Quay lại thư viện ngoại tuyến","Back to offline library")}">←</a><span class="player-title"></span>
    <button id="fullscreen" type="button" title="${text("Toàn màn hình","Fullscreen")}" aria-label="${text("Toàn màn hình","Fullscreen")}">⛶</button>
    <button id="emulatorMenu" type="button" title="${text("Menu giả lập","Emulator menu")}" aria-label="${text("Menu giả lập","Emulator menu")}">☰</button>
    <button id="saveState" type="button" title="${text("Tải save state","Download save state")}" aria-label="${text("Tải save state","Download save state")}">↓S</button>
    <button id="loadState" type="button" title="${text("Nạp save state","Load save state")}" aria-label="${text("Nạp save state","Load save state")}">↑S</button>
    <input id="stateFile" type="file" accept=".state,.savestate,application/octet-stream" hidden>
    <button id="slotMenu" type="button" title="${text("Save slot","Save slots")}" aria-label="${text("Save slot","Save slots")}">▣</button>
    <button id="playerControls" type="button" title="${text("Điều khiển","Controls")}" aria-label="${text("Điều khiển ảo","Virtual controls")}">⌘</button>
  </div><section class="player-stage"><div id="game"></div><div id="tvPad" aria-label="${text("Bộ điều khiển ảo","Virtual controller")}"></div>
    <div id="playerHints" class="player-hints" aria-live="polite"><span>⛶ ${text("Toàn màn hình","Fullscreen")}</span><span>☰ ${text("Menu giả lập","Emulator menu")}</span><span>↓S ${text("Tải save","Download save")}</span><span>↑S ${text("Nạp save","Load save")}</span><span>⌘ ${text("Chỉnh phím ảo","Virtual controls")}</span></div>
    <div id="playerNotice" class="player-notice" role="status" aria-live="polite"></div><div id="loading" class="loading" role="status" aria-live="polite"><strong id="loadingText">${text("Đang chuẩn bị","Preparing")}</strong><div class="progress" role="progressbar" aria-label="${text("Tiến trình khởi động","Startup progress")}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><i id="loadingBar"></i></div><span id="loadingPct">0%</span></div>
  </section><section id="slotPanel" class="slot-panel" hidden role="dialog" aria-label="${text("Save slot trên thiết bị này","Save slots on this device")}"><header><strong>${text("Save slot trên thiết bị này","Save slots on this device")}</strong><button id="closeSlots" type="button" aria-label="${text("Đóng save slot","Close save slots")}">×</button></header>${slotRows()}</section>
  <section id="padPanel" class="pad-panel" role="dialog" aria-label="${text("Phím ảo","Virtual controls")}"><header><strong>${text("Phím ảo","Virtual controls")}</strong><button id="closePad" type="button" aria-label="${text("Đóng bảng điều khiển ảo","Close virtual controls panel")}">×</button></header><label>${text("Kích thước","Size")}<input id="padSize" type="range" min="70" max="135" step="5"></label><label>${text("Độ mờ","Opacity")}<input id="padOpacity" type="range" min="30" max="100" step="5"></label><div><button id="editPad" type="button">${text("Kéo thả","Move")}</button><button id="togglePad" type="button">${text("Ẩn phím","Hide")}</button><button id="resetPad" type="button">${text("Mặc định","Reset")}</button></div></section>`;

  const playOffline = () => {
    const params = new URLSearchParams(location.search), id=params.get("play"), system=params.get("system");
    if (!id || !systems[system] || system === "html5") return false;
    const main=document.createElement("main"), title=params.get("title") || text("Game ngoại tuyến","Offline game");
    main.className="player-shell";
    main.dataset.player=JSON.stringify({mode:"emulator",title,slug:`offline-${id}`,system,channel:systems[system].channel,downloadName:title,lang,offlineId:id});
    main.innerHTML=playerMarkup(); main.querySelector(".player-title").textContent=title;
    document.body.className="player-page offline-player-page";document.body.replaceChildren(main);document.title=`${title} · Ăn 3 Tô Cơm lãnh địa`;
    return true;
  };

  const primaryCores = {
    gb:"gambatte",gba:"mgba",nds:"melonds","3ds":"azahar",nes:"fceumm",snes:"snes9x",n64:"mupen64plus_next",psx:"pcsx_rearmed",psp:"ppsspp",
    segaMD:"genesis_plus_gx",segaMS:"smsplus",segaGG:"genesis_plus_gx",sega32x:"picodrive",segaCD:"genesis_plus_gx",segaSaturn:"yabause",
    arcade:"fbneo","3do":"opera",atari2600:"stella2014",atari7800:"prosystem",jaguar:"virtualjaguar",lynx:"handy",pce:"mednafen_pce",
    amiga:"puae",c64:"vice_x64sc",doom:"prboom"
  };
  const coreCandidates = system => [primaryCores[system]];
  const coreMarker = system => `an3-offline-core-v7:${systems[system].channel}:${system}`;
  const markCoreReady = system => { try{localStorage.setItem(coreMarker(system),String(Date.now()));}catch(_){} };
  const isCoreFileName = (name,system) => coreCandidates(system).some(core=>name===`${core}-wasm.data` || name===`${core}-legacy-wasm.data` || name===`${core}-thread-wasm.data` || name===`${core}-thread-legacy-wasm.data`);
  const isCoreAsset = (request,system) => {
    const name=decodeURIComponent(new URL(request.url).pathname.split("/").pop() || "");
    return isCoreFileName(name,system) || coreCandidates(system).some(core=>name===`${core}.json` || (core==="ppsspp" && name==="ppsspp-assets.zip"));
  };
  const openCoreDatabase = () => new Promise((resolve,reject) => {
    if (!("indexedDB" in globalThis)) return reject(new Error(text("Trình duyệt không hỗ trợ kho core.","This browser does not support core storage.")));
    const request=indexedDB.open("EmulatorJS-core",1);
    request.onupgradeneeded=()=>{if(!request.result.objectStoreNames.contains("core"))request.result.createObjectStore("core");};
    request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error || new Error("EmulatorJS core storage is unavailable"));
  });
  const indexedCoreEntries = async system => {
    if (!("indexedDB" in globalThis)) return [];
    const database=await openCoreDatabase();
    try {
      return await new Promise((resolve,reject) => {
        const tx=database.transaction("core","readonly"),store=tx.objectStore("core"),keysRequest=store.getAllKeys(),valuesRequest=store.getAll();let keys=[],values=[];
        keysRequest.onsuccess=()=>{keys=keysRequest.result || [];};valuesRequest.onsuccess=()=>{values=valuesRequest.result || [];};
        tx.oncomplete=()=>resolve(keys.map((key,index)=>({key:String(key),bytes:Number(values[index]?.data?.byteLength)||0})).filter(entry=>isCoreFileName(entry.key,system)));
        tx.onerror=()=>reject(tx.error || new Error("Could not inspect EmulatorJS core storage"));tx.onabort=()=>reject(tx.error || new Error("Could not inspect EmulatorJS core storage"));
      });
    } finally { database.close(); }
  };
  const deleteIndexedCoreEntries = async entries => {
    if (!entries.length || !("indexedDB" in globalThis)) return 0;
    const database=await openCoreDatabase(),targets=new Set(entries.map(entry=>entry.key));
    try {
      await new Promise((resolve,reject) => {
        const tx=database.transaction("core","readwrite"),store=tx.objectStore("core"),keysRequest=store.get("?EJS_KEYS!");
        keysRequest.onsuccess=()=>{targets.forEach(key=>store.delete(key));const keys=Array.isArray(keysRequest.result)?keysRequest.result.filter(key=>!targets.has(String(key))):[];store.put(keys,"?EJS_KEYS!");};
        keysRequest.onerror=()=>reject(keysRequest.error || new Error("Could not read the EmulatorJS core index"));
        tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error || new Error("Could not delete the EmulatorJS core"));tx.onabort=()=>reject(tx.error || new Error("Could not delete the EmulatorJS core"));
      });
    } finally { database.close(); }
    return targets.size;
  };
  const inspectCore = async system => {
    const idbEntries=await indexedCoreEntries(system),cacheEntries=[];
    if ("caches" in globalThis) {
      for (const key of await caches.keys()) {
        const cache=await caches.open(key);
        for (const request of await cache.keys()) {
          if (!isCoreAsset(request,system)) continue;
          const response=await cache.match(request);
          let bytes=Number(response?.headers.get("content-length")) || 0;
          if (!bytes && response) bytes=(await response.clone().arrayBuffer()).byteLength;
          cacheEntries.push({key,request,bytes,name:decodeURIComponent(new URL(request.url).pathname.split("/").pop() || "")});
        }
      }
    }
    const core=primaryCores[system];
    const primaryReady=idbEntries.some(entry=>entry.bytes>0 && entry.key.startsWith(`${core}-`) && entry.key.endsWith("-wasm.data")) || cacheEntries.some(entry=>isCoreFileName(entry.name,system) && entry.name.startsWith(`${core}-`));
    return {ready:primaryReady,count:idbEntries.length+cacheEntries.length,bytes:idbEntries.reduce((sum,entry)=>sum+entry.bytes,0),idbEntries,cacheEntries};
  };
  const deleteCore = async system => {
    const state=await inspectCore(system);
    const idbCount=await deleteIndexedCoreEntries(state.idbEntries || []);
    for (const entry of state.cacheEntries || []) await (await caches.open(entry.key)).delete(entry.request);
    try {
      const markers=[];
      for (let index=0;index<localStorage.length;index+=1) {
        const key=localStorage.key(index);
        if (key?.startsWith("an3-offline-core-") && key.endsWith(`:${systems[system].channel}:${system}`)) markers.push(key);
      }
      markers.forEach(key=>localStorage.removeItem(key));
    } catch (_) {}
    return idbCount+(state.cacheEntries?.length || 0);
  };
  const ensureOfflineRuntime = async () => {
    if (!("serviceWorker" in navigator)) return;
    await navigator.serviceWorker.register("/service-worker.js");
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) await new Promise(resolve=>{
      const timer=setTimeout(resolve,2500),changed=()=>{clearTimeout(timer);navigator.serviceWorker.removeEventListener("controllerchange",changed);resolve();};
      navigator.serviceWorker.addEventListener("controllerchange",changed,{once:true});
    });
  };
  const preloadCore = async system => {
    if (navigator.onLine === false) {
      const state=await inspectCore(system);
      if (state.ready) return {count:state.count,verified:false};
      throw new Error(text("Hãy kết nối mạng để tải core lần đầu.","Connect to the internet to download this core first."));
    }
    await ensureOfflineRuntime();
    return new Promise((resolve,reject) => {
      const frame=document.createElement("iframe");let settled=false;
      const cleanup=()=>{clearTimeout(timeout);removeEventListener("message",onMessage);frame.remove();};
      const finish=async (error="")=>{if(settled)return;settled=true;cleanup();if(error){reject(new Error(error));return;}try{const state=await inspectCore(system);if(!state.ready)throw new Error(text("Core tải xong nhưng không lưu được vào trình duyệt.","The core downloaded but could not be saved in this browser."));markCoreReady(system);resolve({count:state.count,verified:true,secureOffline:isSecureContext&&"serviceWorker" in navigator});}catch(failure){reject(failure);}};
      const timeout=setTimeout(()=>finish(text("Hết thời gian tải core. Hãy kiểm tra mạng và thử lại.","Core download timed out. Check the connection and try again.")),120000);
      const onMessage=event=>{
        if(event.origin!==location.origin || event.data?.type!=="an3-core-preload" || event.data.system!==system)return;
        finish(event.data.ok===false?(event.data.error || text("Tải core thất bại.","Core download failed.")):"");
      };
      frame.className="core-preload-frame";frame.title="Core preload";frame.src=`/core-preload/${encodeURIComponent(system)}`;
      addEventListener("message",onMessage);frame.onerror=()=>finish(text("Không mở được trình tải core.","Could not open the core downloader."));document.body.appendChild(frame);
    });
  };
  const renderCoreButtons = async () => {
    const grid=document.getElementById("corePreloadGrid"), status=document.getElementById("corePreloadStatus"); if(!grid)return;
    grid.replaceChildren();
    await Promise.all(Object.entries(systems).filter(([key,value])=>value.channel!=="native").map(async ([key,value]) => {
      const item=document.createElement("div"),label=document.createElement("strong"),stateText=document.createElement("small"),actions=document.createElement("div"),download=document.createElement("button"),drop=document.createElement("button");
      item.className="core-preload-item";label.textContent=value.label;download.type="button";download.className="button";download.dataset.coreSystem=key;drop.type="button";drop.className="button danger";
      const refresh=async()=>{const state=await inspectCore(key),core=primaryCores[key];stateText.textContent=state.ready?text(`Đã tải ${core} · ${formatSize(state.bytes)}`,`Downloaded ${core} · ${formatSize(state.bytes)}`):text(`Chưa tải · ${core}`,`Not downloaded · ${core}`);download.textContent=state.ready?text("Tải lại","Download again"):text("Tải core","Download core");drop.textContent=text("Xóa","Delete");drop.disabled=!state.count;};
      download.addEventListener("click",async()=>{download.disabled=true;download.setAttribute("aria-busy","true");status.textContent=text(`Đang tải và kiểm tra core ${value.label}…`,`Downloading and verifying the ${value.label} core…`);try{const result=await preloadCore(key);await refresh();status.textContent=result.secureOffline?text(`Core ${value.label} đã sẵn sàng để chơi offline.`,`The ${value.label} core is ready for offline play.`):text(`Đã lưu core ${value.label} trong trình duyệt. Mở bản HTTPS để có thể tải lại toàn bộ trang khi mất mạng.`,`The ${value.label} core is stored in this browser. Open the HTTPS site to reload the full app while offline.`);}catch(error){status.textContent=error.message;showToast(error.message,true);}finally{download.disabled=false;download.removeAttribute("aria-busy");}});
      drop.addEventListener("click",async()=>{if(!confirm(text(`Xóa core ${value.label} khỏi thiết bị này?`,`Delete the ${value.label} core from this device?`)))return;drop.disabled=true;const count=await deleteCore(key);await refresh();status.textContent=text(`Đã xóa core ${value.label} (${count} tệp cache).`,`Deleted the ${value.label} core (${count} cached files).`);});
      actions.append(download,drop);item.append(label,stateText,actions);grid.appendChild(item);await refresh();
    }));
  };

  const renderLibrary = async () => {
    const grid=document.getElementById("offlineGameGrid");if(!grid)return;
    try {
      const games=await all();grid.replaceChildren();
      if(!games.length){const empty=document.createElement("div");empty.className="empty-state";empty.innerHTML=`<strong>${text("Chưa có game trên máy này.","No games on this device.")}</strong>`;grid.appendChild(empty);return;}
      const groups=new Map();
      games.forEach(game=>{if(!groups.has(game.system))groups.set(game.system,[]);groups.get(game.system).push(game);});
      [...groups.entries()].sort(([left],[right])=>(systems[left]?.label||left).localeCompare(systems[right]?.label||right)).forEach(([system,items])=>{
        const section=document.createElement("section"),header=document.createElement("div"),heading=document.createElement("h3"),count=document.createElement("span"),cards=document.createElement("div");
        section.className="offline-system-section";section.dataset.system=system;header.className="section-title";heading.textContent=systems[system]?.label||system;count.textContent=String(items.length);cards.className="game-grid";header.append(heading,count);section.append(header,cards);
        items.forEach(game=>{const card=document.createElement("article"),body=document.createElement("div"),meta=document.createElement("div"),badge=document.createElement("span"),title=document.createElement("h2"),size=document.createElement("div"),actions=document.createElement("div"),play=document.createElement("button"),download=document.createElement("button"),drop=document.createElement("button");card.className="game-card";card.dataset.system=game.system;body.className="game-card-body";meta.className="game-meta";badge.className="badge";badge.textContent=systems[game.system]?.label||game.system;meta.appendChild(badge);title.textContent=game.title;size.className="muted";size.textContent=formatSize(game.file.size);actions.className="card-actions";play.className="button primary";play.textContent=text("Chơi ngay","Play now");play.disabled=game.system==="html5";play.addEventListener("click",()=>{location.href=`/offline?play=${encodeURIComponent(game.id)}&system=${encodeURIComponent(game.system)}&title=${encodeURIComponent(game.title)}`;});download.className="icon-button";download.title=text("Tải game","Download game");download.textContent="↓";download.addEventListener("click",()=>{const url=URL.createObjectURL(game.file),anchor=document.createElement("a");anchor.href=url;anchor.download=game.name;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});drop.className="icon-button danger";drop.title=text("Xóa game","Remove game");drop.textContent="×";drop.addEventListener("click",async()=>{if(!confirm(text("Xóa game khỏi thiết bị này?","Remove this game from this device?")))return;await remove(game.id);renderLibrary();});actions.append(play,download,drop);body.append(meta,title,size,actions);card.appendChild(body);cards.appendChild(card);});
        grid.appendChild(section);
      });
    } catch(error){showToast(error.message || String(error),true);}
  };

  const setupLibrary = () => {
    const form=document.getElementById("offlineGameForm"),fileInput=document.getElementById("offlineFile"),titleInput=document.getElementById("offlineTitle"),systemInput=document.getElementById("offlineSystem"),status=document.getElementById("offlineDetection");if(!form||!fileInput||!titleInput||!systemInput)return;
    Object.entries(systems).forEach(([key,system])=>{const option=document.createElement("option");option.value=key;option.textContent=system.label;systemInput.appendChild(option);});
    fileInput.addEventListener("change",async()=>{const file=fileInput.files?.[0];if(!file)return;titleInput.value=cleanTitle(file.name);status.textContent=text("Đang nhận diện hệ máy…","Detecting system…");const detected=await inferFile(file);if(detected){systemInput.value=detected;status.textContent=`${text("Đã nhận diện","Detected")}: ${systems[detected].label}`;}else{status.textContent=text("Không chắc chắn, hãy kiểm tra lựa chọn hệ máy.","Could not determine the system; please review the selection.");}});
    form.addEventListener("submit",async event=>{event.preventDefault();const file=fileInput.files?.[0];if(!file)return;const title=titleInput.value.trim();if(!title)return showToast(text("Nhập tên game.","Enter a game title."),true);if(systemInput.value==="html5")return showToast(text("Game HTML5 ngoại tuyến chưa được hỗ trợ.","Offline HTML5 games are not supported yet."),true);try{await put({id:createOfflineId(),title,name:file.name,system:systemInput.value,file,addedAt:Date.now()});form.reset();status.textContent="";renderLibrary();navigator.storage?.persist?.().catch(()=>{});showToast(text("Đã lưu trên máy này.","Saved on this device."));}catch(error){showToast(error.message || String(error),true);}});
    renderCoreButtons();renderLibrary();
  };
  if(!playOffline())setupLibrary();
})();
