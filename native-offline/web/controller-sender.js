// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
(function (root) {
  "use strict";

  const MAX_PENDING_EVENTS = 64;

  function create(options) {
    const send = options.send;
    const requestFrame = options.requestFrame || (callback => root.requestAnimationFrame(callback));
    const onFailure = options.onFailure || (() => {});
    const maxPendingEvents = options.maxPendingEvents || MAX_PENDING_EVENTS;
    let events = [];
    let motion = null;
    let sequence = 0;
    let generation = 0;
    let frameScheduled = false;
    let failed = false;
    let activePump = null;

    const hasPending = () => events.length > 0 || motion !== null;

    const fail = error => {
      if (failed) return;
      failed = true;
      events = [];
      motion = null;
      frameScheduled = false;
      generation += 1;
      onFailure(error instanceof Error ? error : new Error(String(error)));
    };

    const pump = () => {
      if (activePump || failed) return activePump || Promise.resolve();
      const pumpGeneration = generation;
      activePump = (async () => {
        while (!failed && pumpGeneration === generation && hasPending()) {
          const item = events.length ? events.shift() : motion;
          if (!events.length && item === motion) motion = null;
          if (!item) continue;
          const frame = Object.assign({}, item.payload, {
            _an3q: item.kind,
            s: ++sequence
          });
          const result = await send(frame);
          if (result && result.error) throw new Error(result.error);
        }
      })().catch(error => {
        // A send from a controller session that has since been reset must not
        // poison the new session if its old bridge promise rejects late.
        if (pumpGeneration === generation) fail(error);
      }).finally(() => {
        activePump = null;
        if (!failed && hasPending()) void pump();
      });
      return activePump;
    };

    const enqueue = (payload, kind) => {
      if (failed) return false;
      const item = {payload: Object.assign({}, payload), kind: kind === "motion" ? "motion" : "event"};
      if (item.kind === "motion") {
        motion = item;
      } else {
        if (events.length >= maxPendingEvents) {
          fail(new Error("Controller event queue is full; the session was stopped to preserve input transitions."));
          return false;
        }
        // A complete discrete snapshot supersedes any older unsent motion.
        motion = null;
        events.push(item);
      }
      void pump();
      return true;
    };

    const scheduleMotion = makeSnapshot => {
      if (failed || frameScheduled) return false;
      frameScheduled = true;
      requestFrame(() => {
        frameScheduled = false;
        if (!failed) enqueue(makeSnapshot(), "motion");
      });
      return true;
    };

    const reset = () => {
      generation += 1;
      events = [];
      motion = null;
      sequence = 0;
      failed = false;
      frameScheduled = false;
    };

    const waitForIdle = async () => {
      while (activePump || hasPending()) {
        if (!activePump) void pump();
        if (activePump) await activePump;
      }
    };

    const stats = () => ({pendingEvents: events.length, hasMotion: motion !== null, failed});
    return {enqueue, scheduleMotion, reset, waitForIdle, stats};
  }

  root.AN3NativeControllerSender = {create, MAX_PENDING_EVENTS};
})(globalThis);
