# Production-hardening plan

Status: IN PROGRESS; no production deployment.

Current source is a small single-host Python/SQLite application with client-side EmulatorJS. Preserve that architecture unless an audited requirement proves otherwise.

## Priority gates

1. Keep regression coverage for melonDS auto-start, NDS touch bridge, EmulatorJS IndexedDB core storage, report-first selection, persistent cache, NDS ZIP/Range delivery, and browser-local offline behavior.
2. Complete focused static/security review without reading secret values or production data.
3. Verify staging endpoint and service state before any staging deployment. Test NDS/GBA player behavior through runtime state/save-state evidence, not canvas screenshots.
4. Rehearse consistent SQLite backup/restore and define scheduled-backup verification without touching production restore state.
5. Perform production preflight only after staging, security, backup, observability, and E2E gates pass; stop for explicit production approval.

## Unverified backlog

- Real Chrome Android/Firefox Android NDS touch.
- Installed PWA offline end-to-end after network loss and app restart.
- Full approximately 1.7 GB 3DS chunk upload through the intended route.
- Cloudflare WAF/rate-limit/Bot configuration.

No item above is marked complete by static tests.

## Verification history and current state

- Read-only source security review: no shell execution, unsafe deserialization, or secret values found; upload sizes, CSRF, rate limiting, and data-root containment are present in source.
- Expanded regression suite: PASS, now 6/6 tests, including melonDS startup/touch, IndexedDB core contract/report-first selection, persistent cache, and NDS ZIP/Range assertions.
- The outage recorded in report 04 was historical and the host later recovered without intervention.
- Current NDS staging health passed on commit `15697a6`, asset `def955887c68`, with Android 15 AVD mapped/core-render validation. Physical Android remains OPEN.
- Production health was previously verified at asset `7f143995ae30`; it was not re-queried or changed during the current NDS touch loop.

The current blocker for NDS touch promotion is physical Android validation,
followed by a fresh preflight and explicit approval for the exact candidate.
