import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";
import "../native-offline/web/controller-sender.js";

const createSender = globalThis.AN3NativeControllerSender.create;

test("1000 motion events scheduled in one display frame send one latest snapshot", async () => {
  const frames = [];
  const sent = [];
  const sender = createSender({
    send: async frame => { sent.push(frame); },
    requestFrame: callback => frames.push(callback)
  });
  let latestX = 0;
  for (let x = 1; x <= 1000; x += 1) {
    latestX = x;
    sender.scheduleMotion(() => ({a: [latestX, 0, 0, 0], b: []}));
  }
  assert.equal(frames.length, 1, "raw pointer motion creates one animation-frame callback");
  frames.shift()();
  await sender.waitForIdle();
  assert.equal(sent.length, 1);
  assert.equal(sent[0]._an3q, "motion");
  assert.deepEqual(sent[0].a, [1000, 0, 0, 0]);
  assert.equal(sent[0].s, 1);
});

test("button and touch edges stay ordered around coalesced movement and utilities", async () => {
  const sent = [];
  let releaseFirst;
  let firstStarted;
  const started = new Promise(resolve => { firstStarted = resolve; });
  const firstGate = new Promise(resolve => { releaseFirst = resolve; });
  const sender = createSender({send: async frame => {
    sent.push(frame);
    if (sent.length === 1) {
      firstStarted();
      await firstGate;
    }
  }});

  sender.enqueue({b: ["a"], a: [0, 0, 0, 0]}, "event");
  await started;
  sender.enqueue({b: ["a"], a: [0.5, 0, 0, 0]}, "motion");
  sender.enqueue({b: [], a: [0, 0, 0, 0]}, "event");
  sender.enqueue({b: [], a: [0, 0, 0, 0], t: [0.25, 0.75]}, "event");
  sender.enqueue({b: [], a: [0, 0, 0, 0], t: [0.75, 0.25]}, "motion");
  sender.enqueue({b: [], a: [0, 0, 0, 0]}, "event");
  sender.enqueue({b: [], a: [0, 0, 0, 0], u: [{action: "QUICK_SAVE", command_id: "test-1"}]}, "event");
  releaseFirst();
  await sender.waitForIdle();

  assert.deepEqual(sent.map(frame => frame.s), [1, 2, 3, 4, 5]);
  assert.deepEqual(sent.map(frame => frame.b), [["a"], [], [], [], []], "button down/up frames remain visible");
  assert.deepEqual(sent[2].t, [0.25, 0.75], "touch down remains a distinct event");
  assert.equal(sent[3].t, undefined, "touch up remains a distinct release event");
  assert.equal(sent[4].u[0].command_id, "test-1", "utility remains after touch input and is delivered once");
  assert.equal(sent.some(frame => frame._an3q === "motion"), false, "a later full edge snapshot supersedes old motion");
});

test("a full bounded event queue fails closed instead of dropping transitions", async () => {
  let releaseFirst;
  let firstStarted;
  const started = new Promise(resolve => { firstStarted = resolve; });
  const firstGate = new Promise(resolve => { releaseFirst = resolve; });
  const failures = [];
  const sender = createSender({
    maxPendingEvents: 2,
    send: async () => {
      if (!firstStarted) return;
      firstStarted();
      await firstGate;
    },
    onFailure: error => failures.push(error)
  });

  sender.enqueue({b: ["a"]}, "event");
  await started;
  assert.equal(sender.enqueue({b: []}, "event"), true);
  assert.equal(sender.enqueue({b: ["b"]}, "event"), true);
  assert.equal(sender.enqueue({b: []}, "event"), false);
  assert.equal(sender.stats().pendingEvents, 0);
  assert.equal(sender.stats().failed, true);
  assert.match(failures[0].message, /preserve input transitions/);
  releaseFirst();
  await sender.waitForIdle();
});

test("a late failure from a reset session cannot fail the next session", async () => {
  const sent = [];
  let rejectOldSend;
  let oldSendStarted;
  const started = new Promise(resolve => { oldSendStarted = resolve; });
  const failures = [];
  const sender = createSender({
    send: async frame => {
      sent.push(frame);
      if (frame.s === 1 && sent.length === 1) {
        oldSendStarted();
        await new Promise((_, reject) => { rejectOldSend = reject; });
      }
    },
    onFailure: error => failures.push(error)
  });

  sender.enqueue({b: ["old-session"]}, "event");
  await started;
  sender.reset();
  sender.enqueue({b: ["new-session"]}, "event");
  rejectOldSend(new Error("old session closed"));
  await sender.waitForIdle();

  assert.equal(failures.length, 0);
  assert.equal(sender.stats().failed, false);
  assert.equal(sent[1].s, 1, "new session starts its own sequence");
  assert.deepEqual(sent[1].b, ["new-session"]);
});

test("native pad pointer handlers route movement through the bounded scheduler", async () => {
  const source = await readFile(new URL("../native-offline/web/native-app.js", import.meta.url), "utf8");
  assert.match(source, /controllerSender\.scheduleMotion\(\(\) => snapshot\(\)\)/);
  assert.match(source, /stick\.addEventListener\("pointermove", event => \{[\s\S]*?update\(event, "motion"\)/);
  assert.match(source, /controllerTouchscreen\.addEventListener\("pointermove", event => \{[\s\S]*?sendMotionSnapshot\(\)/);
  assert.match(source, /controllerTouchscreen\.addEventListener\("pointerdown", event => \{[\s\S]*?sendSnapshot\(\)/);
  assert.match(source, /controllerTouchscreen\.addEventListener\("pointerup", release\)/);
});
