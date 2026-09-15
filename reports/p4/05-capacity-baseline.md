# P4 staging capacity baseline

Date: 2026-08-23 (Asia/Ho_Chi_Minh)  
Target: `http://192.168.1.8:8092` only; direct LAN, unauthenticated read-only requests.

`ab` sampled `/health`, `/`, `/static/site.js`, and `Range: bytes=0-1048575` for the authorized staging GBA download. Health, homepage, and static samples used 200 requests per level; range used 50 requests per level. No production request was made.

| Endpoint | Concurrency | p50 ms | p95 ms | Requests/s | Errors |
| --- | ---: | ---: | ---: | ---: | ---: |
| `/health` | 1 / 5 / 10 / 25 / 50 | 11 / 14 / 15 / 16 / 18 | 13 / 19 / 21 / 135 / 383 | 87.30 / 335.35 / 448.42 / 535.68 / 304.12 | 0 / 0 / 0 / 0 / 0 |
| `/` | 1 / 5 / 10 / 25 / 50 | 17 / 22 / 34 / 196 / 301 | 22 / 37 / 77 / 688 / 2175 | 54.48 / 200.27 / 218.41 / 97.98 / 60.39 | 0 / 0 / 0 / 0 / 0 |
| `/static/site.js` | 1 / 5 / 10 / 25 | 20 / 27 / 38 / 61 | 25 / 33 / 50 / 175 | 49.73 / 180.12 / 239.24 / 303.22 | 0 / 0 / 0 / 0 |
| GBA 1 MiB Range | 1 / 5 / 10 / 25 / 50 | 96 / 292 / 538 / 2764 / 3119 | 154 / 361 / 643 / 4130 / 3379 | 9.72 / 16.55 / 17.66 / 9.73 / 14.63 | 0 / 0 / 0 / 0 / 0 |

At static-asset concurrency 50, ApacheBench stopped making progress after 100 of 200 completions. The run was stopped rather than increased. Staging stayed healthy; `/health` at concurrency 50 still completed without errors. This is the first observed saturation symptom and makes 25 concurrent static requests the conservative present target until a later server-side concurrency investigation.

| Snapshot | Server CPU / RSS | System memory used / available | Swap | Disk |
| --- | --- | --- | --- | --- |
| Before | 0.0% / 61 MiB | 776 MiB / 14.6 GiB | 0 | 3% used |
| After | 0.4% / 213 MiB | 931 MiB / 14.4 GiB | 0 | 3% used |

`CAPACITY_BASELINE=RECORDED`
