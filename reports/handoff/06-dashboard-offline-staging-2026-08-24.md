# AN3 Arcade — Dashboard analytics and Offline readiness staging handoff

Date: 2026-08-24 (Asia/Ho_Chi_Minh)  
Scope: dashboard analytics truthfulness and Offline **Device Ready** badge placement only. The player source was not edited.

## Delivered to isolated staging

- Replaced fixed Visit and Play chart sequences with the SQLite-backed `page_views` and `play_events` daily series.
- The series now uses local calendar-day boundaries for the last 14 days, including the current partial day, instead of a rolling 24-hour cutoff.
- Replaced the visible static dashboard totals, game count, and most-played list with the corresponding real dashboard data.
- Moved the green Offline **Device Ready** check into a stable top-right badge position; it no longer depends on a fixed left offset.

## Validation

- Local: `python3 -m unittest discover -s tests -v` — 26/26 passing.
- Local: Python/JavaScript/shell syntax checks and `git diff --check` — pass.
- Staging SSH key preflight — `STAGING_SSH_KEY_AUTH=PASS`; the approved local deployment-key fingerprint matched the owner-supplied fingerprint.
- Staging release — `STAGING_RELEASE=PASS`, asset `82a775a3c988`.
- Staging health — `{"ok": true, "environment": "staging", "asset_version": "82a775a3c988"}`.
- Browser QA at `http://192.168.1.8:8092/admin`: both canvases rendered live data and contained 14 daily values; the prior sample totals and sample series were absent; no console errors.
- Browser QA at `http://192.168.1.8:8092/offline`: the import form remained visible and enabled; the Device Ready check was absolutely positioned 17px from the card's top/right edge; no horizontal overflow at the checked viewport.

## Release boundary

`deploy-stage.sh` prepared the matching source-only production candidate as required by the release procedure, but it did not deploy or restart production. Production requires a separate explicit owner approval.
