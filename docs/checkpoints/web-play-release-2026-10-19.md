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

## Is the Web shell consistent with the installed app's shell?

Measured, because "consistent" had to be turned into something checkable. The
answer is that the two shells already share the documented palette, and the gap is
in how they declare it rather than in what they render.

| Measurement | Web shell (`static/theme-violet.css`) | App shell (`native.css`) |
| --- | --- | --- |
| CSS custom properties declared | **55** | **0** |
| Distinct hex colours | 20 | 16 |
| Colours used by both | — | **14** |
| Unique to this shell | 6 | 2 |
| Documented `--ui-*` role values present | 10 of 10 | **9 of 10** (`--ui-danger #f87171` absent) |

So the app shell renders the same violet values — `#07060c`, `#131020`, `#191532`,
`#282238`, `#f3f1fa`, `#a5a0b6`, `#a855f7`, `#8b5cf6`, `#c4b5fd` all appear in
`native.css` — but hardcoded rather than exposed as the token vocabulary the design
system names. That is a maintainability and verifiability gap, not a visual
mismatch, and it means "the Web matches the app" cannot be asserted by comparing
tokens; only the palette can be compared that way.

What remains for a human: hierarchy, spacing rhythm, typography and legibility.
The Web shell's interface face is Inter with Pixelify Sans for display, set by the
theme itself, while the design-system text describes Pixelify and Roboto Condensed
as the app shell's faces; whether those should converge is a design decision, not a
measurement. This session cannot read images (`EACCES` traversing `/home`), so the
visual verdict stays with the owner, and the captures presented alongside this
tracker are the material for it.

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

## Browser 3DS runs on the public production URL

Earlier in this tracker I recorded that browser 3DS could not run on production
because the page was opened as `http://192.168.1.8:8091` — a LAN IP over plain
HTTP, which is not a secure context, so the threaded core could not obtain
`SharedArrayBuffer`. That conclusion was correct about that URL and wrong about
the product: production is also served through a Cloudflare Tunnel over HTTPS, and
the tunnel is the live public route.

Verified on the public URL, not inferred:

| Check | Result |
| --- | --- |
| `https://an3tocom.space/health` | 200, `environment production`, `asset_version 3877f6a56f94` — the same release the LAN URL serves |
| `https://an3tocom.space/offline` | 200 |
| COOP/COEP through the tunnel | `cross-origin-opener-policy: same-origin`, `cross-origin-embedder-policy: require-corp`, `cross-origin-resource-policy: same-origin` |
| `/login`, `/register`, `/admin` on the public URL | 404 |
| `isSecureContext` in the browser | **true** |
| **3DS import and launch** | **`ready`, two canvases, loading "Ready", no player notice, no page errors** |

The 3DS card correctly renders enabled with no HTTPS note on this origin, because
the note is scoped to insecure origins. The fixture is the lawful
devkitPro/3ds-hbmenu v2.4.3 `boot.3dsx` (383,400 bytes), kept in the git-ignored
`work/fixtures/` and never committed.

### NDS closes too, with a lawful fixture

NDS was UNVERIFIED for want of a ROM. `devkitPro/nds-hb-menu` v0.11.0 publishes
`hbmenu-0.11.0.zip`, and `hbmenu/BOOT.NDS` from it is the NDS counterpart of the
3DS fixture used above: 299,008 bytes, sha256
`95f6561daa9d61402d39a2622ce19e7a887f2c8ba24fdb487753db3fcc357d24`, lawful
homebrew, kept in the git-ignored `work/fixtures/` and never committed.

Run on `https://an3tocom.space/offline` with `system=nds`: import succeeds, the
launch is enabled, and the player reaches **`ready` with two canvases, loading
"Ready", no player notice and no page errors**.

Two honest limits on that result. The probe reported a null stored size for the
NDS record while it reads 32768 for GBA — the NDS path keeps its payload in a
different field (the invariants have NDS serving the original ZIP where
appropriate) and the probe does not read it, so that number is a probe gap, not a
storage defect; the launch reaching ready is what shows the ROM was available. And
the page logs two blocked requests for `static.cloudflareinsights.com`, which the
Cloudflare Tunnel injects and our own CSP refuses; it is Cloudflare's analytics
beacon, not a product asset, and it does not affect play.

So the Web-play requirement is met on the public product for **GBA**, **NDS** and **3DS**.
**NDS remains UNVERIFIED for real boot**: it needs a lawful NDS ROM and this host
has neither one nor a toolchain to build one (`arm-none-eabi-gcc` is absent and
there is no devkitPro), and the repository ships no synthetic NDS generator.

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

## App-branch evaluation (objective: evaluate and merge where appropriate)

Every branch was enumerated, local and remote, after `git fetch --all --prune`.
The remote has 27 heads, several of which were not in this checkout at all:
`codex/vce-3.6.10-windows-beta-review`, `codex/vce-3.6.7-ci-candidate`,
`codex/vce-3.6.8-windows-p0-review`, and a whole `core-only/*` family.

**The two lines are unrelated histories.** `git merge-base HEAD origin/main` is
empty; `48fb769`, `fea3fa2` and `d389e22` are separate root commits by different
authors (`huou07` vs `meomeo`). A merge would need
`--allow-unrelated-histories`.

**They are not two halves of one product.** The apparent "62 files the dev branch
lacks" is mostly the app line organising the same capabilities differently, and
two of those differences are contradictory implementations, not gaps:

| Capability | Development branch | App line |
| --- | --- | --- |
| Switch companion | `src-tauri/src/switch_companion.rs`, 9 `switch_companion_*.toml` permissions, `prepare-switch-companion.mjs`, vendored macOS binary | `hosted_frame.rs`, `hosted_frame_consumer.{h,mm}`, 7 `switch_companion_hosted_frame*.toml`, `build-*-eden-companion.*` |
| Core licence texts | Android assets with a `manifest.json`, plus `vendor/` copies | its own `native-core-licenses` directory at the app root |

So "merge the apps branches into the development branch" is the wrong operation:
it would put two Switch implementations in one tree and force a design choice
inside a merge commit. The defensible reconciliation is by **version and
packaging**, keeping one implementation per capability.

**Within the app line itself**, the branches do share `48fb769`, so those merges
are ordinary. Dry runs, on a scratch worktree from the 3.6.10 tip:

| Merge | Conflicts | Files added cleanly |
| --- | --- | --- |
| `vce-3.6.8-flatpak-version-fix` (398 unique) | 22 | 273 |
| `vce-desktop-parity` (333 unique) | 24 | 201 |

The conflicts are concentrated and classifiable: `package.json` /
`package-lock.json`, `Cargo.toml` / `Cargo.lock`, the flatpak manifests and
metainfo, `native-release.yml` / `native-build.yml`, `PRODUCT_STATE.md`, that line's `building.md`, plus three real source files — `sdl_gl_backend.cpp`,
`native-settings-model.json` — and the Android mirror `assets/index.html`. Policy
for a real merge: take the higher version and the newer Azahar pin, union the
workflows and docs, regenerate the lockfiles, resolve the two source files by
reading both sides, and rebuild the mirror with `prepare-web.mjs` rather than by
hand. Then a Linux build and the native guards before it can be called a release
candidate. That is a bounded task and it is not started.

## The GitHub publication ran, 2026-10-19 03:16 +07

`tools/publish-github.sh --confirm --adopt-remote --prebuilt --snapshot <candidate>`
published the core-only source snapshot to `huou07/vibe-coded-emulator`.

| Field | Value |
| --- | --- |
| Candidate | built from `core-only/3.6.6-publication-candidate` at `4d9c28c`, 507 files, 14MB |
| Public `main` head | `77a0250` "Merge the existing remote commit into the initial public release" |
| Public `app.py` | 142,580 bytes, blob `eae4553c63b1`, **no `/login` route** — the account-free product |
| Gates before push | `PUBLICATION_CHECK=PASS` (gitleaks 0 findings, patterns clean) and `PUBLICATION_SOURCE=PASS` (RG-155 core-only) |
| Hosted CI on that SHA | success |
| Repository | public, default branch `main` |
| Branch protection | `required_checks=["test"]`, `strict=true`, 0 required reviews |
| Security settings | secret scanning + push protection, Dependabot alerts, Dependabot security updates, private vulnerability reporting — all enabled |

Two operational facts, both learned the hard way in this round:

- `publish-github.sh` **rebuilds** the snapshot into `--snapshot` unless `--prebuilt`
  is given. The first invocation omitted it and overwrote the core-only candidate
  directory with a build of the development tree; the next invocation then
  correctly refused that directory. The gate caught both states, and the candidate
  was rebuilt into a fresh directory before publishing. Pass `--prebuilt` with a
  candidate that has already been gated.
- The publication enables **branch protection on `main` requiring a PR and the
  `test` check**. That is a lasting change to how this repository is updated, and
  it is now in force.

## The publication gate and command (superseded by the section above)

Branch `core-only/3.6.6-publication-candidate` at `4d9c28c` now satisfies every
gate the release contract names, on the same SHA:

| Gate | Result |
| --- | --- |
| Hosted exact-SHA CI (`core-only/**` triggers it) | **success** |
| `BUILD_SNAPSHOT` | **PASS** — 507 files, 14MB, revision `4d9c28c` |
| `PUBLICATION_SOURCE` (RG-155 core-only product) | **PASS** |
| `PUBLICATION_CHECK` (fail-closed) | **PASS** — gitleaks 0 findings, patterns clean |
| That line's own Python suite | 591 tests, **OK**, 34 skips |

Two faults in my own refresh had to be corrected first, and both were the same
mistake: importing development-line files into a line that has its own contracts.
The gitleaks config import broke `test_real_config_allowlist_targets_the_localstorage_key`
with an `IndexError`, and the `.env.example` import broke
`test_account_login_and_cloud_runtime_are_absent` because it documents
`AN3_AUTH_PEPPER`. That line already covered both cases itself; the imports were
reverted and only the genuinely missing tooling was added.

**The publication has not been run.** `tools/publish-github.sh --confirm` was read
rather than executed, and it is a larger act than it looks: it initialises a fresh
repository in the snapshot, commits the whole tree as one public commit, requires
`--adopt-remote` because the public `main` already exists, merges with `-X ours` so
the snapshot wins, pushes to `main`, and then enables secret scanning, Dependabot
and **branch protection on main requiring a PR and CI**. Nothing about that is
force-pushed or destructive, but it replaces the public tree and changes the
repository's future workflow, so it belongs at the start of a round with budget to
verify the result rather than at the end of one.

It also needs one owner decision the repository cannot make: the candidate is
**3.6.6**, which is the newest app version that passes CI, while the app line's tip
is 3.6.10 and its CI is **red** (Python, Node and a history secret scan all fail on
`18f74f0`). Publishing 3.6.6 moves the public source from 3.3.3 to 3.6.6 and is
honest about what passed; publishing 3.6.10 would first require that line to go
green, which is the app-line merge task.

## The core-only line now publishes (both gates pass)

The refresh above took the core-only candidate from "cannot build a snapshot" to
both publication gates green, at revision `72dfff4`, 507 files, 14 MB:

```
BUILD_SNAPSHOT=PASS work/co361/work/snap4
PUBLICATION_SOURCE=PASS core-only public product: work/co361/work/snap4
candidate=work/co361/work/snap4
gitleaks: 0 findings
personal-data and infra patterns: clean
PUBLICATION_CHECK=PASS
```

Four gaps had to close, and two of them were defects in the toolchain rather than
in the candidate:

| Gap | Resolution |
| --- | --- |
| `tools/publication` held only `.gitleaks.toml` | templates refreshed from the development line, with `disk-preflight.ps1` and the builder |
| Eight files carried `~/<REDACTED_PATH>`, which the builder's own post-scan rejects | replaced with `/opt/developer/ROMs/game.gba`, which also restores the meaning of the test named "username in paths is removed" |
| A PEM-header fixture in that line's bug-report test matched the checker's secret pattern | assembled at run time, identical input to the scrubber, 20 tests still pass |
| The `an3-presentation-renderer-v1` allowlist named only `static/player-runtime.js` | the existing path-scoped entry now also names the test that reproduces that identifier |

The first two are worth naming as toolchain faults: a sanitizer that rewrites
`/Users/<name>/…` into `~/<REDACTED_PATH>` and a post-scan that then rejects every
`~/` cannot both be right, and the core-only line sat on the wrong side of that
contradiction. The allowlist change is the one that most needs care — it is a
secret gate — so it extends an existing identifier-scoped entry to a second path
instead of adding an exclusion, and the config comment now states that rule.

Branch `core-only/3.6.6-publication-candidate` carries all of it and is pushed.

## The core-only line exists, and it is stale

`tools/publish-github.sh --check-candidate` tells a refused candidate to "export
the snapshot from the core-only line (a `core-only/*` branch)". That line **does**
exist on the remote — `core-only/3.6.1-candidate-20261009` (app 3.6.6) is the
newest, and `3.6.0`, `3.4.0`, `3.3.13`, `3.3.12`, `acceptance` precede it. All are
genuinely core-only: `app.py` is 142,570 bytes and defines no `/login` route.

Building a snapshot from the newest one fails, and each failure is a real gap
rather than a tooling quirk:

1. `missing upstream core license: mGBA-MPL-2.0.txt` — and
   `melonDS-DS-GPL-3.0-or-later.txt` with it. `native-offline/vendor/libretro/macos-arm64/`
   tracks only `manifest.json`; `git ls-files -t` returns nothing for either text,
   so they are absent from the tree, not sparse in a worktree. A GPL source
   snapshot shipping the cores' build tooling without their licence texts is not
   publishable. Both are now tracked on branch
   `core-only/3.6.6-publication-candidate`, which fixes that one gap.
2. `missing build helper: tools/disk-preflight.ps1` — the core-only line does not
   carry it.
3. `cp: cannot stat 'tools/publication/docs/.'` — the core-only line does not
   carry the publication templates the current builder reads.

So the core-only line predates the current publication tooling. Refreshing it is
the prerequisite for any GitHub source publication and is not started; the branch
above carries only the licence fix.

## Why 3.6.6 and not 3.6.10: that line has never been green

The app line's tip is 3.6.10, and publishing it would be the better release. It
cannot be published, and the reason is not the publication tooling.

A **pristine checkout** of `origin/codex/vce-3.6.10-windows-beta-review` at
`e49ca9d`, with nothing of mine applied, fails its own suite: **603 tests, 10
failures and 2 errors**, 34 skips. The failures are its own:

| Failure | Class |
| --- | --- |
| `native_release_version_sources_are_consistent` | version sources disagree: `{'3.6.10', '3.6.9'}` |
| `generated_android_about_matches_the_package_version` | the packaged shell still says `data-app-version="3.6.9"` |
| `flatpak_sources_track_the_desktop_version` | the manifest still names `vibecodedemulator-3.6.9-linux-amd64.deb` |
| `generated_tauri_permission_schemas_match_active_commands` (4 schemas) | generated schemas are stale |
| `packaged_android_web_assets_have_no_phone_controller_files` | phone-controller files left in the packaged assets |
| `android_advertises_the_bundled_native_3ds_launch_path` | assertion and code disagree |
| `windows_runtime_smoke` (2) | Windows-only |

So the 3.6.10 bump was incomplete: `package.json` says 3.6.10 while the generated
artefacts still say 3.6.9. `native-offline/scripts/prepare-web.mjs` is the
generator that injects the canonical version ("so the About panel can never drift
from the real build"), but it needs an environment this session did not reproduce,
and hand-editing generated files would defeat the point of having the generator.
### The root cause, and the failures this round removed

The generated artefacts were stuck at 3.6.9 because that line's asset pipeline
**could not run at all**, and the cause was upstream drift rather than anything in
the line. `native-offline/scripts/prepare-web.mjs` fetches the EmulatorJS runtime
and refuses any byte that disagrees with
`native-offline/shared/web-runtime-lock.json` — "refusing an implicit core/runtime
update". The `stable` channel still matches, but `latest/data-v2` has moved:

| Asset | Locked | Live channel now |
| --- | --- | --- |
| `latest/data-v2/loader.js` | `f1650e3dd703…` | `24c682b785d6…` |
| `latest/data-v2/emulator.min.js` | `36b8bfc399a5…` | `d95450a058e2…` |

Every run aborted, so the About panel, the Android mirror and the flatpak metadata
kept the old version. The locked bytes are exactly what this repository already
vendors on the development line — the two lines' locks agree in all 22 entries —
so pointing the generator at that vendored tree
(`AN3_OFFLINE_RUNTIME_SOURCE` at a static server over the vendored `emulatorjs`
directory) lets `prepare-web` complete and regenerate the assets at 3.6.10.

Branch `public/3.6.10-source-candidate` now carries that regeneration plus the
version the bump had missed: `package-lock.json` regenerated with
`npm install --package-lock-only`, the flatpak manifest naming the 3.6.10 DEB, and
the metainfo release at 3.6.10 dated 2026-10-11, the bump's own date. That line's
suite goes from **11 failures to 7 of 603**.

The seven that remain are still its own: the four generated Tauri permission
schemas (generated by a Tauri build, which this host does not run for that line),
the Android 3DS launch assertion, and the two Windows-only smoke tests. Until they
are resolved, 3.6.6 remains the newest publishable source.

Branch `public/3.6.10-source-candidate` carries only the fixes to my own damage:
the development line's gitleaks config and `.env.example`, which broke three tests
here, are reverted to this line's own files, and the tooling this line genuinely
lacked (templates, `disk-preflight.ps1`, the builder) stays. It is pushed and
clean.

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
