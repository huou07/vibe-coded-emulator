# Phase 1 audit

Status: COMPLETE.

Bootstrap established a fresh repository from the legacy working tree. The legacy path is not a Git repository, so source provenance is the copied working-tree state rather than a commit. Detailed application, dependency, deployment, data-path, and security audit follows after the passing baseline.

## Current source and runtime shape

- Python 3.9.6, standard-library HTTP server, SQLite, static JavaScript/CSS/PWA assets; no dependency manifest is present.
- Application entrypoint is `app.py`; data roots are environment-configurable and default under `data/`.
- Production and staging systemd units are separate and use distinct `/opt`, `/srv`, and `/etc` paths. Services run as `tvshare` with `NoNewPrivileges`, `PrivateTmp`, `ProtectHome`, `ProtectSystem=strict`, and bounded memory.
- Deployment scripts package source, use staging release symlinks/health polling, and create a SQLite Online Backup API backup for production before restart.
- Current copied database is a local development artifact: WAL mode, zero games/users/sessions. It is not production data and was not inspected beyond schema/count metadata.
- No external runtime, staging endpoint, production endpoint, or secret environment value was accessed.

## Verified invariants in source

`static/player.js` contains melonDS mapping, `EJS_startOnLoaded = true`, the `EmulatorJS-core` IndexedDB store and `?EJS_KEYS!` index update, report-driven preload, NDS canvas mutation/touch handling, and persistent core cache usage. `app.py` preserves NDS original-file delivery and HTTP Range handling. Integration tests cover public drafts/testing, auth hashing, upload behavior, Range delivery, NDS ZIP delivery, and the admin flows.

## Findings and discrepancies

1. `README.md` is stale and still documents DeSmuME/manual start, core marker v6, and server-side prepared NDS behavior. This matches the handoff backlog and must be corrected before the next handoff.
2. `static/offline.js` still lists DeSmuME variants as NDS `coreCandidates`, although the current player is melonDS-only. This is a potential invariant violation and requires a focused regression-test/code review before production changes.
3. The copied legacy tree has no Git metadata and therefore no commit baseline; the fresh workspace has no commit yet. The source-import record explicitly records this provenance limitation.
4. Manual real-device NDS touch, installed-PWA offline, full 1.7 GB 3DS upload, scheduled backup/restore, and Cloudflare WAF/rate-limit configuration remain unverified backlog items.

## Security and data constraints

Secret values were not read or emitted. The repository contains only placeholder/config-name references. Production SQLite, ROMs, backups, and environment files remain outside this workspace and were not mounted or modified. Production deploy and DB restore remain approval-gated.

## Audit gate

Phase 1 read-only audit: PASS with the above findings. The next required action is Phase 2 invariant/regression baseline review; no production deployment is authorized by this report.
