# Checkpoint — Native Linux journey

Updated: 2026-10-17 (worker `dsh-worker` on the Debian x86_64 host). This is the
durable task record for the **installed/native** product leg. It separates
source-tree native runtime evidence from packaged-shell and cross-platform
acceptance, and it is the only native tracker; do not open a second one.

Evidence vocabulary is the repository's: `GOOD` means the listed live check on
this host is current, `UNVERIFIED` means the implementation exists but the
required live check has not run. A source-tree runtime result is never packaged
acceptance.

## Status

| Milestone | Status |
| --- | --- |
| Vendored Linux gameplay runtime (ELF, cores, manifest, licenses) | `GOOD` — vendored 2026-10-17, integrity-verified SHA-256 `94a5e701…b076e6c` |
| `an3ctl` native control-plane journey (status / baseline / diff) | `GOOD` — real runs, RG-154 |
| Deterministic frame diff detects a frame change | `GOOD` — 120-vs-120 identical, 1-vs-120 differs by 30241 px |
| State save → load round trip through the control plane | `GOOD` — `stateSaved`/`stateLoaded` true, 528448-byte state file |
| Input-sequence dispatch (`--seq`) | `GOOD` for dispatch — 60 frames, 60 core frames |
| Reproducible lawful fixture with no bundled ROM | `GOOD` — `tools/make-synthetic-gba-fixture.py`, idempotent |
| NDS / 3DS native journey | `UNVERIFIED` — only GBA exercised on this host |
| Interactive packaged journey (library, import, player, Exit Game) in a Tauri shell | `UNVERIFIED` — the DEB build has not run here |
| Visual/input/audio correctness of gameplay | `UNVERIFIED` — the synthetic stub renders one animated pixel, not a game |
| Gameplay performance (frame pacing, latency, thermals) | `UNVERIFIED` — see the audit in `docs/evidence/linux-runtime-2026-10/README.md` |
| Android / macOS / Windows native builds | `UNVERIFIED` here — hosted CI and dedicated builders only |

## What was actually run (2026-10-17)

Fixture (generated, not committed; no ROM, BIOS, logo or game bytes):

```sh
python3 tools/make-synthetic-gba-fixture.py
# SYNTHETIC_GBA=work/fixtures/an3-synthetic-gba.gba bytes=32768
#   sha256=94ca9e564f01d9871f84a831e7d28f6dc3ae8a0cf0b93d1bd7395b5a73ee6491
```

Deterministic native journey through the shared control plane:

```sh
FIX=work/fixtures/an3-synthetic-gba.gba
tools/an3ctl/bin/an3ctl emulator status --rom $FIX --system gba --frames 120 --json
tools/an3ctl/bin/an3ctl emulator baseline --name native-checkpoint --rom $FIX --system gba --frames 120 --json
tools/an3ctl/bin/an3ctl emulator diff --name native-checkpoint --rom $FIX --system gba --frames 120 --json
tools/an3ctl/bin/an3ctl emulator diff --name native-checkpoint --rom $FIX --system gba --frames 1 --json
tools/an3ctl/bin/an3ctl emulator state --rom $FIX --system gba --path <state> --save --frames 60 --json
tools/an3ctl/bin/an3ctl emulator state --rom $FIX --system gba --path <state> --load --frames 1 --json
tools/an3ctl/bin/an3ctl emulator input --rom $FIX --system gba --seq 'A@0-30;Start@40-45' --frames 60 --json
```

Observed:

| Command | Result |
| --- | --- |
| `emulator status --frames 120` | `running:true`, `frames:120`, `coreFrames:120`, `width:240`, `height:160`, `fps:59.7275`, core `mGBA 0.11-219-e31759b` |
| `baseline --frames 120` | `rawHash` 64-hex, `pngHash` 64-hex, 153600 raw bytes, 153838 PNG bytes |
| `diff --frames 120` vs that baseline | `match:true`, `differentPixels:0`, `maxChannelError:0` |
| `diff --frames 1` vs that baseline | `match:false`, `differentPixels:30241`, `differentPercent:78.7526`, `maxChannelError:255` |
| `state --save --frames 60` | `stateSaved:true`, state file 528448 bytes under the run's own state dir |
| `state --load --frames 1` | `stateLoaded:true` |
| `input --seq 'A@0-30;Start@40-45' --frames 60` | `frames:60`, `coreFrames:60`, `width:240`, `height:160` |

The self-test lane that exercises this without a browser screenshot:

```sh
AN3_PLAYWRIGHT_BROWSER=chromium \
AN3_PLAYER="$PWD/native-offline/vendor/runtime/linux-x86_64/an3-offline-native" \
node --test tests/an3ctl.test.mjs
# 4 pass / 0 fail / 1 skip (no Android device/emulator connected)
```

Environment facts for these runs: `native-offline/vendor/runtime/linux-x86_64/`
holds the ELF player plus `libretro/{mgba,melondsds,azahar}_libretro.so` and the
integrity manifest; the player resolves a core as
`$AN3_OFFLINE_LIBDIR/libretro/<core>.so`, so the adapter passes the runtime root.
Native saves from a control-plane run land under
`<stateDir>/native-storage/`, never in the caller's profile.

## Gaps found and fixed in this session

1. `tools/an3ctl/adapters/emulator.mjs` had an in-flight edit that called an
   undefined `inferLibdir`, so `--player` / `AN3_PLAYER` threw a `ReferenceError`
   instead of running. It is now a real method and the module parses and runs.
2. The adapter pointed `AN3_OFFLINE_LIBDIR` at a path the player then appended
   `libretro/` to, so the vendored runtime could not find its core. The libdir is
   now the runtime root that actually contains `libretro/`.
3. The fixture the self-test named was a machine-specific absolute path in the
   owner's home directory that does not exist on a worker host, and the run was
   never reproducible from the repository. The self-test now defaults to a
   fixture the repository generates from its own source, and generates it on
   demand when it is absent.
4. The earlier ad-hoc fixture was a static self-loop: frame 1 and frame 120
   rendered identical bytes, so the `emulator diff` "detects a frame change"
   assertion was vacuous. The generator now emits an ARM stub that enables mode 3
   and writes an advancing counter into the frame buffer, which is deterministic
   per frame count and genuinely different across frame counts.
5. The control plane writes native saves into its own state dir by default, so a
   journey never writes into the caller's real profile.

None of these were product-page defects; they were missing native-lane wiring,
which is why the native leg read as "parked" while the runtime was already built.

## Next discriminating actions

1. Build the packaged desktop shell on this host: `cd native-offline && npm ci`,
   then `npm run build:deb` (routing/first checks: `npm run build -- --print-plan`).
   Record the DEB path, SHA-256 and whether the Tauri shell, not just the runtime,
   launches. `@tauri-apps/cli` is currently the missing piece; the WebKitGTK 4.1,
   JavaScriptCore, libsoup 3, SDL2, Vulkan and GTK development packages are
   present.
2. Exercise the packaged journey in the installed shell with the same synthetic
   fixture: offline library → import a ROM → player launch → input → save/load →
   Exit Game → reopen. Use `an3ctl` for any structured inspection and record real
   backend state; packaged UI evidence is required before any of those rows become
   `GOOD`.
3. Repeat the deterministic journey for NDS and 3DS once lawful synthetic
   fixtures exist for those cores. Do not generalise the GBA result.
4. Android/macOS/Windows acceptance stays on their own hosted builders and
   devices; this host has no Android SDK, emulator, or macOS/Windows toolchain.
