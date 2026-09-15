# P1 resumed runtime evidence (2026-09-08, continued 2026-09-09)

No application source changes or deployment in this resumed work. Staging asset 11290264c01d; fresh four JS hash parity PASS (staging-parity.json). Production untouched.

## Proven startup diagnosis
The local source-only staging proxy exposes safe diagnostics in DOM: started=true, paused=false, core=melonds, ROM extracted .nds size134217728, core frame5, OpenAL audioCtx and source gain contexts suspended. A trusted CUA canvas click changes audio to running, frame15 then316, and visibly shows Pokémon Company/Chunsoft logos. The normal bridge probe repeats frame5/suspended -> frame969/running and animated Pokémon intro with effective WebGPU. Independent Sol Medium review agrees with browser audio activation gate (audio-review.md). No speculative ROM/core/input/renderer change is justified from that stall. Debug proxy changes EJS debug verbosity and appends diagnostics; source-only additionally removes presentation, no-hooks additionally omits frame telemetry/speed initialization. Proxy lacks HEAD, so it is diagnostic evidence, not final artifact acceptance.

## Direct unchanged staging
CUA in-app Chromium via authorized loopback SSH18092 to staging8092. ROM Pokémon Mystery Dungeon: Explorers of Sky, melonDS. WebGPU auto effective=webgpu, offscreen=true, animated intro/title visible after trusted click; Return reaches New Game/Other menu. Explicit renderer=webgl2 effective=webgl2, offscreen=true, animated intro/title and same game menu after Return. Core screen images visibly change; no performance claim from overlay or presentation counters. Status stays Video active · gameplay unverified, never Playing.

## Remaining acceptance
Further New Game selection using short z/x/a/Down presses, virtual A click/short drag and direct menu clicks did not conclusively advance past menu. Control Settings dialog opens/closes and reports A:z, B:x, X:a, Y:s, Start:enter. Do not label full input/gameplay PASS yet. Investigate input duration/mapping/automation before blaming current source. Fresh session tabs closed across continuation; reopen staging only as needed.

Console includes failed optional EmulatorJS update check, wake-lock denial, and one Chromium UnknownError (message asks report to Chromium), without stopping animated intro/menu. Not explained as renderer failures. Redmi device discovery=no; retain owner-confirmed earlier tap/drag/gameplay separately.

Baseline93 Python PASS, direct Node8 PASS, native npm/syntax/diff checks PASS. No source edits since these checks. P1 remains IN_PROGRESS until interactive acceptance verdict; no P2 work.

## 2026-09-09 continuation
Input diagnostic on fresh loopback18100: trusted z down/up reaches simulateInput(0,8,1/0), duration0.585ms; direct-keyboard setting disabled, popup=false, settings menu none. Thus earlier short CUA keys are not a reliable game-loop sample. A 40px drag within virtual A delivers press/release133.8ms. At New Game menu this reaches Welcome! with continuation arrow. A prior short 4px drag did not establish a durable input duration.
Controlled adapter-null fixture on fresh18100 requests webgpu, effective webgl2, offscreen=true, core advancing frame8330 and visible Welcome dialogue after virtual A. The fixture uses exactly one response-only replacement requestAdapter->Promise.resolve(null), plus verbose EJS and safe input/status observations. Initial18099 reused cached assets and did NOT inject failure; excluded from forced-fallback acceptance. No production/source changes.

## Final direct staging acceptance
2026-09-09: direct unmodified secure staging, requested webgpu/effective webgpu/offscreen=true, reached Welcome! and next dialogue (portal leading to the Pokémon world) via held virtual A. Settings opened and closed, dialogue retained. Source opacity0/pointer-events auto; presentation opacity1/pointer-events none. Fullscreen resize retains visible output and usable controls; temporary browser viewport override reset. No state save/import/export invoked. No audible-quality or latency claim. P1 renderer interactive acceptance PASS for this desktop runtime; extended mobile/layout/save/audio matrix remains separately UNVERIFIED. Existing native mounted DMG Escape/Save evidence remains valid on unchanged source/artifact. No new application code or deployment required.

P1 COMPLETE. Next P2 — NDS performance diagnosis, Sol Medium. No P2 work executed. Small helpers completed history, independent audio root-cause review and input mapping audit; earlier helper usage failures were handled locally. No usage reset consumed.
