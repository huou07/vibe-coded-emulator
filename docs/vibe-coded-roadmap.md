# Vibe Coded Emulator — roadmap and status plan

Verified 2026-09-16 against the working tree, the release catalog and the git
worktrees. Nothing here is claimed beyond what was run.

> **Historical.** Section 1 described macOS worktrees that do not exist on the
> current Debian host. The active root is this repository; resolve it with
> `git rev-parse --show-toplevel` rather than a fixed path. The branch and HEAD
> values below are kept as evidence of the 2026-09-16 verification.

## 1. Roots and credentials we can use now (2026-09-16, no longer present)

| Purpose | Path | Branch / HEAD |
| --- | --- | --- |
| Original dev/build root (warm caches: `target`, `node_modules`; intentionally dirty) | `<legacy-checkout>` | `ui/production-ux-refresh` @ `542ef98` |
| Clean checkpoint worktree | `<removed-macos-worktree>` | `vibe-coded-emulator` @ `af09bff` |
| Second clean worktree (the renamed `edit an3tocom apps&web`) | `<repo-root>` | `apps-web` @ `b7cc433` |

- All three hold the current source. The two worktrees are self-contained for
  source, tests and deploys.
- **Recommended:** do source edits, commits and deploys from `apps-web` (or a new
  clean worktree); keep `.../an3-arcade` only for builds that benefit from its
  warm `target/` and `node_modules/`. To build entirely from a worktree, run
  `npm ci` in `<worktree>/native-offline` once.

**Staging SSH**
- Private key: `~/an3_codex_ed25519` (600, owner-only).
- Env: `AN3_STAGING_SSH_IDENTITY_FILE` and
  `AN3_STAGING_SSH_KNOWN_HOSTS=$HOME/.ssh/known_hosts`.
- Helper (committed, paths only, no secret): `tools/ssh/staging-env.sh` —
  `source tools/ssh/staging-env.sh` then `tools/ssh/check-staging-key.sh` and
  `./deploy-stage.sh`. Verified working from `apps-web`.
- Other builders via `~/.ssh/config`: `an3-dell` (Debian Linux builder) and
  `an3-win11-build` (Windows VM, ProxyJump via `an3-dell`).

## 2. Features we set out to build

From the original spec plus later requests:

1. Branding — app icon (PNG1), transparent brand logo (PNG2), "Vibe Coded
   Emulator" naming.
2. In-game **Exit Game** with save-on-exit.
3. Configurable **autosave** — Off / On game exit / 30s / 10s / 5s.
4. Per-game quick save slots **1..10** plus a toolbar Save control that exposes
   them without opening the menu; web player already had the slot panel.
5. Full **screen-layout chooser** per core (not a 2-option cycle).
6. **FPS badge** that never blocks clicks; **menu-first** pointer precedence for
   NDS/3DS touch.
7. **Multiplayer rooms** — create room, invite code, host identity, join
   validation, ROM/core compatibility by hash, reconnect, expiry.
8. **Phone-as-controller** — pairing code, session tokens, low-latency
   latest-state-wins input, reconnect.
9. **LAN sync** — discovery + direct device-to-device transfer.
10. **Google sign-in** + **Google Drive sync** with conflict resolution
    (keep local / cloud / both) and sync modes (Off / LAN / Drive / LAN+Drive).
11. **Nintendo Switch** core integration (GPLv3 accepted by owner).
12. Preserve per-platform renderers (Metal/Vulkan/GL/WebGPU-WebGL2) and the
    optimized frame path.
13. Staging-first delivery, docs, and a real test matrix.

## 3. Done vs not done

**Done (shipped)**
- Branding across web + native, icons generated for every platform.
- Exit Game + shared autosave model (`auto_save_mode.h`) on macOS, Android,
  Linux, web.
- Screen-layout chooser from one generated source
  (`native-layout-schema.json` → `native_layouts.h`), macOS/Android/Linux.
- Toolbar Save with all 10 quick slots (macOS/Linux/Android).
- FPS pointer-inert + menu-first touch precedence (macOS/Android/Linux).
- Multiplayer room **API** + `/multiplayer` page (staging-only). The AN3 invite
  code **is** the EmulatorJS relay room name: the player hosts via
  `netplay.openRoom(code)` and joins via the compat-checked AN3 API +
  `netplay.joinRoom(key, code)`. Verified on staging (host `current:1` → guest
  `current:2`); see `reports/handoff/MULTIPLAYER_RELAY_BRIDGE_20260916.md`.
- Phone-controller **API** + `/controller`, `/controller/join` pages
  (staging-only).
- Phone controller is **real on the web player**: a CSP-safe server-side SVG QR
  (`/api/controller/qr.svg`) and a host poll loop that applies the phone's latest
  frame through the player's virtual-input path. Verified end-to-end on staging
  (phone press → `simulateInput(0,7,1)`/`(0,7,0)`); see
  `reports/handoff/WEB_CONTROLLER_BINDING_20260916.md`.
- Phone controller is **real on Android** (1.4.0, staging): the in-game menu
  hosts a session and injects native input through the pad path. Verified on the
  AVD (a `start` press from the phone advanced the GBA title to its menu); see
  `reports/handoff/ANDROID_NATIVE_CONTROLLER_20260916.md`.
- Phone controller **desktop host** (macOS/Linux/Windows share one Rust module,
  macOS 1.4.0 built): session + polling + injection unit-tested against a real
  TCP server; Settings → Phone controller UI; macOS DMG 1.4.0 built, launched,
  deployed. Live desktop pairing is UNVERIFIED; see
  `reports/handoff/DESKTOP_NATIVE_CONTROLLER_20260916.md`.
- Shared cores: `sync_engine.py`, `netcode.py` (unit-tested).
- **Sync mode wired into `app.py`** (staging-only): per-device Off/LAN/Drive/
  LAN+Drive mode, a plan/conflict API over the pure `sync_engine`, and a
  subnet-scoped LAN peer registry with a `/sync` page. Drive stays unavailable
  until owner credentials exist. See `reports/handoff/SYNC_WIRING_20260916.md`.
- Android 1.1.0 published; **1.2.0** published for all five platforms; **1.3.0**
  published for all five platforms (DMG/APK/DEB/Flatpak/EXE), catalog PASS.
- **1.4.0** published for all five platforms (adds the native phone controller;
  release scripts now derive artifact names from the version field). See
  `reports/handoff/RELEASE_1.4.0_20260916.md`.
- Deploy regression fixed (missing `netcode.py`/`sync_engine.py`) + guard test.
- **Switch / Eden (2026-09-17)**: the Eden bridge links and runs on macOS;
  sustained rendering is stable (RG-115 fixed by hosting the CAMetalLayer on a
  hidden window); button/analog input and save-directory export are implemented
  and verified (RG-116/117); `an3_switch_companion` is a separate-process
  companion with a visible window, keyboard input and an stdin automation
  channel (RG-118); `an3ctl switch …` drives it. Legal homebrew only
  (nx-hbmenu). See `docs/checkpoints/eden-native-integration.md`.

**Not done**
- Controller desktop **GUI glue** observed end to end (the client, the
  shell→runtime `INPUT` write, and the runtime→core path are each verified; the
  app's UI/WebView was not driven). Android is done and verified (1.4.0).
- Multiplayer **peer video** on the web (the staged EmulatorJS build has no
  WebRTC; it is relay input lockstep, and peer input sync is verified).
- **LAN byte-level transfer** is implemented and **verified across the MacBook
  and the Debian** (publish → manifest → blob, SHA-256 byte-exact both ways).
  It is LAN-mediated through the staging server (the LAN rendezvous); true
  peer-to-peer device listeners and client-store wiring remain.
- **Google sign-in + Drive transport** (owner skipped; needs OAuth
- **Switch companion** integration: the companion process, its rendering,
  input, saves and automation are built and verified on macOS; what remains is
  the Tauri `CompanionSystem` (detect/launch/focus/stop), `.nro` detection,
  bundling the companion into the packaged app, and a Switch library/UI
  surface. Switch is intentionally not advertised in the app until then.
- Per-engine renderer work is unchanged (and should stay unchanged unless
  demanded).

## 4. Unverified

- **1.3.0 runtime** on Android (Save 10-slot dialog, FPS tap-through,
  menu-vs-touch) and on Linux/Windows. 1.3.0 was **built**, not run.
  (1.2.0 was verified: Android 59 fps, 12 layouts, saved state; macOS/Linux
  runtime smoke.)
- Windows 1.3.0 **launch smoke done** (2026-09-16): installs silently, the app
  launches/responds and initializes WebView2 on the `an3-win11-build` VM.
  Windows **gameplay/rendering/audio/input remain UNVERIFIED** (Session 0, no
  Vulkan ICD). See `reports/handoff/WINDOWS_1.3.0_LAUNCH_SMOKE_20260916.md`.
- macOS menu **click** interaction (GUI), and the new FPS/menu guards at runtime.
- Web UI via Playwright for `/multiplayer` and `/controller`.
- Controller on a real phone (the QR was decoded programmatically, not by a
  phone camera); rooms between two machines; live Google; LAN sync.
- Controller input injection into the packaged native apps.
- Web multiplayer **peer video** (not implemented in the staged build; input
  lockstep is verified end-to-end).
- Desktop controller **GUI** run (no window manager on the Linux builder, so the
  Tauri WebView could not be driven; macOS/Windows GUI runs would need a
  desktop session). Every logic link is verified separately.

## 5. Real blockers and how to resolve

| Blocker | Real? | Resolution |
| --- | --- | --- |
| macOS app is ad-hoc signed, **not notarized** (no Apple Developer credentials) | Yes, external | Acquire Apple Developer ID + notarization; until then it is staging-only. Cannot be fixed in code. |
| Windows build needs the native runtime rebuilt whenever **any** source listed in `vendor/runtime/windows-x64/manifest.json` changes — and that list includes `native-runtime/platform/linux/*` | Yes | Either split the manifest source list per platform, or keep the two-step (`build-windows-runtime.ps1` then `build-windows-staging.ps1`) explicit in the release skill. Documented in scripts. |
| Windows VM must be started/stopped manually; ACPI `virsh shutdown` didn't complete | Mostly solved | Use in-Windows `shutdown /s` over SSH; keep autostart `disable`. |
| Dell `rustc 1.85` too old for the lock | Solved | user-level rustup stable on the Dell (done). |
| `find … -quit` reused a stale DEB | Solved | script clears `bundle/deb` before building (done). |
| PowerShell `ErrorActionPreference=Stop` treats native stderr as fatal | Solved | scripts use `Continue` + `$LASTEXITCODE` (done). |
| Google sign-in | No | Removed. Google cloud sync is not a product feature. |
| Switch: **no maintained libretro core**; GPLv3 accepted | Yes, architectural | Isolate behind a new companion-core abstraction; do not add Switch to `NativeSystem` until the companion design is agreed. **Design note written:** `docs/vibe-coded-switch-companion.md` (Eden, launched as a separate process; the companion is since implemented — see `docs/checkpoints/eden-native-integration.md`). |
| Android generated Kotlin under `native-offline/src-tauri/gen` is untracked | Yes, hygiene | Decide: track `gen/android/app/src/main/java` + assets, or move the custom Kotlin out of the generated tree. |
| CodeGraph index is **stale** for `app.py`, `libretro_host.cpp`, `player-runtime.js`, etc. | Yes, tooling | Re-run `codegraph init`/sync for this project. |
| QR display needs a generator; CSP forbids external scripts/CDNs | Minor | Vendor a tiny local QR encoder (or draw it server-side as an SVG). |

## 6. What is possible to code and fix now

- Runtime-verify 1.3.0 on the AVD (the AVD is up) and on Linux under Xvfb.
- Controller **host binding**: add a poll loop that reads
  `/api/controller/state` and applies `InputRouter.setVirtualButton`/axes in the
  web player, and the equivalent native input injection — makes the feature real.
- **QR renderer** (local, CSP-safe) on `/controller`.
- **Rooms → relay bridge**: verify system/core/ROM-hash, then hand the relay
  origin + room id to the EmulatorJS netplay client (the bundle already exposes
  `getOpenRooms`, `createPeerConnection`, `roomJoined`, `leaveRoom`).
- **LAN**: discovery (UDP broadcast/mDNS) + HTTP transfer endpoint reusing
  `sync_engine` planning; wire the sync modes into `app.py`.
- **Windows 1.3.0 runtime test**, and Android/Linux 1.3.0 checks.
- Re-index CodeGraph; add repo-hygiene commits for `gen`.
- All of the above are codeable here except anything needing Apple/Google
  credentials or a Switch companion decision.

## 7. Custom opencode agents/skills to create for this project

**Created 2026-09-16** under the project-local skill/agent directories (so they
travel with the repo):
`an3-build`, `an3-staging-deploy`, `an3-player-regression`,
`an3-codegraph-first`, `player-verifier`, `release-coordinator`,
`staging-browser-verify`. The descriptions below are the original rationale.

Shared skills belong under `.agents/skills/<name>/SKILL.md`; client-specific
agents, when still needed, remain under `.opencode/agent/`:

1. **skill `an3-build`** — "Build/publish a native platform for Vibe Coded
   Emulator." Encodes: the version-bump rule (patch/minor/major), the exact
   per-platform commands (`npm run build:macos`, `native-offline/scripts/build-android-staging.sh`,
   Dell `build-linux-staging.sh deb|flatpak` via `an3-dell`, Windows two-step via
   `an3-win11-build`), artifact collection, sidecar creation, `catalog.json`
   update, `tools/verify-release-catalog.py`, and the VM shutdown step.
2. **skill `an3-staging-deploy`** — `source tools/ssh/staging-env.sh` →
   `check-staging-key.sh` → `deploy-stage.sh` → health/artifacts/download smoke.
   Staging-only; explicit "never production without owner approval".
3. **skill `an3-player-regression`** — the guard list from `AGENTS.md`: run
   `tests/test_regression_invariants.py`, `test_web_nds_touch_behavior.py`,
   `test_native_regression_guards.py`, `test_shared_player_ui.py`, and the
   node behavior tests before/after any edit to `static/player.js`,
   `static/nds-touch.js`, `static/site.css`, `static/renderer-worker.js`, or
   shared player-model files. Records UNVERIFIED vs GOOD honestly.
4. **agent `player-verifier`** (subagent) — runs the player regression skill and
   an Android AVD smoke (install/launch/dex/uiautomator) and reports pass/fail
   with evidence.
5. **agent `release-coordinator`** (subagent) — orchestrates the 5-platform
   build + publish + deploy, including VM start/stop and the Dell sync.
6. **agent `staging-browser-verify`** (subagent) — Playwright checks for
   `/`, `/multiplayer`, `/controller`, `/controller/join`, viewports, overflow.
7. Optionally **skill `an3-codegraph-first`** — codify "explore with CodeGraph
   before grep/read", including how to pass `projectPath` and how to re-index.

Rationale: each maps to a repeated, error-prone workflow this session actually
hit (version bumps, stale artifacts, VM lifecycle, missing modules, guard tests).

## 8. What to do next (ordered)

1. **Runtime-verify 1.3.0** — Android on the running AVD (Save 10-slot dialog,
   FPS tap-through, menu-first touch) and Linux under Xvfb; record evidence.
2. **Make the controller real** — QR on `/controller` + host poll loop applying
   phone input to the emulator input path. This is the largest user-visible gap.
   **Done on the web player** (staging-verified 2026-09-16), **on Android
   1.4.0**, and **desktop host built** (macOS 1.4.0; live pairing unverified).
3. **Bridge rooms to the relay** — compatibility check → relay handout → invite
   code surfaced in the game UI. **Done and staging-verified** (invite code ==
   relay room name; peer media sync still unverified).
4. **LAN discovery + direct transfer** and **sync wiring** in `app.py`.
   **2026-10-10 private-branch update:** native peer listeners and client-store
   wiring transfer save/state bytes directly. The P1 wire-size gap is closed
   in private source: large members use authenticated 768 KiB chunks,
   one active staged publish bounds memory, and complete sets retain the
   existing hash validation and atomic publish path. The browser tests cover
   large uploads/downloads and the Rust test covers chunk ordering and publish
   slot release. Packaged peer-to-peer transfer and gameplay impact remain
   **UNVERIFIED** pending hosted runtime acceptance. The frozen 3.6.8 core-only
   candidate intentionally excludes LAN Sync.
5. **Windows/Linux 1.3.0 runtime smoke**; re-index CodeGraph.
   **Done:** Android verified; Linux launch smoke; Windows launch smoke
   (gameplay unverified); CodeGraph synced.
6. **Create the skills/agents** in §7 as the workflows stabilize.
7. **Switch companion** last, behind its own abstraction and after a design sign-off. *(Done: the design was signed off and the companion shipped.)*
   **Design note written** (`docs/vibe-coded-switch-companion.md`: Eden, separate
   process, GPL boundary, no keys/firmware, Phase 1 = one desktop platform).
   Implementation shipped; see `docs/checkpoints/eden-native-integration.md`.

Each step: build → focused tests → staging deploy → record UNVERIFIED vs GOOD.
