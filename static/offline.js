// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
(() => {
  const systems = {
    gb:{label:"Game Boy / Color",channel:"stable"}, gba:{label:"Game Boy Advance",channel:"stable"}, nds:{label:"Nintendo DS",channel:"stable"}, "3ds":{label:"Nintendo 3DS",channel:"latest"}, switch:{label:"Nintendo Switch",channel:"native"}, nes:{label:"NES / Famicom",channel:"stable"}, snes:{label:"SNES / Super Famicom",channel:"stable"}, n64:{label:"Nintendo 64",channel:"stable"}, psx:{label:"PlayStation",channel:"stable"}, psp:{label:"PSP",channel:"stable"}, segaMD:{label:"Mega Drive / Genesis",channel:"stable"}, segaMS:{label:"Master System",channel:"stable"}, segaGG:{label:"Game Gear",channel:"stable"}, sega32x:{label:"Sega 32X",channel:"stable"}, segaCD:{label:"Sega CD",channel:"stable"}, segaSaturn:{label:"Sega Saturn",channel:"stable"}, arcade:{label:"Arcade / FBNeo",channel:"stable"}, "3do":{label:"3DO",channel:"stable"}, atari2600:{label:"Atari 2600",channel:"stable"}, atari7800:{label:"Atari 7800",channel:"stable"}, jaguar:{label:"Atari Jaguar",channel:"stable"}, lynx:{label:"Atari Lynx",channel:"stable"}, pce:{label:"PC Engine",channel:"stable"}, amiga:{label:"Amiga",channel:"stable"}, c64:{label:"Commodore 64",channel:"stable"}, doom:{label:"DOOM / PrBoom",channel:"stable"}, html5:{label:"HTML5",channel:"native"}
  };
  const extensionMap = {
    ".gb":"gb", ".gbc":"gb", ".gba":"gba", ".raw":"gba", ".nds":"nds", ".nro":"switch", ".3ds":"3ds", ".3dsx":"3ds", ".cci":"3ds", ".cia":"3ds", ".cxi":"3ds", ".app":"3ds", ".nes":"nes", ".fds":"nes", ".sfc":"snes", ".smc":"snes", ".fig":"snes", ".swc":"snes", ".n64":"n64", ".z64":"n64", ".v64":"n64", ".psx":"psx", ".cso":"psp", ".sms":"segaMS", ".gg":"segaGG", ".32x":"sega32x", ".md":"segaMD", ".gen":"segaMD", ".smd":"segaMD", ".a26":"atari2600", ".a78":"atari7800", ".j64":"jaguar", ".jag":"jaguar", ".lnx":"lynx", ".pce":"pce", ".sgx":"pce", ".adf":"amiga", ".adz":"amiga", ".dms":"amiga", ".ipf":"amiga", ".hdf":"amiga", ".lha":"amiga", ".d64":"c64", ".g64":"c64", ".t64":"c64", ".tap":"c64", ".crt":"c64", ".prg":"c64", ".wad":"doom", ".iwad":"doom", ".pk3":"doom", ".pk4":"doom", ".html":"html5"
  };
  const hints = {"3ds":["3ds","citra","azahar"],nds:["nds","nintendo-ds","melonds"],gba:["gba","gameboy-advance"],gb:["gbc","gameboy-color","game-boy"],psp:["psp"],psx:["ps1","psx","playstation"],n64:["n64"],snes:["snes","super-nintendo"],nes:["nes","famicom"],segaMD:["genesis","megadrive"],segaSaturn:["saturn"],segaCD:["segacd","mega-cd"],arcade:["arcade","fbneo","mame"]};
  const lang = document.documentElement.lang === "en" ? "en" : "vi";
  const text = (vi,en) => lang === "en" ? en : vi;
  // The installed Tauri shell reuses private-ROM storage and player behavior,
  // but never sends the user back to the AN3 web library.
  const nativeOfflineApp = globalThis.AN3NativeOfflineApp === true;
  const nativeEmulatorOrigin = typeof globalThis.AN3OfflineEmulatorOrigin === "string" ? globalThis.AN3OfflineEmulatorOrigin.trim().replace(/\/+$/, "") : "";
  const nativeBridge = () => {
    const tauri=globalThis.__TAURI__,internals=globalThis.__TAURI_INTERNALS__;
    return {invoke:tauri?.core?.invoke||internals?.invoke,asset:tauri?.core?.convertFileSrc||internals?.convertFileSrc};
  };
  // The platform bootstrap declares only the systems that its installed
  // native host genuinely supports. This is a capability contract, not a
  // device-capability guess.
  const nativeIntegratedSystems = () => {
    const declared=globalThis.AN3NativeIntegratedSystems;
    if(Array.isArray(declared))return declared;
    // A desktop build from before the generic bridge only advertised 3DS.
    return globalThis.AN3NativeIntegratedThreeDs===true?["3ds"]:[];
  };
  const nativeIntegratedSystem = system => nativeIntegratedSystems().includes(system);
  const nativeSystemShortName = system => ({gba:"GBA",nds:"NDS","3ds":"3DS",switch:"Switch"}[system]||String(system||"").toUpperCase());
  const androidNativeShell = nativeOfflineApp && /Android/i.test(navigator.userAgent);
  // Keep old desktop bundles compatible. Android 3DS is routed only when the
  // installed bridge explicitly declares the portable Vulkan host.
  const androidThreeDsUnavailable = system => androidNativeShell && system==="3ds" && !nativeIntegratedSystem(system);

  const nativeIntegratedLauncher = () => {
    if(typeof globalThis.AN3NativeLaunchGame === "function")return globalThis.AN3NativeLaunchGame;
    // Tauri injects its bridge after the document starts evaluating. Resolve
    // it at click time so a fast local library retains the in-app route.
    const invoke=nativeBridge().invoke;
    return typeof invoke === "function"?(romId,system,layout)=>invoke("start_native_game",{romId,system,layout:layout||"preserve"}):null;
  };
  const nativeThreeDsLauncher = () => {
    if(androidNativeShell)return null;
    if(typeof globalThis.AN3NativeLaunchThreeDs === "function")return globalThis.AN3NativeLaunchThreeDs;
    // Tauri injects its bridge after the document starts evaluating. Resolve
    // it at click time so a fast local library retains the in-app route.
    const invoke=nativeBridge().invoke;
    return typeof invoke === "function"?(romId,_title,layout)=>invoke("start_native_game",{romId,system:"3ds",layout:layout||"preserve"}):null;
  };
  const nativeIntegratedTitle = system => {
    if(system==="switch")return text("Switch homebrew chạy trong tiến trình đồng hành riêng của VibeCodedEmulator (Eden). Cửa sổ companion nhận bàn phím.","Switch homebrew runs in VibeCodedEmulator's separate companion process (Eden). The companion window takes keyboard input.");
    if(system==="nds")return text("NDS native chạy trong VibeCodedEmulator với Menu → phím ảo → cảm ứng → bàn phím. Bấm vào màn hình game để khóa con trỏ; Esc để nhả.","Native NDS runs inside VibeCodedEmulator with Menu → virtual controls → touch → keyboard. Click the game screen to lock the cursor; press Esc to release it.");
    if(system==="gba")return text("GBA native chạy trong VibeCodedEmulator với Menu → phím ảo → bàn phím vật lý.","Native GBA runs inside VibeCodedEmulator with Menu → virtual controls → physical keyboard.");
    return text("Azahar native chạy trong VibeCodedEmulator với Menu → phím ảo → cảm ứng → bàn phím.","Native Azahar runs inside VibeCodedEmulator with Menu → virtual controls → touch → keyboard.");
  };
  const nativeIntegratedNote = system => {
    if(system==="switch")return text("Switch chạy ở cửa sổ companion riêng. Dùng Focus để đưa cửa sổ lên trước và Stop để dừng.","Switch runs in a separate companion window. Use Focus to bring it forward and Stop to end it.");
    if(system==="nds")return text("NDS native chạy trong VibeCodedEmulator. Bấm màn hình game để khóa con trỏ cho cảm ứng; Esc nhả con trỏ, Esc lần nữa về thư viện.","Native NDS runs inside VibeCodedEmulator. Click the game screen to lock the touchscreen cursor; Esc releases it, and Esc again returns to the library.");
    if(system==="gba")return text("GBA native chạy trong VibeCodedEmulator. Nhấn Esc hoặc Menu → Return to library để thoát.","Native GBA runs inside VibeCodedEmulator. Press Esc or Menu → Return to library to exit.");
    return text("Azahar native chạy trong VibeCodedEmulator. Nhấn Esc hoặc Menu → Return to library để thoát.","Native Azahar runs inside VibeCodedEmulator. Press Esc or Menu → Return to library to exit.");
  };
  const nativeRomPickerAvailable = () => {
    const bridge=nativeBridge();
    return nativeOfflineApp && (typeof globalThis.AN3AndroidNativeImport === "function" || (globalThis.AN3NativeRomStreaming !== false && typeof bridge.invoke === "function"));
  };
  // Android's AssetLoader mounts the packaged application at index.html, not
  // at `/`. Keep native player/back links on that concrete document so a ROM
  // launch never falls through to an unhandled AssetLoader root request.
  const offlineLocation = query => nativeOfflineApp ? `./index.html${query || ""}` : `/offline${query || ""}`;
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
  const romDirectory = async () => {
    if (typeof navigator.storage?.getDirectory !== "function") return null;
    const root=await navigator.storage.getDirectory();
    return root.getDirectoryHandle("an3-arcade-roms",{create:true});
  };
  const writeRom = async (id,file,existing={}) => {
    const directory=await romDirectory();
    if (!directory) return {file};
    const opfsName=existing.opfsName || `${id}.rom`,handle=await directory.getFileHandle(opfsName,{create:true}),writer=await handle.createWritable();
    try { await writer.write(file);await writer.close(); }
    catch(error) { try { await writer.abort(); } catch(_) {} throw error; }
    return {fileHandle:handle,opfsName};
  };
  // EmulatorJS receives local files through File.arrayBuffer(). Browsers reject
  // an exact 2 GiB allocation, while padded NCSD dumps frequently have no data
  // after their declared partitions. Build a temporary, smaller File from the
  // header-defined payload only; the original File/OPFS data and its database
  // record are never altered.
  const playableThreeDsFile = async file => {
    const browserArrayBufferLimit=2**31;
    if (!(file instanceof File) || file.size<browserArrayBufferLimit) return file;
    let header;
    try { header=new Uint8Array(await file.slice(0,0x200).arrayBuffer()); }
    catch(_) { return file; }
    if (header.length<0x160 || String.fromCharCode(...header.slice(0x100,0x104))!=="NCSD") return file;
    const view=new DataView(header.buffer,header.byteOffset,header.byteLength);
    let payloadEnd=0;
    for(let index=0;index<8;index+=1){
      const offset=view.getUint32(0x120+index*8,true),length=view.getUint32(0x124+index*8,true),end=(offset+length)*0x200;
      if(length && (!Number.isSafeInteger(end) || end>file.size)) return file;
      if(length) payloadEnd=Math.max(payloadEnd,end);
    }
    if(!payloadEnd || payloadEnd>=file.size) return file;
    return new File([file.slice(0,payloadEnd)],file.name,{type:file.type,lastModified:file.lastModified});
  };
  const getFile = async id => {
    const game=await get(id);
    if (!game) return null;
    if (game.nativeUrl) {
      // Builds before 0.1.2 stored a UUID-only local streaming URL. Preserve
      // those records but restore their actual ROM suffix at launch time so
      // EmulatorJS can hand mGBA/melonDS/Azahar a recognisable content name.
      const nativeUrl=String(game.nativeUrl);
      const fileName=String(game.name || "");
      const extension=fileName.includes(".") ? fileName.slice(fileName.lastIndexOf(".") + 1).toLowerCase() : "";
      const tail=nativeUrl.split(/[?#]/,1)[0].split("/").pop() || "";
      if (nativeOfflineApp && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(tail) && /^[a-z0-9]{1,10}$/.test(extension)) return `${nativeUrl}.${extension}`;
      return nativeUrl;
    }
    if (game.nativePath) {
      if (nativeOfflineApp) return game.nativePath;
      const bridge=nativeBridge();
      if (!nativeRomPickerAvailable()) throw new Error(text("ROM native này cần bản app mới hơn. Hãy cài lại DMG mới nhất.","This native ROM needs a newer app build. Install the latest DMG."));
      return bridge.asset(game.nativePath);
    }
    if (game.fileHandle?.getFile) {
      const file=await game.fileHandle.getFile();
      return game.system==="3ds" ? playableThreeDsFile(file) : file;
    }
    if (!game.file) return null;
    // A legacy picker File can lose its external backing after IndexedDB
    // persistence. Probe a single byte so the player can explain the repair
    // instead of passing an unreadable object down to EmulatorJS.
    try { await game.file.slice(0,1).arrayBuffer(); }
    catch(_) { throw new Error(text("ROM cũ này không còn đọc được. Hãy nhập lại cùng file để sửa dữ liệu trên thiết bị.","This legacy ROM can no longer be read. Import the same file again to repair its device-only data.")); }
    return game.system==="3ds" ? playableThreeDsFile(game.file) : game.file;
  };
  const nativeRomIdForGame = game => {
    const stored=String(game?.nativeRomId || "");
    if(/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(stored))return stored;
    // Imported records from older native builds predate `nativeRomId`. Their
    // private loopback URL (`/_an3/rom/<uuid>.<ext>`) or Android native path
    // (`/native-rom/<uuid>.<ext>`) already contains the same UUID. Recover it
    // so an existing card keeps playing natively after an app update instead
    // of being blocked and demanding a re-import.
    for (const source of [game?.nativeUrl, game?.nativePath]) {
      const match=String(source || "").match(/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}/i);
      if (match) return match[0];
    }
    // In the installed native app every import is copied into app-private
    // storage under the record's own id, so the record id is the native ROM id
    // even for older records that persisted neither `nativeRomId` nor a native
    // path. Never demand a re-import for a ROM that is already on the device.
    const recordId=String(game?.id || "");
    if(nativeOfflineApp && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(recordId)) return recordId;
    return "";
  };
  const remove = async id => {
    const game=await get(id);
    await transaction("readwrite",store => store.delete(id));
    if (game?.opfsName) try { const directory=await romDirectory();await directory?.removeEntry(game.opfsName); } catch(_) {}
    const nativeRomId=nativeRomIdForGame(game);
    if (nativeRomId && typeof globalThis.AN3AndroidRemoveRom==="function") try { globalThis.AN3AndroidRemoveRom(nativeRomId); } catch(_) {}
    else if (nativeRomId && nativeRomPickerAvailable()) try { await nativeBridge().invoke("remove_native_rom",{romId:nativeRomId}); } catch(_) {}
  };
  window.AN3OfflineLibrary = {get,getFile};

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

  const slotRows = () => Array.from({length:10},(_,index) => { const slot=index+1; return `<div class="save-slot" data-slot="${slot}"><strong>${text("Slot","Slot")} ${slot}</strong><small>${text("Trống","Empty")}</small><button data-save-slot="${slot}">${text("Lưu","Save")}</button><button data-load-slot="${slot}" disabled>${text("Nạp","Load")}</button></div>`; }).join("");
  const padTargetOptions = system => {
    const controls=[["dpad","D-pad"],["a","A"],["b","B"],["start","Start"],["select","Select"]];
    if(["gba","nds","3ds"].includes(system))controls.push(["l","L"],["r","R"]);
    if(["nds","3ds"].includes(system))controls.push(["x","X"],["y","Y"]);
    return controls.map(([value,label])=>`<option value="${value}">${label}</option>`).join("");
  };
  const presentationSettingsMarkup = () => `<section class="player-settings-group player-presentation-renderer"><header><strong>${text("Trình dựng hiển thị","Presentation renderer")}</strong><small>${text("Áp dụng sau khi khởi động lại","Applies after restart")}</small></header><label><span>${text("Renderer mong muốn","Requested renderer")}</span><select id="presentationRenderer"><option value="auto">Auto</option><option value="webgpu">WebGPU</option><option value="webgl2">WebGL2</option></select></label><div class="player-renderer-status"><span>${text("Đã chọn","Requested")}</span><output id="rendererRequestedValue">—</output><span>${text("Đang dùng","Effective")}</span><output id="rendererEffectiveValue">—</output><span>${text("Fallback","Fallback")}</span><output id="rendererFallbackValue">—</output></div><button id="applyPresentationRenderer" type="button">${text("Áp dụng và khởi động lại","Apply and restart")}</button><small id="presentationRendererHint" class="muted">${text("Lựa chọn này có hiệu lực sau khi khởi động lại trình phát.","This choice takes effect after restarting the player.")}</small></section><details id="playerDiagnostics" class="player-diagnostics"><summary>${text("Chẩn đoán","Diagnostics")}</summary><pre id="playerDiagnosticsText"></pre><div class="player-diagnostics-actions"><button id="copyPlayerDiagnostics" type="button">${text("Sao chép chẩn đoán","Copy diagnostics")}</button><span id="copyPlayerDiagnosticsStatus" role="status"></span></div></details>`;
  const performanceSettingsMarkup = system => {
    const renderer=system === "nds" ? `<label><span>${text("Trình dựng NDS","NDS renderer")}</span><select id="performanceRenderer"><option value="native">${text("Mặc định của core","Core default")}</option><option value="legacy">${text("Tương thích / ít yêu cầu hơn","Compatibility / lower demand")}</option></select></label>` : "";
    return `<section class="player-settings-group player-performance-settings"><header><strong>${text("Hiệu năng","Performance")}</strong><small id="performanceRecommendation"></small></header><p class="player-setting-copy">${text("Khuyến nghị cho thiết bị này:","Recommended for this device:")} <strong id="recommendedPerformanceProfile"></strong></p><div class="performance-profile-options" role="radiogroup" aria-label="${text("Hồ sơ hiệu năng","Performance profile")}"><label><input type="radio" name="performanceProfile" value="auto"> ${text("Dùng cài đặt khuyến nghị","Use recommended settings")}</label><label><input type="radio" name="performanceProfile" value="low"> ${text("Máy yếu / Tiết kiệm pin","Low-end / Battery")}</label><label><input type="radio" name="performanceProfile" value="balanced"> ${text("Cân bằng","Balanced")}</label><label><input type="radio" name="performanceProfile" value="quality"> ${text("Chất lượng","Quality")}</label><label><input type="radio" name="performanceProfile" value="custom"> ${text("Tùy chỉnh","Custom")}</label></div><div id="performanceCustomOptions" class="player-performance-custom" hidden>${renderer}</div><div class="player-settings-actions"><button id="useRecommended" type="button">${text("Đặt lại theo khuyến nghị","Use recommended settings")}</button><button id="applyPerformanceProfile" type="button">${text("Áp dụng và khởi động lại","Apply and restart")}</button></div><small id="performanceProfileHint" class="muted"></small></section>`;
  };
  const speedSettingsMarkup = system => {
    if(!["gba","nds"].includes(system)) return "";
    return `<section class="player-settings-group player-speed-settings"><header><strong>${text("Tốc độ","Speed")}</strong><small>${text("Chỉ trong phiên","Session only")}</small></header><div class="player-speed-controls" role="group" aria-label="${text("Tốc độ trò chơi","Game speed")}"><button id="speedDown" type="button" aria-label="${text("Chậm hơn","Slower")}">−</button><output id="speedValue" aria-live="polite">1×</output><button id="speedUp" type="button" aria-label="${text("Nhanh hơn","Faster")}">+</button></div><small id="speedHint" class="muted">${text("Điều chỉnh tốc độ hoạt động sau khi game khởi động.","Speed controls become available after the game starts.")}</small></section>`;
  };
  const virtualPadSettingsMarkup = system => {
    if(!["gb","gba","nds","3ds"].includes(system)) return "";
    return `<section class="player-pad-settings"><header><strong>${text("Phím ảo","Virtual controls")}</strong></header><label><span>${text("Điều hướng","Directional control")}</span><select id="padDirectionalControl"><option value="dpad">D-Pad</option><option value="joystick">Analog Joystick</option></select></label><label><span>${text("Kích thước chung","Overall size")} <output id="padGlobalScaleValue">100%</output></span><input id="padGlobalScale" type="range" min="70" max="100" step="1" value="100"></label><small id="padGlobalScaleHint" class="muted">${text("Mức tối đa giữ nguyên bố cục đã duyệt để tránh chồng phím trên màn hình hẹp.","The maximum keeps the approved layout from overlapping on narrow screens.")}</small><div><button id="resetPadGlobalScale" type="button">${text("Đặt lại kích thước chung","Reset overall size")}</button></div><details class="player-pad-advanced"><summary>${text("Kích thước từng phím","Individual control sizes")}</summary><p class="player-setting-copy">${text("Tỷ lệ tính theo kích thước mặc định của từng phím. Không thể lưu mức làm phím chồng nhau hoặc ra ngoài màn hình.","Sizes are relative to each control’s approved default. Unsafe overlap and off-screen sizes are not saved.")}</p><label><span>${text("Phím cần chỉnh","Control to resize")}</span><select id="padTarget">${padTargetOptions(system)}</select></label><label><span>${text("Kích thước tương đối","Relative size")} <output id="padSizeValue">100%</output></span><input id="padSize" type="range" min="50" max="200" step="1" value="100"></label><small id="padSizeHint" class="muted"></small><div class="player-pad-button-actions"><button id="resetPadTarget" type="button">${text("Đặt lại phím này","Reset this control")}</button><button id="resetPadSizes" type="button">${text("Đặt lại từng phím","Reset all individual sizes")}</button></div></details><label><span>${text("Độ mờ","Opacity")}</span><input id="padOpacity" type="range" min="30" max="100" step="1"></label><div class="player-pad-actions"><button id="editPad" type="button">${text("Kéo thả","Move")}</button><button id="resetPadLayout" type="button">${text("Đặt lại bố cục này","Reset this layout")}</button><button id="resetPad" type="button">${text("Đặt lại tất cả phím ảo","Reset all virtual controls")}</button></div></section>`;
  };
  const controlsSettingsMarkup = system => virtualPadSettingsMarkup(system).replace(/<section class="player-pad-settings"><header><strong>.*?<\/strong><\/header>/,`<section class="player-settings-group player-controls-settings player-pad-settings"><header><strong>${text("Điều khiển","Controls")}</strong><small>${text("Phím ảo","Virtual controls")}</small></header><div class="player-controls-visibility"><span>${text("Phím ảo","Virtual controls")}</span><button id="togglePad" type="button" aria-pressed="false">${text("Hiện phím ảo","Show virtual controls")}</button></div>`);
  const touchToggleMarkup = system => ["gb","gba","nds","3ds"].includes(system) ? `<button id="toggleTouch" class="touch-toggle" type="button" aria-pressed="true" title="${text("Ẩn phím ảo","Hide virtual controls")}" aria-label="${text("Bật hoặc tắt phím ảo","Toggle virtual controls")}">Touch</button>` : "";
  const gameSettingsMarkup = () => `<section class="player-settings-group player-game-settings"><header><strong>${text("Trò chơi & save","Game & saves")}</strong><small>${text("Trên thiết bị này","On this device")}</small></header><div class="player-panel-actions"><button id="saveState" type="button">${text("Tải save state","Download save state")}</button><button id="loadState" type="button">${text("Nạp save state","Load save state")}</button><input id="stateFile" type="file" accept=".state,.savestate,application/octet-stream" hidden></div></section>`;
  const advancedSettingsMarkup = () => `<section class="player-settings-group player-advanced-settings"><header><strong>${text("Nâng cao","Advanced")}</strong></header><p class="player-setting-copy">${text("Mở menu EmulatorJS để dùng các cài đặt core đã được hỗ trợ.","Open the EmulatorJS menu for its supported core settings.")}</p><div class="player-panel-actions"><button id="castScreen" type="button">${text("Dò TV & phát màn hình","Find TV & cast game")}</button><button id="emulatorMenu" type="button">${text("Mở menu giả lập","Open emulator menu")}</button></div></section>`;
  const playerMarkup = system => `<div class="player-toolbar" role="toolbar" aria-label="${text("Điều khiển trình phát","Player controls")}">
    <a class="player-back" href="${offlineLocation("")}" title="${text("Quay lại","Back")}" aria-label="${text("Quay lại thư viện ngoại tuyến","Back to offline library")}"><img src="/static/ui-arrow-left.svg" alt="" width="24" height="24"></a><span class="player-title"></span>
    <div class="player-toolbar-actions"><button id="fullscreen" type="button" title="${text("Toàn màn hình","Fullscreen")}" aria-label="${text("Toàn màn hình","Fullscreen")}"><img src="/static/ui-maximize.svg" alt="" width="24" height="24"></button>
    ${touchToggleMarkup(system)}
    <button id="slotMenu" type="button" aria-expanded="false" title="${text("Save slot","Save slots")}" aria-label="${text("Mở save slot trên thiết bị","Open save slots on this device")}"><img src="/static/ui-save.svg" alt="" width="24" height="24"></button>
    <button id="playerControls" type="button" aria-expanded="false" title="${text("Tùy chọn khác","More options")}" aria-label="${text("Mở tùy chọn trình phát","Open player options")}"><img src="/static/ui-more.svg" alt="" width="24" height="24"></button></div>
  </div><section class="player-stage player-stage-ui"><div id="game"></div><div id="tvPad" aria-label="${text("Bộ điều khiển ảo","Virtual controller")}"></div>
    <div class="player-status"><span class="player-runtime-state"><i aria-hidden="true"></i><span id="playerStatusText">${text("Đang chuẩn bị","Preparing")}</span></span><span id="playerSaveStatus" class="player-save-state">${text("Chưa có save trên thiết bị","No save on this device")}</span><div id="playerNotice" class="player-notice" role="status" aria-live="polite"></div></div><div id="loading" class="loading" role="status" aria-live="polite"><strong id="loadingText">${text("Đang chuẩn bị","Preparing")}</strong><div class="progress" role="progressbar" aria-label="${text("Tiến trình khởi động","Startup progress")}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><i id="loadingBar"></i></div><span id="loadingPct">0%</span></div>
  </section><section id="slotPanel" class="slot-panel" hidden role="dialog" aria-label="${text("Save slot trên thiết bị này","Save slots on this device")}"><header><strong>${text("Save slot trên thiết bị này","Save slots on this device")}</strong><button id="closeSlots" type="button">${text("Đóng","Close")}</button></header>${slotRows()}</section>
  <section id="padPanel" class="pad-panel" role="dialog" aria-label="${text("Tùy chọn trình phát","Player options")}"><header><strong>${text("Tùy chọn trình phát","Player options")}</strong><button id="closePad" type="button">${text("Đóng","Close")}</button></header>${presentationSettingsMarkup()}${performanceSettingsMarkup(system)}${speedSettingsMarkup(system)}${controlsSettingsMarkup(system)}${gameSettingsMarkup()}${advancedSettingsMarkup()}</section>`;

  const playOffline = () => {
    const params = new URLSearchParams(location.search), id=params.get("play"), rom=params.get("rom"), system=params.get("system");
    if ((!id && !rom) || !systems[system] || system === "html5") return false;
    const main=document.createElement("main"), title=params.get("title") || text("Game ngoại tuyến","Offline game");
    const player={mode:"emulator",title,slug:`offline-${id||rom}`,system,channel:systems[system].channel,downloadName:title,lang,emulatorOrigin:nativeEmulatorOrigin};
    if (id) player.offlineId=id;
    if (rom) player.romUrl=`/_an3/rom/${encodeURIComponent(rom)}`;
    main.className="player-shell";
    main.dataset.player=JSON.stringify(player);
    main.innerHTML=playerMarkup(system); main.querySelector(".player-title").textContent=title;
    document.body.className="player-page offline-player-page";document.body.replaceChildren(main);document.title=`${title} · ${nativeOfflineApp ? "VibeCodedEmulator" : "Vibe Coded Emulator"}`;
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
  const indexedCoreEntries = async () => {
    if (!("indexedDB" in globalThis)) return [];
    const database=await openCoreDatabase();
    try {
      return await new Promise((resolve,reject) => {
        const tx=database.transaction("core","readonly"),store=tx.objectStore("core"),keysRequest=store.getAllKeys(),valuesRequest=store.getAll();let keys=[],values=[];
        keysRequest.onsuccess=()=>{keys=keysRequest.result || [];};valuesRequest.onsuccess=()=>{values=valuesRequest.result || [];};
        tx.oncomplete=()=>resolve(keys.map((key,index)=>({key:String(key),bytes:Number(values[index]?.data?.byteLength)||0})).filter(entry=>entry.key!=="?EJS_KEYS!"));
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
  const cachedCoreEntries = async () => {
    const entries=[];
    if ("caches" in globalThis) {
      for (const key of await caches.keys()) {
        const cache=await caches.open(key);
        for (const request of await cache.keys()) {
          const response=await cache.match(request);
          // Core responses normally include Content-Length. Do not clone and
          // read an entire cached binary just to decorate this status panel.
          entries.push({key,request,bytes:Number(response?.headers.get("content-length")) || 0,name:decodeURIComponent(new URL(request.url).pathname.split("/").pop() || "")});
        }
      }
    }
    return entries;
  };
  const coreInventory = async () => {
    const [idbEntries,cacheEntries]=await Promise.all([indexedCoreEntries(),cachedCoreEntries()]);
    return {idbEntries,cacheEntries};
  };
  const inspectCore = async (system,inventory=null) => {
    const source=inventory || await coreInventory();
    const idbEntries=source.idbEntries.filter(entry=>isCoreFileName(entry.key,system));
    const cacheEntries=source.cacheEntries.filter(entry=>isCoreAsset(entry.request,system));
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
    const manifest=document.querySelector('link[rel="manifest"]')?.href;
    const version=manifest ? new URL(manifest).searchParams.get("v") || "1" : "1";
    await navigator.serviceWorker.register(`/service-worker.js?v=${encodeURIComponent(version)}`);
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) await new Promise(resolve=>{
      const timer=setTimeout(resolve,2500),changed=()=>{clearTimeout(timer);navigator.serviceWorker.removeEventListener("controllerchange",changed);resolve();};
      navigator.serviceWorker.addEventListener("controllerchange",changed,{once:true});
    });
  };
  const setupOfflineShortcut = () => {
    const button=document.getElementById("offlineShortcut");
    if(!button) return;
    let deferredPrompt=null;
    addEventListener("beforeinstallprompt",event=>{
      event.preventDefault();
      deferredPrompt=event;
      button.dataset.installReady="true";
    });
    addEventListener("appinstalled",()=>{
      deferredPrompt=null;
      button.dataset.installReady="false";
      showToast(text("Shortcut đã được tạo trên thiết bị này.","The shortcut was created on this device."));
    });
    button.addEventListener("click",async()=>{
      button.disabled=true;
      try {
        await ensureOfflineRuntime();
        await updateReadiness();
        if (deferredPrompt) {
          deferredPrompt.prompt();
          const choice=await deferredPrompt.userChoice.catch(()=>null);
          deferredPrompt=null;
          button.dataset.installReady="false";
          showToast(choice?.outcome==="accepted" ? text("Đang tạo shortcut trên máy…","Creating the desktop shortcut…") : text("Giao diện đã được lưu. Bạn có thể tạo shortcut sau từ menu trình duyệt.","The interface is saved. You can create a shortcut later from the browser menu."));
          return;
        }
        showToast(isSecureContext ? text("Giao diện đã được lưu. Trên Chrome/Edge máy tính, mở menu rồi chọn “Cài đặt ứng dụng” hoặc “Tạo shortcut”.","The interface is saved. In desktop Chrome/Edge, open the browser menu and choose “Install app” or “Create shortcut”.") : text("Giao diện đã được lưu cho origin này. Mở HTTPS hoặc localhost để trình duyệt cho phép tạo shortcut.","The interface is saved for this origin. Open HTTPS or localhost before creating a shortcut."));
      } catch(error) {
        showToast(error.message || String(error),true);
      } finally {
        button.disabled=false;
      }
    });
  };
  let localGameCount = 0;
  const updateReadiness = async (count=localGameCount) => {
    localGameCount=count;
    const network=document.getElementById("offlineNetworkState"),secure=document.getElementById("offlineSecureState"),shell=document.getElementById("offlineShellState"),gameCount=document.getElementById("offlineGameCount");
    if(network)network.textContent=navigator.onLine?text("Đang trực tuyến","Online"):text("Ngoại tuyến","Offline");
    if(secure)secure.textContent=isSecureContext?text("Có","Yes"):text("Không","No");
    if(gameCount)gameCount.textContent=String(count);
    if(!shell)return;
    if(nativeOfflineApp){shell.textContent=text("Đóng gói cùng ứng dụng","Bundled with the app");return;}
    if(!("caches" in globalThis)){shell.textContent=text("Không được hỗ trợ","Not supported");return;}
    try {
      const required=["/offline","/static/site.css","/static/offline.js"],matches=await Promise.all(required.map(path=>caches.match(path)));
      shell.textContent=matches.every(Boolean)?text("Đã lưu cho origin này","Cached for this origin"):text("Chưa xác minh đủ","Not fully confirmed");
    } catch (_) { shell.textContent=text("Không kiểm tra được","Could not check"); }
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
    const inventory=await coreInventory();
    await Promise.all(Object.entries(systems).filter(([key,value])=>value.channel!=="native").map(async ([key,value]) => {
      const item=document.createElement("div"),label=document.createElement("strong"),stateText=document.createElement("small"),actions=document.createElement("div"),download=document.createElement("button"),drop=document.createElement("button");
      item.className="core-preload-item";label.textContent=value.label;download.type="button";download.className="button";download.dataset.coreSystem=key;drop.type="button";drop.className="button danger";
      const renderState=state=>{const core=primaryCores[key];stateText.textContent=state.ready?text(`Đã tải ${core} · ${formatSize(state.bytes)}`,`Downloaded ${core} · ${formatSize(state.bytes)}`):text(`Chưa tải · ${core}`,`Not downloaded · ${core}`);download.textContent=state.ready?text("Tải lại","Download again"):text("Tải core","Download core");drop.textContent=text("Xóa","Delete");drop.disabled=!state.count;};
      const refresh=async()=>renderState(await inspectCore(key));
      download.addEventListener("click",async()=>{download.disabled=true;download.setAttribute("aria-busy","true");status.textContent=text(`Đang tải và kiểm tra core ${value.label}…`,`Downloading and verifying the ${value.label} core…`);try{const result=await preloadCore(key);await refresh();status.textContent=result.secureOffline?text(`Core ${value.label} đã sẵn sàng để chơi offline.`,`The ${value.label} core is ready for offline play.`):text(`Đã lưu core ${value.label} trong trình duyệt. Mở bản HTTPS để có thể tải lại toàn bộ trang khi mất mạng.`,`The ${value.label} core is stored in this browser. Open the HTTPS site to reload the full app while offline.`);}catch(error){status.textContent=error.message;showToast(error.message,true);}finally{download.disabled=false;download.removeAttribute("aria-busy");}});
      drop.addEventListener("click",async()=>{if(!confirm(text(`Xóa core ${value.label} khỏi thiết bị này?`,`Delete the ${value.label} core from this device?`)))return;drop.disabled=true;const count=await deleteCore(key);await refresh();status.textContent=text(`Đã xóa core ${value.label} (${count} tệp cache).`,`Deleted the ${value.label} core (${count} cached files).`);});
      actions.append(download,drop);item.append(label,stateText,actions);grid.appendChild(item);renderState(await inspectCore(key,inventory));
    }));
  };

  const setupCoreManager = () => {
    const manager=document.getElementById("coreManager"),state=document.getElementById("offlineCoreState"),toggle=manager?.querySelector("summary>span:last-child");
    if(!manager)return;
    let rendered=false;
    manager.addEventListener("toggle",async()=>{
      if(toggle)toggle.textContent=manager.open?text("Đóng","Close"):text("Mở","Open");
      if(!manager.open||rendered)return;
      rendered=true;if(state)state.textContent=text("Đang kiểm tra từng hệ máy","Checking individual systems");
      try{await renderCoreButtons();if(state)state.textContent=text("Xem trạng thái theo từng hệ máy","See per-system status below");}
      catch(error){rendered=false;if(state)state.textContent=text("Không kiểm tra được","Could not check");showToast(error.message||String(error),true);}
    });
  };

  // A newer render must win. Rapid navigation, return-from-game, the native
  // capability re-render and an import/remove can all start overlapping async
  // reads; without a generation token a slow older read can commit after a
  // newer one and drop whole system sections (the intermittent "only NDS"
  // library). Each render advances the token and discards its snapshot if a
  // newer render has started.
  const libraryRenderState = {generation: 0};
  const beginLibraryRender = () => (libraryRenderState.generation += 1);
  const isCurrentLibraryRender = generation => generation === libraryRenderState.generation;

  const renderLibrary = async () => {
    const grid=document.getElementById("offlineGameGrid");if(!grid)return;
    const generation=beginLibraryRender();
    try {
      const games=await all();
      if(!isCurrentLibraryRender(generation))return;
      grid.replaceChildren();updateReadiness(games.length);
      if(!games.length){const empty=document.createElement("div");empty.className="empty-state";empty.innerHTML=`<strong>${text("Chưa có game trên máy này.","No games on this device.")}</strong><span>${text("Dùng biểu mẫu bên dưới để lưu ROM riêng trong trình duyệt này.","Use Add ROM to store one on this device.")}</span>`;grid.appendChild(empty);return;}
      const groups=new Map();
      games.forEach(game=>{if(!groups.has(game.system))groups.set(game.system,[]);groups.get(game.system).push(game);});
      [...groups.entries()].sort(([left],[right])=>(systems[left]?.label||left).localeCompare(systems[right]?.label||right)).forEach(([system,items])=>{
        const section=document.createElement("section"),header=document.createElement("div"),heading=document.createElement("h3"),count=document.createElement("span"),cards=document.createElement("div");
        section.className="offline-system-section";section.dataset.system=system;header.className="section-title";heading.textContent=systems[system]?.label||system;count.textContent=String(items.length);cards.className="game-grid";header.append(heading,count);section.append(header,cards);
        items.forEach(game=>{
          const card=document.createElement("article"),body=document.createElement("div"),meta=document.createElement("div"),badge=document.createElement("span"),title=document.createElement("h4"),size=document.createElement("div"),actions=document.createElement("div"),play=document.createElement("button"),download=document.createElement("button"),drop=document.createElement("button");
          const nativeRomId=nativeRomIdForGame(game),nativeIntegrated=!androidThreeDsUnavailable(game.system)&&nativeRomId&&nativeOfflineApp&&nativeIntegratedSystem(game.system)?romId=>{
            const launch=nativeIntegratedLauncher();
            if(!launch)return Promise.reject(new Error(text("Không thể kết nối engine native trong VibeCodedEmulator.","Could not connect to the in-app native engine.")));
            return launch(romId,game.system,"preserve",game.size);
          }:null,nativeThreeDs=!androidThreeDsUnavailable(game.system)&&!nativeIntegrated&&game.system==="3ds"&&nativeRomId&&nativeOfflineApp?(romId,title)=>{
            const launch=nativeThreeDsLauncher();
            if(!launch)return Promise.reject(new Error(text("Không thể kết nối 3DS native trong VibeCodedEmulator.","Could not connect to the in-app native 3DS player.")));
            return launch(romId,title,"preserve",game.size);
          }:null;
          const openEmbeddedPlayer=()=>{location.href=offlineLocation(`?play=${encodeURIComponent(game.id)}&system=${encodeURIComponent(game.system)}&title=${encodeURIComponent(game.title)}`);};
          // A missing copied ROM must never be a dead end. Re-import the same
          // file for this record id (the picker replaces the stored file) and
          // continue straight into native play.
          const repairNativeRom=async()=>{
            const id=nativeRomId||game.id;
            const invoke=nativeBridge().invoke;
            const importNative=typeof globalThis.AN3AndroidNativeImport==="function"?globalThis.AN3AndroidNativeImport:(typeof invoke==="function"?romId=>invoke("pick_and_import_native_rom",{romId}):null);
            if(!importNative)throw new Error(text("Không thể mở trình chọn ROM.","Could not open the ROM picker."));
            const imported=await importNative(id);
            if(!imported)return false;
            const system=typeof imported.system==="string"&&systems[imported.system]?imported.system:game.system;
            const repaired={...game,id,title:cleanTitle(imported.name||game.title),name:imported.name||game.name,system,size:imported.size||game.size,addedAt:Date.now(),nativeRomId:id,...(imported.path?{nativePath:imported.path}:{})};
            await put(repaired);await renderLibrary();
            const launch=nativeIntegratedLauncher();
            if(launch)await launch(id,system,"preserve",repaired.size);
            return true;
          };
          card.className="game-card offline-game-card";card.dataset.system=game.system;card.dataset.testid=game.system==="switch"?"switch-game-card":"game-card";body.className="game-card-body";meta.className="game-meta";badge.className="badge";badge.textContent=systems[game.system]?.label||game.system;meta.appendChild(badge);title.textContent=game.title;size.className="muted";size.textContent=formatSize(game.size ?? game.file?.size ?? 0);actions.className="card-actions";
          let nativeStatus=null;play.type="button";play.className="button primary";play.dataset.testid=game.system==="switch"?"switch-launch":"game-launch";play.textContent=androidThreeDsUnavailable(game.system)?text("3DS chưa hỗ trợ","3DS unavailable"):nativeIntegrated?text(`Chơi ${nativeSystemShortName(game.system)} native`,`Play ${nativeSystemShortName(game.system)} native`):nativeThreeDs?text("Mở Azahar","Open Azahar"):text("Chơi ngay","Play now");play.title=androidThreeDsUnavailable(game.system)?text("3DS requires the installed portable Vulkan host.","3DS requires the installed portable Vulkan host."):nativeIntegrated?nativeIntegratedTitle(game.system):nativeThreeDs?text("Ưu tiên hiệu năng 3DS native; Azahar dùng điều khiển riêng.","Use native 3DS performance; Azahar has its own controls."):"";play.disabled=game.system==="html5"||androidThreeDsUnavailable(game.system);
          play.addEventListener("click",()=>{if(nativeIntegrated||nativeThreeDs){if(nativeStatus){nativeStatus.className="muted";nativeStatus.dataset.state="starting";nativeStatus.textContent=nativeIntegrated?text(`Đang khởi động ${nativeSystemShortName(game.system)} native trong VibeCodedEmulator…`,`Starting native ${nativeSystemShortName(game.system)} inside VibeCodedEmulator…`):text("Đang khởi động Azahar trong VibeCodedEmulator…","Starting Azahar inside VibeCodedEmulator…");}const start=nativeIntegrated?nativeIntegrated(nativeRomId):nativeThreeDs(nativeRomId,game.title);Promise.resolve(start).then(result=>{if(nativeStatus)nativeStatus.dataset.state="running";if(nativeStatus)nativeStatus.textContent=result?.detail||(nativeIntegrated?text(`${nativeSystemShortName(game.system)} native đang chạy trong VibeCodedEmulator.`, `Native ${nativeSystemShortName(game.system)} is running inside VibeCodedEmulator.`):text("Azahar native đang chạy trong VibeCodedEmulator.","Azahar native is running inside VibeCodedEmulator."));}).catch(error=>{const message=error.message||String(error),missing=/unavailable/i.test(message)&&game.system!=="switch";if(nativeStatus){nativeStatus.className="muted error";nativeStatus.dataset.state="error";nativeStatus.textContent=missing?text("ROM native chưa có trong vùng riêng của ứng dụng.","This ROM is not in the app's private storage yet."):message;}showToast(message,true);if(missing&&!actions.querySelector("[data-repair-native]")){const repair=document.createElement("button");repair.type="button";repair.className="button";repair.dataset.repairNative="1";repair.textContent=text("Nhập lại ROM","Re-import ROM");repair.addEventListener("click",()=>{repair.disabled=true;repairNativeRom().catch(err=>{repair.disabled=false;showToast(err.message||String(err),true);});});actions.appendChild(repair);}});return;}openEmbeddedPlayer();});
          if(androidThreeDsUnavailable(game.system)){const note=document.createElement("small");note.className="muted";note.textContent=text("3DS chưa khả dụng trên Android trong bản này.","3DS is unavailable on Android in this build.");actions.appendChild(note);}else if(nativeIntegrated){const note=document.createElement("small");note.className="muted";note.dataset.testid=game.system==="switch"?"switch-status":"native-status";note.dataset.state="stopped";note.textContent=nativeIntegratedNote(game.system);nativeStatus=note;actions.appendChild(note);if(nativeOfflineApp&&game.system==="switch"&&globalThis.AN3NativeSwitch){const focus=document.createElement("button");focus.type="button";focus.className="button switch-control";focus.dataset.switchControl="focus";focus.dataset.testid="switch-focus";focus.textContent=text("Focus","Focus");focus.addEventListener("click",()=>{Promise.resolve(globalThis.AN3NativeSwitch.focus()).then(()=>{note.dataset.state="running";showToast(text("Đã đưa cửa sổ Switch lên trước.","Brought the Switch window forward."));}).catch(error=>showToast(error.message||String(error),true));});const stop=document.createElement("button");stop.type="button";stop.className="button switch-control";stop.dataset.switchControl="stop";stop.dataset.testid="switch-stop";stop.textContent=text("Stop","Stop");stop.addEventListener("click",()=>{Promise.resolve(globalThis.AN3NativeSwitch.stop()).then(()=>{note.className="muted";note.dataset.state="stopped";note.textContent=text("Đã dừng companion Switch.","Switch companion stopped.");}).catch(error=>showToast(error.message||String(error),true));});actions.append(focus,stop);}}else if(nativeThreeDs){const embedded=document.createElement("button");embedded.type="button";embedded.className="button";embedded.textContent=text("Điều khiển VibeCodedEmulator (beta)","Use VibeCodedEmulator controls (beta)");embedded.title=text("Giữ Menu → phím ảo → cảm ứng → bàn phím vật lý.","Keeps Menu → virtual controls → touch → physical keyboard.");embedded.addEventListener("click",openEmbeddedPlayer);actions.appendChild(embedded);}
          download.type="button";download.className="button";download.textContent=text("Tải tệp","Download file");download.addEventListener("click",async()=>{try{const file=await getFile(game.id);if(!file)throw new Error(text("Không tìm thấy ROM trên thiết bị.","The ROM is unavailable on this device."));const url=typeof file==="string"?file:URL.createObjectURL(file),anchor=document.createElement("a");anchor.href=url;anchor.download=game.name;anchor.click();if(typeof file!=="string")setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){showToast(error.message||String(error),true);}});
          drop.type="button";drop.className="button danger";drop.textContent=text("Xóa","Remove");drop.addEventListener("click",async()=>{if(!confirm(text("Xóa game khỏi thiết bị này?","Remove this game from this device?")))return;await remove(game.id);renderLibrary();});
          actions.prepend(play);actions.append(download,drop);body.append(meta,title,size,actions);card.appendChild(body);cards.appendChild(card);
        });
        grid.appendChild(section);
      });
    } catch(error){showToast(error.message || String(error),true);}
  };
  // The native bootstrap advertises Switch only after runtime detection; let it
  // ask the library to re-render once the capability is known.
  globalThis.AN3RerenderLibrary = renderLibrary;

  const setupLibrary = () => {
    const form=document.getElementById("offlineGameForm"),fileInput=document.getElementById("offlineFile"),titleInput=document.getElementById("offlineTitle"),systemInput=document.getElementById("offlineSystem"),status=document.getElementById("offlineDetection"),browserDropzone=document.getElementById("offlineBrowserDropzone"),browserImport=document.getElementById("offlineBrowserImport"),nativePicker=document.getElementById("offlineNativePicker");if(!form||!fileInput||!titleInput||!systemInput)return;
    Object.entries(systems).forEach(([key,system])=>{const option=document.createElement("option");option.value=key;option.textContent=system.label;systemInput.appendChild(option);});
    fileInput.addEventListener("change",async()=>{const file=fileInput.files?.[0];if(!file)return;titleInput.value=cleanTitle(file.name);status.textContent=text("Đang nhận diện hệ máy…","Detecting system…");const detected=await inferFile(file);if(detected){systemInput.value=detected;status.textContent=`${text("Đã nhận diện","Detected")}: ${systems[detected].label}`;}else{status.textContent=text("Không chắc chắn, hãy kiểm tra lựa chọn hệ máy.","Could not determine the system; please review the selection.");}});
    const configureNativePicker=()=>{
      if(!nativeRomPickerAvailable()||!nativePicker||nativePicker.dataset.ready)return false;
      browserDropzone.hidden=true;if(browserImport)browserImport.hidden=true;nativePicker.hidden=false;nativePicker.dataset.ready="true";
      nativePicker.addEventListener("click",async()=>{
        const id=createOfflineId(),invoke=nativeBridge().invoke;
        nativePicker.disabled=true;nativePicker.setAttribute("aria-busy","true");status.textContent=text("Đang chọn và chép ROM vào vùng riêng của ứng dụng…","Selecting and copying the ROM into the app’s private storage…");
        try{
          const imported=typeof globalThis.AN3AndroidNativeImport==="function"?await globalThis.AN3AndroidNativeImport(id):typeof invoke==="function"?await invoke("pick_and_import_native_rom",{romId:id}):null;
          if(!imported){status.textContent=text("Chưa chọn ROM.","No ROM selected.");return;}
          // The native import service inspects safe file suffixes, archives,
          // and ROM headers before returning. Keep the browser name heuristic
          // for older Android bridges and other systems it does not classify.
          const system=typeof imported.system==="string"&&systems[imported.system]?imported.system:await inferFile({name:imported.name});
          if(!system||system==="html5"){
            try{if(typeof globalThis.AN3AndroidRemoveRom==="function")await Promise.resolve(globalThis.AN3AndroidRemoveRom(id));else if(typeof invoke==="function")await invoke("remove_native_rom",{romId:id});}catch(_){}
            throw new Error(text("Không nhận diện được hệ máy từ file ROM này.","Could not identify a supported system from this ROM file."));
          }
          const title=cleanTitle(imported.name),game={id,title,name:imported.name,system,size:imported.size,addedAt:Date.now(),nativeRomId:id,...(imported.path?{nativePath:imported.path}:{nativeUrl:imported.url})};
          await put(game);await renderLibrary();navigator.storage?.persist?.().catch(()=>{});status.textContent="";showToast(text("Đã lưu ROM trong vùng riêng của ứng dụng.","ROM saved in the app’s private storage."));
        }catch(error){status.textContent="";showToast(error.message||String(error),true);}finally{nativePicker.disabled=false;nativePicker.removeAttribute("aria-busy");}
      });
      return true;
    };
    configureNativePicker();if(nativeOfflineApp&&!nativePicker?.dataset.ready)[50,250,1000].forEach(delay=>setTimeout(configureNativePicker,delay));
    form.addEventListener("submit",async event=>{event.preventDefault();const file=fileInput.files?.[0];if(!file)return;const title=titleInput.value.trim();if(!title)return showToast(text("Nhập tên game.","Enter a game title."),true);if(systemInput.value==="html5")return showToast(text("Game HTML5 ngoại tuyến chưa được hỗ trợ.","Offline HTML5 games are not supported yet."),true);try{const prior=(await all()).find(game=>game.name===file.name&&game.system===systemInput.value&&!game.fileHandle),id=prior?.id||createOfflineId(),stored=await writeRom(id,file,prior||{}),game={...(prior||{}),id,title,name:file.name,system:systemInput.value,size:file.size,addedAt:Date.now(),...stored};delete game.file;await put(game);form.reset();status.textContent="";renderLibrary();navigator.storage?.persist?.().catch(()=>{});showToast(prior?text("Đã sửa ROM cũ trên máy này.","Repaired the existing device-only ROM."):text("Đã lưu trên máy này.","Saved on this device."));}catch(error){showToast(error.message || String(error),true);}});
    setupOfflineShortcut();setupCoreManager();renderLibrary();
    addEventListener("online",()=>updateReadiness());addEventListener("offline",()=>updateReadiness());
    addEventListener("load",()=>setTimeout(()=>updateReadiness(),600),{once:true});
  };
  if(!playOffline())setupLibrary();
})();
