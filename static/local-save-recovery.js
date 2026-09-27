// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Rehydrate a verified pre-existing local save backup after EmulatorJS clears
// an empty IDBFS save file during its exit path.
(() => {
  "use strict";

  const PREFIX = "vibe-sync-save-backup-v1:";
  const MAX_BYTES = 3 * 1024 * 1024;
  const HASH = /^[a-f0-9]{64}$/;
  const safeSegment = (value, fallback, limit) => {
    const result = String(value || fallback || "unknown")
      .trim().replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^\.+$/, "").slice(0, limit);
    return result || String(fallback || "unknown");
  };
  const saveKey = (identity, savePath) => {
    const relativePath = String(savePath || "").replace(/^\/data\/saves\/?/, "");
    const parts = String(savePath || "").split("/").filter(Boolean);
    const baseName = parts.at(-1) || "save";
    return [
      "save",
      safeSegment(identity.core || globalThis.EJS_core, "unknown-core", 48),
      safeSegment(identity.gameId || identity.game || globalThis.EJS_gameID, "unknown-game", 48),
      safeSegment(identity.romHash, "unknown-rom", 80),
      safeSegment(identity.saveId || relativePath || baseName, "save", 64),
    ].join(":").slice(0, 256);
  };
  const bytesOf = async value => {
    if (value && typeof value.arrayBuffer === "function") return new Uint8Array(await value.arrayBuffer());
    if (value instanceof ArrayBuffer) return new Uint8Array(value);
    if (ArrayBuffer.isView(value)) return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
    return new Uint8Array();
  };
  const hash = async bytes => {
    if (!globalThis.crypto?.subtle) return "";
    const digest = new Uint8Array(await globalThis.crypto.subtle.digest("SHA-256", bytes));
    return Array.from(digest, byte => byte.toString(16).padStart(2, "0")).join("");
  };
  const readBackup = async key => {
    if (!key) return null;
    try {
      const record = JSON.parse(globalThis.localStorage?.getItem(PREFIX + encodeURIComponent(key)) || "null");
      if (record?.version !== 1 || record.key !== key || !HASH.test(String(record.contentHash || ""))) return null;
      if (!Number.isInteger(record.size) || record.size <= 0 || record.size > MAX_BYTES) return null;
      if (typeof record.data !== "string" || record.data.length > Math.ceil(MAX_BYTES / 3) * 4) return null;
      const binary = globalThis.atob(record.data);
      const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
      if (bytes.byteLength !== record.size || await hash(bytes) !== record.contentHash) return null;
      return bytes;
    } catch (_) {
      return null;
    }
  };
  const normalizeSavePath = path => {
    const value = String(path || "");
    if (!/^\/data\/saves(?:\/|$)/.test(value) || value.length > 256) throw new Error("The emulator returned an unsafe save-file path.");
    const member = value.replace(/^\/data\/saves\/?/, "");
    if (!member || member.split("/").some(part => !/^[A-Za-z0-9._-]+$/.test(part) || part === "." || part === "..")) {
      throw new Error("The emulator returned an unsafe save-file path.");
    }
    return "/data/saves/" + member;
  };
  const ensureParent = (fs, path) => {
    if (typeof fs.mkdir !== "function" || typeof fs.analyzePath !== "function") return;
    let current = "";
    path.slice(0, path.lastIndexOf("/")).split("/").filter(Boolean).forEach(part => {
      current += "/" + part;
      if (fs.analyzePath(current).exists) return;
      try { fs.mkdir(current); }
      catch (error) { if (!fs.analyzePath(current).exists) throw error; }
    });
  };
  const syncFileSystem = fs => !fs || typeof fs.syncfs !== "function"
    ? Promise.resolve()
    : new Promise((resolve, reject) => fs.syncfs(false, error => error ? reject(error) : resolve()));

  const restore = async ({manager, identity = {}} = {}) => {
    if (!manager?.FS || typeof manager.getSaveFilePath !== "function" || typeof manager.getSaveFile !== "function") return false;
    const path = normalizeSavePath(manager.getSaveFilePath());
    const existing = await bytesOf(manager.getSaveFile(false));
    if (existing.byteLength) return false;
    const backup = await readBackup(saveKey(identity, path));
    if (!backup?.byteLength) return false;
    ensureParent(manager.FS, path);
    manager.FS.writeFile(path, backup);
    await syncFileSystem(manager.FS);
    if (typeof manager.loadSaveFiles === "function") manager.loadSaveFiles();
    return true;
  };

  globalThis.AN3LocalSaveRecovery = Object.freeze({restore});
})();
