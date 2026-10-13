# Mission checkpoint — 2026-10-13

Branch `feature/phone-controller-cross-platform`. HEAD `4fb4c4b`.

Starting point was `deade56` with six uncommitted paths. Five of them were
absorbed into commit `2a20968` because they were real work in progress:
`docs/REGRESSION_GUARDS.md` carried four new regression-guard entries
(RG-145 through RG-148) that had never been committed. The other two
(`tests/an3ctl.test.mjs`, `tools/publish-github.sh`) are still uncommitted and
were deliberately left alone — they are not this mission's work. `gen/schemas`
regeneration and `cancel_native_rom_import.toml` likewise remain untouched.

## Commits

| Commit | Subject |
| --- | --- |
| `9d4a7cd` | Scratch inventory tool and preserved Linux acceptance evidence |
| `46011ea` | Publication security gate fails closed |
| `2a20968` | Skill consolidation and stale-path correction |
| `d858e36` | Google cloud sync removed, macOS metadata untracked |
| `e1378bb` | Private-repo CI, two broken public CI references fixed |
| `4fb4c4b` | Direct-HTTPS candidate and deployment survey |

## Verified results

- `bash tools/verify-project.sh` → `PROJECT_VERIFY=PASS`
  (434 Python tests, 20 skipped; 93 Node tests, 90 pass / 3 skipped).
- `python3 -m unittest tests.test_publication_gate` → 12 pass. The same tests
  report 4 failures against the pre-fix `publication-check.sh`.
- `python3 -m unittest tests.test_https_candidate_config` → 7 pass.
- `tools/build-public-snapshot.sh` + `tools/publication-check.sh` → PASS on a
  real 505-file snapshot.
- `hub.py where/status/doctor/verify/report` → all correct; `verify vce` PASS
  with evidence recorded. `usage --slug vce` correctly reports UNAVAILABLE
  rather than a fabricated zero.
- Live read-only probes against `https://an3tocom.space` → no traversal, no
  source disclosure, no XSS reflection, no CORS, Host spoofing rejected, no
  admin surface, terse errors. `/sync` and `/api/sync/*` return 404 in
  production, matching RG-087.

## Outstanding, needs owner or root

1. Install and start Caddy from `deploy/caddy-production.Caddyfile`; the router
   forwards already reach the host but nothing listens behind them.
2. Bind `/opt/an3-arcade/app.py` from `0.0.0.0:8091` to `127.0.0.1:8091`.
3. Replace the real Gmail ACME contact in `/opt/an3-arcade/deploy/Caddyfile`.
4. Remove router forwards for 18088 and 3478; nothing serves them.
5. Identify `0.0.0.0:18880` and `0.0.0.0:18099` and bind them to loopback.
6. Delete `~/an3-migration-final` and `~/an3-migration-initial` (never readable
   by `agents-worker`), and ~433M of residue in `~/eden/.cache` and
   `~/an3-parity-build`.
7. Move `/home/agents-worker/vce-scratch-archive/` somewhere durable.
8. Decide retention for the separate `opencut-v2-*` / `or-*` group (~15G).

## Not done, deliberately

- **No platform acceptance runs.** Native packages need the pinned core
  artifacts and per-platform toolchains. Android, Windows and macOS
  gameplay, frame pacing, input and save/load are **UNVERIFIED** from this
  Debian host.
- **No performance numbers.** Real FPS, frame pacing and input latency require a
  GPU and the pinned cores. Only the static background-work check was done:
  `app.py` starts no unconditional scheduler, and the sync surface is 404 in
  production.
- **No tunnel cutover.** Production routing is untouched.

## Next executable action

Run the step-1 loopback rebind, then steps 2–3 of the migration checklist in
`docs/checkpoints/direct-https-migration.md`. Those are root actions; everything
on the project side is prepared and tested.
