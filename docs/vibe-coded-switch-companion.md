# Vibe Coded Emulator — Nintendo Switch companion design

Status: **superseded as a status source.** This note settled the architecture,
licensing and safety questions. The companion has since been implemented —
`native-offline/src-tauri/src/switch_companion.rs` and the out-of-process bridge
in `native/eden-bridge/`. For what is true today, read
[`checkpoints/eden-native-integration.md`](checkpoints/eden-native-integration.md)
and `docs/REGRESSION_GUARDS.md` (RG-141, RG-148).

`NativeSystem` is unchanged; the companion stays behind its own abstraction and
a separate process for the GPLv3 isolation recorded below.

Date: 2026-09-16. Owner decision already recorded: GPLv3 is acceptable; Switch
must sit behind its own abstraction, separate from `NativeSystem`.

## 1. Core choice (researched 2026-09-16)

| Candidate | Maintained? | License | Builds | Notes |
| --- | --- | --- | --- | --- |
| **Eden** (`git.eden-emu.dev`, `eden-emu.dev`) | Yes, active (nightly, monthly reports) | **GPL-3.0-or-later** | Windows, Linux, macOS, Android, FreeBSD | Yuzu/Sudachi descendant; the maintained reference; packaged in distros (~0.2.x) |
| Sudachi | Canonical repo is a backup (`git.suyu.dev/sudachi-backup`), "compatibility unavailable" | GPLv3 | Android/Linux/macOS/Windows | Public "download" sites are low-trust; prefer as fallback only |
| Citron | Fork of Yuzu, active-ish | GPLv3 | Windows/Linux/Android | Further fork; smaller surface |
| Ryujinx / Ryubing | Ryujinx discontinued; Ryubing continues | MIT (Ryujinx) | Windows/Linux/macOS | Per-title compatibility differs; kept as a note, not the pick |

**Decision:** Eden is the first companion core. Sudachi/Citron are fallbacks only
if Eden stalls. All are GPLv3; the owner accepted GPLv3 for the companion.

There is still **no maintained libretro Switch core**, so the existing
`NativeCoreHost` (libretro) abstraction cannot host Switch. That abstraction
stays untouched.

## 2. Isolation boundary (the whole point)

- The companion is a **separate executable/process**, never linked into the AN3
  binary. GPLv3 obligations stay on the companion; AN3 does not become a derived
  work of it.
- New abstraction, deliberately **not** `NativeSystem` and not a libretro core:

  ```
  CompanionSystem (interface)
    detect() -> availability + version            # never bundled keys/firmware
    launch(romPath, options) -> session handle    # ROM path only, user-supplied
    status() -> running | exited | error
    focus() -> bring the companion window forward
    requestSave() / loadSave()                    # uses the companion's own states
    stop(graceful: bool)
  ```

- AN3 owns the session lifecycle (Exit Game, autosave cadence, window focus),
  exactly as it owns `NativeCoreHost`. The companion owns its own rendering and
  save-state formats; AN3 frames into it are not libretro frames.
- Precedent already in the tree: the Android **Azahar companion** is a separate
  deliverable surface. The Switch companion follows the same pattern, one step
  further (its own process/binary rather than an in-app library).

## 3. Licensing and notices

- Ship the companion as its own component with: the GPLv3 text, a written offer
  for corresponding source, the exact upstream commit, and our patches (if any)
  in the repo under `vendor/` with normalized hashes — mirroring how mGBA/azahar
  are pinned today (RG-073/RG-074 style).
- `THIRD_PARTY_NOTICES.md` records the companion license and the process
  boundary ("launched, not linked").
- No license change to the AN3 app is required for a separate-process launch;
  if any future phase links instead of launches, it stops and returns here.

## 4. Safety invariants (non-negotiable)

- **Never bundle** `prod.keys`, `title.keys`, firmware, or commercial ROMs.
  Users supply their own; the UI must say so.
- `sync_engine` already refuses `firmware` and `keys` (`SYNC_ELIGIBLE_KINDS`);
  the companion must not add a path that syncs them.
- Never advertise a compatibility list, performance numbers, or "Switch works";
  a companion phase reports only what was actually run (e.g. a legal homebrew
  NRO), exactly like the 3DS Android evidence rules.
- Build hosts for the companion are separate; do not run its builds on the
  verified staging host, and never on production.

## 5. Platform phasing

1. **Phase 0 — sign-off (this note).** Completed; Phase 1 and later shipped.
2. **Phase 1 — one desktop platform** (Linux via the Dell builder, or Windows
   via the VM): download/pin a verified Eden build, add the launcher +
   `CompanionSystem`, and produce a launch smoke with a legal homebrew NRO:
   window focus, Exit Game, one save round-trip.
3. **Phase 2 — the second desktop platform**, reusing the same abstraction.
4. **Phase 3 — Android**: Eden ships an Android app, not an embeddable library,
   so this needs a companion APK + intent bridge (the Azahar-companion pattern).
   Only after Phase 1 evidence.
5. **Web**: out of scope — there is no browser Switch path.

## 6. Acceptance for Phase 1 (what will be claimed)

- `CompanionSystem.detect()` reports the pinned Eden version and commit.
- A legal homebrew NRO launches, receives focus, and exits cleanly through
  AN3's Exit Game.
- One save round-trip via the companion's own save-state path.
- No keys/firmware/commercial ROM in the bundle or artifact; catalog and
  notices updated; version bumped for the packaged artifact that changes.

Everything else stays `UNVERIFIED`.

## 7. Open questions for the owner

1. Approve Eden as the first companion core and Phase 1's platform (Linux or
   Windows)?
2. Confirm the companion is distributed **launched, not linked** (required for
   the GPL boundary above).
3. Any restriction on which legal homebrew NRO is used for Phase 1 evidence?
