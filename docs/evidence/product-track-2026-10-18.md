# Product track 2026-10-18 — release record

Recorded: 2026-10-18 by worker `dsh-worker` on the Debian x86_64 host. This is the
acceptance and release record for the 2026-10-18 owner instruction
([`docs/prompts/VCE-PRODUCT-2026-10-18.md`](../prompts/VCE-PRODUCT-2026-10-18.md)).
Per-feature detail lives in the feature pages and their trackers; this file is the
cross-workstream record and the release state, including what was **not**
published and why.

Status words are the repository's: `GOOD` (the named live check is current),
`UNVERIFIED` (no live check), `BLOCKED` (the check cannot run here). A skip is
never `GOOD`.

## Source identity

| Field | Value |
| --- | --- |
| Branch | `feature/semantic-ui-inspection` |
| Head (workstreams) | `32b5f191827b89c4f9263f95e7dc40089b6535f5` |
| Head (this record) | `29a3a00`; its hosted run [39143945163](https://github.com/huou07/vibe-coded-emulator/actions/runs/39143945163) is green, and the only change from the workstream head is this file and the docs index |
| Tree | clean (`git status --porcelain` empty) before and after the release build |
| Baseline when this track started | `c2fcc881467e56ef7edcc4fc4e0db3dbc24f6cd3` |

## Workstreams and their hosted CI

Every workstream commit's exact SHA has a green hosted `verify` run
(`project-verify`, `browser-runtime`, `publication-gate`, `release-gate`):

| Phase | Commit | Hosted run |
| --- | --- | --- |
| A — UI/UX baseline (Web shell, then native `Devices`) | `a660015`, `858f7e5` | [39136825935](https://github.com/huou07/vibe-coded-emulator/actions/runs/39136825935) |
| B — browser 3DS playable | `4b34f62` | [39138535973](https://github.com/huou07/vibe-coded-emulator/actions/runs/39138535973) |
| C — LAN Sync and Phone Controller | `de825c3` | [39141439015](https://github.com/huou07/vibe-coded-emulator/actions/runs/39141439015) |
| D — Switch platform matrix | `bfde47e` | [39141965380](https://github.com/huou07/vibe-coded-emulator/actions/runs/39141965380) |
| E — Android AVD lane | `32b5f19` | [39143321181](https://github.com/huou07/vibe-coded-emulator/actions/runs/39143321181) |

Hosted evidence for `32b5f191…` recorded with `tools/record-hosted-evidence.sh
verify` into `.hub/hosted-evidence.json` (run `39143321181`, conclusion
`success`).

## Acceptance per claimed surface

| Surface | Result | Where the evidence is |
| --- | --- | --- |
| Web shell navigation and offline recovery | `GOOD` | browser lane 2/2 pass, `tests.test_rendered_ui_accessibility` 8 pass, probe over eight routes; `docs/checkpoints/ui-ux-baseline.md` |
| Native (`Devices` destination, About version) | `GOOD` on the packaged Linux shell | Settings 3 viewport-heights → 1, Devices = 2, Switch row hidden, About reports 3.2.5; `docs/checkpoints/ui-ux-baseline.md` |
| Browser 3DS presents frames | `GOOD` on Chromium/Debian x86_64 with a lawful fixture | `THREAD_POOL_READY`, first frame at 1836 ms, three captures with 2795–3681 distinct colours; `docs/features/web-3ds.md`, RG-160 |
| LAN Sync | `BLOCKED` | multicast is not delivered to a same-host listener on this host (raw-socket reproduction); `docs/checkpoints/direct-lan-controller.md` |
| Phone Controller | `BLOCKED` for pairing, `GOOD` for the failure path | same; plus the join-failure text fix |
| Switch (macOS) | `UNVERIFIED` here | the macOS builder's recorded run only; `docs/checkpoints/eden-native-integration.md` |
| Switch (Linux/Windows/Android) | `UNVERIFIED`, not advertised | matrix recorded; no companion built |
| Android install and library → import → play | `GOOD` on the VCE AVD | `vce-api36`, recorded APK; `docs/features/android.md` |
| Android touch effect, save/load, layout | `UNVERIFIED` | no inspectable save artifact on a non-debuggable staging APK |
| macOS / Windows native | `UNVERIFIED` from this host | dedicated builders only |

## Release artifact

| Field | Value |
| --- | --- |
| Path | `native-offline/releases/vibecodedemulator-3.2.5-linux-amd64.deb` (git-ignored staging output) |
| Size | 46,149,424 bytes |
| SHA-256 | `56e56f6754a7959807da9fef777eb25c59fb97f6ffc56cfc537d8f0fc146669a` |
| Control | `Package: vibe-coded-emulator`, `Version: 3.2.5`, `Architecture: amd64`, `Installed-Size: 95888` |
| Built from | clean `32b5f191827b89c4f9263f95e7dc40089b6535f5` |
| Driver | `native-offline/scripts/build-linux-staging.sh deb`, shared native lock, one compilation worker |
| Test bridge absent | `strings … \| grep -c an3-ui-control` = 0 |
| Smoke | the extracted binary launches under `Xvfb :98`, stays alive, maps the `VibeCodedEmulator` window (41,483-byte capture), exits with **0** orphan processes |

Android: the recorded hosted artifact
`vibecodedemulator-3.2.5-android-arm64-staging.apk`, sha256
`fa835dab55cafe235b6dad341fc62a644aad78e52fc83bdebd820a84667b1040`, 50,550,881
bytes, arm64-v8a only, installed and played on `vce-api36`.

macOS and Windows have no artifact from this host; their builders were not run.

## Release state — NOT PUBLISHED

The release is **not** finished. `docs/release.md` requires, in order: a clean
tree, green exact-SHA CI, an artifact from that SHA, recorded acceptance per
claimed surface, then publication. The first three hold. Publication does not,
for two concrete reasons:

1. **The web production path needs the owner's credentials.** `deploy-production.sh`
   requires `AN3_PRODUCTION_APPROVED=1` *and* the staging/production SSH control
   path; `tools/ssh/check-staging-key.sh` reports
   `ERROR: Known-hosts file is unavailable. Verify and add the staging host key
   before using this control path.` The owner instruction grants no credentials or
   keys, so no deploy was attempted.
2. **Missing acceptance rows block the native release.** macOS and Windows have no
   builder run, LAN Sync and Phone Controller have no two-peer/two-device run, and
   the Switch companion exists only for macOS. `docs/release.md`: "Anything
   missing makes the release `UNVERIFIED` for that surface, not 'probably fine'."

### Rollback, recorded before deployment

- **Web**: the previous production revision is re-deployable with
  `AN3_PRODUCTION_APPROVED=1 ./deploy-production.sh`; the post-deploy health check
  (`deploy/an3-arcade-health.sh`) is the acceptance of the rollback. No revision
  was deployed by this track, so nothing needs rolling back.
- **Native (Linux)**: the previously published package stays in
  `native-offline/releases/` and in the GitHub release; the release notes must name
  the previous version. Nothing was published by this track.
- **Android**: the previously recorded staging APK stays in the hosted artifact
  store; this track published none.

## Everything still UNVERIFIED or BLOCKED

1. Two-peer LAN Sync (discovery → transfer → hash match → conflict → reconnect)
   and two-device Phone Controller (fresh code → play → release-all → reconnect).
   Missing: two network stacks on one LAN. On this host multicast never reaches a
   same-host listener.
2. macOS and Windows native acceptance. Missing: their dedicated builders.
3. Switch companion beyond macOS. Missing: a companion build per host; Eden is
   pinned by the licensing audit and is not a bounded packaging step.
4. Android touch effect on gameplay, save/load, and non-default layouts. Missing:
   an inspectable save path on a non-debuggable staging APK, and a fixture that
   renders a game rather than a counter.
5. Browser 3DS on other browsers, audible audio and sustained play. Missing: those
   browsers, a sound device, and a session-length run.
6. Sustained native display frame pacing and audio underruns (`docs/QUALITY.md`
   gaps 1 and 2) — unchanged by this track.
7. Physical-device acceptance of any kind. Missing: owner-supplied devices.

## Reproduce

```sh
bash tools/verify-project.sh                       # local source gate
AN3_WEB_RUNTIME=1 AN3_PLAYWRIGHT_BROWSER=chromium \
AN3_3DS_FIXTURE=/path/to/boot.3dsx \
  node --test tests/web-runtime.test.mjs           # browser lane + 3DS
python3 -m unittest tests.test_web_3ds_runtime tests.test_native_settings \
  tests.test_phone_controller_hosts tests.test_rendered_ui_accessibility
CARGO_HOME=$PWD/work/cargo-home bash native-offline/scripts/build-linux-staging.sh deb
```

## Related

- [`checkpoints/ui-ux-baseline.md`](../checkpoints/ui-ux-baseline.md),
  [`checkpoints/web-3ds-browser.md`](../checkpoints/web-3ds-browser.md),
  [`checkpoints/direct-lan-controller.md`](../checkpoints/direct-lan-controller.md),
  [`checkpoints/eden-native-integration.md`](../checkpoints/eden-native-integration.md),
  [`checkpoints/native-linux-journey.md`](../checkpoints/native-linux-journey.md)
- [`release.md`](../release.md), [`QUALITY.md`](../QUALITY.md),
  [`REGRESSION_GUARDS.md`](../REGRESSION_GUARDS.md) (RG-078, RG-156, RG-159, RG-160)
