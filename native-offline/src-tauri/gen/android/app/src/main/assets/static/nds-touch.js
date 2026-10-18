// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
(() => {
  const SOURCE_SELECTOR = "#game canvas:not(.an3-render-canvas)";
  const SCREEN_WIDTH = 256;
  const SCREEN_HEIGHT = 192;
  const PROTECTED_UI_SELECTOR = [
    "#game .ejs_menu_bar",
    "#game .ejs_context_menu",
    "#game .ejs_popup_body",
    ".player-toolbar",
    "#fullscreen",
    "#toggleTouch",
    "#slotMenu",
    "#playerControls",
    "#tvPad",
    ".pad-panel",
    ".slot-panel",
    ".player-stage-ui [role=\"dialog\"]",
    ".player-stage-ui [aria-modal=\"true\"]",
    ".player-stage-ui dialog",
    ".player-stage-ui .modal"
  ].join(",");

  const finite = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
  const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));

  const isSideBySide = layout => String(layout || "").toLowerCase().replace(/[^a-z]/g, "") === "leftright";

  const inflateRect = (rect, amount) => {
    const left = finite(rect?.left), top = finite(rect?.top);
    const right = finite(rect?.right, left + finite(rect?.width));
    const bottom = finite(rect?.bottom, top + finite(rect?.height));
    return {left: left - amount, top: top - amount, right: right + amount, bottom: bottom + amount};
  };
  const rectsIntersect = (first, second) => Boolean(first && second) &&
    first.left < second.right && first.right > second.left &&
    first.top < second.bottom && first.bottom > second.top;
  const rectsConflict = (first, second, gap) => Boolean(first && second) &&
    first.left < second.right + gap && first.right + gap > second.left &&
    first.top < second.bottom + gap && first.bottom + gap > second.top;
  const rectFromCenter = (center, width, height) => ({
    left: center.x - width / 2,
    top: center.y - height / 2,
    right: center.x + width / 2,
    bottom: center.y + height / 2
  });

  const asElement = node => node?.nodeType === 1 ? node : node?.parentElement || null;
  const isProtectedUiTarget = (root, target, composedPath = []) => {
    const nodes = composedPath.length ? composedPath : [target];
    return nodes.some(node => {
      const element = asElement(node);
      if (!element) return false;
      return Boolean(element.matches?.(PROTECTED_UI_SELECTOR) || element.closest?.(PROTECTED_UI_SELECTOR));
    });
  };

  // The renderer's canvas is deliberately a presentation-only layer. Touch
  // must resolve to the EmulatorJS source canvas even when the presentation
  // layer is visible or the browser reports it as the hit-test target.
  const resolveSourceCanvas = (root, hit, composedPath = []) => {
    // A source-canvas fallback is correct for a presentation hit, but never
    // for a protected UI hit. The root bridge must not turn a menu/settings
    // gesture into a synthetic NDS gesture merely because the source canvas
    // remains structurally present underneath it.
    if (isProtectedUiTarget(root, hit, composedPath)) return null;
    const candidate = hit?.closest?.(SOURCE_SELECTOR) || null;
    if (candidate && root?.contains?.(candidate)) return candidate;
    return root?.querySelector?.(SOURCE_SELECTOR) || null;
  };

  // `viewport` is the composite NDS image in client/CSS coordinates. The
  // core layout determines which half is the touch screen; the map remains
  // stable for scaled, aspect-fitted, and letterboxed canvases.
  const touchScreenRect = (viewport, layout) => {
    const left = finite(viewport?.left);
    const top = finite(viewport?.top);
    const width = Math.max(0, finite(viewport?.width));
    const height = Math.max(0, finite(viewport?.height));
    if (!(width > 0 && height > 0)) return null;
    if (isSideBySide(layout)) {
      return {left: left + width / 2, top, width: width / 2, height, layout: "Left/Right"};
    }
    return {left, top: top + height / 2, width, height: height / 2, layout: "Top/Bottom"};
  };

  const mapPoint = ({clientX, clientY, viewport, layout}) => {
    const rect = touchScreenRect(viewport, layout);
    if (!rect || !(rect.width > 0 && rect.height > 0)) return null;
    const x = finite(clientX);
    const y = finite(clientY);
    if (x < rect.left || x > rect.left + rect.width || y < rect.top || y > rect.top + rect.height) return null;
    const normalizedX = clamp((x - rect.left) / rect.width, 0, 1);
    const normalizedY = clamp((y - rect.top) / rect.height, 0, 1);
    return {
      x: Math.round(normalizedX * (SCREEN_WIDTH - 1)),
      y: Math.round(normalizedY * (SCREEN_HEIGHT - 1)),
      normalizedX,
      normalizedY,
      screenRect: rect
    };
  };

  // One physical finger owns one NDS gesture.  The owner deliberately has no
  // movement threshold: a mapped DOWN followed immediately by UP is a valid
  // touchscreen tap.  Keeping this small state machine separate from browser
  // event families lets the player use TouchEvent lifecycle tracking without
  // allowing a compatibility PointerEvent or a second finger to steal it.
  const createTouchGestureOwner = ({begin, move, end}) => {
    let active = null;
    const result = (accepted, reason, state = null) => ({accepted, reason, state});
    const matches = touch => active && touch?.identifier === active.id;
    return Object.freeze({
      start(touch) {
        if (active) return result(false, "active-gesture");
        const state = begin?.(touch);
        if (!state) return result(false, "down-rejected");
        active = {id: touch.identifier, state};
        return result(true, "logical-down", state);
      },
      move(touch) {
        if (!active) return result(false, "no-active-gesture");
        if (!matches(touch)) return result(false, "non-owner-touch");
        move?.(touch, active.state);
        return result(true, "logical-move", active.state);
      },
      end(touch, cancelled = false) {
        if (!active) return result(false, "no-active-gesture");
        if (!matches(touch)) return result(false, "non-owner-touch");
        const current = active;
        active = null;
        end?.(touch, current.state, cancelled);
        return result(true, cancelled ? "logical-cancel" : "logical-up", current.state);
      },
      release(cancelled = true) {
        if (!active) return result(false, "no-active-gesture");
        const current = active;
        active = null;
        end?.(current.state.lastTouch, current.state, cancelled);
        return result(true, cancelled ? "logical-cancel" : "logical-up", current.state);
      },
      active() { return active ? {id: active.id, state: active.state} : null; }
    });
  };

  // EmulatorJS samples the touchscreen from its animation/input loop. A native
  // mobile tap can deliver DOWN and UP in the same task (measured at 4 ms on
  // Android Chrome), before that loop can observe the pressed state. Keep only
  // a zero-move release through the next input-frame boundary. This is not a
  // timer and never delays a drag; cancellation and forced UI release flush
  // immediately so a later gesture cannot inherit a stale pressed state.
  const createTapReleaseLatch = ({scheduleFrame, cancelFrame} = {}) => {
    const schedule = scheduleFrame || (callback => globalThis.requestAnimationFrame(callback));
    const cancel = cancelFrame || (handle => globalThis.cancelAnimationFrame?.(handle));
    let pending = null;
    const finish = candidate => {
      if (!candidate || pending !== candidate) return false;
      pending = null;
      candidate.release();
      return true;
    };
    return Object.freeze({
      defer(state, release) {
        if (pending) finish(pending);
        const candidate = {release, handle: null, state};
        pending = candidate;
        candidate.handle = schedule(() => finish(candidate));
        return {latched: true, state};
      },
      flush() {
        if (!pending) return false;
        try { cancel(pending.handle); } catch (_) {}
        return finish(pending);
      },
      pending() { return Boolean(pending); }
    });
  };

  // Virtual controls and the emulated touch screen share one glass. A control
  // that sits over the touch half silently steals the taps meant for the DS
  // game, so the pad must resolve the touch screen from runtime geometry and
  // keep its controls clear of it. Controls already clear of the screen keep
  // exactly the position the player chose; only a control that would cover the
  // screen is moved, and only as far as the nearest free slot inside the play
  // area allows. Positions are returned in the same coordinate space as the
  // supplied viewport/bounds and never mutate the caller's saved layout.
  const resolveTouchSafeControls = ({viewport, layout, controls, bounds, edgeGap = 4, controlGap = 4, step = 4} = {}) => {
    const screen = touchScreenRect(viewport, layout);
    if (!screen || !(screen.width > 0 && screen.height > 0)) return null;
    const area = bounds || viewport;
    if (!(area?.width > 0 && area?.height > 0) || !Array.isArray(controls)) return null;
    const forbidden = inflateRect(screen, controlGap);
    const placed = [];
    const positions = {};
    const insideBounds = rect =>
      rect.left >= edgeGap && rect.top >= edgeGap &&
      rect.right <= area.width - edgeGap && rect.bottom <= area.height - edgeGap;
    const free = rect => insideBounds(rect) && !rectsIntersect(rect, forbidden) &&
      !placed.some(other => rectsConflict(rect, other.rect, controlGap));
    const entries = controls.map(control => {
      const width = Math.max(0, finite(control?.width));
      const height = Math.max(0, finite(control?.height));
      const center = {x: finite(control?.center?.x), y: finite(control?.center?.y)};
      return {id: control?.id, width, height, center, rect: rectFromCenter(center, width, height)};
    }).filter(entry => entry.id && entry.width > 0 && entry.height > 0);
    const blocked = entries.filter(entry => rectsIntersect(entry.rect, forbidden));
    const settled = entries.filter(entry => !rectsIntersect(entry.rect, forbidden));
    for (const entry of settled) {
      positions[entry.id] = entry.center;
      placed.push({id: entry.id, rect: entry.rect});
    }
    // Move the controls that only just touch the screen first, so the layout
    // stays as close as possible to the player's arrangement.
    const nearestEscape = rect => Math.min(
      Math.abs(rect.bottom - forbidden.top),
      Math.abs(forbidden.bottom - rect.top),
      Math.abs(rect.right - forbidden.left),
      Math.abs(forbidden.right - rect.left)
    );
    blocked.sort((first, second) => nearestEscape(first.rect) - nearestEscape(second.rect));
    const searchStep = Math.max(2, finite(step, 4));
    for (const entry of blocked) {
      let best = null, bestDistance = Infinity;
      for (let y = edgeGap + entry.height / 2; y <= area.height - edgeGap - entry.height / 2; y += searchStep) {
        for (let x = edgeGap + entry.width / 2; x <= area.width - edgeGap - entry.width / 2; x += searchStep) {
          const candidate = rectFromCenter({x, y}, entry.width, entry.height);
          if (!free(candidate)) continue;
          const distance = (x - entry.center.x) ** 2 + (y - entry.center.y) ** 2;
          if (distance < bestDistance) { bestDistance = distance; best = {x, y}; }
        }
      }
      // No free slot means the play area cannot fit every control outside the
      // screen; keep the player's position rather than losing the control.
      const chosen = best || entry.center;
      positions[entry.id] = chosen;
      placed.push({id: entry.id, rect: rectFromCenter(chosen, entry.width, entry.height)});
    }
    return {zone: screen, positions};
  };

  globalThis.AN3NdsTouchBridge = Object.freeze({
    SOURCE_SELECTOR,
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    isSideBySide,
    PROTECTED_UI_SELECTOR,
    isProtectedUiTarget,
    resolveSourceCanvas,
    touchScreenRect,
    mapPoint,
    createTouchGestureOwner,
    createTapReleaseLatch,
    rectsIntersect,
    rectsConflict,
    resolveTouchSafeControls
  });
})();
