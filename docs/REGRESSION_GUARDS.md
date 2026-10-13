# Vibe Coded Emulator — regression guards

Status: **current.** This is the durable cross-platform guard ledger.

How to read it:

- The **numbered `RG-###` guards** are live. They state why a behaviour is
  protected, what owns it, and what evidence is allowed to call it `GOOD`.
  Newest guards are added at the top; the ledger is never rewritten.
- The **dated `## Current authority — ...` narrative sections** are the
  historical acceptance record for the release train they are named after.
  They are kept because they explain *why* a guard exists. Read them as history,
  not as the current deployment state — the current state is the deployed
  service, `native-offline/releases/catalog.json`, and Git.
- Per-run capture reports are **not** stored in this repository. A section that
  says so is recording that the live evidence existed, not inviting you to open
  a file. New evidence worth keeping goes under `docs/evidence/`.

Status vocabulary, used literally throughout:

| Word | Meaning |
| --- | --- |
| `GOOD` | The listed automated and live runtime evidence is current. |
| `UNVERIFIED` | The implementation exists; the required live check is absent. |
| `KNOWN LIMITATION` | Reproduced and not claimed fixed. |
| `PENDING` | A targeted fix awaits the next staging smoke. |

Source contracts are necessary but never sufficient for interactive behaviour.
A feature is not `GOOD` until its matching behavioural and live acceptance
checks pass.

## Phone controller utility naming — 2026-10-13

- **Phone utility actions (Quick Save, Speed, Menu) were silently dropped
  end to end on the staging path.** The phone page sends canonical ids
  (`static/controller.js` `sendUtility` maps through
  `AN3InputActions.utilityWireToAction`, so `u` carries e.g. `QUICK_SAVE`),
  but `netcode.ControllerState.from_wire` only accepted wire spellings
  (`quick_save`) and discarded canonical ids without queueing anything.
  Conversely, a wire-spelled frame queued `{"action": "quick_save"}`, which
  no host sink can dispatch: the browser `AN3ControllerUtility` dispatcher,
  the desktop `azahar::apply_controller_utility` match, and the Android
  overlay all key on canonical ids, so the entry ended as `unsupported`
  (`quick_save is unavailable on this host`). The existing suites stayed
  green because they posted wire names and asserted queueing only, never
  dispatch. Fix: `netcode.py` loads the canonical ids and the
  wire→canonical map from `native-offline/shared/input-actions-schema.json`
  (`CONTROLLER_UTILITY_CANONICAL`, `UTILITY_WIRE_TO_CANONICAL`) and
  `from_wire` normalizes both spellings to canonical on ingress, matching
  the field's own documented contract ("One-shot canonical utility
  action"). Unknown names remain ignored.
- Automated: `tests.test_input_actions` (ingress normalization both
  spellings, canonical queue contents, ack/disconnect semantics),
  `tests.test_multiplayer_api` (HTTP-level canonical queueing),
  `tests.test_phone_controller_hosts`
  (`test_netcode_queues_canonical_names_every_host_dispatches`), plus the
  unchanged browser dispatcher suite. Status: **GOOD** at the automated
  level. Live phone-to-host utility execution on packaged apps remains
  **UNVERIFIED** (no device harness on this host).
- Owners: `netcode.py`; consumers unchanged (`static/player.js`,
  `native-offline/src-tauri/src/controller_host.rs`,
  `.../azahar.rs`, `ControllerClient.kt`, `NativeGameOverlay.kt`).
  Blast: Phone Controller one-shot actions on every host.


## Local package builds preserve a 25 GiB disk reserve

The macOS, Windows, Linux DEB/Flatpak, and Android package entrypoints check free space
before downloading dependencies or generating build output. Coordinated release
freeze/build operations use the same check before creating archives or run roots.
Below 40 GiB they warn; below the 25 GiB reserve they stop with exit 75 and
direct the operator to CI or known disposable build outputs. The guard never
deletes data. After a successful coordinated matrix, the exact packages and
source manifest remain, while its extracted macOS build copy is removed; failed
run roots remain available for diagnosis.

- Automated: `tests.test_disk_preflight` covers pass, warning, stop, and
  invalid-threshold behavior with a stubbed `df` result;
  `tests.test_native_staging_contract` covers release-train preflight order
  and successful scratch cleanup.
- Entry points: `native-offline/package.json` (`build`, `build:deb`, `android:build`), `native-offline/scripts/build-android-staging.sh`, `native-offline/scripts/build-linux-staging.sh`, and `native-offline/scripts/build-windows-staging.ps1`.
- Initial runtime disk snapshot on 2026-10-09: 143 GiB available. Later
  follow-up measured 135 GiB; no VCE build loop or emulator was active in that
  check. Windows preflight runtime and disposable Android AVD lifecycle remain
  **UNVERIFIED**.

## Parallelism history and current guard

The former `an3-parallel-orchestrator` and its autonomous supervisor are retired
and deleted. The old RG-133/RG-134 orchestration results are archival evidence
only; do not restore, invoke, or extend that workflow.

The current cross-agent guard is the project-agnostic global skill:

```bash
python3 "$HOME/.agents/skills/parallelism/scripts/parallelism_selftest.py"
```

It covers the v1.1/v1.2 deterministic behavior plus v1.3 discovery,
`project.json` validation, portable fixtures, zero-helper behavior and the
optional host-adapter boundary. Parallelism remains Master-owned; Codex native
helpers inherit the Master model/reasoning and are used only when `decide`
recommends independent work.

## Android 3DS Vulkan framebuffer color — 2026-09-18

- RG-124: The Android 3DS Vulkan presenter must never select an `_SRGB` swapchain color format. `native-offline/native-runtime/video/vulkan/vulkan_backend.cpp::create_swapchain_resources` still matched `_SRGB` formats in both the preferred list and the standard-space fallback (the 1.0.1 fix only stopped the wide-gamut `formats.front()` default). The Azahar core hands the frontend display-referred, sRGB-encoded UNORM frames, so an `_SRGB` surface makes the presentation blit apply a second linear-to-sRGB encode and desaturates the 3DS framebuffer. MoltenVK (which only advertises `B8G8R8A8_UNORM`) and the AVD's emulated GPU offer UNORM first and never reproduced it. Fix: an `is_srgb_format()` guard on the preferred list and the fallback scan, a one-time `AN3VK` logcat line of the advertised/selected surface format, and a `device_details()` warning for an sRGB/non-standard swapchain. Device evidence (Redmi 25057RN09G, Android 16, Adreno 619 driver 0762.40): the Vulkan surface advertises `R8G8B8A8_UNORM` (format 37) first and the presenter selected it with `VK_COLOR_SPACE_SRGB_NONLINEAR_KHR` before and after the change, so the `_SRGB` path was not reachable on this unit. Runtime status: 3DS rendered correctly on the packaged 2.3.1 APK (`db5a0a6c05c9123ecf91999b93ea69e535c2e2f63442d2e61bd128f3a94d7a65`) on both the Auto OpenGL ES (`core=57 present=57`) and forced Vulkan (`core=55 present=55`) paths with no new Vulkan errors; the reported intermittent desaturation itself remains **UNVERIFIED** on hardware because it did not reproduce in 60 s recordings on either path. Source checks: `tests.test_android_native_runtime`, `tests.test_native_renderer_contract`, `tests.test_native_regression_guards`.

## Android/mobile build — RG-128, 2026-09-18

- RG-128: **Every Tauri command in `generate_handler!` must exist on every
  target, and each command name must have exactly one `#[tauri::command]`
  definition.** The Switch commit defined `switch_companion_launch_rom` as
  `#[cfg(not(mobile))]` but registered it unconditionally, so an Android/mobile
  build failed with `cannot find macro __cmd__switch_companion_launch_rom`.
  Fixed with a single function whose body is cfg-switched — a
  `#[cfg(not(mobile))] return switch_companion::launch_rom(...)` and a
  `#[cfg(mobile)]` branch returning
  `Err("Nintendo Switch is not supported on this platform.")`. It must be one
  definition, not two cfg'd stubs, because
  `tests/test_offline_consolidation.py::test_native_offline_shell_is_isolated_from_web_routes_and_release_secrets`
  requires the `#[tauri::command]` name set to equal the `build.rs`
  `AppManifest` command list (a duplicate definition fails that parity check).
  The tracked `gen/schemas/android-schema.json` and `mobile-schema.json` must
  carry the same `allow-switch-companion-*` / `allow-ui-control-result`
  permissions as the desktop schema so the mobile ACL matches the runtime
  command exposure. Validation: `cargo check --target aarch64-linux-android
  --lib` finished clean (was 2 errors) and the parity test passes.

## Native save sync ROM preflight — RG-129, 2026-10-08

- RG-129: **Native Sync save must reject a missing compatible peer before
  hashing the ROM, and must show status while a connected-peer sync hashes and
  transfers saves.** Previously `syncGame()` read and SHA-256 hashed the entire
  ROM before the transfer engine checked peer authorization; tapping Sync save
  without a connected peer could leave the button disabled for the duration of
  a multi-gigabyte read. The check now runs first, and the button/status text
  identifies connection check, ROM identity verification, and save transfer.
  The native hash remains on Tauri's blocking worker. Owners:
  `native-offline/web/native-sync.js`, `native-offline/web/native-app.js`.
  Blast: native Android/desktop save sync startup and user feedback.
- Automated validation: `node --test tests/native_sync.test.mjs
  tests/sync_transfer.test.mjs` passes 22/22, including a no-peer assertion
  that `native_sync_game_identity` is never invoked and a connected-peer
  progress-order assertion. The same suite now checks that the Android
  packaged `native-app.js` and `native-sync.js` exactly match their source
  files. Both edited JavaScript files pass `node --check`.
- Live acceptance: install the 3.2.1 package, verify no-peer rejection with a
  large ROM, then connect a peer and verify the identity/transfer messages,
  save comparison, and persisted result. **UNVERIFIED**: no Android device or
  packaged app was available in this work session; Node evidence does not
  establish packaged runtime behavior.

## Public snapshot cache exclusion — RG-130, 2026-10-08

- RG-130: **A public source snapshot must exclude Python `__pycache__` bytecode.**
  Compiled test files can embed a developer's absolute source path; the public
  snapshot builder copied `tests/` recursively and its personal-data gate
  correctly rejected the candidate. `tools/build-public-snapshot.sh` now
  removes `__pycache__` directories from the candidate. Validation: a fresh
  snapshot contains no `__pycache__`; `tools/publication-check.sh` reports
  gitleaks 0 findings, clean personal-data/infra patterns, and `PASS`.
  Owners: `tools/build-public-snapshot.sh`, public source publication.
  Blast: public snapshot provenance and privacy.

## Android native session recovery — RG-136, 2026-10-08

- RG-136: Android native gameplay must resume after the game Activity is
  recreated or its isolated process dies after a successful suspend snapshot.
  `NativeGameActivity` saves the resume intent in instance state, and the JNI
  runtime accepts the atomically written `.suspend.state` after process death;
  the existing failed-export path removes an older snapshot so stale progress
  is never imported. Automated guards: `tests.test_android_native_runtime`
  (activity recreation, on-disk snapshot recovery, and failed-export cleanup)
  and `tests.test_native_regression_guards`. Runtime acceptance on a packaged
  Android build remains **UNVERIFIED** in this session.

## Android an3ctl ROM load reporting — RG-137, 2026-10-08

- RG-137: `an3ctl rom load --target android` may report `loaded: true` only if
  adb copied the ROM into app-private storage, Android accepted the
  `NativeGameActivity` launch, and that activity became resumed. A `Starting:`
  line by itself is insufficient: Android release builds deny direct writes to
  `/data/data/<package>` and keep `NativeGameActivity` non-exported. Automated
  guards: `tests/an3ctl_android_adapter.test.mjs` covers copy denial, launch
  denial, and resumed-activity success. Validation: the packaged Android 15
  staging build returned `E_ACTION_FAILED` with the app-private `Permission
  denied` reason; the previous false `loaded: true` result is fixed. This does
  not establish gameplay acceptance through the in-app import flow.

## Android native launch thread stack — RG-138, 2026-10-08

- RG-138: Native GBA/NDS/3DS startup must keep large ROM-identity hash buffers
  off the emulation thread's stack. The prior 1 MiB local array overflowed the
  Android `:game` thread stack before core initialization and crashed in
  `std::mutex::lock`; the buffer is now heap-backed. Automated guard:
  `tests.test_android_native_runtime.test_rom_identity_hash_buffer_is_not_on_the_game_thread_stack`,
  plus the Android native-runtime, renderer, and native-regression suites.
  Packaged runtime validation: Android 15 APK 3.2.3 imported the generated GBA
  fixture through the system picker, resumed `NativeGameActivity`, completed
  Quick Save/Load Slot 1, remained active for 60 seconds with zero fatal
  signals, returned cleanly to the library, and relaunched the game. This does
  not establish commercial/homebrew gameplay or audio acceptance.

## Linux packaged core discovery — RG-139, 2026-10-08

- RG-139: The Tauri shell must pass the installed runtime directory to the
  bundled Linux player as `AN3_OFFLINE_LIBDIR`. The player uses that directory
  to find `libretro/` beside itself; relying on `/usr/lib/an3-offline-native`
  breaks the DEB's actual `/usr/lib/VibeCodedEmulator/runtime/linux-x86_64`
  layout. Validation: Debian 13 extracted-DEB UI journey imported the lawful
  16 MiB GBA fixture through the native picker and displayed it in Library;
  launching it before the fix reported the missing-core path. Post-fix
  3.2.2 DEB launch used the bundled mGBA 0.11-212 core, rendered Pokémon
  Emerald's title/menu screens, accepted keyboard Start, and created then
  reloaded a slot-1 state file. `SDL_AUDIODRIVER=dummy` was required on the
  headless host, so audible output is **UNVERIFIED**. The Flatpak 3.2.2 bundle
  installed and launched with the expected UI and GPL metadata, but the host's
  document portal failed to mount its FUSE path; picker import and gameplay in
  Flatpak remain **UNVERIFIED**. Performance on a physical Linux GPU and
  battery-save persistence across app exit/relaunch remain **UNVERIFIED**.

## Web download path — RG-140, 2026-10-08

- RG-140: Web navigation must not describe the retired `/offline` notice as a
  browser ROM library or player. The download hero and shared Offline control
  direct visitors to platform downloads; an empty public Games library directs
  them to the offline app. Validation: the local browser rendered `/` and
  `/games`; the hero's “Choose your platform” link moved to `#platformTitle`,
  and the Games page exposed “Get the offline app” and “Open app downloads”.
  Staging and production were not accessed. Details:
  `reports/handoff/2026-10-08-web-download-path-acceptance.md`.

## macOS Switch companion deployment target — RG-141, 2026-10-08

- RG-141: **The macOS Switch companion must link every Apple framework it
  uses, and every packaged Mach-O must honor the app's 13.4 minimum.** SDL3's
  macOS input/file-type implementation references Carbon keyboard APIs and
  `UniformTypeIdentifiers`; `native/eden-bridge/integration/CMakeLists.txt`
  now links both explicitly. A fresh source-dependency build of the pinned
  Eden revision (`7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c`) linked without
  global linker overrides, has no Homebrew runtime dependencies, and reports
  minOS 13.4. The packaged 3.2.3 app's six Mach-O files all report minOS at or
  below 13.4, with no `/opt/homebrew` or `/usr/local` loads. The packaged app
  launched and rendered its home screen; the no-content bridge smoke passed
  43 checks. **UNVERIFIED:** Switch game launch, gameplay, and input because no
  homebrew fixture or live Switch harness was available. Rust 1.98 on macOS
  27 still requires the isolated target-directory/11.0 build workaround for
  Tauri; the final app metadata remains 13.4 and its bundled Mach-O audit is
  the authority for the supported minimum. Source guard:
  `tests.test_eden_switch_bridge` (20 passed, 4 runtime tests skipped).

## Current authority — Switch/Eden bridge, 2026-09-17

- RG-115: The Eden bridge's deterministic harness (`native/eden-bridge/tests/bridge_smoke.c --json [--frames N] [--seconds N]`) is the Switch regression entry point; it emits one `AN3CTL_STATUS {"target":"switch",...,"result":"PASS|FAIL"}` line. Regression guard for the *error and load paths*: `--json` (no content) = 39 checks PASS; `--json --frames 1 <nx-hbmenu.nro>` = 50 checks PASS. **FIXED 2026-09-17 (sustained rendering).** Root cause: the bare `CAMetalLayer` in `src/cocoa_surface.mm` had zero bounds, so MoltenVK created `3 swapchain images with size (0, 0)`; `vkAcquireNextImageKHR` then failed with `kIOGPUCommandBufferCallbackErrorInvalidInput` → `VK_ERROR_OUT_OF_DEVICE_MEMORY: Lost VkDevice` → an uncaught `Vulkan::vk::Exception` on Eden's `GPU` thread → SIGABRT (the ABI cannot catch a foreign-thread throw; same class as RG-111). Fix: host the layer on a hidden `NSWindow`/`NSView` (AppKit), giving it a real drawable size and letting Core Animation recycle drawables. Validation: swapchain now reports `size (1280, 720)`, created once. `--frames 1|5|10|30|60|120|300|600` all PASS (exit 0); `--frames 600` 8/8 runs PASS; sustained `--seconds 65` (3883 frames), `--seconds 60` ×2 (3583 frames each) all PASS with **0 MoltenVK errors** and clean shutdown. Reproduce: `LIBVULKAN_PATH=<moltenvklib> an3_eden_bridge_smoke --json --seconds 60 <nx-hbmenu.nro>`. Frame *delivery to a caller* is still later milestone D work; this guard covers process stability only.

- RG-116: **Switch input reaches Eden (2026-09-17).** `an3_eden_submit_button` / `an3_eden_submit_analog` drive Eden's own `virtual_gamepad` input engine (`InputSubsystem::GetVirtualGamepad()`), and `an3_eden_get_button` / `an3_eden_get_analog` read back Eden's emulated-controller state so a test proves input arrived rather than only being accepted. ABI bumped to v2 (analog gained a `stick` selector; additive diagnostic hooks added). Button map is the standard libretro→Switch map (B→B, A→A, SELECT→Minus, START→Plus, L/R→L/R, L2/R2→ZL/ZR, L3/R3→stick clicks, d-pad→d-pad). Validation: `bridge_smoke --json --frames 5 <nx-hbmenu.nro>` = **69 checks, 0 failures, `inputSupported:true`** — press A → `get_button` reads 1, release → 0; left stick (16384,−16384) reads back ≈(16384,−16384) and resets to (0,0); a full-scale diagonal is circular-gated to ±23169 (Eden's normal behaviour, asserted as such). Null backend remains honest (UNAVAILABLE, 40 checks PASS). Reproduce: `LIBVULKAN_PATH=<moltenvklib> an3_eden_bridge_smoke --frames 5 <nx-hbmenu.nro>`.

- RG-117: **Switch save location + export (2026-09-17).** `an3_eden_get_save_dir` reports Eden's `EdenPath::SaveDir`, and `an3_eden_save_data(path)` exports Eden's save tree to `path` (recursive copy) without touching the live saves — Eden still owns writing them. Guards: `bridge_smoke` reports a defined status for `get_save_dir`, a non-empty path when supported, a successful export to a temp directory, and rejects NULL buffer/path. Validation: `--json --frames 3 <nx-hbmenu.nro>` = **75 checks, 0 failures** (reported dir `~/.local/share/eden/nand`, export 224 KB). **UNVERIFIED:** a game-level save round-trip (nx-hbmenu writes no NAND save data), so "persistence survives restart" is not claimed here.

- RG-118: **Separate-process Switch companion (2026-09-17).** `an3_switch_companion` (built from `native/eden-bridge/companion/main.cpp`) is the production integration boundary: AN3 launches it, never links Eden into the AN3 binary. It owns a visible AppKit window (`AN3_EDEN_WINDOW_VISIBLE=1` → titled "Vibe Coded Emulator — Switch"), a background frame loop, keyboard input (macOS key codes → Switch buttons) and a line-based stdin automation channel (`button <name> down|up`, `analog <L|R> <x> <y>`, `status`, `quit`). Validation: with `nx-hbmenu.nro` it ran 163 frames/3 s and 704 frames/12 s, accepted button/analog commands with `AN3CTL_ACK`, emitted `AN3CTL_STATUS … "result":"PASS"`, and exited 0 with no errors; `CGWindowListCopyWindowInfo` confirmed an on-screen layer-0 window titled `Vibe Coded Emulator — Switch` (RG-115 hidden mode and the 75-check harness are unchanged). **UNVERIFIED:** real keyboard/gamepad interaction and on-screen pixels (no human session), and Tauri `CompanionSystem` wiring/packaging is not yet done.

- RG-119: **RG-111 contained at the bridge boundary (2026-09-17).** Eden's `ErrorVideoCore` load path terminates inside a `noexcept` destructor (`std::system_error: mutex lock failed: Invalid argument` → SIGABRT) that no C ABI `try/catch` can contain. Repro: a valid `hbmenu.nro` with no MoltenVK (`env -u LIBVULKAN_PATH an3_eden_bridge_smoke --frames 1 hbmenu.nro`) aborted with exit 134 before the fix. Fix: `eden_load` pre-flights the Vulkan runtime (mirroring Eden's `Vulkan::OpenLibrary` search: `LIBVULKAN_PATH`, then `libvulkan.1.dylib`/`libMoltenVK.dylib`/`libvulkan.dylib`) and returns `AN3_EDEN_ERR_UNAVAILABLE` with a clear message instead of entering the crashing path. Verification: with no Vulkan the run is now exit 0 with a structured UNAVAILABLE and **no abort**; with MoltenVK the harness still loads (80 checks PASS). **Classification: CONTAINED, not fixed** — other `ErrorVideoCore` causes and the upstream destructor defect remain; the separate companion process keeps AN3 safe and the app surfaces the error. Guarded by `tests/test_eden_switch_bridge.py::test_23_missing_vulkan_is_structured_not_a_crash`.

- RG-120: **Switch save persistence is isolated and survives restart (2026-09-17).** Eden owns save data under its own data dir; the tests run the companion with an isolated `HOME` so the owner's real saves/configuration are never used. `tests/test_switch_saves.py` verifies (40) the save store is created and no file disappears across a clean restart, (41) it survives an abrupt SIGKILL and the companion restarts with exit 0, and (42) the owner's real `~/.local/share/eden/nand` file set is unchanged. **Scope:** service-level persistence only; a game-level save round-trip is UNVERIFIED because nx-hbmenu writes no game save. Never run these against the owner's real HOME.

- RG-121: **Packaged-app Switch UI E2E (2026-09-17).** `tests/test_switch_ui_e2e.py` drives the real packaged `.app` through `an3ctl ui --target macos`, which dispatches real DOM events on the app's own `data-testid` controls — import (`choose-rom`), the Switch card (`switch-game-card`), launch (`switch-launch`), focus (`switch-focus`), stop (`switch-stop`) and the `switch-status` `data-state` (`starting|running|stopped|error`). It never calls a Tauri command directly and uses no screenshots/coordinates. The bridge is the test-only cargo feature `ui-control` (bound to `127.0.0.1`, random bearer token, validated testids only, port+token in `AN3_UI_CONTROL_FILE`); distribution builds do not compile it and the `ui_control_result` receiver is inert without it. Validation: the full workflow (start → detect → import → card → launch → running + companion process → focus → stop → stopped + no process → relaunch → running → stop → app close leaves no orphan) passes in ~12s against a freshly built bundle. The app-side `.nro` picker is pre-answered only in `ui-control` builds via `AN3_UI_TEST_ROM`, so the real import path and frontend handler still run.

- RG-122: **Switch failure paths stay structured (2026-09-17, extends RG-119).** `tests/test_switch_failure_paths.py` proves an invalid `.nro` and a missing Vulkan runtime both end as `AN3CTL_STATUS mode=load-failed result=FAIL` with a normal exit code (never SIGABRT/-6/134); the companion recovers when a good title is launched after repeated failures; and a failed launch leaves no companion process. Explicitly **CONTAINED**, not a fix of Eden's upstream destructor defect.

- RG-123: **Switch audio path is real, audible output UNVERIFIED (2026-09-17).** `tests/test_switch_audio.py` verifies a non-null backend (`auto|cubeb|sdl3`), a device with >=1 channel and a valid 0..1 volume, and a stable audio diagnostic during sustained rendering. A valid sink configuration is **not** physical speaker output: no loopback capture device is available and the homebrew fixture is not a reliable sound source, so audible output remains UNVERIFIED.

## Current authority — Linux + macOS interactive gameplay, 2026-09-17

- RG-114: The packaged 2.2.0 app must render and accept input on Linux and macOS,
  not just launch. **Linux** (authorized Debian builder, headless): ran the
  DEB-bundled player
  `/usr/lib/VibeCodedEmulator/runtime/linux-x86_64/an3-offline-native --rom boot.3dsx
  --system 3ds --renderer vulkan` under `Xvfb :96` + openbox with
  `AN3_OFFLINE_LIBDIR=<extracted runtime dir>` (core resolution falls back to the
  absolute `/usr/lib/an3-offline-native/libretro`, so an uninstalled extracted DEB
  needs the override) and `SDL_AUDIODRIVER=dummy` (headless host has no ALSA
  device). Vulkan device was `llvmpipe` (software). Observed: `Using Vulkan hw
  renderer`; `PresentWindow initialized with 720x240`; 2 frame resources;
  `Load3DSXFile`; and screenshots (`scrot` on the Xvfb framebuffer) showing the 3DS
  Homebrew Launcher fully rendered (`the homebrew launcher`, `hax 2.x ✦ v2.4.3`,
  both screens). Input (`xdotool`, XTEST — real input path): F4 toggled the SDL
  window 1280x720 ↔ 1280x900 fullscreen; F1 changed the dual-screen layout
  left-right → top-bottom; and `z` (mapped to libretro button 0 = B/Cancel) moved
  the emulated 3DS from hbmenu's `3dslink NetLoader` screen back to the
  `No applications found` screen. **macOS**: the built 2.2.0 `.app` UI rendered, and
  GUI click-through was verified with synthesized CGEvents — clicked `Open ROM` →
  native file picker → selected `boot.3dsx` → `Open` → imported as NINTENDO 3DS
  `boot` (374 KB) → clicked `Play 3DS native`. Gameplay rendered the 3DS Homebrew
  Launcher with the app status bar showing **60.0–60.3 FPS · Vulkan** and the
  on-screen virtual pad. Content used: `devkitPro/3ds-hbmenu` v2.4.3 `boot.3dsx`
  (free official 3DS homebrew); staged copies were deleted after the run.
  **Honest gap**: hbmenu's static `No applications found` screen did not visibly
  change when the on-screen A/Y pad buttons were tapped on macOS, so a per-button
  in-game effect there is not independently confirmed (the pad is present and the
  app UI responds to clicks). Linux used software Vulkan (llvmpipe), so it proves
  the path, not performance.

## Current authority — Windows 3DS/Vulkan + input verification, 2026-09-17

- RG-113: The Windows package must be able to run a 3DS title through its Vulkan
  path, and runtime input must reach the emulated system. The blocker was
  environmental, not code: the VM had no Vulkan ICD. A Microsoft-signed
  SwiftShader software ICD is now installed in the VM (see
  `docs/WINDOWS_BUILD_VM.md`). Runtime evidence (installed 2.2.0 EXE,
  `an3-native-runtime.exe --rom boot.3dsx --system 3ds --renderer vulkan`):
  `Loading file ... as 3DSX`; `Using Vulkan hw renderer`;
  `Vulkan device created successfully via negotiation interface`;
  `Enabling extension: VK_KHR_swapchain`; `LibRetro PresentWindow initialized
  with 720x240`; `Created 2 frame resources for LibRetro`; `Load3DSXFile`
  code/rodata/data loaded; 3DS services active (`hid:USER` + `LoadInputDevices`,
  APT, GSP `AcquireGpuRight`/`RegisterInterruptRelayQueue`, PTM). The emulated
  system advanced in real time (~25 s of emulated time in a 25 s run).
  Input was verified by posting real `WM_KEYDOWN`/`WM_KEYUP` (scancode 0x19 = P)
  to the SDL game window: baseline log growth 49,630 bytes/4 s → **0 bytes/5 s
  while paused** → 57,901 bytes/5 s after resume, with a matching ~5.3 s
  emulated-time gap. Test content: `devkitPro/3ds-hbmenu` v2.4.3 `boot.3dsx`
  (free official 3DS homebrew), used locally and not committed. This device is
  CPU software rendering: it proves the path, not performance. True interactive
  desktop click-through is still impossible in session 0, and the Linux and
  macOS interactive-GUI gaps from RG-112 remain **UNVERIFIED**.

## Current authority — 2.2.0 all-platform rebuild, 2026-09-17

- RG-112: Every packaged app moved from 2.1.0 to **2.2.0** together and was rebuilt
  from the committed source on its own builder (macOS arm64 + Android arm64 on the
  Mac, Linux amd64 DEB/Flatpak on the authorized Debian builder, Windows x64 on the
  `an3-win11-build` VM), with the 2.1.0 bytes retained rather than overwritten.
  Automated guard: `tests.test_phase_a_branding_autosave_exit`
  (`test_native_shell_brand_uses_the_logo_and_version_is_bumped`,
  `test_flatpak_sources_track_the_desktop_version`), `tests.test_integration`
  (`test_current_staging_catalog_names_only_the_current_verified_installers`),
  `tools/verify-release-catalog.py` → `RELEASE_CATALOG=PASS (5 installers)`.
  Runtime evidence (this rebuild): macOS DMG mounts, `CFBundleShortVersionString=2.2.0`,
  ad-hoc `codesign --verify --deep --strict` OK, launches; Android APK installs on AVD
  `codex-nds-api35`, `versionName=2.2.0`/`versionCode=2002000`, MainActivity displays,
  library UI renders, `liban3_offline_native.so` loads, no FATAL; Linux DEB extracts,
  `ldd` clean, launches under Xvfb+openbox; Flatpak installs (`space.an3tocom.offline`
  2.2.0) and runs under Xvfb; Windows EXE silently installs to `C:\AN3\app220`,
  FileVersion/ProductVersion 2.2.0, launches with 6 WebView2 children. Interactive
  gameplay/GUI click-through on Windows, Linux and macOS remains **UNVERIFIED**;
  the Windows VM has no Vulkan ICD. Artifacts (gitignored; sidecars + catalog tracked):
  DMG `9886088642cd…`, APK `0546c3438da0…`, DEB `deff093d9801…`, Flatpak
  `3a4528dc5dd3…`, EXE `7af7d49a03fe…`.

## Current authority — Eden Switch bridge runtime, 2026-09-17

The Eden bridge (`native/eden-bridge/`) is a **separate, out-of-tree build**; it is
not linked into the AN3 app and no Switch feature is deployed or advertised.
Guards below cover the bridge and its build integration only.

- RG-108: The Eden-backed bridge must compile and link against Eden's `core` at
  the pinned commit `7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c`. Two build-integration
  facts are required, both derived from the pinned Eden source: (a) Eden compiles
  every target with `-fno-rtti` (`src/CMakeLists.txt`), so `core` emits no
  `typeinfo for Core::Frontend::EmuWindow`; the bridge must also be compiled
  `-fno-rtti` (it uses no RTTI) or the derived `EmuWindow` fails to link.
  (b) VMA is header-only and Eden defines `VMA_IMPLEMENTATION` in exactly one
  frontend TU (`src/yuzu/main_window.cpp`, `src/yuzu_cmd/yuzu.cpp`, or the
  Android `native.cpp`); with `-DENABLE_QT=OFF -DYUZU_CMD=OFF` none exist, so
  `integration/vma_impl.cpp` supplies the single implementation. `core` links
  `video_core` PRIVATE, so `Vulkan::Headers`, `Vulkan::UtilityHeaders` and
  `GPUOpen::VulkanMemoryAllocator` are linked to the bridge explicitly. Build
  command: see `native/eden-bridge/README.md`. Verified: `an3_eden_bridge_smoke`
  links and runs with `backend=eden`.
- RG-109: The Eden bridge owns exactly one `KernelCore` shutdown per `Load`.
  Eden's `System::Load()` calls `KernelCore::Initialize()` before validating
  content, so a failed load can leave kernel state behind. `backend_eden.cpp`
  tracks `kernel_initialized` and calls `System::ShutdownMainProcess()` exactly
  once — on the `ErrorGetLoader` path (this revision returns it before its own
  cleanup), on `eden_stop`/`eden_shutdown` whether or not the core was started,
  and never twice (a second `KernelCore::ShutdownCores()` would dereference the
  cleared `shutdown_threads`). The dispatcher sets `State::Loaded` on a successful
  load, `start` is allowed only from `Loaded`, and pause/resume use
  `System::Pause()`/`System::Run()` (Eden has no separate resume entry point).
  Verified: `an3_eden_bridge_smoke` with `backend=eden` — 39 checks, 0 failures
  on the non-existent-content path (no crash on shutdown) and 50 checks,
  0 failures loading a real NRO.
- RG-110: On macOS the bridge must present Eden a **Cocoa `CAMetalLayer`**;
  Eden's pinned `Vulkan::CreateSurface()` has no Headless branch (`render_surface`
  is only read for Win32/Cocoa/X11/Wayland/Android), and a null surface throws
  `VK_ERROR_INITIALIZATION_FAILED` from `CreateGPU`. `src/cocoa_surface.mm`
  creates an offscreen `CAMetalLayer` (no `NSWindow`/`NSApplication`) bound to the
  system Metal device; the layer is present-capable under MoltenVK. Verified on
  Apple M5 + MoltenVK 1.4.1 (`LIBVULKAN_PATH`): `vkCreateMetalSurfaceEXT` and
  present support succeeded and `an3_eden_bridge_smoke` initialised the GPU
  (`VkDevice`, 27 extensions). Windows/Linux still need a real window surface.
- RG-111: **Known upstream Eden defect at the pinned revision** (recorded, not
  patched): when `System::Load()` fails through `ShutdownMainProcess()`
  (for example `ErrorVideoCore`), the local `Service::Process` is destroyed
  *after* the kernel's `global_object_list_container` was reset, so
  `KAutoObjectWithListContainer::Unregister()` locks a destroyed `std::mutex`
  and throws `std::system_error(EINVAL)` inside a `noexcept` destructor →
  `std::terminate` (observed as `mutex lock failed: Invalid argument`). The
  bridge cannot catch it and avoids it by making the load succeed; a load that
  fails before GPU setup (`ErrorGetLoader`) shuts down cleanly. Any future work
  that must tolerate GPU-init failure needs an Eden patch or a supported upstream
  fix.

## Current authority — native Phone Controller + 2.1.0 all-platform build, 2026-09-17

- RG-103: The Android phone-controller host is **app-scoped in the main process** (`An3ControllerHost`); the isolated `:game` process (`NativeGameActivity`, `android:process=":game"`) binds to `ControllerHostService` and receives resolved buttons/axes/stylus over a `Messenger`. The raw host token never crosses the process boundary, is never logged, and is never persisted. There is exactly one `ControllerClient` implementation shared by the library card and the in-game menu. Automated guard: `tests.test_multiplayer_api` (`test_ack_requires_the_host_token_and_link_requires_the_phone_token`, `test_diagnostics_snapshot_excludes_secrets`). Runtime validation (AVD `codex-nds-api35`, APK 2.1.0 `ba4c650a…`, staging): Settings → Phone Controller → Start created session `QZHYTZ`; the phone paired, launched the GBA fixture, auto-selected the GBA layout, reported `Connected`, and four `Start` presses advanced the game to its NEW GAME / OPTION menu; the NDS fixture auto-selected `nds`, showed the touch screen, and a stylus drag was delivered to the game process.
- RG-104: Every native host acknowledges only frames it really applied and reports the running system so the phone can auto-select its layout. `POST /api/controller/ack` is host-token-scoped; an optional `system` updates the session's `system` only for a known value; `GET /api/controller/link` returns it. On desktop, `controller_host.rs` sends the ack + `system` only when `native_input_ready()` is true (macOS `an3_native_is_running`, Linux/Windows child `try_wait`), and `NativeGameOverlay` on Android. Pairing alone never reports applied input; a host whose input path stops advancing falls out of the two-frame liveness window. Automated guard: `tests.test_netcode` (`test_input_is_active_only_after_the_host_acknowledges`, `test_touch_tuple_round_trips_and_absence_means_released`), `tests.test_multiplayer_api` (`test_the_host_can_report_the_running_system_for_the_layout`, `test_input_active_requires_an_acknowledged_frame`), Rust `controller_host` (`frame_input_maps_normalized_touch_to_the_pointer_contract`, `a_missing_game_never_acknowledges_input`, `the_host_acknowledges_the_frame_it_applied`). Runtime: live staging probe PASS on macOS (`GRFDHN`) and Debian (`KYGD74`), phone layout `gba`/`nds` observed on Android.
- RG-105: The Android in-game General-tab controller is a convenience over the same host: the `:game` process sends `MSG_START`/`MSG_STOP` and the service owns the session, so a Controller Mode session started before a game survives entering and leaving the game. Detaching the game releases all held remote input and cancels the pointer but does not end the pairing. Automated guard: `tests.test_regression_invariants` + the Kotlin build (compilation). Runtime validation: AVD — Start in Settings, enter the GBA game, exit back to the library, and the phone reported `Connected — input unavailable` (no game) without re-pairing.
- RG-106: NDS/3DS stylus from the phone uses the same pointer contract as the on-screen touch: normalized `t=[x,y]` → `x*255`, `y*191` into `nativePointer`, released on frame-without-touch, menu open, game detach, and `pagehide`. Automated guard: `tests.test_netcode` touch-tuple test. Runtime validation: AVD NDS title with the phone's `nds` layout, drag delivered to the `:game` process (frames changed). **Full stylus-effect acceptance on a title that visibly reacts remains UNVERIFIED.**
- RG-107: Every packaged app moved to **2.1.0** together (including the previously stale `src-tauri/Cargo.toml` and `web/index.html` cache-busting), the release catalog lists only 2.1.0 installers with fresh sizes/SHA-256 and sidecars, and `tools/verify-release-catalog.py` passes. Runtime validation: macOS DMG (2.1.0, mounts/launches, `CFBundleShortVersionString=2.1.0`), Android APK (installs/launches on the AVD), Linux DEB (extracts, `ldd` clean, launches under Xvfb+openbox) and Flatpak (installs and runs), Windows EXE (silent installs to `C:\AN3\app100`, launches, FileVersion 2.1.0). Windows interactive gameplay is **UNVERIFIED** (Session 0, no Vulkan ICD); Linux GUI click-through is **UNVERIFIED** (WebKitGTK paints nothing under Xvfb); macOS GUI click-through is **UNVERIFIED** (no assistive-access for UI scripting). Staging serves all five installer URLs 200.

## Current authority — controller/sync/multiplayer UX refactor, 2026-09-17

- RG-096: A phone controller is "Connected" only when the host's input path is keeping up. The host reports the newest frame it has applied via `POST /api/controller/ack` (host-token-scoped), and `netcode.ControllerSession.input_active()` is true only when paired, an ack exists, and the host is at most two frames behind the phone's latest snapshot — so a host whose input path stops advancing reports "Connected — input unavailable" instead of a lie. Pairing success alone is never reported as applied input. The phone reads this through `GET /api/controller/link` (phone-token-scoped); the host's own status words never show `expiresInSeconds` as a countdown. Automated guard: `tests.test_netcode` (`test_input_is_active_only_after_the_host_acknowledges`), `tests.test_multiplayer_api` (`test_input_active_requires_an_acknowledged_frame`, `test_ack_requires_the_host_token_and_link_requires_the_phone_token`). Runtime validation (staging asset `f2c429f14adc`): a running GBA player host created session `43F3Z7`, the phone auto-selected the GBA layout, phone and host both showed `Connected`, and the phone's Start press produced `simulateInput(0,3,1)` / `(0,3,0)` on the live core; a scripted-ack probe showed `Connected` only while acks advanced and `input unavailable` otherwise.
- RG-097: `GET /api/controller/hosts` returns only active controller sessions whose creator is on the caller's own IPv4 /24, and never discloses an address, token, or internal id — just the pairing code the user would otherwise type plus a short label. `clean_controller_name` strips non-printable characters. Automated guard: `tests.test_multiplayer_api` (`test_nearby_hosts_lists_the_session_without_an_address`). Runtime validation (staging): the phone showed the host as "Vibe Coded Emulator / Ready to connect" and pairing by tapping it worked; no IP appeared in the page.
- RG-098: The sync catalog's primary modes are plain-language (`Automatic` — the recommended default, `Local network only`, `Google Drive only`, `Off`); `sync_engine.SyncMode.AUTO` prefers LAN when a peer is present and falls back to Drive only when credentials exist (`select_transport(..., drive_available=...)`), and `requires_drive` (DRIVE/LAN_DRIVE) stays the only credential-gated pair. Content toggles (`save`/`state`/`library`) default on and `rom` defaults off with a visible storage/bandwidth warning; content persists per device. SHA-256 values are never shown in the normal sync UI. Automated guard: `tests.test_sync_api` (`test_default_mode_is_off_and_persists_per_device`, `test_automatic_mode_is_available_without_drive_credentials`, `test_content_toggles_persist_and_rom_warns`), `tests.test_sync_engine` (`test_automatic_prefers_lan_then_drive`). Runtime validation (staging asset `f2c429f14adc`): `/sync` listed `auto,lan,drive(disabled),off`, Drive showed "unavailable in this build", ROM warning toggled, save persisted, and the device list showed "This device". **Byte-level client-store sync and true peer-to-peer transfer remain UNVERIFIED.**
- RG-099: Multiplayer capability is per core, not global (`MULTIPLAYER_CORE_CAPABILITY`): only GBA is advertised (runtime-verified, relay-mediated lockstep); NDS/3DS/Switch/HTML5/GBC show "Not available for this system" and no Create Room button. The normal multiplayer surface never prints the relay origin or the full ROM hash; the collapsed "Technical details" shows system/core and a 16-hex-character short hash only. `/api/multiplayer/room` still returns the exact relay origin to the netplay client, and continues to 404 in production. Automated guard: `tests.test_multiplayer_api` (`test_multiplayer_capability_is_per_core_and_conservative`), `tests.test_integration` (`test_room_page_renders_with_its_controls` asserts no `STAGING` page copy and no relay origin). Runtime validation (staging asset `f2c429f14adc`): GBA `pokemon-emerald` page created room `TC08MX`, a same-game guest joined as "Compatible. Connecting…" and the host showed "Player joined. Connecting…"; the NDS game page showed "Not available for this system". **Peer video does not exist in this build; transport is relay.**
- RG-100: `GET /api/diagnostics` and `/diagnostics` expose operational detail only (environment, asset version, session counts, TTLs, capability map, relay transport) and must never contain a token, host token, pairing code of a live session, or a device address. Gated to staging/development like the rest of the controller/sync/multiplayer surfaces. Automated guard: `tests.test_multiplayer_api` (`test_diagnostics_snapshot_excludes_secrets`). Runtime validation (staging): the JSON rendered with no `token` field.
- RG-101: The web player may inject a phone stylus gesture into the NDS/3DS touchscreen only through the shared `AN3NdsTouchBridge` geometry: `payload.t = [x, y]` normalized 0..1 is mapped to the source canvas via `touchScreenRect` + `resolveNdsVideoViewport`, dispatched as synthetic `mousedown`/`mousemove`/`mouseup` with `pointerType:"touch"`, and released on frame-without-touch, menu open, stop, and `pagehide`. Runs only while gameplay is started, not failed, and no EmulatorJS menu is open. Automated guard: the existing player/NDS contracts (`tests.test_regression_invariants`, `tests/web_nds_touch_behavior.test.js`, `tests/web_renderer_behavior.test.js`, `tests.test_web_nds_touch_behavior`) all still pass; the new code is additive and only synthesizes events. Runtime validation (staging asset `f2c429f14adc`, NDS `pokemon-mystery-dungeon-explorers-of-sky` running): a phone touchscreen drag produced `mousedown` → four `mousemove` (advancing coordinates) → `mouseup`, all `pointerType:"touch"` on `#game canvas:not(.an3-render-canvas)`; the host and phone both showed `Connected`. **macOS/Windows/Linux packaged-app GUI pairing with a real phone remains UNVERIFIED.**
- RG-102: Phone page input transitions must never be coalesced away: button and stylus down/up transitions are sent as their own ordered frames; only consecutive analog/touch moves may coalesce (latest-state-wins). On disconnect the phone releases every held button/axis/touch, and the host releases all applied input when it stops, on session end (403/404), and on `pagehide`. Automated guard: `tests.test_multiplayer_api` touch-frame test + existing player release contracts. Runtime validation (staging): holding `right` and disconnecting produced `[0,7,1]` then `[0,7,0]` on the live core, and the host returned to "Waiting for a phone…".

## Current authority — LAN save-set transfer, 2026-09-20

- RG-135: A normal save is a logical, deterministic save set, not a stream of independently persisted files. Its identity is `core + gameId + full ROM SHA-256`; members are normalized relative paths with exact byte lengths and SHA-256 values, sorted lexicographically, and the manifest carries an aggregate hash. The server validates every member and stores a complete set atomically; the browser validates every downloaded member and persists the set only after aggregate validation, with save states remaining a separate `state` artifact. Automated guards: `tests/sync_transfer.test.mjs` (single-member compatibility, deterministic ordering, missing/unexpected/duplicate/hash/size rejection, atomic failure, set-level conflict), `tests.test_sync_api` (multi-member publish/manifest/download, malformed identities, missing blobs, payload/security limits), and `tests.test_phase_a_branding_autosave_exit` (version parity after the required packaged-app bump). Runtime acceptance for this slice is recorded separately below; no ROM synchronization or background synchronization is implied.

## Current authority — LAN save/state transfer, 2026-09-16

- RG-095: LAN transfer must accept only `sync_engine`-eligible kinds (never `firmware`/`keys`), verify every published item's SHA-256 prefix against its bytes, cap items (16 MiB) and the list (512), keep blobs **in memory only** with a 900 s TTL reaped on every LAN request, and serve a blob only when the caller's `hash` matches the stored one. All `/api/sync/lan/*` routes are `SYNC_ENABLED`-gated (production 404). Automated guard: `tests.test_sync_api`. Runtime validation (2026-09-16, two real devices): MacBook published a 1041-byte state blob and the Debian staging host pulled it byte-exact (sha256 `d610c3a8…`); the Debian published a 780-byte save blob and the Mac pulled it byte-exact (sha256 `ea48442b…`). Report `reports/handoff/LAN_TRANSFER_20260916.md`. **True peer-to-peer (device-hosted listener) and client wiring remain UNVERIFIED.**

## Current authority — desktop controller ACL fix + Linux GUI end-to-end, 2026-09-16

- RG-093: Every Tauri command must be listed in `src-tauri/build.rs`'s `AppManifest::commands([...])` **and** have its `allow-<kebab>` permission in `src-tauri/capabilities/default.json`. Historical failure: 1.4.0 shipped the three `native_controller_*` commands in `lib.rs` and the capability file but omitted them from `build.rs`, so Tauri never generated the permissions and the WebView showed `Command native_controller_status not allowed by ACL` — the desktop controller panel was non-functional. Fixed in 1.4.1. Automated guard: `tests.test_offline_consolidation` derives every `#[tauri::command]` from `src/*.rs` and requires the build.rs list to match and each capability entry to exist. Runtime validation: after the fix, the Linux GUI flow works end to end (see RG-094).
- RG-094: The desktop controller chain — phone → staging API → Tauri host poll → `set_native_input` → runtime `INPUT` stdin → core — was verified in the real Linux app under Xvfb + openbox: session `FM9MVQ`, host showed `Phone connected`, and eight phone `start` frames advanced the running GBA to its NEW GAME / OPTION menu. Evidence: `reports/staging/linux-desktop-controller-session.png`, `-connected.png`, `-game-before.png`, `-game-after.png`. macOS/Windows **GUI** pairing remains UNVERIFIED (build/launch only). Runtime validation of 1.4.1: macOS DMG 1.4.1 mounts/launches and contains `native_controller_status`; Windows EXE 1.4.1 installs silently and launches/responds with WebView2 children; all five installers served 200 by staging.

## Current authority — Linux 1.4.0 runtime + controller path, 2026-09-16

- RG-092: The Linux 1.4.0 bundle must launch and its bundled player must honour the shell's `--control-stdin` `INPUT <buttons> <circleX> <circleY> <touchX> <touchY> <touched>` protocol for the controller's libretro button bits. Historical context: Linux 1.4.0 was built but unrun. Runtime validation (Dell, Xvfb, 2026-09-16): the extracted 1.4.0 DEB runtime ran the full `timeout 25s` (EXIT=124) with `SDL_AUDIODRIVER=dummy LIBGL_ALWAYS_SOFTWARE=1`; the installed app binary contains `nativeControllerCard`; `cargo test --lib controller_host` passes on Linux (6/6) and the live staging probe passed (session `FY5554`); feeding `INPUT 8 …` (GBA `start`) then releasing advanced the game from the Game Freak logo to its menu, captured in `reports/staging/linux-1.4.0-input-before.png` / `-after.png`. The shell→runtime write path itself is now unit-tested (`linux_runtime::tests::input_writes_the_control_stdin_protocol` feeds a fake child and asserts `INPUT 8 1234 -1234 7 9 1`), and `tests.test_native_input_contract` pins the exact line format shared by the Linux and Windows adapters. The Tauri app autonomously writing those lines while polling (GUI glue), Windows 1.4.0 runtime, and a real phone driving a running desktop game remain **UNVERIFIED**.

## Current authority — release 1.4.0 across five platforms, 2026-09-16

- RG-091: Every release script must derive the artifact name from the version field (`build-android-staging.sh`, `package-macos.sh`, `build-linux-staging.sh`, `build-windows-staging.ps1`, `verify-flatpak-install.sh`); the Flatpak manifest and metainfo are pinned by `tests.test_phase_a_branding_autosave_exit.test_flatpak_sources_track_the_desktop_version`. Historical failure (found 2026-09-16): `build-windows-staging.ps1` looked for `VibeCodedEmulator_1.3.0_x64-setup.exe`, so a 1.4.0 build copied a leftover 1.3.0 installer under the wrong filename (caught before publishing). Runtime validation: all five 1.4.0 installers (DMG/APK/DEB/Flatpak/EXE) pass `tools/verify-release-catalog.py` and are served 200 by staging with the catalog sizes. Runtime follow-up (2026-09-16): Linux 1.4.0 runtime verified (RG-092) and the Windows 1.4.0 EXE installed silently and launched (FileVersion/ProductVersion 1.4.0, `msedgewebview2` children) on the VM. Windows **gameplay** remains unverified.

## Current authority — desktop native phone-controller host, 2026-09-16

- RG-090: The desktop shells (macOS/Linux/Windows) share one Rust controller host (`src-tauri/src/controller_host.rs`). It speaks plain HTTP/1.1 over `std::net::TcpStream` (the controller service is a LAN HTTP origin; `https` is refused, and there is no HTTP dependency), creates the session, polls `/api/controller/state`, and applies a full `NativeInput` snapshot through the existing `set_native_input` — the same path the in-app controls use. The button map must equal the web/Kotlin maps (`tests.test_multiplayer_api.ControllerButtonParityTests`), the raw host token never leaves the module, input is released on stop / session end (403/404) / window destroy, and nothing runs unless a session is started. `scripts/package-macos.sh` and `scripts/build-android-staging.sh` derive the artifact name from the version field so a bump cannot publish a stale filename. Automated guard: `tests.test_multiplayer_api`, Rust `controller_host` tests (7, one ignored live probe). Runtime validation (2026-09-16): `cargo test --lib controller_host` passes including a real local TCP session lifecycle; the ignored live probe against staging created session `X911XP`, paired as a phone, submitted `right`, and reached the input sink; macOS DMG 1.4.0 (`638d44ee…`) mounts, reports `CFBundleShortVersionString 1.4.0`, ships `nativeControllerCard`, and launches/stays alive; staging serves it 200. **A phone driving a running desktop game, and Linux/Windows compile/run, remain UNVERIFIED.**

## Current authority — Android native phone-controller host, 2026-09-16

- RG-089: The Android native app is a phone-controller **host**: the in-game General menu creates a session on the configured staging controller server, shows the code, polls `/api/controller/state`, and feeds the phone's frame through the same `input`/`directionalInput` callbacks the on-screen pad uses. Invariants: the libretro button map must equal the web `controllerButtonIndex` (`tests.test_multiplayer_api.ControllerButtonParityTests`); the raw host token is never logged, shown, or persisted (it stays inside `ControllerClient`); input is applied only while the menu is closed and is released on stop/destroy; cleartext HTTP is permitted only for the staging host via `res/xml/network_security_config.xml` (base stays `cleartextTrafficPermitted="false"`). `POST /api/controller/session` accepts a bounded `ttlSeconds` (60–3600) so a native game session outlives the web 2-minute pairing window; invalid/absent values clamp to the existing 120 s default (`tests.test_multiplayer_api.test_session_lifetime_is_bounded_by_the_request`). Runtime validation (AVD `codex-nds-api35`, APK 1.4.0 `3c7518a2…`, staging asset `e792e8578089`): the app created session `0M656E` (3594 s), reported `Phone connected · no input`, and six `start` presses sent from the Mac (paired as the phone) advanced the GBA title from the Game Freak logo to the NEW GAME / OPTION menu. Evidence: `reports/android-regression/1.4.0-phone-controller.png`, `1.4.0-phone-before.png`, `1.4.0-phone-after.png`. macOS/Linux/Windows native injection is **not implemented** (UNVERIFIED).

## Current authority — Windows 1.3.0 launch smoke, 2026-09-16

- RG-088: A Windows staging EXE launch smoke must not be reported as gameplay. The 1.3.0 Windows installer installs silently (`/S`) and the installed `an3-offline-native.exe` (FileVersion 1.3.0) launches, stays alive, is responsive and spawns its `msedgewebview2.exe` children on the `an3-win11-build` VM — but that VM has no Vulkan ICD and only GDI Generic OpenGL 1.1 and the app runs over SSH in Session 0. **Gameplay, rendering, audio, and input on Windows remain UNVERIFIED.** Do not install a software renderer to fabricate acceptance (RG-073). Automated guard: none (verification record). Evidence: `reports/handoff/WINDOWS_1.3.0_LAUNCH_SMOKE_20260916.md`. Method: start the VM on demand (`sudo virsh start` on the Dell), `scp` the verified installer, `Start-Process … /S`, launch `C:\AN3\app100\an3-offline-native.exe`, check `Get-Process`/`msedgewebview2`, then in-Windows `shutdown /s`; keep `Autostart: disable`.

## Current authority — cross-device sync wiring, 2026-09-16

- RG-087: Cross-device sync is staging-only and its decision logic lives in the pure `sync_engine`; `app.py` owns only the per-device mode, the plan/conflict surface, and the LAN peer registry. Every `/api/sync/*` route and `/sync` return 404 in production (`SYNC_ENABLED = ENVIRONMENT in {staging, development}`). Google cloud sync was removed on 2026-10-13: the Drive transport module and its tests are deleted and `GOOGLE_DRIVE_ENABLED` is now the constant `False`, so the option can never be advertised as available and `POST /api/sync/settings`/`plan` always return 409 `drive-unavailable`. Local saves and LAN save/state transfer are unaffected. Automated guard: `tests.test_sync_api.test_drive_mode_is_permanently_unavailable`. A device's mode is keyed by the hashed visitor cookie (no account needed). The LAN registry is in-memory only, TTL-reaped, and discloses a peer's address only to a requester on the same IPv4 /24. Automated guard: `tests.test_sync_api`. Runtime validation (staging, asset `e792e8578089`): `/sync` 200; `GET /api/sync/settings` → `off` with Drive `available:false`; `POST` `lan` → persisted; `POST` `drive` → 409; `POST /api/sync/plan` → `download`/`remote-changed` for a remote-only change; `POST /api/sync/lan/announce` → the announcing peer at `192.168.1.6`, `sameSubnet:true`; Playwright `/sync` saved `lan` and listed the peer with no console errors. Byte-level LAN transfer between two devices and any Google Drive transport are **UNVERIFIED** (not implemented in this phase).

## Current authority — multiplayer relay bridge, 2026-09-16

- RG-085: The player page CSP must allow the EmulatorJS netplay relay over a **WebSocket**. `connect-src` treats `ws:`/`wss:` as distinct schemes from `http:`/`https:`, so listing only the relay's HTTP origin silently blocks the Socket.IO upgrade (`Connecting to 'ws://…/socket.io/…' violates … connect-src`), the socket never connects, and the netplay room is never created. Fix: `player_content_security_policy(netplay_origin)` adds `ws://` (from `http://`) or `wss://` (from `https://`). Automated guard: `tests.test_multiplayer_api.PlayerCspTests`, `tests.test_regression_invariants`. Runtime validation (staging, Chrome via Playwright): before the fix `socketConnected=false` and the room never appeared; after it `socketConnected=true` and the room appeared in the relay `/list`.
- RG-086: The AN3 multiplayer room and the EmulatorJS relay room are the same room: the AN3 invite code is the relay room name, hosting uses `emu.netplay.openRoom(code, 2, "")`, and joining resolves the relay key from `getOpenRooms()` and uses `emu.netplay.joinRoom(key, code)`. The AN3 `/api/multiplayer/join` compatibility check (system + core + ROM hash) runs before any relay join. `openNetplayMenu()` is used only to materialize the netplay object and its own panel is hidden again. The player `roomSignature` is computed server-side (single source of truth). Staging-only: production 404s the room API and `/multiplayer` and the panel is absent. Automated guard: `tests.test_multiplayer_api`, `tests.test_qr_svg`, `tests.test_integration`, `tests.test_regression_invariants`. Runtime validation (staging, Chrome via Playwright, two pages, live relay `http://192.168.1.8:8094`): host created room `B4VZ0W` (relay `current:1`), guest joined the same relay room (`current:2`), both `isNetplay=true` with a connected socket, and the panel QR rendered. The **staged web EmulatorJS build has no WebRTC**: netplay is relay-mediated input lockstep (`socket.emit("data-message", {"sync-control": …})` with state snapshots), gated upstream behind `EJS_DEBUG_XX && EJS_EXPERIMENTAL_NETPLAY` (our bridge calls `openNetplayMenu()` directly). `GameManager.simulateInput` already routes into `netplay.simulateInput` when `isNetplay`, so AN3's virtual pad and the phone controller participate. Runtime validation of input sync: a guest `simulateInput(0,7,1)/(0,7,0)` ×6 appeared on the host's raw core `gameManager.functions.simulateInput` as 12 remote calls. Peer **video** is not a thing in this build (each peer runs its own core); the Android asset build (different, with WebRTC) is not what staging serves.

## Current authority — web phone-controller binding + pairing QR, 2026-09-16

- RG-082: Every POST endpoint must consume its request body before responding, even when the payload is ignored. Historical failure: `controller_create_session` never read its body, so on an HTTP/1.1 keep-alive connection the next request line was prefixed with the leftover JSON (`{"deviceId":"host"}GET`) and the server answered 501. It worked in curl/`http.client` tests only because each opened a new connection. Fix: `Handler.read_optional_json()` drains a present-but-ignored body; `controller_create_session` calls it. Automated guard: `tests.test_multiplayer_api.test_session_create_consumes_its_body_on_a_keepalive_connection`. Runtime validation (staging, Chrome via Playwright): the 501 disappeared from `/controller` and `/play/<slug>` consoles.
- RG-083: The pairing QR is generated server-side as a self-contained SVG (`app.controller_qr_svg`) served only from `GET /api/controller/qr.svg?code=` (gated by `CONTROLLER_ENABLED`; production 404). It must contain no `<script>`, no external references, and must carry explicit `width`/`height` so an `<img>` reports a non-zero `naturalWidth` (a `viewBox`-only SVG reported 0 and never rendered). The absolute join URL is built from the request's own `Host` header (`app.controller_join_url`), never a caller-supplied value, so the endpoint cannot be used to render an arbitrary URL. Automated guard: `tests.test_qr_svg`, `tests.test_multiplayer_api`, `tests.test_integration` (player page ships `controllerEnabled` and `#ctrlPhonePanel`). Runtime validation (staging, Chrome via Playwright): `/controller` showed the QR at `naturalWidth=41`, and the rendered PNG decoded with OpenCV to `http://192.168.1.8:8092/controller/join?code=39EW5E`.
- RG-084: The web player is the pairing host for the phone controller and may apply a phone frame only while gameplay is running and no EmulatorJS menu owns input (`gameStarted && !runtimeFailed && !emulator-menu-open`). It must release every applied button and axis on disconnect, panel close, session end, and `pagehide`, and must never inject input into a stopped session. Automated guard: `tests.test_regression_invariants`, `tests.test_web_nds_touch_behavior`, `tests.test_native_regression_guards`, `tests.test_shared_player_ui`, and the `tests/web_nds_touch_behavior.test.js` + `tests/web_renderer_behavior.test.js` node suites (all unchanged contracts). Runtime validation (staging, Chrome via Playwright): host `/controller` session `EG9JFT`; phone page paired, pressed Right; host status `Phone connected · 117s`; `EJS_emulator.gameManager.simulateInput` observed `[7,1]` then `[7,0]`. Native input injection into the packaged apps is **UNVERIFIED** (not implemented in this phase).

## Current authority — Android 3DS UI-gate fix, 2026-09-15

- RG-075: Android 3DS visibility must come from exactly one capability declaration. `native-offline/web/android-staging.js` (shipped as `assets/android-staging.js`) must read `window.AN3NativeIntegratedSystems`, never a second hardcoded system list. Historical failure: the frozen `8b6375` production APK shipped `const supported = new Set(["gba","nds"])`, so the script disabled the 3DS system option and the 3DS library card right after render even though `native-bootstrap.js` declared `["gba","nds","3ds"]`. Symptom: 3DS appeared "unavailable"/hidden on Android although the Azahar payload and native launch path were functional. Fix: read the declaration (`new Set(Array.isArray(declared) ? declared : [])`). Automated guard: `tests.test_offline_consolidation`, `tests.test_android_native_runtime`, `tests.test_native_staging_contract`, plus generated-bootstrap synchronization.
- RG-075 runtime validation (AVD, Android 15, host Vulkan / Apple M5): the incoming production APK `4ee9e6399a4f08880a71c2c5f3955949cf4b252412883bd3f6151759efc6b3cb` disabled the 3DS option/card and would only launch 3DS through the JS bridge (Vulkan frames + input confirmed behind the gate). Corrected APK `f0fd3a572bb6841dd02eb5882434073d1b020cec9ab972147a7981847114f520` (same Android Debug v2 signer `b48f3cdecc39349a75b66817aaad645a861d538be34835f290a2aa570c3beb4b`) enables the 3DS option and card and launches a playable 3DS title from the real UI click (56–58 FPS, working input). Deployed staging `staging-94c80267ea7b4b57` and production `production-94c80267ea7b4b57`; public HTTPS serves the corrected bytes and the superseded hash returns 404. Android 3DS **audio audibility remains UNVERIFIED** (RG-057/RG-064 gate still open); this guard covers UI exposure and native playability only.

## Current authority — web/shared player parity fixes, 2026-09-15

- RG-076: Every `PLAYER_BOOT_ASSETS` entry must be served by the versioned `/static/v/<asset>/<name>` route. Historical failure: the route regex in `app.py` omitted `player-ui.js`, so `offline_page` and `player_page` both loaded a 404 (`MIME type ('text/plain') is not executable`); `globalThis.AN3PlayerUI` stayed `undefined`, `addAnalogStick` returned early, and the service-worker precache fetched the same 404. Symptom: no shared UI model and no virtual analog joystick on the web/offline player even though native had it. Fix: the versioned regex now includes `player-ui.js`, matching the frozen boot-asset set. Automated guard: `tests.test_integration` derives the served list from `app.PLAYER_BOOT_ASSETS` and requests each versioned file. Runtime validation (2026-09-15, Chrome 152 headless, legal fixtures): fixed local build `17885c13838a` served `player-ui.js` 200 `text/javascript`; GBA frames advanced 82→564, NDS 112→594; `window.AN3PlayerUI.model.tabs` reported the nine DMG sections; the 3DS Azahar core preloaded (3.8 MB) and verified in `EmulatorJS-core`.
- RG-077: The offline web player must expose the same D-Pad/Analog-Joystick choice as the DMG/native player. Historical failure: `static/offline.js` rendered virtual-pad settings without `#padDirectionalControl`, so `settings.directionalControl` stayed at its per-system default and the analog joystick could not be enabled in `/offline` even after the shared model loaded. Fix: the offline markup now includes `#padDirectionalControl` with `dpad`/`joystick` options, driving the existing `player.js` change handler. Automated guard: `tests.test_offline_consolidation`. Runtime validation (Chrome 152 headless, local fixed build): selecting `joystick` set `#tvPad.analog-mode` and made `.tvStick` visible.

- RG-078 (superseded 2026-09-15): a browser-only 3DS lock was added and then withdrawn at the owner's direction. No browser-only playback lock may be reintroduced. The only remaining gate is the installed Android capability declaration (`androidThreeDsUnavailable`, RG-075). Browser Azahar wasm does not present video (`getVideoDimensions() = -1`, no audio context, black source and presentation canvases with both the cached `latest` and CDN `nightly` cores), but that is recorded as an upstream limitation, not enforced as a UI lock. Automated guard: `tests.test_offline_consolidation` and `tests.test_android_native_runtime` assert `browserThreeDsUnavailable` is absent and the play control is bound only to `androidThreeDsUnavailable`/`html5`.
- RG-079: Android native launch must never dead-end on a record whose copied file id no longer matches. `MainActivity.launchNative(romId, system, expectedSize)` resolves the exact `<romId>.<ext>` first, then a unique ROM of the same system with `length() == expectedSize`, and the library passes the recorded byte size through `launchNativeSized`. A genuinely absent ROM keeps the play button enabled and shows a one-tap "Nhập lại ROM" (`data-repair-native`) that re-imports for the same record id and continues into native play. Historical failure: `nativeRomFile(romId, system)` returned null for a stale id and the card showed the dead-end "Native ROM is unavailable" with no recovery. Automated guard: `tests.test_offline_consolidation`, `tests.test_android_native_runtime`, `tests.test_native_regression_guards`. Runtime validation (AVD Android 15, 0.4.8 build `9fb8b5c4…`): a fresh UUID launched with the real 256 MB NDS file's exact size returned `""` and resumed `NativeGameActivity` with the `:game` process, while the legacy 2-arg call still returned "Native ROM is unavailable"; the missing-file card showed the error note plus the "Nhập lại ROM" button and stayed enabled.

## Current authority — fresh staging implementation, 2026-09-13

- RG-072: Installer freshness is distinct from static web assets. `native_release_identity()` fingerprints the complete release catalog and frozen source identity; `/health`, the manifest and Release Center expose the same `release_id`. Download URLs bind the expected SHA-256; a stale hash returns 404 even when the filename is reused. Package creation verifies catalog sizes/hashes and portable sidecars. Behavioral HTTP regression reproduces same-size replacement and verifies new identity, old-link rejection and `no-store`. Post-deploy HTTP parity remains required.
- Current fresh staging acceptance: `staging-e9ac3ffc8a028015`, directory `20260913-204524-df14d4aa2d9a`; four HTTP installer streams match final catalog size/SHA, new ID visible, stale hash links 404, Windows blocked. Rollback `20260912-182516-df14d4aa2d9a` preserved. Exact bytes/evidence in current CODEX_PROGRESS Artifact Matrix; earlier release-specific bytes below are historical.
- RG-072 follow-up: packaging monitoring asserts the verified catalog handoff and sidecar inclusion, not obsolete hardcoded installer names. Canonical verification exposed the stale assertion; exact corrected test PASS. Build/deploy input parity is unchanged by this test-only correction.
- RG-073: Tauri common resources contain no Mac native binaries; macOS resources preserve their original paths in `tauri.macos.conf.json`, and Windows uses only Windows x64 core DLLs. Native Windows staging preflight verifies SDK files, exact core size/SHA/PE architecture and refuses absent native launcher integration. A shell NSIS is diagnostic only. The VM has no Vulkan ICD and only GDI Generic OpenGL 1.1; do not install a software renderer to fabricate native acceptance.
- RG-074: mGBA Windows is built from existing commit `e31759b24e7a4e3899285ff720d7b573ac328ae7`. Its sole MSVC patch closes each logging macro invocation inside its conditional branch; severity, format, arguments and emulation behavior are unchanged. Patch and normalized source hashes are checked. melonDS DS uses official v1.3.1 x64 archive digest `ec7ff94ae5be3a6308859ea33ec63ac9d9b12d940b2c93d012e9502f71e57681`.
- Native web packaging now checks all 22 prepared runtime files against `shared/web-runtime-lock.json`; a mutable upstream change fails instead of producing different platform dependency bytes.

## Previous authority — staging release completion, 2026-09-12

This authority supersedes older claims below where the current artifact bytes, platform availability, owner audio evidence, or staging asset differ. Earlier entries remain historical evidence.

- RG-057: Android normal gameplay uses the portable libretro host and native Surface/ANativeWindow presentation, with Vulkan preferred and GLES3 fallback for software cores. **PASS** for GBA/NDS source and AVD paths. Android 3DS uses the shared libretro Vulkan hardware interface and core-provided image/synchronization path; it has no normal GPU readback/re-upload path. Its availability remains **UNVERIFIED/UNADVERTISED** until its separate audio gate is met.
- RG-060: Native frame resources remain reusable/bounded: no per-frame wait-idle, CPU readback for native GPU-frame cores, per-frame pipeline recreation, `glFinish`, or `glReadPixels` hot path. **PASS** source/contract checks and accepted NDS Vulkan/GLES3 runtime diagnostics. Linux native GBA/Vulkan and NDS desktop OpenGL fallback Xvfb smoke also passed on the authorized Debian builder.
- RG-062: The shared screen-layout schema is the only enumeration for Settings and `Next Layout`; selecting/advancing recomputes render and touch geometry and persists. **PASS** Android NDS layouts/live preview/Save-Discard and Android 3DS legal-homebrew layout persistence. GBA hides the multi-screen control.
- RG-063: Native menu semantics remain aligned across macOS/Android/Linux where applicable, including Pad/Next Layout and draft Save Settings. **PASS** source/AVD acceptance for Android controls; Linux shares the portable runtime model and has package/runtime smoke, not a full manual UI acceptance.
- RG-064: **OWNER-VERIFIED runtime/audio evidence:** current macOS DMG GBA/NDS gameplay is smooth; current Android APK GBA/NDS gameplay is smooth; actual audible audio on both is smooth. This supersedes prior “audibility unverified” wording for GBA/NDS. It is not automated evidence, and it does not satisfy Android 3DS audio acceptance: two legal homebrew trials supplied no qualifying confirmed samples.
- RG-067: Android archive imports inspect ZIP and 7z entries safely, reject unsafe paths, preserve supported original suffixes, and ask rather than guess for multiple plausible candidates. **PASS** Kotlin/native tests and AVD ZIP/7z import with the XZ decoder dependency. No arbitrary archive extraction path is used.
- RG-068: Linux artifacts must be native packages, never browser-only substitutes. **PASS** for the fresh authorized Debian builds: the DEB (1,848,192 bytes, `1c6d0a9c14a3cc65ce41aaba2f76d2faf5836dbc9451cbb4558c8cd28950d304`) and Flatpak (1,835,048 bytes, `f6aa7b7010c92b81186d68ebd22cdaabe4a18140f7cbfc5991fe956a9ad9a7af`) each passed a controlled Xvfb core-frame launch with the native SDL/GTK path. Fresh staging HTTP stream size/SHA-256 parity passed for both.
- RG-069: Web and native renderer families remain separate. **PASS** behavior contract: a successful WebGPU initialization must set `effective=webgpu`; native prefers Vulkan then OpenGL/GLES fallback. Current `http://192.168.1.8:8092` is an insecure context with no `navigator.gpu`, so its `requestAdapter` → WebGL2 result is expected fallback evidence, not successful-WebGPU evidence.
- RG-070: Release Center fails closed on catalog byte drift and publishes only explicit staging artifacts. **PASS** fresh staging release `/opt/an3-arcade-staging/releases/20260912-182516-df14d4aa2d9a`: `/health` returned `environment=staging`; macOS DMG, Android APK, Linux DEB, and Linux Flatpak HTTP stream size/SHA-256 all matched the updated local catalog; Windows EXE remains blocked with no download URL. Production untouched.
- RG-071: A single-file Flatpak must include a verified runtime repository and install into a fresh user data root; it must not depend on a builder cache or a manually preinstalled GNOME runtime. **PASS on authorized Debian staging:** the prior bundle failed with `org.gnome.Platform/x86_64/49` missing; the fresh bundle imports Flathub runtime metadata, passed a disposable `flatpak --user install`, and launched the native binary. The reported Linux Mint host remains the required final environment acceptance.

## Current authority — P5 native migration, 2026-09-11 (COMPLETE WITH KNOWN LIMITATIONS)

The owner's architecture correction supersedes earlier Android WebView gameplay acceptance. P5's exact staging candidate is `cd98c834d5730f532b6e68a373072231c2519780822db9c6c30ff65e00086ff6`; browser tests remain browser evidence, while the evidence below is native Android AVD evidence. It is published only through staging asset `bef86865b122`, whose Release Center download matches the local 74,229,651-byte APK and SHA-256. No production access occurred.

- RG-057: Android normal gameplay uses the portable libretro host and SurfaceView/ANativeWindow. Auto selects native Vulkan, then native GLES3, then explicit failure; no browser fallback. Native settings are separate from web settings. **PASS** source/AVD: NDS ran through Vulkan and explicit saved/relaunched GLES3; Android 3DS is deliberately unavailable rather than advertised.
- RG-058: Native emulation runs once per scheduler tick even if presentation is unavailable; slots 1–10 and separate Auto Save remain raw files isolated from web states. **PASS** compiled fake-core behavioral test and exact-APK live path: slot 1 and slot 10 saved, timed Auto Save completed, state exported/imported, and slot 1 loaded after restart.
- RG-059: Native session calls are bound to their owning Activity. **PASS** source guard and repeated final-candidate restart/relaunch; the old-Activity ownership invariant remains source/behavioral-protected rather than inferred from the restart smoke.
- RG-060: Native Vulkan retains persistent mappings, two reusable slots, bounded aligned noncoherent flush, and no successful-frame wait-idle/readback; GLES uses a reusable texture/program/two PBOs and no `glFinish`/`glReadPixels`. **PASS** source/link guards and final NDS runtime at 59–60 core/present FPS under both Vulkan and explicit GLES3. Do not infer physical-device performance from this AVD.

- RG-061: Native input snapshots preserve a completed short button/pointer tap for one core frame; cancel clears pending touch. **PASS** behavioral host test; final AVD accepted tap/drag/release with no crash. Layout-specific touch proof is recorded separately under RG-062.
- RG-062: Android NDS selected layout is available before `retro_init`, retained through `retro_load_game`/GET_VARIABLE, and is never derived from orientation. **PASS** source/behavioral guards and final AVD: Side-by-Side and restored Top/Bottom both saved/relaunched, then accepted tap → drag → release on the visible touch-screen area without crash. The ROM supplied no distinct visual response, so no gameplay-effect claim is made.
- RG-063: Android native menu mirrors the DMG nine-section feature contract and Save Settings is a draft boundary. **PASS** final AVD: the horizontally scrollable row exposed all nine sections; changing Show FPS then backing out without Save reopened at the former persisted value.
- RG-064: Native AAudio accepts fractional core rates and negotiates integer output; bounded producer resampling supports gain/mute, speed and quality without callback allocation/blocking. **KNOWN LIMITATION:** stub/source test and runtime UI/counters pass, but no AVD speaker audibility is claimed.

- RG-065: Native surface resume is permitted only for the immediately successful transient snapshot and picker failures are handled. **PASS** source guards; state export/import was live-tested. Injected failed-snapshot recovery remains separately unverified.

- RG-066: Native Vulkan software blit uses IDENTITY transform and compositor rotation, with an explicit unsupported-transform failure instead of sideways/stretching output. **PASS** final portrait → landscape → portrait NDS runtime remained upright and unstretched; the persisted-layout touch result is separately accepted under RG-062.

Capture: per-run report from that release train, not retained in this repository.

## Current authority — P3 completion, 2026-09-09

P3 COMPLETE. Final staging e9cca6502858 adds renderer choice and safe diagnostics inside the existing options panel. No overall release CLEAN claim. 93 Python/12 Node tests and served-source parity PASS. Desktop diagnostics/copy, animated NDS output and AVD portrait/landscape options layout PASS. Fullscreen and extended input/menu matrix remain UNVERIFIED; P2 AVD gameplay limitation is retained.

- RG-054: persisted presentation choice applies only on restart; explicit URL choice wins, including Auto. Requested/effective/fallback are distinct. Storage denial must not prevent an explicit restart choice. Owner player-runtime.js/player.js; behavior tests cover precedence and denial.
- RG-055: copied diagnostics use named scalar fields only, preserve null/zero and sanitize fallback reasons to fixed text. Never serialize arbitrary session/renderer data, raw exceptions, private paths, cookies or ROM contents. Owner player-runtime.js/player.js; adversarial privacy test and live Copied result PASS.
- RG-056: player CSS must be pathname-versioned and included in immutable route allowlist and offline shell. Older query-insensitive service workers served stale CSS and clipped new controls. Owner app.py/service-worker.js; exact-byte route test and previously stale-origin live grid/overflow check PASS.

Report: per-run report from that release train, not retained in this repository.

## Current authority — release train P2, 2026-09-09T14:45:14+07:00

P2 is **COMPLETE** under the permitted insufficient-evidence classification after the user authorized an Android Virtual Device in place of the physical Redmi. Passive telemetry and desktop baselines are current; the AVD does not establish the Redmi root cause or authorize an optimization.

- RG-052: core/source FPS comes from deltas in EmulatorJS `gameManager.getFrameNum/get_current_frame_count` over wall time. It is never derived from rAF or renderer callbacks, and becomes null after a counter regression.
- RG-053: bitmap acquisition, worker render, presentation rate, rendered/dropped/replaced/skipped counts, UI pacing, long tasks, source/presentation dimensions and pixels, DPR, and requested/effective renderer remain separate fields. Diagnostics do not feed back into timing, input, menus, renderer selection, or fallback.
- Matched Mac New Game samples: WebGPU core 60.0001/presentation 60.0799 FPS; WebGL2 core 60.0143/presentation 59.9713 FPS. Both have zero dropped/replaced/skipped frames and sub-millisecond capture/render percentiles at 2560x1212, DPR2.
- Final staging asset af16e551490f has four-file source/served SHA-256 parity and a live explicit-WebGL2 telemetry smoke. 93 Python/9 Node tests PASS. The AVD host-GPU run showed core about38.5 FPS and presentation about60 FPS with inexpensive capture/render, but both source and presentation were black; WebGPU requestAdapter failed with correct WebGL2 fallback. SwiftShader stalled at completed startup. Classification is insufficient evidence for Redmi/visible gameplay, with a scoped virtual DEVICE/CPU/WASM signal only. No performance optimization was made. Production untouched.

Report: per-run report from that release train, not retained in this repository.

## Current authority — P1 completion, 2026-09-09T09:29:59+07:00

P1 **COMPLETE**; overall release readiness is not declared CLEAN. This supersedes the following September8 P1 blocker only within the evidence below; historical entries remain.

- RG-032/RG-038/RG-050: direct unchanged secure staging effective WebGPU/OffscreenCanvas shows animated NDS plus New Game/advancing dialogue. Explicit WebGL2 reaches menu; controlled adapter-null WebGPU→WebGL2 worker fallback reaches and advances dialogue. Renderer acceptance PASS for desktop Chromium.
- RG-010/RG-025/RG-028/RG-051: prior fresh final mounted DMG Escape rollback, explicit Save/relaunch and precedence PASS retained on unchanged artifact.
- RG-030/RG-033: status remains gameplay-unverified automatically; human runtime evidence supplies acceptance. Presentation counts/FPS overlay do not prove game progress.
- Browser autoplay activation can leave core frame5 with suspended OpenAL audio; trusted canvas click resumes. Do not diagnose renderer/core/ROM failure before a valid activation test or bypass browser policy. Preserve RG-043 auto-start. Short automation key taps (0.585ms observed) are not reliable input samples;133.8ms held virtual A advances dialogue without changing input code.
- Settings open/close, pointer-inert presentation/source ownership and fullscreen resize smoke PASS. Fresh physical Redmi, full audio/save/latency/layout/orientation matrix remains UNVERIFIED. Owner-confirmed prior Redmi tap/drag/gameplay evidence retained.
-93 Python/8 Node tests and syntax/native/diff checks PASS; four JS hash parity PASS; staging asset11290264c01d. Production untouched. No new application edits in resumed acceptance.

Report: per-run report from that release train, not retained in this repository.

## Current authority — release train P1, 2026-09-08T16:32:16+07:00

P1 and overall release readiness: **BLOCKED**. This section supersedes the historical integrity snapshot below only for the evidence explicitly listed. Other guards retain their unverified/known-limitation scopes; old PASS is not promoted to current acceptance.

- RG-010/RG-025/RG-028: shared closeMenuDiscardingDraft fixes Escape bypass. Fresh final mounted DMG Escape draft rollback and explicit Save Settings/relaunch PASS; keyboard capture/menu/library precedence PASS. Native NDS cursor release leaves game running. Audio, latency, save-state and complete settings matrix remain UNVERIFIED.
- RG-032/RG-038: worker COEP omission and missing WebGPU texture RENDER_ATTACHMENT are repaired. Secure staging effective=webgpu/offscreen=true and explicit WebGL2 frame submission PASS, but visible NDS gameplay FAILS in these launches. Controlled source-only white-output failure persists separately. No overall renderer gameplay PASS.
- RG-030/RG-033: boot and frame submission have separate readiness milestones; no automatic Playing label or gameplay acceptance from presentation counts. Optional telemetry is not mandatory.
- RG-034/RG-037/RG-038/RG-042/RG-045: current asset 11290264c01d, release /opt/an3-arcade-staging/releases/20260908-112644-11290264c01d. Served JS and DMG hash parity PASS. Final DMG SHA 37e24bf1d1d6c44ff3267c5649b16010f8bce076cc0bac632cddf17d431b975c. Fresh GBA launch/menu/relaunch and NDS visible title/intro PASS; full platform runtime matrix UNVERIFIED. Production untouched.
- RG-015/RG-017/RG-033/RG-043/RG-044/RG-048: preserve prior owner-confirmed Redmi Chrome tap/drag/gameplay response PASS. DEVICE_CONNECTED=no during P1 prevents fresh device verification and does not revoke that owner evidence.
- Baseline 91 Python PASS; after changes 93 Python PASS including renderer behavior wrapper, direct Node touch plus renderer 8 PASS, syntax/diff/native build checks PASS.

Captures: per-run reports and staging captures from 2026-09-08, not retained in this
repository. The asset hashes quoted in this section remain the durable record.

### Additional P1 guards

| ID | Invariant / cause / protected owner | Automated evidence | Current runtime evidence |
| --- | --- | --- | --- |
| RG-049 | Isolated player dedicated renderer workers require matching COEP require-corp on raw/versioned GET and HEAD; preserve CORP and CSP. Owner app.py serve_static. Missing worker header caused browser rejection before worker code. | test_integration.py verifies both routes/methods. | Same-byte isolated fixture fails without worker COEP and starts with it; current secure staging worker starts. |
| RG-050 | WebGPU external image destination includes COPY_DST plus RENDER_ATTACHMENT and TEXTURE_BINDING; validate init/first frame, retain stage/exception, close rejected bitmaps; fresh WebGL2 canvas precedes external fallback. Owner renderer-worker.js. | web_renderer_behavior.test.js and Python wrapper. | Original texture validation error reproduced; corrected synthetic output visible; staging submission works but real NDS gameplay remains failed. |
| RG-051 | Menu and Escape share one non-save draft-discard boundary without changing explicit Save or capture/cursor/library priority. Owner azahar_host.mm. | test_native_regression_guards.py close-path assertions. | Fresh mounted DMG draft rollback, saved preference relaunch, keyboard capture precedence PASS; original saved Show FPS restored. |
| RG-052 | Core/source rate uses independent core-counter deltas over wall time; rAF and presentation callbacks cannot populate it. A regressing counter invalidates the rate. Owner player-runtime.js. | web_renderer_behavior.test.js and Python wrapper. | Advancing Mac NDS New Game samples report approximately 60 core FPS with zero regressions. Redmi UNVERIFIED. |
| RG-053 | P2 diagnostics keep capture, worker render, presentation, UI pacing, long tasks, dimensions/DPR, renderer selection and frame-loss counters distinct and passive. Owners renderer-worker.js/player.js. | web_renderer_behavior.test.js and Python wrapper. | Mac WebGPU/WebGL2 matched scene PASS; final staging telemetry smoke PASS. Authorized AVD evidence classified insufficient for Redmi/visible gameplay. |

## Historical authority snapshot — 2026-09-08 integrity audit (pre-P1)


Current source, current staging, the fresh packaged artifact, and current owner
runtime evidence supersede historical PASS/PENDING statements. Historical
incidents and exact prior evidence are retained in
`reports/handoff/REGRESSION_GUARDS-before-integrity-20260908.md` and the incident
history below. The evidence column and matrix above/below now describe current
acceptance, not inherited release status.

OWNER-VERIFIED PHYSICAL DEVICE PASS: Redmi 15 5G, Android Chrome, actual NDS tap and drag/gameplay response. Not automated evidence.

This closes the older same-browser “physical touch pending”, bridge-only, and
DEVICE_CONNECTED=no limitations for actual tap and drag. It does not claim
Firefox acceptance or unobserved menu/fullscreen/orientation subcases.
The current harness also independently detects Android 16 / Chrome
152.0.7977.75 with DEVICE_CONNECTED=yes; no private identifiers were recorded.

Release readiness: BLOCKED by reproduced Settings Escape/draft behavior,
secure WebGPU worker initialization failure, and absence of a reproducible
advancing web gameplay scene for the comparative smoothness measurement.
The owner touch PASS remains valid and is not revoked by these separate issues.

### Evidence scope for every guard

`Source` below refers to the current 91-test Python suite plus focused Node
behavior tests and syntax checks; a passing suite is not proof of every live
invariant. `Package` refers only to fresh DMG SHA-256
`5e0de9ea7280b59f8ac71dc3f7dfd1e9bbcbd8c28ad9b57421055ee4d21c8d01`.
`Staging` uses asset `50d711002677`. N/A means that platform is outside the
specific guard; UNVERIFIED means its complete runtime acceptance was not run.

| Guard | Current source | Current staging | Current packaged app | Current owner runtime evidence |
| --- | --- | --- | --- | --- |
| RG-001 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-002 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-003 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-004 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-005 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-006 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-007 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-008 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-009 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-010 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | PASS first Escape closes menu only | No new owner assertion for this guard |
| RG-011 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-012 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-013 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-014 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | Identity/library smoke PASS; migration UNVERIFIED | No new owner assertion for this guard |
| RG-015 | Tests PASS; live limits apply | UNVERIFIED full runtime acceptance | N/A | OWNER-VERIFIED PHYSICAL DEVICE PASS — NDS tap + drag only |
| RG-016 | Tests PASS; live limits apply | UNVERIFIED full runtime acceptance | N/A | No new owner assertion for this guard |
| RG-017 | Tests PASS; live limits apply | UNVERIFIED full runtime acceptance | N/A | OWNER-VERIFIED PHYSICAL DEVICE PASS — NDS tap + drag only |
| RG-018 | Tests PASS; live limits apply | UNVERIFIED full runtime acceptance | N/A | No new owner assertion for this guard |
| RG-019 | Tests PASS; live limits apply | UNVERIFIED full runtime acceptance | N/A | No new owner assertion for this guard |
| RG-020 | Tests PASS; live limits apply | UNVERIFIED full runtime acceptance | N/A | No new owner assertion for this guard |
| RG-021 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-022 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-023 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-024 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-025 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | REGRESSION: Escape retains unsaved draft | No new owner assertion for this guard |
| RG-026 | Tests PASS; live limits apply | UNVERIFIED full runtime acceptance | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-027 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-028 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | REGRESSION: Escape retains unsaved draft | No new owner assertion for this guard |
| RG-029 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-030 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-031 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-032 | Tests PASS; live limits apply | LAN worker transport PASS; secure WebGPU FAIL; visible gameplay UNVERIFIED | N/A | No new owner assertion for this guard |
| RG-033 | Tests PASS; live limits apply | UNVERIFIED full runtime acceptance | N/A | OWNER-VERIFIED PHYSICAL DEVICE PASS — NDS tap + drag only |
| RG-034 | Tests PASS; live limits apply | UNVERIFIED full runtime acceptance | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-035 | Tests PASS; live limits apply | UNVERIFIED full runtime acceptance | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-036 | Tests PASS; live limits apply | UNVERIFIED full runtime acceptance | N/A | No new owner assertion for this guard |
| RG-037 | Tests PASS; live limits apply | PASS current staging deployment checks | N/A | No new owner assertion for this guard |
| RG-038 | Tests PASS; live limits apply | PASS current staging deployment checks | N/A | No new owner assertion for this guard |
| RG-039 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | Prior affected-device crackle remains KNOWN LIMITATION |
| RG-040 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-041 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-042 | Tests PASS; live limits apply | N/A or shared web subcase UNVERIFIED | Nine tabs + visible NDS gameplay PASS; remaining flows UNVERIFIED | No new owner assertion for this guard |
| RG-043 | Tests PASS; live limits apply | UNVERIFIED full runtime acceptance | N/A | OWNER-VERIFIED PHYSICAL DEVICE PASS — NDS tap + drag only |
| RG-044 | Tests PASS; live limits apply | UNVERIFIED full runtime acceptance | N/A | OWNER-VERIFIED PHYSICAL DEVICE PASS — NDS tap + drag only |
| RG-045 | Tests PASS; live limits apply | PASS current staging deployment checks | N/A | No new owner assertion for this guard |
| RG-046 | Tests PASS; live limits apply | UNVERIFIED full runtime acceptance | UNVERIFIED full runtime acceptance | No new owner assertion for this guard |
| RG-047 | Tests PASS; live limits apply | UNVERIFIED full runtime acceptance | N/A | No new owner assertion for this guard |
| RG-048 | Tests PASS; live limits apply | UNVERIFIED full runtime acceptance | N/A | OWNER-VERIFIED PHYSICAL DEVICE PASS — NDS tap + drag only |

## Guard ledger

| ID | Scope and invariant | Historical failure → symptom → cause → actual fix | Do-not-regress patterns; owners; blast radius | Automated guard | Runtime reproduction and acceptance | Evidence / last verified / confidence |
| --- | --- | --- | --- | --- | --- | --- |
| RG-001 | Native video must remain software framebuffer → Vulkan → MoltenVK → Metal for GBA/NDS, and GPU image → VulkanFrontend → MoltenVK → Metal for 3DS. | CPU readback and per-frame device idle were identified as smoothness regressions; native persistent mapped buffers and the 2/3-frame ring removed the synchronous path. | No GPU→CPU→GPU copy, per-frame resource rebuild, or queue/device idle in the draw path. Owners: `vulkan_frontend.*`, `azahar_host.mm`. Blast: native GBA/NDS/3DS. | `test_native_renderer_contract.py`, `test_native_regression_guards.py`. | Packaged GBA/NDS/3DS run at 1×; inspect frame pacing and the renderer path. Acceptance: no readback or per-frame idle and stable presented frames. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-002 | NDS/3DS screen layout is an explicit per-system preference and survives menu, fullscreen, speed, save/load, and restart. | A speed/settings pass silently restored Top/Bottom; the fix made Side-by-Side the stored/default-aware layout and preserved it across relaunch. | Never infer layout from transient window orientation after a saved preference exists. Owners: `azahar_host.mm`, `azahar.rs`, `offline.js`, `native-bootstrap.js`. Blast: native dual-screen UX and web NDS mapping. | Native and web layout contract tests. | Set Side-by-Side, open/close menu, fullscreen, speed, save/load, restart. Acceptance: same layout remains. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-003 | Native NDS relative input uses right +X, left -X, down +Y, up -Y. | Earlier cursor movement was directionally inverted because the host transform used the wrong sign convention; `native_input_transform.h` now makes the screen-facing convention explicit. | Keep host/core coordinates separate from UI coordinates. Owner: `native_input_transform.h`, `azahar_host.mm`. Blast: native NDS touch. | Native input contract and regression tests. | Slow and fast directional drags in packaged NDS. Acceptance: cursor follows finger in all four directions. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-004 | Native NDS cursor movement is direct and continuous at 1×, not just sign-correct. | Fractional scheduling produced 0/2 `retro_run` frame polls and visible lag; the fix uses atomic deltas and exactly one core frame per draw at 1×. | No debounce, timer, smoothing, or “helpful” coalescing on the input-to-core path. Owners: `azahar_host.mm`, scheduler. Blast: native NDS interaction. | `test_native_regression_guards.py` scheduler/input assertions. | Move the cursor slowly, quickly, across screen edges. Acceptance: no skipped first movement, no trailing motion, no visible 0/2 cadence. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-005 | GBA, NDS, and 3DS audio is audible at 1× and survives repeated play. | Queue counters showed progress after a converter reached EndOfStream/zero frames; the repair converts interleaved S16 to planar Float32 explicitly and uses `NoDataNow` between realtime batches. | Do not use queue growth as proof of sound; keep bounded PCM peak/nonzero checks and do not terminate the realtime converter. Owner: `azahar_host.mm` audio. Blast: all native cores. | Audio callback/source assertions in native regression tests. | Packaged GBA/NDS/3DS speaker and Bluetooth checks at 1×. Acceptance: audible output and no terminal converter state. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-006 | Supported GBA ROMs reach gameplay, return, and relaunch. | Malformed Core Options v2 fields crashed AppKit while building the menu; the host now consumes the real v2 ABI. | Never construct popup metadata from v1/v2 fields interchangeably. Owners: `core_options.h`, `azahar_host.mm`. Blast: packaged GBA launch and menu. | Native GBA launch/ABI tests. | Launch a known GBA ROM, open menu, return to library, launch again. Acceptance: no abort, exception, or blank runtime. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-007 | Keep 0.5×, 1×, 2×/4×/8× three-button controls; a new session is 1× and max is 8×. | Speed UI and native scheduler changes risked conflating display FPS with emulation multiplier; controls and host values are now explicit. | Never let FPS telemetry alter the core speed. Owners: `azahar_host.mm`, `player.js`, `player-runtime.js`. Blast: native/web play. | Native and player speed contract tests. | Cycle down/up through all values, restart, save/load. Acceptance: clean 1× start and exact displayed values. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-008 | Exactly ten user Quick Save slots, 1–10, remain native and web. | Slot UI and migration work risked losing the hidden fifth slot or changing the public count; slot enumeration remains 1 through 10. | Do not add a slot 0, remove slot 5, or derive slot count from available files. Owners: `azahar_host.mm`, `offline.js`, `player-runtime.js`. Blast: user save data. | Slot-count and path tests. | Open save UI; verify slots 1 and 10 and hidden slot 5; save/load each boundary. Acceptance: ten stable user slots. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-009 | Auto Save is independent `<rom_id>.autosave.state`, never a Quick Save slot. | Auto Save was at risk of overwriting a numbered slot during migration; it now has a separate path and lifecycle. | Keep Auto Save out of the 1–10 namespace and test it with a dirty game state. Owners: native save manager and web save runtime. Blast: recovery data. | Save path/name assertions. | Enable/use Auto Save, make a numbered save, restart. Acceptance: both states remain independently loadable. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-010 | Escape closes an open game menu first, consumes the event, and leaves the game running; a second Escape exits. | Escape previously leaked through the menu and exited the player unexpectedly; menu priority now runs before game exit. | Menu state owns Escape before library/navigation state. Owner: `azahar_host.mm`. Blast: native menu and exit semantics. | Native menu key tests. | Open menu; press Escape once, then twice. Acceptance: first closes only; second exits. | PASS current packaged first Escape closes menu and leaves game running; settings draft defect tracked in RG-025/RG-028. |
| RG-011 | Import/Export `.state` keeps raw serialization, bounds checks, and no quick-slot overwrite. | State import/export and slot migration could be confused by a shared path; explicit file handling and bounds checks preserve separation. | Never parse external `.state` into a numbered slot implicitly; reject oversized/truncated payloads. Owners: native state API and web state controls. Blast: user save data. | Native state and web state contract tests. | Export, modify, import, and load a `.state`; inspect all ten slots. Acceptance: round trip works and slots are unchanged. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-012 | Native FPS and presented-frame telemetry remain display diagnostics, never an emulation-speed multiplier. | A frame-rate audit risked using telemetry as a multiplier; scheduler and display counters remain separate. | No FPS-driven `retro_run` multiplier; 1× is exactly one core frame per draw. Owners: `azahar_host.mm`, `vulkan_frontend.*`. Blast: timing and speed. | Scheduler and FPS guard tests. | Run at 1× and 8× while watching FPS; acceptance: FPS reports presentation, speed remains selected multiplier. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-013 | Volume label, flexible slider, and percent label fit inside the AppKit panel at minimum and wide sizes. | Volume overflow appeared at ~480–600 px; the row now uses flexible layout and bounded controls. | Do not use fixed widths that force the percent label outside padded content. Owner: `azahar_host.mm` AppKit menu. Blast: native settings usability. | Layout/source guard tests. | Inspect minimum, ~480, ~600, desktop, and fullscreen menu sizes. Acceptance: no clipped or overflowing slider/label. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-014 | Preserve VibeCodedEmulator identity and existing bundle/data/ROM/state/IndexedDB/keymap paths. | Product rename and native-offline work could strand local data; identity and path contracts remain unchanged. | No namespace migration without an explicit compatibility plan. Owners: Tauri config, native bootstrap, web persistence. Blast: all existing users. | Native identity/path tests. | Upgrade an install containing ROMs, saves, and keymap settings. Acceptance: data is still visible and loadable. | PASS fresh app identity and existing local library visible; upgrade/data migration beyond this smoke UNVERIFIED. |
| RG-015 | Web NDS touch always dispatches to the EmulatorJS source canvas, never the visible `.an3-render-canvas` presentation layer or protected UI. | The renderer bridge added a visible canvas above the hidden source; `protectNdsCanvas()` then applied `pointer-events:auto!important` to both, so hit-testing selected the presentation canvas and EmulatorJS saw no input. The follow-up menu recurrence showed that a source fallback is valid for a presentation hit but invalid for a menu/settings hit. Fix: source-only selectors, noninteractive presentation CSS, a shared resolver, and protected-UI rejection. | Presentation canvas is output-only; never bind touch listeners or force pointer events on it. A menu/panel/toolbar/virtual-control origin must return to its UI owner and never be redirected to source. Owners: `nds-touch.js`, `player.js`, `renderer-worker.js`, `site.css`. Blast: web NDS touch, menu access, and 3DS renderer input. | `test_web_nds_touch_behavior.py`; player/site static assertions; realistic DOM ownership cases. | On staging, with renderer bridge active, tap the lower NDS screen and then a native menu item. Acceptance: debug path names `canvas.ejs_canvas` for gameplay, while menu interaction produces no NDS dispatch. | OWNER-VERIFIED PHYSICAL DEVICE PASS: Redmi 15 5G, Android Chrome, actual NDS tap and drag/gameplay response. Not automated evidence. Extended menu/layout/orientation cases remain separately unverified. |
| RG-016 | Web NDS mapping supports Top/Bottom and Left/Right, scaled/aspect-fitted/letterboxed canvases, with only the touch-screen half mapping to 256×192. | The old mapper always subtracted half the height, so Side-by-Side clicks mapped incorrectly; the shared mapper now chooses the configured half and rejects margins/other screen. | Never infer a fixed top-bottom geometry from `videoWidth/videoHeight`; use the resolved viewport and applied core layout. Owners: `nds-touch.js`, `player.js`. Blast: web NDS pointer accuracy. | Node behavioral geometry tests cover both layouts, scaling, margins, edge coordinates. | Tap center, all four corners, other screen, and letterbox margins in both layouts. Acceptance: exact normalized DS coordinates and no false touches. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-017 | Web NDS touch has a complete press→move→release/cancel lifecycle, preserves pointer capture, and does not leave a stuck button, including when menu/fullscreen/blur interrupts a gesture. | First-tap and Android retargeting regressions arose when events were bound only to the canvas; root/document listeners and release handling now cover retargeted gestures. Menu-open detection additionally releases active root gestures before protected UI takes over. | Prevent default only after accepting a gameplay touch; release on `pointerup`, `pointercancel`, `touchend`, `touchcancel`, menu open, visibility loss, and fullscreen transition; never synthesize gameplay input for protected UI. Owner: `player.js`. Blast: NDS touchscreen, menu access, and browser scroll. | Node gesture/ownership sequence test plus source assertions. | Drag off the canvas, release, cancel, open menu before release, blur/fullscreen, re-enter, and repeat. Acceptance: one down, continuous movement, one release, no stuck pointer, and no menu-origin NDS event. | OWNER-VERIFIED PHYSICAL DEVICE PASS: Redmi 15 5G, Android Chrome, actual NDS tap and drag/gameplay response. Not automated evidence. Extended menu/layout/orientation cases remain separately unverified. |
| RG-018 | Player layering is game output base, NDS touch above it, status below toolbar, toolbar above pad, options/save panels above all; EmulatorJS menu temporarily owns the top layer and protected UI owns its own events. | Historical failure: refresh stacking placed the virtual pad above the native EmulatorJS menu and the root bridge rebound menu-origin touches to an arbitrary canvas. The current recurrence: source-canvas recovery restored gameplay input but allowed protected menu events to fall through the resolver. Fix: keep the current source/presentation relationship, lower/inert `#tvPad` to z-index 19 while `emulator-menu-open`, keep the native menu inside `#game` at its existing z-index 9999, and reject protected targets before preventDefault/resolve/dispatch. | Keep `#tvPad` buttons interactive while the menu is closed, pad background transparent, menu-open pad inert, and no full-screen pointer layer above the game. The source canvas may remain pointer-enabled structurally; ownership is decided by target/composed path. Owners: `site.css`, `player.js`, `nds-touch.js`, `docs/player-layering.md`. Blast: all touch/player controls. | Layering/static tests and realistic DOM ownership/release tests. | Open pad, native menu, Settings, AN3 options, save slots, modal/dialogs, and fullscreen/resize; tap each owner. Acceptance: native menu/Settings first, then AN3 panels, toolbar, virtual controls, NDS gameplay, with no event leakage. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-019 | EmulatorJS menu precedence is deterministic: custom options close before native menu opens, native menu detection keeps `emulator-menu-open` current, protected UI events never reach NDS, and custom overlays cannot open above an active native menu. | Native menu priority was lost during virtual-pad work; menu mutation observation and `emulator-menu-open` state restore the priority. The source-canvas recovery recurrence bypassed visual z-index by allowing the root bridge to resolve a menu descendant to `.ejs_canvas`; the resolver now rejects menu/panel/toolbar/virtual-control composed paths, and menu-open sync releases an active gesture. | Preserve the `.ejs_menu_bar,.ejs_popup_body,.ejs_context_menu` MutationObserver, menu click refresh, z-index exception, AN3 option auto-close, and no broad arbitrary z-index increase. Owners: `player.js`, `nds-touch.js`, `site.css`. Blast: menu access and touch. | Regression invariant tests plus menu/settings/virtual-pad behavioral ownership cases. | With pad visible, open native menu on first tap, select Settings, change a setting, close menu, and tap gameplay. Acceptance: menu/settings actions work on first interaction, no NDS debug event is produced by UI taps, active gestures release cleanly, and gameplay resumes immediately. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-020 | Physical keyboard remains routed to EmulatorJS while custom touch owns only touch/pointer gestures. | Touch-first desktop and canvas listeners risked suppressing keyboard focus; keyboard behavior remains a separate path. | Do not globally prevent keyboard events or steal focus from the emulator. Owner: `player.js`, EmulatorJS host. Blast: desktop play. | Source guard for no global keyboard interception. | Focus player, use arrows/A/B/Start/Escape. Acceptance: keyboard works with pad hidden and shown. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-021 | GBA launch does not crash AppKit and returns to a usable library/player state. | Same as RG-006, retained as a separate launch smoke because the crash was first observed as a packaged user regression. | GBA smoke is mandatory after shared host/menu/Core Options edits. Owners: native host and packaging. Blast: entry point for every GBA user. | Native regression tests and build. | Fresh packaged GBA launch, open menu, exit, relaunch. Acceptance: no crash and status transitions are truthful. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-022 | Core Options v2 ABI and namespace are exact, including v2-intl handling and no v1 field reads from v2 storage. | Wrong struct layout/namespace caused malformed popup data and AppKit crash; `core_options.h` and `azahar_host.mm` now use the actual v2 ABI and v2-intl namespace. | Treat core options as ABI, not a best-effort dictionary; guard null/terminator bounds. Owners: core headers and host. Blast: menu construction for GBA/NDS/3DS. | ABI/source tests. | Open core options for each native core. Acceptance: options render, change, and return without crash. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-023 | Audio repair must cover all native cores and distinguish audio callback delivery from speaker audibility. | A converter terminal state caused silence despite nonzero queue counters; explicit sample conversion and realtime `NoDataNow` fixed delivery. | No speculative device-specific “fix”; retain the Redmi 15 5G crackle as a known limitation until reproduced/fixed. Owner: native audio/QA. Blast: all native audio. | PCM conversion/callback tests. | Speaker and Bluetooth smoke for GBA/NDS/3DS, including 1× and menu transitions. Acceptance: audible output; crackle is recorded separately. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-024 | Scheduler/frame pacing owns emulation timing; drawing/presentation cannot add fractional duplicate/skipped core runs. | 1× stutter came from polling/scheduling mismatch; native draw now runs one core frame at 1× and explicit multiple runs only for selected speed. | No idle wait to “stabilize” timing; no telemetry feedback loop. Owners: `azahar_host.mm`, frontend. Blast: speed, cursor latency, video. | Native scheduler tests. | Compare 1×, 2×, 8× and inspect core-frame count. Acceptance: 1× one frame/draw; selected multipliers only. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-025 | Native layout, settings tabs, and Save Settings semantics are stable: draft changes apply only on Save/explicit Apply, and tabs remain General, Graphics, Audio, Keyboard, Controller, Emulation, Save States, Diagnostics, About. | Settings refreshes risked losing tabs or applying drafts unexpectedly; the AppKit tab contract and draft semantics were established in the settings audit. | Do not collapse tabs into one uncontrolled panel or persist a draft on cancel. Owners: `azahar_host.mm`. Blast: native configuration. | Settings tab/source contract tests. | Change a draft, cancel/close, reopen; then Save Settings and relaunch. Acceptance: cancel discards, save persists, all tabs render. | REGRESSION reproduced in fresh DMG: Escape closes without discarding unsaved Show FPS preview. Menu-button close discards correctly; Save Settings acknowledges save. See integrity handoff. |
| RG-026 | Fullscreen/orientation changes recompute touch mapping and do not reset the persisted dual-screen layout. | Landscape/fullscreen reset the layout and made touch hit stale viewport coordinates; resize/fullscreen listeners now re-evaluate geometry while preserving explicit preference. | Invalidate viewport cache on gesture start/resize; never use stale WebGL viewport or window orientation as a stored preference. Owners: `player.js`, native layout. Blast: web/native dual screen. | Web/source resize guards; native layout tests. | Enter/exit fullscreen in portrait and landscape; rotate/rescale; tap known screen corners. Acceptance: coordinate accuracy and unchanged selected layout. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-027 | Native volume slider and panel are flex-safe at minimum/wide sizes, with label and percentage inside content bounds. | Same regression as RG-013, retained for the settings audit category. | No fixed-width slider/label combination that overflows on narrow panels. Owner: `azahar_host.mm`. Blast: native audio settings. | Layout contract tests. | Resize panel to 480/600 px and inspect min/max volume. Acceptance: no clipping/overflow. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-028 | Settings tab selection and Save Settings do not alter gameplay state, layout, speed, or save slots unintentionally. | Tab and save work risked applying unrelated drafts; explicit draft/apply boundaries are now documented. | Keep settings persistence separate from runtime state and numbered saves. Owners: native settings and web player settings. Blast: settings and saves. | Settings/source tests. | Modify graphics/audio/controller draft, cancel, save, restart. Acceptance: only intended settings change. | REGRESSION reproduced in fresh DMG: Escape closes without discarding unsaved Show FPS preview. Menu-button close discards correctly; Save Settings acknowledges save. See integrity handoff. |
| RG-029 | Quick Save 1–10, hidden slot 5, migration, Auto Save, and `.state` import/export remain separate namespaces. | Multiple save migrations could overwrite slot 5 or Auto Save; explicit filenames and count checks protect the legacy data model. | Never “simplify” by renumbering or merging paths. Owners: native save manager, `offline.js`, `player-runtime.js`. Blast: irreversible user data loss. | Save path/migration tests. | Populate slots 1, 5, 10 and Auto Save; migrate/restart; import `.state`. Acceptance: all remain independently visible/loadable. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-030 | Product rename, FPS telemetry, and status text remain cosmetic/diagnostic and do not change identity, timing, or core state. | Rename and performance work could accidentally change storage keys or make “Playing” a proxy for a frame; identity and telemetry are now isolated. | Never use status text/telemetry as a gameplay readiness proof. Owners: native/web status and identity. Blast: data and truthful UX. | Identity/FPS/source tests. | Upgrade, play, watch FPS, change speed, reload. Acceptance: data paths and speed remain stable. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-031 | Native Vulkan ring path has no readback, no per-frame wait-idle, and bounded reusable resources. | Performance inspection found synchronous readback/idle hazards; persistent mapped buffers and bounded ring were introduced. | Keep ring size bounded, close/recycle resources, and avoid “fixing” contention with device idle. Owners: Vulkan frontend and host. Blast: native smoothness/battery. | `test_native_renderer_contract.py`. | Run packaged games and inspect diagnostics/latency. Acceptance: steady frame delivery without per-frame stalls. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-032 | Web renderer boundaries are truthful: worker/OffscreenCanvas/ImageBitmap latest-wins path is bounded; WebGPU requested vs WebGL2 effective is reported; SAB requires isolation. | Earlier phase handoff described worker/SAB as not implemented, while later dirty source added a real bridge; current source is the authority but runtime must verify it. | Close replaced/pending bitmaps; keep two-frame ring; distinguish requested/effective backend; never claim SAB on HTTP. Owners: `player-runtime.js`, `renderer-worker.js`, `player.js`. Blast: web rendering and 3DS. | Phase1 renderer contract and new web tests. | Inspect `AN3RendererStatus`: offscreen active, effective backend, dropped frames, SAB/isolation. Acceptance: bounded latest-wins and truthful fallback. | PARTIAL: current LAN WebGL2 worker frames advance; visible NDS gameplay not proven in audit launch. Secure Android WebGPU initialization FAILS; effective external-core-canvas, Render worker failed. |
| RG-033 | “Playing” is not proof of a visible, interactive game: status requires core readiness, render path, and input smoke. | Source-only audit marked web GBA/NDS `GOOD` without a current ROM run; live staging could show `Playing` while NDS touch was dead. | Never close a feature as GOOD from AX state, source contracts, telemetry, or absence of console errors alone. Owners: player runtime and QA. Blast: all browser play acceptance. | Live smoke checklist plus regression tests. | Load a known ROM, verify visible frame, tap/keyboard input, release, resize. Acceptance: render and interaction both pass; otherwise `UNVERIFIED`. | OWNER-VERIFIED PHYSICAL DEVICE PASS: Redmi 15 5G, Android Chrome, actual NDS tap and drag/gameplay response. Not automated evidence. Extended menu/layout/orientation cases remain separately unverified. |
| RG-034 | ROM delivery, core cache, IndexedDB, and service worker keep versioned player assets and do not silently serve stale or wrong files. | Stale PWA/core caches and UUID-only native ROM URLs caused core-load failures; versioned routes, extension-preserving delivery, and dedicated core cache fixes were added. | Add every boot asset to the versioned allowlist and service-worker shell; never mix production/staging cache roots. Owners: `app.py`, `service-worker.js`, `offline.js`. Blast: web/offline launch. | Integration route/cache tests. | Cold-load ROM, reload under service worker, offline reload, migrate cached core. Acceptance: correct asset version and ROM extension; no stale Playing state. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-035 | Responsive/fullscreen/orientation layouts preserve playable canvas, status, pad, and toolbar bounds on narrow/short/landscape screens. | Short fullscreen devices hid the pad and stale aspect-fit viewport rotated incorrectly; safety checks and resize/fullscreen handling preserve usable geometry. | No viewport-width assumptions that hide controls or create horizontal overflow; keep `min-width:0` in flex/grid player containers. Owners: `site.css`, `player.js`. Blast: mobile/browser UX. | CSS/source and DOM geometry tests. | Test portrait, landscape, short fullscreen, browser bars, and resize. Acceptance: no horizontal scroll, hidden usable pad, or clipped status. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-036 | Touch controls never overlap each other, the game touch surface, toolbar, menu, or status; individual/global scale changes are safety-checked. | Pad scaling and overlay refresh could overlap controls or make them unreachable; constrained positions and collision checks reject unsafe settings. | Do not bypass `inspectCurrentButtonScales`, bounds, or overlap checks; pad background remains pointer-inert. Owners: `player.js`, `site.css`. Blast: all touch systems. | Regression invariant and player behavior tests. | Show pad, resize/fullscreen, scale/move each control, open menu/options. Acceptance: controls fit and game/menu ownership remains correct. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-037 | Staging and production are isolated in service names, paths, cache roots, URLs, data, and deploy commands. | Deployment/migration work exposed risk of cross-environment changes; staging-first scripts and explicit production approval are now mandatory. | Never run production deploy/restart/health/data access for this task; never alter production symlinks. Owners: deploy scripts and operators. Blast: service/data integrity. | Deployment/static isolation tests. | Verify staging health and asset only; production remains untouched. Acceptance: no production command or state change in task evidence. | PASS staging-only health, release and DMG publication; production untouched. |
| RG-038 | Staging asset version, immutable headers, CSP/COOP/COEP, and worker script delivery match the deployed source. | Browser cache and cross-origin isolation differences made worker/3DS behavior appear inconsistent; asset fingerprint and headers are part of every smoke. | Record active release, rollback release, asset version, and headers; do not call the unversioned artifact the verified one. Owners: staging deploy/health. Blast: reproducibility and SAB/WebGPU. | Integration HTTP/header tests. | Fetch `/health`, versioned boot assets, service worker; inspect headers. Acceptance: 200, immutable assets, expected isolation policy. | PASS six deployed source hashes, served versioned assets and substituted service-worker template. Current asset 50d711002677, release 20260908-093537-50d711002677, rollback 20260908-001932-50d711002677. |
| RG-039 | Native 3DS Redmi 15 5G speaker/Bluetooth crackle remains an explicit unresolved limitation until a reproducible fix is proven. | Crackle reproduced in Firefox/Chrome/Mi Browser and speaker/Bluetooth; low profile, 1×, and VSync changes did not prove a fix. | Do not label it fixed from queue counters or another device. Owner: native audio/QA. Blast: 3DS audio on affected device. | Regression test keeps the limitation documented; no false PASS. | Reproduce on the affected Redmi device and compare speaker/Bluetooth at 1×. Acceptance for closure requires before/after recordings and no new silence. | KNOWN LIMITATION retained: affected-device 3DS audio crackle has no new closure evidence. |
| RG-040 | Native 3DS GPU image path stays zero-readback and compatible with VulkanFrontend; no fallback to a CPU copy is introduced to mask visual issues. | Azahar in-process Vulkan and image path were added during native renderer work; performance contract protects it. | Keep 3DS-specific GPU image import separate from GBA/NDS software buffers. Owners: `azahar_host.mm`, `vulkan_frontend.*`. Blast: 3DS performance. | Renderer contract tests. | Packaged Pokémon X/3DS run; inspect stable frame path. Acceptance: visible frames without GPU readback or per-frame idle. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-041 | Native input direction and latency are separately guarded; a direction fix must not reintroduce polling/stutter. | Sign inversion and 0/2-frame cursor cadence were separate packaged regressions and received separate fixes. | Any input edit must run direction and latency smokes, not only one. Owners: native transform, scheduler, host. Blast: NDS controls. | RG-003/RG-004 tests. | Four-direction and slow/fast drag in packaged NDS. Acceptance: correct direction and continuous response. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-042 | Tauri native identity, offline bundle, native commands, ROM import, and web fallback paths remain isolated and compatible. | Native-offline packaging and rename work could mix web routes or change bundle identity; native shell keeps local-only data and explicit commands. | No web account/dashboard/production data in native shell; package all required player assets. Owners: `native-offline/`, Tauri config. Blast: native distribution. | Native staging contract and bundle tests. | Install/open native shell offline, import ROM, launch, save, relaunch. Acceptance: local-only workflow works. | PARTIAL: fresh DMG built, signed, mounted, launched; all nine Settings tabs exercised and existing NDS gameplay visible. Full offline/import/save acceptance UNVERIFIED. |
| RG-043 | NDS web core remains melonDS with auto-start, NDS ZIP delivery, and EmulatorJS IndexedDB core contract. | Legacy DeSmuME/manual start and non-ZIP delivery caused blank/non-starting NDS; melonDS auto-start and ZIP route became the protected path. | Do not reintroduce DeSmuME or a manual start button; preserve report-first core selection and cache. Owners: `player.js`, `app.py`, `offline.js`. Blast: web NDS boot. | Regression invariant and integration tests. | Cold-load a known NDS ZIP on staging and offline shell. Acceptance: core starts automatically and reaches visible gameplay. | OWNER-VERIFIED PHYSICAL DEVICE PASS: Redmi 15 5G, Android Chrome, actual NDS tap and drag/gameplay response. Not automated evidence. Extended menu/layout/orientation cases remain separately unverified. |
| RG-044 | Android regression harness covers first tap, cursor drag, pad/menu precedence, fullscreen, and release on owner-approved devices without collecting private device identifiers. | First tap and wrong relative motion repeatedly regressed across Android browsers; the geometry-mapped bridge and harness became the acceptance path. | No root/device serial logging; browser-specific results must be named. Owners: `reports/android-regression/`, player QA. Blast: Android NDS users. | Harness/static checks where available. | Chrome Android: direct tap/drag/release, pad, menu, fullscreen; Firefox separately records known white-canvas limitation. Acceptance: Chrome path passes; limitations remain explicit. | OWNER-VERIFIED PHYSICAL DEVICE PASS: Redmi 15 5G, Android Chrome, actual NDS tap and drag/gameplay response. Not automated evidence. Extended menu/layout/orientation cases remain separately unverified. |
| RG-045 | Deployment packaging removes AppleDouble/metadata contamination and health/backup scripts remain portable and quoted. | `._*` files contaminated deploys; health parser quoting and GNU `find` assumptions broke operational scripts. Fix: `COPYFILE_DISABLE`, cleanup, portable shell quoting. | Do not add password helpers or unverified SSH; staging key-only strict host checking is required. Owners: deploy scripts/operations. Blast: release reliability. | Deployment/source tests. | Build staging archive, inspect names, run staging health/backup check. Acceptance: clean archive and parseable health. | PASS staging package and health; harmless SCHILY.fflags archive warnings recorded. No AppleDouble failure. |
| RG-046 | Offline browser-local ROM/save data, core cache, keymap, and service-worker shell remain local and recoverable across reload/update. | PWA/core cache and migration changes risked deleting or aliasing user-local data; dedicated core cache and stable local keys preserve it. | Do not upload offline ROMs or merge local data with production; preserve old cores while replacing shell caches. Owners: `offline.js`, `service-worker.js`, native shell. Blast: privacy and data loss. | Offline consolidation, integration, and native bundle tests. | Import local ROM, save, reload offline, update shell, reload again. Acceptance: ROM/save/core remain available without network. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-047 | Protected UI events are never redirected into the NDS source canvas. | A menu-origin touch can still hit the `#game` root while the source canvas remains structurally present. A resolver fallback that is correct for `.an3-render-canvas` is unsafe for `.ejs_menu_bar`, `.ejs_context_menu`, `.ejs_popup_body`, AN3 panels, toolbar actions, or virtual controls. | Check `event.target` and `composedPath()` before `preventDefault`, canvas resolution, pointer capture, or synthetic NDS dispatch; release any active NDS gesture when a native menu opens. Owners: `nds-touch.js`, `player.js`. Blast: native EmulatorJS menu, Settings, save/options panels, virtual controls, and NDS touch. | Realistic DOM ownership test plus player static assertions. | With a real NDS player and `ndsdebug=1`, tap gameplay, menu/Settings, AN3 options, save slots, virtual buttons, and then gameplay after close. Acceptance: only gameplay emits NDS dispatch; UI owners receive their first tap; active menu-open gestures release once. | UNVERIFIED current full live acceptance; historical evidence retained, not inherited as current PASS. |
| RG-048 | A valid mobile web NDS touchscreen `DOWN → UP` with zero MOVE registers exactly one discrete press and one release. | Historical Android first-tap/retargeting fixes established document-level release and geometry-mapped source dispatch. The recurrence left desktop click and mobile drag working while mobile tap failed. A real Android Chrome trace showed the down did reach `canvas.ejs_canvas`, but the accepted zero-move press lasted only 3–6 ms before up—too short for the emulator input loop to observe. The same trace showed synthetic touch-compatibility mouse moves reaching EmulatorJS’s parent-level desktop menu observer, which cancelled a drag. | After protected-UI rejection and touchscreen mapping, TouchEvent owns exactly one physical finger; a zero-move release waits for one animation/input-frame boundary, while moves and cancels release immediately. The proven synthetic pointer+mouse source contract remains, but untrusted touch-compatibility mouse events stop at the source canvas and cannot bubble into the parent desktop-menu observer. Use `changedTouches` at end; no movement threshold, synthetic DOM click, broad `preventDefault` removal, presentation-canvas input, or second-finger takeover. Owners: `static/nds-touch.js`, `static/player.js`. Blast: mobile Chrome NDS tap/drag, menus, Settings, virtual pad, layouts, fullscreen. | `tests/web_nds_touch_behavior.test.js` covers pointer tap, realistic touch end, Chromium pointer/touch ownership, tap-vs-drag, very-short latch, protected UI, repeat taps, post-drag/menu taps, and both layouts; Python wrapper and regression invariants protect latch, release, source ownership, and menu shielding. | On the same failing mobile browser, verify a known NDS UI tap, five taps, very short/long presses, drag→tap, menu-close→tap, menu/Settings, virtual pad, layouts, fullscreen, and orientations. `ndsdebug=1` must show `logical-down`, `moveCount=0`, `logical-up`, and one released synthetic up. | OWNER-VERIFIED PHYSICAL DEVICE PASS: Redmi 15 5G, Android Chrome, actual NDS tap and drag/gameplay response. Not automated evidence. Extended menu/layout/orientation cases remain separately unverified. |

## Audit matrix for every change

The following matrix is the required release checklist. “Static” means source,
route, or contract assertions; “behavioral” means a DOM/Node/native harness
exercises the transition; “live” means a packaged app or browser runtime with
the actual feature. A blank live cell is not a PASS.

| # | Audit category | Static test | Behavioral test | Live runtime status |
| ---: | --- | --- | --- | --- |
| 1 | Web NDS source/presentation ownership | `test_web_nds_touch_behavior.py` | presentation hit resolves to source | OWNER-VERIFIED PHYSICAL DEVICE PASS: Redmi 15 5G, Android Chrome, actual NDS tap and drag/gameplay response. Not automated evidence. Extended menu/layout/orientation cases remain separately unverified. |
| 2 | Web NDS Top/Bottom mapping | mapper contract | center/edge/margin sequence | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 3 | Web NDS Left/Right mapping | layout selector | right-half coordinates | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 4 | Scaled/letterboxed viewport | viewport guard | margin rejection | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 5 | Pointer capture and release | listener/source checks | down/move/up/cancel | OWNER-VERIFIED PHYSICAL DEVICE PASS: Redmi 15 5G, Android Chrome, actual NDS tap and drag/gameplay response. Not automated evidence. Extended menu/layout/orientation cases remain separately unverified. |
| 6 | Native cursor direction | native transform guard | four-direction drag harness | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 7 | Native cursor latency | scheduler guard | slow/fast drag | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 8 | Dual-screen geometry | layout persistence guard | menu/fullscreen/restart sequence | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 9 | Fullscreen touch mapping | resize/fullscreen source guard | coordinate smoke after toggle | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 10 | Virtual pad layering | CSS z-index contract | overlap ownership sequence | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 11 | Menu precedence | menu observer/static guard | native menu vs pad/options | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 12 | Escape handling | host key guard | first close/second exit | PASS current packaged first Escape closes menu and leaves game running; settings draft defect tracked in RG-025/RG-028. |
| 13 | Physical keyboard | no global suppression | arrows/action/Escape | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 14 | GBA launch/crash | ABI/core guard | launch/menu/relaunch | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 15 | Core Options ABI | v2 layout/namespace assertions | open/change/close options | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 16 | Audio delivery | PCM conversion guard | callback batches and silence check | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 17 | Scheduler | one-frame-at-1× assertion | speed/frame sequence | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 18 | Layout persistence | per-system settings guard | save/restart/menu | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 19 | Volume slider | flexible row/layout guard | min/wide panel geometry | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 20 | Settings tabs | tab inventory/draft guard | cancel vs Save Settings | REGRESSION reproduced in fresh DMG: Escape closes without discarding unsaved Show FPS preview. Menu-button close discards correctly; Save Settings acknowledges save. See integrity handoff. |
| 21 | Quick Save 1–10 | count/path guard | slots 1/5/10 save/load | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 22 | Hidden slot 5 | explicit slot enumeration | slot 5 round trip | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 23 | Migration | filename compatibility guard | upgrade/reopen | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 24 | Auto Save | independent path guard | Auto Save + numbered slot | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 25 | `.state` import/export | raw/bounds guard | export/import round trip | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 26 | Product rename | identity/path guard | upgrade existing data | PASS fresh app identity and existing local library visible; upgrade/data migration beyond this smoke UNVERIFIED. |
| 27 | FPS telemetry | no-speed-coupling guard | FPS while changing speed | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 28 | Vulkan no-readback | renderer contract | packaged frame-path smoke | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 29 | Ring/no wait-idle | bounded ring guard | sustained run | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 30 | Worker/OffscreenCanvas | worker contract | actual presentation frames | PARTIAL: current LAN WebGL2 worker frames advance; visible NDS gameplay not proven in audit launch. Secure Android WebGPU initialization FAILS; effective external-core-canvas, Render worker failed. |
| 31 | WebGPU/WebGL2 effective backend | requested/effective fields | capability fallback | PARTIAL: current LAN WebGL2 worker frames advance; visible NDS gameplay not proven in audit launch. Secure Android WebGPU initialization FAILS; effective external-core-canvas, Render worker failed. |
| 32 | ImageBitmap/SAB | close/ring/isolation guard | bitmap lifecycle and isolated page | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 33 | False Playing | status contract | render + input readiness | OWNER-VERIFIED PHYSICAL DEVICE PASS: Redmi 15 5G, Android Chrome, actual NDS tap and drag/gameplay response. Not automated evidence. Extended menu/layout/orientation cases remain separately unverified. |
| 34 | ROM/cache | versioned route/core cache guard | cold/offline reload | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 35 | Service worker | app-shell asset list | update/reload | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 36 | Responsive layout | CSS bounds | portrait/landscape/short viewport | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 37 | Fullscreen/orientation | cache invalidation | rotate/toggle/tap | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 38 | Touch-control overlap | scale/bounds guard | scale/move/open-menu | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 39 | Staging isolation | deploy path/header guard | staging-only health/asset | PASS staging-only health, release and DMG publication; production untouched. |
| 40 | Production isolation | script/path guard | negative check: no prod action | PASS staging-only health, release and DMG publication; production untouched. |
| 41 | Staging cache/version | fingerprint/header guard | fetch active asset | PASS six deployed source hashes, served versioned assets and substituted service-worker template. Current asset 50d711002677, release 20260908-093537-50d711002677, rollback 20260908-001932-50d711002677. |
| 42 | Android Chrome NDS | harness contract | tap/drag/menu/fullscreen | OWNER-VERIFIED PHYSICAL DEVICE PASS: Redmi 15 5G, Android Chrome, actual NDS tap and drag/gameplay response. Not automated evidence. Extended menu/layout/orientation cases remain separately unverified. |
| 43 | Android Firefox limitation | documented browser guard | white-canvas smoke | UNVERIFIED Android Firefox 155; historical white-canvas limitation retained separately. |
| 44 | NDS melonDS auto-start | core/start route guard | cold ZIP boot | OWNER-VERIFIED PHYSICAL DEVICE PASS: Redmi 15 5G, Android Chrome, actual NDS tap and drag/gameplay response. Not automated evidence. Extended menu/layout/orientation cases remain separately unverified. |
| 45 | Offline local data | IndexedDB/cache guard | import/save/offline reload | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 46 | Deployment contamination/health | shell/archive guard | package + staging health | PASS staging package and health; harmless SCHILY.fflags archive warnings recorded. No AppleDouble failure. |
| 47 | Protected UI event ownership | resolver/source assertions | nested menu/settings/pad DOM and menu-open release | UNVERIFIED current complete runtime case; historical PASS is archived and is not current acceptance. |
| 48 | Mobile zero-movement NDS tap | root dispatcher/gesture-owner return contract | down→up, immediate, repeat, tap-vs-drag, protected UI, layouts | OWNER-VERIFIED PHYSICAL DEVICE PASS: Redmi 15 5G, Android Chrome, actual NDS tap and drag/gameplay response. Not automated evidence. Extended menu/layout/orientation cases remain separately unverified. |
| 49 | Artifact publication integrity | explicit allowlist plus size/SHA-256 check | mutate bytes, inspect manifest and route | PASS: byte drift changes availability to blocked, removes URL and returns no published path. |
| 50 | Blocked release truthfulness | five-category manifest/page contract | inspect cards and links | PASS: DEB, Flatpak and EXE state blockers and have no download URL; unlisted historical files return 404. |
| 51 | Release cache isolation | service-worker shell/bypass contract | inspect worker and live response | PASS: page/icons packaged; installers/source bypass cache and manifest is network-only. Asset `8ecb7b06ad8c`. |
| 52 | Native save sync preflight | peer eligibility before ROM hash; status callbacks | absent-peer rejection and connected-peer progress order | UNVERIFIED: no connected device or package runtime available. |

## Verification levels

1. Level 1 — static: run the full Python suite and source/route/ABI checks.
2. Level 2 — behavioral: run the Node DOM/geometry/gesture tests and native
   harnesses that exercise ownership, coordinates, release, layering,
   renderer-worker status, precedence, resize, fullscreen, and migration.
3. Level 3 — live: use the actual staged browser or signed packaged app with
   a known ROM. Verify visible frames, input response, release, audio, resize,
   fullscreen, menu, keyboard, saves, and status truthfulness. Static or
   behavioral success cannot promote a live feature to GOOD.

## Shared-host blast radius

`native-offline/src-tauri/src/azahar_host.mm` serves mGBA, melonDS, Azahar,
audio, input, states, speed, Core Options, settings, scheduler, and AppKit.
Every edit requires GBA, NDS, and 3DS launch smoke; audio edits require all
three audio checks; layout edits require NDS/3DS persistence; input edits
require direction and latency; menu edits require containment and Escape;
packaging edits require the signed packaged `.app`, not a development binary.

## Historical web NDS incidents — superseded status

Historical last known good was the geometry-mapped root bridge before the renderer
presentation canvas was introduced (historical commit `3eba5b1`, verified in
the Android handoffs). The current live staging page on asset
`3a257e271678` reported `Playing`, but `#game` contained a hidden source
`.ejs_canvas` and a visible `.an3-render-canvas`; `elementFromPoint()` selected
the presentation layer, whose pointer events had been forced back to `auto` by
the old canvas-protection loop. No console error appeared, so the touch bridge
silently dispatched to a canvas without EmulatorJS listeners.

The targeted fix is source-only resolution plus a shared geometry mapper:
`static/nds-touch.js`, `static/player.js`, `static/site.css`, asset routing in
`app.py`/`static/service-worker.js`, and the native offline script order. The
fix now has a current staging browser smoke on `45ba4629b867`: a visible frame,
advancing OffscreenCanvas-worker frames, source-canvas gameplay ownership, and
the menu/pad precedence contract. A real touch device or equivalent browser
touch harness is still required before Web NDS can be called `GOOD`.

The 2026-09-07 menu recurrence is separately protected by RG-047. Its root
cause was the new source-canvas recovery resolver treating every non-canvas
hit as a source-canvas fallback; a menu descendant could therefore be
redirected into EmulatorJS even while the visual menu was above the game. The
fix is target/composedPath exclusion before preventDefault, resolution,
pointer capture, or synthetic dispatch; menu-open release; and the existing
scoped `#tvPad` z-index 19 / pointer-inert exception. No renderer architecture
or presentation-canvas ownership changed.

- RG-080: Android native 3DS sessions must survive long play and app suspension. Fixes: (a) the overlay's per-second diagnostics no longer recurse the save tree on the UI thread — Azahar's shader cache grows across a session and the old `saveDirectory.walkTopDown()` (maxDepth 4) ran every second on the main thread and could stall/ANR; it now checks the deterministic `native-libretro/states/<romId>.autosave.state` file, at most every 15s or on an Auto Save message. (b) Auto Save now defaults on so a device kill or crash preserves progress. (c) `nativeStop` waits up to 1500 ms for the worker to leave the render loop (`Session::finished`) before detaching the join, so the worker cannot touch a destroyed `ANativeWindow` — Azahar's documented Android surface-destruction crash class (rotation, app suspension, screen off). (d) `NativeGameActivity` handles `onTrimMemory`/`onLowMemory` by requesting an Auto Save. Evidence (AVD Android 15, 2 GB, 0.4.9 build `c98518941c21…`): 337 s of in-game 3D gameplay with input, RSS stable ~577 MB, zero FATAL/SIGSEGV; pressing HOME on 0.4.8 killed the `:game` process on the same 2 GB AVD, while on 0.4.9 both processes survived and the game stopped/suspended cleanly with zero crash entries. Shared renderer/input contracts were not changed. Automated guard: `tests.test_android_native_runtime`, `tests.test_native_regression_guards`, `tests.test_offline_consolidation`.

- RG-081: Android 3DS must not use the Azahar Vulkan renderer on drivers that return an out-of-spec result from graphics-pipeline creation. Historical failure (2026-09-15, physical Redmi `25057RN09G`, Android 16, Adreno 619 driver 0762.40): ~10 s into 3DS gameplay the `:game` process aborted with `Fatal signal 6 (SIGABRT)` in thread "Pipeline worker"; the tombstone read `terminating due to uncaught exception of type vk::UnknownError: vk::Device::createGraphicsPipelineUnique: ErrorUnknown` at `Vulkan::GraphicsPipeline::Build` (Azahar 2126.1.1, the current pinned release, calls `UNREACHABLE_MSG` on any non-success result). The AVD (host GPU) and macOS (MoltenVK) never reproduce it. Fix: Android 3DS defaults to the core's OpenGL ES renderer (`citra_graphics_api=OpenGL`), with the frontend owning the EGL context, returning a color FBO from `get_current_framebuffer`, resolving GL entries through `eglGetProcAddress`, and blitting the core's layout region into the window with aspect-fit letterboxing. `NativeCoreHost::initialize` takes the graphics API; `requested=="vulkan"` still forces Vulkan; GBA/NDS are unchanged. Automated guard: `tests.test_android_native_runtime`. Runtime validation (same physical device, APK `vibecodedemulator-0.4.10-android-arm64-staging.apk`, 48,091,373 bytes, SHA-256 `7cff442f13c74e9e987efcca1baf8d5bd933c5153b37762b29f43bf9a8422506`): 3DS (Pokémon X, 1.8 GB) rendered both screens correctly at 52–57 FPS and played **337 s (5.6 min)** with button/analog input, zero `SIGABRT`/`SIGSEGV`/`vk::` entries and RSS stabilizing ~800–930 MB. The Vulkan path is retained for devices where it works.

Update (2026-09-18, same physical Redmi `25057RN09G`, Adreno 619, driver 0762.40): forcing the Vulkan renderer aborted roughly four seconds into Pokémon X. Tombstone: `signal 6 (SIGABRT)` in thread `Pipeline worker`, `Abort message: 'terminating due to uncaught exception of type vk::UnknownError: vk::Device::createGraphicsPipelineUnique: ErrorUnknown'`, backtrace frame `Vulkan::GraphicsPipeline::Build(bool)+3316` (uncaught C++ exception, not an Azahar assertion). The Adreno driver logged `AdrenoVK-0: Shader compilation failed for shaderType: 0` and `AdrenoVK-0: Pipeline create failed` immediately before, so `vkCreateGraphicsPipelines` returned `VK_ERROR_UNKNOWN` and the exception escaped the worker thread. One-variable A/B on identical builds: `citra_use_hw_shader=disabled` + `citra_use_disk_shader_cache=disabled` → 0 driver failures and no crash; re-enabling only the disk shader cache → 29 driver shader-compile failures and the same abort; `citra_shaders_accurate_mul` is not a factor. Root cause: the persisted on-disk driver pipeline cache (`<shader dir>/vulkan/pipeline/<program>-<vendor><device>.bin`) is validated only against the driver UUID, so it survives frontend/core changes and goes stale, and Adreno's compiler then rejects the cached SPIR-V. Fix: the native runtime pins `citra_use_disk_shader_cache=disabled` for Android 3DS sessions using the Vulkan renderer (the OpenGL ES path keeps the cache and the RG-125 software-shader pin). Runtime validation (APK `vibecodedemulator-2.3.5-android-arm64-staging.apk`, SHA-256 `d17b281cec8d3ebcbf9b47e175b7b1e22afdb1859ef6722f2f52c76cb6ffa70a`): Vulkan initializes and Quick Save Slot 1 renders Sycamore and the room in full colour at 52–56 FPS for 2+ minutes with zero `FATAL`/`SIGABRT` and no silent GLES fallback (game process logged `AdrenoVK-0`); switching back to OpenGL ES still renders Quick Save Slot 1 correctly, confirming RG-125 is intact. Residual: the driver still logs occasional `Shader compilation failed for shaderType: 4` for other variants without aborting. Automated guard: `tests.test_android_native_runtime`.

- RG-125: Android 3DS must not use the Azahar core's hardware (GLES) PICA shader path on Adreno GPUs. Historical failure (2026-09-18, physical Redmi `25057RN09G`, Android 16, Adreno 619 driver 0762.40, APK `vibecodedemulator-2.3.2-android-arm64-staging.apk`): on Pokémon X Quick Save Slot 1 the Sycamore introduction rendered the whole 3D layer black — Sycamore's model, the room, and the mirror-room character models were RGB≈0 while the 2D dialogue box, the bottom screen, and the frame presentation stayed correct. Controlled single-variable A/B on the same bad scene: `citra_use_hw_shader=enabled` (default) → black 3D; `citra_use_hw_shader=disabled` (software PICA shader interpreter) → identical draw calls render with full colour. `citra_use_disk_shader_cache=disabled` with hardware shaders still enabled → still black, so the shader disk cache is not the cause; the frontend GL blit was already shown faithful, and the same textures/PICA state/TEV inputs render correctly through the interpreter, exonerating texture upload, texture cache, PICA texture state, and the core framebuffer. Android is the only platform that runs Azahar's OpenGL renderer (desktop builds use its Vulkan renderer, which is correct), so the defect is confined to the core's GLES hardware-shader codegen/execution on Adreno. Fix: the native runtime's `GET_VARIABLE` override pins `citra_use_hw_shader=disabled` for Android 3DS sessions (the same enforcement mechanism already used for `citra_graphics_api`), keeping the faithful software shader path. Runtime validation (same device, APK `vibecodedemulator-2.3.4-android-arm64-staging.apk`, SHA-256 `63e483e750c9aebe3be7e3ff650eaa9e313eb4daef2664bce0cc55bb08af1cfa`): Quick Save Slot 1 renders Sycamore, the room, and the 2D UI correctly at 49–55 FPS with Quick Save Slot 1 preserved. Automated guard: `tests.test_android_native_runtime`.

## RG-142 — Bounded native LAN handlers (2026-10-10)

- The desktop direct-controller listener and native sync listener each admit at most eight active TCP handler threads. Once a listener reaches its limit, it closes an accepted socket before creating a thread. The RAII permit is held for the handler lifetime and releases on normal return or panic; its process-wide lifetime keeps stopped/restarted services within the same bound. I/O remains off the emulator render loop, and no waiting work queue is added.
- Automated validation: `cargo test --lib` — 35 passed, 3 ignored; this includes the permit saturation/release test and existing direct-controller pairing/input integration tests. `cargo check --lib` and `rustfmt --check src/connection_limit.rs` pass.
- Scope limit: packaged-runtime behavior under connection saturation and gameplay p95/p99 impact remain **UNVERIFIED**. Do not claim runtime latency acceptance from these source-level checks.

## RG-143 — Native LAN sync requests stay off the UI thread (2026-10-10)

- Native sync discovery waits up to two seconds on multicast UDP, and sync RPCs perform blocking socket writes and reads, including potentially large save/state payloads. Both Tauri commands must be `async` and call their socket work through `tauri::async_runtime::spawn_blocking`, so slow peers cannot freeze the UI thread or block the async executor.
- Automated validation: `tests.test_native_sync_command` checks both commands' blocking-worker boundary; `cargo check --lib` validates the Rust commands; `node --test tests/native_sync.test.mjs tests/sync_transfer.test.mjs` covers the existing sync behavior and packaged JavaScript parity.
- Runtime acceptance: slow-peer UI responsiveness during packaged save/state transfer remains **UNVERIFIED**; source and test checks do not prove the packaged interaction.

## RG-144 — Large native LAN sync transfers stay within frame and memory bounds (2026-10-10)

- Native sync frames remain capped at 8 MiB. Members up to 16 MiB and sets up to 64 MiB transfer through ordered 768 KiB chunks; each receiving client checks the complete member SHA-256 before local persistence. Upload metadata and all received members are validated before the existing atomic set publish. At most one chunked publish may be staged process-wide; other peers receive a retryable busy error. Peers without chunk support retain the legacy path for transfers up to 4 MiB, while larger transfers fail with an update-required message.
- Automated validation: `node --test tests/native_sync.test.mjs tests/sync_transfer.test.mjs` covers chunked uploads/downloads, byte order, and Android asset parity; `cargo test --lib` covers server chunk order and publish-slot release; `cargo check --lib` validates the native implementation.
- Runtime acceptance: a packaged two-peer transfer above 8 MiB, atomic recovery after interruption, and gameplay p95/p99 impact remain **UNVERIFIED**. Source and unit tests do not prove the packaged interaction.

## RG-145 — Vulkan presentation semaphores follow swapchain-image lifetime (2026-10-11)

- `VkPresentInfoKHR::pWaitSemaphores` must use a semaphore associated with the acquired swapchain image, not a frame-in-flight slot. A `vkQueueSubmit` fence does not prove the presentation engine consumed its wait semaphore; reusing the frame-slot semaphore can therefore violate Vulkan synchronization and hang or corrupt presentation on physical drivers.
- The beta fix is commit `1731316a6fba190eca1967cd5dcc66a214eb3aef` on `codex/vce-optional-features-beta`: both portable desktop and macOS Vulkan presenters allocate one `render_finished` semaphore per swapchain image and select it using the acquired image index. Their libretro sync index is constrained to its advertised mask. The packaged Windows 3DS smoke now requires continuing core/present counters across multiple intervals and repeated input transitions.
- Focused validation on the beta worktree: 111 tests passed, 5 skipped; Python smoke syntax checks and `git diff --check` passed. Hosted Windows package run `38117097243` built an unsigned x64 installer from `dd1cbc40ac854dbdc087f0c8657ee746de69909f`; packaged shell/GBA and NDS checks passed on that artifact. The first 3DS smoke failure was a missing release edge in the test sequence, corrected in review-only commit `756a659f0f9d04649f264e12e41db4b07f266266` (only the Windows 3DS packaged smoke changed). Its exact-SHA artifact-reuse run `38120522197` still failed: SwiftShader reported core/presentation counters through 1,406 frames, then no further progress; release input command 2 was acknowledged only at shutdown, after the 10-second smoke wait expired. Diagnostic log and screenshots are artifact `windows-packaged-3ds-diagnostics` (ID `11695516123`). This is a hosted software-Vulkan freeze/responsiveness failure after input, so the P0 remains open. It is not a harness-only failure and cannot be waived by the earlier first-frame result. Physical Windows GPU acceptance remains **UNVERIFIED**. Upstream's exact pinned core source waits in `PresentWindow::GetRenderFrame()` on the frontend's `wait_sync_index` callback before selecting its frame; libretro specifies that callback must wait for frontend activity on the current sync index before the core may reuse that image ([Azahar 2126.1.2 source](https://github.com/azahar-emu/azahar/blob/9e6f523a57fac9564ac0bf8286db3c3702d301ec/src/citra_libretro/libretro_vk.cpp), [libretro Vulkan contract](https://github.com/libretro/RetroArch/blob/master/libretro-common/include/libretro_vulkan.h)). Both `UINT64_MAX` fence/acquire waits in VCE and the void callback's no-timeout contract need safe session-level containment; returning early from the callback is not safe. The Vulkan rule follows the [Khronos Vulkan Guide on swapchain semaphore reuse](https://github.com/KhronosGroup/Vulkan-Guide/blob/main/chapters/swapchain_semaphore_reuse.adoc).

## RG-146 — Native large-ROM import reports real progress and hashes during copy (2026-10-11)

- Native ROM import must not silently wait through a multi-gigabyte copy or read the completed file a second time solely to compute SHA-256. Copy from the selected source to the existing `.part` file in bounded 1 MiB chunks, hash the same bytes as they are written, preserve `sync_all` and atomic rename, and seed the existing library identity cache from that digest.
- The 3.6.9 development branch adds keyed progress events for inspection, byte-counted copying, finalization, and library update. The installed library shows an accessible progress state, determinate byte progress while copying, and an indeterminate animation for phases without a known duration. Import and hashing remain in Tauri's blocking worker.
- Focused validation: `tests.test_offline_consolidation` (12 tests), JavaScript syntax check, source invariants, and `git diff --check` pass. The new Rust copy/hash unit test is present but has not yet run. Packaged macOS/Windows runtime interaction with a multi-gigabyte ROM remains **UNVERIFIED**; do not label the user journey GOOD until it is exercised in an installed build.

## RG-147 — Windows release shell does not create a console window (2026-10-11)

- The Tauri shell executable must use the Windows GUI subsystem in release builds so launching the installed app does not create a CMD window. Keep debug builds attached to a console for diagnostics. The SDL child continues to hide its own console with `CREATE_NO_WINDOW`.
- The 3.6.9 private branch applies the conditional subsystem attribute in `native-offline/src-tauri/src/main.rs` and adds a source guard in `tests/test_regression_invariants.py`.
- Source assertion and Python syntax validation pass. PE subsystem inspection and exact packaged launch acceptance remain **UNVERIFIED** until the updated Windows artifact is built and launched.
## Switch/Eden experimental OFF lifecycle — RG-148, 2026-10-11

- RG-148: With `experimental-switch-eden` OFF or missing from a profile, startup detection must not resolve the companion path, launch must be rejected, and status/hosted-frame/input commands must not touch the companion runtime. Saving OFF while the feature was active must disable command access and stop the hosted-frame consumer and companion before returning to the inactive UI. The fast command guard reads a process-owned atomic setting snapshot; settings storage is read on startup detection or settings save, not per input event. Enabling the feature makes availability discoverable but does not launch it.
- Beta implementation: commit `1b66954` on `/private/tmp/vce-optional-features-beta` (branch `codex/vce-optional-features-beta`), product version 3.6.9. It also removes Switch from Android's advertised systems because that package does not ship the companion. The setting remains OFF by default.
- Focused validation: Rust test `native_settings::tests::experimental_preferences_are_off_for_a_fresh_profile_and_persist_opt_in` PASS; `tests::switch_commands_are_rejected_while_the_experimental_feature_is_off` PASS; touched JavaScript `node --check` PASS; `git diff --check` PASS. Rust tests used the existing vendored runtime inputs through temporary symlinks in the beta worktree, then removed those links and the 1.3 GB Cargo target tree.
- **UNVERIFIED:** packaged UI transition from ON to OFF, active companion shutdown, and no process/GPU/wakeup in an installed beta build. The beta line has no Phone Controller or LAN Sync runtime integration yet; those toggles must not be represented as working services until their feature paths are integrated.

## RG-149 — Native large-ROM import progress and single-pass digest update (2026-10-11)

- Desktop native import reads and hashes each bounded source chunk while writing the same bytes to the existing `.part` file, then syncs and atomically finalizes it. The existing content-hash cache is seeded from that digest, avoiding a second full read. Progress events are keyed to the ROM and report real byte totals during copy; inspection/finalization/library work remains indeterminate. Cancellation is checked between chunks and removes the partial file.
- Android's direct native ROM copy reports the same progress phases into the shared UI event path. Its file-provider access remains owned by the existing background import thread. Android cancellation is not exposed until that native picker/import path supports it.
- Source validation on beta `codex/vce-optional-features-beta` at working-tree base `7d8bdef09572a8d6515a241f568c4efee8fda56a`: `cargo test --lib native_rom` passed 6 tests (including exact-prefix hash/progress and cancellation); `tests.test_offline_consolidation tests.test_native_regression_guards` passed 49 tests; JavaScript syntax, Cargo metadata/JSON parsing, and `git diff --check` passed. Full `cargo test --lib` compiled but one existing ABI test failed because this isolated checkout did not contain the pinned mGBA core; 19 passed and 5 were ignored. Android Gradle/Kotlin compilation and packaged import UX remain **UNVERIFIED** because this checkout has no Android SDK or Gradle wrapper. No installed-runtime claim is made.
