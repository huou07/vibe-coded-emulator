# P5 architecture correction — work in progress

Authoritative request: /Users/meomeo/.codex/attachments/48d16cff-3348-43f8-9203-d50948d32507/pasted-text.txt

P5 remains IN_PROGRESS. P6 has not started. Production is untouched; no P5 candidate has been published. Last observed staging asset remains 8ecb7b06ad8c (P4).

## Audit and migration

KEEP: Android Tauri/library bootstrap, private ROM document import/storage, staging labels, build-target fixes in build.rs and azahar.rs, APK build tooling and Android-only bundle exclusions. Preserve original macOS host/renderer as the regression reference.

SEPARATE COMPATIBILITY WORK: offline.js web renderer controls, android-staging.js EmulatorJS export and IndexedDB Auto Save belong solely to browser gameplay. Earlier AVD GBA/NDS visible frames, input and save tests exercised this browser path and do not satisfy native acceptance. These states must never be silently imported into native state slots.

REPLACE: default Android launch ownership with portable libretro host, SurfaceView/ANativeWindow, Vulkan preferred and native GLES3 fallback, native input and AAudio, native raw serialization. No automatic fallback to browser gameplay. 3DS remains explicitly unsupported until a compatible native hardware core/context is negotiated.

## Protected behavior / blast radius

Portable extraction affects software upload, device/surface lifetime, frame fences, direct core write, formats, and diagnostics; existing RG native renderer, no-readback, pacing, input, audio, layout, state and core-option ABI guards apply. Original AppKit/AVFoundation/MoltenVK files remain unchanged. The native-runtime tree is a staged Android-first extraction, not macOS acceptance by inheritance. Android library launcher changes affect ROM identity and supported-system dispatch. Browser renderer and touch implementation are preserved.

Baseline: 43 existing native Python guards passed on 2026-09-10 before integration. These are source guards, not proof of native runtime behavior.

## Current evidence

Portable Vulkan translation unit passed Android NDK syntax compilation before integration. Official Android AArch64 mGBA and melonDS DS cores have ABI/export/hash provenance manifests. Native runtime acceptance remains UNVERIFIED until actual APK presentation/input/audio/save tests.

Redmi update previously rejected because installed app signature differs. No uninstall or data wipe performed. AVD is authorized and available for initial runtime tests.

## Native implementation and current acceptance — September 11

This section supersedes the initial unverified compilation-only snapshot above. P5 remains IN_PROGRESS.

The Android APK now runs official pinned AArch64 mGBA and melonDS DS through the portable C++ libretro host, native SurfaceView, Vulkan or explicit GLES3, and AAudio. Original Mac host/renderer and browser player remain the references and were not rewritten. APK installs were updates on the authorized AVD, preserving ROM/state data. No physical device was connected during the latest check.

The owner requested the current DMG's in-game pad, controls, features and menu. Its reference is version 0.4.4, SHA-256 `37e24bf1d1d6c44ff3267c5649b16010f8bce076cc0bac632cddf17d431b975c`. Native Android now has Menu/Pad/Lock cursor, speed controls, directional pad, ABXY, L/R, Start/Select, and the same nine menu sections: General, Graphics, Audio, Keyboard, Controller, Emulation, Save States, Diagnostics and About. Native Android widgets adapt the geometry to the device. Ten state slots, separate Auto Save, raw import/export, audio volume/mute/latency/quality and core-announced options are implemented. Controller mapping remains read-only as in the reference. Android 3DS is not advertised.

Observed native AVD runtime:

- Pokemon Emerald: animated native Vulkan and explicit GLES3 presentation, title and New Game interaction, approximately 59 core/present FPS with zero renderer drops in observed samples.
- Metal Slug 7: animated native Vulkan and GLES3 title/menu; held Start advances to the menu, approximately 59 FPS in observed samples.
- Golden Sun Dark Dawn: imported through Android document picker, native Vulkan title and name-entry keyboard; direct native 120 ms touch visibly enters a letter. A long press also works. An instantaneous automation tap can be missed by the game despite the new one-core-frame input latch; this is not promoted to universal short-tap acceptance.
- Golden Sun raw quick slot 1: saved default name Matthew, edited name to a, loaded slot 1 and visibly restored Matthew. Screenshot `reports/staging/p5-native-20260910/golden-sun-native-slot1-restored.png`.
- Activity ownership bug reproduced and fixed: an older Activity's destroy callback could stop the new GBA-to-NDS session. JNI now checks its weak Activity owner. Subsequent switching visibly launched the new game.
- Overlay measurement fixed after fresh launch showed oversized control hitboxes. New APK displays correctly sized controls and Pad hides them.
- Fractional NDS audio rate 32728.498047 is accepted and resampled to negotiated AAudio rate. Focused bounded resampler tests compiled and executed on AVD successfully. Nonzero PCM delivery is observed in game samples, but actual speaker audibility is UNVERIFIED.

New fixes awaiting final runtime matrix: selected NDS layout is supplied before retro_load_game; completed short button taps are sampled for one core frame; pointer cancel suppresses pending taps; Escape cancels key capture first, then discards open menu drafts. Behavioral mock-core tests verify preload layout/default, short button/pointer input, release/cancel, state isolation, and continuation through presentation drops. A bounded 240-sample core frame-interval diagnostic was added; this reports pacing separately from renderer upload/present timing.

Remaining acceptance includes side-by-side touch and orientation, draft cancel runtime, state slot 10/Auto Save/import/export, audio audibility, matched backend performance with memory/CPU/thermal, and final candidate hash. Runtime observations from older candidates require appropriate final smoke, not automatic inheritance. No P5 deployment/publication or production access has occurred.

Current local candidate (September 11, before remaining runtime checks): `native-offline/src-tauri/gen/android/app/build/outputs/apk/universal/debug/app-universal-debug.apk`, 74,224,851 bytes, SHA-256 `55943f347ce9dd8abdbad19c45e00401c1a048e9e8a4f8bf10bfbc388ec76a1f`. APK signature v2 verifies. Embedded runtime bytes match the current generated JNI library and include the bounded frame-interval diagnostic. This is debug-signed STAGING, unpublished, not a production release.

Latest independent read-only checks: 102 Python tests PASS, web NDS touch PASS and 11 renderer behavior tests PASS (12 Node checks total). APK archive contains arm64-v8a Tauri/runtime/mGBA/melonDS libraries and bundled core notices/licenses. Source/packaging checks do not replace the remaining AVD runtime checks.

Additional state error-path review: Android cache-file creation is now caught and reported instead of escaping the document callback. Failed transient suspend serialization removes a previous snapshot so the next surface cannot silently restore an older position. Rejected imported temp copies may be deleted because the owner-selected source document is preserved. SAF export failure can leave a partial destination and is reported as failure; atomic replacement is not guaranteed by arbitrary document providers. These error-path fixes require a new candidate hash after rebuilding.

Fresh AVD restart/update succeeded after the environment restart. Escape draft cancellation is now observed: Start fullscreen was changed in the draft, Escape dismissed it, and reopening retained the saved checked value. Persisted library entries survive the update. A fresh Side by Side test exposed top-bottom rendering despite the saved left-right preference; therefore the prior preload-layout implementation was insufficient. The host now binds the selected layout before retro_init and answers GET_VARIABLE directly, following the protected Mac host path. A repeated live geometry/touch check is pending. The new candidate SHA-256 is `b7e5cec9c208146e90d3585527f774e7fb1b1bda3266a549cbca27da7a50457a`, 74,229,602 bytes; this supersedes the earlier local hash above.

After the final layout/state error-path changes, 11 focused Android tests and all 105 Python tests PASS. The fixture reads the layout during retro_init as well as retro_load_game, protecting the earlier snapshot timing that the first test missed. New candidate APK v2 signature verifies.

The repeated layout test now passes in the native APK: Golden Sun renders true left-right screens, Quick load 1 restores Matthew, and a 120 ms native touchscreen press enters a. Fullscreen hides system bars. Rotation exposed a separate Vulkan bug: the blit-only renderer claimed `currentTransform` pre-rotation while supplying unrotated pixels, producing sideways/stretched landscape. The portable renderer now requests supported identity transform and delegates rotation to composition; unsupported identity produces an explicit error. This has potential compositor cost and is not claimed as a pre-rotation optimization. Reference: https://docs.vulkan.org/samples/latest/samples/performance/surface_rotation/README.html . Original Mac renderer remains untouched. New rebuild and repeated rotation acceptance pending.

Rotation-fix candidate: 74,229,769 bytes, SHA-256 `0b81cae33cf48a83e8abb6045e51b735b0a92b7e38a558e2d317dcfdf461ccb6`. Independent review and new transform guard PASS; 12 focused Android tests and 106 total Python tests PASS. This candidate supersedes previous hashes for remaining runtime acceptance.

Native held-pointer drag is now covered by the compiled harness: coordinates change while pressed across successive core runs, then release retains the final coordinates. Focused 12-test Android suite PASS. The rotation-fix landscape screenshot now shows upright left/right Golden Sun screens with correct aspect-fit geometry; final touch after rotation and return-to-portrait check is underway.
