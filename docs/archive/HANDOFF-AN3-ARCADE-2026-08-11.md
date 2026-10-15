> Status: archival. Retired workstation/session snapshot; historical paths and
> operational authority are not current. Original body retained below. Use the
> current repository guide and documentation index for new work.

# AN3 Arcade handoff — 2026-08-11

## Workspace and provenance

- New workspace: `/Users/meomeo/Documents/Codex/2026-08-11/an3-arcade`
- Legacy reference (read-only): `/Users/meomeo/Documents/Codex/2026-08-08/v/outputs/an3-arcade`
- Legacy Git metadata: unavailable; source was copied from the legacy working tree.
- Source baseline commit: `d389e226542436a470a051e37d82da46695fcebd`
- NDS recovery baseline: `ed0a32d50944f32bda9052bc6e41be3173d7f2c4`
- NDS touch code deployed: `15697a634360e3d9ae66bf4b5176333ce53ba5a3`
- Last staging release candidate: `15697a634360e3d9ae66bf4b5176333ce53ba5a3`
- Live staging and production asset: `def955887c68` (health PASS).
- Default touch variant: `geometry-mapped`; `hybrid-root` remains query-selectable for rollback diagnostics.

## Current architecture

Single-host Python standard-library HTTP app with SQLite WAL and static PWA assets. ROMs, covers, screenshots, and database remain server-side; EmulatorJS/WASM, canvas, saves, and game emulation run client-side. Staging and production use separate service/config/data paths.

## Changes in this session

- Imported the legacy working tree into a new workspace without modifying legacy.
- Added session memory, bootstrap/audit/production-readiness reports, repository safety rules, and this handoff.
- Removed DeSmuME fallback candidates from offline core selection; NDS offline selection is melonDS-only.
- Updated README to document melonDS auto-start, NDS touch bridge, EmulatorJS IndexedDB core storage, report-first selection, NDS ZIP delivery, and PWA limitations.
- Added explicit regression tests for melonDS startup/touch, IndexedDB core contract, report-first selection, persistent cache, and NDS ZIP/Range behavior.
- Recorded a no-source-change Phase A baseline and corrected two stale integration expectations.
- Added fail-closed staging/development-only NDS touch observability.
- Added the query-only `geometry-only` candidate, which preserves `hybrid-root`
  event semantics and restores the relative MouseEvent delta polled by melonDS.
- Recorded C01 as PARTIAL after measured viewport scales proved raw CSS deltas
  cannot keep the core cursor aligned with the finger across display modes.
- Added the second and final P1 candidate, `geometry-mapped`, which maps the live
  rendered core viewport to integer 256x192 DS cursor targets. It rejects stale
  out-of-bounds WebGL viewport values after rotation.

## Verified evidence

- Explicit full suite: 6/6 tests PASS.
- JavaScript syntax, shell syntax, and Python compilation PASS (compile uses a writable cache prefix because the default environment cache path is restricted).
- Local SQLite Online Backup API rehearsal: integrity check `ok`, WAL mode retained.
- Release package excludes local `data/`, `work/`, tests, reports, and `.codex/`.
- Staging deployment completed for the final NDS touch code candidate; live asset `def955887c68`.
- Staging browser smoke: GBA and NDS reached `Sẵn sàng`; NDS canvas had `pointer-events:auto`, `touch-action:none`, and `data-an3-nds-touch=1`; no browser warning/error logs.
- Staging NDS delivery: ZIP, 46,342,391 bytes; Range `bytes=0-15` returned HTTP 206 and exactly 16 bytes.
- Exact cached-runtime trace proves the running core's default Mouse mode consumes
  relative MouseEvent movement; the `hybrid-root` control delivers zero for that
  field while `geometry-only` delivers non-zero values in both axes.
- Official source and the cached runtime disprove the old invalid-option theory:
  `melonds_touch_mode=Touch` is valid; the historical `core-touch` experiment
  instead had an event-dispatch mismatch and duplicate-binding risk.
- Android 15 AVD first tap, exact 3x3 targets, horizontal/vertical/diagonal drag,
  hold, release, portrait, live rotation, landscape, fullscreen, injected stale
  viewport fallback, and save-state checks passed for `geometry-mapped`.
- Controlled fullscreen frames prove exact core mapping: `+102` DS X moved the
  cursor 85 rendered pixels in the 213-pixel viewport; `+48` DS Y moved it 40
  rendered pixels in the 320-pixel viewport.
- Real-phone user evidence now passes startup, click, cursor/animation, all drag
  directions, hold/release, virtual pad, fullscreen, and save-state for C02.
  Firefox Android normal play passes; portrait/landscape was explicitly waived.
  See `reports/nds-touch/04-physical-android.md`.
- Staging `/offline` UI reports mGBA and melonDS cores downloaded with sizes and enabled delete controls.
- Read-only production HTTPS headers show Cloudflare, HSTS, CSP, no-sniff, and expected security policies; Cloudflare WAF/rate-limit/Bot configuration remains unverified.
- Read-only TVBox audit: application, staging, and tunnel services active; production backup file exists; no dedicated AN3 backup timer found; Cloudflared has registered connections but also transient network errors.
- Added and locally verified scheduled-backup deployment assets (SQLite backup, media manifest, service, timer); not activated in production.
- Staging Linux backup rehearsal passed: integrity `ok`, WAL retained, database/manifest mode `0600`, 2 manifest entries.
- Staging restore drill passed from that backup: integrity `ok`, 15 tables, 2 games, temporary restore removed.
- Host-side systemd verification confirmed the existing arcade units; backup-unit verification is pending the production-only helper installation path.
- Requirement-by-requirement evidence is summarized in `reports/production-readiness/11-completion-matrix.md`.
- Production deployment was explicitly approved and completed. Production health
  now passes at asset `def955887c68`; service/timer, rollback artifacts, served
  player hash, and public AVD smoke were verified.

## Remaining separate gates

- User subsequently confirmed save-state works on a real device; browser download-event evidence remains unavailable, but requirement is treated as PASS with user/device evidence.
- Physical Android accepted scope: PASS, with portrait/landscape explicitly
  waived for the tested phone.
- Firefox Android normal play: PASS.
- Installed PWA offline after network loss/restart remains OPEN.
- Full approximately 1.7 GB 3DS upload remains OPEN.
- Cloudflare WAF/rate-limit/Bot configuration verification remains OPEN.
- The NDS production promotion is complete. See
  `reports/production-readiness/13-nds-touch-production-deployment.md`.

## Safety status

Production NDS touch code was deployed only after physical validation, the full
gate, and explicit approval. No database restore was performed. No secrets,
passwords, tokens, cookies, or environment values are included here.

## Exact next step

NDS touch recovery is complete. Use the recorded rollback artifacts only if a
verified production regression appears.
