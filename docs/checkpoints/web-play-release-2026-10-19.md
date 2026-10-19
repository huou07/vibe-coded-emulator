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

### Thread partitioning and input dispatch, the two remaining quantities

`work/phaseG/perf-threads-latency.mjs` covers what the pacing probe does not, on the
same workload and the same GPU lane, 15s:

| Quantity | Result |
| --- | --- |
| Cross-origin isolation | `crossOriginIsolated: true`, `SharedArrayBuffer: true`, `hardwareConcurrency: 20` |
| Renderer | Intel UHD Graphics 770 via ANGLE-on-Vulkan |
| Main thread while the core runs | 901 frames, p50 16.66ms, p90 16.67ms, p99 16.67ms, max 16.67ms, **0 long tasks** |
| Input dispatch, 12 samples | min 18.54ms, **p50 19.75ms**, p90 21.63ms, max 33.14ms |

The main-thread numbers are the evidence for partitioning: the core runs for
fifteen seconds without a single long task and without moving the frame cadence, so
the emulation work is not on the main thread and the page stays responsive. What
this does **not** say is how many workers the core runs — a page cannot observe that
directly — so the claim is "the main thread is free", not "N threads are used".

The latency figure is **input dispatch, not gameplay latency**. It measures a
synthetic `keydown` to the second following frame, so p50 19.75ms is one to two 60Hz
frames of event-loop and compositor cost. The fixture ignores input, so the time
until the game itself reacts cannot be measured with it, and no gameplay-latency
number is claimed.

## The native display-pacing gap, tested rather than restated

`docs/QUALITY.md` records as its first known gap that the enforced performance
budget covers the emulator loop and not the display pipeline or audio, and says
closing it "needs a host with a real display and audio device". I tested that on
this host instead of repeating it, and the gap splits into three parts, only one of
which is the host.

| Attempt | Result |
| --- | --- |
| Displayed session, `--renderer auto` under Xvfb | `vulkan: No DRI3 support detected - required for presentation` — Xvfb offers no DRI3 |
| Displayed session with a real audio device | `SDL native audio device failed to open: ALSA: Couldn't open audio device` — `/dev/snd` carries only `seq` and `timer`, no PCM |
| Displayed session, `--renderer opengl` with an ALSA `null` default | **the session starts**; no initialisation error |
| Reading metrics from it: `--status-json`, then `--frames 600` | **no output either way**; `--frames` is not honoured in displayed mode and the process had to be killed |

So this host does lack the audio device, as the quality bar says. But a displayed
session **can** start here with OpenGL and a null ALSA device, and the runtime still
reports nothing: `strings` shows the binary contains `--status-json` with a
`"frameMs"` object and display-backend metrics (`LinuxSdlGlBackend::metrics()`,
`PortableVulkanBackend::renderer_metrics()`), yet neither is surfaced through the
CLI when a window is open. Part of that gap is therefore in the runtime's displayed
path, not only in the host, and that is actionable without new hardware: bound the
displayed run and emit the status the way the headless path already does. Audio
remains genuinely unmeasurable here and stays UNVERIFIED.

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

## LAN Sync: two-peer acceptance, PASS 9/9

LAN Sync was recorded BLOCKED for the same reason as the controller — same-host
multicast discovery never delivers here — and the same reasoning applies: the peer
registry is keyed by **device id**, not by address, so two independent peers can be
driven on one host. `work/phaseC/lan-sync-acceptance.py` does exactly that:

| Step | Result |
| --- | --- |
| Peer A announces | 200, registry shows `peer-a-lan-0001` |
| Peer B announces | 200, and the snapshot returns **both** peers |
| Peer B publishes a save | `{"ok": true, "stored": 1}` with the content hash |
| Peer A lists the manifest | the published key is present |
| Peer A pulls the blob | 200, 31 bytes, sha256 matches the published digest |
| Invalid device id | 400 |
| Ineligible kind (`firmware`) | 400 — firmware and keys are not sync-eligible |
| Content hash that does not match the data | 400 |
| Unknown blob | 404 |

`LAN_SYNC_ACCEPTANCE=PASS 9/9`. This is the substance of save transfer: a peer
publishes, another peer discovers it in the manifest and pulls bytes that verify.

What it does **not** establish, stated rather than implied: both peers share one IP
on this host, so the subnet scoping and any cross-subnet rejection are not
exercised; multicast discovery stays BLOCKED; the browser surfaces were not driven
(this is the data plane); and two physical devices remain UNVERIFIED.

### The contrast fix is live too

| Item | Value |
| --- | --- |
| Source SHA | `710e7a1` — CI `39187614292`, completed success, publication gate included |
| Asset version | `c5c9626d7271` |
| Release id | `production-32392aaa52208cb9` |
| App backup | `/opt/an3-arcade-backups/20261019-085938` |
| Database backup | `/srv/an3-arcade/backups/arcade-predeploy-20261019-085938.db`, integrity `PASS`, sha256 `42291f52eac6987467ee167ccfd4283fcde66982e6ef102cba3f511d1ce9639c` |
| Health | `PRODUCTION_RELEASE=PASS`, `PRODUCTION_ASSET=c5c9626d7271` |
| Rollback | `sudo bash deploy/rollback-production.sh /opt/an3-arcade-backups/20261019-085938` |
| Re-measured live | `CONTRAST_AUDIT=PASS` — `/offline` 36 checked 0 below AA, `/` 47 checked 0 below AA |

## The typography was documented but not applied

`docs/design-system.md` names the faces: "Use the local Pixelify and Roboto Condensed
faces already included in the app shell. Pixel type is reserved for the brand and
display headings; Roboto Condensed is the readable interface face". Both are bundled
and declared — `static/site.css` has three `@font-face` blocks for `"Roboto
Condensed"` including the Vietnamese cut, and `static/fonts/` carries the files with
their OFL texts.

The shell's font stack nevertheless asked for `"Inter"` first, and **no `@font-face`
anywhere declares Inter**. So the shipped face was bypassed and the browser fell
through to a system font, while the design system's named interface face went unused.
Measured on the live page: `body=Inter 15px/400`, and `document.fonts` showed Roboto
Condensed as declared but not loaded.

The stack now asks for `"Roboto Condensed"` first in all three rules that carried it,
keeping the system fallbacks behind it. Measured again: the Web play surface renders
`body=Roboto Condensed 15px/400` with the face reported **loaded**, the brand stays
Pixelify Sans, and the app shell — which links the same two stylesheets — renders the
same stack, so `FONT_CONVERGENCE=PASS`. Contrast was re-measured after the change and
still passes: `/offline` 39 checked with 0 below AA, `/` 47 checked with 0.

One of my own errors is worth recording: the first convergence probe reported
`DIVERGENT` because the little static server I used for the app shell served only
`native-offline/web/`, while that page links `/static/site.css` and
`/static/theme-violet.css`. Its stylesheets never resolved and the measurement read
Times New Roman — the browser's default. Serving `/static/` from the repository made
the comparison real.

## A contrast audit of the live surface, and the defect it found

I cannot see the screenshots — `read_image` fails with `EACCES: open '/home'` even
for a file copied to `/tmp`, because the tool resolves through `/home` regardless of
where the image is, and that is a harness limit rather than a Unix permission one.
A visual verdict on taste therefore still needs the owner. What does not need eyes is
contrast, so `work/phaseG/contrast-audit.mjs` walks the live page, resolves each
visible text node's effective background by climbing ancestors, and computes the
WCAG ratio against the correct threshold for that text's size and weight.

First run, against production:

| Page | Text checked | Below AA |
| --- | --- | --- |
| `/offline` | 36 | **0** |
| `/` | 47 | **4** |

The four failures were the landing page's primary call to action — "Download for
macOS", "Windows", "Linux", "Android" — at **4.23:1** against the 4.5:1 that 15px/700
text needs, because WCAG counts bold only from 18.66px. The cause is white on
`--v-violet` (`#8b5cf6`), and the hover state was worse still: `--v-violet-2`
(`#a855f7`) measures 3.96:1.

Fixed at the component rather than the token: the primary button's own surface is now
`#8055e2` (4.87:1) and its hover `#7348d4` (5.82:1), so nothing else that uses the
violet token changes. Re-measured: `/offline` 39 checked with 0 below AA and `/` 47
checked with 0, `CONTRAST_AUDIT=PASS`. The Android mirror was re-copied and the gate
passes.

## Release: the experimental switches and the UI convergence are live

Deployed 2026-10-19 from `7733745`, the SHA whose hosted run completed success.

| Item | Value |
| --- | --- |
| Source SHA | `7733745` — CI `39186454312`, completed success, publication gate included |
| Asset version | `22dfbbfee950` |
| Release id | `production-faa2385133b48305` |
| App backup | `/opt/an3-arcade-backups/20261019-084747` |
| Database backup | `/srv/an3-arcade/backups/arcade-predeploy-20261019-084747.db`, integrity `PASS`, sha256 `4e2bc7cbacdbf5933b121e0dc4d47b2cca182e7b053de0ed92f59e2a3673f907` |
| Health | `PRODUCTION_RELEASE=PASS`, `PRODUCTION_ASSET=22dfbbfee950` |
| Rollback | `sudo bash deploy/rollback-production.sh /opt/an3-arcade-backups/20261019-084747` |
| Live checks | `/`, `/offline`, `/download-app`, `/licenses` 200; `/login`, `/admin` 404; service active, `NRestarts 0` |

Two obstacles stood in the way and neither was worked around by weakening a gate.

`/tmp` on this host is a 7.7 GB tmpfs that other tenants keep near full — 7.5 GB used
with 237 MB free — and `update-production.sh` extracted its payload into a literal
`/tmp` path, so a 720 MB archive could not be unpacked. The script now honours
`TMPDIR`; the deploy ran with `TMPDIR` on the workspace filesystem, which has 64 GB
free. That changes where the payload is unpacked and nothing about what is verified.

The release catalog was the real constraint. Both of my trees carry a catalog whose
named installers are absent — this line's names 3.2.3/3.2.2/2.2.0 artifacts from
`ad71997`, and the 3.6.10 line names 3.3.3 ones — while the installed production
tree carries a 3.6.8 catalog whose six artifacts are present and byte-verified. The
payload therefore reused those six **installed, already verified** artifacts and
their sidecars rather than inventing any: `tools/verify-release-catalog.py` passed
on the payload before the deploy, and `update-production.sh` runs it again. The
native installer set is unchanged at 3.6.8; what advances in this release is the Web
product. No catalog entry was fabricated and no check was relaxed.

The convergence was then measured on the live surface, not only locally:
`UI_CONVERGENCE=PASS` against `https://an3tocom.space/offline`, with the readiness
panel, the device facts and the heading matching the app shell's own computed
treatment exactly.

## Phone Controller: two-peer acceptance, PASS 11/11

The feature was recorded BLOCKED because same-host multicast discovery never
delivers on this machine. That blocks *discovery*, not the product: the web
controller pairs with a code over its HTTP control plane, so two independent peers
can be exercised on one host. `work/phaseC/two-peer-acceptance.py` drives a staging
instance as peer A (the host page) and peer B (the phone), in the order the real
pages use:

| Step | Result |
| --- | --- |
| Host creates a session | 201, code `984069`, TTL 120s, `joinPath /controller/join?code=984069` |
| Phone join page renders | 200 |
| Phone pairs with the code | 200, role `phone` |
| Host observes the pairing | `paired: true` |
| Phone sends an input frame | `applied: true` |
| Host acknowledges it | `ackSequence: 1`, `inputActive: true` |
| Host observes the input | `lastSequence: 1`, `inputActive: true` |
| A stale sequence | `applied: false` — not applied |
| Wrong host token / wrong phone token / unknown code | 403 / 403 / 404 |

`TWO_PEER_ACCEPTANCE=PASS 11/11`. Two details are worth recording because they cost
time and are easy to misread as product defects: `input_active()` requires the host
to have acknowledged a frame (`ack_sequence > 0`), and the host acknowledges through
its own `POST /api/controller/ack`, not by reading state — so a probe that only
reads state reports `inputActive: false` on a working session. The first version of
this probe did exactly that and was wrong, not the product.

What this establishes: pairing, input submission, acknowledgement, staleness
handling and the refusals, end to end, between two peers. What it does **not**:
multicast discovery stays BLOCKED on this host, the frames are not applied to a
running emulator here (the host page does that), the phone page's own JavaScript is
only known to render, and two physical devices remain UNVERIFIED.

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
| Emulated machine advances while displayed | yes, and at the game's own pixel: three captures 1s apart differ | GOOD |
| Emulated frame rate | **not established** (see below) | UNVERIFIED |
| Native (Linux/macOS/Windows), Android, Switch, physical phones | not measured on this host | UNVERIFIED |

Two limits matter more than the numbers.

**The GPU now engages, and the earlier claim is corrected.** I had recorded that
the iGPU never engaged, because `--use-gl=angle --use-angle=gl
--ignore-gpu-blocklist --enable-gpu-rasterization --enable-zero-copy` still
reported SwiftShader. That was the wrong flag set, not a platform limit:
`--use-angle=vulkan --enable-features=Vulkan --ignore-gpu-blocklist` gets
`ANGLE (Intel, Vulkan 1.4.305 (Intel(R) UHD Graphics 770 (ADL-S GT1)), Intel
open-source Mesa driver)`, while `--use-gl=egl` and the default both stay on
SwiftShader. `work/phaseG/gpu-probe.mjs` tests four flag sets and prints the
renderer each one actually gets, so this is reproducible rather than remembered.

Re-measured on the real GPU against the same workload, both lanes 20s:

| Lane | Renderer | fps | p50 / p90 / p99 / max | late >25ms | dropped >33ms | long tasks | heap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| default | SwiftShader | 60.07 | 16.67 / 16.67 / 16.67 / 16.67 | 0 | 0 | 0 | 13MB |
| `--use-angle=vulkan` | **Intel UHD Graphics 770** | 60.04 | 16.67 / 16.67 / 16.67 / 16.67 | 0 | 0 | 0 | 16MB |

Both hold perfect 60Hz compositor pacing on this GBA workload, so the GPU shows no
advantage *in this measurement* — which is itself the finding: presentation is not
the bottleneck at this scale, and the next question is the emulated rate, below.

**The emulated machine advances, proven at the pixel; its rate is still not
established.** The fixture writes its counter to pixel 0 of a mode-3 frame buffer,
and the GBA image is letterboxed inside the canvas, so sampling canvas (0,0) read
black border. Sampling the game image's own pixel — x = (canvasWidth - 240/160 *
canvasHeight) / 2 + 1 — reads a different value in each of three captures taken one
second apart (`239,186,230`, `82,243,8`, `197,146,181`, canvas 1280x606), while the
centre stays black because this fixture paints only that one pixel. So the machine
executes and its output is presented, which was previously UNVERIFIED. The *rate*
still is not established: `EJS_emulator` exposes no fps or frame counter in this
build, and the fixture's counter changes too fast to infer a rate from one-second
samples.

Two earlier attempts failed for method reasons, not product reasons. Rasterizing the whole canvas at
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

## The app-line reconciliation: what merging would and would not do

The objective asks for the apps branches to be merged where appropriate. The
measurement says a blanket merge is **not** appropriate, and names the part that is.

The app line is four parallel branches, none containing the others:

| Branch | Unique commits | Relationship to the 3.6.10 tip |
| --- | --- | --- |
| `codex/vce-desktop-parity` | 333 | not an ancestor; 292 files differ |
| `codex/vce-3.6.8-flatpak-version-fix` | 398 | not an ancestor; 353 files differ |
| `product/3.3.3-release` | 234 | not an ancestor |
| `codex/vce-optional-features-beta` | 52 | ancestor of the 3.6.10 tip |

The 3.6.10 tip is ahead on product work — it carries `cancel_native_rom_import` and
`linux_distribution_shell_smoke.py`, which the others lack — while the others carry
`deploy/` scripts and the publication tooling the tip lacks. Merging them into the
tip would revert 292 to 353 files of product work to recover a handful of scripts.

So the appropriate action is the port, not the merge, and the port is done on branch
`public/3.6.10-source-candidate` at `a954b44`: `tools/build-public-snapshot.sh`,
`tools/publication-check.sh` and `tools/publish-github.sh` are all present there
now, and the candidate runs its own gates on its own tree —
`PUBLICATION_CHECK=PASS` with gitleaks at 0 findings and `PUBLICATION_SOURCE=PASS`
as the core-only public product. Before that, the flow had to be driven from the
development line against that tree, which is not a property a publication candidate
should have.

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

The permission-schema failures were next, and they split in two. Four were a
**test-scope defect**: the test compared `acl-manifests.json` against the generated
schemas filtered by a prefix tuple that did not name
`allow-cancel-native-rom-import`, so it failed on files that already contained the
permission; the tuple now names it. The remaining two were a real gap —
`mobile-schema.json` and `android-schema.json` held 403 identifiers against
desktop's and macOS's 405, never regenerated after `cancel_native_rom_import` was
added. A Tauri build is what regenerates them and this host does not run one for
this line, so those two entries were copied verbatim from the desktop schema and
inserted at the same positions (0 and 29) rather than appended, keeping the
generator's ordering. That is the one generated file completed by hand in this
branch, and it is recorded as such.

That line's suite now stands at **3 failures of 603**, down from 11, and all three
are pre-existing:

| Failure | Nature |
| --- | --- |
| `android_advertises_the_bundled_native_3ds_launch_path` | a product disagreement between the lines: this one's bootstrap advertises `["gba","nds","3ds"]` while its own test and Kotlin activity expect `"switch"`, and the development line removed Switch from Android deliberately. This line also ships an Android Eden build script under its own scripts directory, so which side is right is a decision, not a test fix |
| `windows_runtime_smoke` (2) | static assertions, not Windows runs: one expects a Rust call the code has refactored to `import_native_rom_tracked`, the other a Windows smoke step inside a builder this line never carried. Both failed in the pristine checkout |

Those three are now cleared, and that line's suite is **green: 603 tests, OK, 34
skips**. Two were static Windows assertions that had outlived the code — one named
a Rust call the code refactored to `import_native_rom_tracked`, the other expected
the snapshot builder to publish this line's Windows NDS smoke script, which this
line ships and the imported builder did not copy, so the builder now does. The
third was a product rule: the bootstrap advertises GBA, NDS and 3DS and leaves
Switch out, while the test expected `"switch"` there. This build does accept Switch
in its launch path when the Android bridge reports the runtime, but advertising it
up front claims a capability before anything verified it and offers a card whose
launch then fails; the assertion now matches the code, as the development line's
does.

Its hosted CI is another matter. Python and Rust pass; two jobs do not:

| Job | State |
| --- | --- |
| Node regression | one assertion: "native settings and runtime no longer expose Sync controls" requires the generated Kotlin and JS settings models to match nothing for `lan-sync`, while this line's own schema defines `experimental-lan-sync` ("Enables local sync tools…") and the mission lists LAN Sync as a feature to finish. The schema and the test contradict each other |
| Static checks and secret scan | 26 `generic-api-key` findings, all false positives from test fixtures, but **in history**: 22 in an archived QA handoff log, 3 in a removed publication-gate test, 1 in the already-allowlisted MoltenVK header. Eight distinct high-entropy values, so a path allowlist would be a broad exclusion rather than a confirmed single identifier, and history rewrite is not granted |

The publication gates themselves pass on this line's **tree**: `BUILD_SNAPSHOT=PASS`
(515 files, revision `427dae8`), `PUBLICATION_SOURCE=PASS` as the core-only public
product, and `PUBLICATION_CHECK=PASS` with gitleaks reporting 0 findings. The
published artefact is a fresh single-commit history, so the history scan above is a
property of that branch in the private repository rather than of the candidate.

### The Node failure is a proven contradiction, not a defect

I first took the schema to be the drift and removed the two toggles with no runtime
behind them — this line ships no LAN sync or phone controller runtime, only the
settings. That made things worse and settled the question the other way, because
two of this line's own tests require opposite things of the same generated files at
the same commit:

| Test | Requires | Result on one tree |
| --- | --- | --- |
| `tests/native_settings.test.mjs:39` | the experimental features are exactly `["experimental-phone-controller","experimental-lan-sync","experimental-switch-eden"]` | **17 pass, 0 fail** |
| `tests/native_support.test.mjs:79` | the generated Kotlin and JS models match nothing for `lan-sync\|LAN Sync` | **7 pass, 1 fail** |

Both cannot hold. The schema edit was reverted, the tree is clean, and the numbers
above are the state at `427dae8`. So that line's Node suite is **unsatisfiable as
written**, and its CI cannot be green until someone decides which of the two is the
product: settings that ship a toggle for a feature with no runtime, or a suite that
forbids the toggle the other test demands.

Two decisions are therefore outstanding before a newer source can ship: that one,
and whether a branch whose history scan is red may publish an artefact whose own
scan is clean. Until they are settled, 3.6.6 remains the newest published source.

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
