# VibeCodedEmulator multi-model release train
RUN: 2026-09-08-multimodel-release-train
CURRENT_PHASE: release verification and staging publication
CURRENT_STATUS: COMPLETE_WITH_KNOWN_LIMITATIONS
LAST_COMPLETED_PHASE: portable Android and Linux native release verification
NEXT_PHASE: qualify Android 3DS emitted/audible audio before advertising it; validate Windows on a real Windows host
NEXT_MODEL: Terra Ultra

## Current authority — September 12, 2026

This entry supersedes older P5/Linux-blocked, “audibility unverified,” artifact-byte, and staging-asset statements below. Historical entries remain provenance only.

- **Staging only:** asset `df14d4aa2d9a` is live at `/opt/an3-arcade-staging/releases/20260912-164924-df14d4aa2d9a`; the preserved rollback target is `/opt/an3-arcade-staging/releases/20260911-230833-bef86865b122`. Production was not accessed, packaged, changed, or restarted.
- **Release Center:** macOS DMG, Android APK, Linux DEB, and Linux Flatpak are available only after catalog size/SHA-256 verification. HTTP stream downloads from staging matched each local byte count and SHA-256. Windows remains blocked with no URL.
- **OWNER-VERIFIED runtime/audio evidence:** current macOS DMG GBA/NDS gameplay is smooth; current Android APK GBA/NDS gameplay is smooth; actual audible audio is smooth on both. This supersedes old “audibility unverified” status, but is owner observation rather than fabricated automated audio evidence.
- **Android 3DS:** the portable Azahar/libretro Vulkan hardware path now boots legal homebrew with visible advancing frames, input, persisted layouts, and save states. The exercised homebrew did not emit qualifying confirmed audio samples, so Android 3DS remains hidden/unadvertised and is not accepted.
- **Linux:** authorized Debian built and smoke-ran native GBA/Vulkan and NDS desktop OpenGL fallback paths for both `.deb` and Flatpak with SDL audio configured. The DEB and Flatpak are published with no browser-only substitute.
- **Web:** current HTTP staging has no `navigator.gpu` in its insecure context, so requested WebGPU correctly falls back to WebGL2 at `requestAdapter`. The contract still requires `effective=webgpu` whenever adapter/device initialization succeeds.

| Artifact | Size | SHA-256 | Staging result |
| --- | ---: | --- | --- |
| macOS DMG | 42,282,073 | `762f1e8122c0b3455ed4a43509c001eb9a12adb252a398b5310c4ac9f8cb90f3` | HTTP parity PASS |
| Android APK | 87,703,074 | `128780ed3f21cbf2ac4b158fcd02fc60bd97e92c9b9ded90918f52ad7a3faa24` | HTTP parity PASS; APK v2 verified |
| Linux DEB | 1,812,216 | `7b8672db446a73c8dcf78220b77feb1501d9a0ae6958623fa74ba9319a3a7b49` | HTTP parity PASS |
| Linux Flatpak | 1,805,368 | `65f72ed64935cd958d1e977dcbbb3a2e3ecad5e29d8c6746be76c9916a525a50` | HTTP parity PASS |

All 119 explicit Python regression tests passed after the final package-contract correction. Release-catalog tests (30), package shell syntax, local installer sidecars, staging archive inspection, and staging HTTP parity also passed.

## Completed phases
P4 — artifact publication infrastructure, COMPLETE on 2026-09-09
P3 — deterministic web-facing features, COMPLETE on 2026-09-09
P1 — Runtime blockers, COMPLETE on 2026-09-09T09:29:59+07:00
P2 — NDS performance diagnosis, COMPLETE on 2026-09-09T15:07:11+07:00

## Current P5 completion — September 11
The exact Android staging APK `cd98c834d5730f532b6e68a373072231c2519780822db9c6c30ff65e00086ff6` was installed on the ARM64 AVD and accepted as a native GBA/NDS candidate. Native NDS ran visibly at 59–60 core/present FPS with Vulkan, then with explicit GLES3 after saving/relaunching, and Vulkan was restored. Portrait → landscape → portrait stayed upright without stretching. Side-by-Side and Top/Bottom were each saved/relaunched and accepted touch tap/drag/release without crash; no ROM-specific visible input effect was claimed. The nine-section horizontal menu, native pad/touch, draft Save Settings semantics, slots 1 and 10, independent timed Auto Save, `.state` export/import, and post-restart slot load were exercised. Android 3DS is explicitly unavailable in this build and is not advertised.

The AVD did not establish actual speaker audibility; AAudio counters/UI are not treated as proof. The platform status is therefore **PARTIAL**, not audio-PASS. The current macOS DMG was also rebuilt/relaunched from its exact bytes: GBA and NDS ran at 59–60 FPS via Vulkan → MoltenVK → Metal; the compact nine-section menu, slots, Auto Save controls and Escape draft discard were observed. A fresh macOS 3DS long-run and speaker audibility remain unaccepted.
Report: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/RELEASE_TRAIN_P5_NATIVE_MIGRATION_20260910.md
Latest handoff: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/RELEASE_TRAIN_HANDOFF_20260912.md

## Current blockers
Linux DEB and Flatpak are **BLOCKED** on the authorized Debian builder: the current-source Linux entrypoint exited 3 for both instead of making a browser-only package, because the shared portable desktop surface/audio/OpenGL adapter and package integration are not present. Debian packages for mGBA and DeSmuME libretro exist, but they are not a substitute for the missing native desktop host. Windows EXE is **BLOCKED** pending a real Windows Vulkan build/signing/runtime host; a deterministic PowerShell build path is present, but no `.exe` is claimed or published.

Historical P2 disposition:
No remaining P2 implementation blocker. At the user's direction, an Android 15 ARM64 AVD replaced the physical Redmi comparison. Its host-GPU run produced advancing core telemetry but black source/presentation output; WebGPU requestAdapter failed and fell back correctly to WebGL2. Its software-GPU run stalled at completed startup. Classification is INSUFFICIENT EVIDENCE for Redmi or visible Android gameplay, with a scoped virtual DEVICE/CPU/WASM signal only. No optimization was made. P2 report: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/RELEASE_TRAIN_P2_20260909.md

## Current staging
**PASS — staging only.** Asset `bef86865b122` was published at `/opt/an3-arcade-staging/releases/20260911-230833-bef86865b122` (rollback target `/opt/an3-arcade-staging/releases/20260909-195906-8ecb7b06ad8c`). The staging health endpoint, Release Center manifest, and HTTP downloads all agree with the local current artifacts: the macOS DMG is 42,976,820 bytes / `b63b3e61708c532c899b1a8e7283af5d200c648a9465deef1f3d54f1d5fb2870`; the Android APK is 74,229,651 bytes / `cd98c834d5730f532b6e68a373072231c2519780822db9c6c30ff65e00086ff6`. Linux and Windows entries correctly remain blocked with no download URL. The deploy path packages only source plus those two current verified installers, uses strict key-only SSH, and neither packages nor uploads a production archive/script. Production was not read, changed, restarted, or packaged.

## Current owner evidence
Owner-confirmed Redmi 15 5G Chrome NDS tap, drag and gameplay touch response PASS. Preserve separately from failed audit launches and unverified extended cases.

## Artifact inventory
macOS DMG: `native-offline/releases/vibecodedemulator-0.4.4-macos-aarch64.dmg`, arm64, 42,976,820 bytes, SHA-256 `b63b3e61708c532c899b1a8e7283af5d200c648a9465deef1f3d54f1d5fb2870`; ad-hoc staging signature verified, not notarized; **PARTIAL** because speaker audibility and fresh 3DS long-run are unaccepted.
Android APK: `native-offline/releases/vibecodedemulator-0.4.4-android-arm64-staging.apk`, universal ARM64-capable debug candidate, 74,229,651 bytes, SHA-256 `cd98c834d5730f532b6e68a373072231c2519780822db9c6c30ff65e00086ff6`; APK v2 verified with Android Debug staging certificate; **PARTIAL** because speaker audibility is unaccepted and Android 3DS is intentionally unavailable.
Linux DEB: **BLOCKED**; no artifact.
Linux Flatpak: **BLOCKED**; no artifact.
Windows EXE: **BLOCKED**; no artifact.

## Phase history
### 2026-09-09 — P4 — COMPLETE (immutable entry)
Added a staging-only machine-readable five-category artifact manifest and Release Center. SHA-256 and size are enforced on every publication/download decision. Current macOS DMG and evidenced Android APK are downloadable; DEB, Flatpak and EXE remain blocked without links. 94 Python/12 Node tests PASS; final staging 8ecb7b06ad8c and full download hash parity PASS. Service worker packages the Release Center assets and bypasses installers/source while fetching the manifest network-only. Production untouched. Next P5, Astra Medium.
Report: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/RELEASE_TRAIN_P4_20260909.md

### 2026-09-09 — P3 — COMPLETE (immutable entry)
Persisted renderer selection, truthful requested/effective/fallback UI, safe diagnostics and copying implemented. Fixed reproduced stale CSS cache mismatch with versioned player stylesheet. 93 Python and 12 Node tests PASS; final staging e9cca6502858 health/hash parity PASS. Desktop copy/visible output and AVD options layout verified; extended fullscreen/input matrix remains UNVERIFIED. Next P4, Sol Light. Production untouched.
Report: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/RELEASE_TRAIN_P3_20260909.md

### 2026-09-08T16:32:16+07:00 — P1 — BLOCKED (immutable entry)
Repairs, tests and staging publication completed; web gameplay acceptance still fails independently of presentation bridge, and Redmi is disconnected. Native Escape/Save mounted acceptance PASS; 93 Python tests and direct Node touch/renderer tests PASS. Secure staging effective WebGPU and explicit WebGL2 worker submission PASS; gameplay FAIL. Current asset 11290264c01d; DMG parity PASS. No next-phase work.
Authoritative report: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/RELEASE_TRAIN_P1_20260908.md
Evidence: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/staging/p1-20260908
Next assignment: remaining P1, Astra Medium. P2 remains gated.


### 2026-09-09T09:29:59+07:00 — P1 — COMPLETE (immutable entry)
Native Escape/Save mounted acceptance retained on unchanged artifact; WebGPU direct staging and controlled WebGL2 fallback interactive dialogue PASS. Browser audio activation and brief CUA input explain earlier failed audit.93 Python/8 Node tests PASS. No additional application source changes or deployment. Production untouched. Next P2, Sol Medium; no next-phase work performed.
Authoritative report: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/RELEASE_TRAIN_P1_20260909_COMPLETION.md

### 2026-09-09T14:45:14+07:00 — P2 — BLOCKED (immutable entry)
Passive source, presentation, capture, worker, UI pacing, long-task, dimension, DPR, and renderer telemetry is deployed to staging. Matched Mac New Game baselines show about 60 FPS in WebGPU and WebGL2 with zero dropped/replaced frames and sub-millisecond bitmap/worker costs. DEVICE_CONNECTED=no prevents the required Redmi comparison. No optimization was made because no affected-device BEFORE evidence exists. 93 Python/9 Node tests PASS; final asset af16e551490f; production untouched.
Authoritative report: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/RELEASE_TRAIN_P2_20260909.md

### 2026-09-09T15:07:11+07:00 — P2 — COMPLETE (immutable entry)
User authorized an Android Virtual Device in place of physical Redmi testing. Android15 ARM64 AVD, Chrome124, 4 virtual cores, 2.5GB RAM, landscape320x640 profile: host-GPU WebGL2 core measured about38.5 FPS while presentation stayed about60 FPS with sub-millisecond render costs, but both source and presentation were black and the required New Game scene could not be verified. Requested WebGPU failed at requestAdapter and correctly used WebGL2. SwiftShader stalled at completed startup. Classification: insufficient evidence for physical/visible gameplay; scoped virtual DEVICE/CPU/WASM limitation only. No performance change. P2 complete under the permitted insufficient-evidence classification; next P3, Astra Light. Production untouched.
Authoritative report: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/RELEASE_TRAIN_P2_20260909.md
