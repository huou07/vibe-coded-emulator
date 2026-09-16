# AN3 Arcade session rules

## CodeGraph is the mandatory first step

This repo has a `.codegraph/` index. Before any grep/glob/read of source, run
`codegraph_explore` (MCP) or `codegraph explore "<symbols/question>"` (shell)
and read only the files it narrows down. Re-check with CodeGraph before every
edit to get callers/callees/blast radius. Skip it only if the area is genuinely
outside the index (config/CSS/HTML strings, non-code assets) and say why.

## App versioning rule (owner-mandated)

Every change to a packaged app must bump that app's version, and the bump size
follows the change type:

- Bug fix → bump the patch: `X.X.X+1` (e.g. `0.4.7` → `0.4.8`).
- New feature or small update → bump the minor: `X.X+1.X` (e.g. `0.4.8` → `0.5.0`).
- Refactor or big update → bump the major: `X+1.X.X` (e.g. `0.5.0` → `1.0.0`).

Apply it to the version fields the app actually uses (Android
`tauri.android.conf.json` `version`, desktop `tauri.conf.json`/`package.json`
when those artifacts are rebuilt), the artifact filename, the release catalog,
and the sidecar. Never republish changed bytes under an already-published
version + filename.

- This is the new development workspace for the 2026-08-11 session.
- Treat `/Users/meomeo/Documents/Codex/2026-08-08/v/outputs/an3-arcade` as read-only legacy reference.
- Preserve the handoff invariants: client-side emulation, melonDS with auto-start, NDS touch bridge, EmulatorJS IndexedDB core contract, report-first core selection, persistent core cache, NDS ZIP delivery, and offline browser-local data.
- Never expose secrets or production data. Do not mix staging and production paths.
- Runtime changes require local baseline/tests and staging verification before any production consideration. Production deployment requires explicit approval.
- P2 UI work follows `docs/design-system.md` and `docs/ui-page-contract.md`; keep generic consumer/admin styling scoped away from the protected player surface. Any player input, canvas, overlay, or virtual-pad geometry change is a separate task.
- Read the latest comprehensive handoff and P2/P3 acceptance handoffs before production work. Write new handoffs and report references with their full absolute paths.
- Work staging-first. Run the Android regression harness before player/mobile releases; do not root devices or record device serials/private data.
- All new non-player pages must use the shared AN3 design system. Read `docs/player-layering.md` before any player-shell change and preserve player interaction invariants.
- Preserve intentional dirty work; never destructive-clean it. Never expose secrets. Production deploys require explicit user approval and must never be automatic.
- Staging SSH must use `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/tools/ssh/README.md`: owner-installed verified key/agent auth only, password auth disabled, and strict host-key checking. Never create an SSH password helper.

## Regression Safety

- Read `reports/handoff/SYSTEM_INSPECTION_HANDOFF.md` and `docs/REGRESSION_GUARDS.md` before shared emulator-host work.
- Before modifying shared host code, identify every protected behavior that file can affect; run its baseline tests before and the same tests after the edit.
- Never broad-revert a shared subsystem to fix one bug. User-reported packaged-runtime regressions override earlier PASS claims.
- Do not declare UX, audio, or input fixed from compilation, accessibility state, telemetry, or source review alone; verify the packaged app at runtime.
- Add every newly fixed regression to `docs/REGRESSION_GUARDS.md` with its validation before finishing the task.

## Regression ledger workflow

- Before editing a file or symbol, search `docs/REGRESSION_GUARDS.md` and the handoff index for every guard that names it or its subsystem; record that blast radius in the work notes.
- Before and after each shared emulator, renderer, input, audio, save, settings, or player-layer edit, run every matching guard, including its behavioral and live requirement.
- Static/source checks and a truthful status label are not interactive acceptance. If a browser or packaged runtime was not exercised, record `UNVERIFIED` rather than `GOOD`.
- Web NDS touch must resolve the EmulatorJS source canvas; presentation canvases are output-only and must remain pointer-inert. Validate Top/Bottom, Left/Right, scaled/letterboxed, pointer capture, release/cancel, menu precedence, and keyboard passthrough.
- Any edit to `static/player.js`, `static/nds-touch.js`, `static/site.css`, or `static/renderer-worker.js` that affects player canvas/input/layers must run the Web NDS gameplay-touch, menu-precedence, Settings-clickability, virtual-pad-precedence, presentation/source-ownership, pointer-release/cancel, and fullscreen/resize tests before and after the edit.
- For staging verification, record the asset version, active release, browser/runtime, ROM identity, visible-frame result, input result, and console/runtime errors. Do not access production while performing this audit.

## Public release security gate (mandatory)

Before any push, release, or publication to a public GitHub repository, run the
public-release-security workflow (`tools/publication-check.sh`, policy in
`.opencode/skills/public-release-security/SKILL.md`). Do not publish if secret
scanning, personal-data checks, licence checks, or relevant source-history
checks are incomplete or failing. Never bypass the security gate without
explicit user approval of the specific finding — and approval does not make an
exposed active credential safe: rotate or revoke it first.

Publishing rules for this repo:

- The public repository is only the product source. Never publish `.opencode/`,
  `.codex/`, `AGENTS.md`, `reports/`, `work/`, handoff/status documents,
  staging/production operational docs, SSH material, real environment files,
  ROMs, saves, firmware or keys.
- The development history contains personal paths and private infrastructure
  details. Do not push this history to a public remote; export a clean snapshot
  and add a truthful provenance note instead.
- All source comments, documentation and public-facing text must be in English.

## Never publish automatically

Do **not** push to GitHub (or any public remote) on your own initiative. Publish
only when the user explicitly asks for it in the current request. When asked,
run `tools/build-public-snapshot.sh` then `tools/publication-check.sh`, and only
then `tools/publish-github.sh --confirm` (a single fresh public commit — never
the development history).
