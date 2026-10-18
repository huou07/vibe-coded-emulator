# Checkpoint — Native Linux journey

Updated: 2026-10-18 (worker `dsh-worker` on the Debian x86_64 host). This is the
durable task record for the **installed/native** product leg. It separates
source-tree native runtime evidence from packaged-shell and cross-platform
acceptance, and it is the only native tracker; do not open a second one.

Evidence vocabulary is the repository's: `GOOD` means the listed live check on
this host is current, `UNVERIFIED` means the implementation exists but the
required live check has not run, and `BLOCKED` names a check that cannot run
here at all. A source-tree runtime result is never packaged acceptance.

`deploy/shadow/` is owner-only (mode 700), so `git status` prints
`Permission denied` for it on this host. Those lines are not changes.

## Status

| Milestone | Status |
| --- | --- |
| Vendored Linux gameplay runtime (ELF, cores, manifest, licenses) | `GOOD` — vendored 2026-10-17, integrity-verified SHA-256 `94a5e701…b076e6c` |
| `an3ctl` native control-plane journey (status / baseline / diff) | `GOOD` — real runs, RG-154 |
| Deterministic frame diff detects a frame change | `GOOD` — 120-vs-120 identical, 1-vs-120 differs by 30241 px |
| State save → load round trip through the control plane | `GOOD` — `stateSaved`/`stateLoaded` true, 528448-byte state file |
| Input-sequence dispatch (`--seq`) | `GOOD` for dispatch — 60 frames, 60 core frames |
| Reproducible lawful fixture with no bundled ROM | `GOOD` — `tools/make-synthetic-gba-fixture.py`, idempotent |
| Bundled web runtime (GBA/NDS/3DS EmulatorJS payload) | `GOOD` — all 22 locked assets resolve; the 9 repaired-Azahar `latest/data-v2` files are **tracked in-tree** and match `shared/web-runtime-lock.json` byte for byte (`tools/verify-project.sh`, `tests/test_linux_native_runtime.py`) |
| Linux DEB build inputs (disk preflight, core pins, native player compile, runtime bundle) | `GOOD` — the build now reaches the Rust/Tauri stage and finishes |
| **Linux DEB package (Tauri shell)** | `GOOD` — built from clean HEAD `2f27cbd`; staging artifact `vibecodedemulator-3.2.5-linux-amd64.deb` (git-ignored staging output of `native-offline/releases/`), 46,115,818 bytes, SHA-256 `9cde017b…f4b4` |
| Interactive packaged journey: library, import, player launch | `GOOD` for the automation E2E build (same shell + test-only `ui-control` bridge); the distribution binary launches and renders the library |
| Packaged quick save (slot 1) | `GOOD` — 528448-byte `…slot1.state` written by the packaged player, byte-deterministic while paused |
| Packaged quick load (slot 1) | `GOOD` — a save→advance→load→re-save round trip reproduces the saved bytes exactly |
| **Packaged Exit Game (Esc / menu → return to library)** | **BROKEN** — the player's windows are destroyed and the loop stops, but the process does not exit (see below) |
| NDS / 3DS native journey | `UNVERIFIED` — only GBA exercised on this host |
| Visual/input/audio correctness of gameplay | `UNVERIFIED` — the synthetic stub renders an animated counter, not a game; this host has no sound device and the GL window is not capturable (see below) |
| Gameplay performance (frame pacing, latency, thermals) | `UNVERIFIED` — see the audit in `docs/evidence/linux-runtime-2026-10/README.md` |
| Hosted Android arm64 build lane | `GOOD` — `.github/workflows/native-build.yml` green on `ubuntu-24.04` at every revision listed below; the lane is dispatched for each revision of this branch and `tools/record-hosted-evidence.sh` records the run for the revision that carries this file |
| Android device / instrumentation / gameplay acceptance | `UNVERIFIED` — no SDK, NDK, `adb`, emulator or device on this host; the hosted lane is a build lane only |
| macOS / Windows native builds | `UNVERIFIED` here — hosted CI and dedicated builders only |

## 1. The Linux DEB builds from the tree — the "owner-seeded runtime" was a wiring gap

The previous session recorded the DEB as `BLOCKED` because the repaired Azahar
`latest/data-v2` runtime was "not available locally (owner-seeded)". That was
true of the *packager*, not of the repository: the nine pinned files are already
tracked at HEAD under
`native-offline/src-tauri/gen/android/app/src/main/assets/emulatorjs/latest/data-v2/`
and every one of them matches `native-offline/shared/web-runtime-lock.json`:

```sh
# all 22 locked assets, against the tracked vendored copy and against the
# repository's own published v3.6.8 Android APK: 22/22 match, 0 differ
```

`prepare-web.mjs` consulted only the frozen dependency cache and the network, so
a fresh checkout reported the runtime as missing while shipping every byte of
it. The fix (commit `cfe6a6c`) reads the vendored copy before the network. The
lock assertion is unchanged and still decides, so a drifted vendored file is
rejected exactly like a downloaded one; a fresh checkout now needs no seeded
source and no pre-populated cache for `latest/data-v2`:

```sh
# network origin deliberately unreachable, data-v2 cache entries removed,
# require-cache asserted on: the nine vendored files supply the run
AN3_REQUIRE_DEPENDENCY_CACHE=1 AN3_OFFLINE_RUNTIME_SOURCE=http://127.0.0.1:9/emulatorjs \
  npm run prepare-web      # exit 0; dist verified 22/22 against the lock
```

The build then ran to completion on this host:

```sh
CARGO_HOME=$PWD/work/cargo-home bash native-offline/scripts/build-linux-staging.sh deb
```

Observed (`work/deb-build3.log`, HEAD `2f27cbd2418f556cf140cf002a9b908f9754505a`):

```text
DISK_PREFLIGHT=PASS task=Linux deb staging package available=… reserve=25GiB.
LINUX_GBA_NDS_LIBRETRO_REUSE=…/native-offline/vendor/libretro/linux-x86_64 (pinned cores already verified; no download)
AZAHAR_DESKTOP=VERIFIED linux-x86_64 9e00fb4249a9eacad5ade873e6bb6ae7ece22508e0ec0a841c758f4a53f87903
LINUX_NATIVE_RUNTIME=VERIFIED an3-offline-native 94a5e701bf97a5363c27736221ca48f7e7c6a9a6c13e9275cf7503195b076e6c
INPUT_ACTIONS=generated buttons=12 utility=4 sectors=8
NATIVE_SETTINGS_SCHEMA=generated emulation gba=17 nds=73 3ds=32 switch=0
LINUX_DEB=/…/native-offline/releases/vibecodedemulator-3.2.5-linux-amd64.deb
```

Artifact identity (the sha256 sidecar verifies):

| Field | Value |
| --- | --- |
| Path | staging output `native-offline/releases/` + `vibecodedemulator-3.2.5-linux-amd64.deb` (never committed; `.gitignore` excludes it) |
| Size | 46,115,818 bytes |
| SHA-256 | `9cde017b1cc323033e53cfb9035a635ac45693010bfc9027387f14cb8201f4b4` |
| Control | `Package: vibe-coded-emulator`, `Version: 3.2.5`, `Architecture: amd64`, `Installed-Size: 95772`, `Depends: libwebkit2gtk-4.1-0, libgtk-3-0, libsdl2-2.0-0, libvulkan1, libgl1, libasound2` |
| Built from | clean HEAD `2f27cbd2418f556cf140cf002a9b908f9754505a`, working tree clean |
| Driver | `CARGO_HOME=<repo>/work/cargo-home cargo 1.98.0`, `node 24.21.0`, Tauri CLI 2.11.4 |

The packaged binary carries the repaired runtime — the DEB's
`usr/bin/an3-offline-native` contains
`emulatorjs/latest/data-v2/cores/azahar-thread-wasm.data`, so the 3DS payload is
inside the installed product rather than fetched at runtime.

Two environment facts, not product defects, are needed to run it here: this host
has **no PCM audio device** (`/dev/snd` holds only `seq` and `timer`, root-only),
so the shell is started with `SDL_AUDIODRIVER=dummy`; and there is no display, so
it runs under `Xvfb :98` with `LIBGL_ALWAYS_SOFTWARE=1`.

```sh
dpkg-deb -x native-offline/releases/vibecodedemulator-3.2.5-linux-amd64.deb work/dist-deb
HOME=work/smoke-home DISPLAY=:98 Xvfb :98 -screen 0 1280x900x24 &
DISPLAY=:98 SDL_AUDIODRIVER=dummy ./work/dist-deb/usr/bin/an3-offline-native
# the shell stayed up and mapped a 1280x820 "VibeCodedEmulator" window;
# work/dist-shell-library.png (34586 bytes, sha256 1eed0fc3…d2767cca)
# is byte-identical to the capture from the pre-commit build
```

## 2. The interactive packaged journey

The distribution shell has no automation hook by design, so the journey ran
against the **automation E2E build** of the same shell — the same Tauri window,
the same bundled player, the same imported ROM storage — plus the documented
test-only cargo feature `ui-control` (a token-gated loopback bridge that
dispatches real DOM events on `data-testid` elements; `docs/agent-control-plane.md`).
Distribution builds do not compile it, and that was verified on the artifacts:

```sh
npm run tauri -- build --bundles deb --features ui-control
work/automation-e2e-3.2.5-amd64.deb  46115798 bytes
  sha256 acac2fe862e7e6c87f5a59785899fe1ecb5498553a1b6b3a847d866c415324b9
strings automation binary | grep -c an3-ui-control  -> 2
strings distribution binary | grep -c an3-ui-control -> 0
```

Launched with `AN3_UI_CONTROL_FILE=work/ui-control.json` and
`AN3_UI_TEST_ROM=work/fixtures/an3-synthetic-gba.gba` (which pre-answers the
native picker so the real import path and frontend handler run), under
`Xvfb :99`, `SDL_AUDIODRIVER=dummy`.

| Step | How it was driven | Real result |
| --- | --- | --- |
| Library | `GET /diag` | `ready=complete`, `title="Vibe Coded Emulator"`, `systems="gba,nds,3ds"`, `testids=19`, loopback `href=http://127.0.0.1:38471/` |
| (empty library) | `GET /tree` | `game-grid` text: `No games on this device. Use Add ROM to store one on this device.` |
| Import | `GET /click?testid=open-rom` | `{"clicked":true}`; `game-card` = `GAME BOY ADVANCE / an3 synthetic gba / 32 KB`, `game-launch` = `Play GBA native`, `native-status` state `stopped` |
| Fixture | `tools/make-synthetic-gba-fixture.py` | 32768 bytes, SHA-256 `94ca9e564f01d9871f84a831e7d28f6dc3ae8a0cf0b93d1bd7395b5a73ee6491` (no ROM, BIOS or game bytes) |
| Import persists | shell restarted, `GET /text?testid=game-grid` | the imported entry is still there from `…/an3-roms/2b47d129-…gba` |
| Player launch | `GET /click?testid=game-launch` | `native-status` state `running`, text `Native game window opened. Menu: F2 · Pad: F3 · Next Layout: F1`; real child `…/runtime/linux-x86_64/an3-offline-native --rom … --system gba --layout preserve --storage … --control-stdin`; three X windows mapped (shell 1280x820, game 1280x720, controls 849x620) |
| Quick save | `xdotool key F5` to the player window | `…/saves/native-libretro/states/…-169cedbbce5d599d.slot1.state`, 528448 bytes |
| Quick load | `xdotool key F9` after advancing | round trip below |

The player binds `F5`/`F9` to quick save/load slot 1 and `Esc` to close the menu
or quit (`native-offline/native-runtime/platform/linux/linux_runtime.cpp`). The
save/load verdict uses byte identity, and that is only meaningful if the
serializer is deterministic, so it was measured first — all with the emulator
paused so nothing advances between the compared saves:

```text
paused save A                 753/754… (A == B for two consecutive saves)
advance 6 s, pause, save C    C != A            state genuinely advances
load slot 1 (F9), save D      D == A            the saved state was restored
```

The first attempt at this produced `D == C`, which looked like a failed load; it
was a defect in the probe, not the product — `F5` always writes slot 1, so the
"load" was loading the state that was already current. Correcting the probe gave
`D == A`. Corroboration: the player's own `runtime.log` records
`Savestate: Loading savedata` / `Savestate: Loading RTC` groups for the loads.

### Exit Game is broken (new finding, not fixed here)

Pressing `Esc` in the packaged player destroys both of its windows and stops
frame execution, but **the process never exits**:

```text
after Esc:   game window 6291458 and controls window 10485763 destroyed (xwininfo: no such window)
             pid 3791280 alive, STAT Sl, 3 threads, VmRSS 112648 kB
             CPU ticks over 6 s: 0            (the render loop really did stop)
             no autosave.state written        (auto_save.on_exit is off)
threads:     an3-offline-nat (main), an3-offline-nat (detached --control-stdin reader),
             [pango] fontcon
```

The Tauri shell only reaps it when the user starts another game: `start()` calls
`stop()`, which writes `QUIT` and kills after 5 s. Verified — a second
`game-launch` click removed the stuck pid and started pid 3800228 with
`native-status` back to `running`. So the leak is bounded but real: a stale
~112 MB process per session lingers until the next launch or app exit. This is a
native-runtime teardown defect, not a UI defect. Changing it means changing
`linux_runtime.cpp` and re-vendoring the pinned player with its recorded SHA-256,
which `docs/QUALITY.md` treats as its own reviewed change; it was **not** done
here.

### What the packaged journey did not establish

- **No visual or audio review.** The GL/Vulkan game window does not appear in X11
  screen captures — `scrot -w` of the game window is 99.99 % black with 4
  distinct colours, and sampled frames 3 s apart differ in 7 of 131658 pixels.
  The captures are kept (`work/journey-fullscreen-running.png`,
  `work/player-frame-a.png`, `work/player-frame-b.png`) but a human or a working
  image tool must read them; this worker's image tool could not read files under
  the worker home directory, so **no frame content was visually verified**.
- **No real audio.** There is no sound hardware; `SDL_AUDIODRIVER=dummy` only
  lets the player initialise. Audio correctness, quality and underruns are
  `UNVERIFIED`.
- **`AN3_UI_TEST_ROM` pre-answers the picker.** The real GTK file dialog was
  never driven; the import *path* is real, the *dialog* is not.
- **Only GBA.** No NDS or 3DS fixture exists, so nothing is generalised.
- **It was extracted, not installed.** `dpkg -i` needs root, which this worker
  does not have, so the package was unpacked with `dpkg-deb -x` and run from the
  layout it installs (`usr/bin` binary, `usr/lib/VibeCodedEmulator` runtime). The
  packaged binary and the bundled player both resolve every shared library
  (`ldd … | grep -c 'not found'` is 0 for each), but `dpkg -i`, the `Depends:`
  resolution against a real package database, and the desktop-entry launch are
  `UNVERIFIED`.

## 3. Android: the recorded premise did not hold

The 2026-10-18 instruction recorded `.github/workflows/native-build.yml` and
`.github/workflows/platform-verification.yml` as "the only Android authority
here". Rechecked against `ab57ac4`:

- `.github/workflows/` at HEAD contains **only** `verify.yml`, which states that
  native packages are not built there.
- `native-build.yml` exists on `origin/main`, but that is an **unrelated
  public-release history** (the 3.3.x line, `git merge-base` empty) whose
  workflow calls a `fetch-android-libretro.mjs` helper that this branch does not
  contain.
- `platform-verification.yml` has **never existed in any ref**
  (`git log --all --name-only -- '.github/workflows/*'` lists only `ci.yml`,
  `native-build.yml`, `native-release.yml`, `verify.yml`,
  `windows-runtime-smoke.yml`).
- `tools/release-train.sh` deliberately blocks the Android staging candidate
  anywhere but macOS: `ANDROID_APK=BLOCKED (current Android staging builder is
  macOS)`, exit 3.

That guard was left alone.  The actual hosted failure of the only Android run
this repository has (run `39018396692`, PR from `public/source-20261017`) was:

```text
scripts/build-android-runtime.sh: line 10:
/usr/local/lib/android/sdk/ndk/26.3.11579264/toolchains/llvm/prebuilt/darwin-x86_64/bin/aarch64-linux-android26-clang++:
No such file or directory
ANDROID_APK=FAILED (builder returned an error)
```

`build-android-runtime.sh` hardcoded the macOS NDK host toolchain on a job that
ran on `ubuntu-24.04`. Commit `cfe6a6c` selects the NDK prebuilt host from
`uname` (`linux-x86_64` / `darwin-x86_64` / `windows-x86_64`), names the missing
compiler instead of failing as a shell error, resolves the SDK on Linux as well
as macOS, and prefers `sha256sum` where `shasum` is absent.

A hosted build lane was then added (`.github/workflows/native-build.yml`): one
`ubuntu-24.04` job that installs the pinned NDK 26.3.11579264 and the
`aarch64-linux-android` Rust target, builds the runtime through
`native-offline/scripts/build-android-staging.sh` — the same builder the release
train calls — checksums the APK and uploads it. It is explicitly labelled a build
lane with no device acceptance, and it does not invoke `release-train.sh`, so the
release train's macOS-only Android *candidate* guard is untouched.

| Run | Revision | Event | Job | Verdict |
| --- | --- | --- | --- | --- |
| `39064964493` | `cfe6a6c` | push | Android arm64 APK (build lane, no device acceptance) | success |
| `39065560904` | `2f27cbd` | workflow_dispatch | Android arm64 APK (build lane, no device acceptance) | success |
| `39066997580` | `7ef6352` | workflow_dispatch | Android arm64 APK (build lane, no device acceptance) | success |
| `39065425857` | `2f27cbd` | push | verify: project-verify, browser-runtime, publication-gate, release-gate | success, all four |
| `39064964363` | `cfe6a6c` | push | verify: project-verify, browser-runtime, publication-gate, release-gate | success, all four |
| `39066985469` | `7ef6352` | push | verify: project-verify, browser-runtime, publication-gate, release-gate | success, all four |

A docs-only commit does not re-trigger this lane (its `paths:` filter covers
`native-offline/**`, the workflow itself and the disk preflight), so each later
revision is dispatched with
`gh workflow run native-build.yml --ref feature/semantic-ui-inspection`. The APK
digest is not stable across runs even from identical native source — zip entries
carry build timestamps — so the recorded digests identify artifacts, not a
reproducible build:

| Revision | APK SHA-256 |
| --- | --- |
| `cfe6a6c` | `2a39f8f6cbde16d2343fd0697ab027aef98c65cf71efc139cff4ee310c15d92a` |
| `2f27cbd` | `0e7a6ada2a5f24e68d008133fa1692267c708749cfdf9be44a7fab960e0e441f` |
| `7ef6352` | `1d8d7f8c6f59173490767dcbcc033613fe7e899e34cffa77a59cfaff0fb5d469` |

Both Android runs selected the right toolchain, which is the line that used to
be hardcoded, and produced the same product package name:

```text
/usr/local/lib/android/sdk/ndk/26.3.11579264/toolchains/llvm/prebuilt/linux-x86_64/
ANDROID_STAGING_APK=releases/vibecodedemulator-3.2.5-android-arm64-staging.apk
ANDROID_STAGING_SHA256=0e7a6ada2a5f24e68d008133fa1692267c708749cfdf9be44a7fab960e0e441f
Source revision: 2f27cbd2418f556cf140cf002a9b908f9754505a
Device, instrumentation and gameplay acceptance: NOT RUN on this lane.
```

| Hosted Android artifact | Value |
| --- | --- |
| Name | `vibecodedemulator-3.2.5-android-arm64-staging.apk` |
| SHA-256 at `2f27cbd` (run `39065560904`) | `0e7a6ada2a5f24e68d008133fa1692267c708749cfdf9be44a7fab960e0e441f` |
| SHA-256 at `cfe6a6c` (run `39064964493`) | `2a39f8f6cbde16d2343fd0697ab027aef98c65cf71efc139cff4ee310c15d92a` |
| Uploaded artifact | `android-apk`, 49,348,596 bytes, id `12112809316` |
| Signing | shared Android Debug identity via `build.gradle.kts`; not a production signing identity |

`AN3_BUILD_ANDROID_TESTS`, the `:app:testArm64DebugUnitTest` step and the three
API-35 device-acceptance jobs from the other history's workflow are deliberately
**not** carried over: there is no `src-tauri/gen/android/app/src/test` tree at
this HEAD, and no device or emulator runs in this lane.

## Gaps found and fixed in this session

1. `prepare-web.mjs` never read the repaired `latest/data-v2` runtime the
   repository already tracks, which made a complete tree look like a missing
   upstream artifact. Fixed in `cfe6a6c`; guarded by
   `tests/test_linux_native_runtime.py::test_prepare_web_reads_the_vendored_runtime_before_reaching_the_network`
   and `::test_vendored_repaired_runtime_matches_the_frozen_lock`.
2. The Android builder assumed its host was macOS in three separate places (NDK
   host toolchain, default SDK path, `JAVA_HOME` fallback) and assumed `shasum`
   exists. Fixed in `cfe6a6c`; guarded by
   `tests/test_android_native_runtime.py::test_android_build_selects_the_ndk_host_toolchain_it_is_running_on`.
3. There was no hosted Android lane on this branch. Added in `cfe6a6c`; guarded
   by `tests/test_android_native_runtime.py::test_hosted_android_lane_builds_from_this_revision`.
4. `tools/build-public-snapshot.sh` copied `native-offline/src-tauri` — including
   the multi-gigabyte `target/` tree — before deleting `target/` again, so on
   this host's 7.7 GiB scratch mount the candidate build died with `cp: No space
   left on device` instead of evaluating its assertions. `target/` is now
   excluded at copy time (`2f27cbd`); the candidate builds in under a second with
   the same file list as before plus one test added since.
5. Every staging builder writes `<artifact>.sha256` next to an installer that
   `.gitignore` already excludes, so a documented build left the tree dirty.
   `native-offline/releases/*.sha256` is now ignored (`cfe6a6c`).
6. `tools/check-docs-refs.py` treats an ignored build-output path differently
   depending on whether the file is materialized: a backticked
   `native-offline/releases/<artifact>.deb` passes on a workstation that has
   built it (`git status --ignored` sees it) and fails on a clean checkout, which
   is how revision `7a83c6c` passed the local gate and failed hosted
   `project-verify` (`run 39066265462`, two findings, same artifact path). The
   tracker now names the staging file without treating it as a repository path.
   Anyone editing this file should validate with a clean clone, not the working
   tree.

## Next discriminating actions

1. Fix the packaged player's Exit Game teardown (`linux_runtime.cpp` does not
   return from the process after the render loop breaks) and re-vendor the
   pinned Linux player with its recorded SHA-256, as its own reviewed change.
   Reproduction is above: launch a game, press `Esc`, then check that the child
   pid disappears instead of lingering idle.
2. Read the retained packaged-shell captures by hand or with a working image
   tool; this worker could not, so library rendering, the player surface and the
   controls window remain visually `UNVERIFIED`.
3. Repeat the deterministic journey for NDS and 3DS once lawful synthetic
   fixtures exist for those cores. Do not generalise the GBA result.
4. Android device/instrumentation acceptance and macOS/Windows acceptance stay
   with their own hosted builders and devices; this branch has a green hosted
   *build* lane only, and that is all it claims.
