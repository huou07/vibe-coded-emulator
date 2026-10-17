// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Foreground direct-LAN sync coordinator. The native peer owns sockets and the
// local trust registry; this module owns mode policy, UI-facing status, and the
// existing save-transfer adapter boundary.
(() => {
  "use strict";
  const MODE_KEY = "an3-lan-mode-v1";
  const BACKGROUND_KEY = "an3-lan-background-v1";
  const TRANSFER_CHUNK_BYTES = 768 * 1024;
  const TRANSFER_CHUNK_CHARS = TRANSFER_CHUNK_BYTES / 3 * 4;
  const LEGACY_TRANSFER_BYTES = 4 * 1024 * 1024;
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
  const status = () => call("native_sync_status");
  const start = async (requestedMode = mode()) => {
    setMode(requestedMode);
    return call("native_sync_start", {mode: mode()});
  };
  const join = (code, peerId = null) => {
    const value = String(code || "");
    if (mode() === "guest" && !peerId && !/^\d{6}$/.test(value)) throw new Error("Enter exactly six decimal digits.");
    chunkedTransfers = undefined;
    return call("native_sync_join", {code: value, mode: mode(), peerId});
  };
  const reconnect = peerId => { chunkedTransfers = undefined; return call("native_sync_join", {code: "", mode: mode(), peerId}); };
  const forget = peerId => call("native_sync_forget", {peerId});
  const discover = () => call("native_sync_discover");
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
  let chunkedTransfers;
  const supportsChunkedTransfers = async () => {
    if (!chunkedTransfers) {
      chunkedTransfers = request("ping", {}).then(result => result?.chunkedTransfers === 1);
    }
    return chunkedTransfers;
  };
  const publish = async payload => {
    const items = Array.isArray(payload?.items) ? payload.items : [];
    const totalSize = items.reduce((total, item) => total + Number(item?.size || 0), 0);
    if (totalSize <= LEGACY_TRANSFER_BYTES) return request("publish", payload);
    if (!(await supportsChunkedTransfers())) {
      throw new Error("This sync peer needs an update before it can receive larger save data.");
    }
    const metadata = {...payload, items: items.map(({data, ...item}) => item)};
    const started = await request("publish-begin", {payload: metadata});
    const transferId = String(started?.transferId || "");
    if (!transferId) throw new Error("The sync peer did not start the large transfer.");
    try {
      for (let index = 0; index < items.length; index += 1) {
        const item = items[index];
        const encoded = String(item.data || "");
        if (!Number.isSafeInteger(Number(item.size)) || Number(item.size) <= 0 || encoded.length !== Math.ceil(Number(item.size) / 3) * 4) {
          throw new Error("A save member has invalid encoded data.");
        }
        let encodedOffset = 0;
        let byteOffset = 0;
        while (encodedOffset < encoded.length) {
          const part = encoded.slice(encodedOffset, encodedOffset + TRANSFER_CHUNK_CHARS);
          const padding = part.endsWith("==") ? 2 : part.endsWith("=") ? 1 : 0;
          const partBytes = part.length / 4 * 3 - padding;
          const result = await request("publish-chunk", {
            transferId, index, offset: byteOffset, data: part,
          });
          byteOffset += partBytes;
          encodedOffset += part.length;
          if (result?.nextOffset !== byteOffset) throw new Error("The sync peer lost a save-data chunk.");
        }
        if (byteOffset !== Number(item.size)) throw new Error("A save member ended at the wrong size.");
      }
      return await request("publish-commit", {transferId});
    } catch (error) {
      try { await request("publish-abort", {transferId}); } catch (_) {}
      throw error;
    }
  };
  const blob = async (kind, item, context) => {
    if (Number(item?.size) <= LEGACY_TRANSFER_BYTES) {
      const result = await request("blob", {kind, item, context: context || null});
      return bytesFromBase64(result?.data);
    }
    if (!(await supportsChunkedTransfers())) {
      throw new Error("This sync peer needs an update before it can send larger save data.");
    }
    const size = Number(item.size);
    if (!Number.isSafeInteger(size) || size <= 0) throw new Error("The sync peer announced an invalid save-data size.");
    const result = new Uint8Array(size);
    let offset = 0;
    while (offset < size) {
      const chunk = await request("blob", {
        kind, item, context: context || null, offset, length: TRANSFER_CHUNK_BYTES,
      });
      const bytes = bytesFromBase64(chunk?.data);
      if (chunk?.offset !== offset || chunk?.size !== size || chunk?.contentHash !== item.contentHash ||
          bytes.length === 0 || bytes.length > TRANSFER_CHUNK_BYTES || offset + bytes.length > size) {
        throw new Error("The sync peer returned an invalid save-data chunk.");
      }
      result.set(bytes, offset);
      offset += bytes.length;
    }
    return result;
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
    publish,
    blob,
    resolve: payload => request("resolve", payload),
    close: async () => {},
  });
  const init = async () => {
    const current = await start(mode());
    // Foreground-only bounded reconnect. The OS is not promised a background
    // service; a future opt-in background implementation must reuse this path.
    for (const peer of current.peers || []) {
      if (peer.state === "offline") {
        try { await reconnect(peer.deviceId); } catch (_) {}
      }
    }
    return status();
  };
  const syncGame = async (system, romId, kind = "save", onProgress) => {
    if (!globalThis.AN3SyncTransfer?.sync) throw new Error("The save-sync engine is unavailable.");
    if (!(await sameAccount({capability: "sync", kind}))) {
      throw new Error("Connect a compatible sync peer before syncing saves.");
    }
    onProgress?.("Reading the game file to verify its identity. Large files can take a while.");
    const identity = await gameIdentity(system, romId);
    onProgress?.("Comparing and syncing save data…");
    const context = contextFor(kind, system, romId, identity);
    const result = await globalThis.AN3SyncTransfer.sync({
      kind,
      mode: "lan",
      transport,
      storage: storage(kind, system, romId, identity),
      identity,
      context,
      deviceId: (await call("native_sync_identity")).deviceId,
    });
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
  globalThis.AN3NativeSync = Object.freeze({mode, setMode, backgroundEnabled, setBackgroundEnabled, start, join, reconnect, forget, discover, status, request, storage, gameIdentity, syncGame, resolveGameConflict, transport, sameAccount, authenticateAccount, init});
})();
