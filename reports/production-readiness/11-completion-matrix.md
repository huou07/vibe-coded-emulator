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
| Real-device NDS touch | user matrix: baseline/touch click but no movement; native/root fail startup; current touch-only document-level move fallback is on staging | OPEN; Android movement test required |
| Installed PWA offline end-to-end | no network-loss/restart device evidence | OPEN |
| Save-state export | user-confirmed working on real device; browser download event was not observed | PASS (user/device evidence) |
| Cloudflare WAF/rate-limit/Bot settings | authenticated zone dashboard review: no visible custom/rate-limit rules; Managed Rules upgrade prompt; Bot settings visible | PARTIAL; no settings changed |
| Production preflight and deployment | user has explicitly approved production; backup timer activation and final preflight remain pending | AUTHORIZED / OPEN |

This matrix is the authoritative handoff summary. No OPEN item may be reported as PASS without stronger evidence matching its scope.
