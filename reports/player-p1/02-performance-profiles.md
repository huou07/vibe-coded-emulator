# AN3 Arcade — P1.2 Conservative Performance Profiles

Date: 2026-08-20 (Asia/Ho_Chi_Minh)
Commit: `3bc01fe` (`feat(player): add conservative performance profiles`)
Staging release: `20260820-143947` at `http://192.168.1.11:8092`

## Delivered behavior

- Browser-local schema: `an3-player-performance-v1` with a version, a selected profile, and a narrowly scoped custom NDS renderer override. Malformed values safely fall back to automatic selection; storage failures do not break startup.
- Profiles: Low-end / Battery, Balanced, Quality, and Custom, plus Use recommended settings. Recommendation is derived in memory from conservative, local capability signals and never overwrites an explicit choice.
- Balanced is the default recommendation. Low-end is recommended only for clear combined low-memory/low-concurrency evidence or for an NDS browser without WebGL2. Quality does not silently enable shaders or quality reductions.
- The only profile effect is an NDS next-launch choice of the verified melonDS legacy compatibility core. mGBA stays on its established legacy default. There are no profile controls for canvas/DPR, frame skip, audio latency, or threads.
- Online and offline player markup carry the same profile controls. The service-worker cache was advanced to `an3-arcade-pwa-v21` so installed shells refresh the changed player assets.

## Staging result

| Check | Result |
| --- | --- |
| Staging health after release restart | PASS (`environment: staging`, asset version `a84638351a5b`) |
| Existing P0 menu-layer source marker preserved | PASS |
| `melonds-legacy-wasm.data` | PASS — HTTP 200, 1,193,773 bytes |
| NDS default / recommended startup (`pmd-eos`) | PASS — reached in-game state; Graphics Settings shows `WebGL2 (Requires restart)` enabled |
| NDS Low-end / Battery restart | PASS — reached in-game state; Graphics Settings has no WebGL2 control, confirming the legacy flavor |
| Use recommended reset and restart | PASS — returns to Balanced recommendation and native melonDS flavor |
| Browser console errors | PASS — none observed |

## Guardrails retained

- The selection is explicit, persisted only in the browser, reversible, and applied only after the player restarts.
- P0 canvas-only NDS gesture acquisition, menu priority/pad inertness, desktop keyboard focus, fullscreen shell, save-state controls, and touch-pad policy were carried forward from the current staging release.
- This staging deployment is not a production deployment or production approval. The remaining P1 phases require their own tests and staging validation.
