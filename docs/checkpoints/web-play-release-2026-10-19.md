# Web play on production, and the apps line that has to be reconciled

Status: production is live with Web play; the apps line is not yet merged.
Owner decisions recorded here: the public product has no accounts, no ROM is
stored on the server, the browser supplies the cores and the interface.

## What production serves now (2026-10-19 01:58 +07)

| Field | Value |
| --- | --- |
| Host | `http://192.168.1.8:8091/`, `an3-arcade.service`, user `tvshare` |
| `asset_version` | `fe0a9e80f859` |
| `release_id` | `production-ee45520ce725c27d` |
| Archive | `an3-arcade-production-20261019-015826.tgz`, sha256 `6ab250d94e48e8d33259e113654677e6569b814e6e1f3802b20abc4f3758d0f0` |
| Backup | `/opt/an3-arcade-backups/20261019-015835` |
| Rollback | `sudo an3-arcade-rollback-production /opt/an3-arcade-backups/20261019-015835` |
| Route shape | `/`, `/download-app`, `/offline`, `/licenses` 200; `/login`, `/register`, `/admin`, `/api/account/*`, `/games` 404 on every verb |
| Shell | `Web play` + `Download app` only; zero account links in a production-mode render |
| Update gate | `PRODUCTION_RELEASE=PASS` — the first passing health gate on this host |

## Web play verified

| Check | Where | Result |
| --- | --- | --- |
| GBA import -> library -> play | live production, `http://192.168.1.8:8091` | `ready`, two canvases, no notice; ROM stored with its bytes (32768) |
| GBA import -> library -> play | non-secure LAN origin, `http://192.168.1.8:18099` | same, `isSecureContext: false` |
| Account links on the page | live production | 0 |
| 3DS on a non-secure origin | `http://192.168.1.8:18099` | card states the reason; **not runnable** |

Three defects were found and fixed to get there:

1. **The embedded launch never started.** `/offline` was returned with the default
   page policy (`connect-src 'self'`, `style-src 'self'`), so EmulatorJS could not
   fetch its core from the CDN and inline styles were refused. A page that hosts
   the player now gets the player's CSP and cross-origin isolation
   (`send_html(..., player_csp=True)`) without pretending to be the player shell.
2. **The ROM was never stored on a LAN origin.** `writeRom` returns `{file}` when
   OPFS is unavailable — which is every non-secure context, i.e. `http://<lan-ip>`
   — and the caller dropped `file` unconditionally, so the record kept neither a
   handle nor the bytes. Verified fixed on a non-secure origin.
3. **The update path could not report success.** `deploy/update-production.sh`
   computed the fingerprint with a copy of the application's algorithm that also
   sorted `directories`, and merged `static/` into the installed tree instead of
   replacing it. Both are fixed; the installed tree is now exactly the released
   tree and the gate passes.

## Browser 3DS is blocked by a platform constraint, not by code

The 3DS core is the threaded build: it needs `window.crossOriginIsolated` with
`SharedArrayBuffer`, which browsers grant only in a secure context. Production is
a LAN IP over plain HTTP, so 3DS cannot run there. There is no non-threaded
fallback — `/data/cores/azahar-wasm.data` and `azahar-thread-wasm.data` both 404.

Options, none taken yet: serve production over HTTPS (the repository carries
`deploy/Caddyfile` and `cloudflared-config.yml.example` for exactly this), or use
the installed app for 3DS. The card now states the reason without disabling
itself, because RG-078 forbids a browser-only 3DS lock.

## The apps line and this branch are two histories

`origin/main` is a squashed 2-commit "initial public release" at **3.3.3**. The
`codex/*` branches are descendants of it, and
`codex/vce-3.6.8-ci-candidate` carries **3.6.8** — the version production's
download catalog serves and the version the installers in
`/opt/an3-arcade/native-offline/releases/` were built from. That line and the
development branch (`feature/semantic-ui-inspection`) share no merge base.

Unmerged branches with unique work, by recency:

| Branch | Unique commits | Note |
| --- | --- | --- |
| `codex/vce-3.6.8-ci-candidate` | 46 | 3.6.8, the app version in production |
| `codex/vce-optional-features-beta` | 52 | on top of the same base |
| `codex/vce-desktop-parity` | 333 | desktop surfaces |
| `codex/vce-3.6.8-flatpak-version-fix` | 398 | flatpak |
| `product/3.3.3-release` | 234 | the 3.3.3 release |
| `codex/public-snapshot-completeness-4b48` | 123 | publication candidate |
| `core-only/web-3ds-audio-gate` | 1 | the browser 3DS audio-gate fix, ported and deployed |

The unreconciled state is why the public product had no Web play: the app line
descends from 3.3.3 and never received the Web work on this branch. Reconciling
them is the remaining release blocker, and it is a deliberate merge, not a
fast-forward: pick the highest app version as the base, carry the Web-play and
no-accounts contract onto it, and re-run both gates before any publication.

## Still open

- NDS browser play: needs a lawful NDS fixture; no synthetic generator exists in
  the repository, so it stays **UNVERIFIED** for real boot.
- Web 3DS: needs HTTPS on the production host.
- UI parity with the installed app shell, and the visual review itself — the
  review is a human verdict, and `read_image` is unavailable in this session.
- Per-platform performance measurement.
- The apps-line reconciliation above, then one release to GitHub and production.
