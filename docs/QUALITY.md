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
| Windows / macOS / Android | built and packaged on dedicated builders | VERIFIED_NATIVE only when the hosted job passes | `release-train.sh` + hosted CI |
| Switch (Eden) companion | macOS-verified bridge in a separate process | VERIFIED_NATIVE (macOS only) | licensing + checkpoint docs |

Not claimed: cloud-hosted multiplayer rooms, the `rust-gateway` relay (cutover
permanently blocked), native builds for platforms without a pinned core artifact,
pixel-identical parity across platforms.

## Attributes

| Attribute | Target | How it is measured | Gate that enforces it | Current status |
|---|---|---|---|---|
| Correctness | source gate passes | `bash tools/verify-project.sh` | verify | see recorded result |
| Gameplay performance | sustained frame pacing / no audio underruns on named hardware | `vce-gameplay-performance` evidence | manual, skill-driven | UNVERIFIED for sustained runs |
| Reliability | save states, 10 quick slots, autosave, Exit Game, recovery | Python + JS behaviour tests, guards in `REGRESSION_GUARDS.md` | verify | verified for covered paths |
| Accessibility / UX | rendered-tree names/landmarks; design tokens and responsive contract | `tests/test_rendered_ui_accessibility.py`, `inspect-ui.py` | verify | partial: `ui-page-contract.md` and `design-system.md` rules are manual |
| Security | sanitized snapshot, pinned gitleaks, fail-closed publication gate | `tools/publication-check.sh` | acceptance (candidate) | enforced when a candidate exists |
| Compatibility | pinned core artifacts per platform | release catalog check | `verify-release-catalog.py` + hosted CI | hosted authority |
| Maintainability | docs index complete, refs resolve, no orphan scripts | `check-docs-refs.py` | verify | verified |
| Cost | resource use of a bounded native job | owner limits in AGENTS.md | manual | partially verified |

## Known gaps, in priority order

1. The public workflow `tools/publication/.github/workflows/native-build.yml`
   calls `tools/release-train.sh`, which `build-public-snapshot.sh` does not copy
   into the candidate: the published CI cannot run as shipped.
2. The sanitizer patterns omit absolute home-directory paths and `~/`, and the forbidden-path list
   misses `docs/prompts/`, `docs/AGENT-AUTHORITY.md`,
   `AGENT_INTERACTION_CAPABILITY_AUDIT.md` and `.codegraph`.
3. `tools/home-scratch-audit.sh` is referenced by nothing; two sparse-checkout
   entries and `deploy/shadow/` (mode 700) hide tracked content from `git status`.
4. Fixture-dependent tests skip instead of failing, so an emulator lane can
   report success while measuring nothing.
5. No automated frame-time or audio budget exists; gameplay performance is
   skill-driven evidence only.

## Evidence rules

- Source gate: `bash tools/verify-project.sh` — docs refs, Python and JS tests,
  native source checks, whitespace. It proves source behaviour only.
- Acceptance gate: `bash tools/acceptance.sh` — source gate plus the fail-closed
  publication gate when a candidate snapshot exists.
- Release gate: `tools/release-train.sh` on dedicated builders plus hosted CI.
- A skipped, missing or unavailable check is `UNVERIFIED`; it is never PASS.
