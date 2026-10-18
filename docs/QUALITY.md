# VCE quality bar

Authority: this is VCE's definition of "good" for the product. It does not
replace [AGENTS.md](../AGENTS.md), `.agents/skills.md`, `docs/REGRESSION_GUARDS.md`
or `docs/AGENT-AUTHORITY.md`; where they disagree, the source, the guards and the
exact-SHA hosted runs decide.

Last reviewed: 2026-10-18.

## Supported targets

| Target | Claimed support | Evidence class | Last exact-source run |
|---|---|---|---|
| Web (browser) | GBA/NDS/3DS via EmulatorJS on the surfaces it supports | VERIFIED_BEHAVIORAL (node --test, rendered-tree checks) | `tools/verify-project.sh` |
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
| Gameplay performance | sustained frame pacing / no audio underruns on named hardware | emulator-loop throughput budget in `tests/an3ctl.test.mjs` (600 frames ≤ 20s, ≈0.3 s measured on the vendored Linux runtime), claimed by the verify gate; `vce-gameplay-performance` evidence for sustained runs | verify (emulator-loop throughput only) | the throughput budget is enforced whenever the gate runs; sustained frame pacing and audio `UNVERIFIED` |
| Reliability | save states, 10 quick slots, autosave, Exit Game, recovery | Python + JS behaviour tests, guards in `REGRESSION_GUARDS.md` | verify | verified for covered paths |
| Accessibility / UX | rendered-tree names/landmarks; design tokens and responsive contract | `tests/test_rendered_ui_accessibility.py`, `inspect-ui.py`, and the browser lane's computed token values, two-tier control height and 360px no-overflow assertions | verify + browser lane | tokens/overflow enforced; the compact control tier is a recorded gap |
| Security | sanitized snapshot, pinned gitleaks, fail-closed publication gate | `tools/publication-check.sh` | acceptance (candidate) | enforced when a candidate exists |
| Compatibility | pinned core artifacts per platform | release catalog check | `verify-release-catalog.py` + hosted CI | hosted authority |
| Maintainability | docs index complete, refs resolve, every committed Android asset matches the source it copies | `check-docs-refs.py`, `tools/check-native-mirror.py` | verify | verified |
| Cost | resource use of a bounded native job | owner limits in AGENTS.md | manual | partially verified |

## Known gaps, in priority order

1. No frame-time distribution and no audio-underrun counter exist in the native
   runtime's `--status-json`, so the automated budget is emulator-loop
   throughput only. Adding them means changing the native runtime and
   re-vendoring the pinned artifact (with its recorded SHA-256), which is its
   own reviewed change; once the pinned runtime reports them, the lane that
   would carry the assertion is:

   ```bash
   AN3_PLAYER=native-offline/vendor/runtime/linux-x86_64/an3-offline-native \
     AN3_FIXTURE=work/fixtures/an3-synthetic-gba.gba \
     node --test tests/an3ctl.test.mjs
   ```

   The browser player already samples `uiFrameP50Ms`/`uiFrameP95Ms`/`uiFrameP99Ms`
   and long tasks in `static/player-runtime.js`, but no lane asserts them and no
   sustained real-device run is recorded, so sustained frame pacing and audio
   stay `UNVERIFIED`.
2. The shared shell's compact control tier (system filter chips, table row
   actions, admin range selector, small nav toggle) ships at 28–38px, below the
   42px guidance in `docs/design-system.md`. The browser lane now asserts the
   real two-tier contract (primary ≥42px, compact ≥28px) instead of a blanket
   42px, and the doc states the gap; raising the compact tier is a UI change that
   needs its own responsive review.

Closed since the 2026-10-18 review:

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
- Hosted evidence: after a successful hosted run for the current commit,
  `bash tools/record-hosted-evidence.sh <workflow>` records it in `.hub/hosted-evidence.json`. The Hub
  merges it into a verification record only when it names that exact revision;
  without it `release-check` is `BLOCKED` by "no hosted-runner evidence", which
  is true, not a defect.
