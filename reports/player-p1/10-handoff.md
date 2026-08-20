# AN3 Arcade — P1 Closeout Handoff

Date: 2026-08-20 (Asia/Ho_Chi_Minh)  
Status: `P1_STATUS=PRODUCTION_DEPLOYED_KNOWN_DEFECT_ACCEPTED`

## Start here in a fresh session

1. Read this file, `reports/player-p1/00-baseline.md` through `09-production-release.md`, `docs/player-layering.md`, and `reports/roadmap/00-current-state.md`.
2. Run `git status --short --branch`, `git rev-parse HEAD`, `git log --oneline -20`, and `git diff --check` before editing.
3. Preserve the dirty worktree exactly. Do not use `git reset --hard`, `git clean -fdx`, or a broad checkout.
4. P1 is closed. Do not start P2/admin/telemetry/migration/ads/points/multiplayer/3DS/Switch/content work, or change production, without a new explicit owner scope and approval.

## Workspace and source state

- Workspace: `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade`
- Branch: `ui/production-ux-refresh`
- P1 closeout HEAD before this handoff document: `1d24515913ad74f26cf23efbbceac10dae4327fa`
- Branch state at closeout: `ahead 22` of `origin/ui/production-ux-refresh`; no force-push or history rewrite was performed.
- Legacy repository remains read-only and untouched.

### Preserved dirty state (not part of the P1 release commit history)

| Path | Ownership / handling |
| --- | --- |
| `app.py` | Separate enrichment-review flow; preserve. |
| `static/player.js` | Contains the retained P0 canvas-only root NDS touch overlay; it was included in staging/production release material but remains dirty in this local worktree. |
| `static/site.css`, `static/site.js` | Separate enrichment-review work; preserve. |
| `tests/test_integration.py`, `tests/test_regression_invariants.py` | Enrichment/P0 assertions; preserve. |
| `reports/.DS_Store`, `reports/roadmap/` | Pre-existing untracked work; do not delete or absorb without separate scope. |

The P1 commits were created with an index-only integration approach specifically to avoid discarding or accidentally committing this owner work.

## P0 inherited state — closed, preserve as invariants

- EmulatorJS remains client-side; NDS core is `melonds`, auto-start is enabled, IndexedDB persistence and offline/NDS ZIP support remain intact.
- An NDS root touch gesture starts only on the actual `#game canvas` and remains bound to that canvas; it must not begin from an EmulatorJS menu/dialog hit.
- Layering contract: `game canvas < touch controls < transient HUD < modal/settings`.
- When the native NDS menu is open, custom pad is below the game (`z-index: 19`) and pointer-inert; menu settings must remain clickable.
- Desktop default hides the virtual pad via capability signals, not UA sniffing. Touch devices default shown; persisted user override remains available. Keyboard autofocus/remapping, fullscreen target (`player-shell`), and save states are invariants.

P0 was owner-device validated and previously production-deployed. Do not reopen it unless current evidence shows a regression.

## P1 implementation

### Runtime and performance-capability findings

- Verified deployed runtime: EmulatorJS 4.2.3.
- mGBA uses its legacy flavor by default. melonDS uses WebGL2 by report when the browser supports it; the verified legacy melonDS flavor is available and starts successfully.
- Supported P1 surfaces: `EJS_forceLegacyCores` (next launch), native `webgl2Enabled` (restart), VSync (live), `getFrameNum()`, `getVideoDimensions()`, and the four verified fast-forward/slow-motion methods.
- Unsupported/not admitted: frame skip, render/DPR scaling, audio-latency loader setting, NDS thread binary, unconfigured shader effects, and the existing `EJS_fixedSaveInterval`, `EJS_browserMode`, and `EJS_mouseLock` no-op assignments.
- FPS HUD is now the verified native EmulatorJS setting `fps:"show"`; it is a default rather than a forced replacement of existing non-NDS user preferences.

See `01-performance-capabilities.md` for source/symbol, default, safety, and per-core evidence.

### Profiles and recommendation

- Local-only schema: `an3-player-performance-v1`.
- Shape: `{version:1, selectedProfile:"auto"|"low"|"balanced"|"quality"|"custom", customOverrides:{ndsRenderer:"native"|"legacy"}}`.
- Profiles: Low-end/Battery, Balanced, Quality, Custom, plus Use recommended settings.
- Recommendation is memory-only and conservative: Balanced normally; Low only with combined low-memory/low-concurrency evidence or NDS without WebGL2. Never auto-recommend Quality. Explicit selection is persisted and never overwritten.
- Only verified profile effect: Low (or Custom legacy) selects melonDS legacy compatibility rendering at the next launch. No canvas scaling, frame skip, shader, thread, or audio-latency control is exposed.

### Speed controls

- GBA/NDS compact session-only controls: `0.5×`, `1×`, `1.5×`, `2×`.
- Uses `setFastForwardRatio`, `toggleFastForward`, `setSlowMotionRatio`, and `toggleSlowMotion` only after game start. At `1×`, both modes are disabled.
- No speed persistence key exists. Native duplicate fast-forward/slow-motion settings are hidden; the existing native rewind surface remains.

### Virtual-pad settings and migration

- NDS settings key: `an3-pad-settings-v4:nds`; other custom-pad systems: `an3-pad-settings-v2`.
- Layout keys remain `an3-pad-v4:nds:<system>:<orientation>` and `an3-pad-v3:<system>:<orientation>`.
- Schema uses `globalScale`, `buttonScales`, opacity, and NDS `visibilityMode` (`auto|shown|hidden`). Legacy absolute `sizes` are migrated to relative multipliers while preserving effective geometry.
- Global scale is 70–100%; selected control scaling is relative 50–200%, subject to measured edge and collision guards. The actual `.tvCtrl` hitbox is used.
- The original P1.5 whole-pad hide on a short viewport caused an Android pad-only-in-fullscreen regression. Commit `af6cca9` retains safety checks for increases/moves but never hides an already playable pad because of the measurement result.

### Player UX/PWA

- Player panel grouping: Performance, Speed, Controls, Game & saves, Advanced.
- More opens the panel for all cores; native EmulatorJS menu still closes the app panel before opening.
- Online/offline markup is mirrored. PWA shell cache is `an3-arcade-pwa-v26`.

## P1 files and commits

Main implementation/release files:

- `app.py`
- `static/offline.js`
- `static/player.js`
- `static/service-worker.js`
- `static/site.css`
- `tests/test_regression_invariants.py`
- `reports/player-p1/`
- `docs/player-layering.md`

P1 commit sequence:

```text
7d2c67f docs(player): record P1 performance capability audit
3bc01fe feat(player): add conservative performance profiles
33d0bce docs(player): record profile staging validation
2db68e5 feat(player): add session speed controls
49e4429 fix(pwa): refresh player speed assets
2850c46 docs(player): record speed staging validation
f3d6546 feat(player): add safe global pad scaling
bd96836 feat(player): add safe individual pad sizing
803a6ec fix(player): guard pad scale transitions
1420ce0 feat(player): group player options safely
5a3fdae docs(player): record P1 control validation
727e26d docs(player): record P1 staging validation
af6cca9 fix(player): keep mobile pad visible and default fps hud
6869d1c docs(player): record mobile staging follow-up
cc2da51 docs(player): record NDS audio device evidence
1d24515 docs(player): close P1 production release
```

## Tests and validation

| Gate | Result |
| --- | --- |
| Local full suite | PASS — 15/15 |
| JS syntax, Python compilation, `git diff --check` | PASS |
| Staging health and GBA/NDS startup | PASS |
| Profiles/recommendation/persistence/reset | PASS |
| Compact speed | PASS |
| Global and selected-pad scaling/reset | PASS |
| P0 NDS menu priority/root touch | PASS |
| Owner device: save/load, keyboard/remapping, PWA, weak-device performance, speed, virtual pad, fullscreen | PASS |
| Production: health, homepage, public GBA/NDS play routes, player markers | PASS |

Staging release remains `20260820-215934-p1-mobile-fix`, asset `49eeea612e77`. Production is active with health asset `aa8faa00dc8a`.

## Failed experiments and known limitation

### P1-KD-001 — NDS audio crackle on Redmi 15 5G

- Reproduces with Firefox, Chrome, and Mi Browser; Firefox is frequent, Chrome/Mi Browser are most apparent at scene transitions.
- Both the built-in speaker and Bluetooth headphones reproduce it, supporting an emulation/WebAudio underrun diagnosis rather than output hardware/codec fault.
- FPS was reported around 30–50.
- On Chrome, `1×` speed, Low-end/Battery (legacy renderer), and native VSync disabled did **not** resolve it.
- Current core defaults are `melonds_audio_bitrate = Automatic` and `melonds_audio_interpolation = None`. The exposed 10-bit/16-bit choices are fidelity controls, not a proven stability/buffer remedy.
- Runtime hard-codes RetroArch `audio_latency = 64`; no supported AN3 loader/API control exists. No speculative bitrate, interpolation, buffer, core, or global setting was shipped.

Owner explicitly accepted this defect, instructed that it be recorded but not fixed, and approved P1 production closure. Do not treat it as a P0 regression or silently tune it in a future session. A new audio/core-runtime feasibility scope is required before any change.

## Production state and rollback

- Production service: `an3-arcade.service` active at `/opt/an3-arcade`.
- Production health: `environment: production`, asset `aa8faa00dc8a`.
- Deployed exact files: `app.py`, `static/offline.js`, `static/player.js`, `static/service-worker.js`, `static/site.css`.
- These files match the validated staging release byte-for-byte.
- Production rollback archive: `/opt/an3-arcade-backups/20260820-225248-p1-production/p1-files.tar.gz`.
- Prior preflight backup: `/opt/an3-arcade-backups/20260820-225113-p1-pre-production/p1-files.tar.gz`.
- A first deployment attempt rolled back automatically because of an invalid shell health-parser quote; it was not an application failure. Production was confirmed healthy at the pre-P1 asset before the successful deployment.

Never modify production, restore a backup, delete game data, or rotate infrastructure credentials without a new explicit owner approval.

## Next recommended phase

Stop here. P1 is closed.

The next session must wait for a new explicit owner request. If the owner chooses to pursue NDS audio later, start with a separate feasibility/audit phase that validates the current EmulatorJS/melonDS core version, native Android WebAudio behavior, alternative core compatibility, save-state compatibility, touch handling, and a staging/device matrix before changing any default or production release.
