# AN3 Arcade — P1.1 Performance Capability Audit

Date: 2026-08-20 (Asia/Ho_Chi_Minh)
Scope: the deployed EmulatorJS runtime used by both staging and production. This audit intentionally distinguishes verified behavior from ideas that must **not** become controls.

## Evidence source

- Runtime: EmulatorJS 4.2.3, verified read-only on staging and production. The deployed loader, runtime JavaScript, and CSS hashes match the workspace snapshot under `work/ui-baseline-data/emulatorjs-cache/stable/`.
- Loader mapping: `work/ui-baseline-data/emulatorjs-cache/stable/loader.js` lines 81–125.
- Runtime symbols: `work/ui-baseline-data/emulatorjs-cache/stable/emulator.min.js` (`EmulatorJS.downloadGameCore`, `handleSpecialOptions`, and `EJS_GameManager`).
- AN3 bootstrap: `static/player.js` lines 75–124 and 497–547; player shell CSS at `static/site.css` lines 1515–1523.
- Core reports: `cores/reports/mgba.json` and `cores/reports/melonds.json`.

## Current core behavior

| Core | Reported options | Current renderer behavior | P1 conclusion |
| --- | --- | --- | --- |
| mGBA | `{}` | Uses the `mgba-legacy-wasm.data` flavor by default. | No WebGL2 or threading profile override is warranted. |
| melonDS | `defaultWebGL2: true`, `supportsMouse: true` | Uses the WebGL2 core flavor when the browser supports WebGL2; otherwise EmulatorJS chooses its legacy flavor. | Low-end/Battery deliberately selects the legacy compatibility flavor on the next launch; Balanced and Quality retain the verified native default. Both flavors now have a successful staging startup record. |

## Verified candidates

| Setting / signal | Supported | Source / symbol | Current default | Performance and visual impact | Runtime safe? | Reload required? | Per-core? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| WebGL2 core flavor | Yes | `EJS_forceLegacyCores` mapped by `loader.js`; `supportsWebgl2` / `webgl2Enabled` in `EmulatorJS.downloadGameCore()` | mGBA legacy; melonDS WebGL2 where available | Chooses a core/driver path, not a resolution scale. Legacy can reduce compatibility risk but may also reduce features. | No | Yes; core binary may download | Yes |
| Native `webgl2Enabled` option | Yes | EmulatorJS graphics settings and `preGetSetting("webgl2Enabled")` | Report-driven where no native setting persists | Same as above | No | Yes; native UI explicitly labels it “Requires restart” | Yes |
| Threads | Yes, but not for this P1 scope | `EJS_threads` in loader/runtime | AN3 enables only PSP/3DS; mGBA and melonDS are false | Can change binary/runtime behavior | No | Yes | Yes |
| Shader registry / runtime toggle | Runtime supports it; not admitted to P1 profile effects | `EJS_SHADERS`, `enableShader()`, `gameManager.toggleShader()` | No AN3-selected shader | Potentially material visual and GPU cost; core compatibility has not been validated | Technically yes after start | No for toggle, but not P1-safe without core validation | Yes |
| VSync | Yes | `gameManager.setVSync(bool)` / native `vsync` setting | Enabled in the generated RetroArch configuration | Frame-pacing / tearing tradeoff; device dependent | Yes | No | Yes |
| Emulated frame count | Yes | `gameManager.getFrameNum()` | Not displayed | Counts emulated frames, not guaranteed presented FPS | Read-only | No | Yes |
| Core video dimensions | Yes | `gameManager.getVideoDimensions()` | Not displayed | Diagnostic only | Read-only | No | Yes |
| WebGL / WebGL2 availability | Yes | Standard canvas contexts | Not stored or sent | Capability signal only | Read-only | No | Browser/device |
| `hardwareConcurrency`, `deviceMemory`, DPR, viewport/screen size | Conditionally | Standard browser APIs | Not stored or sent | Weak, multi-signal recommendation inputs only | Read-only | No | Browser/device |

## Explicit non-candidates

| Candidate | Finding | P1 action |
| --- | --- | --- |
| Frame skip | No `frameskip`, `frame_skip`, or equivalent EmulatorJS option exists in the verified loader/runtime or the two core reports. | Do not expose or emulate a frameskip control. |
| Render / resolution scale / DPR setting | No verified key exists. EmulatorJS CSS sizes the canvas to its parent; backing size is browser/core-owned. At 1280×720, AN3 gives the game 1280×606 CSS pixels; DPR 2 produced 2560×1212 backing pixels in the P0 measurement. | Never mutate canvas dimensions/DPR: it risks NDS touch mapping and is not a supported tuning surface. |
| Audio latency | The runtime hard-codes `audio_latency = 64` in its generated RetroArch configuration; no supported `EJS_audioLatency` control was found. | Do not expose latency tuning. |
| GPU renderer string | Available only through fingerprint-sensitive extensions and not necessary for the recommendation. | Do not query or transmit it. |
| Existing `EJS_fixedSaveInterval`, `EJS_browserMode`, `EJS_mouseLock` assignments | The deployed loader/runtime has no references to these names. They are not usable performance controls. | Preserve existing P0 behavior; do not build new behavior around these no-ops. |

## Local capability probe and diagnostics design

The P1 probe is browser-local and intentionally conservative:

1. Read only `hardwareConcurrency`, optional `deviceMemory`, DPR, viewport/screen dimensions, WebGL/WebGL2 booleans, and `SharedArrayBuffer`/cross-origin-isolation availability.
2. Recommend **Low-end / Battery** only for clear combined low-end evidence (for example, both low reported memory and low concurrency) or an NDS browser without WebGL2. Otherwise recommend **Balanced**.
3. Never auto-recommend Quality: no short benchmark or single hardware value is strong enough evidence.
4. Keep `recommendedProfile` separate from a persisted `selectedProfile`; an explicit selection is never overwritten at page load.
5. Expose a short, staging/development-only diagnostic window after startup: canvas CSS/backing dimensions, selected profile, core flavor, WebGL availability, wall-clock samples of `getFrameNum()`, and `requestAnimationFrame` stability. It is not continuous polling, does not include a GPU renderer string, and is never sent to the server.

## P1.2 profile contract

| Profile | Verified effect | User-facing contract |
| --- | --- | --- |
| Low-end / Battery | For melonDS only, select the verified legacy compatibility core flavor for the next player launch. No shader or resolution reduction. mGBA remains on its existing legacy default. | Lower-risk renderer path; reversible with Balanced or Use recommended settings. |
| Balanced | Preserve the report-driven native renderer default and no AN3-selected shader. | Recommended normal experience. |
| Quality | Preserve the native renderer default and no unvalidated shader. | Intentionally does not enable an expensive effect merely because the profile is named Quality. |
| Custom | Let the player deliberately choose only the verified NDS renderer compatibility override. | Explicit and resettable; no obscure core options. |

P1 must document that renderer selection applies on the next player launch. Native EmulatorJS settings remain available through its own menu; AN3 will not duplicate unknown core options.

## P1.2 staging confirmation

The first profile candidate was staged on 2026-08-20 without modifying production. The staging server returned `200` for `melonds-legacy-wasm.data` (1,193,773 bytes), and the NDS game `pmd-eos` reached the in-game state with the Low-end / Battery profile selected. Its EmulatorJS Graphics Settings omitted the `WebGL2 (Requires restart)` control, while the same game restarted with Use recommended settings reached the in-game state and showed that control enabled. This verifies that the profile selects a real alternative core flavor rather than a no-op setting.
