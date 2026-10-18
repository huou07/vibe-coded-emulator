# VCE architecture — the short version

Status: current (2026-10-18). This page is deliberately short. It names the
boundaries, the data flow and the rule that decides where a change belongs.
Per-feature behaviour, status and evidence live in [features](features/); binding
contracts live in the reference docs listed at the end. Where this page and the
code disagree, the code wins.

## Two products, one repository

| Product | Entry point | Emulation runs in | What it stores |
| --- | --- | --- | --- |
| Web | `app.py` (Python standard library HTTP + SQLite) serving `static/` | The browser, through EmulatorJS and WASM cores | Accounts, library metadata, ROM delivery; offline ROMs and saves stay browser-local |
| Native desktop | `native-offline/` (Tauri 2 shell, Rust host) | A child process: the portable C++ player with libretro cores | App-private storage on the device; the server is not involved |
| Native Android | `native-offline/src-tauri/gen/android/` | The same portable player through the Android host | App-private storage; no server |

The server never emulates and never relays gameplay. Emulation is client-side on
every surface, and a native build does not embed the web server.

## The one shared-UI rule

`static/` is simultaneously the browser UI and the native player's UI:
`native-offline/scripts/prepare-web.mjs` copies it into the Tauri bundle at build
time. A `static/` edit is therefore a Web change *and* an unreleased native
change, so it must stay runtime-agnostic — branch on the `globalThis.AN3Native*`
adapters, never on Tauri internals outside the two adapter files.

Android is the exception: it serves a committed mirror under
`native-offline/src-tauri/gen/android/app/src/main/assets/` that no build step
regenerates. Re-copy an edited `static/` or `native-offline/web/` file there, or
`tools/check-native-mirror.py` (the `native-mirror` section of the local gate,
guard RG-156) fails.

## Where a change belongs

| You are changing | Edit here | Do not edit |
| --- | --- | --- |
| An HTTP route, page, API or SQLite schema | `app.py` | the native shell |
| Browser site or player UI | `static/` | the compiled Android mirror |
| Native UI only (Tauri window, shell chrome) | `native-offline/web/` | `app.py` |
| Tauri host, process lifecycle, permissions | `native-offline/src-tauri/src/` | `static/` |
| Emulation, video, audio, input at the core boundary | `native-offline/native-runtime/` | the Tauri shell |
| Android host or activity | `native-offline/src-tauri/gen/android/` | generated mirror files |
| Packaging, version, catalog | `native-offline/scripts/` and `tools/` | product source |
| LAN save transfer or phone controller | `static/lan-peer.js`, `static/sync*.js`, `sync_engine.py`, `native-offline/` host code | the server as a relay |

## Data flow

- Web: browser → `app.py` (routes, sessions, ROM bytes or ZIP, Range requests) →
  EmulatorJS in the page → browser-local storage for offline ROMs and saves.
- Native: shell → player child process (`--control-stdin` when launched by the
  shell) → frames through Vulkan/Metal/software → app-private save and state
  files. `an3ctl` drives the same player deterministically for evidence.
- LAN sync and phone controller: two peers on the same LAN, direct TCP, no
  server in the path. `docs/LAN_PEER_ARCHITECTURE.md` is the contract.

## Invariants that must survive any change

One line each; the binding detail is in [features](features/) and the reference
docs below.

1. Emulation stays client-side; the server stores and serves data only.
2. Offline ROMs and saves stay browser-local on the Web surface.
3. NDS uses melonDS with `EJS_startOnLoaded = true`; no DeSmuME, no start gate.
4. The NDS touch bridge, the custom virtual pad and the `geometry-mapped` touch
   default (with its `hybrid-root` rollback variant) stay intact.
5. The EmulatorJS core contract stays `EmulatorJS-core` / `core` / `?EJS_KEYS!`,
   carrying `version` and `ArrayBuffer` data.
6. Core selection stays report-first, then browser capability, then binary.
7. The core cache key `an3-arcade-cores-v1` persists independently of shell
   versions.
8. NDS serves the original ZIP where appropriate; Range requests and chunked
   upload keep working.
9. Per-core settings, 10 quick-save slots, autosave and Exit Game keep working.
10. The Android asset mirror matches its `static/` or `native-offline/web/`
    source (RG-156).

## Deliberately not here

- Google sync: removed in `d858e36`; do not reintroduce.
- `rust-gateway/`: a shadow reverse proxy, never wired into `app.py`; its cutover
  is permanently blocked.
- Cloud-hosted multiplayer rooms or a server-relayed LAN session: the server is
  not a relay, rendezvous service or blob store.
- Native builds for a platform with no pinned core artifact.

## Reference contracts (read only when your change touches them)

| Contract | Document |
| --- | --- |
| Player interaction order: z-index, input precedence | `docs/player-layering.md` |
| Shared-shell DOM IDs and page continuity | `docs/ui-page-contract.md` |
| Design tokens and the responsive/touch-target contract | `docs/design-system.md` |
| Evidence classes, browser lane and native prerequisites | `docs/UI_TESTING.md` |
| Guard ledger (append-only, cited by ID from code and tests) | `docs/REGRESSION_GUARDS.md` |
| Direct-LAN peer contract | `docs/LAN_PEER_ARCHITECTURE.md` |
| Quality bar, gates and known gaps | `docs/QUALITY.md` |
