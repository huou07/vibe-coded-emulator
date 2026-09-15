# AN3 Arcade — Admin tab layout staging handoff

Date: 2026-08-24 (Asia/Ho_Chi_Minh)  
Scope: Admin dashboard tab strip only. Player source and routes were not edited.

## Accepted layout behavior

- The admin task tabs use the reference-aligned desktop grid with vertically centered content.
- Narrow viewports constrain panning to the tab strip's horizontal axis; the document does not overscroll.
- The final tab label has been restored to `Tài khoản và báo lỗi` (`Accounts and reports`).

## Validation and staging release

- `python3 -m unittest discover -s tests -v`: 28/28 passing.
- Python, JavaScript and deploy-script syntax checks, plus `git diff --check`: pass.
- Staging SSH preflight: `STAGING_SSH_KEY_AUTH=PASS`.
- Staging release: `STAGING_RELEASE=PASS`, asset `ab2ef82683e4`.
- Staging health: `environment: staging`, asset `ab2ef82683e4`.

## Prepared owner-run production candidate

Production was not run. If this staging release is accepted, the owner may run:

```bash
sudo bash /tmp/deploy-an3-production-20260824-160208.sh
```

Expected asset: `ab2ef82683e4`.
