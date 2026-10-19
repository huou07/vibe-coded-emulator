# Eden (Nintendo Switch) direct integration — feasibility and blocker

Status: **audited; direct integration NOT completed.** Pinned commit recorded.
The blocker is technical, not licensing.

## Upstream facts (verified 2026-09-16)

- Authoritative repository: `https://git.eden-emu.dev/eden-emu/eden` (Gitea),
  default branch `master`.
- **Pinned commit for any integration:** `7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c`
  (2026-09-16). Do not integrate a moving branch.
- License: **GPL-3.0-or-later** (`LICENSE.txt`, README: "GPLv3 (or any later
  version)"). Files carry per-file SPDX tags; `src/core` files are dual-tagged
  `GPL-3.0-or-later` (Eden) and `GPL-2.0-or-later` (yuzu-derived). The `LICENSES/`
  directory holds Apache-2.0, BSD, MIT, MPL-2.0, LGPL-3.0-or-later, Unlicense,
  Zlib, CC0, BSL-1.0 and others — all compatible with a GPLv3 combined work.
- Layout: `src/core` (emulation), `src/video_core`, `src/audio_core`,
  `src/hid_core`, `src/input_common`, `src/network`, `src/shader_recompiler`,
  `src/dynarmic`, `src/frontend_common`, and the frontends `src/yuzu` (Qt6),
  `src/yuzu_cmd`, `src/yuzu_room_standalone`, `src/android`.

## Embeddability assessment

See `docs/vibe-coded-switch-companion.md` for the earlier design note. The
audit refines it:

1. **`core` is a CMake static library**, not an application:
   `add_library(core STATIC …)` in `src/core/CMakeLists.txt`, linked as
   `target_link_libraries(core PUBLIC common PRIVATE audio_core hid_core network
   video_core nx_tzdb tz)`.
2. **There is no C ABI / FFI layer.** `src/ffi`, `src/c_api`, and `src/libretro`
   do not exist in the tree. Eden's API is C++ (`Core::System`, loaders,
   `VideoCore`, `AudioCore`, `InputCommon`), with no stable ABI and no versioned
   interface guarantee.
3. **The frontends are Qt6 applications.** Qt6 is required for the GUI frontend;
   `frontend_common` provides config/settings/content management used by them.
4. **Heavy dependency graph**: Boost, SDL2, fmt, enet, httplib, nlohmann/json,
   OpenSSL, zlib/zstd/lz4, opus, FFmpeg, Vulkan, dynarmic and more, resolved via
   CPM/externals at configure time.
5. **Keys/firmware**: encrypted commercial content needs the user's `prod.keys`
   and firmware. Unencrypted homebrew NROs can run without them, which is why
   Phase-1 evidence must use a legal homebrew NRO.

## The concrete blocker

Direct integration is **technically feasible but requires substantial new
first-party code and a large native build**, and none of the Step A–G acceptance
can be verified in this environment:

- **No embeddable interface exists.** Integrating directly means writing and
  maintaining a C++/C capability layer over `core` (+ `video_core`, `audio_core`,
  `hid_core`, `input_common`) and a Vulkan presentation bridge into AN3's render
  path. That is a multi-week effort on its own, upstream-coupled, and must be
  re-validated on every Eden change. Per the owner's instruction, a
  companion-process substitute is **not** to be silently substituted for this.
- **Build scale**: configuring/building Eden pulls a large external dependency
  set and takes far longer than a session; it also needs a Vulkan-capable host
  to validate rendering.
- **No legal Switch test content in this environment**, so Step B (game launch),
  Step C (rendering), Step D (input), Step E (audio) and Step F (save) could not
  be exercised even if the build existed. Claiming them from compilation would be
  false.

## Licensing outcome (not a blocker)

Linking Eden into a GPL-3.0-or-later Vibe Coded Emulator is compatible:
Eden is GPL-3.0-or-later, its yuzu-derived files are GPL-2.0-or-later
(compatible with v3 via "or later"), and the remaining `LICENSES/` components are
GPLv3-compatible. The combined work would be GPL-3.0-or-later, its corresponding
source must include Eden's source at the pinned commit plus any shim we write,
and Eden's notices must be preserved. No new permission from Eden is required.

## Recommended incremental path (when resumed)

1. Add `native-offline/native-runtime/companion/switch_core.h` — an AN3-owned
   C++ interface (`initialize`, `load_nro`, `run_frame`, `render_target`,
   `push_input`, `save`, `shutdown`) with no `NativeSystem` coupling.
2. Build Eden's `core` + deps for one platform only, as an out-of-tree CMake
   add_subdirectory pinned at `7bf95be2…`, behind an off-by-default CMake option.
3. Implement `switch_core.cpp` against `Core::System` and a Vulkan surface the
   AN3 host provides; keep it a separate static library so the existing
   GBA/NDS/3DS libretro path is untouched.
4. Verify Step A → G on a legal homebrew NRO before any UI integration.
5. Only then add Switch to the library/UI and bump versions.

Until 1–4 are done and verified, **Switch remains unintegrated** and no Switch
claim should be made.
