# VCE Development Guide

Vibe Coded Emulator (VCE) is an **offline-first emulator front end**. The user
supplies their own legally obtained ROM files; the project bundles no ROMs,
firmware, keys or saves. Emulation itself runs on third-party cores (mGBA,
melonDS DS, Azahar natively; EmulatorJS in the browser).

## Product scope — the real one

| In scope, worked on | Not in scope |
| --- | --- |
| GBA / NDS / 3DS emulation on Android, Windows, Linux, macOS | Google sync — removed in `d858e36`, do not reintroduce |
| Switch (Eden) companion bridge, macOS-verified | Cloud-hosted multiplayer rooms on a LAN relay — not a server capability |
| Browser emulation on the surfaces EmulatorJS genuinely supports | Native builds for platforms with no pinned core artifact |
| Gameplay performance, frame pacing, reliability | Unspecified "improve everything" refactors |
| Save states, autosave, per-core settings, 10 quick slots | |
| LAN Sync (save transfer) and Phone Controller (direct LAN peer) | |

**Never claim a capability in docs, README or UI that the code and the recorded
evidence do not support.** `docs/REGRESSION_GUARDS.md` labels this repo's
findings `GOOD` / `UNVERIFIED`; keep using those two words literally. A claim
without evidence is `UNVERIFIED`, never "should work".

## Layout and the app/Web boundary

- `app.py` — the Web product: HTTP routing, SQLite, sessions, ROM delivery,
  EmulatorJS proxy, pages. Python **standard library only**, no dependencies.
- `static/` — browser player and site UI. **Also the native player's UI**:
  `native-offline/scripts/prepare-web.mjs` copies it into the Tauri bundle, so
  a `static/` edit is simultaneously a Web change *and* an unreleased native
  change. Keep `static/` runtime-agnostic: branch on `globalThis.AN3Native*`
  adapters, never on `__TAURI__` directly outside `offline.js` and `player.js`.
- `native-offline/` — Tauri 2 shell (`src-tauri/`, Rust), the portable libretro
  player (`native-runtime/`, C++), the native UI (`web/`), and the Android host.
- `rust-gateway/` — a shadow reverse proxy. **Not wired into `app.py`; its
  cutover is permanently blocked** (`docs/archive/rust-shadow-staging-cutover.md`).
  Do not build on it.
- `tests/` — Python `unittest` (Web/server) and Node `--test` (browser and
  native JS models).
- `tools/`, `native-offline/scripts/`, `deploy/` — verification, packaging,
  release and staging operations. Read a script before running it.

`docs/README.md` is the documentation index and states what is current.

## Verification

Local, lightweight, and safe on this Debian host:

```bash
bash tools/verify-project.sh        # the whole local gate
python3 -m unittest discover -s tests
node --test --test-concurrency=1 tests/*.test.mjs tests/*.test.js
npm --prefix native-offline run check
```

**GitHub Actions is the build and test authority.** `.github/workflows/verify.yml`
runs the local gate on every push and PR. Anything that needs a real toolchain —
Rust/C++ compilation, Tauri bundles, APK/DEB/Flatpak/DMG/EXE packaging,
Android instrumentation, per-platform runtime acceptance — belongs to
`tools/release-train.sh` on its dedicated builders, not to a Debian workstation.

**This host cannot do heavy work.** No VMs, no Android emulators or AVDs, no GPU
or emulator compilation, no release installers. Tests that need absent tooling
(the Playwright leg of `tests/an3ctl.test.mjs`) skip rather than fail; a skip is
`UNVERIFIED`, not a pass. Never weaken an assertion to make a gate go green.

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

Before and after touching the player canvas, input, layering, save, audio or a
renderer, run the matching guards in `docs/REGRESSION_GUARDS.md` and honour the
interaction contracts in `docs/player-layering.md`.

## Safety and release boundary

- Work staging-first. Production, releases and publication to a public
  repository require **explicit human approval** — never automatic.
- Never rewrite published history and never force-push.
- Keep third-party notices and license texts intact; see `docs/licensing/`.
- Use only lawful fixtures.
- `tools/publication-check.sh` fails closed. If a scanner cannot run,
  publication is blocked, not waved through.

## Agents and skills

Project skills in `.agents/skills/` load on demand and cover the areas a
generic agent cannot know: `an3-build` (packaging and the release catalog),
`an3-control-plane` (the `an3ctl` runtime control loop), `an3-player-regression`
(the player guards), `an3-staging-deploy`, `public-release-security`. Prefer
these and the shared host skills over inventing a parallel process.
