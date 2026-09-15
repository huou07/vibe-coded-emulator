# P1 history and regression findings — 2026-09-08

Scope: read-only history/source review. No production access, source edit, UI
automation, or launch was performed.

## Current evidence

- P1 is correctly **BLOCKED**: both staged presentation backends render black,
  while the source-only controlled proxy renders white with the EmulatorJS FPS
  overlay. This isolates the remaining failure from the new presentation
  bridge, but does not identify a melonDS/core cause. See
  `reports/handoff/RELEASE_TRAIN_P1_20260908.md:50-65` and
  `reports/handoff/RELEASE_TRAIN_STATE.md:12-20`.
- The failed audit launches do **not** revoke the separately recorded owner
  evidence: Redmi 15 5G Chrome NDS tap, drag, and gameplay response passed.
  Its extended current cases remain unverified because the device was absent.
  See `reports/handoff/RELEASE_TRAIN_STATE.md:19-20` and
  `reports/handoff/RELEASE_TRAIN_P1_20260908.md:69-71`.
- The repaired renderer transport is real but is insufficient as gameplay
  proof: effective WebGPU submitted 4,852 frames and WebGL2 1,898, both with
  black output; source-only output remained white. Treat frame counts and FPS
  as presentation/telemetry only (RG-030/RG-033). See
  `reports/handoff/RELEASE_TRAIN_P1_20260908.md:53-60` and
  `docs/REGRESSION_GUARDS.md:153-156`.

## Relevant history

1. **Previously proven cold-boot defect: ZIP bytes under an `.nds` URL.** On
   2026-08-23, a white canvas with `Playing`/60 FPS was traced to EmulatorJS
   receiving an inline ZIP through an `.nds`-suffixed player URL, so it could
   skip decompression and feed the ZIP to melonDS as a raw ROM. Preserving the
   `.zip` suffix fixed Chrome Android startup and led to visible game/menu
   acceptance. See `reports/p2-acceptance/03-physical-nds.md:23-36`.

2. **The current controlled launch has evidence against a recurrence of that
   exact URL-suffix defect.** The proxy records a `.zip` game-file GET and
   `compression/extractzip.js` request after it, at
   `reports/staging/p1-20260908/source-proxy.log:59-61`. Current integration
   coverage also requires a named `.zip` URL in the player body at
   `tests/test_integration.py:293-325`. This does not prove successful archive
   extraction or `load_game`; it only rules out the earlier filename mismatch
   as the best-supported explanation.

3. **Current boot configuration still selects the protected path.** The player
   maps NDS to `melonds`, sets `retroarch_core:"melonds"`, retains the selected
   layout/audio options, uses the fetched game URL, enables auto-start, and
   leaves EmulatorJS databases enabled in `static/player.js:991-1052`.
   Preload derives the core report/data and extractor from the same configured
   channel in `static/player.js:247-303`. The source guards assert melonDS and
   auto-start in `tests/test_regression_invariants.py:23-40`.

4. **A prior false-positive class is protected and must remain excluded.**
   Historical staging could say `Playing` when output/input were not accepted;
   the current status path intentionally labels booted/submitted video as
   gameplay-unverified in `static/player-runtime.js:387-400` and
   `static/player.js:147-161`. RG-033 requires a visible frame plus input,
   release, and resize smoke; status/source/telemetry alone is unverified
   (`docs/REGRESSION_GUARDS.md:156`).

## Evidence-backed hypotheses for P1 diagnosis

1. **Highest-value remaining branch: observe the EmulatorJS/melonDS load path
   after archive fetch/extraction.** The current trace reaches the named ZIP
   request and extractor request, while source-only output is white. Capture
   non-invasive runtime evidence for extractor completion, selected core data,
   `load_game` success/failure, and canvas dimensions/pixel output. This
   distinguishes archive/core boot failure from a valid but white core frame.
   It is a diagnostic hypothesis, not a claim that extraction is failing.

2. **Compare the current controlled launch with the historical Chrome-Android
   success at the exact boot contract boundary.** The historical issue was
   delivery semantics, and current source has additional profile-driven legacy
   selection (`static/player.js:104-105`, `static/player.js:275-276`,
   `static/player.js:1051`). Record the active profile, `EJS_forceLegacyCores`,
   selected melonDS data filename/report version, archive URL suffix, and
   post-load core state before changing configuration. No evidence supports
   switching cores, disabling auto-start, or replacing the renderer.

3. **Treat the proxy's HEAD 501 as a proxy limitation, not a staging root
   cause.** Its `SimpleHTTP` handler rejects HEAD at
   `reports/staging/p1-20260908/source-proxy.log:58-59`, then serves the ZIP by
   GET at line 60. The report itself says the proxy is local and only changes
   the presentation bridge (`RELEASE_TRAIN_P1_20260908.md:57-60`); therefore it
   is useful for renderer isolation but cannot alone establish production-like
   ROM transport behavior.

## Guard blast radius for any eventual change

- Boot/core/cache/delivery: RG-034, RG-043, RG-046; preserve named ZIP,
  melonDS auto-start, report-first core selection, IndexedDB contract, and
  versioned/service-worker assets. Required acceptance includes cold NDS ZIP
  boot to visible gameplay (`docs/REGRESSION_GUARDS.md:157,166,169`).
- Player/renderer changes: RG-015–020, RG-026, RG-030, RG-032–038, RG-043–048.
  Presentation canvas remains output-only; touch/menu/pad ownership and
  release must be re-run, with both behavioral and live checks.
- Do not use a broad rollback to historical `3eba5b1`: that commit only changed
  the default touch variant (`git show 3eba5b1`), whereas the current issue is
  reproduced with the presentation bridge bypassed. Historical renderer/touch
  changes carry independent ownership guards (RG-015/RG-017/RG-018/RG-019/
  RG-047/RG-048).
