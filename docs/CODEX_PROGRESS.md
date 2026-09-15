# Codex Progress

## Goal

Complete the staging-only native release train: portable Android and Linux native runtime work, shared layouts and controls, archive detection, renderer verification, verified release artifacts, and accurate handoff evidence. Production remains untouched.

## Current Status

**ACTIVE — shared player / all-platform GBA–NDS–3DS implementation, requested 2026-09-13.** The previous staging release is complete and preserved. This new owner request authorizes runtime/UI/build changes: Android/Linux 3DS, Windows GBA/NDS/3DS, a circular joystick with a smaller circular thumb, DMG-reference player UI across web/apps, and one build coordinator for all targets. Existing renderer backends must remain. New implementation source is NOT FROZEN; earlier release freezes/artifacts remain immutable historical evidence. Production untouched.

Previous status (historical):

The existing filesystem contains the authoritative completed staging release train. The tested Android raw APK was promoted, and the Release Center serves four fail-closed verified installers on staging asset `df14d4aa2d9a`. HTTP stream size/SHA-256 parity, final release evidence documentation, canonical verification, and temporary AVD shutdown are complete. Production remains untouched.

The worktree is deliberately dirty: 17 tracked files are modified and a large, untracked `native-offline/` implementation/release tree exists. Nothing is staged. Preserve all of it.

## Historical Completed — superseded by active session below

- Implemented the portable libretro Vulkan hardware-frame contract and Android Azahar 3DS path without a GPU-to-CPU-to-GPU hot path.
- Implemented shared canonical screen-layout schema/model, Android layout restoration, immediate Settings preview, persisted `Next Layout`, and macOS layout alignment.
- Implemented Android virtual-control customization (position, scale, opacity, reset) plus D-Pad/analog-joystick selection and native analog/digital mapping.
- Implemented safe Android ZIP and 7z inspection/import, including safe entries, supported suffix preservation, NDS-before-GBA header detection, and the XZ decoder dependency.
- Implemented Linux SDL/native window, Vulkan-first/OpenGL fallback, audio/input/storage/file-picker integration, Debian and Flatpak packaging.
- Built and runtime-smoke-tested final Linux DEB/Flatpak on the authorized Debian host; GBA Vulkan and NDS OpenGL fallback processes ran under Xvfb with SDL dummy audio.
- Built and integrity-verified the current macOS DMG.
- Built, signed, and device-tested the current Android APK. GBA/NDS runs, layouts, `Next Layout`, settings Save/Discard, D-Pad/joystick, archive import, saves, and GLES fallback were exercised.
- Exercised Android Azahar with legal 3DS homebrew: visible advancing frames, input, saved states, and stable Vulkan presentation work. It remains unadvertised because a qualifying 3DS title with confirmed emitted audible audio has not yet been observed.
- Reproduced web renderer behavior on HTTP staging: WebGPU is unavailable in the insecure context (`navigator.gpu` absent), so the observed WebGL2 fallback is expected. No successful-WebGPU regression was demonstrated.

## Historical In Progress — superseded by active session below

- No active implementation work remains. Retain the explicit Android 3DS and Windows acceptance limits below.

## Historical Remaining — superseded by active session below

1. Keep Android 3DS hidden until a qualifying title produces confirmed emitted/audible runtime audio in addition to the already accepted boot/frames/input/save/presentation evidence.
2. Validate Windows only on a real Windows Vulkan build/signing/runtime host; do not fabricate an EXE.
3. For a later release, repeat byte-parity verification before replacing any of the four staging artifacts.

## Historical Files Changed — superseded by active session below

- `native-offline/native-runtime/`: portable libretro hardware-renderer contracts, Vulkan backend, Linux adapters, input/layout integration, and Android JNI runtime.
- `native-offline/src-tauri/`: Android activity/overlay/import pipeline, Azahar dependency fetching, and packaging inputs.
- `native-offline/shared/native-layout-schema.json`: canonical cross-platform multi-screen layouts.
- `native-offline/scripts/build-linux-staging.sh`, Linux package files, and tests: native DEB/Flatpak build/runtime contract.
- `native-offline/releases/`: current final macOS, Android, DEB, and Flatpak staging candidates, each with a local SHA-256 sidecar suitable for byte-parity verification.
- `app.py`, `deploy/package-staging.sh`, and `tests/test_integration.py`: Release Center now catalogs/packages all four evidenced staging installers and preserves the Windows blocked entry.
- `reports/handoff/RELEASE_TRAIN_STATE.md`, `SYSTEM_INSPECTION_HANDOFF.md`, `RELEASE_TRAIN_HANDOFF_20260912.md`, `RELEASE_TRAIN_ARTIFACT_MANIFEST_20260912.md`, and `docs/REGRESSION_GUARDS.md`: current release authority/evidence and retained limitations.
- Existing tracked web/app/deployment changes predate this continuation and are preserved unchanged unless the release task requires an additive edit.

## Historical Tests / Builds — superseded by active session below

- macOS: `npm run build:macos` completed; codesign and DMG verification completed. Current DMG SHA-256: `762f1e8122c0b3455ed4a43509c001eb9a12adb252a398b5310c4ac9f8cb90f3` (42,282,073 bytes).
- Linux final candidates: DEB SHA-256 `7b8672db446a73c8dcf78220b77feb1501d9a0ae6958623fa74ba9319a3a7b49` (1,812,216 bytes); Flatpak SHA-256 `65f72ed64935cd958d1e977dcbbb3a2e3ecad5e29d8c6746be76c9916a525a50` (1,805,368 bytes). Debian runtime smokes returned the expected timeout while still running (`124`) for GBA/Vulkan and NDS/OpenGL fallback.
- Android: latest universal debug APK was promoted to `native-offline/releases/vibecodedemulator-0.4.4-android-arm64-staging.apk`; SHA-256 `128780ed3f21cbf2ac4b158fcd02fc60bd97e92c9b9ded90918f52ad7a3faa24` (87,703,074 bytes), v2 signature verified. Kotlin compilation and targeted Android/native tests passed after the archive fixes.
- Web renderer node tests: 11 passed. NDS touch behavior passed.
- Complete explicit Python suite: 119 tests passed on 2026-09-12 after the exact `refusing a browser-only package` package-contract wording was restored. The change is a comment-only static-contract fix and does not alter the already verified Linux binaries.
- Release-catalog verification: 30 relevant Python tests passed; `deploy/package-staging.sh` passed syntax validation; all four local installer SHA-256 sidecars verified.
- Staging release: archive inspection confirmed exactly the four catalog artifacts with byte parity. `deploy-stage.sh` completed with the supplied SSH identity and published `/opt/an3-arcade-staging/releases/20260912-164924-df14d4aa2d9a`. HTTP stream downloads matched each catalog size/SHA-256; `/health` reported `ok=true`, `environment=staging`, asset `df14d4aa2d9a`; Windows EXE remained blocked.
- Final canonical verification: `tools/release-train.sh --staging verify all` passed 119 Python tests, web NDS touch behavior, 11 web renderer cases, native script syntax checks, and `git diff --check`.
- Cleanup: `adb -s emulator-5554 emu kill` completed; a follow-up device listing was empty and no emulator, Gradle, or Flatpak builder process remained.

## Historical Known Issues — superseded by active session below

- Android 3DS has not met the required audio-acceptance gate. The two legal homebrew tests produced no confirmed samples; do not advertise 3DS even though Vulkan, frames, input, and save states worked.
- The newly built DMG has build/integrity verification but not a fresh post-build human runtime acceptance. Owner observation verifies the current DMG's GBA/NDS smooth gameplay and audible audio, not an automated run of the newly packaged DMG.
- HTTP staging cannot expose WebGPU due to its insecure origin; fallback must remain explained as `requestAdapter`/unavailable rather than silently treated as WebGPU.
- Windows has no authorized real builder or runtime acceptance environment.

## Historical Important Decisions — superseded by active session below

- OWNER-VERIFIED runtime/audio evidence: the owner observed smooth GBA/NDS gameplay on the current macOS DMG and Android APK, and smooth audible audio on both. This supersedes old “audibility unverified” wording but is observational evidence, not fabricated automation.
- Native 3DS uses the core-provided Vulkan image/synchronization path through the shared hardware renderer; no normal CPU readback/re-upload path is allowed.
- The shared layout schema is the sole layout enumeration for Settings and `Next Layout`; single-screen GBA does not show the control.
- Android public system advertising remains GBA/NDS only until the 3DS audio gate is met.
- Web and native renderer families remain separate: web is WebGPU-preferred with WebGL2 fallback; native is Vulkan-preferred with OpenGL/GLES fallback.

## Historical Do Not Redo — superseded by active session below

- Do not reset, revert, overwrite, or discard the existing tracked or untracked worktree changes.
- Do not redo Android NDS/3DS, layout, control, archive, or Linux runtime implementation merely because they are uncommitted.
- Do not reclassify the HTTP WebGPU fallback as a code regression without a secure context where adapter/device acquisition is available.
- Do not publish or advertise Android 3DS, nor claim qualifying 3DS audio evidence.
- Do not replace the just-promoted Android APK with the older 74,229,651-byte candidate.

## Historical Next Step — superseded by active session below

No release action is pending. A future session should begin with a source-of-truth worktree check, then only pursue a real Android 3DS audio acceptance run or a real Windows native build environment; it must not reimplement or re-advertise the completed work.

## Continuation update — 2026-09-13 (Windows 11 build VM)

The persistent `an3-win11-build` Windows 11 x64 VM is now installed on the
authorized Debian host. The host was not rebooted, its physical LAN was not
bridged, and both production and staging services remained untouched.

### VM and access

- Q35, host-passthrough CPU, 8 vCPU, 6 GiB RAM, existing sparse 100 GiB qcow2,
  matching Microsoft OVMF 4M CODE/VARS, Secure Boot on, TPM 2.0, and loopback-
  only SPICE.
- `an3-build-nat` and the DHCP reservation `192.168.251.50` are preserved.
- VirtIO networking is working after cold boot; the system disk remains SATA.
  A VirtIO system-disk experiment did not return the guest display or SSH and
  was rolled back without recreating or modifying the qcow2. The unused LSI
  SCSI controller was removed after Windows reported it as a problem device.
- OpenSSH Server and `an3builder` key-only access work through the existing Mac
  `ProxyJump an3-dell` configuration. The private key remains on the Mac.

### VirtIO verification

The official `virtio-win-0.1.302.iso` is SHA-256
`303f7ae40dad495d6ae474fdc571df58958a4dbc5c37a522d80f9a203867949d`. The
guest-tools MSI wrapper is SHA-256
`4f4388468a7ac5286bd1f1924ef02e7281a60a600390a7cfcfd55809efc0889f` and is
`NotSigned`; that wrapper status was not used as a driver verdict. NetKVM,
vioscsi, viostor, Balloon, and vioserial INF/CAT/SYS files each returned
`Valid` from `Get-AuthenticodeSignature` with the Microsoft Windows Hardware
Compatibility Publisher, and `pnputil` accepted the packages under Secure
Boot. The official fwcfg CAT/SYS were valid and `pnputil` installed
`fwcfg.inf` for `ACPI\\QEMU0002`; no non-OK VM devices remain. No viorng device
was exposed, so viorng was not installed.

### Toolchain and repository result

Git 2.55.0.windows.5, Visual Studio Build Tools 17.14.40 with Windows SDK
10.0.26100.0, CMake 4.4.3, Ninja 1.13.2, Rust MSVC 1.98.1, Node 24.21.0 LTS,
and npm 11.19.0 are installed. Trivial MSVC, Rust, CMake/Ninja, Node/npm, and
Git checks passed. The repository's `npm ci` and existing Tauri command built
an x64 NSIS installer (31,912,290 bytes,
SHA-256 `55b9eb56b342362868ae2bcd28e1904b6a422fdb0b30daba3a06cb1b44e835d2`).
The installer was launched for a smoke check and removed afterward.

The repository's deterministic `build-windows-staging.ps1 -VerifyOnly` remains
blocked by its explicit `VULKAN_SDK`/verified Windows runtime-core prerequisites.
The checked-in package configuration still names Mac arm64 runtime resources,
so the NSIS output is not claimed as a release-valid Windows runtime. This VM
also provides no proof of real Vulkan/3DS acceleration.

### Checkpoints and safety

Only `baseline-clean` and `an3-dev-ready` external disk-only snapshots exist;
the original qcow2, OVMF VARS, TPM state, NAT, and staging files remain intact.
Staging health was rechecked after the work (`/health` returned `ok=true` for
asset `df14d4aa2d9a`). The VM autostart setting is disabled and the final
`virsh domstate an3-win11-build` is `shut off`.

The regression command that has just passed was:

```sh
PYTHONPYCACHEPREFIX="$PWD/work/pycache-final-python-20260912" python3 -m unittest -q tests.test_android_native_runtime tests.test_auth_redirects tests.test_integration tests.test_linux_native_runtime tests.test_monitoring tests.test_native_input_contract tests.test_native_regression_guards tests.test_native_renderer_contract tests.test_native_staging_contract tests.test_offline_consolidation tests.test_phase1_renderer_contract tests.test_regression_invariants tests.test_web_nds_touch_behavior tests.test_web_renderer_behavior
```

The earlier explicit suite was the immediate post-source gate; the final canonical run additionally executed the web behavior checks, native package check, and whitespace validation.

## Continuation update — 2026-09-12 (current owner evidence)

The earlier release evidence remains authoritative for the checks it actually performed, but the owner has reported three later acceptance gaps that override its broader completion wording: Android 3DS is not yet a complete playable acceptance; the Linux SDL runtime has not reached the DMG/APK feature/UI contract; and the exported Flatpak has failed installation on the Linux Mint test machine. Do not relabel those reports as passed based on Debian/Xvfb smoke evidence.

### Completed work retained; do not redo

- Keep the accepted Android GBA/NDS runtime, Android 3DS Vulkan frame/input/layout/save evidence, Linux GBA/NDS runtime smoke, renderer contracts, completed broad suites, and prior staging byte-parity evidence intact.
- The current workspace is deliberately dirty (17 tracked modifications plus the untracked native release tree); nothing was reset, cleaned, staged, or reverted in this continuation.

### Current discovery

- The local macOS host has no connected Android device and no Flatpak runtime. Staging key-only preflight passed using the owner-provided identity; the authorized staging host is Debian 13 with Flatpak 1.16.6, not the reported Linux Mint acceptance machine.
- Android native 3DS implementation exists in the portable runtime, but the Android-facing capability/UI gate intentionally exposes only GBA/NDS. Its prior legal-homebrew run had video, input, layout persistence, and saves, but no qualifying audible/emitted audio evidence.
- The Linux runtime is a narrow SDL/GTK CLI surface (F1 layout, Esc quit, F5/F9 slot 1). It does not reuse the full macOS/Android feature model or canonical layout schema. The Linux release build packages GBA/NDS cores only; 3DS intentionally cannot start there.
- The Flatpak manifest builds a single-file bundle from the DEB but no documented installation test exists. The exact Mint failure still needs reproduction on that machine or equivalent supplied environment.

### Files changed in this continuation

- `docs/CODEX_PROGRESS.md` only (this checkpoint update).

### Targeted checks run in this continuation

- Read the supplied system handoff, regression ledger, agent rules, and prior checkpoint; inspected the dirty worktree without altering it.
- Staging SSH key-only preflight: `STAGING_SSH_KEY_AUTH=PASS`.
- Local environment: zero connected Android devices; no local Flatpak command. Authorized staging host: Debian 13, Flatpak 1.16.6.

### Current blocker

The actual Linux Mint test environment is not reachable through the only authorized staging SSH path. No production system was accessed. Android 3DS audible acceptance likewise cannot be honestly claimed without an attached/authorized Android runtime and a title producing confirmed audio.

### Exact next action

Identify the Linux UI and Flatpak installer blast radius in the current source, run its existing targeted baseline guards, then implement the smallest shared-model Linux UI/Flatpak changes before requesting the missing Mint/Android live acceptance environment.

## Continuation update — 2026-09-12 (Linux/Flatpak candidate ready for staging)

### Completed work

- Reproduced the actual Flatpak failure class in a disposable staging-host user installation: the old single-file bundle failed because `org.gnome.Platform/x86_64/49` was unavailable. The bundle builder now embeds the Flathub runtime repository, and `scripts/verify-flatpak-install.sh` proves installation from an empty user-data root instead of relying on a builder cache.
- Added the smallest Linux-native control surface without changing the SDL game loop or renderer: a GTK companion window exposes the nine desktop-menu sections, Pause/Resume, fullscreen, native pad, keyboard/controller guidance, audio gain/mute, speed, real core options, live persisted layouts, Auto Save, ten quick-save slots, import/export, diagnostics, and return-to-library. Vulkan-first and the existing OpenGL fallback remain unchanged; no readback, finish, wait-idle, or per-frame resource path was introduced.
- Rebuilt the Debian DEB and Flatpak on the authorized Debian host. The final DEB and Flatpak each passed a controlled Xvfb core-frame launch with the GTK controls; the Flatpak also passed a fresh disposable install and native `--help` launch. The controlled fixture has no game logic and does not replace the earlier owner/runtime GBA/NDS acceptance evidence.
- Built the fresh Android ARM64 APK, confirmed the bundled native Azahar core/assets, and verified its Android Debug v2 signature. Android 3DS remains intentionally hidden: there is no connected Android device or qualifying audible/emitted 3DS test in this session.

### Fresh artifact bytes staged locally

- Android APK: `4c435d832bf5f6bd8d0c3de1c74fd399cf699e431b3a1ca0a4f8094e5281db20` (89,010,116 bytes).
- Linux DEB: `1c6d0a9c14a3cc65ce41aaba2f76d2faf5836dbc9451cbb4558c8cd28950d304` (1,848,192 bytes).
- Linux Flatpak: `f6aa7b7010c92b81186d68ebd22cdaabe4a18140f7cbfc5991fe956a9ad9a7af` (1,835,048 bytes).
- The exact prior Linux artifacts were copied to `work/release-predeploy-backup-20260912/` before their requested replacement. macOS DMG remains untouched.

### Files changed in this continuation

- `native-offline/native-runtime/core/libretro_host.{h,cpp}`
- `native-offline/native-runtime/platform/linux/{linux_controls.{h,cpp},linux_runtime.cpp,sdl_audio_backend.{h,cpp}}`
- `native-offline/scripts/{build-linux-staging.sh,verify-flatpak-install.sh}`
- `native-offline/flatpak/space.an3tocom.offline.yml`
- `native-offline/packaging/linux/{control,space.an3tocom.offline.desktop}`
- `native-offline/releases/` Android APK, Linux DEB, and Flatpak only; macOS DMG untouched.
- `app.py`, `tests/test_linux_native_runtime.py`, `docs/REGRESSION_GUARDS.md`, and this checkpoint.

### Final targeted verification before deployment

- Final syntax/catalog guard and focused regression suite: 88 tests passed (`test_android_native_runtime`, `test_linux_native_runtime`, native input/renderer/staging/regression guards, integration, and monitoring).
- Android APK v2 signature verification passed; package contains `liban3_offline_native.so`, `libazahar_libretro_android.so`, and native Android assets.
- Flatpak clean install and controlled Xvfb runtime launch passed on authorized Debian. The original Linux Mint machine remains unavailable, so Mint-specific acceptance is not claimed.

### Staging deployment completed

- `deploy-stage.sh` passed key-only preflight and deployed only to staging: `/opt/an3-arcade-staging/releases/20260912-182516-df14d4aa2d9a`. The previous staging release remains the rollback target; production was not accessed.
- Staging `/health` returned `ok=true`, `environment=staging`, asset `df14d4aa2d9a`.
- HTTP stream size/SHA-256 parity passed for all four Release Center artifacts: unchanged macOS DMG, fresh Android APK, fresh Linux DEB, and fresh Flatpak. The staging manifest marks the three refreshed candidates available and correctly retains Windows as blocked.
- The exact disposable Debian build/install directories were removed after parity verification; no staging release or user data was deleted.

### Do not redo

- Do not rerun accepted broad Android GBA/NDS or historical Linux runtime audits.
- Do not remove the Android 3DS advertising gate without device evidence of video, input, audio, saves, and stable gameplay.
- Do not replace or alter the macOS DMG, access production, reset/clean the dirty worktree, or discard the preserved Linux artifact backup.

### Current blocker

- The requested Linux Mint machine and an Android device/title capable of qualifying 3DS audio acceptance are not available via the authorized environment. This blocks only those physical acceptance claims, not staging deployment of the correctly gated fresh candidate.

### Exact next action

On the reported Linux Mint machine, install the staged Flatpak from a fresh user data root and launch a legal local GBA/NDS ROM through the GTK controls. Separately attach an authorized Android device and run a qualifying 3DS title through video, input, audible audio, save/reload, and smooth-play acceptance before removing its advertising gate. Do not touch production.

## Fresh staging release — 2026-09-13 (active session authority)

### Source frozen commit/worktree state
SOURCE_FROZEN. All five artifact builds used fingerprint `07b2597ba72e677d2a0511400bf2172ea02af0df929f0568f37a032ab691c4ce`, base commit `542ef985ddd22435cad00695b065dda1be4f80d3` plus preserved dirty worktree. After canonical verification exposed a stale assertion, only non-packaged `tests/test_monitoring.py` changed. Final verification snapshot `106f8008410dac19cc46e95c44ee09c00f839b3ff0f5de8f3cb75c32250de84e`; every app/native/package/dependency/deploy byte remains identical to the build freeze, so no artifact is affected. Both manifests retained under `work/release-20260913/`. Final snapshot parity PASS.

### Completed This Session
- Fixed Windows SDK, pinned native x64 core provisioning and platform-specific resource selection; proved remaining native-integration/VM graphics blocker and retained diagnostic installer outside downloads.
- Added truthful catalog-derived visible release identity and SHA-bound installer URLs, prepackage byte/sidecar verification and locked web dependency inputs.
- Built all five fresh candidates from the recorded common build freeze; performed package/runtime checks with the exact candidates.
- Completed canonical checks once with one stale test-only assertion corrected and its exact case rerun; app/native/deploy bytes stayed frozen and no artifact was affected.
- Deployed four eligible artifacts through existing staging tooling. HTTP release identity, manifest/page, all four streamed size/SHA values, stale-link rejection and Windows blocked state PASS.
- Preserved explicit prior staging rollback; stopped AVD, verified Windows shut off/non-autostart, removed only own Dell disposable roots, kept staging active and production untouched.

### In Progress
None. Current staging release and cleanup are complete.

### Remaining
None for this staging release. Windows remains intentionally unavailable pending actual Windows native surface/audio/input/launcher integration and a supported graphics/interactive acceptance environment. Android 3DS remains hidden pending its existing qualifying video/input/audio/save/stable-play gate.

### Artifact Matrix with hashes/sizes
- DMG: `vibecodedemulator-0.4.4-macos-aarch64.dmg`, 42,282,411 bytes, SHA-256 `d3615455f9f85cdb3c73874ec88b59fd6ec4ff10bf1016d45fa7125142ac3ffb`; codesign deep/strict ad-hoc PASS; DMG integrity PASS; Fresh mounted app: GBA/NDS visible advancing title frames with Vulkan, native nine-tab menus responsive; app quit and DMG detached. New audible/gameplay-input acceptance not claimed.
- DEB: `vibecodedemulator-0.4.4-linux-amd64.deb`, 1,846,616 bytes, SHA-256 `d46f594006647847a70d574ef3382b5d0792dbb16b7dee3ca51f5b1ab5cac85c`; DEB metadata, apt install simulation, dependency closure and extracted package PASS; Real bundled mGBA GBA/Vulkan and melonDS DS NDS/OpenGL under Xvfb; visible GTK controls captured; controlled fixture input/save/load smoke PASS; SDL dummy audio.
- Flatpak: `an3-offline-0.4.4-linux-amd64-staging.flatpak`, 1,835,048 bytes, SHA-256 `688203648c89cf83e74f160086fa78304360ad306cac4265537cc6770d4a2877`; Fresh disposable user install with empty valid system repo; runtime downloaded from embedded Flathub source; --help PASS; Exact installed bundle GBA/Vulkan and legal NDS homebrew/OpenGL ran with visible GTK controls captured; input/save/load smoke; SDL dummy audio.
- APK: `vibecodedemulator-0.4.4-android-arm64-staging.apk`, 86,436,942 bytes, SHA-256 `5486af1cd010ebc6f3dc58cd76106b96fb39049e712f748ec79a34da36f74537`; Fresh output created; Android Debug v2 signature PASS; Fresh clean AVD install; GBA Start/A input and visible save restoration after relaunch; NDS Start/B and touch in Top/Bottom and Side by Side, Next Layout, draft Discard and Save Settings persistence, slot 1 restored after relaunch. Vulkan diagnostics, 59 core/present FPS. Android 3DS hidden; no new human audibility claim.
- EXE-diagnostic: `VibeCodedEmulator_0.4.4_x64-setup.exe`, 25,264,627 bytes, SHA-256 `e9396f43a75263b457c729ab670b7893840c9729fc8e02f5c2d2ad08f7f9c237`; Fresh NSIS clean install PASS; installed application PE x64, packaged DLLs ABI 1/load PASS; no Mac resource files; unsigned staging diagnostic; BLOCKED: native launch integration absent; no Vulkan ICD/OpenGL 3+; no signed-in interactive desktop. Session-0 launch had no GUI window. Not downloadable.

### Files Changed
app.py; deploy/package-staging.sh; platform Tauri resource configurations; native Windows preparation/preflight/package command; mGBA logging-only MSVC patch; pinned prepared-web runtime verification; release catalog verifier and freshness/integration tests; release metadata, regression ledger and checkpoint. No shared runtime/renderer/player implementation edits.

### Tests / Builds
Five fresh builds complete, package/runtime results in matrix. Canonical executed once: 123 Python cases, 122 initially passed and one stale packaging assertion failed; exact corrected test then PASS. Remaining canonical NDS touch, 11 renderer cases, native script syntax and diff check PASS. Local four-artifact catalog/portable sidecars PASS. Final source parity PASS. Windows SDK/core integrity PASS, native release gate BLOCKED. No full-suite repetition after the targeted test correction.

### Runtime Evidence
Fresh mounted Mac GBA/NDS Vulkan title frames and native menus; fresh clean-installed Android GBA Start/A input, NDS Start/B and visible touch in both layouts, Next Layout, settings Save/Discard and persistence, saved-state restoration after relaunch. DEB and fresh user-installed Flatpak each ran GBA/Vulkan and NDS/OpenGL with actual GTK controls and nonzero states under Xvfb/dummy audio. Windows clean install/application x64/core ABI loading PASS; actual playable GUI acceptance BLOCKED/UNVERIFIED. Automation does not renew human audibility/smoothness or Linux Mint-specific acceptance. Prior accepted owner observations retained separately.

### Known Issues
Windows official SDK and pinned x64 cores pass integrity/load checks, but native surface/audio/input/Rust launch integration is absent. The VM reports no Vulkan ICD and GDI Generic OpenGL 1.1; no signed-in desktop was available for GUI acceptance. EXE is diagnostic only and HTTP download returns 404. Android 3DS remains hidden; no new qualifying 3DS audio/stable-play acceptance. Fresh Mac/Android human audibility and Linux Mint-specific checks were not claimed from automation.

### Do Not Redo
No pending staging work. Do not repeat completed builds/audits/VM setup, rerun the whole historical suite, or recreate disposable roots. Preserve the dirty worktree, both freeze manifests, all final artifacts and diagnostic NSIS, Windows SDK/build/snapshots, current and rollback staging releases. No production operation. Keep Windows VM non-autostart and shut off; keep AVD stopped. Retain existing renderer architecture and Android 3DS/Windows release gates.

### Exact Next Step
Release complete. No pending staging action.

### Important discovery / focused changes — 2026-09-13
- Current staging HTTP baseline captured in `work/release-20260913/staging-before.json`: all four streamed installer sizes/hashes match the old catalog. Its static asset identity remains `df14d4aa2d9a` despite the prior refresh.
- Windows SDK 1.4.357.0 downloaded from official LunarG; installer Authenticode is Valid for LunarG, SHA-256 `81f474711e9042f4cd22b31b2f7a8870db2e428b21586fb43dd80150be97310d`. Installation finished and headers/x64 import library exist. Initial Vulkan probe reports missing ICD; VM exposes Microsoft Basic Display Adapter. This is a real platform limitation, not evidence of Vulkan/3DS performance.
- No Windows native surface/audio/input adapter or Rust launch integration exists in current source. Non-macOS native launch explicitly rejects the request. Do not manufacture acceptance with a placeholder README, copied Mac binaries, browser fallback, or software renderer.
- Preparing Windows x64 mGBA from the existing exact official source revision and melonDS DS from the official v1.3.1 x64 release (GitHub SHA-256 pinned).
- Packaging resource mappings moved into platform overrides; original Mac resource destinations and Vulkan→MoltenVK→Metal path preserved. Windows script now verifies SDK files and core PE machine/hashes and reports missing actual launch integration.
- Added generated `releases/catalog.json` as release metadata, a catalog-derived visible `release_id` independent of web asset cache identity, SHA-bound installer links that reject stale hashes, and prepackage catalog/sidecar validation. Generated release metadata is intentionally finalized after builds and is not a native compilation input.
- Blast radius: RG-070/049-051 release integrity/cache isolation and platform package resources. Focused pre-edit native staging/integration baseline: 15 PASS. No shared emulator/renderer/player input files changed.
- Files changed now: app.py; native-offline/src-tauri/tauri.conf.json and new platform overrides; Windows staging/core preparation scripts; native-offline/package.json; deploy/package-staging.sh; tools/verify-release-catalog.py; integration/freshness tests; checkpoint.
- Exact next step: finish Windows pinned core build and VM graphics proof; run focused checks; freeze implementation source; build the fresh matrix.

### SOURCE_FROZEN — 2026-09-13
- Base commit: `542ef985ddd22435cad00695b065dda1be4f80d3` with preserved dirty tracked/untracked work. Source fingerprint: `07b2597ba72e677d2a0511400bf2172ea02af0df929f0568f37a032ab691c4ce`.
- Exact 389 build/source/input files and their SHA-256 values are recorded in `work/release-20260913/frozen-source-manifest.json`; shared archive is `frozen-source.tar.gz`. Excluded only generated caches/build outputs, installer/catalog metadata, documentation/evidence and unrelated source outside this release.
- Native build inputs (including platform dependency manifests and 22 web-runtime pins) are frozen. Release catalog, sidecars, checkpoint and test evidence are finalized after builds; they are not native compilation inputs. No implementation edits after this point without invalidating affected artifacts.
- Focused final tests: 17 PASS; native script syntax check PASS; locked runtime preparation PASS; diff whitespace PASS. Windows core DLLs load on the VM, libretro ABI 1: mGBA reports `0.11-1-e31759b-dirty` (shallow source count + documented logging-only patch at same accepted commit), melonDS DS reports `1.3.1`.
- Windows SDK/core preflight PASS, final release gate BLOCKED on absent Windows surface/audio/input/Rust native launcher; independent VM graphics proof: Vulkan `vkCreateInstance: Found no drivers`, exit 1; Microsoft GDI Generic OpenGL 1.1.0. No software-renderer workaround.
- Exact next step: build Mac DMG, Dell isolated DEB/Flatpak, and Windows diagnostic NSIS from frozen inputs; build Android next on Mac and complete targeted runtime acceptance before staging publication.

### macOS fresh build complete — 2026-09-13
- Frozen-source DMG: `vibecodedemulator-0.4.4-macos-aarch64.dmg`; 42,282,411 bytes; SHA-256 `d3615455f9f85cdb3c73874ec88b59fd6ec4ff10bf1016d45fa7125142ac3ffb`. Tauri build, deep/strict ad-hoc codesign and DMG integrity PASS. Source parity after build PASS. Fresh packaged launch/runtime smoke pending.
- Windows frozen-source SDK/core gate remains correctly BLOCKED. VM could not resolve the external CDN during web preparation; the identical Mac-prepared bundle will be copied and verified against frozen static/web source plus all 22 runtime hashes. No source change is needed.
- Exact next step: fresh Android build on Mac; Mac mounted-package smoke; Dell build/package runtime checks; resume Windows diagnostic build with verified prepared assets.

### Linux fresh builds complete — 2026-09-13
- DEB: `vibecodedemulator-0.4.4-linux-amd64.deb`, 1,846,616 bytes, SHA-256 `d46f594006647847a70d574ef3382b5d0792dbb16b7dee3ca51f5b1ab5cac85c`. Built in isolated `/var/tmp/an3-frozen-20260913.Wo6HMK`; frozen source parity PASS. Runtime checks pending.
- Flatpak: `an3-offline-0.4.4-linux-amd64-staging.flatpak`, 1,835,048 bytes, SHA-256 `688203648c89cf83e74f160086fa78304360ad306cac4265537cc6770d4a2877`. Built in isolated `/var/tmp/an3-frozen-20260913.Wo6HMK`; frozen source parity PASS. Runtime checks pending.
- Android build completed with bytes identical to the previous release; rerunning package creation after removing only its generated APK output to prove a fresh artifact, then signature and clean AVD install/runtime checks.
- Exact next step: disposable Linux installation and actual GTK controls/core-frame smoke, then fresh AVD install.

### Android / Windows package update — 2026-09-13
- Fresh APK: 86,436,942 bytes, SHA-256 `5486af1cd010ebc6f3dc58cd76106b96fb39049e712f748ec79a34da36f74537`; v2 signature verified using the installed Java 17 path. The first verifier invocation lacked JAVA_HOME (tool environment issue, not a signature failure). Clean AVD uninstall/install and launch completed; runtime smoke remains pending.
- Fresh frozen-source Windows diagnostic NSIS completed: 25,264,627 bytes, SHA-256 `e9396f43a75263b457c729ab670b7893840c9729fc8e02f5c2d2ad08f7f9c237`. Keep it outside the downloadable release catalog.

### Package/runtime verification and cleanup checkpoint — 2026-09-13
- Mac mounted-package GBA/NDS launch and visible Vulkan title frames PASS; menus open with nine sections. Fresh audio audibility and a reliable gameplay-input effect were not independently verified; prior accepted owner behavior is retained. App closed and DMG detached.
- DEB metadata, dependency/install simulation, extracted-package GBA Vulkan and NDS OpenGL smokes PASS. The tiny original NDS fixture was rejected; existing legal `argvTest.nds` homebrew ran with actual GTK controls. Screenshots and window evidence captured.
- Flatpak clean user install PASS with runtime downloaded from embedded Flathub source, then exact installed bundle GBA/Vulkan and NDS/OpenGL GTK controls/launch smokes PASS. Initial artificial empty-system directory lacked an OSTree repo; corrected test isolation to an empty valid repo and reran only the affected install/runtime check. This was a test-environment issue, no source/package change.
- Windows diagnostic NSIS clean install PASS with x64 application and both expected Windows core DLLs, no .dylib/Mac resources. GUI launch cannot be accepted: no interactive user is logged in (only LogonUI session 1); authorized SSH session-0 process has no GUI window. No login/security bypass or renderer workaround performed. Final Windows release gate remains BLOCKED, no catalog download entry.
- Exact next step: stop Windows diagnostic processes/task and gracefully shut VM down; finish AVD native GBA/NDS smoke, then finalize metadata, canonical verification, staging deployment/HTTP parity and cleanup.

### Windows cleanup confirmed — 2026-09-13
- Temporary GUI scheduled task removed and diagnostic process stopped. Graceful Windows shutdown completed. `virsh domstate an3-win11-build` returns `shut off`; autostart remains `disable`; staging service is `active`. SDK, diagnostic installer/build tree and existing VM snapshots are retained.
- Exact next step: complete AVD native GBA/NDS acceptance, then final catalog/canonical checks and staging deploy.

### Android GBA acceptance update — 2026-09-13
- Actual document picker imported the existing owner-used Emerald fixture into private app storage. Fresh native activity showed copyright/title, Start opened New Game/Option, A opened the professor introduction. Quick-save slot 1 created 528,448 bytes; relaunch and Quick Load restored New Game/Option visibly. An earlier rapid click sequence ran ahead of menu creation; stable UI-read/click sequence passed, no source change. Screenshots/XML are in `work/release-20260913/`.
- NDS existing Golden Sun fixture imported through the same native picker and launched; next finish touch/layout/settings/save, then catalog/canonical/deploy.

### Android acceptance and metadata finalization — 2026-09-13
- Fresh clean-installed APK GBA native Start/A input and slot-1 restore after relaunch PASS. NDS Golden Sun Start/B input, visible touchscreen name entry in both Top/Bottom and Side by Side, live layout preview/Discard, Next Layout, Save Settings/FPS persistence and saved-state restore after relaunch PASS. NDS saved state is 19,498,039 bytes; GBA state is 528,448 bytes. Screenshots/XML and state evidence retained in `work/release-20260913/`.
- NDS native diagnostics requested auto/effective Vulkan, core and presentation ~59 FPS, bounded ring=2. Counters are not physical audio/smoothness acceptance. 3DS stays hidden; no repeat of prior 3DS audit.
- Android app stopped, temporary display overrides reset, AVD `emu kill` completed. Windows already shut off/non-autostart; do not restart either for completed checks.
- Generated catalog now records exact fresh four installer hashes/sizes, frozen source fingerprint and honest runtime/signature statuses. Windows gate BLOCKED, filename/hash/URL absent; diagnostic retained separately.

### Final verification correction — 2026-09-13
- Canonical command executed once: 123 Python tests ran, 122 passed; the sole failure expected two hardcoded installer names in `package-staging.sh`. This assertion was stale after RG-072 moved installer selection to the hash-verified generated catalog. Corrected only `tests/test_monitoring.py` to require the verifier invocation, its output consumed as the allowlist, catalog copy and sidecar copy. The corrected exact test passed (1 test, 0.117s). No gate removed/weakened.
- Preserved the original 389-file build freeze and archive. All app/native/package/dependency/deploy inputs match that freeze exactly; only this non-packaged test differs. No release artifact is affected, so no artifact rebuild is required. Final verification snapshot: `106f8008410dac19cc46e95c44ee09c00f839b3ff0f5de8f3cb75c32250de84e` in `final-verification-source-manifest.json`; installer build fingerprint remains `07b2597ba72e677d2a0511400bf2172ea02af0df929f0568f37a032ab691c4ce`.
- Finish the canonical Node touch/renderer checks, native script checks and diff check that were skipped after the Python failure. Do not rerun the entire historical suite. Then deploy staging.

### Predeployment checkpoint — 2026-09-13
- Final local catalog/sidecars and frozen source parity PASS. Expected `/health` and Release Center identity: `staging-e9ac3ffc8a028015`; static web asset remains `df14d4aa2d9a`. All four candidate installer hashes differ from the streamed baseline, including the same-size Flatpak. The visible release ID and SHA-bound URLs distinguish them.
- Immediately before deployment, HTTP old catalog equals the complete previously streamed baseline. Current staging directory is still `20260912-182516-df14d4aa2d9a`; it exists and remains the explicit rollback. Staging active; VM shut off and autostart disabled; AVD absent.
- Authorized next mutation is staging-only deployment through existing tooling.

### STAGING_DEPLOY=PASS — 2026-09-13
- Existing staging tool completed with strict-key SSH preflight PASS. Active release: `/opt/an3-arcade-staging/releases/20260913-204524-df14d4aa2d9a`.
- Explicit preserved rollback: `/opt/an3-arcade-staging/releases/20260912-182516-df14d4aa2d9a`. Static web asset remains `df14d4aa2d9a`; expected catalog-derived release identity is `staging-e9ac3ffc8a028015`.
- Log: `work/release-20260913/staging-deploy.log`. Only staging tooling/service was operated. HTTP stream verification follows; local success alone is not publication byte acceptance.

### RELEASE_COMPLETE — 2026-09-13
- Active staging directory: `/opt/an3-arcade-staging/releases/20260913-204524-df14d4aa2d9a`; release identity `staging-e9ac3ffc8a028015`; static web asset `df14d4aa2d9a`. `/health` reports `ok=true`, `environment=staging`.
- Release Center and catalog expose the new release ID and SHA-bound URLs. All four HTTP downloads streamed and matched both exact byte size and SHA-256; no-store headers verified. Every old candidate hash URL returned 404, including same-size Flatpak. Windows catalog entry is blocked with no URL and direct diagnostic route returns 404.
- Explicit preserved rollback: `/opt/an3-arcade-staging/releases/20260912-182516-df14d4aa2d9a`. Current symlink points to the new directory; staging service is active.
- Lifecycle verified: AVD stopped and absent; temporary display overrides reset; Mac app closed/DMG detached and no unnecessary emulator/Gradle/build process. Windows graceful shutdown completed and final `virsh domstate an3-win11-build` is `shut off`; autostart is `disable`. Session-owned Dell frozen build/archive, two exact Flatpak test-state roots and diagnostic screenshot removed. Windows SDK/build/installer/snapshots, local final artifacts and rollback data retained. Production untouched.
- Evidence: `work/release-20260913/staging-deploy.log`, `staging-after-http-verified.json`, `staging-http-verification.log`, `final-host-cleanup.txt`, `release-complete.json`, artifact matrix, package/runtime screenshots/logs and both source manifests.
- Exact next action: **Release complete; none.**

## Unified player implementation — 2026-09-13 (current active authority)

### Current Status
RELEASE_COMPLETE — Staging and owner-authorized production now serve the current `8b6375…` five-artifact catalog. Production's Android APK is the native-3DS-enabled build: its embedded bridge declares GBA/NDS/3DS, includes the Azahar payload, and its production HTTP bytes match catalog SHA-256 `4ee9e6399a4f08880a71c2c5f3955949cf4b252412883bd3f6151759efc6b3cb`. Production is download-first, does not expose the former server-ROM library, and retains reversible application/SQLite/ROM rollback evidence. The Android AVD is stopped; Windows VM `an3-win11-build` is `shut off` with autostart disabled; Dell's disposable coordinated-build root is removed.

### Source Frozen state
SOURCE_FROZEN — Immutable source manifest `work/release-train/source-freeze-20260914T044409Z-35592/SOURCE_FROZEN.json`; source SHA-256 `8b6375f3897bc6056f9e6af09e64b99a69d859e010e28671fe11843ed577046b`; dependency-cache SHA-256 `73976f9f0e20504980b6d8eec9594bf53ae1b507d58fcaacf4fad356b71d9f9c`. All five installers were built only from this manifest. A deployment failure forced one post-freeze `deploy/update-production.sh` invocation repair (`bash` for a source-tree helper with no execute bit); it changes no native/app source or platform build input, so no installer bytes were affected or rebuilt. Preserve immutable source/cache archive `7de4a7d707d20f33fb6abb4e0f3adfe6cacce93f87db8d1f8a1d4c3bb60fa400` / `c16583c59c2f8e9a4ca7828d390bfb21ef0400ef40ada3a974ac57ed515e6282` and its manifest as superseded diagnostic evidence; it is ineligible for deployment because the owner expanded release scope after it froze. Earlier `e546…` and `67684…` archives/candidates remain diagnostic only.

### Completed This Session
Read only current checkpoint/guards, Windows continuation, player-layering contract and relevant handoff/core/UI sections. Read-only Luna located UI/joystick counterparts. Shared portable core now has Windows DLL loading, owned platform launch integration and Vulkan hardware-frame support; Linux packages the pinned Azahar core; existing layout schema is shared. The prior frozen coordinator completed isolated macOS DMG and Android APK builds, then reached a fresh DEB and failed only when Flatpak could not resolve that exact DEB through its source-relative manifest path. The replacement coordinator completed all five new frozen artifacts. Mounted DMG integrity/deep-strict arm64 code-sign validation, APK v2 signature validation, all-five manifest SHA-256 parity, and Windows gate outputs PASS. The Windows EXE was clean-installed into its own VM directory: installer hash matched, 47 runtime files and 3 native cores matched manifests, all tested executable/core PE headers were x64, native runtime help worked, and the GUI stayed alive for the controlled launch. Final Linux package checks now pass: DEB metadata/installability, controlled GBA/NDS native runs with GTK Controls windows and F5 save states, and Flatpak clean-user installation plus granted-file GBA runtime smoke. The `7de4…` coordinated build completed macOS DMG, Android APK, Dell DEB/Flatpak, and Windows NSIS output from one archive; Windows SDK/core and native-build integrity gates passed. The coordinator's final Windows `Remove-Item` hit the known stale pycache path race after all artifacts had already been copied; exact `C:\AN3\release-train-7de4a7d707d20f33-20260914T041652Z-25655` cleanup passed manually. The final frozen Android APK was installed over preserved legal fixtures and launched GBA/NDS plus 3DS through the real activity. Its 3DS diagnostics record Vulkan, 7,619 core/presented frames with zero drops, nonzero AAudio output, 3DS analog-driven language selection, layout switching, and a Quick Save 1 update from 7,225,645 to 7,237,050 bytes. This satisfies the automated device acceptance evidence for the existing Android 3DS runtime; audibility and human-perceived smoothness remain unclaimed.

### In Progress
None — release complete.

### Remaining
None — release complete. Do not run an additional test/smoke suite unless a future release changes source or artifacts.

### Artifact Matrix
Current frozen publish candidates — macOS DMG `vibecodedemulator-0.4.4-macos-aarch64.dmg`, 42,284,430 bytes, SHA-256 `cb66a012d867edf25360fa53ace4e5eada7b12c3c0e0f5cdf27f563bb3998ff0`; Android APK `vibecodedemulator-0.4.4-android-arm64-staging.apk`, 86,441,975 bytes, SHA-256 `4ee9e6399a4f08880a71c2c5f3955949cf4b252412883bd3f6151759efc6b3cb`; Linux DEB `vibecodedemulator-0.4.4-linux-amd64.deb`, 12,758,676 bytes, SHA-256 `27e0f6c33d1be06f455fc0d1f1f0f26ded5d55b606c0d429c1e639913f431566`; Linux Flatpak `an3-offline-0.4.4-linux-amd64-staging.flatpak`, 12,640,424 bytes, SHA-256 `bb373665c735c602c3a0da467eaeb277592507b5db90edd4f30ba90e70ef3c21`; Windows NSIS EXE `vibecodedemulator-0.4.4-windows-x64-staging.exe`, 42,999,520 bytes, SHA-256 `cacfa0f08d3b2bf65f476de68df7fd110ac3c64e285291eb1d8bfc2db01f4c39`. All five were collected by coordinated build `work/release-train/build-8b6375f3897bc605-20260914T044501Z-35646/artifacts/`; its `ARTIFACTS.sha256` matches catalog sidecars. The exact former local catalog/release set is retained at `work/release-train/prepublish-release-catalog-20260914T045555Z`.

Previous verified release matrix above remains the current downloadable staging baseline. New frozen candidates: macOS DMG `vibecodedemulator-0.4.4-macos-aarch64.dmg`, 42,284,337 bytes, SHA-256 `4ad0885084db04595a1c1fa0c06d5350bc96c6dcf4db227f9a53ce5e9df86681`; `hdiutil verify` and mounted `codesign --verify --deep --strict` arm64 ad-hoc validation PASS. Android APK `vibecodedemulator-0.4.4-android-arm64-staging.apk`, 86,438,119 bytes, SHA-256 `336fa7d7f9126f1bc55c3c744222d4cb3c2162850c89c405a8f8d9b9ffaa4c13`; APK Signature Scheme v2 and Android Debug certificate validation PASS. Linux DEB `vibecodedemulator-0.4.4-linux-amd64.deb`, 12,761,136 bytes, SHA-256 `a731827460f07c019f81cc2e6203844e4253d08a643f1a1d9cb12acac3482993`; Flatpak `an3-offline-0.4.4-linux-amd64-staging.flatpak`, 12,649,000 bytes, SHA-256 `0b355bee1b68b118c6351d2a332b224048eb1998f56a4cf5dfa7abcff0085916`; Windows NSIS EXE `vibecodedemulator-0.4.4-windows-x64-staging.exe`, 43,000,700 bytes, SHA-256 `b38ed4b182d640cd4dccf56421b0478f830b7e90b6bb0bb0bdbf1cf0a78f0c7b`. The integrated Windows preflight printed `WINDOWS_SDK_AND_CORE_INTEGRITY=PASS` and `WINDOWS_NATIVE_BUILD_INTEGRITY=PASS`; clean install/manifest/x64-PE/GUI launch PASS. In the no-user, no-desktop VM session, a legal GBA OpenGL launch ended at `Desktop OpenGL texture allocation failed`; it is recorded as VM display-environment evidence, not a package/core failure and not performance proof. Linux package runtime smoke PASS: DEB metadata and simulated install, GBA/NDS OpenGL native runs (480 core/presented frames and zero drops in each), visible GTK Controls windows, and GBA/NDS F5 state files were captured; Flatpak fresh-user install PASS. A direct CLI ROM path is correctly denied by its sandbox; a fresh-user, temporary read-only fixture grant then ran the Flatpak GBA smoke to timeout PASS. Android GBA/NDS/3DS final-candidate smoke passed, but all listed `e546…` bytes are diagnostic only after the justified Android public-capability correction and will not be cataloged. Superseded first-attempt diagnostic outputs are retained only under `work/release-train/build-67684ceb11ed83ac-20260914T032331Z-4887/artifacts/`: DMG 42,284,320 bytes SHA-256 `21eea20e397fc9112c8c2a701c0bfcf0ad974484feccca0eb3368d250e98fe66`; APK 86,440,263 bytes SHA-256 `4f616d2df70ad077486be7d1f9f3ba981bc2ac9105f7911fa1071bfa00697cd5`. They will not be cataloged or promoted. The earlier Android UI smoke APK is also implementation-only.

### Files Changed
Current edits: shared player model/generator and generated C++/Kotlin/web adapters; round joystick in Android/Mac/Linux/web; Linux 3DS packaging and pinned desktop Azahar fetcher; Windows SDL/Vulkan loader, owned runtime launcher and dependency packaging; `tools/release-train.sh` cross-host frozen-source coordinator; platform-correct Windows staging candidate export; dependency-cache fail-closed preparation; Android/Mac/Linux shared toolbar labels. Current final-release scope also changes `app.py`, `deploy/package-production.sh`, `deploy/update-production.sh`, `deploy/rollback-production.sh`, and adds `deploy/retire-production-rom-library.sh` for download-first production, catalog-only public installers, credential-safe source packaging, and reversible public-ROM retirement. Blast radius: shared input/layout/menu model, native platform adapters, web player controls, Android overlay, platform packaging/core fetch and build coordinator, production routing and deployment payload only.

### Tests / Builds
Final release operations: coordinator `work/release-train/build-8b6375f3897bc605-20260914T044501Z-35646/artifacts/` emitted all five installers and `ARTIFACTS.sha256`; current catalog sidecars were written from those bytes. Staging packaging/deployment preflight passed; health reported `environment=staging`, static asset `baa8a060f571`, release `staging-ced9540547b280ab`. Production package archive `work/production-deploy-artifacts/20260914-115925/an3-arcade-production-20260914-115925.tgz` SHA-256 `5edd43da8ed6f5b1bc5eb778b14d053e24a84bf45a22a2596a3618197daf91a8` passed catalog, allowlist, sensitive-name and credential-shaped-content checks. Production updater reported `PRODUCTION_RELEASE=PASS`, static asset `baa8a060f571`, application backup `/opt/an3-arcade-backups/20260914-120025`, consistent SQLite backup `/srv/an3-arcade/backups/arcade-predeploy-20260914-120025.db`, and ROM retirement archive `/srv/an3-arcade-retired-roms/20260914-120028` with 73 records retired. No post-freeze smoke/test suite was run at the owner's direction. The production Android APK's embedded `native-bootstrap.js` declares GBA/NDS/3DS and native 3DS launch, its Azahar payload is present, and its streamed production HTTP SHA-256 matches the catalog (`4ee9e6399a4f08880a71c2c5f3955949cf4b252412883bd3f6151759efc6b3cb`). Android AVD stop PASS; `virsh domstate an3-win11-build` returned `shut off`; libvirt autostart is `disable`; Dell disposable build root removal PASS.

Focused checks: 12 prior shared UI/staging contract tests PASS; after the Flatpak-path fix, 15 Linux/staging contract tests PASS, Linux script syntax, player-UI generator drift check, and `git diff --check` PASS. An isolated Dell build with an external `AN3_RELEASE_DIR` rebuilt the DEB, byte-compared it to `native-offline/releases/vibecodedemulator-0.4.4-linux-amd64.deb`, and completed the Flatpak bundle (12,643,520 bytes) PASS. Android current-source debug staging smoke APK is 137,617,742 bytes, SHA-256 `2623c447d4c8466320f55d067277e72b357036e579d5f0e05ce7604338f60f40`, v2 signature verified and installed over the existing legal-fixture data. It is not a frozen or publishable candidate. The new Android native activity launched the legal 3DS title, showed shared Menu/Pad/Next Layout/0.5x/1x/x2 controls, toggled layout, and accepted round-stick input. Dell rebuilt the current Linux controls source and, under disposable Intel-Wayland hardware validation, initialized the GTK controls window and reached `core=360 present=360 drops=0` with the Vulkan 3DS core. The headless validation used SDL's dummy audio endpoint only because no physical ALSA device exists there; it is not audio acceptance. Windows current staging PowerShell syntax parser and installed LunarG SDK x64 header/import-library check PASS. The minimal Android capability correction changed only `native-offline/web/native-bootstrap.js` and its focused expectation; `tests.test_offline_consolidation`, `tests.test_android_native_runtime`, and `tests.test_native_staging_contract` passed, Android generated bootstrap synchronization passed, and the replacement source/cache freeze integrity is PASS as recorded above. Frozen Android APK v2 signature verification PASS (Android Debug certificate SHA-256 `b48f3cdecc39349a75b66817aaad645a861d538be34835f290a2aa570c3beb4b`). All five `ARTIFACTS.sha256` entries match their frozen bytes. Windows runtime gate PASS; clean-install manifest checks found 47 dependency files and 3 x64 core DLLs, and GUI launch stayed alive. Final DEB metadata and apt simulation PASS; exact extracted GBA/NDS package runs reached 480 core/presented frames with zero drops, exposed real GTK Controls windows, and produced F5 state files. Flatpak clean install and scoped-fixture runtime smoke PASS.

### Runtime Evidence
Final frozen Android 3DS evidence is captured under `work/unified-player-20260913/`: visible Pokémon X language screen, current shared toolbar, circular base/smaller circular thumb, analog input changing the selected language, Next Layout changing to the vertical composition, and native Diagnostics reporting `requested=auto effective=vulkan core=7619 presented=7619 drops=0`, nonzero AAudio output and `save completed`. Quick Save 1 grew from 7,225,645 to 7,237,050 bytes. These automated signals establish the native path, but do not claim audible sound or human-perceived smoothness. Linux actual Intel Vulkan/Wayland launch reaches 960 core/presented frames with zero drops and persistent title save creation, while the current GTK-controls run proves that the companion GTK controls window initializes in the real Vulkan session. Windows package/launch integrity is proven, not real VM Vulkan/3DS performance; the unlogged-in VM console has no active desktop user and its legal GBA OpenGL smoke stopped at texture allocation, so no Windows GBA/NDS/3DS gameplay or file-picker/settings/save interaction is claimed from this VM session.

### Known Issues / approach
The release preserves Vulkan-first/OpenGL/GLES fallback paths and does not add a software renderer to fabricate Windows VM performance. Android device diagnostics prove AAudio delivery rather than human audibility; the existing Redmi-specific crackle limitation remains open. Windows package and staging gate are proven, while real Windows VM Vulkan/3DS performance remains unclaimed.

### Do Not Redo
No full-repo/history audit, destructive worktree cleanup, Windows install/OVMF/VirtIO rebuild, or further production mutation without a new owner request. Keep the prior staging baseline, production application backup, SQLite backup, ROM retirement archive and local release-catalog backup intact.

### Exact Next Step
Release complete. On a future change, start from this checkpoint, retain the listed rollback evidence, and create a new source freeze before rebuilding affected artifacts.

### Shared joystick implementation update — 2026-09-14
- Affected baseline: 68 tests PASS (native input/renderer/menu/Android/Linux and web touch/renderer guards), log `work/unified-player-20260913/baseline.log`.
- Added `shared/player-ui.json` and deterministic generator for shared menu names, panel bounds, joystick deadzone/travel/thumb geometry in C++/Kotlin/web. Android now draws a circular base and smaller movable thumb with owned-pointer/cancel/focus reset; Mac Circle Pad uses the same geometry and reset; Linux GTK has a circular analog widget using shared normalization.
- Implementation is in progress, not runtime accepted. No render backend changed. Web joystick, desktop core fetch, Windows adapter and build coordinator remain next. Prior staging/artifact bytes remain untouched.

### Portable runtime integration update — 2026-09-14
- Shared joystick/model behavior: 18 focused tests PASS, including compiled C++ vs web axis parity, circular bounds/deadzone, EmulatorJS half-axis magnitude/reversal/release and Linux menu model. Prior 68-test baseline retained. macOS native compilation and Android Kotlin compilation PASS; no live acceptance claim yet.
- Official Azahar 2126.0 desktop core fetcher now pins archive/core/license/source hashes. Linux core 47,237,568 bytes SHA `a447e9ecb7b4ef0a530d31eeb83a39edf4697f17bb3e44251f27a1d25fde7662`; Windows core 33,849,344 bytes SHA `5ed23fda6ed3fcc5846bf2ca99c2d482601e611f5e718af936431fb99db4ecf2`. Linux DEB development build with 3DS core PASS in isolated `/tmp/an3-unified-20260914/native-offline`; it is not frozen/release-accepted and has not replaced staging bytes.
- Official MSYS2 archive verified SHA `3035f76513e4d91259f875f5d81507cb48d44a9d56aa022cb1967561bd614fa8`; installed into VM `C:\AN3\msys64`, signed package-manager installation of UCRT64 GCC/SDL2/GTK3/Vulkan dependencies completed. No Windows/OVMF/VirtIO reinstall.
- Windows uses the same portable native core/SDL/GTK/render code, with a parent-owned private control pipe and native GUI. Added platform storage/core paths, deterministic dependency closure bundle, Rust launch/stop/input ownership and fail-closed source/binary verification. First Windows compile exposed a POSIX-only Vulkan loader include; added a Windows `LoadLibraryExW` adapter restricted to application/System32 directories. Render loops/frame resource architecture unchanged. Rebuild, closure verification and clean-install probe now pass; see the superseding Windows/live-3DS evidence update below.
- Fixed SDL window setup so missing Vulkan can reach the existing OpenGL fallback. This does not supply a software renderer or establish VM 3DS performance.
- VM and AVD are currently running only for the active focused validation; VM autostart remains disabled. Final lifecycle cleanup remains mandatory. Existing staging `staging-e9ac3ffc8a028015` and rollback remain intact; production untouched.
- Logs/evidence: `work/unified-player-20260913/` (`macos-compile.log`, `android-compile.log`, `linux-build.log`, `windows-runtime-build.log`, `msys2-packages.log`, `iteration-tests.log`). Full UI parity, qualifying 3DS runtime acceptance and one build coordinator remain unfinished.

### Windows and live 3DS evidence update — 2026-09-14
- Windows native runtime now builds from the verified UCRT64 dependency set and bundles a deterministic 47-file x64 PE closure plus pinned Windows mGBA, melonDS and Azahar cores. `build-windows-staging.ps1 -VerifyOnly` reports `WINDOWS_SDK_AND_CORE_INTEGRITY=PASS`, `WINDOWS_NATIVE_BUILD_INTEGRITY=PASS`, and `WINDOWS_BUILD_PATH=READY`; `cargo check --target x86_64-pc-windows-msvc` passes. Fresh NSIS diagnostic candidate `work/unified-player-20260913/windows/VibeCodedEmulator_0.4.4_x64-setup.exe` is 42,991,850 bytes, SHA-256 `fd703811a272b0aff3c11b1fc0e16c03b008f230455fea132feb7dac7a6b62d2`. A clean silent install verifies all 47 runtime files, all three cores, executable architecture and a live process; this does not prove hardware Vulkan, visual gameplay, audio or 3DS performance in the VM.
- Android staging candidate `work/unified-player-20260913/candidates/vibecodedemulator-0.4.4-android-arm64-staging.apk` is 86,436,942 bytes, SHA-256 `2266914700202769fb9fda3e7e5c67b1b46f3f419808847e4db8aa0740ded93f`, with Android v2 signature verification PASS. On the existing AVD, a legal existing 3DS title launched through the actual native activity using Vulkan; captured evidence shows video, circular base/smaller thumb movement, language-selection input change, layout switching, 59 FPS counters and a 7,225,645-byte quick state. Nonzero audio samples were emitted, but audibility remains unproven; keep public Android 3DS visibility gated until the full acceptance contract is met.
- Dell Debian: installed only `weston` and `vulkan-tools` for disposable hardware validation. A root-owned temporary Wayland runtime plus Weston headless GL renderer uses `/dev/dri/renderD128` and Intel UHD 770; independent `vkcube --wsi wayland` completed. The isolated fresh DEB native runtime launched the legal 3DS title with Azahar's Vulkan hardware renderer, negotiated the Intel device, emitted `AN3_NATIVE_READY vulkan`, and reached `core=960 present=960 drops=0` before a clean controlled exit. It created real per-title save data and shader cache in the disposable root. Earlier Xvfb and software-headless Weston failures were environmental WSI limitations, not a runtime fallback. This evidence does not establish a human-visible screen or audible audio; it proves real Intel Vulkan core/presentation progress without a software renderer.
- Prior staging release and rollback remain untouched; production was not accessed. AVD and VM remain running only while the active implementation requires them; final shutdown requirements remain in force.

### Owner-requested APK 3DS production reupload — 2026-09-14
- COMPLETE: uploaded the unchanged 86,441,975-byte 3DS-enabled APK and SHA-256 sidecar again; production replacement was verified, backup retained at `/opt/an3-arcade-backups/apk-reupload-20260914T053753.244863Z`.
- Public HTTPS download returned HTTP 200 and SHA-256 `4ee9e6399a4f08880a71c2c5f3955949cf4b252412883bd3f6151759efc6b3cb`; no-store/BYPASS, exact Release Center link, stale-hash 404 and production health passed. Catalog and other platform installers were preserved; no service restart or new gameplay smoke.
- Full handoff: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/APK_3DS_PRODUCTION_REUPLOAD_20260914.md
- Download verification: /Users/meomeo/Documents/Codex/2026-09-14/use-codegraph-first-to-narrow-symbols/work/apk-reupload/production-http-verification.json
- Exact next step: none; the requested reupload is complete.

## Web/player parity fixes and platform verification — 2026-09-15 (this session)

### Completed
- Fixed the stale integration contract that failed canonical verification: production is
  download-first and intentionally retires the public server-ROM library. `tests/test_integration.py`
  now runs library-surface tests against a second staging-environment server (`ArcadeLibraryIntegrationTests`,
  port 18792) and adds `ArcadeProductionIntegrationTests` for the production 404 gating, current-catalog
  downloads and HTTP/1.1 reuse. Full Python discovery is 129 tests, all PASS (was 127/129).
- Fixed RG-076: the versioned `/static/v/<asset>/...` route omitted `player-ui.js`, so `/offline` and
  `/play` loaded a 404 for the generated shared UI model; `globalThis.AN3PlayerUI` stayed undefined and
  the web virtual analog joystick never rendered. `app.py` now serves it, and the integration test derives
  every served name from `app.PLAYER_BOOT_ASSETS`.
- Fixed RG-077: the offline player had no D-Pad/Analog-Joystick selector. `static/offline.js` now renders
  `#padDirectionalControl`, matching the DMG/native control model.
- Added RG-078: browser-only 3DS gate. Runtime evidence (Chrome 152, ANGLE Metal M5, cross-origin
  isolated, legal homebrew CIA): the Azahar wasm core boots but reports `getVideoDimensions() = -1`, has no
  OpenAL/WebAudio context, and leaves both the EJS source canvas and the WebGPU presentation canvas black
  for both the cached `latest` (2026-08-24) and CDN `nightly` (2026-07-25) cores, after clearing caches and
  unregistering the service worker. The web shell now disables 3DS cards with a native-app prompt and a
  `/download-app` link; Android/macOS/Windows/Linux native 3DS playback is unchanged.

### Runtime verification (2026-09-15)
- Web (local fixed build `0c307876a21f`, Chrome 152 headless via CDP, legal fixtures): GBA frames
  82→564, NDS 112→594; 3DS Azahar core preloaded (3.8 MB) and verified in `EmulatorJS-core`; joystick
  selector toggles `.analog-mode`; 3DS cards disabled by RG-078 gate; console errors are limited to the
  benign EmulatorJS `checkForUpdates` CDN fetch (blocked by COEP, non-fatal).
- Android AVD `codex-nds-api35`, installed APK 0.4.7 (`versionCode 4007`), via WebView CDP:
  GBA "Minimal GBA" Pokémon Emerald intro at 59/59 FPS; NDS "Minimal NDS" Golden Sun title/boot at
  59–60/60 FPS; 3DS "Minimal 3DS" Pokémon X language screen at 58/58 FPS with the circular joystick and
  native nine-control overlay. `topResumedActivity=NativeGameActivity`, isolated `:game` process stable
  for 60 s+, zero `FATAL EXCEPTION`/tombstone entries, clean return to `MainActivity`.
- Evidence: `work/apps-web-20260915/` (screenshots, CDP drivers, logs).

### Blocker / not done
- LAN deployment blocked at the end of the session: `192.168.1.8` still answers ICMP but refuses TCP on
  22/8091/8092 from this Mac (public `https://an3tocom.space` health remains 200 via Cloudflare). The
  new web source package was built locally (`work/production-deploy-artifacts/20260915-172108/`,
  SHA-256 `82232f4c90ed0d8449ad0559d22858eae0a63a1368717664ee97c6cb901d0758`, expected asset
  `17885c13838a`) but was not published. Rebuild the package after the RG-078 gate change before deploy.
- Web 3DS playability is an upstream Azahar wasm limitation (RG-078), not fixed in this session.

### Exact next step
- After the LAN path is restored: run `tools/release-train.sh --staging verify all`, rebuild
  `deploy/package-production.sh` + staging package from the final source, deploy staging, verify HTTP
  parity, then run the owner-authorized production update and verify public HTTPS.

### Deployment completed — 2026-09-15 (same session)

- Root cause of the LAN outage: the Mac's Wi-Fi is on a network that also uses
  `192.168.1.0/24`; the `.8` it pinged was a different device. The real host
  (`debian`, `wlp0s20f3` = `192.168.1.8`) answers ICMP but not TCP from that
  network. The host is healthy: `ss -ltn` shows `0.0.0.0:22`, `0.0.0.0:8091`
  and `192.168.1.8:8092`, and UFW is active with the intended rules
  (`22/tcp Anywhere`, `8091/tcp` and `8092/tcp` from `192.168.1.0/24`).
  `https://an3tocom.space` stayed online the whole time because cloudflared
  connects outbound to `127.0.0.1:8091`.
- Deploy path used: Tailscale peer `debian` = `100.94.63.8`. Strict host-key
  checking was preserved by verifying that the live ED25519 host key
  (`SHA256:GKhJRLdeuup0u+mawvqP81INvw0vG7LAdWpzqL9sVBo`) matches the existing
  `192.168.1.8` entry in `~/.ssh/known_hosts`, then pinning that key for
  `100.94.63.8`/`debian` in `work/apps-web-20260915/known_hosts`.
- Staging: `STAGING_RELEASE=PASS`, asset `0c307876a21f`, release
  `/opt/an3-arcade-staging/releases/20260915-184351-0c307876a21f`, rollback
  `/opt/an3-arcade-staging/releases/20260915-134525-690bcb150246`. Health,
  four-asset `static/v` byte parity and the versioned `player-ui.js` 200 were
  verified through a strict `ssh -L 18092:192.168.1.8:8092` tunnel.
- Production: `PRODUCTION_RELEASE=PASS`, asset `0c307876a21f`, release
  `production-548d5753f65777cf`, application backup
  `/opt/an3-arcade-backups/20260915-184440`, SQLite backup
  `/srv/an3-arcade/backups/arcade-predeploy-20260915-184440.db` (integrity
  PASS, SHA-256 `4a75b6cc7b9155ce5fad1f5d8593c67c4ec7c0f3d4cc0466e5c7f4d69fe3285b`).
  Public HTTPS: `/health` reports the new asset; `/`, `/offline`,
  `/download-app` 200; all four versioned assets byte-parity with local source;
  the deployed `offline.js` contains the RG-077 selector and RG-078 gate;
  `/games`, `/api/library-version` and `/game/*` correctly 404 (download-first);
  all five catalog installers return `200` with exact expected sizes and
  `no-store`; a stale-hash URL returns 404. Production GBA web smoke: frames
  `41 → 403` with "Video active".
- Lifecycle: staging tunnel stopped, local Chrome stopped, host `/tmp` deploy
  files removed. `an3-arcade`, `an3-arcade-staging` and `cloudflared` are all
  `active`.

## Android 0.4.8 native launch recovery + lock removal — 2026-09-15 (this session)

### Owner report
NDS/3DS would not play on the owner's device; the production APK was still 0.4.7 and
showed a front-end-style dead end "Native ROM is unavailable". The owner asked for the
locks to be removed, not for another lock.

### Root cause
`MainActivity.launchNative(romId, system)` called `nativeRomFile(romId, system)`, which only
matched `dataDir/an3-roms/<romId>.<ext>`. When a record's stored id no longer matched its
copied file (for example a WebView store restored while the private file was not, or a
legacy record), the lookup returned null and the launch failed with the dead-end string.
The browser-only 3DS lock added earlier the same day (RG-078) was also a lock the owner
explicitly rejected.

### Fixes
- Removed the browser-only 3DS lock; the play control is bound only to the installed
  Android capability declaration (RG-078 superseded).
- `MainActivity.nativeRomFile(romId, system, expectedSize)` now recovers a unique ROM of
  the same system whose byte length equals the recorded size, and `launchNativeSized`
  exposes that to the library. The exact `<romId>.<ext>` match stays first.
- `static/offline.js` passes `game.size` to the native launcher and, only when a ROM is
  genuinely absent, adds a one-tap "Nhập lại ROM" (`data-repair-native`) that re-imports
  for the same record id and continues straight into native play. The play button is never
  disabled for a supported system.
- Version bump 0.4.7 -> 0.4.8 (versionCode 4008) per the app versioning rule; native shell
  asset query strings bumped to `?v=0.4.8` so the WebView cannot serve a cached old
  `offline.js`.

### Verification
- Canonical suite `tools/release-train.sh --staging verify all`: 131 Python tests, web NDS
  touch, 11 renderer cases, `npm run check`, `git diff --check` -> PASS.
- AVD Android 15, installed 0.4.8 (`versionCode 4008`, Android Debug signer `b48f3cde…`):
  fresh-UUID `launchNativeSized` with the real NDS file's exact size returned `""` and
  resumed `NativeGameActivity` with the `:game` process; the same UUID with the legacy
  `launchNative` still returned "Native ROM is unavailable"; the missing-file card showed
  the error note plus the enabled "Nhập lại ROM" button; the real NDS card launched.
- APK: `vibecodedemulator-0.4.8-android-arm64-staging.apk`, 48,080,829 bytes, SHA-256
  `9fb8b5c4b1f1e81490f306e97b797ff56d219fb4510a5507767b7be1834a1de6`, v2 signature PASS.

### Deployment
- Staging `STAGING_RELEASE=PASS`, asset `add269259a01`, release
  `/opt/an3-arcade-staging/releases/20260915-200544-add269259a01`, rollback
  `/opt/an3-arcade-staging/releases/20260915-184351-0c307876a21f`.
- Production `PRODUCTION_RELEASE=PASS`, asset `add269259a01`, release
  `production-32090271423455aa`, app backup `/opt/an3-arcade-backups/20260915-200650`,
  SQLite backup+integrity PASS. Public HTTPS serves the 0.4.8 APK at its exact size and
  SHA-256 (`9fb8b5c4…`, verified by full download), all four versioned assets byte-parity,
  the deployed `offline.js` has no browser lock and does contain the repair action, the old
  0.4.7 URL returns 404, and `/games`/`/api/library-version`/`/game/*` remain 404.

### Android 0.4.9 — long-session and suspension stability — 2026-09-15 (this session)

Owner report: 3DS played but crashed after a while; acceptance was >4 minutes of play.
The AVD could not reproduce a foreground crash (12+ minutes, RSS flat), so the fixes
target the documented Azahar Android surface/lifecycle crash class and main-thread load.

- `NativeGameOverlay.updateDiagnostics` no longer calls `saveDirectory.walkTopDown()` every
  second on the UI thread; it checks the deterministic auto-save file at most every 15 s or
  when an Auto Save message arrives. This removed a growing main-thread I/O scan.
- Auto Save defaults on (activity start flag, settings command, overlay flags) so any
  device kill preserves progress.
- `NativeGameActivity` handles `onTrimMemory`/`onLowMemory` with an Auto Save request.
- `jni_runtime.stop_session` now waits up to 1500 ms for the worker (`Session::finished`)
  before detaching its join, so the renderer cannot touch a destroyed `ANativeWindow`
  (Azahar's known Android surface crash on rotation/suspension/screen-off).
- Version 0.4.9 / versionCode 4009; shell asset query strings bumped to `?v=0.4.9`.

Verification: canonical suite 131 Python + Node + npm + diff PASS. AVD Android 15 (2 GB),
APK `vibecodedemulator-0.4.9-android-arm64-staging.apk` 48,083,017 bytes SHA-256
`c98518941c213bbb350d37e7c0519a9cc4bcf07e2f5cd34d3cf7873df8a9a49a`: 337 s of in-game 3D
gameplay with input at ~577 MB RSS and zero crashes; HOME now leaves both processes alive
(on 0.4.8 the `:game` process was killed on the same AVD). Menu (nine sections) renders.

Deployment: staging `STAGING_RELEASE=PASS` release `/opt/an3-arcade-staging/releases/20260915-204949-add269259a01`
(asset `add269259a01`, rollback `20260915-200544-add269259a01`). Production
`PRODUCTION_RELEASE=PASS`, asset `add269259a01`, app backup `/opt/an3-arcade-backups/20260915-205047`,
SQLite backup+integrity PASS. Public HTTPS serves the 0.4.9 APK at exact size and verified
SHA-256, old 0.4.8 URL 404, all five installers exact-size `no-store`.

### Android 0.4.10 — 3DS Adreno Vulkan crash fixed via OpenGL ES — 2026-09-15 (this session)

Owner report: 3DS played but crashed after a while on the physical device. Acceptance:
play more than 4 minutes, then deploy production.

Root cause (physical Redmi `25057RN09G`, Android 16, Adreno 619, driver 0762.40): the
`:game` process aborted ~10 s into 3DS gameplay with SIGABRT in the "Pipeline worker"
thread. Tombstone: `terminating due to uncaught exception of type vk::UnknownError:
vk::Device::createGraphicsPipelineUnique: ErrorUnknown` at `Vulkan::GraphicsPipeline::Build`.
Azahar 2126.1.1 (the current pinned release) treats any non-success pipeline result as
fatal. The AVD (Apple-host GPU) and macOS/MoltenVK never reproduce it.

Fix: Android 3DS now defaults to the core's OpenGL ES renderer
(`citra_graphics_api=OpenGL`). The frontend owns the EGL context, returns a color FBO from
`get_current_framebuffer`, resolves GL entries via `eglGetProcAddress`, and blits the core's
layout region into the window with aspect-fit letterboxing. `NativeCoreHost::initialize`
takes the graphics API; an explicit `requested=="vulkan"` still forces Vulkan; GBA/NDS are
unchanged. Vulkan remains the path on macOS/Windows/Linux.

Verification: canonical suite 131 Python + Node + npm + diff PASS. Physical device with
APK `vibecodedemulator-0.4.10-android-arm64-staging.apk` (48,091,373 bytes, SHA-256
`7cff442f13c74e9e987efcca1baf8d5bd933c5153b37762b29f43bf9a8422506`): 3DS rendered both
screens correctly at 52–57 FPS and played 337 s (5.6 min) with input, zero
SIGABRT/SIGSEGV/vk:: entries.

Deployment: staging `STAGING_RELEASE=PASS` release
`/opt/an3-arcade-staging/releases/20260915-215308-add269259a01` (rollback
`20260915-204949-add269259a01`). Production `PRODUCTION_RELEASE=PASS`, asset
`add269259a01`, app backup `/opt/an3-arcade-backups/20260915-215421`, SQLite backup +
integrity PASS. Public HTTPS serves the 0.4.10 APK at exact size and verified SHA-256, the
old 0.4.9 URL returns 404, and all five installers match their catalog sizes.

## Dark-purple UI refresh — Dashboard, /offline, native app — 2026-09-16 (this session)

### Scope
Product-focused redesign of the three surfaces the owner called out, English-only,
staging-only. No production deploy.

### Web
- Admin dashboard (`app.py` `admin_page`/`dashboard_analytics`): date-range selector
  (7/30/90/All time), "Total Visits" + "App Downloads" cards with real previous-window
  percentage change, one clean two-line chart (visits violet `#a855f7`, downloads cyan
  `#22d3ee`), server status moved into a collapsed `<details>` panel that only polls
  when opened. Play/player/ROM-catalog analytics stay removed. `format_dashboard_count`
  now uses English thousands separators.
- `/offline` (`app.py` `offline_page`): minimal centered notice ("You're offline",
  description, Try Again, three small facts). Removed the ROM import form, library,
  core manager, device-readiness cards and the player script bundle. Route no longer
  uses the permissive player CSP. The obsolete `welcomeGuide` onboarding and its nav
  trigger were removed from `layout()`.
- Brand is now `AN3` (was `"Ăn 3 Tô Cơm"`); remaining user-facing Vietnamese error
  strings were translated. Manifest + theme color updated to `#07060c`.
- `static/theme-violet.css` gained dashboard, offline-notice, disabled-button and
  chart-footer rules and neutralizes the legacy lime admin chrome.
- `static/site.js` lazily starts server-status polling on `<details>` open.

### Native app (offline-first)
- `native-offline/web/index.html` rewritten as a Play/Library/Settings/Help/About shell
  with a desktop sidebar and a portrait bottom nav. Library keeps Add ROM, search and
  the `offline.js` grid; Settings/Help/About show only real state.
- New `native-offline/web/native-app.js` (section switching, search filter, Open ROM).
- `native-offline/web/native.css` rewritten for the violet theme; `theme-violet.css`
  is now linked. The local-ROM import/native-launch pipeline in `static/offline.js`
  is unchanged; `android-staging.js` label target updated.
- Version bumped 0.4.x → 1.0.0 (tauri configs, package.json, build scripts, catalog).

### Verification
- `PYTHONPATH=. python3 -m unittest discover -s tests -p 'test_*.py'`: PASS.
- `node tests/web_nds_touch_behavior.test.js`, `node tests/web_renderer_behavior.test.js`,
  `node native-offline/scripts/generate-player-ui.mjs --check`: PASS.
- `npm --prefix native-offline run check`, `git diff --check`: PASS.
- Headless Chrome review (desktop/tablet/phone) of `/offline`, `/admin`, homepage and
  the native shell: no horizontal overflow at 360/390/1024/1440.
- `tools/verify-release-catalog.py`: `RELEASE_CATALOG=PASS (5 installers)`.

### Artifacts + staging
- `native-offline/releases/vibecodedemulator-1.0.0-macos-aarch64.dmg` (42,240,094 B,
  sha256 `6a93c60ef580a90bc326823bace6b02c7bbd1f90400d14e3176bca58ffd02924`).
- `native-offline/releases/vibecodedemulator-1.0.0-android-arm64-staging.apk`
  (48,104,490 B, sha256 `43e6f907f6f346affcdd95db6b7994e8fc0bdf72c15db4a1a147613bca475fdf`).
- Staging deploy: `STAGING_RELEASE=PASS`, asset `73db1627eb30`, release
  `/opt/an3-arcade-staging/releases/20260916-000023-73db1627eb30`, rollback
  `/opt/an3-arcade-staging/releases/20260915-232627-ee43c8150f95`. Staging listens on
  `127.0.0.1:18093`; `/offline` is the minimal notice, brand `AN3`, both 1.0.0 installers
  serve at exact size, superseded `0.4.5` DMG is 404.
- Production untouched: `/health` still reports asset `add269259a01`, release
  `production-827e2af4bb60ed30`.
- Linux DEB/Flatpak and Windows EXE remain the previous `0.4.5` verified builds
  (cannot be rebuilt from this macOS host); they keep the pre-refresh native UI until
  rebuilt on their own toolchains.

## All-platform 1.0.1 parity + Windows .exe + Android Vulkan color fix — 2026-09-16 (this session)

Owner request: bring `.dmg` `.exe` `.deb` `.flatpak` to the same UI/UX + features as the
staging `1.0.0` DMG, fix the Android 3DS "intermittently loses color channels on Vulkan"
report, keep GBA/NDS/3DS smooth/stable/no-crash on every build, and deploy the fixed
versions on staging. Staging-first; production untouched.

### Root causes found
- **Windows EXE was stale `0.4.5`.** `build-windows-staging.ps1` hard-coded `0.4.5`
  filenames and `src-tauri/Cargo.toml` (and `build-linux-staging.sh`,
  `verify-flatpak-install.sh`, the Flatpak manifest/metainfo) still carried `0.4.5`; the
  Windows artifact was never rebuilt after the violet UI refresh.
- **Android Vulkan color handling.** `vulkan_backend.cpp::create_swapchain_resources`
  defaulted `selected = formats.front()`. If the driver listed no preferred
  UNORM+sRGB-nonlinear format, it silently kept a wide-gamut (e.g. DISPLAY_P3) surface
  color space; Android's compositor then reinterpreted the display-referred UNORM frame's
  channels. MoltenVK/desktop always advertise the standard space, so it only showed on
  Android. The existing warning comment confirmed the hazard but the fallback remained.
- **Windows build hygiene.** macOS AppleDouble `._*` files and the excluded Android
  `gen/` tree broke `generate-player-ui.mjs --check` and Tauri's capabilities loader; the
  Dell needed rustup `~/.cargo/bin` (1.98) instead of system rustc 1.85 and `CI=true`.

### Fixes (shared layer first)
- `native-runtime/video/vulkan/vulkan_backend.cpp`: never adopt a non-standard surface
  color space — prefer a blit-capable format with `VK_COLOR_SPACE_SRGB_NONLINEAR_KHR`,
  then any blit-capable standard-space format, before the `formats.front()` last resort.
- Version bump `1.0.0 → 1.0.1` (bug fix) applied to `tauri.conf.json`,
  `tauri.android.conf.json`, `package.json`, `Cargo.toml`, `web/index.html`,
  `build-windows-staging.ps1`, `build-linux-staging.sh`, `build-android-staging.sh`,
  `package-macos.sh`, `verify-flatpak-install.sh`, the Flatpak manifest + metainfo, the
  release catalog and sidecars.
- No renderer architecture change; the native Windows/Linux presenter and macOS
  Metal/MoltenVK path are untouched. Web shell and native overlay remain the one shared UI.
- Added a temporary `an3ui` autologon local admin on the VM (guest-only, reversible) to
  obtain an interactive desktop for screenshots; `qemu-monitor input-send-event` +
  `virsh screenshot` drive/read the guest.

### Builds (all from the current dirty worktree)
- macOS DMG `vibecodedemulator-1.0.1-macos-aarch64.dmg` — 42,239,986 B,
  sha256 `a03e6017531ef2188595dfa6a6d91d9b2d5956c587cc68c6707bb65e8fc9659e`.
- Android APK `vibecodedemulator-1.0.1-android-arm64-staging.apk` — 48,105,150 B,
  sha256 `c198d425be08078885c1dcdf5fc65e60388c6e25051020771eef3a18344fbc3f` (includes the
  Vulkan color-space fix).
- Windows NSIS `vibecodedemulator-1.0.1-windows-x64-staging.exe` — 42,530,728 B,
  sha256 `86ceef648d8f40c1b4bf0b417bc3b985a064f8e77c68fbee15673c9c0cda354e` (built on
  `an3-win11-build`; 47-file x64 runtime closure + 3 pinned cores; `prepare-web` re-run
  so the embedded shell is 1.0.1).
- Linux DEB `vibecodedemulator-1.0.1-linux-amd64.deb` — 44,215,158 B,
  sha256 `f57c5defdcbf86fea196380e91cbff4c9803b3b8a8c4636a3c1eddb93bea617b`.
- Linux Flatpak `an3-offline-1.0.1-linux-amd64-staging.flatpak` — 27,819,624 B,
  sha256 `2b46b153c5e32bb044a281eca8aca597e6bac7dd5a7eb05d31fa24c07f9c18e5`.
- `tools/verify-release-catalog.py`: `RELEASE_CATALOG=PASS (5 installers)`.

### Windows runtime evidence (real screenshots, personally inspected)
VM `an3-win11-build` (Windows 11 x64, 1280x800, Microsoft Basic Display Adapter). Exact
final 1.0.1 installer silently installed to `C:\AN3\app100` then launched in the `an3ui`
desktop session. Captured with `virsh screenshot` under `/tmp/an3-win/`:
`app1/app2.png` (Play), `click.png` (Library), `win-settings.png`, `win-help.png`,
`win-about.png`, `win-max3.png` (maximized), `fin2-about.png` (final 1.0.1 About).
Verified: violet AN3 sidebar, Play/Library/Settings/Help/About, Add ROM (GBA·NDS·3DS),
empty-library state, facts, maximized reflow, no Windows-only visual artifacts; UI/UX
matches the shared macOS shell (identical `web/` + `site.css` + `theme-violet.css`).
- In-game on the VM remains GPU-blocked: `Vulkan unavailable … Vuek … Desktop OpenGL
  texture allocation failed.` No Vulkan ICD and GDI Generic OpenGL 1.1 only. Per RG-073
  no software renderer was installed to fabricate acceptance. Windows GBA/NDS/3DS
  gameplay is therefore **UNVERIFIED on this VM** (shell UI is verified).

### Android runtime evidence
AVD `codex-nds-api35` (arm64): 1.0.1 APK installed; violet shell renders (`avd2.png`),
Library lists the imported GBA (`avd-lib.png`); native GBA launched into
`NativeGameActivity` (`:game` process) and rendered the title at `core=59 present=59`
with the shared overlay (`avd-gba-play.png`), AAudio started, no crash. The AVD uses the
Apple host GPU and cannot reproduce the Adreno-specific channel loss; the fix is the
shared presenter change above. The 1.8 GB legal 3DS fixture was not re-imported this
session (import cost); 3DS Vulkan channel behavior on Adreno remains **UNVERIFIED on
hardware**.

### Staging
`STAGING_DEPLOY=PASS`, asset `73db1627eb30`, release
`/opt/an3-arcade-staging/releases/20260916-012702-73db1627eb30`, rollback
`/opt/an3-arcade-staging/releases/20260916-000023-73db1627eb30`. Staging
(`127.0.0.1:18093`) serves all five 1.0.1 installers at exact size + SHA-256; superseded
`1.0.0` and `0.4.5` URLs return 404. Production untouched.

### Remaining / next step
- Windows in-game gameplay (GBA/NDS/3DS) needs a real Windows GPU (native host or a
  safe, reversible iGPU option); not attempted this session to avoid destructive VFIO
  changes. UI/UX parity is complete.
- Optional: import the legal 3DS fixture on a real Adreno device to confirm the
  color-space fix end-to-end.
- VM cleanup performed after capture: `an3ui` autologon removed + user deleted, temp
  scheduled tasks removed, guest shut down, autostart left disabled; AVD stopped.
