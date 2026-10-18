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

## UI/UX audit against the design-system contract

`work/phaseA/audit-ui-contract.mjs` measures the non-player shell against
`docs/design-system.md` and `docs/ui-page-contract.md` on a live surface, at 360,
390 and 1280px, on `/`, `/download-app`, `/offline` and `/licenses`. It reads the
`--ui-*` set from `body`, which is where `theme-violet.css` scopes it and where
`tests/web-runtime.test.mjs` reads it.

| Check | Before | After (production, `3877f6a56f94`) |
| --- | --- | --- |
| Token mismatches | 0 | **0** |
| Document-level horizontal overflow | **4** — `/offline` 462px at 360 and 390, `/licenses` 668px at 360 and 390 | **0** |
| `.button` under 42px | 0 | **0** |
| Missing menu control at 360/390 | 0 | **0** |
| Header height at 1280px | 72px | 72px |
| Shell destinations | — | `Web play`, `Download app` only |

Two cascade defects, not taste: `body.offline-shell .offline-facts` (five columns)
outranked the 560px media query by source order, and the readiness card pins a
fixed 308px column that collapsed the facts column to 0px; the offline hero's
full-bleed `100vw` margin arithmetic overshot by 8px at 390px. The licence table
now scrolls in its own labelled region.

**The audit was wrong before it was right**, and that is recorded deliberately:
its first version read the tokens from `documentElement`, where they are empty,
and reported 120 mismatches on a correct page. No product defect was reported on
that reading.

**Not established by a human eye.** This session's image reader is blocked
(`EACCES` traversing `/home`), so taste, hierarchy and legibility are still an
owner verdict. What is established is measurable: geometry, tokens, control tiers
and the responsive contract. The native shell declares no `--ui-*` set at all —
`native-offline/web/native.css` uses its own naming — so Web and app token parity
is a real divergence, not a measurement artefact, and is open work.

## Browser 3DS is blocked by a platform constraint, not by code

The 3DS core is the threaded build: it needs `window.crossOriginIsolated` with
`SharedArrayBuffer`, which browsers grant only in a secure context. Production is
a LAN IP over plain HTTP, so 3DS cannot run there. There is no non-threaded
fallback — `/data/cores/azahar-wasm.data` and `azahar-thread-wasm.data` both 404.

Options, none taken yet: serve production over HTTPS (the repository carries
`deploy/Caddyfile` and `cloudflared-config.yml.example` for exactly this), or use
the installed app for 3DS. The card now states the reason without disabling
itself, because RG-078 forbids a browser-only 3DS lock.

## Performance: what was measured, and what it cannot establish

Probes live in `work/phaseG/perf-probe.mjs`, `perf-core.mjs` and `perf-pixel.mjs`
and write their raw output to `work/phaseG/perf-*.json`. The procedure followed is
`.agents/skills/vce-gameplay-performance`, which states plainly that a software
renderer run, a boot frame or a UI FPS counter is not gameplay acceptance.

Workload: the Web-play surface `http://192.168.1.8:8091/offline`, the synthesized
GBA fixture `an3-synthetic-gba.gba` (32768 bytes, sha256
`94ca9e564f01d9871f84a831e7d28f6dc3ae8a0cf0b93d1bd7395b5a73ee6491` — recomputed
at run time and stored in the JSON), implicit rate 59.7Hz, 20s and 10s sampling,
Chromium from the repository's Playwright install, on the Intel AlderLake-S GT1
iGPU host.

| Metric | Result | Class |
| --- | --- | --- |
| Compositor frame pacing, 20s | 60.06fps, mean 16.7ms, p50 16.7ms, p90 16.7ms, p99 16.8ms, max 16.8ms | GOOD for this browser on this host |
| Late frames >25ms / dropped >33ms | 0 / 0 over 1202 frames | GOOD, same scope |
| Main-thread long tasks | 0 observed, 0ms total | GOOD, same scope |
| JS heap while playing | 18MB used of a 4192MB limit | GOOD, same scope |
| No-GPU vs GPU launch flags | **both** report `ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)), SwiftShader driver)` | GPU path **UNVERIFIED** |
| Emulated machine advances while displayed | yes: three captures 1s apart differ | GOOD |
| Emulated frame rate | **not established** (see below) | UNVERIFIED |
| Native (Linux/macOS/Windows), Android, Switch, physical phones | not measured on this host | UNVERIFIED |

Two limits matter more than the numbers.

**The GPU never engaged.** Chromium accepted `--use-gl=angle --use-angle=gl
--ignore-gpu-blocklist --enable-gpu-rasterization --enable-zero-copy` and still
reported SwiftShader, so the 60fps above is a software-rasterized compositor on a
machine that has an Intel iGPU and an accessible `/dev/dri/renderD128` (the
worker is in the `render` group and opens the node). Software pacing is a source
regression check, not gameplay acceptance, and it says nothing about the iGPU
path a real user gets.

**The emulated rate was not established, and no cause is claimed.** Two attempts
failed for method reasons, not product reasons. Rasterizing the whole canvas at
40x30 and hashing every seventh byte reported 0.7 changes per second — but the
fixture advances its counter by writing the low halfword of a register to a
single pixel, so downscaling averages the only changing pixel away; that number
measures the sampler, not the core. Reading that single pixel directly then
returned a constant 0 for 600 samples over 10s, which is equally consistent with
sampling the wrong canvas, with a WebGL drawing buffer that is not preserved
across the read, or with a stalled core. This probe cannot distinguish those, so
it establishes nothing about performance, and `EJS_emulator` exposes no `fps` or
frame counter in this build to fall back on.

A third probe (`perf-frames.mjs`) settles the weaker question — whether the
machine advances at all while it is displayed — without settling the rate. Three
Playwright element screenshots of the live canvas, one second apart, produce three
different images (sha256 `dc4ac1484aea8ede`, `36be377acbe714e4`, `9d7f775be114714b`,
1280x606 each): the emulated machine is executing and its output is being
presented. Reading the counter itself then failed for a known reason, not an
unknown one: the GBA's 240x160 image is letterboxed inside that 1280x606 canvas,
so canvas pixel (0,0) — and (1,0), and the centre — is black border, not pixel 0 of
the fixture's mode-3 frame buffer. The displayed-pixel rate therefore remains
unestablished.

What would settle it, in order: a headed Chromium on the iGPU with a GPU process
report showing ANGLE-on-Intel, and a fixture whose *entire* frame changes each
VBlank (or a read taken inside the frame callback with the buffer preserved), on
physical hardware for the native platforms. Until then, per-platform gameplay
performance stays UNVERIFIED.

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
