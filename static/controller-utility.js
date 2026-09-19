// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Shared, host-agnostic dispatcher for the canonical Phone Controller utility
// actions. A host supplies the actual operations (its existing save/speed/menu
// code), so no host re-implements the action semantics or the replay guard.
(function (root, factory) {
  const model = factory();
  if (typeof module === "object" && module.exports) module.exports = model;
  else root.AN3ControllerUtility = model;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  // Canonical utility action identifiers, matching
  // native-offline/shared/input-actions-schema.json.
  const ACTIONS = ["QUICK_SAVE", "SPEED_UP", "SPEED_DOWN", "OPEN_MENU"];

  /**
   * Build a dispatcher around a host's existing operations. `operations` maps a
   * canonical action to a function; unknown actions are reported as unsupported
   * instead of being silently ignored. The per-press sequence makes the
   * dispatcher idempotent: a retried/duplicated entry never runs twice.
   */
  function createDispatcher(operations = {}) {
    let last = 0;
    return {
      actions: () => ACTIONS.slice(),
      get lastSequence() { return last; },
      reset() { last = 0; },
      supports(action) { return typeof operations[action] === "function"; },
      dispatch(utilities) {
        const results = [];
        for (const entry of Array.isArray(utilities) ? utilities : []) {
          const sequence = Number(entry && entry.sequence) || 0;
          if (sequence <= last) continue;
          last = sequence;
          const action = String((entry && entry.action) || "");
          const operation = operations[action];
          if (typeof operation !== "function") {
            results.push({action, sequence, ok: false, reason: "unsupported"});
            continue;
          }
          try {
            results.push({action, sequence, ok: true, value: operation()});
          } catch (error) {
            results.push({action, sequence, ok: false, reason: (error && error.message) || String(error)});
          }
        }
        return results;
      },
    };
  }

  return {ACTIONS, createDispatcher};
});
