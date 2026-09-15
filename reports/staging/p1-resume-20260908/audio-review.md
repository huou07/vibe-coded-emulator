# P1 independent review — NDS audio activation and first advancing frame

Date: 2026-09-08 (Asia/Ho_Chi_Minh)

Scope: read-only source and supplied runtime-evidence review. No production
HTTP request or other production access was made. No staging request, browser
automation, source edit, or test run was performed by this review. The existing
dirty worktree was preserved.

## Conclusion

The strongest current explanation for the frame-5 stall is browser user
activation of Web Audio, not the AN3 presentation bridge and not a demonstrated
melonDS load failure. In both the bridge-free diagnostic proxy and the normal
WebGPU bridge probe, melonDS remained at frame 5 while the Emscripten/OpenAL
audio context and its source-gain contexts were `suspended`. One trusted canvas
click changed those contexts to `running`, advanced the frame count into the
hundreds, and exposed a visible, animated Pokémon/Chunsoft intro. The same
cause-and-effect across both presentation paths is strong runtime evidence that
the core, ROM and source rendering path were already viable but waiting for
browser activation.

No application source fix is justified from this evidence alone. A trusted
user gesture is sufficient to resume this observed launch, and the current
layering deliberately allows that gesture to reach the EmulatorJS-owned source
surface. P1 acceptance should repeat a cold launch in the unchanged direct
staging runtime and record the pre-click suspended/frame-5 state and the
post-click running/advancing/visible state. This is a browser interaction
precondition, not evidence that gameplay can be declared good before the
interaction.

If product acceptance requires an explicit cue instead of an initially blank
surface, the smallest defensible follow-up is a prompt that appears only after
runtime observation confirms both suspended EmulatorJS audio and a stagnant
frame counter, and disappears after the first trusted interaction/running
context. It must not replace `EJS_startOnLoaded = true`, call a second game-start
path, or reintroduce the historical manual **Vào game** flow protected by
RG-043. That UX change is not yet necessary to establish the root cause and
would require the full player-layer/input regression matrix.

## Direct evidence

1. The supplied bridge-free run started melonDS and remained at frame 5 while
   `Module.AL.currentCtx.audioCtx.state` and the contexts reached through
   `Module.AL.currentCtx.sources[*].gain.context.state` were `suspended`.
   Clicking the canvas through the browser changed the contexts to `running`,
   advanced the frame counter to at least 316, and showed Pokémon/Chunsoft
   logos.

2. The supplied normal WebGPU-bridge run reproduced the same initial state:
   frame 5 and suspended audio contexts. One trusted canvas click changed audio
   to `running`, advanced the frame counter to at least 969, and showed the
   animated Pokémon intro. Because the trigger and recovery are the same with
   and without the presentation bridge, the bridge is not required for this
   failure or recovery.

3. The diagnostic probe reads exactly the relevant runtime fields without
   modifying them: `EJS_emulator.started`, `paused`,
   `gameManager.getFrameNum()`, the OpenAL audio context, and each source gain's
   owning context (`work/p1-resume/diagnostics.js:2-6`). Thus the observed
   state transition is not inferred from the FPS overlay or bridge submission
   counters.

4. AN3 still configures an automatic melonDS launch:
   `retroarch_core:"melonds"` is set at `static/player.js:1018-1029`,
   `EJS_startOnLoaded = true` at `1042`, and `EJS_onGameStart` at `1053-1062`.
   For NDS, the callback calls `finishLoading()` immediately. It does not wait
   for a nonblank or advancing frame and does not inspect Web Audio state.

5. In the pinned diagnostic copy, EmulatorJS `startGame()` starts/resumes the
   main loop, marks the instance started, and emits its start event before any
   audio-running proof. Its `checkStarted()` polls
   `Module.AL.currentCtx.sources[*].gain.context.state`; while that state is
   suspended it displays **Click to resume Emulator**, then closes the popup
   after the state changes. However, `startGame()` calls `checkStarted()` only
   under `this.isSafari && this.isMobile`
   (`work/p1-resume/emulator.min.js`, minified line 1, byte offsets roughly
   234316-235350). The reviewed file contains no direct `audioCtx.resume()`
   call. Therefore this pinned EmulatorJS UI does not provide the equivalent
   suspended-audio prompt on the observed desktop Chromium path.

6. The renderer bridge preserves the source surface as the input owner. Its
   presentation canvas has `pointerEvents = "none"` and z-index 2, while the
   source canvas remains beneath it at z-index 1
   (`static/renderer-worker.js:487-506`). After a successfully copied frame the
   bridge sets only the source canvas's opacity to zero
   (`static/renderer-worker.js:537-544`, `633-640`); opacity does not remove the
   element from hit testing. AN3 additionally removes
   `ejs-canvas-no-pointer` and forces source-canvas `pointer-events:auto`
   (`static/player.js:816-825`). This explains why a real click on the visible
   presentation area can still activate the hidden EmulatorJS source surface.

7. The loading overlay is removed shortly after `EJS_onGameStart` calls
   `finishLoading()` (`static/player.js:196-215`, `1053-1062`), and
   `.loading.done` is `display:none` (`static/site.css:3`). After that point it
   does not block the trusted canvas interaction.

## Inferences and limits

- **High-confidence inference:** the browser's user-activation gate on the
  Web Audio graph is the proximate cause of the observed frame-5 stall. The
  temporal coupling is exact in two renderer configurations: suspended audio
  plus frozen core before the click, then running audio plus advancing visible
  core output after it.

- **Supported but not directly located in reviewed JavaScript:** some browser,
  Emscripten/OpenAL, or generated-core behavior resumes the audio graph from the
  trusted interaction. The reviewed `emulator.min.js` does not itself contain
  a direct `audioCtx.resume()` call, and the generated melonDS core script was
  not part of this source-only inspection. The report therefore does not assign
  ownership of the actual resume call more narrowly.

- **Not supported by current evidence:** a bad ZIP suffix/extraction, wrong
  melonDS artifact, presentation shader, ImageBitmap copy, or source-canvas
  visibility defect as the cause of this launch. Each would have to explain why
  a single trusted click simultaneously changes audio state and produces
  advancing, recognizable game output without a reload or configuration
  change.

- **Acceptance limit:** the observed recovery proves startup and visible
  advancement for this ROM/browser path after one trusted click. It does not
  complete keyboard/touch release, menu precedence, resize/fullscreen, offline
  reload, service-worker cache, or physical Android acceptance. RG-033 still
  requires visible output plus input/release/resize evidence, and the broader
  P1 status remains blocked until the owner records the required current
  runtime matrix.

## Recommendation

1. Treat the direct unchanged staging tunnel run as the deciding reproduction.
   Record browser/runtime, asset/release identity, ROM identity, source and
   presentation frame signatures, frame number, `audioCtx.state`, unique gain
   context states, and visible output immediately before and after one trusted
   click.

2. If the unchanged direct staging run repeats the supplied transition, close
   the renderer/ROM-load root-cause branch for this incident and classify the
   initial stall as awaiting browser user activation. Keep the required first
   interaction explicit in the runtime evidence; do not call frame 5 or the
   pre-click blank surface gameplay-ready.

3. Make no change to `static/player.js`, the renderer bridge, source-canvas
   opacity, touch dispatch, core choice, ZIP delivery, or auto-start for root
   cause. In particular, do not restore the old manual-start implementation:
   RG-043 explicitly protects melonDS auto-start and prohibits a manual start
   button (`docs/REGRESSION_GUARDS.md:166`).

4. Consider a conditional activation cue only as a separate UX fix if users
   can remain on a blank surface with no discoverable action. Prefer runtime
   detection over browser-name detection. Preserve menu/toolbar/virtual-pad
   ownership and let a trusted interaction reach the existing EmulatorJS
   surface; do not synthesize a click because synthetic events do not provide
   browser user activation. Any such edit touches protected player layers and
   must run RG-015-RG-020, RG-026, RG-030, RG-032-RG-038 and RG-043-RG-048,
   including live browser and physical-device checks.

