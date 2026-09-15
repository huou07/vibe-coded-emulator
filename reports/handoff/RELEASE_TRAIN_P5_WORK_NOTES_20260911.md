# P5 release-train work notes — 2026-09-11

## Recovery baseline

- Current state and the latest P5 handoff were read before implementation.
- Intentional dirty-tree work is preserved. No reset, checkout, clean, production command, or production endpoint has been used.
- Baseline passed: 106 Python tests, focused Android/native renderer/state/input/staging guards (55 tests), both Node behavior suites, native script syntax checks, and `git diff --check`.

## Portable-host seam: planned blast radius

The first shared-code change extracts platform-neutral renderer contract types from the macOS presenter header. It must not alter macOS presentation behavior or Android runtime behavior.

- RG-057: Android GBA/NDS remains portable libretro + SurfaceView/ANativeWindow, native Vulkan then GLES3, with no browser fallback.
- RG-058: raw slots 1–10, separate Auto Save, and state import/export remain isolated from browser state.
- RG-060: Vulkan/GLES reusable-resource, bounded-frame, no-readback/no-wait-idle/no-`glFinish` hot-path contract remains unchanged.
- RG-062: selected NDS layout remains available before core initialization.
- Shared renderer guards RG-001, RG-031, and RG-040 remain applicable to native presentation paths.

Required post-change validation: focused Android/native guard suite, full Python suite, Node behavior suites, platform syntax/compile checks, and native packaged/runtime acceptance appropriate to the changed platform.

## September 12 continuation: portable 3DS, layouts, controls, and Linux seam

The current source, current state, latest handoff, P5 migration report, and
regression ledger were read before this continuation. The tree remains
intentionally dirty; no reset, clean, checkout, production access, or
production packaging is authorized.

The shared host is being extended from its explicit software-only Android
boundary to accept a libretro Vulkan hardware-render contract for Azahar. This
touches `native-runtime/core/libretro_host.*`, the portable Vulkan presenter,
and Android's thin adapter. The required invariant is direct Vulkan image plus
core-supplied synchronization to the Android `VkSurfaceKHR` swapchain; there is
no normal GPU-to-CPU readback or CPU/GPU re-upload. Relevant guards are
RG-057, RG-058, RG-060, RG-061, RG-062, RG-064, RG-065, RG-066, RG-040 and
the native renderer/input contract suites. The macOS host remains the reference
and is not to be copied into portable code.

The Android overlay/import work touches screen-layout persistence/touch
geometry, native input, safely bounded document import, and user-visible menu
draft semantics. Relevant guards are RG-002, RG-026, RG-057, RG-058, RG-061,
RG-062, RG-063, RG-064, RG-065 and the explicit source/presentation ownership
requirements. Layout selection must be drawn from one shared schema; `Next
Layout` cannot maintain a second list. Virtual control changes preview locally
and remain draft-only until Save Settings; the direct Next Layout action is
persisted because it immediately changes active gameplay geometry.

The Linux work will add adapters/package integration only after the shared host
contracts compile locally. The authorized Debian evidence is a key-only,
strict-host-checking preflight (Debian 13, graphics/audio runtime present but no
native build checkout or development packages); its old build gate exited 3
without fabricating browser-only packages. Linux artifacts may be published
only after native GBA/NDS runtime and package validation.

The staging WebGPU reproduction was deliberately read-only: direct HTTP was
not secure or cross-origin isolated, `navigator.gpu` was unavailable and
`requestAdapter` failed, so requested `webgpu` truthfully fell back to
`webgl2`. This is not an effective-WebGPU regression on a capable, secure
context and does not justify weakening staging security headers.

## macOS menu refinement: planned blast radius

The menu work is restricted to AppKit presentation and grouping. It must retain all nine sections and every control/action.

- RG-010, RG-025, RG-028, and RG-051: first Escape dismisses/discards an open draft; explicit Save remains the persistence boundary; key-capture and return-to-library precedence remain unchanged.
- RG-008, RG-009, RG-011, and RG-029: all ten numbered slots, separate Auto Save, and raw state import/export remain visible and independent.
- RG-013 and RG-027: constrained volume geometry remains valid at narrow and wide panel widths.
- Shared-host blast radius: any AppKit menu edit requires a fresh packaged GBA/NDS/3DS launch smoke; this task will not inherit older runtime claims.
