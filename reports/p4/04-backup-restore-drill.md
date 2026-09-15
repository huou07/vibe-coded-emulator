# P4 backup restore drill

Date: 2026-08-23 (Asia/Ho_Chi_Minh)  
Scope: production backup only; the live production database was never restored over or opened for write access.

## Repair before drill

The scheduled backup service runs as `tvshare`, but its executable had become `root:root` mode `0750`, which prevented execution. The narrowly scoped repair changed the executable to `root:tvshare` mode `0750`; a new backup then completed successfully.

## Isolated restore evidence

A fresh consistent SQLite backup and its paired ROM manifest were used. The database was copied only to a newly created root-owned disposable restore directory, then removed by the drill cleanup.

| Check | Result |
| --- | --- |
| SQLite integrity check | `ok` |
| Foreign-key violations | `0` |
| Application tables | 16 |
| Aggregate records | 8,288 |
| Manifest rows | 383 |
| Manifest bytes | 2,230,256,264 |
| Restored database bytes | 1,273,856 |
| Disposable restore directory afterward | absent |
| Real backup retained | yes |

`BACKUP_RESTORE_DRILL=PASS`

