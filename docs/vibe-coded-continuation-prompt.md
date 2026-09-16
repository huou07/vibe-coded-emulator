# Vibe Coded Emulator — continuation prompt for a new session

Copy everything below into the next session. It is self-contained.

---

## Mission

Continue the "Vibe Coded Emulator" product expansion (web + native apps +
emulator runtime + networking + sync + auth + cores). Work incrementally:
preserve working emulation and per-platform renderers, make small coherent
phases, build + test each phase, deploy to **staging only**, and report honestly
(`UNVERIFIED` rather than `GOOD` when a runtime was not actually exercised).

## Environment (verified 2026-09-16)

| Purpose | Path | Branch @ HEAD |
| --- | --- | --- |
| Original dev/build root (warm caches `target/`, `node_modules/`; intentionally dirty — never destructive-clean) | `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade` | `ui/production-ux-refresh` @ `542ef98` |
| Clean checkpoint worktree | `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/vibe-coded-emulator` | `vibe-coded-emulator` @ `4fceec7` |
| **Primary work root (use this)** | `/Users/meomeo/Documents/edit an3tocom apps&web` | `apps-web` @ `add0053` |

- **Do edit/commit/deploy from `apps-web`.** Keep `.../an3-arcade` only for
  build jobs that benefit from warm caches (or run `npm ci` once in the
  worktree's `native-offline/`).
- **CodeGraph is now indexed in all three roots** (`codegraph init -y` in the
  two worktrees, `codegraph sync` for the main tree). Use
  `codegraph_explore` MCP with `projectPath` (or `codegraph explore "<query>"
  --path ...`) before any grep/read of source.
- **Staging SSH:** key `/Users/meomeo/.ssh/an3_codex_ed25519`;
  `source tools/ssh/staging-env.sh` (sets `AN3_STAGING_SSH_IDENTITY_FILE` +
  `AN3_STAGING_SSH_KNOWN_HOSTS=$HOME/.ssh/known_hosts`), then
  `tools/ssh/check-staging-key.sh` (must print `STAGING_SSH_KEY_AUTH=PASS`) and
  `./deploy-stage.sh`.
- **Builders** (via `~/.ssh/config`): `an3-dell` (Debian Linux builder; has
  user-level rustup stable, Flathub, x86_64), `an3-win11-build` (Windows VM,
  ProxyJump via `an3-dell`; rustc 1.98.1, node 24, MSYS2 UCRT64, VulkanSDK).
- Staging: `http://192.168.1.8:8092`. **Never touch production** without
  explicit owner approval.

## Owner decisions (apply these)

1. **macOS:** only need to build and upload the `.dmg`. No Apple Developer
   account/notarization required — do not treat it as a blocker.
2. **Windows:** rebuild the Windows native runtime whenever its manifest sources
   change (the manifest hashes include `native-runtime/platform/linux/*`).
   Keep the documented two-step: `build-windows-runtime.ps1` then
   `build-windows-staging.ps1`. Start the VM only when needed, then shut it down
   gracefully (`shutdown /s` from inside Windows; ACPI `virsh shutdown` alone did
   not complete) and keep autostart `disable`.
3. **Switch:** use a maintained open-source Switch core (e.g. an actively
   maintained Yuzu fork such as Eden, or Citron/Sudachi — research current
   status and license). Owner accepts GPLv3; the project is open source. Isolate
   it behind its own abstraction; do not tightly couple to one implementation.
4. **Android `gen/`:** clean it up, track or relocate the custom Kotlin, rebuild
   and fix.
5. **CodeGraph:** re-index when stale (done now; re-run `codegraph sync`).

## Feature scope (the full wanted list — remember it)

Branding · Exit Game · configurable autosave (Off/On-exit/30/10/5) · quick slots
1–10 + toolbar Save · full per-core screen-layout chooser · non-blocking FPS
badge + menu-first touch precedence · multiplayer rooms + invite codes ·
phone-as-controller (QR/pairing) · LAN sync · Google sign-in + Drive sync ·
Switch core · preserve per-platform renderers · staging-first delivery + test
matrix · repo skills/agents.

## Current state

**Done and published (catalog 1.3.0, all five platforms, staging deployed):**
- Branding; Exit Game; shared autosave (`core/auto_save_mode.h`).
- Layout chooser from one generated source
  (`shared/native-layout-schema.json` → `shared/generated/native_layouts.h`).
- Toolbar Save exposing all ten quick slots; FPS pointer-inert; menu-first touch
  (macOS/Android/Linux).
- Staging-only multiplayer room API + `/multiplayer`; phone-controller API +
  `/controller`, `/controller/join`.
- Shared modules: `sync_engine.py`, `google_sync.py`, `netcode.py` (unit-tested).
- 1.3.0 artifacts: DMG 44,706,349 · APK 49,571,879 · DEB 45,484,618 ·
  Flatpak 29,090,480 · EXE 46,720,549. `RELEASE_CATALOG=PASS`; suite 225 tests.

**Not done:**
- Controller input actually driving the emulator + a QR renderer.
- Multiplayer rooms bridged to the EmulatorJS-Netplay relay with AN3 invite codes.
- LAN discovery + direct transfer; sync-mode wiring in `app.py`.
- Switch companion integration.
- Google OAuth routes/UI (owner said skip earlier; Drive sync UI absent).

**Unverified:** 1.3.0 runtime on Android/Linux/Windows (1.2.0 was verified:
Android 59 fps, 12 layouts, saved state; macOS/Linux runtime smoke). Windows has
never been run interactively. GUI menu clicks, Playwright web checks, real-phone
controller, two-machine rooms, live Google, LAN.

## Blockers and how to resolve

| Blocker | Resolution |
| --- | --- |
| Windows runtime must rebuild on source change | Already scripted; run the two-step (owner approved). |
| Windows VM lifecycle | Start only when needed; graceful in-Windows `shutdown /s`; keep autostart disabled. |
| Switch: no libretro core | Build a separate companion abstraction using an open-source Switch core (owner approved GPLv3). |
| Google OAuth | Needs owner-held credentials; module exists and is tested with an injected transport. |
| Android generated `gen/` untracked | Clean/relocate the custom Kotlin; rebuild. |
| CodeGraph stale | `codegraph sync` (already done; repeat as needed). |
| QR display under CSP | Vendor a tiny local QR encoder or render an SVG server-side. |

## Ordered work plan (do in this order; build+test+deploy each)

1. **Runtime-verify 1.3.0** — Android on the `codex-nds-api35` AVD (Save 10-slot
   dialog, FPS tap-through, menu-vs-touch) and Linux under Xvfb (`SDL_AUDIODRIVER=dummy
   AN3_OFFLINE_LIBDIR=<dir with libretro/core> LIBGL_ALWAYS_SOFTWARE=1`). Record
   evidence; don't claim GOOD without running.
2. **Make the controller real** — CSP-safe QR on `/controller`; host poll loop
   reading `/api/controller/state` and applying input via
   `InputRouter.setVirtualButton`/axes (web) and the native input injection
   (`nativeButton`/`nativeAnalog`). Acceptance: a phone moves the game.
3. **Bridge rooms → relay** — after the compatibility check, hand the relay
   origin + room id to the EmulatorJS netplay client (the bundle exposes
   `getOpenRooms`, `createPeerConnection`, `roomJoined`, `leaveRoom`) and surface
   the invite code in the game UI.
4. **LAN discovery + direct transfer + sync modes** — UDP/mDNS discovery + HTTP
   transfer reusing `sync_engine` planning; wire modes (Off / LAN / Drive /
   LAN+Drive) into `app.py`.
5. **Windows/Android/Linux 1.3.0 smokes**; re-index CodeGraph.
6. **Create the project skills/agents** (see below).
7. **Switch companion** last, behind its own abstraction, after a design note.

Then continue the remaining scope (Drive sync UI, etc.). Deploy to staging after
each completed step and verify.

## Skills/agents to create (project-local under `.opencode/`)

- **skill `an3-build`** — version-bump rule (patch/minor/major), per-platform
  commands (`npm run build:macos`; `bash scripts/build-android-staging.sh`; Dell
  `bash scripts/build-linux-staging.sh deb|flatpak`; Windows two-step), artifact
  collection, SHA-256 sidecars, `catalog.json` update,
  `python3 tools/verify-release-catalog.py`, then VM shutdown.
- **skill `an3-staging-deploy`** — `source tools/ssh/staging-env.sh` →
  `check-staging-key.sh` → `deploy-stage.sh` → `/health`, `artifacts.json`,
  installer download smoke. Staging-only.
- **skill `an3-player-regression`** — run the guards from `AGENTS.md` before/after
  any edit to `static/player.js`, `static/nds-touch.js`, `static/site.css`,
  `static/renderer-worker.js`, or shared player-model files; report UNVERIFIED vs
  GOOD honestly.
- **agent `player-verifier`** — runs the regression skill + Android AVD smoke
  (install/launch/dex/uiautomator) and reports evidence.
- **agent `release-coordinator`** — orchestrates the 5-platform build + publish +
  deploy incl. VM start/stop and Dell sync.
- **agent `staging-browser-verify`** — Playwright checks for `/`, `/multiplayer`,
  `/controller`, `/controller/join`, viewports/overflow.
- optional **skill `an3-codegraph-first`** — explore-before-grep; how to pass
  `projectPath`; how to re-index.

## Rules / guardrails

- Read the nearest `AGENTS.md` first; CodeGraph before grep/read.
- **App versioning:** every packaged-app change bumps the version (bug→patch,
  feature→minor, refactor→major) in `package.json`, `Cargo.toml`, `tauri*.conf.json`,
  `web/index.html`, build scripts, flatpak manifest/metainfo, the artifact
  filename, the catalog and the sidecar. **Never republish changed bytes under a
  published version + filename.**
- Never destructive-clean the dirty main worktree. Never expose secrets. Never
  create an SSH password helper. Production deploys require explicit owner
  approval.
- Do not declare UX/audio/input fixed from compilation alone.
- Keep the compact dark-violet minimal design; no feature cards/neon/marketing
  copy. Player input/canvas/overlay/virtual-pad geometry changes are separate
  tasks with their own guards.

## Commands cheat-sheet

```bash
# tests
PYTHONPYCACHEPREFIX="$PWD/work/pycache" python3 -m unittest discover -s tests
node --check static/player.js
# staging
source tools/ssh/staging-env.sh && tools/ssh/check-staging-key.sh && ./deploy-stage.sh
# catalog
python3 tools/verify-release-catalog.py
# macOS
cd native-offline && npm run build:macos
# Android
cd native-offline && bash scripts/build-android-staging.sh
# Linux (on an3-dell, after rsync of native-offline + static)
#   export CARGO_HOME=$HOME/.cargo RUSTUP_HOME=$HOME/.rustup; . "$HOME/.cargo/env"
#   cd ~/an3-verify/native-offline && PATH="$HOME/.cargo/bin:$PATH" bash scripts/build-linux-staging.sh deb|flatpak
# Windows (on an3-win11-build, two-step)
#   powershell -NoProfile -ExecutionPolicy Bypass -File ...\scripts\build-windows-runtime.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File ...\scripts\build-windows-staging.ps1
```

## Reporting

After each phase: what changed, files, version bump, build/test results,
staging asset + smoke, and an explicit list of what is verified vs UNVERIFIED.
Update `docs/vibe-coded-roadmap.md` and the continuation handoff in
`reports/handoff/` with absolute paths.

Start by reading `docs/vibe-coded-roadmap.md`, then continue the ordered plan
from step 1.
