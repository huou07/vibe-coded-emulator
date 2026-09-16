# Vibe Coded Emulator — roadmap and status plan

Verified 2026-09-16 against the working tree, the release catalog and the git
worktrees. Nothing here is claimed beyond what was run.

## 1. Roots and credentials we can use now

| Purpose | Path | Branch / HEAD |
| --- | --- | --- |
| Original dev/build root (warm caches: `target`, `node_modules`; intentionally dirty) | `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade` | `ui/production-ux-refresh` @ `542ef98` |
| Clean checkpoint worktree | `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/vibe-coded-emulator` | `vibe-coded-emulator` @ `af09bff` |
| Second clean worktree (the renamed `edit an3tocom apps&web`) | `/Users/meomeo/Documents/edit an3tocom apps&web` | `apps-web` @ `b7cc433` |

- All three hold the current source. The two worktrees are self-contained for
  source, tests and deploys.
- **Recommended:** do source edits, commits and deploys from `apps-web` (or a new
  clean worktree); keep `.../an3-arcade` only for builds that benefit from its
  warm `target/` and `node_modules/`. To build entirely from a worktree, run
  `npm ci` in `<worktree>/native-offline` once.

**Staging SSH**
- Private key: `/Users/meomeo/.ssh/an3_codex_ed25519` (600, owner-only).
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
- Multiplayer room **API** + `/multiplayer` page (staging-only).
- Phone-controller **API** + `/controller`, `/controller/join` pages
  (staging-only).
- Shared cores: `sync_engine.py`, `google_sync.py`, `netcode.py` (unit-tested).
- Android 1.1.0 published; **1.2.0** published for all five platforms; **1.3.0**
  published for all five platforms (DMG/APK/DEB/Flatpak/EXE), catalog PASS.
- Deploy regression fixed (missing `netcode.py`/`sync_engine.py`) + guard test.

**Not done**
- Controller **input actually driving the emulator** (host polling + applying to
  EmulatorJS/native input) and a **QR renderer**.
- Multiplayer rooms **bridged to the EmulatorJS-Netplay relay** with AN3 invite
  codes end-to-end in the game UI.
- **LAN discovery + direct transfer** (transport only; `sync_engine` planning
  exists).
- **Sync wiring in `app.py`** (Drive mode UI + routes). Google OAuth routes/UI
  were explicitly skipped by the owner.
- **Switch companion** integration.
- Per-engine renderer work is unchanged (and should stay unchanged unless
  demanded).

## 4. Unverified

- **1.3.0 runtime** on Android (Save 10-slot dialog, FPS tap-through,
  menu-vs-touch) and on Linux/Windows. 1.3.0 was **built**, not run.
  (1.2.0 was verified: Android 59 fps, 12 layouts, saved state; macOS/Linux
  runtime smoke.)
- Windows 1.3.0 at all (build only); no interactive Windows run has ever been
  recorded.
- macOS menu **click** interaction (GUI), and the new FPS/menu guards at runtime.
- Web UI via Playwright for `/multiplayer` and `/controller`.
- Controller on a real phone; rooms between two machines; live Google; LAN sync.

## 5. Real blockers and how to resolve

| Blocker | Real? | Resolution |
| --- | --- | --- |
| macOS app is ad-hoc signed, **not notarized** (no Apple Developer credentials) | Yes, external | Acquire Apple Developer ID + notarization; until then it is staging-only. Cannot be fixed in code. |
| Windows build needs the native runtime rebuilt whenever **any** source listed in `vendor/runtime/windows-x64/manifest.json` changes — and that list includes `native-runtime/platform/linux/*` | Yes | Either split the manifest source list per platform, or keep the two-step (`build-windows-runtime.ps1` then `build-windows-staging.ps1`) explicit in the release skill. Documented in scripts. |
| Windows VM must be started/stopped manually; ACPI `virsh shutdown` didn't complete | Mostly solved | Use in-Windows `shutdown /s` over SSH; keep autostart `disable`. |
| Dell `rustc 1.85` too old for the lock | Solved | user-level rustup stable on the Dell (done). |
| `find … -quit` reused a stale DEB | Solved | script clears `bundle/deb` before building (done). |
| PowerShell `ErrorActionPreference=Stop` treats native stderr as fatal | Solved | scripts use `Continue` + `$LASTEXITCODE` (done). |
| Google sign-in needs OAuth client id/secret + redirect URIs | Yes, external | Owner must create credentials; code path exists (`google_sync.py`) and is tested against an injected transport. |
| Switch: **no maintained libretro core**; GPLv3 accepted | Yes, architectural | Isolate behind a new companion-core abstraction; do not add Switch to `NativeSystem` until the companion design is agreed. |
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

Suggested under `.opencode/skill/<name>/SKILL.md` and `.opencode/agent/<name>.md`
(project-local so they travel with the repo):

1. **skill `an3-build`** — "Build/publish a native platform for Vibe Coded
   Emulator." Encodes: the version-bump rule (patch/minor/major), the exact
   per-platform commands (`npm run build:macos`, `scripts/build-android-staging.sh`,
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
3. **Bridge rooms to the relay** — compatibility check → relay handout → invite
   code surfaced in the game UI.
4. **LAN discovery + direct transfer** and **sync wiring** in `app.py`.
5. **Windows/Linux 1.3.0 runtime smoke**; re-index CodeGraph.
6. **Create the skills/agents** in §7 as the workflows stabilize.
7. **Switch companion** last, behind its own abstraction and after a design sign-off.

Each step: build → focused tests → staging deploy → record UNVERIFIED vs GOOD.
