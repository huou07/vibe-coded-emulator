# Public GitHub publication — audit, sanitization, and blockers (2026-09-16)

Target: `https://github.com/huou07/vibe-coded-emulator`. **Publication was not
performed**: mandatory gates pass on a sanitized candidate, but publishing is
blocked by missing GitHub credentials/identity. Nothing was pushed.

## Result

| Item | Status |
| --- | --- |
| Security scan of tracked content | Implemented and tested (0 real secrets) |
| PII/infra sanitization of product source | Implemented and tested |
| Sanitized publication candidate | Implemented and tested (gate passes) |
| Fail-closed pre-publication check + skill + AGENTS rule | Implemented and tested |
| Push / repo creation / GitHub security settings | **Blocked** (no `gh`, no credentials) |
| Public history decision | Clean snapshot chosen; **no history rewrite performed** |

## Security findings (categories only; no values)

| Category | Location (redacted) | In Git history? | Rotation |
| --- | --- | --- | --- |
| Personal email address (PII) | product source: default maintainer contact; deploy reverse-proxy config | Yes | Not a credential — sanitized in the snapshot |
| Private LAN addresses (infra) | deploy scripts, compose files, docs, Android network-security config | Yes | Sanitized in the snapshot |
| Personal filesystem paths | docs, scripts, native web assets | Yes | Sanitized in the snapshot |
| Private-key marker | `app.py` | Yes | **False positive** — it is an upload-validation regex |
| `generic-api-key` | `static/player-runtime.js` | Yes | **False positive** — a `localStorage` key name |
| Real API keys / OAuth secrets / tokens / SSH keys / DB passwords | none found | — | None |

No real credential value was found, printed, or committed. Full-history scan of
the *original* development history was not run because that history is not
selected for publication (clean snapshot instead).

## Blockers requiring the owner

1. **GitHub access.** `gh` is not installed and no GitHub credential/remote is
   configured on this machine. Creating the repository, verifying
   `huou07/vibe-coded-emulator`, pushing, and configuring repository security
   settings all require it.
2. **Public commit identity.** Existing commits carry a machine-hostname author
   address, which must not be published. Provide the author name/email (or
   approve a GitHub `noreply` address) for public commits.

## Delivered

- **Sanitized candidate** at `/tmp/an3-public/vibe-coded-emulator` (private,
  outside the repo; 361 files, 8.9 MB) containing only product source:
  `app.py` + shared modules, `static/`, `tests/`, `native/` (Eden bridge),
  `native-offline/` source (no vendored core binaries, no releases), `rust-gateway/`,
  sanitized `deploy/` and `tools/`, plus `LICENSE`, `THIRD_PARTY_NOTICES.md`,
  `README.md` (real repo URL), `CONTRIBUTING.md`, `SECURITY.md`, `.env.example`,
  `.gitleaks.toml`, `docs/` (building, architecture/rendering, licensing) and a
  least-privilege CI workflow.
- **Excluded**: `.opencode/`, `.codex/`, `AGENTS.md`, `reports/`, `work/`,
  root handoff/status docs, `tools/ssh/`, `deploy/shadow/`, vendored core
  binaries, release artifacts, caches and build outputs.
- **Tooling**: `tools/publication-check.sh` (fail-closed; requires gitleaks),
  `.opencode/skills/public-release-security/SKILL.md`, and the mandatory gate
  rule in `AGENTS.md`.

## Gate evidence

```
PUBLICATION_CHECK=PASS
  gitleaks: 0 findings
  personal-data and infra patterns: clean
  no ROM/keys/firmware/database/binary content
  required license/notice files present
```

The single gitleaks finding was suppressible only via a narrowly scoped,
documented allowlist for the `localStorage` key name in
`static/player-runtime.js`.

## Notes for the continuation

- The working tree keeps the real staging LAN host in the Android
  network-security config so the staging app keeps working; the public snapshot
  uses the RFC 5737 documentation address with instructions to replace it.
- The candidate is a snapshot, so it must be committed with a truthful
  provenance note ("exported from the private development history; see
  provenance") rather than fabricated history.
- macOS staging artifacts remain ad-hoc signed and are not part of the public
  source release.

## Update — reproducible builder + manual publish script (2026-09-16)

Owner decisions applied:

- **Publishing stays manual.** `AGENTS.md` now states: never publish to GitHub
  automatically; only on an explicit request. `tools/publish-github.sh` refuses
  to run without `--confirm`.
- **No development history is published.** The public repository is created from
  a clean snapshot as a **single fresh commit** with a GitHub `noreply` author
  (`huou07 <huou07@users.noreply.github.com>` by default, overridable via
  `AN3_PUBLIC_AUTHOR_NAME`/`AN3_PUBLIC_AUTHOR_EMAIL`). No history rewrite, no
  force-push, and the private history stays private.
- **Reproducible snapshot**: `tools/build-public-snapshot.sh` writes
  `work/public-snapshot` (product source only; PII/infra replaced; no AI files,
  reports, vendor binaries or releases).
- **Gate**: `tools/publication-check.sh [--history]` — fail-closed, requires
  gitleaks; currently `PUBLICATION_CHECK=PASS` including the history scan of the
  fresh commit.
- Public template files live in `tools/publication/` (README-adjacent docs,
  `.env.example`, `.gitleaks.toml`, CI workflow, provenance).

### Owner runbook (macOS)

```bash
brew install gh gitleaks
gh auth login
cd "<repo>"
tools/build-public-snapshot.sh
tools/publication-check.sh work/public-snapshot --history
tools/publish-github.sh --confirm
```

`publish-github.sh` creates `huou07/vibe-coded-emulator` (public) if missing,
pushes `main`, and applies secret scanning + push protection, Dependabot alerts
and security updates, private vulnerability reporting and branch protection,
reporting each result (settings that the plan or permissions reject are listed,
not silently assumed).

## Published — 2026-09-16

`https://github.com/huou07/vibe-coded-emulator` is live (public).

- Published from a **clean snapshot** (`tools/build-public-snapshot.sh`), not the
  development history: one fresh commit authored
  `huou07 <huou07@users.noreply.github.com>`, merged non-destructively with the
  repository's pre-existing commit (snapshot files win, no force-push).
- Security gate before the push: `PUBLICATION_CHECK=PASS` (gitleaks 0 findings;
  personal-data and infra patterns clean).
- Repository settings applied: secret scanning + push protection, Dependabot
  alerts, Dependabot security updates, private vulnerability reporting, branch
  protection (required PR + the `test` CI check).
- GitHub token scope `workflow` was required to publish `.github/workflows/`;
  granted via `gh auth refresh -h github.com -s workflow`.

Republish/update later with:

```bash
tools/publish-github.sh --confirm
```

It rebuilds the snapshot, re-runs the gate, and pushes. Publishing is never
automatic.

## Production release 2.0.0 (owner-approved) — 2026-09-17

- The root `deploy.sh` was **stale and unsafe** (packaged only `app.py/static`,
  so production would fail to import `netcode`/`sync_engine`/`qrcodegen`). It now
  exits with a pointer to the reviewed path.
- New `deploy-production.sh` (requires `AN3_PRODUCTION_APPROVED=1`): packages with
  `deploy/package-production.sh`, runs a payload security preflight, uploads, and
  runs the host-side `update-production.sh` (backup + asset check + health gate).
- Deployed: `PRODUCTION_RELEASE=PASS`, asset `973c9002b67f`, release
  `production-388027d63bb9c5a4`; app backup
  `/opt/an3-arcade-backups/20260917-010822`, DB backup
  `/srv/an3-arcade/backups/arcade-predeploy-20260917-010822.db` (integrity PASS).
- Verified live: `/health` = production, `/` 200, `/licenses` 200,
  `/licenses/gpl-3.0.txt` 200 (35,149 B); staging-only routes (`/controller`,
  `/multiplayer`, `/api/sync/*`) correctly 404.
- **Finding**: the production database still stores a personal maintainer email
  in `site_settings.maintainer_email`, which the footer renders publicly. The
  code default is now empty; clear or replace the stored value if it should not
  be public.
