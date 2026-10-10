# Native LAN sync chunk transfer — 2026-10-10

## Exact private source state

- Branch: `feature/phone-controller-cross-platform`
- Exact source SHA: `9994fff57e9318e3c80d6c87606a7ea055e6a3be`
- Implementation commit: `9059b9836c68076bc0213a8773786d00f272e893`
- Range-validation follow-up: `9994fff57e9318e3c80d6c87606a7ea055e6a3be`; malformed or mistyped range values are rejected rather than falling back to whole-file reads.
- Package version fields remain at `3.2.5`; no artifact was built and no versioned bytes were republished.
- Frozen public 3.6.8 candidate remains at `ffd1ebc79750a026e7bbbcc6a7762c0ead93ab4c`. It remains core-only and excludes LAN Sync. No public snapshot, push, release, CI dispatch, or deployment was made.

## Product gap and fix

Native sync allowed members up to 16 MiB and save/state sets up to 64 MiB, but each authenticated JSON frame was capped at 8 MiB. Base64 made the single-frame path fail before reaching the accepted member or set limits.

The native peer now reads download ranges and accepts ordered upload chunks of at most 768 KiB. Chunked uploads retain the existing member/set size, SHA-256, manifest, and atomic publish checks. A process-wide permit allows one staged large publish at a time, bounding staged transfer memory to the existing 64 MiB set cap. The web client negotiates chunk support, preserves the legacy single-frame path through 4 MiB, and assembles larger downloads before passing them to the existing full-hash verification and persistence flow. The Android packaged client asset is synchronized.

Regression guard RG-144 records the boundary and verification requirements. The roadmap now marks the private-source wire-size gap closed and records the runtime evidence still needed.

## Evidence

- Before the chunk implementation, `node --test tests/native_sync.test.mjs tests/sync_transfer.test.mjs` passed 22/22.
- Current same suite passes 24/24, including large upload/download chunking and Android asset parity.
- `cargo test --lib` passes: 37 passed, 3 ignored, including ordered upload chunks, publish-slot release, and malformed range rejection.
- `cargo check --lib` succeeds, with existing dead-code warnings in controller, LAN, and UI-control modules.
- `git diff --check` passed for the committed change.
- `cargo fmt --check` was attempted and reports extensive pre-existing formatting differences across unrelated crate files; those files were not reformatted.

## Release and runtime status

This is private product work outside the frozen 3.6.8 candidate, so it does not alter the current release scope or require a new candidate snapshot. The 3.6.8 operator acceptance package remains the source of truth for current release readiness.

Packaged two-peer transfer above 8 MiB, interrupted-transfer recovery in the packaged app, and gameplay p95/p99 impact remain **UNVERIFIED**. Windows execution is limited to hosted CI per operator direction; no local Windows machine was used. This commit was not pushed, so no hosted workflow was dispatched. Do not claim runtime acceptance from these source and unit checks.

The remaining action for this private feature is to include it in a future explicitly scoped package/CI acceptance pass after release convergence permits that work. Preserve the frozen candidate and current dirty reports/screenshots/`.DS_Store` files.
