# Native LAN sync UI-thread fix — 2026-10-10

## Exact source state

- Branch: `feature/phone-controller-cross-platform`
- Source commit: `67dcf10` (`Keep native LAN waits off the UI thread`)
- App version: `3.2.5` in `native-offline/package.json`, Cargo.toml/Cargo.lock, and both desktop and Android Tauri configs.
- The frozen public 3.6.8 core-only candidate was not changed. No package, artifact, catalog, sidecar, public snapshot, push, release, or deployment was produced.

## Product gap and fix

Tauri executes synchronous commands on its main thread. Native peer discovery blocks in multicast receive for up to two seconds, and sync RPCs do blocking socket reads/writes while transferring save/state data. Both were exposed as synchronous Tauri commands, so a slow LAN peer could make the app UI unresponsive.

`native_sync_discover` and `native_sync_request` are now async Tauri commands that run their existing socket work through `tauri::async_runtime::spawn_blocking`. The protocol, transfer validation, and shared-stream serialization are unchanged. Regression guard RG-143 records the requirement.

## Evidence

- Before change: `node --test tests/native_sync.test.mjs tests/sync_transfer.test.mjs` passed 22/22.
- After change: the same sync suite passed 22/22; the new `tests.test_native_sync_command` checks that both commands use the blocking worker and passed 2/2.
- `cargo check --lib` succeeded. It emitted 28 existing dead-code warnings in controller/LAN/UI-control code.
- `git diff --check` passed.
- All five app-version fields agree on `3.2.5`.

## Acceptance limit

Packaged runtime responsiveness during slow discovery and large save/state transfer remains **UNVERIFIED**. This source-level fix keeps blocking I/O off the UI and async executor workers, but it does not by itself prove the packaged interaction or gameplay latency. Validate through hosted CI/runtime acceptance when this development line is next packaged. Do not apply the fix to or rebuild the frozen 3.6.8 candidate.
