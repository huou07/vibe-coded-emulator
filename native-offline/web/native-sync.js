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
    publish: payload => request("publish", payload),
    blob: (kind, item, context) => request("blob", {kind, item, context: context || null}),
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
