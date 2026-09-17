# Nintendo Switch / Eden integration — completion handoff (2026-09-17)

Worker: Switch domain owner. Branch `agent/switch`. Staging was **not** deployed
and no production artifact was published; the integrator owns that gate.

## Scope delivered

A user can, on macOS, install AN3, import a legal Switch `.nro`, see a Nintendo
Switch library entry, launch the separate-process companion from the app, play
with keyboard input, focus/stop it, and relaunch — with the companion bundled in
the app and no development-machine paths.

## Commits (base `342b0f6`)

| SHA | Milestone |
| --- | --- |
| `c5784ac` | RG-115 hosted CAMetalLayer (sustained render) |
| `5c15dad` | harness `--seconds` sustained mode |
| `856c057` | RG-116 real Eden input + read-back diagnostics |
| `6279310` | RG-117 save-dir query + export |
| `e2c3f60` | `an3ctl switch` + runtime guards |
| `88133c7` | RG-118 separate-process companion |
| `cd8bfd4` | docs + `an3ctl switch companion` |
| `daa20c8` | Tauri CompanionSystem + 2.3.0 |
| `f4444c1` | checkpoint |
| `c232c3e` | app-drivable IPC, focus, audio diagnostics |
| `5a19e16` | self-contained companion bundled into the macOS app |
| `094ab57` | `.nro` library integration + in-app launch + lifecycle E2E |
| `d084196` | `an3ctl switch e2e` |
| `810ee41` | RG-111 contained (Vulkan pre-flight, RG-119) |
| `665bf1a` | packaged/saves/lifecycle tests |
| `88ee484` | regenerated Android web assets |

## Packaging evidence

Built `VibeCodedEmulator.app` (2.3.0, ad-hoc signed, `codesign --verify --deep`
OK). `Contents/Resources/switch/macos-arm64/` contains
`an3_switch_companion` (+x), `lib/` (25 dylibs), `manifest.json` (Eden pin
`7bf95be2…`, SHA-256, library list) and `EDEN-GPL-3.0-or-later.txt`. Install
names are rewritten to `@loader_path` — `otool -L` shows **0** `/opt/homebrew`
or `/usr/local` references across the companion and every bundled dylib. The
frontend embedded in the binary contains the Switch library/UI wiring. The
bundled companion was executed from inside the installed bundle with the bundled
MoltenVK and answered status/input/audio. (RG-118, `tests/test_switch_packaged.py`.)

## Library / UI

`native_system_from_extension` maps `.nro` → `switch` (plus `NRO0` header magic);
the importer accepts `.nro`; the library renders a Nintendo Switch section; the
bootstrap routes Switch launches to `switch_companion_launch_rom` (never the
libretro host) and detects availability at runtime before advertising it; the
card exposes Focus and Stop. Only `.nro` is exposed as runnable.

## Verification

- Python suite **313 tests OK** (`python3 -m unittest discover -s tests`).
- `cargo test --lib` **8 switch tests pass**; ignored app-level E2E passes
  (launch → sustained frames → button/analog/focus/audio → stop → relaunch, new
  pid); ignored installed-layout resolution passes against the real bundle.
- `an3ctl switch e2e --rom hbmenu.nro` → 20/20 steps pass in ~7 s.
- Node behaviour suites (`web_nds_touch_behavior`, `web_renderer_behavior`,
  `native_android_library`) pass; `npm --prefix native-offline run check` OK.

## Audio

Eden owns audio (`cubeb` sink). `an3_eden_get_audio_info` reports the configured
engine, output device, channel count and volume; the companion emits
`AN3CTL_AUDIO`. Sink initialisation and a non-null device (2 channels, volume
1.0) are verified; **audible output is UNVERIFIED** (no capture path here and
nx-hbmenu is not a reliable audio fixture).

## Saves

Service-level persistence verified with an isolated `HOME` (RG-120): the store
is created, survives a clean restart and a SIGKILL, and the owner's real save
store is never touched. **Game-level save round-trip is UNVERIFIED** (nx-hbmenu
writes no game save). Save states are not advertised.

## RG-111

**CONTAINED.** The reachable `ErrorVideoCore` cause (missing Vulkan runtime) is
now pre-flighted and returns a structured `AN3_EDEN_ERR_UNAVAILABLE` instead of
aborting (was exit 134, now exit 0). The upstream `noexcept` destructor defect
remains for other `ErrorVideoCore` causes; the companion runs in its own process,
so AN3 survives and reports the error. Not claimed as a fix.

## Platform matrix

| Platform | Build | Launch | Switch runtime |
| --- | --- | --- | --- |
| macOS | VERIFIED (2.3.0 .app) | VERIFIED | VERIFIED (hosted render, input read-back, saves, lifecycle) |
| Linux | not built here | — | UNAVAILABLE (no Eden build; Dell lacks cmake/ninja) |
| Windows | not built here | — | UNAVAILABLE (no Eden build; VM has no Vulkan ICD) |
| Android | unaffected | — | NOT SUPPORTED (companion is macOS-only; `.nro` lists but does not launch) |

## Integration handoff

Branch `agent/switch` @ `88ee484` is ready for the integrator (cherry-pick /
merge, cross-platform regression, artifact build, staging deploy, staging
verification). The integration branch `integration/20260917-1326` does **not**
contain these commits (verified with `git merge-base --is-ancestor`). No staging
deployment was performed from this worker.

## Known limitations

- In-app UI click-through inside the packaged WKWebView was not automatable with
  the available tooling; the same commands the UI calls are covered by the
  app-level E2E and the library source contracts.
- Physical gamepad and real keyboard interaction are UNVERIFIED (no device).
- macOS app is ad-hoc signed, not notarized.
