# Native LAN handler bound — 2026-10-10

## Exact development state

- Branch: `feature/phone-controller-cross-platform`
- Product source commit: `6d1002c` (`Bound native LAN connection handlers`)
- Native app version fields: `3.2.4` in `native-offline/package.json`, `src-tauri/Cargo.toml`, `tauri.conf.json`, and `tauri.android.conf.json`.
- The frozen 3.6.8 core-only candidate remains unchanged. No package, release catalog, sidecar, public snapshot, staging deployment, or production deployment was produced.

## Product gap and change

Both native LAN listeners previously created one detached OS thread for every accepted TCP connection, while handshake reads could wait up to 30 seconds. A burst of idle or incomplete connections could therefore grow worker-thread count without a bound.

The direct-controller and sync listeners now each admit at most eight active handlers. A full listener closes a newly accepted socket before spawning a thread. An RAII permit is held through the handler lifetime and returns capacity on exit or panic; the static limit remains in place across service restarts. Normal I/O remains on handler threads, and the change adds no queue to gameplay paths.

## Evidence

- Baseline `cargo test --lib lan_host::tests`: 5 passed.
- Final `cargo test --lib`: 35 passed, 0 failed, 3 ignored. This includes the new limiter saturation/release test and existing direct-controller pairing/input tests.
- `cargo check --lib`: passed.
- `rustfmt --check src/connection_limit.rs` and `git diff --check`: passed.
- A whole-crate `cargo fmt --check` reports formatting differences across multiple unchanged Rust files; it was not applied because that would create broad unrelated edits.

## Limits and next acceptance

No packaged app was rebuilt. Windows hosted runtime, service saturation behavior in a packaged app, physical-device use, and gameplay p95/p99 under connection load remain **UNVERIFIED**. Before restoring these services in a release, validate the exact packaged runtime and measure gameplay only under the bounded connection case.
