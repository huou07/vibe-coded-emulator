# VCE quality bar

Authority: this is VCE's definition of "good" for the product. It does not
replace [AGENTS.md](../AGENTS.md), `.agents/skills.md`, `docs/REGRESSION_GUARDS.md`
or `docs/AGENT-AUTHORITY.md`; where they disagree, the source, the guards and the
exact-SHA hosted runs decide.

Last reviewed: 2026-10-18.

## Supported targets

| Target | Claimed support | Evidence class | Last exact-source run |
|---|---|---|---|
| Web (browser) | GBA/NDS/3DS via EmulatorJS on the surfaces it supports; all three verified playing on the **public production surface over HTTPS** (`https://an3tocom.space/offline`) with lawful homebrew fixtures | VERIFIED_BEHAVIORAL (node --test, rendered-tree checks) plus a live public-surface run | `tools/verify-project.sh`; `work/phaseG/live.mjs` against the public URL, recorded in `docs/checkpoints/web-play-release-2026-10-19.md` |
| Linux native (Tauri) | deterministic runtime evidence is `GOOD`; packaged shell is `UNVERIFIED` | VERIFIED_SOURCE / partial native | `docs/checkpoints/native-linux-journey.md` |
| Windows / macOS / Android | built and packaged on dedicated builders; the public packages are unsigned staging | VERIFIED_NATIVE only when the private release-train job passes | `native-offline/scripts/build-*.sh` on those builders; the public snapshot publishes source, and the public `v3.6.8` release serves unsigned staging packages (`.deb`, `.dmg`, `.exe`, `.apk`/`.aab`, `.flatpak`) with `.sha256` sidecars |
| Switch (Eden) companion | macOS-verified bridge in a separate process | VERIFIED_NATIVE (macOS only) | licensing + checkpoint docs |

Not claimed: cloud-hosted multiplayer rooms, the `rust-gateway` relay (cutover
permanently blocked), native builds for platforms without a pinned core artifact,
pixel-identical parity across platforms.

## Attributes

| Attribute | Target | How it is measured | Gate that enforces it | Current status |
|---|---|---|---|---|
| Correctness | source gate passes | `bash tools/verify-project.sh` | verify | see recorded result |
| Gameplay performance | sustained frame pacing / no audio underruns on named hardware | measured emulator-loop frame-time distribution in `tests/an3ctl.test.mjs` (`frameMs` p50/p95/p99/max over 600 frames, plus measured fps and the whole-run ≤ 20s throughput bound), read from the vendored Linux runtime's `--status-json`; `vce-gameplay-performance` evidence for sustained runs | verify (emulator-loop timing only) | the frame-time distribution and the throughput bound are enforced whenever the gate runs (measured p95 ≈ 0.29 ms, max ≈ 0.43 ms); sustained display frame pacing and audio underruns `UNVERIFIED` |
| Reliability | save states, 10 quick slots, autosave, Exit Game, recovery | Python + JS behaviour tests, guards in `REGRESSION_GUARDS.md`; LAN Sync and Phone Controller also verified between two independent peers on one host (data and control planes), which does not replace two-device acceptance | verify | verified for covered paths; two physical devices `UNVERIFIED` |
| Accessibility / UX | rendered-tree names/landmarks; design tokens and responsive contract | `tests/test_rendered_ui_accessibility.py`, `inspect-ui.py`, and the browser lane's computed token values, control tiers, published `compactBelow42` set and 360px no-overflow assertion | verify + browser lane | tokens/overflow enforced; every control measured at 360px is ≥42px, and any compact control still below 42px is published in the evidence artifact rather than described |
| Security | sanitized snapshot, pinned gitleaks, fail-closed publication gate | `tools/publication-check.sh` | acceptance (candidate) | enforced when a candidate exists |
| Compatibility | pinned core artifacts per platform | release catalog check | `verify-release-catalog.py` + hosted CI | hosted authority |
| Maintainability | docs index complete, refs resolve, every committed Android asset matches the source it copies | `check-docs-refs.py`, `tools/check-native-mirror.py` | verify | verified |
| Cost | resource use of a bounded native job | owner limits in AGENTS.md | manual | partially verified |

## Known gaps, in priority order

1. The enforced budget covers the emulator loop, not the display pipeline and not
   audio. `--status-json` now reports a measured frame-time distribution
   (`frameMs` p50/p95/p99/max over 600 frames) and a measured `measuredFps`,
   distinguishable from the pre-existing `fps` field, which is the rate the core
   *advertises*. The lane asserts the distribution and fails at p95 > 10 ms or a
   single frame > 250 ms (`AN3_EMULATOR_FRAME_P95_MS`,
   `AN3_EMULATOR_FRAME_MAX_MS`), which the whole-run throughput bound cannot see.
   What remains open is presentation and audio: the lane runs `--headless`, which
   uses `NullAudioBackend` and a capture video backend and now says so
   (`audioMeasured:false`). The metrics contract already reserves
   `audio_underruns` (`native-runtime/core/renderer_contract.h`), but
   `LinuxSdlAudioBackend` does not populate it, and closing that needs a host
   with a real display and audio device, which the gate host does not have. The
   same lane carries the assertion once such a host reports the SDL renderer's
   metrics:

   ```bash
   AN3_PLAYER=native-offline/vendor/runtime/linux-x86_64/an3-offline-native \
     AN3_FIXTURE=work/fixtures/an3-synthetic-gba.gba \
     node --test tests/an3ctl.test.mjs
   ```

   The browser player already samples `uiFrameP50Ms`/`uiFrameP95Ms`/`uiFrameP99Ms`
   and long tasks in `static/player-runtime.js`, but no lane asserts them and no
   sustained real-device run is recorded, so sustained display frame pacing and
   audio underruns stay `UNVERIFIED`.
2. The tier contract is measured on the 360px library view only. There every
   control now clears 42px (compact minimum 42px, down from a measured 31px on the
   selected filter chip), the lane publishes `compactBelow42` in
   `work/ui-runtime/evidence.json`, and that set is empty. The deliberately dense
   desktop controls — table row actions, the admin range selector, the small nav
   toggle — keep their 28px floor and live on surfaces this lane never loads, so
   their real heights are not machine-checked. A second pass over the admin and
   library update-notice surfaces is what would close that, and it needs the
   browser lane, not a source assertion.

Closed since the 2026-10-18 review:

- The compact control tier sat below the 42px touch guidance, and the claim was
  prose rather than a measurement. The browser lane now publishes every compact
  control below 42px, with its height, tag, id and class, as `compactBelow42` in
  `work/ui-runtime/evidence.json`, and refuses to pass when either tier measures
  nothing (the bounds could otherwise hold vacuously over an empty set). Measured
  at 360px on the library view: primary minimum 44px; compact minimum 31px with
  three system filter chips under 42px (37px, 37px and a 31px selected chip). The
  chips are the compact controls a thumb actually taps at that width, so they were
  raised to a 42px minimum and the desktop-density tier kept its 28px floor.
  Re-measured: compact minimum 42px, `compactBelow42` empty, primary minimum
  44px, `scrollWidth` 360 against a 360px viewport. Repeating the same edit
  without re-copying the Android mirror makes `tools/check-native-mirror.py` fail,
  which is RG-156 doing its job.

- The automated gameplay budget could not see a single stalled frame. The
  vendored Linux runtime's `--status-json` reported only `fps`, which is the rate
  the *core advertises* (`av.timing.fps`), never a measurement, so the lane's one
  throughput number was the strongest available claim. It now reports a measured
  wall-clock frame-time distribution around `run_one`
  (`frameMs` samples/mean/p50/p95/p99/max) and a measured `measuredFps`, and
  `tests/an3ctl.test.mjs` asserts the distribution, its ordering and its tail
  (p95 ≤ 10 ms, max ≤ 250 ms, both overridable). Measured on the vendored runtime
  after re-vendoring: mean 0.284 ms, p50 0.283 ms, p95 0.292 ms, p99 0.308 ms,
  max 0.413 ms, measured 3519 fps over 600 frames, with the whole-run bound at
  234 ms against its 20 s budget. The parked half of gap 1 — display presentation
  and audio underruns — stays open and is now stated by the payload itself
  (`audioMeasured:false`), because the lane runs `--headless` with
  `NullAudioBackend`.

- Every local native build dirtied the working tree, so no evidence could bind to
  a revision: `source-integrity` was `NOT_VERIFIED` and both gates `STALE` at
  `d94a8b7`. Two causes, both fixed. The tracked `gen/schemas/**` was per-target
  build output — a desktop `cargo build --release --lib` adds
  `linux-schema.json`, which the tracked six-file set never contained — and it
  was found holding `android-schema.json` byte-identical to the desktop schema
  beside a 0-byte `mobile-schema.json`; it is now untracked and ignored, while
  the mobile ACL invariant it was meant to protect is already asserted
  statically against `capabilities/` and `build.rs` in
  `tests/test_offline_consolidation.py` (RG-157). The Android web-asset mirror
  under `gen/android/app/src/main/assets/` had drifted from `static/`: the
  committed `site.css` and `theme-violet.css` were a month behind the Web and
  desktop sources, and `tools/build-public-snapshot.sh` keeps that `site.css`
  verbatim, so the stale sheet was publishable. It is re-copied and now enforced
  by `tools/check-native-mirror.py`, the `native-mirror` check in the source gate
  (RG-156). Measured afterwards: a desktop build and `npm run prepare-web` leave
  the tree clean, and `hub.py assess vce` reports `source_integrity VERIFIED`
  with `verify` and `acceptance` `CURRENT`.

Closed since the 2026-10-17 review:

- The published `native-build.yml` was removed. Its jobs ran
  `bash tools/release-train.sh` five times while the snapshot copied neither that
  script nor its builders, and its `paths:` filters named a `tools/testrom/**`
  directory that does not exist, so no published native job could ever pass.
  Cross-platform packaging stays with the private release train on its dedicated
  builders, and `tools/publication-check.sh` now refuses a candidate whose
  workflows call a script the candidate does not contain
  (`tools/publication/check-workflow-scripts.py`). The portable published
  workflow's whitespace step no longer assumes a parent commit, so it runs in the
  single-commit public repository.
- The sanitizer hole is closed. `/home/<user>/` and `~/` are now blocking
  patterns in both `tools/publication-check.sh` and the snapshot builder's
  post-sanitisation scan; `check-docs-refs.py` scans source and test files for
  absolute host paths as well as prose; `docs/prompts/`,
  `docs/AGENT-AUTHORITY.md`, `AGENT_INTERACTION_CAPABILITY_AUDIT.md` and
  `.codegraph` are forbidden paths in a candidate; and the operator README under
  `tools/android/` (owner key filenames, staging host, legacy checkout path) is
  no longer copied into the snapshot.
- The missing gates exist for what the product can measure. The browser lane
  (`tests/web-runtime.test.mjs`) asserts the computed design tokens, the two-tier
  control-height contract and 360px no-overflow in a real browser, and
  `docs/design-system.md` now documents the shipped violet token values and the
  compact tier instead of a stale lime table and a blanket 42px claim. The
  emulator lane carries a throughput budget (600 frames ≤ 20s) on the vendored
  Linux runtime and prints `AN3_EMULATOR_BUDGET ... result=PASS`.
- The orphaned one-shot scratch-audit script is removed, closing this file's
  first known gap. Two sparse-checkout entries and `deploy/shadow/` (mode 700)
  still hide tracked content from `git status`; `docs/development-workflows.md`
  records the reduced scope of a sparse checkout.
- A green source gate can no longer hide what it did not run.
  `tools/verify-project.sh` captures each suite's output and ends with
  `VERIFY_SKIPS=<json>` from `tools/verify-skip-manifest.py`, listing every
  skipped test with its reason (counted and named, including bare-function
  skips), and fails if the manifest cannot be produced. The fixture-dependent
  emulator lane in `tests/an3ctl.test.mjs` now fails when it is claimed
  (`AN3_PLAYER`/`AN3_PLAYER_TARGET` set) but its fixture is missing, instead of
  reporting a skip; `tools/verify-project.sh` and the hosted `project-verify` job
  claim it with the tracked vendored player, so the unclaimed skip is no longer
  the default in the registered gate.

## Evidence rules

- Source gate: `bash tools/verify-project.sh` — docs refs, Python and JS tests,
  native source checks, whitespace. It proves source behaviour only.
- Acceptance gate: `bash tools/acceptance.sh` — source gate plus the fail-closed
  publication gate when a candidate snapshot exists.
- Release gate: `tools/release-train.sh` on dedicated builders plus hosted CI.
- Quality contract: `.aeh/quality.json` maps those gate names to the Hub's
  `verify`/`acceptance`/`release` commands, and `tools/verify-project.sh` writes
  the declared `.hub/gate-report.json` so every run publishes what it skipped and
  did not run (git-ignored runtime state, never source, never published).
- Required check: the `release-gate` job in `.github/workflows/verify.yml`
  aggregates every lane and fails unless all of them succeeded, so a skipped or
  cancelled lane cannot read as green. `main` requires that job.
- A skipped, missing or unavailable check is `UNVERIFIED`; it is never PASS.
- Per-feature status and open work live in [`features/`](features/); a change that
  alters a status updates its feature page in the same commit. This file keeps the
  cross-cutting bar and the known gaps.
- Hosted evidence: after a successful hosted run for the current commit,
  `bash tools/record-hosted-evidence.sh <workflow>` records it in `.hub/hosted-evidence.json`. The Hub
  merges it into a verification record only when it names that exact revision;
  without it `release-check` is `BLOCKED` by "no hosted-runner evidence", which
  is true, not a defect.
