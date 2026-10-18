# VCE documentation — start here

This index is a router, not a summary. Read the row that matches your task, then
that document only. **The repository and its source are authoritative** — where a
document disagrees with the code, the code wins and the document is a bug.

## Authority order

1. The source, the tests and the exact-SHA CI run.
2. [`QUALITY.md`](QUALITY.md) — the definition of good, the gates and the known
   gaps.
3. The active tracker for your feature under `docs/checkpoints/`.
4. The feature page under [`features/`](features/).
5. Dated evidence and archived documents — history, never current state.

Status words are the repository's: `GOOD` (the named live check is current for
this source), `UNVERIFIED` (implementation exists, no live check), `BROKEN` (a
live check failed). A skip is never `GOOD`; "should work" is always `UNVERIFIED`.

## Route by task

| Your task | Read | Open next only if needed |
| --- | --- | --- |
| Pick up the 2026-10-18 product track (UI/UX, Web 3DS, LAN/controller, Eden, release) | [`prompts/VCE-PRODUCT-2026-10-18.md`](prompts/VCE-PRODUCT-2026-10-18.md) | the phase's feature page |
| Understand the system before changing it | [`ARCHITECTURE.md`](ARCHITECTURE.md) | the feature page |
| Browser playback, player UI, ROM delivery, EmulatorJS proxy | [`features/web-player.md`](features/web-player.md) | `UI_TESTING.md` |
| Make 3DS playable in the browser | [`features/web-3ds.md`](features/web-3ds.md) | `features/core-selection.md` |
| Core choice, capability report, EmulatorJS contract, core cache | [`features/core-selection.md`](features/core-selection.md) | `UI_TESTING.md` |
| Save states, 10 quick slots, autosave, Exit Game data | [`features/saves.md`](features/saves.md) | `REGRESSION_GUARDS.md` |
| NDS playback, touch bridge, virtual pad, input precedence | [`features/nds-touch.md`](features/nds-touch.md) | `player-layering.md` |
| Layout chooser, per-core display options, layout persistence | [`features/screen-layout.md`](features/screen-layout.md) | `ui-page-contract.md` |
| LAN save transfer between two peers | [`features/lan-sync.md`](features/lan-sync.md) | `LAN_PEER_ARCHITECTURE.md` |
| Phone as a controller (pairing, input, reconnect) | [`features/phone-controller.md`](features/phone-controller.md) | `LAN_PEER_ARCHITECTURE.md` |
| Switch / Eden companion in the installed app | [`features/switch-eden.md`](features/switch-eden.md) | `checkpoints/eden-native-integration.md` |
| Tauri shell, library, import, player lifecycle, vendoring, `an3ctl` | [`features/native-app.md`](features/native-app.md) | `native-offline.md`, `agent-control-plane.md` |
| Android host, asset mirror, APK lane, AVD/device testing | [`features/android.md`](features/android.md) | `android-regression.md` |
| UI/UX, design tokens, navigation, clutter, accessibility | [`features/ui-shell.md`](features/ui-shell.md) | `design-system.md`, `ui-page-contract.md` |
| Build a package, bump a version, update the catalog | [`development-workflows.md`](development-workflows.md) | `native-offline.md`, skill `an3-build` |
| Release: exact-SHA CI → GitHub release → web production | [`release.md`](release.md) | `QUALITY.md`, skill `vce-release` |
| Deploy or smoke-test staging | [`staging.md`](staging.md) | `operations.md`, skill `an3-staging-deploy` |
| Publish a public source snapshot | [`QUALITY.md`](QUALITY.md) (evidence rules) | skill `public-release-security` |
| Current production topology and safety rules | [`operations.md`](operations.md) | `checkpoints/direct-https-migration.md` |
| AI-assisted game metadata upload (admin) | [`ai-game-enrichment-upload.md`](ai-game-enrichment-upload.md) | — |
| Windows packaging builder | [`WINDOWS_BUILD_VM.md`](WINDOWS_BUILD_VM.md) | — |
| What am I allowed to do? | [`AGENT-AUTHORITY.md`](AGENT-AUTHORITY.md) | [`AGENTS.md`](../AGENTS.md) |
| Licensing and third-party compliance | [`licensing/license-audit.md`](licensing/license-audit.md) | [`licensing/distribution-compliance.md`](licensing/distribution-compliance.md), [`licensing/eden-integration-feasibility.md`](licensing/eden-integration-feasibility.md) |

## Reference contracts — read only when your change touches them

| Contract | Document |
| --- | --- |
| Player interaction order (z-index, input precedence) | [`player-layering.md`](player-layering.md) |
| Shared-shell DOM IDs and page continuity | [`ui-page-contract.md`](ui-page-contract.md) |
| Design tokens and responsive/touch-target contract | [`design-system.md`](design-system.md) |
| Evidence classes, canonical browser lane, native prerequisites | [`UI_TESTING.md`](UI_TESTING.md) |
| Guard ledger — cited by ID from code and tests; append-only | [`REGRESSION_GUARDS.md`](REGRESSION_GUARDS.md) |
| Direct-LAN peer contract (what the server is *not*) | [`LAN_PEER_ARCHITECTURE.md`](LAN_PEER_ARCHITECTURE.md) |
| `an3ctl` envelope, exit codes and adapters | [`agent-control-plane.md`](agent-control-plane.md) |
| Quality bar, gates, evidence rules, known gaps | [`QUALITY.md`](QUALITY.md) |

These are long by design. Do not read them "for context"; a feature page or a
guard index tells you when they are binding.

## Agent prompts — `docs/prompts/` (never published)

| Prompt | State |
| --- | --- |
| [`VCE-PRODUCT-2026-10-18.md`](prompts/VCE-PRODUCT-2026-10-18.md) | Current owner track: UI/UX, Web 3DS, LAN Sync and Phone Controller, Eden/Switch, Android lane, release |
| [`CONTINUE-VCE.md`](prompts/CONTINUE-VCE.md) | Historical handoff and pause records (2026-10-17); durable content now lives in `AGENTS.md` and the feature pages |
| [`NEXT-VCE.md`](prompts/NEXT-VCE.md) | Historical 2026-10-17 quality-system task list; its items are closed |
| [`FINISH-VCE.md`](prompts/FINISH-VCE.md) | Historical mandate, superseded by [`AGENT-AUTHORITY.md`](AGENT-AUTHORITY.md) |

## Active trackers — `docs/checkpoints/`

Trackers hold unfinished work. Finished work moves to `docs/archive/`.

| Tracker | State |
| --- | --- |
| [`native-linux-journey.md`](checkpoints/native-linux-journey.md) | The only native tracker. Deterministic runtime `GOOD`; packaged shell, NDS/3DS and cross-platform legs `UNVERIFIED`; Exit Game `BROKEN` |
| [`ui-ux-baseline.md`](checkpoints/ui-ux-baseline.md) | The only UI/UX tracker. Bounded friction backlog, one change per journey, and the `Devices` entry pattern |
| [`direct-lan-controller.md`](checkpoints/direct-lan-controller.md) | Phone controller and LAN peer milestones; two-device acceptance not run |
| [`eden-native-integration.md`](checkpoints/eden-native-integration.md) | Eden/Switch bridge phases; packaged acceptance outside macOS not run |
| [`direct-https-migration.md`](checkpoints/direct-https-migration.md) | `READY_FOR_OWNER_ACTION`; every remaining step is root/owner action |

## Evidence

[`evidence/`](evidence/) holds retained acceptance evidence small enough for Git:
[`ci-2026-10-14.md`](evidence/ci-2026-10-14.md) (inspected CI failures and their
repairs), [`ui-library-2026-10-14.md`](evidence/ui-library-2026-10-14.md),
[`save-slots-2026-10-14.md`](evidence/save-slots-2026-10-14.md),
[`staging-availability-2026-10-14.md`](evidence/staging-availability-2026-10-14.md)
and [`linux-runtime-2026-10/README.md`](evidence/linux-runtime-2026-10/README.md).
Per-run captures are not committed; the reference checker fails a document that
points at a machine-specific report path.

## Archive

[`archive/`](archive/) is append-only history for work that is done, superseded
or permanently blocked. Do not read it as current state and do not update it in
place. Move a document there when its work closes, with a one-line reason at the
top.

| Archived | Why |
| --- | --- |
| `AN3-ARCADE-FULL-SYSTEM-HANDOFF-2026-08-13.md`, `HANDOFF-AN3-ARCADE-2026-08-11.md`, `SESSION-HANDOFF-2026-08-09.md` | Retired workstation/session snapshots; historical paths and authority are not current |
| `CODEX_PROGRESS.md` | Append-only session log of the 2026-09 release train, frozen at 1.0.x |
| `checkpoint-google-sync-removal.md` | Completed; Google sync was removed in `d858e36` |
| `checkpoint-gplv3-eden-integration.md`, `checkpoint-home-scratch-cleanup.md`, `checkpoint-mission-2026-10-13.md` | Completed checkpoints |
| `agent-interaction-capability-audit-2026-09-17.md` | Dated one-session capability audit; superseded by `AGENTS.md`, `AGENT-AUTHORITY.md` and `QUALITY.md` |
| `netplay-staging.md` | Staging-only EmulatorJS netplay relay; the server is not a multiplayer service |
| `rust-shadow-staging.md`, `rust-shadow-staging-cutover.md` | The shadow gateway stack; its cutover is permanently blocked |
| `vibe-coded-continuation-prompt.md` | Old session prompt with machine-specific paths; durable content is in `AGENTS.md` |
| `vibe-coded-platform-2026-10.md` | Dated system/status survey, superseded by `ARCHITECTURE.md` and `features/` |
| `vibe-coded-roadmap-2026-10.md` | Dated roadmap verified 2026-09-16, superseded by `features/`, `release.md` and the checkpoints |

## Maintenance rules

- Every document is listed in this index. A new document is added here in the
  same change, or the reference check fails.
- Feature pages carry status; reference documents carry contracts; trackers carry
  unfinished work. Do not put a second copy of one inside another.
- `docs/prompts/` holds agent handoff prompts and is never published (the
  publication gate forbids it), as is `AGENT-AUTHORITY.md`.
- Dated documents are evidence. Keep the date and the evidence word; do not
  rewrite history to match today.
- The reference checker (`tools/check-docs-refs.py`) fails a dangling path or an
  absolute host path. Archived documents are exempt by design.
