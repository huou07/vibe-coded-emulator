# AN3 Arcade — Admin tab layout production release handoff

Date: 2026-08-24 (Asia/Ho_Chi_Minh)  
Scope: Admin dashboard task-tab layout only. The protected player source, routes, controls, canvas, and gameplay behavior were not edited.

## Release state

| Environment | Health | Asset | Result |
| --- | --- | --- | --- |
| Isolated staging | pass | `ab2ef82683e4` | Tested candidate. |
| Production | pass | `ab2ef82683e4` | Owner-authorized, owner-run release. |

The owner explicitly approved and manually ran the prepared release script on the production server:

```bash
sudo bash /tmp/deploy-an3-production-20260824-160208.sh
```

The script reported `PRODUCTION_RELEASE=PASS`, asset `ab2ef82683e4`, and retained application backup `/opt/an3-arcade-backups/20260824-160315`.

## Delivered behavior

- The admin task-tab strip follows the accepted reference layout on desktop: a single aligned row, matching tab proportions, and content vertically centered in each tab.
- The tab strip is the only horizontally pannable surface on narrow viewports. Vertical drag and document-level overscroll are blocked for this interaction.
- The final tab label is restored to `Tài khoản và báo lỗi` (`Accounts and reports`).
- No player-page code or protected player interaction surface changed.

## Validation evidence

- `python3 -m unittest discover -s tests -v`: **28/28 passing**.
- Python compilation, JavaScript syntax, deploy-script syntax, and `git diff --check`: pass.
- Staging SSH preflight: `STAGING_SSH_KEY_AUTH=PASS`.
- Staging release: `STAGING_RELEASE=PASS`, asset `ab2ef82683e4`.
- Public production health verification after the owner-run release returned `ok: true`, `environment: production`, and asset `ab2ef82683e4`.

## Deployment observation

The owner-run script printed an initial localhost `curl` connection failure for port `8091`, then completed with `PRODUCTION_RELEASE=PASS`. The required public read-only health check immediately afterward confirmed that production is serving the expected asset. Treat a future case where the final PASS marker or public health check is absent as a failed release and investigate before further changes.

## Operating procedure retained

1. Preserve the dirty worktree and do not copy data, sessions, ROMs, or fixtures between staging and production.
2. Run local tests and the approved strict-host-key staging deploy flow.
3. Verify the affected staging UI before considering production.
4. Every staging deploy must prepare and print the matching production archive, production script, and asset.
5. Obtain a new explicit owner approval for each production candidate. Codex never runs production deployment.
6. Owner runs the exact prepared script manually, then perform the public read-only health check and confirm the expected asset.

## Relevant files

- `app.py` — Restored final Admin tab label.
- `static/site.css` — Reference-aligned Admin tab layout and horizontal-only narrow-screen panning.
- `tests/test_monitoring.py` — Regression coverage for the tab strip and staging-to-production preparation rule.
- `deploy-stage.sh`, `docs/staging.md` — Staging-first release procedure and mandatory production-script preparation.

## Explicit non-inclusions

- No passwords, private keys, tokens, session cookies, or production data are recorded.
- No production database migration or data import.
- No change to player, emulator, game controls, gameplay, Offline ROM storage, or service-worker behavior.
