# Completion matrix

| Requirement | Evidence | Status |
| --- | --- | --- |
| New workspace, legacy read-only | `reports/bootstrap/source-import.md`, clean Git history | PASS |
| Full handoff/objective read | `reports/bootstrap/handoff-analysis.md` | PASS |
| Client-side emulation | `app.py`, `static/player.js`, integration/regression tests | PASS |
| melonDS auto-start and NDS touch bridge | staging browser DOM/runtime evidence; regression tests | PASS (browser/runtime scope) |
| EmulatorJS IndexedDB core contract | regression tests and staging Offline UI | PASS (API storage itself not exposed by in-app browser) |
| Report-first core selection | `tests/test_regression_invariants.py`, source inspection | PASS |
| Persistent core cache / offline UI | source tests and staging Offline UI showing mGBA/melonDS ready | PASS (full offline restart still open) |
| NDS ZIP and HTTP Range | staging `application/zip`, 46,342,391 bytes, HTTP 206 for 16-byte range | PASS |
| Chunk upload | local integration test only | PARTIAL; full 1.7 GB route open |
| Local/staging backup and restore | local + staging Linux backup, integrity `ok`; staging restore: 15 tables/2 games | PASS for staging drill |
| Scheduled production backup timer | assets prepared; TVBox audit found no timer; production not deployed | OPEN |
| Security/source/package checks | local baseline, headers, package boundary, read-only TVBox audit | PASS with Cloudflare config open |
| NDS touch runtime | `EXP-C02-geometry-mapped` on commit `15697a6`, staging asset `def955887c68`: exact 3x3 DS targets, all drag axes, hold/release, portrait/rotation/landscape/fullscreen, stale-viewport fallback, save state, and core-rendered X/Y displacement matching measured scale; a real phone now passes startup, click, and cursor movement; default remains `hybrid-root` | PASS for AVD browser/runtime/mapped/core-render scope; PARTIAL for physical device, remaining matrix open |
| Installed PWA offline end-to-end | no network-loss/restart device evidence | OPEN |
| Save-state export | user-confirmed working on real device; browser download event was not observed | PASS (user/device evidence) |
| Cloudflare WAF/rate-limit/Bot settings | authenticated zone dashboard review: no visible custom/rate-limit rules; Managed Rules upgrade prompt; Bot settings visible | PARTIAL; no settings changed |
| NDS touch production promotion | Requires physical Chrome PASS, physical Firefox PASS or documented exception, full regression, known rollback, and explicit approval for this candidate; none was inferred from earlier unrelated production work | OPEN / NOT APPROVED |

This matrix is the authoritative handoff summary. No OPEN item may be reported as PASS without stronger evidence matching its scope.
