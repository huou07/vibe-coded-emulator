# AN3 Arcade — Migration A5: Initial Data Manifest

Date: 2026-08-21 (Asia/Ho_Chi_Minh)  
Status: `INITIAL_SEED=PASS`; `FINAL_DELTA=PENDING`

The source host lacks `rsync`, so owner-approved initial transfer used metadata-preserving SCP over the private LAN to a mode-0700 landing directory. The source stayed live and writable; no `--delete` or raw copy of live SQLite WAL/SHM was used.

| Dataset | Bytes | Files | Target landing parity |
| --- | ---: | ---: | --- |
| ROMs | 2,177,179,174 | 71 | PASS |
| Covers | 12,176,830 | 96 | PASS |
| Screenshots | 7,345,828 | 215 | PASS |
| Uploads / custom | 0 | 0 | PASS |
| Prepared ROMs | 226,077,436 | 11 | PASS |
| Proposal media | 5,530,787 | 148 | PASS |
| EmulatorJS cache | 28,083,401 | 31 | PASS |
| Persistent backups | 4,706,304 | 11 | PASS |

The exact production `app.py` SHA-256 matched source and landing target:

```text
f0f6642dbaa76b45c39ec4dd28c4cdc60ffb66886618b6a14eae8378b9323ce8
```

Source online SQLite snapshot, target landing snapshot, and target installed database each passed `PRAGMA integrity_check = ok`. The target database will be replaced by a final consistent snapshot during cutover; target-only test-session writes are non-authoritative.
