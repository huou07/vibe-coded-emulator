# Android 0.4.10 — 3DS Adreno Vulkan crash fixed with OpenGL ES

Status: COMPLETE. Staging and owner-authorized production serve asset
`add269259a01` and publish APK `0.4.10`.

## Owner report

3DS played but crashed after a while on the physical device. Acceptance: play
more than 4 minutes, then deploy production. The physical device was provided
for testing.

## Reproduction (physical Redmi `25057RN09G`, Android 16, Adreno 619)

The `space.an3tocom.offline:game` process aborted about 10 s into 3DS gameplay
(Pokémon X, 1.8 GB). Tombstone:

```
signal 6 (SIGABRT), fault addr --------
Abort message: 'terminating due to uncaught exception of type vk::UnknownError:
    vk::Device::createGraphicsPipelineUnique: ErrorUnknown'
  #06 ... libazahar_libretro_android.so (Vulkan::GraphicsPipeline::Build(bool)+3316)
```

`device uptime 10s`, `name: Pipeline worker`. Logcat also showed
`AHardwareBuffer: GraphicBuffer(w=4, h=4 ...) failed (Unknown error -2)` and
`AdrenoVK-0: Pipeline create failed`.

Azahar 2126.1.1 (the current pinned release) treats any non-success graphics
pipeline result as fatal (`UNREACHABLE_MSG`). The AVD (Apple-host GPU) and macOS
(MoltenVK) never reproduce it, which is why it was invisible locally.

## Fix

Android 3DS now defaults to the core's **OpenGL ES** renderer
(`citra_graphics_api=OpenGL`) because the Adreno Vulkan driver returns an
out-of-spec result from the core's pipeline creation. Implementation:

- `NativeCoreHost::initialize` takes the graphics API and reports it to the core.
- `SET_HW_RENDER` accepts `RETRO_HW_CONTEXT_OPENGLES3` and installs the frontend
  callbacks the core needs; `gl_current_framebuffer` returns a color FBO the
  core renders its layout into, and `get_proc_address` resolves GL entries
  through `eglGetProcAddress`.
- `AndroidGles3Backend` creates the FBO (with aspect-fit letterboxing blit to
  the window) and presents the core's frame on the worker thread.
- `jni_runtime` selects the OpenGL ES backend for 3DS unless the user explicitly
  chose `Vulkan`. GBA/NDS and macOS/Windows/Linux are unchanged.

## Artifact

| Platform | File | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Android arm64 | `vibecodedemulator-0.4.10-android-arm64-staging.apk` | 48,091,373 | `7cff442f13c74e9e987efcca1baf8d5bd933c5153b37762b29f43bf9a8422506` |

`versionName 0.4.10` / `versionCode 4010`, v2 signature with the shared Android
Debug certificate `b48f3cdecc39349a75b66817aaad645a861d538be34835f290a2aa570c3beb4b`
(drop-in update). Other four installers unchanged at 0.4.5.
`tools/verify-release-catalog.py` -> `RELEASE_CATALOG=PASS (5 installers)`.

## Verification

- **Physical device (the acceptance test):** 3DS rendered both screens correctly
  at 52–57 FPS; **337 s (5.6 minutes)** of gameplay with button/analog input, with
  zero `SIGABRT` / `SIGSEGV` / `vk::` entries and RSS stabilizing ~800–930 MB.
  Before the fix the same device aborted in ~10 s.
- Canonical `tools/release-train.sh --staging verify all`: 131 Python tests, web
  NDS touch, 11 renderer cases, `npm run check`, `git diff --check` -> PASS.
- Production HTTPS: APK 200 at exact size 48,091,373 and full-download SHA-256
  `7cff442f13c7…`; old 0.4.9 URL 404; all five installers exact-size `no-store`.

## Deployment

- Staging `STAGING_RELEASE=PASS`, asset `add269259a01`, release
  `/opt/an3-arcade-staging/releases/20260915-215308-add269259a01`, rollback
  `/opt/an3-arcade-staging/releases/20260915-204949-add269259a01`.
- Production `PRODUCTION_RELEASE=PASS`, asset `add269259a01`, release
  `production-827e2af4bb60ed30`, app backup
  `/opt/an3-arcade-backups/20260915-215421`, SQLite backup
  `/srv/an3-arcade/backups/arcade-predeploy-20260915-215421.db` (integrity PASS).

## Notes

- On this device the OpenGL ES renderer is stable; Vulkan can still be forced in
  the Renderer setting. If OpenGL ES ever fails to initialize, the app falls back
  to Vulkan automatically.
- The previous per-boot `:game` process that died on the 2 GB AVD under memory
  pressure is separately covered by RG-080 (bounded surface stop + Auto Save).
