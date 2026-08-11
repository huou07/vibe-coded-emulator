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

## Current verification

- Read-only source security review: no shell execution, unsafe deserialization, or secret values found; upload sizes, CSRF, rate limiting, and data-root containment are present in source.
- Expanded regression suite: PASS, 5/5 tests, including melonDS startup/touch, IndexedDB core contract/report-first selection, persistent cache, and NDS ZIP/Range assertions.
- Staging health `http://192.168.1.11:8092/health`: UNVERIFIED; connection refused from this environment.
- Production health `https://an3tocom.space/health`: UNVERIFIED; hostname did not resolve from this environment.

These runtime checks are not deployment failures attributable to the new workspace, but they block any claim of staging or production readiness.
