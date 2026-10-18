# VCE Development Guide

Vibe Coded Emulator (VCE) is an **offline-first emulator front end**. The user
supplies their own legally obtained ROM files; the project bundles no ROMs,
firmware, keys or saves. Emulation runs on third-party cores (mGBA, melonDS DS,
Azahar natively; EmulatorJS in the browser). The Switch companion launches Eden
as a separate process on a host that has a companion build.

## Product scope — the real one

| In scope, worked on | Not in scope |
| --- | --- |
| GBA / NDS / 3DS emulation on Android, Windows, Linux, macOS | Google sync — removed in `d858e36`, do not reintroduce |
| Switch (Eden) companion in the installed app, per host that has a companion build | Eden or any Switch core in the browser |
| Browser emulation: GBA/NDS play today; making 3DS playable is the open Web gap | Cloud-hosted multiplayer rooms or a server-relayed LAN session |
| UI/UX completion, and the entry points of Switch, LAN Sync and Phone Controller | Unspecified "improve everything" refactors |
| LAN Sync (save transfer) and Phone Controller (direct LAN peer) | Native builds for platforms with no pinned core artifact |
| Gameplay performance, frame pacing, reliability | |
| Save states, autosave, per-core settings, 10 quick slots | |

**Never claim a capability in docs, README or UI that the code and the recorded
evidence do not support.** Findings use this repository's two words literally:
`GOOD` (the named live check is current for this source) and `UNVERIFIED` (the
implementation exists, no live check establishes it). A feature page may add
`BROKEN` for a live check that failed. A skip is never `GOOD`; "should work" is
always `UNVERIFIED`.

## Read the right document, not all of them

| You need | Read |
| --- | --- |
| Orientation before changing anything | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| The feature you are changing | [`docs/features/`](docs/features/README.md) — the router picks one page |
| Task → document lookup | [`docs/README.md`](docs/README.md) |
| Quality bar, gates, known gaps | [`docs/QUALITY.md`](docs/QUALITY.md) |
| What you are allowed to do | [`docs/AGENT-AUTHORITY.md`](docs/AGENT-AUTHORITY.md) |
| Unfinished work for a feature | the page's tracker under `docs/checkpoints/` |
| Release steps | [`docs/release.md`](docs/release.md) |

Reference contracts (`docs/REGRESSION_GUARDS.md`, `docs/UI_TESTING.md`,
`docs/player-layering.md`, `docs/ui-page-contract.md`, `docs/design-system.md`)
are long and binding. Read one only when a feature page, a guard index or the
change itself makes it binding. Do not read them "for context".

Documentation rules: every document is listed in `docs/README.md`; a feature page
carries status, a reference document carries a contract, a tracker carries
unfinished work; do not duplicate one inside another. `tools/check-docs-refs.py`
fails a dangling path or an absolute host path, so a moved document is a change
that updates its references.

## Layout and the app/Web boundary

- `app.py` — the Web product: HTTP routing, SQLite, sessions, ROM delivery,
  EmulatorJS proxy, pages. Python **standard library only**, no dependencies.
- `static/` — browser player and site UI. **Also the native player's UI**:
  `native-offline/scripts/prepare-web.mjs` copies it into the Tauri bundle, so a
  `static/` edit is simultaneously a Web change *and* an unreleased native change.
  Keep it runtime-agnostic: branch on the `globalThis.AN3Native*` adapters, never
  on `__TAURI__` directly outside `offline.js` and `player.js`. **Android serves
  the committed mirror** `native-offline/src-tauri/gen/android/app/src/main/assets/`,
  which no build step regenerates; re-copy an edited `static/` or
  `native-offline/web/` file there too. `tools/check-native-mirror.py` (the
  `native-mirror` check in `tools/verify-project.sh`, guard RG-156) fails until
  the mirror matches.
- `native-offline/` — Tauri 2 shell (`src-tauri/`, Rust), the portable libretro
  player (`native-runtime/`, C++), the native UI (`web/`), the Android host and
  the vendored runtime.
- `native/` — the Eden bridge sources used by the Switch companion, kept separate
  from the player and from the Tauri shell.
- `rust-gateway/` — a shadow reverse proxy. **Not wired into `app.py`; its cutover
  is permanently blocked** (`docs/archive/rust-shadow-staging-cutover.md`). Do
  not build on it.
- `tests/` — Python `unittest` (Web/server) and Node `--test` (browser and native
  JS models).
- `tools/`, `native-offline/scripts/`, `deploy/` — verification, packaging,
  release and staging operations. Read a script before running it.

## Build and verify on this host

Owner instruction 2026-10-18 permits, on this Debian host, bounded Linux native,
Web and Android work. One resource-intensive job at a time, one compilation
worker, memory and disk checked first, bounded timeout, full process-group
cleanup, and the shared native lock where one applies.

- **Linux native:** build locally (`native-offline/scripts/build-linux-staging.sh deb`),
  then run the packaged journey. Source-tree runtime evidence is not packaged
  acceptance.
- **Web:** run `app.py` on loopback and the canonical browser lane; follow
  `docs/UI_TESTING.md` for evidence classes.
- **Android:** use a **VCE-dedicated AVD** (for example `vce-api36`, built from the
  installed `android-36` system image). Never attach to, reconfigure or stop the
  other project's `an3-api36` AVD. An emulator run is device-class evidence, not
  packaging acceptance.
- **macOS / Windows:** build and test through GitHub-hosted CI and their dedicated
  builders. Never claim their acceptance from this host.

```bash
bash tools/verify-project.sh        # the whole local gate
python3 -m unittest discover -s tests
node --test --test-concurrency=1 tests/*.test.mjs tests/*.test.js
npm --prefix native-offline run check
```

**GitHub Actions is the authoritative remote gate.** Read
[UI/runtime testing](docs/UI_TESTING.md) for the canonical browser lane, static
inspector limits, evidence classes and Tauri prerequisites. Browser evidence
never establishes packaged/native or gameplay acceptance. Missing tools and skips
remain `UNVERIFIED`. Never weaken an assertion to make a gate green.

## Invariants

Verified behaviour that must survive every change:

- Emulation stays client-side; the server stores and serves data only.
- Offline ROM and save data stays browser-local.
- NDS uses melonDS with `EJS_startOnLoaded = true`. No DeSmuME, no manual-start
  workaround, no start-button gate.
- The NDS touch bridge, the custom virtual pad and the `geometry-mapped` touch
  default (with its `hybrid-root` rollback variant) stay intact.
- The EmulatorJS core contract stays `EmulatorJS-core` / `core` / `?EJS_KEYS!`,
  carrying `version` and `ArrayBuffer` data.
- Core selection stays report-first, then browser capability and binary.
- The core cache key `an3-arcade-cores-v1` persists independently of PWA shell
  versions.
- NDS serves the original ZIP where appropriate; Range requests and chunked
  upload keep working.
- Per-core settings, 10 quick-save slots, autosave and Exit Game keep working.
- The Android asset mirror matches its source (RG-156).

Before and after touching the player canvas, input, layering, save, audio or a
renderer, run the matching guards in `docs/REGRESSION_GUARDS.md` and honour the
interaction contracts in `docs/player-layering.md`.

## Authority, release and safety

- The owner instruction dated 2026-10-18 authorizes: completing UI/UX, adding the
  Eden/Switch companion to the installed app (not the Web), finishing LAN Sync and
  Phone Controller, making 3DS playable on the Web, building and testing Linux,
  Web and Android on this host, and releasing versions that pass the gates to
  GitHub and the web production path.
- Resolve authorization from the current task; historical mandates are evidence,
  not permanent publication authority. The instruction grants no credentials,
  privilege escalation, history rewrite or branch-protection bypass.
- **Never release or deploy without the exact-SHA CI gate and the recorded
  acceptance** for the surfaces claimed — see [`docs/release.md`](docs/release.md).
- Never rewrite published history and never force-push.
- Keep third-party notices and license texts intact; see `docs/licensing/`.
- Use only lawful fixtures.
- `tools/publication-check.sh` fails closed. If a scanner cannot run, publication
  is blocked, not waved through.
- `tools/publish-github.sh` refuses a candidate that is not the core-only public
  product (RG-155). Export the snapshot from a `core-only/*` branch, never from
  the full-featured development branch, and run
  `tools/publish-github.sh --check-candidate --snapshot <dir>` first.

## Instruction artifacts

Keep project guidance and skill resources in English; use the owner's preferred
language in conversation. Current source, CI and runtime evidence establish
capabilities; dated documents and skips do not. Load only the relevant procedure,
and report missing tools or unavailable source identity explicitly.

## Skills

Project skills live in `.agents/skills/` and are routed by
[`.agents/skills.md`](.agents/skills.md). Load one only when the task matches its
description; a skill description never authorizes a privileged action.

| Skill | Use for |
| --- | --- |
| `an3-build` | Packaging, versions, release catalog, per-platform artifacts |
| `an3-control-plane` | `an3ctl` targets, deterministic captures, save/input assertions |
| `an3-player-regression` | Player surface edits and their guards |
| `an3-staging-deploy` | Staging deploy, smoke and rollback |
| `public-release-security` | Public publication candidate and fail-closed gate |
| `vce-gameplay-performance` | Sustained gameplay frame pacing and audio evidence |
| `vce-product-journeys` | Completing one user-visible flow end to end |
| `vce-ui-ux` | UI/UX work across Web, native and Android surfaces |
| `vce-web-3ds` | Making 3DS playable in the browser |
| `vce-eden-native` | Eden/Switch companion integration and acceptance |
| `vce-lan-peer` | LAN Sync and Phone Controller transport and two-peer evidence |
| `vce-android-device` | VCE-dedicated AVD, Android builds and device acceptance |
| `vce-release` | CI → GitHub release → web production, with evidence and rollback |
