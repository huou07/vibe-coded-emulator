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

// A virtual control must never cover the emulated touch screen.  The shared
// resolver moves only the controls that would overlap the touch half, using
// runtime viewport geometry, while keeping controls that are already clear.
const controlSizes = {dpad:[157,157],a:[64,64],b:[64,64],x:[64,64],y:[64,64],l:[64,64],r:[64,64],start:[49,29],select:[49,29],stick:[112,112]};
const portraitPositions = {dpad:[23.4,81.6],a:[89,80],b:[78.2,89.7],x:[78,70.2],y:[67.3,79.9],l:[8.1,63.3],r:[91.2,62.5],start:[47.4,62.1],select:[57.9,62]};
const landscapePositions = {dpad:[13,69],a:[90,65],b:[80,76],x:[90,38],y:[80,50],l:[13,18],r:[87,18],start:[40,90],select:[60,90]};
const controlRect = (center, size) => ({left:center.x-size[0]/2,top:center.y-size[1]/2,right:center.x+size[0]/2,bottom:center.y+size[1]/2});
const pointsInRect = (rect, point) => point.x > rect.left && point.x < rect.right && point.y > rect.top && point.y < rect.bottom;
const layoutCases = [
  {name:"portrait phone 360x646", width:360, height:646, positions:portraitPositions, viewport:{left:0,top:0,width:360,height:540}, layout:"Top/Bottom"},
  {name:"tall portrait phone 412x738", width:412, height:738, positions:portraitPositions, viewport:{left:0,top:0,width:412,height:618}, layout:"Top/Bottom"},
  {name:"landscape phone 800x340", width:800, height:340, positions:landscapePositions, viewport:{left:0,top:20,width:800,height:300}, layout:"Left/Right"},
  {name:"wide landscape 900x420", width:900, height:420, positions:landscapePositions, viewport:{left:0,top:30,width:900,height:337}, layout:"Left/Right"},
];
assert.equal(typeof bridge.resolveTouchSafeControls, "function", "the safe layout resolver is exported");
assert.equal(typeof bridge.rectsIntersect, "function", "the geometry helpers are exported");
for (const testCase of layoutCases) {
  const controls = Object.keys(testCase.positions).map(id => ({
    id,
    width: controlSizes[id][0],
    height: controlSizes[id][1],
    center: {x:testCase.positions[id][0]/100*testCase.width, y:testCase.positions[id][1]/100*testCase.height}
  }));
  const frozen = JSON.stringify(controls);
  const solved = bridge.resolveTouchSafeControls({
    viewport: testCase.viewport,
    layout: testCase.layout,
    controls,
    bounds: {width:testCase.width,height:testCase.height},
    edgeGap: 4,
    controlGap: 4
  });
  assert.ok(solved, `${testCase.name} resolves a safe layout`);
  assert.equal(JSON.stringify(controls), frozen, `${testCase.name} never mutates the caller's controls`);
  assert.ok(solved.zone, `${testCase.name} reports the touch screen it protected`);
  const ids = Object.keys(solved.positions);
  assert.equal(ids.length, controls.length, `${testCase.name} keeps every control`);
  const rects = {};
  for (const id of ids) {
    rects[id] = controlRect(solved.positions[id], controlSizes[id]);
    assert.equal(bridge.rectsIntersect(rects[id], solved.zone), false, `${testCase.name} keeps ${id} clear of the touch screen`);
    assert.ok(rects[id].left >= 0 && rects[id].top >= 0 && rects[id].right <= testCase.width && rects[id].bottom <= testCase.height,
      `${testCase.name} keeps ${id} inside the play area`);
  }
  for (let first = 0; first < ids.length; first += 1) for (let second = first + 1; second < ids.length; second += 1) {
    assert.equal(bridge.rectsConflict(rects[ids[first]], rects[ids[second]], 4), false,
      `${testCase.name} keeps ${ids[first]} and ${ids[second]} non-overlapping`);
  }
  // The DS touch screen's center and four inset corners stay reachable, so a
  // tap meant for the emulated screen is never swallowed by a control.
  const zone = solved.zone;
  const reachable = [
    {x:zone.left+zone.width/2, y:zone.top+zone.height/2},
    {x:zone.left+2, y:zone.top+2}, {x:zone.right-2, y:zone.top+2},
    {x:zone.left+2, y:zone.bottom-2}, {x:zone.right-2, y:zone.bottom-2}
  ];
  for (const point of reachable) {
    assert.equal(ids.some(id => pointsInRect(rects[id], point)), false, `${testCase.name} leaves the touch screen reachable`);
  }
}
// A control the player placed clear of the screen keeps its exact position; a
// resize re-resolves against the new runtime geometry instead of a cached one.
{
  const clear = bridge.resolveTouchSafeControls({viewport:{left:0,top:0,width:360,height:540},layout:"Top/Bottom",
    controls:[{id:"x",width:64,height:64,center:{x:300,y:100}}],bounds:{width:360,height:646}});
  assert.equal(clear.positions.x.x, 300, "a clear custom position keeps its x");
  assert.equal(clear.positions.x.y, 100, "a clear custom position keeps its y");
  const resized = bridge.resolveTouchSafeControls({viewport:{left:0,top:0,width:360,height:540},layout:"Top/Bottom",
    controls:[{id:"x",width:64,height:64,center:{x:300,y:400}}],bounds:{width:360,height:646}});
  assert.equal(bridge.rectsIntersect(controlRect(resized.positions.x, controlSizes.x), resized.zone), false,
    "a resize that exposes a control to the screen re-resolves its slot");
}
// The analog stick is a round control like the D-pad and the round face
// buttons; it must use the same safe-slot resolution.
{
  const solved = bridge.resolveTouchSafeControls({viewport:{left:0,top:0,width:360,height:540},layout:"Top/Bottom",
    controls:[{id:"stick",width:112,height:112,center:{x:180,y:400}}],bounds:{width:360,height:646}});
  assert.equal(bridge.rectsIntersect(controlRect(solved.positions.stick, controlSizes.stick), solved.zone), false,
    "the analog stick is kept clear of the touch screen");
}
// Multitouch ownership: a finger on a virtual control and a finger on the NDS
// touch screen are independent. Ending the control finger must not release the
// active NDS gesture, and a non-owner end is rejected.
{
  const harness = makeGestureHarness();
  const ndsTouch = touch(110, 256, 576);
  const controlTouch = touch(111, 40, 700);
  assert.equal(harness.owner.start(ndsTouch).accepted, true, "the touch screen owns its finger");
  assert.equal(harness.owner.end(controlTouch).accepted, false, "a control finger cannot end the NDS gesture");
  assert.equal(harness.owner.end(controlTouch).reason, "non-owner-touch");
  assert.ok(harness.owner.active(), "the NDS gesture survives the unrelated finger");
  assert.equal(harness.owner.move(ndsTouch).accepted, true, "the NDS gesture keeps moving");
  assert.equal(harness.owner.end(ndsTouch).accepted, true, "the owning finger releases exactly once");
  assert.deepEqual(harness.output.map(event => event.type), ["press", "move", "release"]);
}
// Cancel and release are terminal, and a cancelled NDS gesture emits one
// cancel without leaving a stuck owner for the next touch.
{
  const harness = makeGestureHarness();
  const startTouch = touch(112, 256, 576);
  assert.equal(harness.owner.start(startTouch).accepted, true);
  assert.equal(harness.owner.end(startTouch, true).accepted, true);
  assert.deepEqual(harness.output.map(event => event.type), ["press", "cancel"]);
  assert.equal(harness.owner.active(), null, "a cancelled gesture leaves no active owner");
  const nextTouch = touch(113, 256, 576);
  assert.equal(harness.owner.start(nextTouch).accepted, true, "the next tap starts cleanly after a cancel");
  assert.equal(harness.owner.end(nextTouch).accepted, true);
  assert.deepEqual(harness.output.map(event => event.type), ["press", "cancel", "press", "release"]);
}

process.stdout.write("web NDS touch behavior: ok\n");
