# VCE quality bar

Authority: this is VCE's definition of "good" for the product. It does not
replace [AGENTS.md](../AGENTS.md), `.agents/skills.md`, `docs/REGRESSION_GUARDS.md`
or `docs/AGENT-AUTHORITY.md`; where they disagree, the source, the guards and the
exact-SHA hosted runs decide.

Last reviewed: 2026-10-17.

## Supported targets

| Target | Claimed support | Evidence class | Last exact-source run |
|---|---|---|---|
| Web (browser) | GBA/NDS/3DS via EmulatorJS on the surfaces it supports | VERIFIED_BEHAVIORAL (node --test, rendered-tree checks) | `tools/verify-project.sh` |
| Linux native (Tauri) | deterministic runtime evidence is `GOOD`; packaged shell is `UNVERIFIED` | VERIFIED_SOURCE / partial native | `docs/checkpoints/native-linux-journey.md` |
| Windows / macOS / Android | built and packaged on dedicated builders | VERIFIED_NATIVE only when the private release-train job passes | `native-offline/scripts/build-*.sh` on those builders; the public snapshot publishes source, not packages |
| Switch (Eden) companion | macOS-verified bridge in a separate process | VERIFIED_NATIVE (macOS only) | licensing + checkpoint docs |

Not claimed: cloud-hosted multiplayer rooms, the `rust-gateway` relay (cutover
permanently blocked), native builds for platforms without a pinned core artifact,
pixel-identical parity across platforms.

## Attributes

| Attribute | Target | How it is measured | Gate that enforces it | Current status |
|---|---|---|---|---|
| Correctness | source gate passes | `bash tools/verify-project.sh` | verify | see recorded result |
| Gameplay performance | sustained frame pacing / no audio underruns on named hardware | emulator-loop throughput budget in `tests/an3ctl.test.mjs` (600 frames ≤ 20s, measured 280ms on the vendored Linux runtime); `vce-gameplay-performance` evidence for sustained runs | verify (throughput only) | throughput budget enforced; sustained gameplay `UNVERIFIED` |
| Reliability | save states, 10 quick slots, autosave, Exit Game, recovery | Python + JS behaviour tests, guards in `REGRESSION_GUARDS.md` | verify | verified for covered paths |
| Accessibility / UX | rendered-tree names/landmarks; design tokens and responsive contract | `tests/test_rendered_ui_accessibility.py`, `inspect-ui.py`, and the browser lane's computed token values, two-tier control height and 360px no-overflow assertions | verify + browser lane | tokens/overflow enforced; the compact control tier is a recorded gap |
| Security | sanitized snapshot, pinned gitleaks, fail-closed publication gate | `tools/publication-check.sh` | acceptance (candidate) | enforced when a candidate exists |
| Compatibility | pinned core artifacts per platform | release catalog check | `verify-release-catalog.py` + hosted CI | hosted authority |
| Maintainability | docs index complete, refs resolve, no orphan scripts | `check-docs-refs.py` | verify | verified |
| Cost | resource use of a bounded native job | owner limits in AGENTS.md | manual | partially verified |

## Known gaps, in priority order

1. `tools/home-scratch-audit.sh` is referenced by nothing; two sparse-checkout
   entries and `deploy/shadow/` (mode 700) hide tracked content from `git status`.
2. No frame-time distribution and no audio-underrun counter exist in
   `--status-json`, so the automated budget is emulator-loop throughput only.
   Adding them means changing the native runtime and re-vendoring the pinned
   artifact (with its recorded SHA-256), which is its own reviewed change; until
   then sustained frame pacing and audio stay `UNVERIFIED`.
3. The shared shell's compact control tier (system filter chips, table row
   actions, admin range selector, small nav toggle) ships at 28–38px, below the
   42px guidance in `docs/design-system.md`. The browser lane now asserts the
   real two-tier contract (primary ≥42px, compact ≥28px) instead of a blanket
   42px, and the doc states the gap; raising the compact tier is a UI change that
   needs its own responsive review.

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
- A green source gate can no longer hide what it did not run.
  `tools/verify-project.sh` captures each suite's output and ends with
  `VERIFY_SKIPS=<json>` from `tools/verify-skip-manifest.py`, listing every
  skipped test with its reason (counted and named, including bare-function
  skips), and fails if the manifest cannot be produced. The fixture-dependent
  emulator lane in `tests/an3ctl.test.mjs` now fails when it is claimed
  (`AN3_PLAYER`/`AN3_PLAYER_TARGET` set) but its fixture is missing, instead of
  reporting a skip; only the unclaimed lane skips, and it says so.

## Evidence rules

- Source gate: `bash tools/verify-project.sh` — docs refs, Python and JS tests,
  native source checks, whitespace. It proves source behaviour only.
- Acceptance gate: `bash tools/acceptance.sh` — source gate plus the fail-closed
  publication gate when a candidate snapshot exists.
- Release gate: `tools/release-train.sh` on dedicated builders plus hosted CI.
- A skipped, missing or unavailable check is `UNVERIFIED`; it is never PASS.
