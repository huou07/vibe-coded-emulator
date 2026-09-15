# AN3 Arcade P3.0 — Repository reconciliation

Date: 2026-08-23 (Asia/Ho_Chi_Minh)

## Scope and source evidence

This P3 reconciliation is read-only with respect to production and preserves the intentionally dirty local tree. It was based on these full-path records:

- `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/00-comprehensive-project-handoff-2026-08-21.md`
- `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/01-p2-15-staging-acceptance-2026-08-23.md`
- `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/p2-acceptance/07-production-deployment.md`
- `/Users/meomeo/Downloads/AN3-P3-OPERATIONAL-UX-ANDROID-AUTOMATION(1).md`

Current live, read-only health responses report asset `9cf7de4b8d0b` for both isolated staging (`http://192.168.1.8:8092`) and production (`http://192.168.1.8:8091`). No production endpoint, service, data path, or configuration was changed.

## Checkpoint

| Field | Value |
| --- | --- |
| Repository | `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade` |
| Branch | `ui/production-ux-refresh` |
| Committed HEAD | `542ef985ddd22435cad00695b065dda1be4f80d3` |
| Branch relation | ahead of `origin/ui/production-ux-refresh` by 23 commits |
| Working tree | intentionally dirty and preserved |
| `git diff --check` | pass |
| Current static asset fingerprint | `9cf7de4b8d0b` |
| Release checkpoint | `REPO_CHECKPOINT=DOCUMENTED_DIRTY` |

## Dirty-path classification

| Category | Paths | Handling |
| --- | --- | --- |
| Accepted P2.15 application/source package | `app.py`, `static/player.js`, `static/service-worker.js`, `static/site.css`, `static/site.js`, `deploy-stage.sh`, `deploy.sh`, `deploy/an3-arcade-staging.service`, `deploy/p2-install-staging.sh`, `deploy/p2-package-staging.sh`, `deploy/p2-rebuild-staging.sh`, `deploy/p2-update-staging.sh` | Preserve as the known P2.15 baseline. The deployed `app.py` checksum and locally calculated static fingerprint prove this boundary. |
| Preserved enrichment-review WIP, overlapping the accepted source package | enrichment proposal schema/routes/review UI and its integration coverage in `app.py`, `static/site.js`, `static/site.css`, and `tests/test_integration.py` | Do not discard or split from the accepted P2 baseline: P2.15 packaged the same application/static tree, and the features overlap the release source boundary. P3 changes must be additive, covered, and independently documented. |
| P2 operational/test support | `tests/test_regression_invariants.py`, `tests/test_monitoring.py`, `docs/design-system.md`, `docs/ui-page-contract.md`, `reports/handoff/`, `reports/p2-acceptance/`, `reports/p2-ui/`, `reports/roadmap/`, `reports/server-migration/`, `reports/staging/` | Preserve. These document the accepted P2 release and its stage-only checks. |
| Generated junk | `.DS_Store`, `reports/.DS_Store` | Leave untracked and out of commits/releases. |
| Unknown changes | none identified | No overwrite risk found. |

## Decision

The P2.15 file boundary is historically uncommitted and interleaves accepted application work with enrichment-review work. Creating a retrospective separation commit would risk misrepresenting or overwriting that history. P3 therefore starts from the documented dirty checkpoint rather than forcing a clean tree.

```
P2_RELEASE_PROVENANCE=PASS
UNKNOWN_DIRTY_OVERWRITE_RISK=NONE
```

The accompanying release details are in `/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/p3/01-production-release-manifest.md`.
