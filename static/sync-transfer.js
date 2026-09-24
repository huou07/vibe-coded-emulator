// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
(function () {
  "use strict";

  // The transfer protocol is shared by save states and ordinary emulator save
  // files. Each storage adapter owns discovery and persistence; this module
  // owns identity, hashing, planning, transport, and conflict resolution.
  var STATE_DATABASE_NAME = "an3-arcade-save-slots";
  var STATE_STORE_NAME = "states";
  var DEVICE_STORAGE_KEY = "vibe-sync-device-v1";
  var SAVE_BACKUP_PREFIX = "vibe-sync-save-backup-v1:";
  var MAX_SAVE_BACKUP_BYTES = 3 * 1024 * 1024;
  var KIND_STATE = "state";
  var KIND_SAVE = "save";
  var KEY_PATTERN = /^[A-Za-z0-9._:@/\\-]{1,256}$/;
  var HASH_PATTERN = /^[a-f0-9]{64}$/;
  var MAX_MANIFEST_ITEMS = 2000;
  var SAVE_SET_MEMBER_LIMIT = 64;
  var SAVE_SET_MAX_BYTES = 64 * 1024 * 1024;
  var SAVE_MEMBER_PATTERN = /^[A-Za-z0-9._-]+(?:\/[A-Za-z0-9._-]+)*$/;
  var compareMemberId = function (left, right) { return left < right ? -1 : left > right ? 1 : 0; };

  var hex = function (bytes) {
    return Array.from(bytes).map(function (byte) {
      return byte.toString(16).padStart(2, "0");
    }).join("");
  };

  // Android Chrome does not expose Web Crypto on an http://192.168.x.x LAN
  // origin. Keep the same SHA-256 contract there without weakening the
  // byte-integrity check or requiring a second crypto dependency.
  var sha256Fallback = function (value) {
    var input = value instanceof Uint8Array ? value : new Uint8Array(value);
    var bitLength = input.length * 8;
    var totalLength = ((input.length + 9 + 63) >> 6) << 6;
    var padded = new Uint8Array(totalLength);
    padded.set(input);
    padded[input.length] = 0x80;
    var highLength = Math.floor(bitLength / 0x100000000);
    var lowLength = bitLength >>> 0;
    padded[totalLength - 8] = (highLength >>> 24) & 0xff;
    padded[totalLength - 7] = (highLength >>> 16) & 0xff;
    padded[totalLength - 6] = (highLength >>> 8) & 0xff;
    padded[totalLength - 5] = highLength & 0xff;
    padded[totalLength - 4] = (lowLength >>> 24) & 0xff;
    padded[totalLength - 3] = (lowLength >>> 16) & 0xff;
    padded[totalLength - 2] = (lowLength >>> 8) & 0xff;
    padded[totalLength - 1] = lowLength & 0xff;
    var words = [
      0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
      0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
    ];
    var constants = [
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b,
      0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01,
      0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7,
      0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
      0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152,
      0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
      0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
      0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
      0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819,
      0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08,
      0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f,
      0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
      0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
    ];
    var rotateRight = function (value, count) {
      return (value >>> count) | (value << (32 - count));
    };
    var schedule = new Uint32Array(64);
    for (var offset = 0; offset < padded.length; offset += 64) {
      for (var index = 0; index < 16; index += 1) {
        var base = offset + index * 4;
        schedule[index] = ((padded[base] << 24) | (padded[base + 1] << 16) | (padded[base + 2] << 8) | padded[base + 3]) >>> 0;
      }
      for (var word = 16; word < 64; word += 1) {
        var first = schedule[word - 15];
        var second = schedule[word - 2];
        var small0 = rotateRight(first, 7) ^ rotateRight(first, 18) ^ (first >>> 3);
        var small1 = rotateRight(second, 17) ^ rotateRight(second, 19) ^ (second >>> 10);
        schedule[word] = (schedule[word - 16] + small0 + schedule[word - 7] + small1) >>> 0;
      }
      var a = words[0];
      var b = words[1];
      var c = words[2];
      var d = words[3];
      var e = words[4];
      var f = words[5];
      var g = words[6];
      var h = words[7];
      for (var round = 0; round < 64; round += 1) {
        var big1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
        var choose = (e & f) ^ (~e & g);
        var temporary1 = (h + big1 + choose + constants[round] + schedule[round]) >>> 0;
        var big0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
        var majority = (a & b) ^ (a & c) ^ (b & c);
        var temporary2 = (big0 + majority) >>> 0;
        h = g;
        g = f;
        f = e;
        e = (d + temporary1) >>> 0;
        d = c;
        c = b;
        b = a;
        a = (temporary1 + temporary2) >>> 0;
      }
      words[0] = (words[0] + a) >>> 0;
      words[1] = (words[1] + b) >>> 0;
      words[2] = (words[2] + c) >>> 0;
      words[3] = (words[3] + d) >>> 0;
      words[4] = (words[4] + e) >>> 0;
      words[5] = (words[5] + f) >>> 0;
      words[6] = (words[6] + g) >>> 0;
      words[7] = (words[7] + h) >>> 0;
    }
    return words.map(function (word) { return word.toString(16).padStart(8, "0"); }).join("");
  };

  var digestBytes = async function (bytes) {
    if (globalThis.crypto?.subtle) return hex(new Uint8Array(await globalThis.crypto.subtle.digest("SHA-256", bytes)));
    return sha256Fallback(bytes);
  };

  var encodeBase64 = function (bytes) {
    var alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    var output = "";
    for (var index = 0; index < bytes.length; index += 3) {
      var first = bytes[index];
      var second = index + 1 < bytes.length ? bytes[index + 1] : 0;
      var third = index + 2 < bytes.length ? bytes[index + 2] : 0;
      output += alphabet[first >> 2];
      output += alphabet[((first & 3) << 4) | (second >> 4)];
      output += index + 1 < bytes.length ? alphabet[((second & 15) << 2) | (third >> 6)] : "=";
      output += index + 2 < bytes.length ? alphabet[third & 63] : "=";
    }
    return output;
  };

  var decodeBase64 = function (value) {
    if (typeof globalThis.atob !== "function") return null;
    try {
      var binary = globalThis.atob(String(value || ""));
      var bytes = new Uint8Array(binary.length);
      for (var index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
      return bytes;
    } catch (_) {
      return null;
    }
  };

  var saveBackupStorageKey = function (artifactKey) {
    return SAVE_BACKUP_PREFIX + encodeURIComponent(String(artifactKey || ""));
  };

  // EmulatorJS currently removes its IDBFS save file during its beforeunload
  // exit path. Keep a verified, bounded local copy so a browser reload can
  // rehydrate the same canonical path without introducing another save API or
  // changing the LAN transfer contract.
  var writeSaveBackup = function (artifactKey, bytes, contentHash) {
    if (!artifactKey || !bytes?.byteLength || bytes.byteLength > MAX_SAVE_BACKUP_BYTES) return;
    try {
      globalThis.localStorage?.setItem(saveBackupStorageKey(artifactKey), JSON.stringify({
        version: 1,
        key: artifactKey,
        contentHash: contentHash,
        size: bytes.byteLength,
        data: encodeBase64(bytes),
      }));
    } catch (_) {}
  };

  var readSaveBackup = async function (artifactKey) {
    if (!artifactKey) return null;
    try {
      var raw = globalThis.localStorage?.getItem(saveBackupStorageKey(artifactKey));
      if (!raw) return null;
      var record = JSON.parse(raw);
      if (record?.version !== 1 || record.key !== artifactKey || !HASH_PATTERN.test(String(record.contentHash || ""))) return null;
      var bytes = decodeBase64(record.data);
      if (!bytes || bytes.byteLength !== Number(record.size) || bytes.byteLength > MAX_SAVE_BACKUP_BYTES) return null;
      if (await digestBytes(bytes) !== record.contentHash) return null;
      return bytes;
    } catch (_) {
      return null;
    }
  };

  var readBytes = async function (value) {
    if (value && typeof value.arrayBuffer === "function") {
      return new Uint8Array(await value.arrayBuffer());
    }
    if (value instanceof ArrayBuffer) return new Uint8Array(value);
    if (ArrayBuffer.isView(value)) return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
    throw new Error("Sync storage returned an unreadable byte value.");
  };

  var safeSegment = function (value, fallback, limit) {
    var result = String(value || fallback || "unknown")
      .trim()
      .replace(/[^A-Za-z0-9._-]+/g, "_")
      .replace(/^\.+$/, "")
      .slice(0, limit || 48);
    return result || String(fallback || "unknown");
  };

  var pathBaseName = function (path) {
    var parts = String(path || "").split("/").filter(Boolean);
    return parts.length ? parts[parts.length - 1] : "save";
  };

  var utf8Bytes = function (value) {
    if (typeof TextEncoder === "function") return new TextEncoder().encode(String(value));
    var encoded = encodeURIComponent(String(value));
    var bytes = [];
    for (var index = 0; index < encoded.length; index += 1) {
      if (encoded[index] === "%") {
        bytes.push(parseInt(encoded.slice(index + 1, index + 3), 16));
        index += 2;
      } else {
        bytes.push(encoded.charCodeAt(index));
      }
    }
    return new Uint8Array(bytes);
  };

  var normalizeSaveIdentity = function (identity) {
    identity = identity || {};
    var core = String(identity.core || globalThis.EJS_core || "").trim();
    var gameId = String(identity.gameId || identity.game || globalThis.EJS_gameID || "").trim();
    var romHash = String(identity.romHash || "").trim().toLowerCase();
    if (!/^[A-Za-z0-9_.:-]{1,64}$/.test(core) || !/^[A-Za-z0-9_.-]{1,64}$/.test(gameId)) {
      throw new Error("A save set needs a valid core and game identity.");
    }
    if (!/^(?:sha256:)?[a-f0-9]{64}$/.test(romHash)) {
      throw new Error("A save set needs the complete ROM SHA-256 identity.");
    }
    return {core: core, gameId: gameId, romHash: romHash};
  };

  var normalizeSavePath = function (path) {
    var value = String(path || "");
    if (!/^\/data\/saves(?:\/|$)/.test(value) || value.length > 256) {
      throw new Error("The emulator returned an unsafe save-file path.");
    }
    var memberId = value.replace(/^\/data\/saves\/?/, "");
    if (!SAVE_MEMBER_PATTERN.test(memberId) || memberId.split("/").some(function (part) {
      return part === "." || part === "..";
    })) {
      throw new Error("The emulator returned an unsafe save-set member path.");
    }
    return {memberId: memberId, path: "/data/saves/" + memberId};
  };

  // Normal saves include the artifact kind, emulator core, game identity,
  // ROM identity, and the core-selected save filename. The `kind` field in
  // every API call provides a second server-side namespace from save states.
  var saveArtifactKey = function (identity, savePath) {
    identity = identity || {};
    var relativePath = String(savePath || "").replace(/^\/data\/saves\/?/, "");
    return [
      KIND_SAVE,
      safeSegment(identity.core || globalThis.EJS_core, "unknown-core", 48),
      safeSegment(identity.gameId || identity.game || globalThis.EJS_gameID, "unknown-game", 48),
      safeSegment(identity.romHash, "unknown-rom", 80),
      safeSegment(identity.saveId || relativePath || pathBaseName(savePath), "save", 64),
    ].join(":").slice(0, 256);
  };

  var saveSetId = function (identity) {
    identity = normalizeSaveIdentity(identity);
    return [
      KIND_SAVE,
      safeSegment(identity.core, "unknown-core", 48),
      safeSegment(identity.gameId, "unknown-game", 48),
      safeSegment(identity.romHash, "unknown-rom", 80),
    ].join(":").slice(0, 256);
  };

  var saveSetMemberKey = function (identity, savePath, setIdOverride) {
    var path = normalizeSavePath(savePath);
    return (setIdOverride || saveSetId(identity)) + ":" + path.memberId;
  };

  var saveSetCanonicalPayload = function (set) {
    return JSON.stringify({
      setId: set.setId,
      core: set.core,
      gameId: set.gameId,
      romHash: set.romHash,
      memberCount: set.memberCount,
      totalSize: set.totalSize,
      members: (set.members || []).map(function (member) {
        return {
          memberId: member.memberId,
          path: member.path,
          size: member.size,
          contentHash: member.contentHash,
        };
      }),
    });
  };

  var saveSetManifestHash = async function (set) {
    return digestBytes(utf8Bytes(saveSetCanonicalPayload(set)));
  };

  var buildSaveSet = async function (identity, records, setIdOverride) {
    var normalized = normalizeSaveIdentity(identity);
    var setId = setIdOverride || saveSetId(normalized);
    if (!/^save:[A-Za-z0-9._-]{1,48}:[A-Za-z0-9._-]{1,48}:[A-Za-z0-9._-]{1,80}(?:\.conflict)?$/.test(setId)) {
      throw new Error("The save-set identity is invalid.");
    }
    if (!Array.isArray(records) || !records.length || records.length > SAVE_SET_MEMBER_LIMIT) {
      throw new Error("A save set must contain one to " + SAVE_SET_MEMBER_LIMIT + " members.");
    }
    var members = [];
    var seen = new Set();
    var totalSize = 0;
    for (var index = 0; index < records.length; index += 1) {
      var record = records[index] || {};
      var path = normalizeSavePath(record.path || record.memberPath || "");
      if (seen.has(path.memberId)) throw new Error("The save set contains a duplicate member.");
      seen.add(path.memberId);
      var bytes = await readBytes(record.bytes);
      if (!bytes.byteLength) throw new Error("A save-set member cannot be empty.");
      var contentHash = await digestBytes(bytes);
      var key = saveSetMemberKey(normalized, path.path, setId);
      if (record.key && record.key !== key && !String(record.key).startsWith(saveSetId(normalized) + ":")) {
        throw new Error("A save-set member identity does not match its path.");
      }
      totalSize += bytes.byteLength;
      if (totalSize > SAVE_SET_MAX_BYTES) throw new Error("The save set is too large.");
      members.push({
        key: key,
        memberId: path.memberId,
        path: path.path,
        bytes: bytes,
        size: bytes.byteLength,
        contentHash: contentHash,
        updatedAt: Number(record.updatedAt) || 0,
      });
    }
    members.sort(function (left, right) { return compareMemberId(left.memberId, right.memberId); });
    var set = {
      kind: KIND_SAVE,
      setId: setId,
      core: normalized.core,
      gameId: normalized.gameId,
      romHash: normalized.romHash,
      memberCount: members.length,
      totalSize: totalSize,
      members: members,
    };
    set.manifestHash = await saveSetManifestHash(set);
    return set;
  };

  var validateSaveSet = async function (candidate, expectedIdentity) {
    var set = candidate && typeof candidate === "object" ? candidate : null;
    if (!set) throw new Error("The LAN manifest is missing its save set.");
    var normalized = normalizeSaveIdentity({core: set.core, gameId: set.gameId, romHash: set.romHash});
    var expectedSetId = saveSetId(normalized);
    var setId = String(set.setId || "");
    var isConflict = setId === expectedSetId + ".conflict";
    if (setId !== expectedSetId && !isConflict) throw new Error("The LAN manifest contains an invalid save-set identity.");
    if (expectedIdentity && setId !== saveSetId(expectedIdentity)) {
      throw new Error("The LAN manifest belongs to a different game or core.");
    }
    if (!Array.isArray(set.members) || !set.members.length || set.members.length > SAVE_SET_MEMBER_LIMIT) {
      throw new Error("The LAN manifest contains an invalid save-set member list.");
    }
    if (Number(set.memberCount) !== set.members.length || !Number.isSafeInteger(Number(set.totalSize)) || Number(set.totalSize) < 1 || Number(set.totalSize) > SAVE_SET_MAX_BYTES) {
      throw new Error("The LAN manifest contains an invalid save-set aggregate.");
    }
    var members = [];
    var seen = new Set();
    var totalSize = 0;
    for (var index = 0; index < set.members.length; index += 1) {
      var member = set.members[index] || {};
      var memberId = String(member.memberId || "");
      var path = String(member.path || "");
      if (!SAVE_MEMBER_PATTERN.test(memberId) || seen.has(memberId) || path !== "/data/saves/" + memberId) {
        throw new Error("The LAN manifest contains an invalid save-set member path.");
      }
      if (index > 0 && compareMemberId(members[index - 1].memberId, memberId) >= 0) {
        throw new Error("The LAN manifest members are not deterministically ordered.");
      }
      var size = Number(member.size);
      var contentHash = String(member.contentHash || "").toLowerCase();
      var key = String(member.key || "");
      if (!Number.isSafeInteger(size) || size < 1 || !HASH_PATTERN.test(contentHash) || key !== setId + ":" + memberId || !KEY_PATTERN.test(key)) {
        throw new Error("The LAN manifest contains an invalid save-set member.");
      }
      seen.add(memberId);
      totalSize += size;
      members.push({
        key: key,
        memberId: memberId,
        path: path,
        size: size,
        contentHash: contentHash,
        deviceId: String(member.deviceId || set.deviceId || ""),
      });
    }
    if (totalSize !== Number(set.totalSize)) throw new Error("The LAN manifest total size does not match its members.");
    var normalizedSet = {
      kind: KIND_SAVE,
      setId: setId,
      core: normalized.core,
      gameId: normalized.gameId,
      romHash: normalized.romHash,
      memberCount: members.length,
      totalSize: totalSize,
      members: members,
      manifestHash: String(set.manifestHash || "").toLowerCase(),
      deviceId: String(set.deviceId || ""),
      conflict: isConflict,
    };
    if (!HASH_PATTERN.test(normalizedSet.manifestHash) || await saveSetManifestHash(normalizedSet) !== normalizedSet.manifestHash) {
      throw new Error("The LAN manifest aggregate hash is invalid.");
    }
    return normalizedSet;
  };

  var deviceId = function () {
    try {
      var existing = globalThis.localStorage?.getItem(DEVICE_STORAGE_KEY);
      if (existing && /^[A-Za-z0-9_-]{8,64}$/.test(existing)) return existing;
      var created = globalThis.crypto?.randomUUID
        ? globalThis.crypto.randomUUID()
        : "sync" + Date.now() + Math.random().toString(36).slice(2, 10);
      globalThis.localStorage?.setItem(DEVICE_STORAGE_KEY, created);
      return created;
    } catch (_) {
      return "sync" + Date.now() + Math.random().toString(36).slice(2, 10);
    }
  };

  var openDatabase = function (indexedDb) {
    if (!indexedDb || typeof indexedDb.open !== "function") {
      throw new Error("This browser does not support local save-state storage.");
    }
    return new Promise(function (resolve, reject) {
      var request = indexedDb.open(STATE_DATABASE_NAME, 1);
      request.onupgradeneeded = function () {
        if (!request.result.objectStoreNames.contains(STATE_STORE_NAME)) {
          request.result.createObjectStore(STATE_STORE_NAME, {keyPath: "id"});
        }
      };
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error || new Error("save-state storage unavailable")); };
    });
  };

  var indexedStorage = function (indexedDb) {
    indexedDb = indexedDb || globalThis.indexedDB;
    return {
      readAll: async function () {
        var database = await openDatabase(indexedDb);
        try {
          return await new Promise(function (resolve, reject) {
            var records = [];
            var transaction = database.transaction(STATE_STORE_NAME, "readonly");
            var request = transaction.objectStore(STATE_STORE_NAME).getAll();
            request.onsuccess = function () { records = request.result || []; };
            request.onerror = function () { reject(request.error || new Error("save-state storage failed")); };
            transaction.oncomplete = function () { resolve(records); };
            transaction.onerror = function () { reject(transaction.error || new Error("save-state storage failed")); };
            transaction.onabort = function () { reject(transaction.error || new Error("save-state storage was interrupted")); };
          });
        } finally {
          database.close();
        }
      },
      put: async function (record) {
        var database = await openDatabase(indexedDb);
        try {
          await new Promise(function (resolve, reject) {
            var transaction = database.transaction(STATE_STORE_NAME, "readwrite");
            transaction.objectStore(STATE_STORE_NAME).put(record);
            transaction.oncomplete = resolve;
            transaction.onerror = function () { reject(transaction.error || new Error("save-state storage failed")); };
            transaction.onabort = function () { reject(transaction.error || new Error("save-state storage was interrupted")); };
          });
        } finally {
          database.close();
        }
      },
    };
  };

  var ensureSaveParent = function (fs, path) {
    if (!fs || typeof fs.mkdir !== "function" || typeof fs.analyzePath !== "function") return;
    var parent = path.slice(0, path.lastIndexOf("/"));
    var current = "";
    parent.split("/").filter(Boolean).forEach(function (part) {
      current += "/" + part;
      var exists = false;
      try { exists = Boolean(fs.analyzePath(current).exists); } catch (_) {}
      if (!exists) {
        try { fs.mkdir(current); } catch (error) {
          try { if (!fs.analyzePath(current).exists) throw error; } catch (_) { throw error; }
        }
      }
    });
  };

  var syncFileSystem = function (fs) {
    if (!fs || typeof fs.syncfs !== "function") return Promise.resolve();
    return new Promise(function (resolve, reject) {
      fs.syncfs(false, function (error) { error ? reject(error) : resolve(); });
    });
  };

  // EmulatorJS owns the ordinary save-file store. It is an IDBFS-mounted
  // Emscripten filesystem, so reads and writes go through gameManager.FS and
  // are flushed with syncfs rather than creating a parallel IndexedDB schema.
  var gameSaveStorage = function (options) {
    options = options || {};
    var manager = options.manager || globalThis.EJS_emulator?.gameManager;
    var identity = options.identity || {};
    var canonicalPath = "";
    var canonicalKey = "";
    var requireManager = function () {
      if (!manager || !manager.FS || typeof manager.getSaveFilePath !== "function" || typeof manager.getSaveFile !== "function") {
        throw new Error("The EmulatorJS save-file storage is unavailable until a game is running.");
      }
      return manager;
    };
    var resolvePath = function () {
      var active = requireManager();
      var path = String(active.getSaveFilePath() || "");
      var normalized = normalizeSavePath(path);
      canonicalPath = normalized.path;
      canonicalKey = saveArtifactKey(identity, canonicalPath);
      return normalized.path;
    };
    var conflictPath = function (path, contentHash) {
      return path + ".an3-conflict-" + String(contentHash || "unknown").slice(0, 16);
    };
    var readPath = async function (active, path) {
      if (path === canonicalPath && typeof active.getSaveFile === "function") {
        var primary = active.getSaveFile(false);
        if (primary) return readBytes(primary);
      }
      if (typeof active.FS.readFile !== "function") return null;
      try { return await readBytes(active.FS.readFile(path)); } catch (_) { return null; }
    };
    var listPaths = function (active, primaryPath) {
      if (typeof active.FS.readdir !== "function" || typeof active.FS.readFile !== "function") return [primaryPath];
      var paths = [];
      var visit = function (directory) {
        var entries;
        try { entries = active.FS.readdir(directory) || []; } catch (_) { return; }
        entries.forEach(function (entry) {
          if (entry === "." || entry === "..") return;
          var path = directory === "/" ? "/" + entry : directory + "/" + entry;
          if (!/^\/data\/saves(?:\/|$)/.test(path) || path.length > 256) return;
          var isDirectory = false;
          try {
            var stat = typeof active.FS.stat === "function" ? active.FS.stat(path) : null;
            isDirectory = typeof active.FS.isDir === "function" && active.FS.isDir(stat?.mode);
          } catch (_) {}
          if (isDirectory) visit(path);
          else {
            try {
              var normalized = normalizeSavePath(path);
              if (!normalized.memberId.includes(".an3-conflict-")) paths.push(normalized.path);
            } catch (_) {}
          }
        });
      };
      visit("/data/saves");
      if (!paths.includes(primaryPath)) paths.push(primaryPath);
      return Array.from(new Set(paths)).sort();
    };
    var targetPath = function (record) {
      var path = normalizeSavePath(record?.path || canonicalPath || resolvePath()).path;
      if (record?.targetPath) path = normalizeSavePath(record.targetPath).path;
      else if (record?.isCopy) path = conflictPath(path, record.contentHash);
      return path;
    };
    var putSet = async function (records) {
      var active = requireManager();
      if (!Array.isArray(records) || !records.length) throw new Error("The save set has no members to persist.");
      var prepared = [];
      var seen = new Set();
      var canonicalWrite = false;
      for (var index = 0; index < records.length; index += 1) {
        var record = records[index] || {};
        var bytes = await readBytes(record.bytes);
        if (!bytes.byteLength) throw new Error("Refusing to persist an empty game save.");
        var path = targetPath(record);
        if (seen.has(path)) throw new Error("The save set contains duplicate persistence paths.");
        seen.add(path);
        prepared.push({record: record, path: path, bytes: bytes});
        if (!record.isCopy && !record.targetPath) canonicalWrite = true;
      }
      var snapshots = [];
      for (var snapshotIndex = 0; snapshotIndex < prepared.length; snapshotIndex += 1) {
        var target = prepared[snapshotIndex].path;
        var previous = await readPath(active, target);
        snapshots.push({path: target, bytes: previous});
      }
      try {
        prepared.forEach(function (entry) {
          ensureSaveParent(active.FS, entry.path);
          if (typeof active.FS.writeFile !== "function") throw new Error("The EmulatorJS save filesystem cannot write files.");
          active.FS.writeFile(entry.path, entry.bytes);
        });
        await syncFileSystem(active.FS);
      } catch (error) {
        // IDBFS has no multi-file transaction. Restore every touched path when
        // the underlying filesystem exposes the operations, so a failed set
        // does not silently replace a previously valid save.
        try {
          snapshots.forEach(function (snapshot) {
            if (snapshot.bytes?.byteLength) active.FS.writeFile(snapshot.path, snapshot.bytes);
            else if (typeof active.FS.unlink === "function") active.FS.unlink(snapshot.path);
          });
          await syncFileSystem(active.FS);
        } catch (_) {}
        throw error;
      }
      for (var backupIndex = 0; backupIndex < prepared.length; backupIndex += 1) {
        var entry = prepared[backupIndex];
        if (!entry.record.isCopy && !entry.record.targetPath) {
          var key = entry.record.key || saveArtifactKey(identity, entry.path);
          writeSaveBackup(key, entry.bytes, await digestBytes(entry.bytes));
        }
      }
      if (canonicalWrite && typeof active.loadSaveFiles === "function") active.loadSaveFiles();
    };
    return {
      readAll: async function () {
        var active = requireManager();
        var path = resolvePath();
        // EmulatorJS's saveSaveFiles asks the core to flush SRAM/RTC/etc. into
        // the mounted save file before the bytes are read.
        if (typeof active.saveSaveFiles === "function") active.saveSaveFiles();
        var records = [];
        var paths = listPaths(active, path);
        for (var index = 0; index < paths.length; index += 1) {
          var memberPath = paths[index];
          var bytes = await readPath(active, memberPath);
          if (!bytes?.byteLength) continue;
          var key = saveArtifactKey(identity, memberPath);
          writeSaveBackup(key, bytes, await digestBytes(bytes));
          records.push({id: key, key: key, bytes: bytes, path: memberPath, updatedAt: Date.now()});
        }
        return records;
      },
      put: async function (record) {
        await putSet([record]);
      },
      putSet: async function (records) {
        await putSet(records);
      },
      restore: async function () {
        var active = requireManager();
        var path = resolvePath();
        var existing = active.getSaveFile(false);
        if (existing) {
          var existingBytes = await readBytes(existing);
          if (existingBytes.byteLength) return false;
        }
        var bytes = await readSaveBackup(canonicalKey);
        if (!bytes?.byteLength) return false;
        ensureSaveParent(active.FS, path);
        active.FS.writeFile(path, bytes);
        await syncFileSystem(active.FS);
        if (typeof active.loadSaveFiles === "function") active.loadSaveFiles();
        return true;
      },
      artifactKey: function () { return canonicalKey || saveArtifactKey(identity, resolvePath()); },
    };
  };

  var storageFor = function (kind, options) {
    if (options.storage) return options.storage;
    return kind === KIND_STATE ? indexedStorage(options.indexedDB) : gameSaveStorage(options);
  };

  var localItems = async function (storage, kind) {
    var records = await storage.readAll();
    var items = [];
    for (var index = 0; index < records.length; index += 1) {
      var record = records[index] || {};
      var key = String(record.id || record.key || "");
      var value = kind === KIND_STATE ? record.state : record.bytes;
      if (!KEY_PATTERN.test(key) || !value) continue;
      var bytes = await readBytes(value);
      if (!bytes.byteLength) continue;
      items.push({
        key: key,
        bytes: bytes,
        contentHash: await digestBytes(bytes),
        size: bytes.byteLength,
        updatedAt: Number(record.updatedAt) || 0,
        path: record.path || "",
      });
    }
    if (items.length > MAX_MANIFEST_ITEMS) throw new Error("Too many local sync artifacts in one pass.");
    return items;
  };

  var persistLocal = async function (storage, kind, key, bytes, contentHash, source) {
    var isCopy = Boolean(source && key !== source.key);
    if (kind === KIND_STATE) {
      await storage.put({
        id: key,
        state: new Blob([bytes], {type: "application/octet-stream"}),
        updatedAt: Date.now(),
        digest: contentHash,
        auto: /:auto$/.test(key),
      });
      return;
    }
    await storage.put({
      id: key,
      key: key,
      bytes: bytes,
      contentHash: contentHash,
      isCopy: isCopy,
      source: source || null,
      path: source?.path || "",
      updatedAt: Date.now(),
    });
  };

  var saveSetRecords = function (set, identity, asCopy) {
    return (set.members || []).map(function (member) {
      var conflictHash = set.conflictOf || set.manifestHash || "unknown";
      var targetPath = asCopy
        ? member.path + ".an3-conflict-" + String(conflictHash).slice(0, 16)
        : member.path;
      return {
        id: asCopy ? saveArtifactKey(identity, targetPath) : member.key,
        key: asCopy ? saveArtifactKey(identity, targetPath) : member.key,
        bytes: member.bytes,
        path: member.path,
        targetPath: asCopy ? targetPath : undefined,
        contentHash: member.contentHash,
        isCopy: Boolean(asCopy),
        source: set,
        updatedAt: Date.now(),
      };
    });
  };

  var persistSaveSets = async function (storage, identity, sets) {
    var records = [];
    var targetPaths = new Set();
    for (var index = 0; index < sets.length; index += 1) {
      var entry = sets[index] || {};
      var set = await validateSaveSet(entry.set, entry.asCopy ? undefined : identity);
      var bytesByKey = new Map((entry.set.members || []).map(function (member) { return [member.key, member.bytes]; }));
      set = Object.assign({}, set, {
        members: set.members.map(function (member) {
          return Object.assign({}, member, {bytes: bytesByKey.get(member.key)});
        }),
        conflictOf: entry.set.conflictOf || "",
      });
      var setRecords = saveSetRecords(set, identity, Boolean(entry.asCopy));
      for (var recordIndex = 0; recordIndex < setRecords.length; recordIndex += 1) {
        var record = setRecords[recordIndex];
        var path = record.targetPath || record.path;
        if (targetPaths.has(path)) throw new Error("The save-set persistence plan contains duplicate paths.");
        targetPaths.add(path);
        records.push(record);
      }
    }
    if (typeof storage.putSet === "function") {
      await storage.putSet(records);
      return;
    }
    if (records.length === 1 && typeof storage.put === "function") {
      await storage.put(records[0]);
      return;
    }
    throw new Error("Atomic save-set persistence is unavailable.");
  };

  // The HTTP adapter is intentionally opt-in. It exists for the browser
  // development/test fixtures that exercise the pure sync engine; installed
  // AN3 clients use the direct LAN peer adapter instead.
  var requestJson = async function (fetcher, url, options) {
    var response = await fetcher(url, options);
    var data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data.error || ("HTTP " + response.status));
    return data;
  };

  var requestBytes = async function (fetcher, url) {
    var response = await fetcher(url);
    if (!response.ok) {
      var message = "HTTP " + response.status;
      try { message = (await response.json()).error || message; } catch (_) {}
      throw new Error(message);
    }
    return new Uint8Array(await response.arrayBuffer());
  };

  var createHttpTransport = function (fetcher) {
    if (typeof fetcher !== "function") throw new Error("The development HTTP sync adapter needs fetch.");
    return {
      manifest: function (kind) {
        return requestJson(fetcher, "/api/sync/lan/manifest?kind=" + encodeURIComponent(kind));
      },
      plan: function (payload) {
        return requestJson(fetcher, "/api/sync/plan", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload),
        });
      },
      publish: function (payload) {
        return requestJson(fetcher, "/api/sync/lan/publish", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload),
        });
      },
      blob: function (kind, item) {
        return requestBytes(fetcher, "/api/sync/lan/blob?kind=" + encodeURIComponent(kind) + "&key=" + encodeURIComponent(item.key) + "&hash=" + encodeURIComponent(item.contentHash));
      },
      resolve: function (payload) {
        return requestJson(fetcher, "/api/sync/resolve", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload),
        });
      },
      // This adapter is deliberately limited to development/test fixtures. It
      // is never selected implicitly by an installed app and cannot claim to
      // prove a user account over the LAN.
      development: true,
    };
  };

  var syncPeerAuthorization = async function (transport, options, kind) {
    if (transport.development === true) return;
    if (typeof transport.sameAccount !== "function" || !(await transport.sameAccount({
      capability: "sync",
      kind: kind,
      identity: options && options.identity ? options.identity : null,
    }))) {
      throw new Error("The LAN peer is not verified for this AN3 account.");
    }
  };

  var transportFor = function (options) {
    if (options && options.transport) return globalThis.AN3LanPeer?.asSyncTransport
      ? globalThis.AN3LanPeer.asSyncTransport(options.transport)
      : options.transport;
    if (globalThis.AN3LanPeerTransport) return globalThis.AN3LanPeer?.asSyncTransport
      ? globalThis.AN3LanPeer.asSyncTransport(globalThis.AN3LanPeerTransport)
      : globalThis.AN3LanPeerTransport;
    // Passing `fetch` is the explicit test/development escape hatch. There is
    // no same-origin fallback in the installed product.
    if (options && typeof options.fetch === "function") return createHttpTransport(options.fetch);
    throw new Error("Direct LAN peer transport is unavailable in this build.");
  };

  var remoteItems = function (manifest, kind) {
    var items = manifest && Array.isArray(manifest.items) ? manifest.items : [];
    if (items.length > MAX_MANIFEST_ITEMS) throw new Error("The LAN manifest is too large.");
    var seen = new Set();
    return items.map(function (item) {
      var key = String(item && item.key || "");
      var contentHash = String(item && item.contentHash || "").toLowerCase();
      var size = Number(item && item.size);
      if (!KEY_PATTERN.test(key) || seen.has(key) || !HASH_PATTERN.test(contentHash) || !Number.isSafeInteger(size) || size < 1) {
        throw new Error("The LAN manifest contains an invalid " + kind + ".");
      }
      seen.add(key);
      // Native peer blobs are addressed by their validated storage path as
      // well as by key/hash. Preserve these optional identity fields so the
      // shared transfer layer works with both the direct peer and the
      // development HTTP adapter.
      return {
        key: key,
        path: String(item.path || ""),
        memberId: String(item.memberId || ""),
        contentHash: contentHash,
        size: size,
        deviceId: String(item.deviceId || ""),
      };
    });
  };

  var legacySaveSet = async function (manifest, identity) {
    var expectedSetId = saveSetId(identity);
    var items = remoteItems(manifest, KIND_SAVE).filter(function (item) {
      return item.key.indexOf(expectedSetId + ":") === 0 && !item.key.endsWith(".conflict");
    });
    if (!items.length) return null;
    var members = items.map(function (item) {
      var memberId = item.key.slice(expectedSetId.length + 1);
      return {
        key: item.key,
        memberId: memberId,
        path: "/data/saves/" + memberId,
        contentHash: item.contentHash,
        size: item.size,
        deviceId: item.deviceId,
      };
    }).sort(function (left, right) { return compareMemberId(left.memberId, right.memberId); });
    var candidate = {
      setId: expectedSetId,
      core: normalizeSaveIdentity(identity).core,
      gameId: normalizeSaveIdentity(identity).gameId,
      romHash: normalizeSaveIdentity(identity).romHash,
      memberCount: members.length,
      totalSize: members.reduce(function (total, member) { return total + member.size; }, 0),
      members: members,
    };
    candidate.manifestHash = await saveSetManifestHash(candidate);
    return validateSaveSet(candidate, identity);
  };

  var remoteSaveSet = async function (manifest, identity) {
    var sets = manifest && Array.isArray(manifest.sets) ? manifest.sets : [];
    var seen = new Set();
    for (var index = 0; index < sets.length; index += 1) {
      var validated = await validateSaveSet(sets[index]);
      if (seen.has(validated.setId)) throw new Error("The LAN manifest contains a duplicate save set.");
      seen.add(validated.setId);
      if (validated.setId === saveSetId(identity)) return validated;
    }
    return legacySaveSet(manifest, identity);
  };

  var publish = async function (transport, device, kind, item, keyOverride, context) {
    var key = keyOverride || item.key;
    return transport.publish({
      deviceId: device,
      kind: kind,
      context: context || null,
      items: [{key: key, path: item.path || "", size: item.size, contentHash: item.contentHash, data: encodeBase64(item.bytes)}],
    });
  };

  var publishSaveSet = async function (transport, device, identity, set, setIdOverride, replaceManifestHash, context) {
    var outgoing;
    if (setIdOverride) {
      outgoing = await buildSaveSet(identity, set.members, setIdOverride);
    } else {
      var validated = await validateSaveSet(set, identity);
      var bytesByKey = new Map((set.members || []).map(function (member) { return [member.key, member.bytes]; }));
      outgoing = Object.assign({}, validated, {
        members: validated.members.map(function (member) {
          return Object.assign({}, member, {bytes: bytesByKey.get(member.key)});
        }),
      });
      if (outgoing.members.some(function (member) { return !member.bytes; })) {
        throw new Error("The save set has no bytes to publish.");
      }
    }
    return transport.publish({
        deviceId: device,
        kind: KIND_SAVE,
        context: context || null,
        replaceManifestHash: replaceManifestHash || "",
        set: {
          setId: outgoing.setId,
          core: outgoing.core,
          gameId: outgoing.gameId,
          romHash: outgoing.romHash,
          memberCount: outgoing.memberCount,
          totalSize: outgoing.totalSize,
          manifestHash: outgoing.manifestHash,
          members: outgoing.members.map(function (member) {
            return {
              key: member.key,
              memberId: member.memberId,
              path: member.path,
              size: member.size,
              contentHash: member.contentHash,
            };
          }),
        },
        items: outgoing.members.map(function (member) {
          return {
            key: member.key,
            memberId: member.memberId,
            path: member.path,
            size: member.size,
            contentHash: member.contentHash,
            data: encodeBase64(member.bytes),
          };
        }),
    });
  };

  var download = async function (transport, kind, item, context) {
    var bytes = await transport.blob(kind, item, context);
    if (bytes.byteLength !== item.size || await digestBytes(bytes) !== item.contentHash) {
      throw new Error("Downloaded " + kind + " failed hash verification.");
    }
    return bytes;
  };

  var downloadSaveSet = async function (transport, set, identity, context) {
    var validated = await validateSaveSet(set, identity);
    var members = [];
    for (var index = 0; index < validated.members.length; index += 1) {
      var member = validated.members[index];
      var bytes = await download(transport, KIND_SAVE, member, context);
      members.push(Object.assign({}, member, {bytes: bytes}));
    }
    // Revalidate the complete aggregate after every member has been fetched.
    var downloaded = Object.assign({}, validated, {members: members});
    if (await saveSetManifestHash(downloaded) !== validated.manifestHash) {
      throw new Error("Downloaded save set failed aggregate verification.");
    }
    return downloaded;
  };

  var syncStateKind = async function (options) {
    options = options || {};
    var kind = String(options.kind || KIND_STATE);
    if (kind !== KIND_STATE && kind !== KIND_SAVE) throw new Error("Unsupported sync artifact kind.");
    var transport = transportFor(options);
    await syncPeerAuthorization(transport, options, kind);
    var storage = storageFor(kind, options);
    var device = String(options.deviceId || deviceId());
    if (!/^[A-Za-z0-9_-]{8,64}$/.test(device)) throw new Error("Invalid sync device identity.");
    var local = await localItems(storage, kind);
    var remote = remoteItems(await transport.manifest(kind, options.context || null), kind);
    var localByKey = new Map(local.map(function (item) { return [item.key, item]; }));
    var remoteByKey = new Map(remote.map(function (item) { return [item.key, item]; }));
    var keys = Array.from(new Set(local.concat(remote).map(function (item) { return item.key; }))).sort();
    var records = keys.map(function (key) {
      var localItem = localByKey.get(key);
      var remoteItem = remoteByKey.get(key);
      return {
        key: key,
        local: localItem ? {content_hash: localItem.contentHash, size: localItem.size, modified_at: localItem.updatedAt, device_id: device} : undefined,
        remote: remoteItem ? {content_hash: remoteItem.contentHash, size: remoteItem.size, device_id: remoteItem.deviceId} : undefined,
      };
    });
    var plan = await transport.plan({mode: options.mode || "lan", sameLan: options.sameLan !== false, kind: kind, records: records});
    var conflicts = [];
    var uploaded = 0;
    var downloaded = 0;
    for (var index = 0; index < (plan.transfers || []).length; index += 1) {
      var transfer = plan.transfers[index];
      var localItem = localByKey.get(transfer.key);
      var remoteItem = remoteByKey.get(transfer.key);
      if (transfer.direction === "upload" && localItem) {
        await publish(transport, device, kind, localItem, undefined, options.context);
        uploaded += 1;
      } else if (transfer.direction === "download" && remoteItem) {
        var incoming = await download(transport, kind, remoteItem, options.context);
        await persistLocal(storage, kind, remoteItem.key, incoming, remoteItem.contentHash, remoteItem);
        downloaded += 1;
      } else if (transfer.direction === "conflict") {
        conflicts.push({
          key: transfer.key,
          kind: kind,
          copyKey: transfer.copyKey || transfer.key + ".conflict",
          local: localItem || null,
          remote: remoteItem || null,
          reason: transfer.reason || "both-changed",
        });
      }
    }
    return {
      kind: kind,
      storage: storage,
      plan: plan,
      local: local,
      remote: remote,
      conflicts: conflicts,
      counts: {uploaded: uploaded, downloaded: downloaded, conflicts: conflicts.length},
    };
  };

  var syncSaveKind = async function (options) {
    options = options || {};
    var transport = transportFor(options);
    await syncPeerAuthorization(transport, options, KIND_SAVE);
    var storage = storageFor(KIND_SAVE, options);
    var identity = normalizeSaveIdentity(options.identity || {});
    var device = String(options.deviceId || deviceId());
    if (!/^[A-Za-z0-9_-]{8,64}$/.test(device)) throw new Error("Invalid sync device identity.");
    var localItemsFound = await localItems(storage, KIND_SAVE);
    var localSet = localItemsFound.length ? await buildSaveSet(identity, localItemsFound) : null;
    var manifest = await transport.manifest(KIND_SAVE, options.context || null);
    var remoteSet = await remoteSaveSet(manifest, identity);
    var setId = saveSetId(identity);
    var records = [];
    if (localSet || remoteSet) {
      records.push({
        key: setId,
        local: localSet ? {content_hash: localSet.manifestHash, size: localSet.totalSize, modified_at: Date.now(), device_id: device} : undefined,
        remote: remoteSet ? {content_hash: remoteSet.manifestHash, size: remoteSet.totalSize, device_id: remoteSet.deviceId || ""} : undefined,
      });
    }
    var plan = await transport.plan({mode: options.mode || "lan", sameLan: options.sameLan !== false, kind: KIND_SAVE, records: records});
    var conflicts = [];
    var uploaded = 0;
    var downloaded = 0;
    for (var index = 0; index < (plan.transfers || []).length; index += 1) {
      var transfer = plan.transfers[index];
      if (transfer.direction === "upload" && localSet) {
        await publishSaveSet(transport, device, identity, localSet, undefined, undefined, options.context);
        uploaded += 1;
      } else if (transfer.direction === "download" && remoteSet) {
        var incoming = await downloadSaveSet(transport, remoteSet, identity, options.context);
        await persistSaveSets(storage, identity, [{set: incoming, asCopy: false}]);
        downloaded += 1;
      } else if (transfer.direction === "conflict" && localSet && remoteSet) {
        conflicts.push({
          key: setId,
          setId: setId,
          kind: KIND_SAVE,
          copyKey: transfer.copyKey || setId + ".conflict",
          local: localSet,
          remote: remoteSet,
          reason: transfer.reason || "both-changed",
        });
      }
    }
    return {
      kind: KIND_SAVE,
      storage: storage,
      identity: identity,
      plan: plan,
      local: localSet,
      remote: remoteSet,
      conflicts: conflicts,
      counts: {uploaded: uploaded, downloaded: downloaded, conflicts: conflicts.length},
    };
  };

  var syncKind = async function (options) {
    return String(options?.kind || KIND_STATE) === KIND_SAVE ? syncSaveKind(options) : syncStateKind(options);
  };

  var syncState = function (options) {
    return syncKind(Object.assign({}, options || {}, {kind: KIND_STATE}));
  };

  var syncSave = function (options) {
    return syncSaveKind(Object.assign({}, options || {}, {kind: KIND_SAVE}));
  };

  var restoreGameSave = function (options) {
    return gameSaveStorage(options || {}).restore();
  };

  var resolveConflict = async function (options) {
    options = options || {};
    var conflict = options.conflict || {};
    var kind = String(options.kind || conflict.kind || KIND_STATE);
    if (kind !== KIND_STATE && kind !== KIND_SAVE) throw new Error("Unsupported sync artifact kind.");
    var resolution = String(options.resolution || "").toLowerCase();
    if (!["local", "remote", "both"].includes(resolution)) throw new Error("Invalid conflict resolution.");
    var transport = transportFor(options);
    await syncPeerAuthorization(transport, options, kind);
    var storage = storageFor(kind, options);
    var device = String(options.deviceId || deviceId());
    if (!/^[A-Za-z0-9_-]{8,64}$/.test(device)) throw new Error("Invalid sync device identity.");
    var local = conflict.local;
    var remote = conflict.remote;
    if (!local || !remote) throw new Error("The conflict is missing one side's bytes.");
    var action = await transport.resolve({
        kind: kind,
        key: conflict.key,
        resolution: resolution,
        localHash: local.manifestHash || local.contentHash,
        remoteHash: remote.manifestHash || remote.contentHash,
    });
    if (kind === KIND_SAVE && conflict.setId && Array.isArray(local.members) && Array.isArray(remote.members)) {
      var identity = normalizeSaveIdentity(options.identity || local);
      if (resolution === "local") {
        await publishSaveSet(transport, device, identity, local, undefined, remote.manifestHash, options.context);
      } else {
        // Download and verify every remote member before either the canonical
        // set or a keep-both copy is handed to the storage adapter.
        var incomingSet = await downloadSaveSet(transport, remote, identity, options.context);
        var pending = [{set: incomingSet, asCopy: false}];
        if (resolution === "both") {
          var copySet = await buildSaveSet(identity, local.members, action.copyKey || conflict.copyKey || conflict.key + ".conflict");
          copySet.conflictOf = local.manifestHash;
          await publishSaveSet(transport, device, identity, copySet, copySet.setId, undefined, options.context);
          pending.unshift({set: copySet, asCopy: true});
        }
        await persistSaveSets(storage, identity, pending);
      }
      return {action: action, resolution: resolution};
    }
    if (resolution === "local") {
      await publish(transport, device, kind, local, undefined, options.context);
    } else {
      if (resolution === "both") await publish(transport, device, kind, local, action.copyKey || conflict.copyKey, options.context);
      var incoming = await download(transport, kind, remote, options.context);
      if (resolution === "both") await persistLocal(storage, kind, action.copyKey || conflict.copyKey, local.bytes, local.contentHash, local);
      await persistLocal(storage, kind, conflict.key, incoming, remote.contentHash, remote);
    }
    return {action: action, resolution: resolution};
  };

  globalThis.AN3SyncTransfer = Object.freeze({
    sync: syncKind,
    syncState: syncState,
    syncSave: syncSave,
    resolveConflict: resolveConflict,
    restoreGameSave: restoreGameSave,
    indexedStorage: indexedStorage,
    gameSaveStorage: gameSaveStorage,
    saveArtifactKey: saveArtifactKey,
    saveSetId: saveSetId,
    saveSetMemberKey: saveSetMemberKey,
    buildSaveSet: buildSaveSet,
    validateSaveSet: validateSaveSet,
    deviceId: deviceId,
    digestBytes: digestBytes,
    transportFor: transportFor,
  });
})();
