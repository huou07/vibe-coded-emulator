# P4 staging large resumable-upload drill

Date: 2026-08-23 (Asia/Ho_Chi_Minh)  
Target: staging only.

A synthetic sparse zero-filled fixture of 1,887,436,800 bytes (approximately 1.8 GiB) was used. No copyrighted ROM was used.

| Check | Result |
| --- | --- |
| Chunk size / count | 8,388,608 bytes / 225 |
| First chunk accepted | PASS |
| Interrupted-client resume | PASS; server retained the expected next offset |
| Duplicate retry handling | PASS; `409` reported the persisted offset |
| Remaining sequential chunks | PASS |
| Finalization | PASS; finalized size matched the fixture |
| Staging cleanup | PASS; temporary game deleted, `upload_sessions=0`, synthetic-game rows `=0`, upload part files `=0` |
| Disk before / after | identical: 9,587,752,960 bytes used; 451,008,933,888 bytes free |
| Staging service RSS after | 60,216 KiB |

The local fixture, temporary chunk, cookie jar, and all staging test state were removed.

`LARGE_UPLOAD=PASS`

