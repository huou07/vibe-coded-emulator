# P2.1b data isolation

Date: 2026-08-23 (Asia/Ho_Chi_Minh)

The staging rebuild used SQLite's Online Backup API against the production
database. It did not raw-copy a live SQLite database or WAL sidecars.

Only the two authorized test-game records were retained from that snapshot.
The rebuild clears copied sessions, users, ratings, comments, favorites,
reports, page views, play events, screenshots, updates, proposals, upload
sessions, site settings, and all other game records before fixture seeding.
It creates a new staging-only authentication pepper instead of copying a
production environment value.

The stale staging data tree found during discovery contained a broad
production-derived media copy. It was removed only after the new staging
service passed health; production paths were never modified.

## Isolated writable data tree

`/srv/an3-arcade-staging` contains its own database, `roms`, `prepared-roms`,
`covers`, `screenshots`, `proposal-covers`, `proposal-screenshots`, `custom`,
`uploads`, `emulatorjs-cache`, `cache`, `tmp`, `logs`, and `backups`
directories. The root is `tvshare:tvshare` mode `0750`; the database is mode
`0640`. The protected staging environment file is root-owned mode `0600`.

Final checks: SQLite integrity `ok`; staging sessions `0`; staging users `0`.
The clean authentication state means a production browser cookie cannot
authenticate to staging. A staging-only admin must be created through the
application's approved bootstrap/admin mechanism before authenticated admin
acceptance testing.
