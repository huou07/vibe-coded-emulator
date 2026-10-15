# VCE documentation index

Start here. This index is the map of `docs/`; it is not a second copy of the
content. **The repository and its source are authoritative** — where a document
disagrees with the code, the code wins and the document is a bug.

## Status vocabulary

Every document that is not plainly current should carry a `Status:` line in its
first few lines:

| Status | Meaning |
| --- | --- |
| *(none)* | Current. Read it. |
| `Status: superseded by <file>` | Kept for context, but another file is the truth. |
| `Status: archival` | Historical record. Not maintained, not a task list. |

Findings in [`REGRESSION_GUARDS.md`](REGRESSION_GUARDS.md) use the repo's two
evidence words: `GOOD` (verified) and `UNVERIFIED` (not proven). Keep using them
literally.

## Architecture and invariants

| Document | What it is for |
| --- | --- |
| [`REGRESSION_GUARDS.md`](REGRESSION_GUARDS.md) | The guard ledger (RG-###) and the interaction/rendering invariants every player change must satisfy. Long, and append-only by design — the numbered guards are the live part. |
| [`LAN_PEER_ARCHITECTURE.md`](LAN_PEER_ARCHITECTURE.md) | The direct-LAN peer contract behind LAN Sync and Phone Controller. The server is **not** a relay, blob store or rendezvous service. |
| [`player-layering.md`](player-layering.md) | Binding player interaction order (z-index, input precedence). |
| [`ui-page-contract.md`](ui-page-contract.md) | Shared-shell and per-page DOM ID continuity. |
| [`design-system.md`](design-system.md) | Dark-arcade visual tokens and the responsive contract. |
| [`vibe-coded-platform.md`](vibe-coded-platform.md) | System-by-system architecture and feature status. |

## Building, verification and development

| Document | What it is for |
| --- | --- |
| [`UI_TESTING.md`](UI_TESTING.md) | Evidence classes, canonical browser lane, adapter compatibility and concrete native prerequisites. |
| [`development-workflows.md`](development-workflows.md) | The two products, their exact checks, and their platform limits. |
| [`native-offline.md`](native-offline.md) | Tauri native app: build commands, per-platform release commands, performance boundary. |
| [`WINDOWS_BUILD_VM.md`](WINDOWS_BUILD_VM.md) | The persistent `an3-win11-build` guest used by the release train for Windows packaging. |
| [`agent-control-plane.md`](agent-control-plane.md) | `an3ctl` design contract: JSON envelope, exit codes, adapters. |

## Operations

| Document | What it is for |
| --- | --- |
| [`operations.md`](operations.md) | Current topology, safety rules, baseline validation. |
| [`staging.md`](staging.md) | The staging update and rollback workflow. |
| [`android-regression.md`](android-regression.md) | Android regression and private PWA procedure. |
| [`ai-game-enrichment-upload.md`](ai-game-enrichment-upload.md) | Runbook for AI-generated game metadata proposals (admin approval). |

## Product status and active checkpoints

`docs/checkpoints/` holds durable task state for work that is **not finished**.
Finished work is archived, not left to rot in place.

| Checkpoint | State |
| --- | --- |
| [`direct-https-migration.md`](checkpoints/direct-https-migration.md) | `READY_FOR_OWNER_ACTION`. Candidate config prepared and reviewed; production routing untouched. Every remaining step is root/owner action. |
| [`eden-native-integration.md`](checkpoints/eden-native-integration.md) | Eden/Switch bridge integration, updated per completed phase. |
| [`direct-lan-controller.md`](checkpoints/direct-lan-controller.md) | AN3 Controller LAN v1 protocol and milestone record. |

## Licensing

| Document | What it is for |
| --- | --- |
| [`licensing/license-audit.md`](licensing/license-audit.md) | Per-component license table and compatibility verdicts. |
| [`licensing/distribution-compliance.md`](licensing/distribution-compliance.md) | The GPLv3 release checklist. |
| [`licensing/eden-integration-feasibility.md`](licensing/eden-integration-feasibility.md) | Eden embeddability audit and the licensing blocker that keeps the bridge in a separate process. |

Repository-wide notices live in [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)
and [`../native-offline/THIRD_PARTY_NOTICES.md`](../native-offline/THIRD_PARTY_NOTICES.md).

## Evidence

[`evidence/`](evidence/) holds retained acceptance evidence that is small enough
to keep in Git. See [`ci-2026-10-14.md`](evidence/ci-2026-10-14.md) for the
inspected CI failure causes and corresponding repairs,
[`ui-library-2026-10-14.md`](evidence/ui-library-2026-10-14.md) for the
server-rendered library semantics and compact-card action review, and
[`save-slots-2026-10-14.md`](evidence/save-slots-2026-10-14.md) for deterministic
quick-save storage behavior and the remaining real-browser/runtime acceptance,
[`staging-availability-2026-10-14.md`](evidence/staging-availability-2026-10-14.md)
for the read-only staging health and artifact-size probe plus its local builder
dependency, and [`linux-runtime-2026-10/README.md`](evidence/linux-runtime-2026-10/README.md)
for retained Linux probes and the current gameplay-performance target audit. Large
per-run captures are **not** committed: a machine-specific path under `reports/` is not
a durable reference, and nothing in `docs/` points at one.
`tools/verify-project.sh` fails if such a reference reappears.

## Archive

[`archive/`](archive/) is append-only history for work that is done, superseded
or permanently blocked. **Do not read it as current state and do not update it
in place.** Move a document there when its work closes, and leave a one-line
reason at the top of the file.

| Archived | Why |
| --- | --- |
| `AN3-ARCADE-FULL-SYSTEM-HANDOFF-2026-08-13.md`, `HANDOFF-AN3-ARCADE-2026-08-11.md`, `SESSION-HANDOFF-2026-08-09.md` | Retired workstation/session snapshots; historical paths and authority are not current. Original bodies retained in archive. |
| `CODEX_PROGRESS.md` | Append-only session log of the 2026-09 release train, frozen at 1.0.x. Superseded by the release catalog and by Git history. |
| `checkpoint-google-sync-removal.md` | Completed. Google sync was removed in `d858e36`; the decision now lives in `AGENTS.md` scope. |
| `checkpoint-gplv3-eden-integration.md` | Completed pre-GPLv3 recovery point. |
| `checkpoint-home-scratch-cleanup.md` | Completed host housekeeping record. |
| `checkpoint-mission-2026-10-13.md` | Completed mission report. |
| `netplay-staging.md` | Staging-only EmulatorJS netplay relay. The server is not a multiplayer service; see `LAN_PEER_ARCHITECTURE.md`. |
| `rust-shadow-staging.md`, `rust-shadow-staging-cutover.md` | The `rust-gateway` shadow stack. Its cutover helpers deliberately refuse to act; the gateway is not wired into `app.py`. |
| `vibe-coded-continuation-prompt.md` | An old session prompt with machine-specific absolute paths. Its durable content is now in `AGENTS.md`. |
