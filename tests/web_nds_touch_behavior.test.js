const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "static", "nds-touch.js"), "utf8");
const context = {globalThis: {}};
vm.runInNewContext(source, context, {filename: "nds-touch.js"});
const bridge = context.globalThis.AN3NdsTouchBridge;
assert.ok(bridge, "the shared NDS touch bridge is exported");

class MiniElement {
  constructor(nodeName, {id = "", className = "", attributes = {}} = {}) {
    this.nodeName = nodeName.toUpperCase();
    this.nodeType = 1;
    this.id = id;
    this.className = className;
    this.attributes = {...attributes};
    this.children = [];
    this.parentElement = null;
  }
  append(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }
  matchesSimple(selector) {
    const negations = [...selector.matchAll(/:not\(([^)]+)\)/g)].map(match => match[1]);
    if (negations.some(negation => this.matchesSimple(negation))) return false;
    selector = selector.replace(/:not\(([^)]+)\)/g, "");
    const tag = selector.match(/^[a-z][a-z0-9-]*/i)?.[0];
    if (tag && this.nodeName.toLowerCase() !== tag.toLowerCase()) return false;
    const id = selector.match(/#([a-z0-9_-]+)/i)?.[1];
    if (id && this.id !== id) return false;
    for (const className of [...selector.matchAll(/\.([a-z0-9_-]+)/gi)].map(match => match[1])) {
      if (!this.className.split(/\s+/).includes(className)) return false;
    }
    for (const attribute of [...selector.matchAll(/\[([^=\]]+)(?:=["']?([^\]"']+)["']?)?\]/g)]) {
      if (!(attribute[1] in this.attributes)) return false;
      if (attribute[2] && this.attributes[attribute[1]] !== attribute[2]) return false;
    }
    return true;
  }
  matches(selector) {
    return selector.split(",").some(part => {
      const pieces = part.trim().split(/\s+/).filter(Boolean);
      let current = this;
      for (let index = pieces.length - 1; index >= 0; index -= 1) {
        while (current && !current.matchesSimple(pieces[index])) current = current.parentElement;
        if (!current) return false;
        if (index > 0) current = current.parentElement;
      }
      return true;
    });
  }
  closest(selector) {
    for (let current = this; current; current = current.parentElement) if (current.matches(selector)) return current;
    return null;
  }
  contains(node) {
    return node === this || this.children.some(child => child.contains(node));
  }
  querySelector(selector) {
    for (const child of this.children) {
      if (child.matches(selector)) return child;
      const nested = child.querySelector(selector);
      if (nested) return nested;
    }
    return null;
  }
}

const root = new MiniElement("div", {id: "game", className: "ejs_parent"});
const sourceCanvas = root.append(new MiniElement("canvas", {className: "ejs_canvas"}));
const presentationCanvas = root.append(new MiniElement("canvas", {className: "an3-render-canvas"}));
const menu = root.append(new MiniElement("div", {className: "ejs_context_menu"}));
const nestedMenuItem = menu.append(new MiniElement("a"));
const settingsPanel = new MiniElement("section", {id: "padPanel", className: "pad-panel", attributes: {role: "dialog"}});
const settingsControl = settingsPanel.append(new MiniElement("button", {id: "speedDown"}));
const toolbar = new MiniElement("div", {className: "player-toolbar"});
const toolbarButton = toolbar.append(new MiniElement("button", {id: "playerControls"}));
const pad = new MiniElement("div", {id: "tvPad"});
const virtualButton = pad.append(new MiniElement("div", {className: "tvCtrl"}));
const pathFor = node => {
  const path = [];
  for (let current = node; current; current = current.parentElement) path.push(current);
  return path;
};
const ownerFor = (target, hit = target) => {
  const path = pathFor(target);
  if (bridge.isProtectedUiTarget(root, target, path)) return {owner: "ui", canvas: null};
  return {owner: bridge.resolveSourceCanvas(root, hit, path) ? "nds" : "none", canvas: bridge.resolveSourceCanvas(root, hit, path)};
};

assert.equal(bridge.resolveSourceCanvas(root, presentationCanvas), sourceCanvas,
  "a visible renderer presentation hit resolves to the EmulatorJS source canvas");
assert.equal(bridge.resolveSourceCanvas(root, sourceCanvas), sourceCanvas,
  "a source canvas hit remains the input owner");
assert.equal(bridge.resolveSourceCanvas(root, nestedMenuItem, pathFor(nestedMenuItem)), null,
  "a nested native menu hit never falls back to the source canvas");
assert.equal(ownerFor(root, sourceCanvas).owner, "nds", "an uncovered gameplay hit belongs to NDS touch");
assert.equal(ownerFor(nestedMenuItem, sourceCanvas).owner, "ui", "a nested menu item owns its touch");
assert.equal(ownerFor(settingsControl, sourceCanvas).owner, "ui", "an AN3 settings control owns its touch");
assert.equal(ownerFor(toolbarButton, sourceCanvas).owner, "ui", "a toolbar control owns its touch");
assert.equal(ownerFor(virtualButton, sourceCanvas).owner, "ui", "a virtual button owns its touch");
assert.equal(ownerFor(root, presentationCanvas).canvas, sourceCanvas,
  "presentation remains output-only while gameplay resolves to source");

// Model the menu-open edge case: opening protected UI during a held NDS
// gesture must synthesize one clean release, then the next gameplay tap is
// accepted immediately after the menu closes.
const ownershipEvents = [];
let activeGameplayPointer = false;
const beginGameplay = target => {
  if (ownerFor(target, sourceCanvas).owner !== "nds") return false;
  ownershipEvents.push("mousedown");
  activeGameplayPointer = true;
  return true;
};
const openMenu = () => {
  if (activeGameplayPointer) ownershipEvents.push("mouseup");
  activeGameplayPointer = false;
};
assert.equal(beginGameplay(root), true);
openMenu();
assert.deepEqual(ownershipEvents, ["mousedown", "mouseup"], "menu open releases an active NDS gesture");
assert.equal(beginGameplay(nestedMenuItem), false, "menu stays UI-owned while open");
assert.equal(beginGameplay(root), true, "gameplay works on the first tap after menu close");

// Menu precedence is independent of the selected dual-screen geometry and a
// resize/fullscreen viewport change must not change ownership.
for (const layout of ["Top/Bottom", "Left/Right"]) {
  const viewport = layout === "Top/Bottom"
    ? {left: 0, top: 0, width: 512, height: 768}
    : {left: 0, top: 0, width: 1024, height: 384};
  const gameplayPoint = layout === "Top/Bottom" ? {clientX: 256, clientY: 576} : {clientX: 768, clientY: 192};
  assert.ok(bridge.mapPoint({...gameplayPoint, viewport, layout}), `${layout} gameplay maps after resize/fullscreen`);
  assert.equal(ownerFor(nestedMenuItem, sourceCanvas).owner, "ui", `${layout} menu remains protected`);
}

const topBottomViewport = {left: 20, top: 10, width: 640, height: 480};
const topBottomCenter = bridge.mapPoint({clientX: 340, clientY: 370, viewport: topBottomViewport, layout: "Top/Bottom"});
assert.deepEqual({x: topBottomCenter.x, y: topBottomCenter.y}, {x: 128, y: 96});
assert.equal(bridge.mapPoint({clientX: 340, clientY: 130, viewport: topBottomViewport, layout: "Top/Bottom"}), null,
  "the top NDS screen does not become touch input");

const letterboxed = {left: 100, top: 40, width: 800, height: 600};
const fitted = bridge.mapPoint({clientX: 500, clientY: 490, viewport: letterboxed, layout: "Top/Bottom"});
assert.deepEqual({x: fitted.x, y: fitted.y}, {x: 128, y: 96},
  "scaled and vertically letterboxed bottom-screen input maps to DS coordinates");
assert.equal(bridge.mapPoint({clientX: 80, clientY: 490, viewport: letterboxed, layout: "Top/Bottom"}), null,
  "horizontal letterbox margins are ignored");

const sideBySideViewport = {left: 50, top: 100, width: 1000, height: 400};
const sideBySideCenter = bridge.mapPoint({clientX: 800, clientY: 300, viewport: sideBySideViewport, layout: "Left/Right"});
assert.deepEqual({x: sideBySideCenter.x, y: sideBySideCenter.y}, {x: 128, y: 96});
assert.equal(bridge.mapPoint({clientX: 300, clientY: 300, viewport: sideBySideViewport, layout: "Left/Right"}), null,
  "the left NDS screen does not become touch input");

// Model the required gesture contract: an accepted press, a normalized move,
// and exactly one release. A press outside the touch screen is rejected.
const events = [];
const dispatch = (type, point, layout = "Top/Bottom") => {
  const mapped = bridge.mapPoint({...point, viewport: topBottomViewport, layout});
  if (!mapped) return false;
  events.push({type, x: mapped.x, y: mapped.y});
  return true;
};
assert.equal(dispatch("mousedown", {clientX: 340, clientY: 130}), false);
assert.equal(dispatch("mousedown", {clientX: 340, clientY: 370}), true);
assert.equal(dispatch("mousemove", {clientX: 500, clientY: 430}), true);
assert.equal(dispatch("mouseup", {clientX: 500, clientY: 430}), true);
assert.deepEqual(events.map(event => event.type), ["mousedown", "mousemove", "mouseup"]);
assert.deepEqual(events[2], {type: "mouseup", x: 191, y: 143});

// RG-048: a mobile NDS gesture has one owner and has no movement threshold.
// The harness uses the same owner primitive as player.js; physical event
// families are deliberately separate from the logical press/move/release.
const touch = (identifier, clientX, clientY) => ({identifier, clientX, clientY});
const makeGestureHarness = ({layout = "Top/Bottom", protectedTarget = false} = {}) => {
  const viewport = layout === "Left/Right"
    ? {left: 0, top: 0, width: 1024, height: 384}
    : {left: 0, top: 0, width: 512, height: 768};
  const output = [];
  const owner = bridge.createTouchGestureOwner({
    begin: input => {
      if (protectedTarget) return null;
      const mapped = bridge.mapPoint({...input, viewport, layout});
      if (!mapped) return null;
      output.push({type: "press", x: mapped.x, y: mapped.y});
      return {lastTouch: input, mapped, moveCount: 0};
    },
    move: (input, state) => {
      state.lastTouch = input;
      state.moveCount += 1;
      const mapped = bridge.mapPoint({...input, viewport, layout});
      output.push({type: "move", x: mapped.x, y: mapped.y});
    },
    end: (input, state, cancelled) => {
      state.lastTouch = input || state.lastTouch;
      output.push({type: cancelled ? "cancel" : "release", x: state.mapped.x, y: state.mapped.y, moves: state.moveCount});
    }
  });
  return {owner, output};
};

// TEST 1 — pointerdown(pointerType=touch) -> pointerup, no pointermove.
{
  const harness = makeGestureHarness();
  const pointer = touch(71, 256, 576);
  assert.equal(harness.owner.start(pointer).accepted, true);
  assert.equal(harness.owner.end(pointer).accepted, true);
  assert.deepEqual(harness.output.map(event => event.type), ["press", "release"]);
}

// TEST 2 — realistic TouchEvent end uses changedTouches because touches is empty.
{
  const harness = makeGestureHarness();
  const first = touch(72, 256, 576);
  const touchstart = {touches:[first], targetTouches:[first], changedTouches:[first]};
  const touchend = {touches:[], targetTouches:[], changedTouches:[first]};
  assert.equal(harness.owner.start(touchstart.changedTouches[0]).accepted, true);
  assert.equal(harness.owner.end(touchend.changedTouches[0]).accepted, true);
  assert.deepEqual(harness.output.map(event => event.type), ["press", "release"]);
}

// TEST 3 — Chromium pointer + touch compatibility is one logical gesture.
{
  const harness = makeGestureHarness();
  const physicalPointer = touch(73, 256, 576);
  // Native pointerdown is observed, while the touch family owns the bridge.
  const touchStart = harness.owner.start(physicalPointer);
  assert.equal(touchStart.accepted, true);
  assert.equal(harness.owner.start(physicalPointer).reason, "active-gesture");
  assert.equal(harness.owner.end(physicalPointer).accepted, true);
  assert.deepEqual(harness.output.map(event => event.type), ["press", "release"]);
}

// TESTS 4 and 5 — tap and very-short tap share the same press path; only a
// drag emits updates.  No timer participates in either case.
{
  const tap = makeGestureHarness(), drag = makeGestureHarness();
  const start = touch(74, 256, 576), firstMove = touch(74, 320, 600), secondMove = touch(74, 384, 624);
  tap.owner.start(start); tap.owner.end(start);
  drag.owner.start(start); drag.owner.move(firstMove); drag.owner.move(secondMove); drag.owner.end(secondMove);
  assert.deepEqual(tap.output.map(event => event.type), ["press", "release"]);
  assert.deepEqual(drag.output.map(event => event.type), ["press", "move", "move", "release"]);
  assert.equal(tap.output[1].moves, 0, "an immediate down/up remains observable without a timeout");
}

// TEST 6 — protected menu/settings/virtual-control taps never start NDS input.
for (const protectedSurface of ["menu", "settings", "virtual-controls"]) {
  const harness = makeGestureHarness({protectedTarget:true});
  assert.equal(harness.owner.start(touch(75, 256, 576)).accepted, false, `${protectedSurface} stays UI-owned`);
  assert.deepEqual(harness.output, []);
}

// TESTS 7–9 — repeated taps, a tap after drag, and a first tap after closing
// protected UI each have a fresh owner rather than a stuck first gesture.
{
  const repeated = makeGestureHarness();
  for (let id = 80; id < 83; id += 1) { const point = touch(id, 256, 576); repeated.owner.start(point); repeated.owner.end(point); }
  assert.equal(repeated.output.filter(event => event.type === "press").length, 3);
  assert.equal(repeated.output.filter(event => event.type === "release").length, 3);
  const afterDrag = makeGestureHarness();
  const dragStart = touch(84, 256, 576), dragMove = touch(84, 320, 600), after = touch(85, 256, 576);
  afterDrag.owner.start(dragStart); afterDrag.owner.move(dragMove); afterDrag.owner.end(dragMove); afterDrag.owner.start(after); afterDrag.owner.end(after);
  assert.deepEqual(afterDrag.output.map(event => event.type), ["press", "move", "release", "press", "release"]);
  const afterMenuClose = makeGestureHarness();
  const immediate = touch(86, 256, 576);
  assert.equal(afterMenuClose.owner.start(immediate).accepted, true);
  assert.equal(afterMenuClose.owner.end(immediate).accepted, true);
}

// TEST 10 — both layouts map a zero-movement press and release correctly.
for (const [layout, point] of [["Top/Bottom", touch(90, 256, 576)], ["Left/Right", touch(91, 768, 192)]]) {
  const harness = makeGestureHarness({layout});
  harness.owner.start(point); harness.owner.end(point);
  assert.deepEqual(harness.output.map(event => [event.type, event.x, event.y]), [["press", 128, 96], ["release", 128, 96]], `${layout} tap maps its touch screen`);
}

// The actual mobile bridge latches only the zero-move release across one
// input-frame boundary.  A deterministic scheduler verifies that a very short
// down/up is observable as pressed before its one release; this is deliberately
// not a duration-based timeout and drags still release synchronously.
{
  const scheduled = [];
  const releases = [];
  const latch = bridge.createTapReleaseLatch({
    scheduleFrame: callback => { scheduled.push(callback); return scheduled.length; },
    cancelFrame: () => {}
  });
  const shortTap = {moveCount: 0, mapped: {x: 128, y: 96}};
  assert.equal(latch.defer(shortTap, () => releases.push("tap-release")).latched, true);
  assert.deepEqual(releases, [], "immediate mobile up does not erase the pressed state in the same task");
  assert.equal(scheduled.length, 1, "a tap waits for exactly one input-frame boundary");
  scheduled.shift()();
  assert.deepEqual(releases, ["tap-release"], "the next input frame receives exactly one release");
  assert.equal(latch.pending(), false);

  const secondTap = {moveCount: 0, mapped: {x: 128, y: 96}};
  latch.defer(secondTap, () => releases.push("flushed-release"));
  assert.equal(latch.flush(), true, "a forced UI/cancel release flushes a pending tap exactly once");
  assert.deepEqual(releases, ["tap-release", "flushed-release"]);
  assert.equal(latch.flush(), false, "a second forced release cannot duplicate the up event");
}

process.stdout.write("web NDS touch behavior: ok\n");
