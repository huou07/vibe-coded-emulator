// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Shell feature flags: which optional surfaces this installed app offers.
//
// These three switches gate whole screens and bridges (the Devices destination,
// LAN Sync, Phone Controller, the Eden companion), not emulator behaviour, so
// they are a property of the shell rather than a per-core setting. Keeping them
// in the core settings model made them depend on a platform settings adapter:
// Android had one, desktop had none, and the switches therefore became dead
// controls that no screen consumed. This module is the single store for the
// decision on every platform, so the toggle and the screen it reveals can never
// disagree.
//
// The ids and their labels/notes stay declared in the shared settings model
// (`native-settings.js`, generated from `shared/native-settings-schema.json`):
// one declaration, one default (off), and one place that explains each feature.
(() => {
  "use strict";
  const root = globalThis;
  const STORAGE_KEY = "an3-shell-flags-v1";
  const IDS = Object.freeze([
    "experimental-switch-eden",
    "experimental-lan-sync",
    "experimental-phone-controller",
  ]);

  // A desktop shell persists this store inside its WebView data directory and
  // Android inside the app's data directory; both survive an app update. A
  // denied storage backend must never turn a flag on, so a read failure means
  // "off" and a write failure is reported to the caller.
  const readStore = () => {
    try {
      const parsed = JSON.parse(root.localStorage?.getItem(STORAGE_KEY) || "{}");
      const values = parsed && typeof parsed === "object" ? parsed.values : null;
      return values && typeof values === "object" ? {...values} : {};
    } catch (_) {
      return {};
    }
  };
  const writeStore = values => {
    try {
      root.localStorage?.setItem(STORAGE_KEY, JSON.stringify({version: 1, values}));
      return true;
    } catch (_) {
      return false;
    }
  };

  const model = () => root.NativeSettingsModel;
  const definition = id => (model()?.global || []).find(item => item.id === id) || null;
  const flagIds = () => {
    const declared = (model()?.global || []).filter(item => item.category === "experimental");
    return declared.length ? declared.map(item => item.id) : [...IDS];
  };
  const valueOf = definition => {
    const declared = definition && typeof definition.default === "string" ? definition.default : "false";
    return String(declared).toLowerCase() === "true";
  };
  const labelOf = id => definition(id)?.label || id.replace(/^experimental-/, "").replace(/-/g, " ");
  const noteOf = id => definition(id)?.note || "";

  // A build that shipped the switches only inside the platform settings store
  // (Android 3.6.10 did) must not silently lose the user's choice. Adopt a
  // stored "on" once, when this store has no opinion yet, then own the value.
  const adoptedLegacy = new Set();
  const legacyValue = id => {
    if (adoptedLegacy.has(id)) return undefined;
    adoptedLegacy.add(id);
    let inherited;
    try {
      const raw = root.AN3NativeSettings || root.AN3AndroidSettings;
      const parsed = JSON.parse(raw?.all?.() || "{}");
      const value = parsed?.global?.[id];
      inherited = value === undefined || value === null ? undefined : String(value).toLowerCase() === "true";
    } catch (_) {
      return undefined;
    }
    // Persist the adopted value once, so the old store is consulted exactly
    // once and a later toggle can never be overridden by a stale preference.
    if (inherited !== undefined) {
      const values = readStore();
      if (values[id] !== inherited) {
        values[id] = inherited;
        writeStore(values);
      }
    }
    return inherited;
  };

  const read = id => {
    const values = readStore();
    if (Object.prototype.hasOwnProperty.call(values, id)) return values[id] === true;
    const inherited = legacyValue(id);
    return inherited === undefined ? valueOf(definition(id)) : inherited;
  };

  const subscribers = new Set();
  const notify = changed => {
    const snapshot = all();
    for (const listener of [...subscribers]) {
      try { listener(snapshot, changed); } catch (_) { /* a view must not break the store */ }
    }
  };

  const set = (id, value) => {
    if (!flagIds().includes(id)) throw new Error(`Unknown feature flag: ${id}`);
    const next = value === true || String(value).toLowerCase() === "true";
    const values = readStore();
    if (values[id] === next) return true;
    values[id] = next;
    if (!writeStore(values)) return false;
    notify({id, value: next});
    return true;
  };

  const all = () => {
    const result = {};
    for (const id of flagIds()) result[id] = read(id);
    return result;
  };

  const anyOn = () => Object.values(all()).some(Boolean);

  root.AN3ShellFlags = Object.freeze({
    ids: flagIds,
    definitions: () => flagIds().map(id => ({id, label: labelOf(id), note: noteOf(id)})),
    get: read,
    set,
    all,
    anyOn,
    subscribe: listener => {
      subscribers.add(listener);
      return () => subscribers.delete(listener);
    },
    // Test seam: forget the cached legacy adoption and re-read storage.
    reset: () => { adoptedLegacy.clear(); },
    storageKey: STORAGE_KEY,
  });
})();
