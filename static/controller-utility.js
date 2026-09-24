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
  const ACTIONS = ["QUICK_SAVE", "QUICK_LOAD", "SPEED_UP", "SPEED_DOWN", "OPEN_MENU"];

  /**
   * Build a dispatcher around a host's existing operations. `operations` maps a
   * canonical action to a function; unknown actions are reported as unsupported
   * instead of being silently ignored. The per-press sequence makes the
   * dispatcher idempotent: a retried/duplicated entry never runs twice.
   */
  function createDispatcher(operations = {}) {
    let last = 0;
    let seenCommandIds = new Set();
    let commandOrder = [];
    return {
      actions: () => ACTIONS.slice(),
      get lastSequence() { return last; },
      reset() { last = 0; seenCommandIds = new Set(); commandOrder = []; },
      supports(action) { return typeof operations[action] === "function"; },
      dispatch(utilities) {
        const results = [];
        for (const entry of Array.isArray(utilities) ? utilities : []) {
          const sequence = Number(entry && entry.sequence) || 0;
          const commandId = String((entry && (entry.command_id || entry.commandId)) || "").trim();
          if (commandId) {
            if (seenCommandIds.has(commandId)) continue;
            seenCommandIds.add(commandId);
            commandOrder.push(commandId);
            if (commandOrder.length > 64) {
              const oldest = commandOrder.shift();
              seenCommandIds.delete(oldest);
            }
          } else {
            if (sequence <= last) continue;
          }
          last = Math.max(last, sequence);
          const action = String((entry && entry.action) || "").toUpperCase();
          const operation = operations[action];
          if (typeof operation !== "function") {
            results.push({action, sequence, command_id: commandId, ok: false, reason: "unsupported"});
            continue;
          }
          const rawSlot = Number(entry && entry.slot);
          const slot = Number.isInteger(rawSlot) && rawSlot >= 1 && rawSlot <= 10 ? rawSlot : null;
          const command = {action, sequence, command_id: commandId, slot};
          try {
            results.push({action, sequence, command_id: commandId, slot, ok: true, value: operation(command)});
          } catch (error) {
            results.push({action, sequence, command_id: commandId, slot, ok: false, reason: (error && error.message) || String(error)});
          }
        }
        return results;
      },
    };
  }

  return {ACTIONS, createDispatcher};
});
