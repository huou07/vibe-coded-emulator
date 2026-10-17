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
| Linux DEB build inputs (disk preflight, core pins, native player compile, runtime bundle) | `GOOD` — the build now reaches `prepare-web`; see below |
| Linux DEB package (Tauri shell) | `BLOCKED` on this worker — the repaired Azahar `latest/data-v2` runtime is not available locally (owner-seeded) |
| NDS / 3DS native journey | `UNVERIFIED` — only GBA exercised on this host |
| Interactive packaged journey (library, import, player, Exit Game) in a Tauri shell | `UNVERIFIED` — the DEB build has not completed here |
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

## Packaged desktop shell (Tauri DEB) — real progress and the exact boundary

`cd native-offline && npm ci && npm run build:deb` was run on this host. It is
**not** blocked by the toolchain: `npm ci` installs the locked
`@tauri-apps/cli` 2.11.4, `npm run build -- --print-plan` selects `build:deb`,
and the disk preflight, core verification, native player compile and runtime
bundle all succeed:

```text
DISK_PREFLIGHT=PASS task=Linux deb staging package available=150GiB reserve=25GiB.
LINUX_GBA_NDS_LIBRETRO_REUSE=<repo>/native-offline/vendor/libretro/linux-x86_64 (pinned cores already verified; no download)
AZAHAR_DESKTOP=VERIFIED linux-x86_64 9e00fb4249a9eacad5ade873e6bb6ae7ece22508e0ec0a841c758f4a53f87903
LINUX_NATIVE_RUNTIME=VERIFIED an3-offline-native 94a5e701bf97a5363c27736221ca48f7e7c6a9a6c13e9275cf7503195b076e6c
INPUT_ACTIONS=generated buttons=12 utility=4 sectors=8
NATIVE_SETTINGS_SCHEMA=generated emulation gba=17 nds=73 3ds=32 switch=0
```

Two gaps were observed, in order:

1. **Core-pin drift (fixed here).** The build first died in
   `fetch-linux-gba-nds-libretro.mjs`: the script pinned `nightly-20261007`
   archive/core hashes while the repository ships and bundles the
   `nightly-20260911` cores, and the buildbot URL is a rolling `latest` target,
   so the pinned archive can never be re-fetched. The pins now describe the bytes
   the repository actually ships (identical to
   `vendor/libretro/linux-x86_64/manifest.json` and to the runtime bundle), the
   reuse path reports itself, and
   `tests/test_linux_native_runtime.py::test_linux_core_pins_describe_the_cores_the_repository_ships`
   fails if they drift again. Verified: running both fetchers in build order
   round-trips the tracked manifest byte-for-byte with no download.
2. **Missing EmulatorJS runtime source (owner boundary).** `prepare-web` then
   stops on the first `latest/data-v2/loader.js`: those assets are the repaired
   Azahar runtime, published only by a seeded local AN3 runtime source. On this
   worker none is available — they are not in Git, the frozen dependency cache
   holds only the 13 standard CDN files, `/srv/an3-arcade-staging/emulatorjs-cache`
   is unreadable to this UID, `an3-arcade-staging.service` is `inactive` and
   cannot be started without root, and reading the production cache is outside
   this task's mandate. The failure now names that boundary and the two remedies
   instead of a bare `TypeError: fetch failed`.

Owner action to finish this lane (one of):

- start/reactivate the staging service so `http://127.0.0.1:8092/emulatorjs`
  serves the seeded `latest/data-v2` runtime, or
- set `AN3_OFFLINE_RUNTIME_SOURCE` to another seeded runtime source, or
- provide a complete frozen dependency cache for `AN3_DEPENDENCY_CACHE`.

Then `npm run build:deb` can finish, the DEB can be extracted with
`dpkg-deb -x` for packaged-artifact inspection, and the packaged interactive
journey can be attempted. Until then the packaged rows stay `UNVERIFIED`; the
runtime evidence in RG-154 is a source-tree result and is not packaged acceptance.

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

1. Unblock the packaged desktop shell by providing the seeded EmulatorJS runtime
   source (see the boundary section above): start staging on `:8092`, point
   `AN3_OFFLINE_RUNTIME_SOURCE` at another seeded source, or supply a complete
   frozen dependency cache. Everything before that step already passes on this
   host, including `npm ci` and the Tauri CLI (2.11.4); WebKitGTK 4.1,
   JavaScriptCore, libsoup 3, SDL2, Vulkan and GTK development packages are
   present.
2. Then finish `npm run build:deb`, record the DEB path and SHA-256, extract it
   with `dpkg-deb -x`, and exercise the packaged journey in the installed shell
   with the same synthetic fixture: offline library → import a ROM → player
   launch → input → save/load → Exit Game → reopen. Use `an3ctl` for any
   structured inspection and record real backend state; packaged UI evidence is
   required before any of those rows become `GOOD`.
3. Repeat the deterministic journey for NDS and 3DS once lawful synthetic
   fixtures exist for those cores. Do not generalise the GBA result.
4. Android/macOS/Windows acceptance stays on their own hosted builders and
   devices; this host has no Android SDK, emulator, or macOS/Windows toolchain.
