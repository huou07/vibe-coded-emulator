// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Foreground direct-LAN sync coordinator. The native peer owns sockets and the
// local trust registry; this module owns mode policy, UI-facing status, and the
// existing save-transfer adapter boundary.
(() => {
  "use strict";
  const MODE_KEY = "an3-lan-mode-v1";
  const BACKGROUND_KEY = "an3-lan-background-v1";
  const invoke = () => globalThis.AN3NativeInvoke?.() || globalThis.__TAURI__?.core?.invoke || globalThis.__TAURI_INTERNALS__?.invoke;
  const mode = () => {
    try { return localStorage.getItem(MODE_KEY) === "account" ? "account" : "guest"; } catch (_) { return "guest"; }
  };
  const setMode = value => {
    const next = value === "account" ? "account" : "guest";
    try { localStorage.setItem(MODE_KEY, next); } catch (_) {}
    return next;
  };
  const backgroundEnabled = () => {
    try { return localStorage.getItem(BACKGROUND_KEY) === "true"; } catch (_) { return false; }
  };
  const setBackgroundEnabled = value => {
    try { localStorage.setItem(BACKGROUND_KEY, value ? "true" : "false"); } catch (_) {}
    return Boolean(value);
  };
  const call = async (name, args = {}) => {
    const runner = invoke();
    if (typeof runner !== "function") throw new Error("Direct LAN Sync requires the installed AN3 app.");
    return runner(name, args);
  };
  let discoveryInFlight = null;
  const status = () => call("native_sync_status");
  const start = async (requestedMode = mode()) => {
    setMode(requestedMode);
    return call("native_sync_start", {mode: mode()});
  };
  const join = (code, peerId = null) => {
    const value = String(code || "");
    if (mode() === "guest" && !peerId && !/^\d{6}$/.test(value)) throw new Error("Enter exactly six decimal digits.");
    return call("native_sync_join", {code: value, mode: mode(), peerId});
  };
  const reconnect = peerId => call("native_sync_join", {code: "", mode: mode(), peerId});
  const forget = peerId => call("native_sync_forget", {peerId});
  const discover = () => {
    if (!discoveryInFlight) {
      discoveryInFlight = call("native_sync_discover").finally(() => { discoveryInFlight = null; });
    }
    return discoveryInFlight;
  };
  const request = (method, payload) => call("native_sync_request", {method, payload});
  const bytesFromBase64 = value => {
    const binary = atob(String(value || ""));
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    return bytes;
  };
  const base64FromBytes = bytes => {
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    return btoa(binary);
  };
  const contextFor = (kind, system, romId, identity) => ({
    kind,
    system: String(system || "").toLowerCase(),
    romId: String(romId || ""),
    identity: identity || null,
  });
  const serializeRecord = async (record, kind) => {
    const source = kind === "state" ? record.state : record.bytes;
    const bytes = source && typeof source.arrayBuffer === "function"
      ? new Uint8Array(await source.arrayBuffer())
      : source instanceof Uint8Array ? source : new Uint8Array(source || []);
    const path = record.targetPath || record.path || (kind === "state" ? "/data/states/" + String(record.key || record.id || "").split(":").pop() : "");
    return {
      key: record.key || record.id || "",
      path,
      targetPath: record.targetPath || "",
      contentHash: record.contentHash || "",
      size: bytes.byteLength,
      data: base64FromBytes(bytes),
    };
  };
  const storage = (kind, system, romId, identity) => ({
    readAll: async () => {
      const payload = await call("native_sync_storage_read", {payload: contextFor(kind, system, romId, identity)});
      return (payload.records || []).map(record => ({
        ...record,
        bytes: record.bytes ? bytesFromBase64(record.bytes) : undefined,
        state: record.state ? new Blob([bytesFromBase64(record.state)], {type: "application/octet-stream"}) : undefined,
      }));
    },
    put: async record => {
      await call("native_sync_storage_write", {payload: {
        ...contextFor(kind, system, romId, identity),
        records: [await serializeRecord(record, kind)],
      }});
    },
    putSet: async records => {
      await call("native_sync_storage_write", {payload: {
        ...contextFor(kind, system, romId, identity),
        records: await Promise.all(records.map(record => serializeRecord(record, kind))),
      }});
    },
  });
  const libraryManifest = () => call("native_sync_library_manifest");
  const libraryStatus = payload => call("native_sync_library_upload_status", {payload});
  const libraryReadChunk = payload => call("native_sync_library_read_chunk", {payload});
  const libraryWriteChunk = payload => call("native_sync_library_write_chunk", {payload});
  const libraryHash = /^[a-f0-9]{64}$/;
  const libraryRomId = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
  const librarySystemForExtension = extension => {
    if (["gba", "raw"].includes(extension)) return "gba";
    if (extension === "nds") return "nds";
    if (extension === "nro") return "switch";
    if (["3ds", "3dsx", "z3dsx", "elf", "axf", "cci", "zcci", "cxi", "zcxi", "app"].includes(extension)) return "3ds";
    return "";
  };
  const normalizeLibraryManifest = manifest => {
    const items = Array.isArray(manifest?.items) ? manifest.items : [];
    if (items.length > 2000) throw new Error("The native library manifest is too large.");
    const seen = new Set();
    return items.map(item => {
      const romId = String(item?.romId || "");
      const extension = String(item?.extension || "").toLowerCase();
      const key = String(item?.key || `rom:${romId}`);
      const system = String(item?.system || "").toLowerCase();
      const size = Number(item?.size);
      const contentHash = String(item?.contentHash || "").toLowerCase();
      if (!libraryRomId.test(romId) || !/^[a-z0-9]{1,10}$/.test(extension) || librarySystemForExtension(extension) !== system || key !== `rom:${romId}` || seen.has(key)
        || !Number.isSafeInteger(size) || size < 1 || !libraryHash.test(contentHash)) {
        throw new Error("The native library manifest contains an invalid ROM.");
      }
      seen.add(key);
      return {
        key,
        romId,
        extension,
        system,
        name: String(item?.name || `${romId}.${extension}`),
        path: String(item?.path || `/data/roms/${romId}.${extension}`),
        size,
        contentHash,
        deviceId: String(item?.deviceId || manifest?.deviceId || ""),
      };
    }).sort((left, right) => left.key.localeCompare(right.key));
  };
  const libraryPayload = item => ({
    romId: item.romId,
    extension: item.extension,
    size: item.size,
    contentHash: item.contentHash,
  });
  const throwIfLibraryCancelled = signal => {
    if (!signal?.aborted) return;
    const error = new Error("Library sync canceled.");
    error.code = "ABORT_ERR";
    throw error;
  };
  const retryLibrary = async (operation, signal) => {
    let failure;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      throwIfLibraryCancelled(signal);
      try { return await operation(); }
      catch (error) {
        failure = error;
        if (attempt === 2) break;
        await new Promise(resolve => setTimeout(resolve, 100 * (attempt + 1)));
      }
    }
    throw failure || new Error("Library sync failed.");
  };
  const upsertNativeLibraryRecord = async item => {
    const library = globalThis.AN3OfflineLibrary;
    if (!library?.put) return;
    const existing = (await library.list?.() || []).find(game => String(game?.id || "") === item.romId);
    const name = item.name || `${item.romId}.${item.extension}`;
    const nativeRecord = /Android/i.test(globalThis.navigator?.userAgent || "")
      ? {nativePath: `/native-rom/${name}`}
      : {nativeUrl: `/_an3/rom/${name}`};
    await library.put({
      ...(existing || {}),
      id: item.romId,
      title: existing?.title || name,
      name: existing?.name || name,
      system: item.system || existing?.system || "gba",
      size: item.size,
      romHash: item.contentHash,
      addedAt: existing?.addedAt || Date.now(),
      nativeRomId: item.romId,
      ...nativeRecord,
    });
  };
  const syncLibrary = async options => {
    options = typeof options === "function" ? {onState: options} : (options || {});
    const onState = typeof options.onState === "function" ? options.onState : () => {};
    const signal = options.signal;
    const requestedKeys = options.keys == null ? null : (() => {
      if (!Array.isArray(options.keys) || options.keys.length > 2000) {
        throw new Error("The library sync selection is invalid.");
      }
      const keys = new Set();
      for (const key of options.keys) {
        if (typeof key !== "string" || !key.startsWith("rom:") || !libraryRomId.test(key.slice(4))) {
          throw new Error("The library sync selection contains an invalid ROM key.");
        }
        keys.add(key);
      }
      return keys;
    })();
    throwIfLibraryCancelled(signal);
    onState({phase: "checking-peer", completedBytes: 0, totalBytes: 0});
    const current = await status();
    if (!(current.peers || []).some(peer => peer.state === "connected")) {
      throw new Error("No LAN peer is connected. Open Sync and pair a device first.");
    }
    if (!(await sameAccount({capability: "sync", kind: "library"}))) {
      throw new Error("The LAN peer is not verified for this AN3 account.");
    }
    onState({phase: "scanning", completedBytes: 0, totalBytes: 0});
    const local = normalizeLibraryManifest(await libraryManifest());
    const remote = normalizeLibraryManifest(await retryLibrary(() => request("library-manifest", {}), signal));
    const localByKey = new Map(local.map(item => [item.key, item]));
    const remoteByKey = new Map(remote.map(item => [item.key, item]));
    const keys = Array.from(new Set([...localByKey.keys(), ...remoteByKey.keys()])).sort();
    const allTransfers = [];
    for (const key of keys) {
      const localItem = localByKey.get(key);
      const remoteItem = remoteByKey.get(key);
      const direction = !localItem ? "download" : !remoteItem ? "upload" : localItem.extension === remoteItem.extension && localItem.system === remoteItem.system && localItem.contentHash === remoteItem.contentHash && localItem.size === remoteItem.size ? "none" : "conflict";
      allTransfers.push({key, direction, local: localItem || null, remote: remoteItem || null, reason: direction === "conflict" ? "both-changed" : direction === "none" ? "identical" : direction === "upload" ? "local-only" : "remote-only"});
    }
    if (requestedKeys) {
      const availableKeys = new Set(allTransfers.map(transfer => transfer.key));
      if (Array.from(requestedKeys).some(key => !availableKeys.has(key))) {
        throw new Error("A selected library item is not present on either peer.");
      }
    }
    // Optional stable-key selection is useful for per-game sync and safe targeted
    // recovery. Omitting keys preserves the existing full-library behavior.
    const transfers = requestedKeys
      ? allTransfers.filter(transfer => requestedKeys.has(transfer.key))
      : allTransfers;
    const totalBytes = transfers.reduce((total, transfer) => total + (transfer.direction === "upload" ? transfer.local.size : transfer.direction === "download" ? transfer.remote.size : 0), 0);
    let completedBytes = 0;
    const conflicts = transfers.filter(transfer => transfer.direction === "conflict").map(transfer => ({...transfer, kind: "library"}));
    let uploaded = 0;
    let downloaded = 0;
    const transferOne = async transfer => {
      if (transfer.direction === "none" || transfer.direction === "conflict") return;
      const item = transfer.direction === "upload" ? transfer.local : transfer.remote;
      const spec = libraryPayload(item);
      const state = transfer.direction === "upload"
        ? await retryLibrary(() => request("library-upload-status", spec), signal)
        : await retryLibrary(() => libraryStatus(spec), signal);
      if (state?.complete === true) {
        completedBytes += item.size;
        onState({phase: transfer.direction === "upload" ? "uploading" : "downloading", item: item.key, completedBytes, totalBytes});
      } else {
        let offset = Math.max(0, Number(state?.nextOffset || 0));
        while (offset < item.size) {
          throwIfLibraryCancelled(signal);
          const length = Math.min(2 * 1024 * 1024, item.size - offset);
          const chunk = transfer.direction === "upload"
            ? await retryLibrary(() => libraryReadChunk({...spec, offset, length}), signal)
            : await retryLibrary(() => request("library-blob", {...spec, offset, length}), signal);
          const bytes = bytesFromBase64(chunk?.data);
          if (Number(chunk?.offset) !== offset || bytes.byteLength !== length) throw new Error("The LAN library returned an invalid ROM chunk.");
          const payload = {...spec, offset, data: base64FromBytes(bytes)};
          const result = transfer.direction === "upload"
            ? await retryLibrary(() => request("library-publish-chunk", payload), signal)
            : await retryLibrary(() => libraryWriteChunk(payload), signal);
          offset = Number(result?.nextOffset ?? offset + bytes.byteLength);
          if (!Number.isSafeInteger(offset) || offset <= 0 || offset > item.size) throw new Error("The LAN library returned an invalid transfer offset.");
          completedBytes += bytes.byteLength;
          onState({phase: transfer.direction === "upload" ? "uploading" : "downloading", item: item.key, completedBytes, totalBytes});
        }
      }
      if (transfer.direction === "download") {
        await upsertNativeLibraryRecord(item);
        downloaded += 1;
      } else {
        uploaded += 1;
      }
    };
    for (const transfer of transfers) await transferOne(transfer);
    const resolved = transfers.filter(transfer => {
      const item = transfer.local || transfer.remote;
      return transfer.direction !== "conflict" && ["gba", "nds", "3ds"].includes(item?.system);
    });
    const artifacts = [];
    for (const item of resolved.map(transfer => transfer.local || transfer.remote)) {
      throwIfLibraryCancelled(signal);
      onState({phase: "syncing-data", item: item.key, completedBytes, totalBytes});
      for (const kind of ["save", "state"]) {
        const result = await syncGame(item.system, item.romId, kind, state => onState({phase: `syncing-${kind}`, item: item.key, state, completedBytes, totalBytes}));
        artifacts.push({kind, item: item.key, result});
      }
    }
    onState({phase: "complete", completedBytes, totalBytes});
    return {local, remote, transfers, conflicts, artifacts, counts: {uploaded, downloaded, conflicts: conflicts.length}};
  };
  const gameIdentity = (system, romId) => call("native_sync_game_identity", {system, romId});
  const sameAccount = async context => {
    const current = await status();
    const connected = (current.peers || []).find(peer => peer.state === "connected" || peer.state === "connecting");
    if (!connected) return false;
    if (mode() === "guest") return connected.mode === "guest";
    if (!globalThis.AN3Account?.state?.user) await globalThis.AN3Account?.load?.();
    if (!globalThis.AN3Account?.state?.user) return false;
    if (connected.mode !== "account") return false;
    if (connected.accountVerified === true) return true;
    const peerContext = await call("native_sync_account_context");
    if (!peerContext.challenge) return false;
    const localProof = await globalThis.AN3Account.proof(peerContext.challenge);
    if (!localProof) return false;
    await call("native_sync_set_account_proof", {proof: localProof});
    let remoteProof = peerContext.remoteProof;
    if (current.role === "peer") {
      const response = await request("account-proof", {proof: localProof});
      remoteProof = response?.proof || remoteProof;
    }
    if (!remoteProof || !(await globalThis.AN3Account.verify(peerContext.challenge, remoteProof))) return false;
    await call("native_sync_mark_account_verified", {peerId: connected.deviceId, verified: true});
    return true;
  };
  const authenticateAccount = () => sameAccount({capability: "sync"});
  const transport = Object.freeze({
    development: false,
    discover,
    sameAccount,
    manifest: (kind, context) => request("manifest", {kind, context: context || null}),
    plan: payload => request("plan", payload),
    publish: payload => request("publish", payload),
    blob: async (kind, item, context) => {
      const result = await request("blob", {kind, item, context: context || null});
      // The native peer returns an authenticated JSON response so the Rust
      // request layer can keep framing and error handling uniform.  Adapt its
      // base64 member payload back to the transfer engine's byte contract;
      // the transfer engine performs the final size/SHA-256 check before any
      // persistence.
      if (result instanceof Uint8Array) return result;
      if (!result || typeof result.data !== "string") throw new Error("The direct LAN peer returned no save bytes.");
      return bytesFromBase64(result.data);
    },
    resolve: payload => request("resolve", payload),
    close: async () => {},
  });
  const init = async () => {
    const current = await start(mode());
    // Foreground-only bounded reconnect. The OS is not promised a background
    // service; a future opt-in background implementation must reuse this path.
    for (const peer of current.peers || []) {
      if (!backgroundEnabled()) break;
      if (peer.state === "offline") {
        try { await reconnect(peer.deviceId); } catch (_) {}
      }
    }
    return status();
  };
  const syncGame = async (system, romId, kind = "save", onState = () => {}) => {
    if (!globalThis.AN3SyncTransfer?.sync) throw new Error("The save-sync engine is unavailable.");
    // Fail fast before any expensive identity work. Hashing a multi-gigabyte
    // ROM (or a full manifest scan) must never run when no LAN peer is
    // connected, because the transfer cannot proceed without one and the user
    // would otherwise wait in silence.
    onState("checking-peer");
    const current = await status();
    // Only an established session can exchange a manifest; a peer that is still
    // connecting has no session yet, so do not start the expensive work for it.
    const hasPeer = (current.peers || []).some(peer => peer.state === "connected");
    if (!hasPeer) throw new Error("No LAN peer is connected. Open Sync and pair a device first.");
    onState("scanning");
    const identity = await gameIdentity(system, romId);
    const context = contextFor(kind, system, romId, identity);
    onState("syncing");
    const result = await globalThis.AN3SyncTransfer.sync({
      kind,
      mode: "lan",
      transport,
      storage: storage(kind, system, romId, identity),
      identity,
      context,
      deviceId: (await call("native_sync_identity")).deviceId,
    });
    onState("complete");
    return Object.assign(result, {context, system, romId});
  };
  const resolveGameConflict = async (system, romId, conflict, resolution) => {
    const identity = await gameIdentity(system, romId);
    const context = contextFor(conflict.kind || "save", system, romId, identity);
    return globalThis.AN3SyncTransfer.resolveConflict({
      conflict,
      kind: conflict.kind || "save",
      resolution,
      identity,
      context,
      storage: storage(conflict.kind || "save", system, romId, identity),
      transport,
      deviceId: (await call("native_sync_identity")).deviceId,
    });
  };
  globalThis.AN3NativeSync = Object.freeze({mode, setMode, backgroundEnabled, setBackgroundEnabled, start, join, reconnect, forget, discover, status, request, storage, gameIdentity, syncGame, syncLibrary, resolveGameConflict, transport, sameAccount, authenticateAccount, init});
})();
