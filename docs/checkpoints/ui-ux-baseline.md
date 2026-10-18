# Checkpoint — UI/UX baseline

Updated: 2026-10-18 (worker `dsh-worker` on the Debian x86_64 host). This is the
durable record for the UI/UX leg of the 2026-10-18 product track. It carries the
bounded backlog, one change per journey, and the entry pattern the shell reuses.
It is the only UI/UX tracker; `docs/features/ui-shell.md` keeps status and
`docs/design-system.md` / `docs/ui-page-contract.md` keep the contracts.

Evidence vocabulary is the repository's: `GOOD` (the named live check is current
for this source), `UNVERIFIED` (the implementation exists, no live check), and
`BROKEN` (a live check failed). A source reading is not a live check, and a
screenshot nobody looked at is not a visual review.

## Scope of this pass

Owner report 2026-10-18: the Linux native UI is "khá rối" (fairly cluttered);
Android and macOS are an acceptable baseline. The track named three features —
Switch, LAN Sync, Phone Controller — with no coherent place in the shell.

Surfaces in this pass, in the order the track fixes: the Web shell (cheap
iteration), the Linux native shell, then the Android mirror. The macOS and
Windows shells serve the same `native-offline/web/` markup through their own
builders, so a change here is unreleased there too and is never a macOS/Windows
acceptance claim.

## Backlog — concrete friction per journey

Measurements are from the live probes kept beside the captures:
`work/phaseA/probe-web.mjs` (Web, 390 px and 1440 px) and
`work/phaseA/drive-native.sh` (packaged Linux shell at 1400×1000, driven through
the test-only `ui-control` bridge). "Screens" is the number of distinct
viewport-heights of scroll a destination really has.

| Journey | Surface | Friction (observable) | Status |
| --- | --- | --- | --- |
| Navigation | Web shell | The header carried **two labels for one destination**: `Download app` → `/` and a chip whose visible text was `Offline` and whose accessible name was `Open app downloads` → `/download-app`. `/` and `/download-app` render the same page. The chip's visible label is not contained in its accessible name (WCAG 2.5.3), and it had no JavaScript consumer. | fixed |
| Recovery | Web `/offline` | The only recovery action said `Try Again` and linked to `/offline` — itself. The real way out was the mislabelled chip above. | fixed |
| Navigation | Native shell | Six destinations existed (Play, Library, Settings, Help, About is five) and **every device-to-device feature was buried in Settings**: Settings measured **3 viewport-heights** of one undifferentiated stack of seven cards mixing device facts, app config, per-system config, device-to-device features and legal notices. | fixed |
| New-feature entry points | Native shell | Three competing primary actions — `Start Hosting` (LAN Sync), `Start Hosting` (Phone Controller), `Host Game` (LAN Multiplayer) — sat in one scroll for one user intent, "connect to another device". The Phone Controller card was `hidden` in the markup and revealed only by JavaScript, so it had no discoverable entry at all. | fixed |
| New-feature entry points | Native shell | LAN Sync was nested inside a card headed `Account & LAN Sync` whose first control was a sign-in form: a save-transfer feature presented as authentication. | fixed |
| Library | Native shell | 4 viewport-heights of scroll on the empty library, mostly the always-open import form. | backlog |
| Launch / in-game controls | Web player | Player surface — out of scope here; governed by `docs/player-layering.md`. | not touched |
| Settings | Native shell | Settings still mixes device facts, app settings, per-system settings and licenses, but no longer carries the device-to-device features. A further split into Device / Emulation / About is the next candidate, not this change. | backlog |
| About | Native shell | The About screen reported **Version 3.2.0** while `native-offline/src-tauri/tauri.conf.json` says **3.2.5**, and every bundled asset is cache-busted with `?v=3.2.0`. Hardcoded version strings that no build step rewrites. | fixed (About); asset `?v=` backlog |
| Dense desktop controls | Web admin | Table row actions, the admin range selector and the small nav toggle keep a documented 28 px floor and are not machine-checked (`docs/QUALITY.md` gap 2). Still open. | backlog |

## The entry pattern

One destination named **Devices**, one card per device-to-device feature, one
primary action per card, and a state that is honest before the user commits:

- On the **installed app** the destination is a first-class navigation item
  (sidebar and bottom navigation, `data-nav="devices"`), and owns LAN Sync,
  Phone Controller, LAN Multiplayer and the Switch companion.
- A feature row is **rendered only on a host that can complete it**. The Switch
  card stays hidden until the companion reports `available: true`, so a host
  with no companion never advertises Switch. LAN Sync keeps its sign-in framing
  because a guest identity cannot complete the peer proof.
- On the **Web**, the pattern resolves to its honest subset: Switch is never a
  Web feature (owner decision 2026-10-18) and LAN Sync's browser peer is a
  development adapter, not a product path, so neither gets a Web entry point.
  The Web keeps one destination per purpose instead — which is what the header
  duplication above violated.

## Changes in this pass

| # | Journey | Change | Files |
| --- | --- | --- | --- |
| A1 | Web navigation + offline recovery | One destination per purpose: the header no longer carries the mislabelled `Offline`/`Open app downloads` duplicate, `Download app` points at `/download-app` and marks itself `aria-current="page"` on the download page, and `/offline` recovers to the library (`/games`) instead of to itself — `/download-app` in production, where there is no public library. | `app.py` (`layout`, `offline_page`, `download_app_page`) |
| A2 | Native new-feature entry points | The Devices destination and its four cards; `Devices` added to the sidebar, the bottom navigation and the Help guide; LAN Sync retitled from `Account & LAN Sync`; Phone Controller documented with the actual join path; the About version read from the running build. | `native-offline/web/index.html`, `native-app.js`, `native-bootstrap.js`, and the committed Android mirror |

## Evidence

| Claim | Live check | Result |
| --- | --- | --- |
| Web header has one destination per purpose | `work/phaseA/probe-web.mjs after` → `friction.json` | `Download app → /download-app`, no duplicate chip, on all eight probed routes |
| Web offline recovery leaves the notice | `work/phaseA/probe-web.mjs after` (`/offline`) | one primary action, `Open the online library`, 61 px tall |
| Web design contract survives | `AN3_WEB_RUNTIME=1 node --test tests/web-runtime.test.mjs` | pass; tokens unchanged, `minCompactHeight` 42, `compactBelow42` empty, 360 px no overflow |
| Web accessibility tree | `python3 -m unittest tests.test_rendered_ui_accessibility` | 8 tests pass |
| Native Settings is no longer the device hub | `work/phaseA/drive-native.sh after devices settings` | Settings **3 screens → 1 screen**; rendered tree on Settings is `settings-storage, application-settings, game-settings, licenses`, and the device cards are gone |
| Native Devices destination exists and owns the features | the same run | `tree-devices` = `account-lan-sync, phone-controller, lan-multiplayer`; destination is **2 screens**; reachable from the sidebar and the bottom navigation |
| A host without a Switch companion does not advertise Switch | the same run + `/diag` | `switch-companion` present and **hidden**; `AN3SwitchDetect` = `{ok:true, available:false, detail:"The Nintendo Switch companion is not installed in this build…"}` |
| About reports the shipped version | `/text?testid=native-app-version` | `3.2.5`, matching `tauri.conf.json`, instead of the literal `3.2.0` |
| The sixth navigation item is safe at phone width | `node work/phaseA/measure-native-layout.mjs` | 360 px and 390 px: six items, **52 px** tall each, no truncation, `scrollWidth` == viewport, no horizontal overflow |
| Android mirror matches its sources | `python3 tools/check-native-mirror.py` | `NATIVE_MIRROR=PASS` |
| Whole local gate | `bash tools/verify-project.sh` | `PROJECT_VERIFY=PASS`, exit 0, 22 skips published in `VERIFY_SKIPS` |

Packaged native artifact for the after-state captures: staging DEB
`VibeCodedEmulator_3.2.5_amd64.deb`, SHA-256
`9a81dbf0768ba622ffc6b899787933a4defe8f083358ddfeeaa0ce8cd64f61a3`, built from
`c2fcc881467e56ef7edcc4fc4e0db3dbc24f6cd3` plus this change, with the test-only
`ui-control` feature (absent from distribution builds). The before-state capture
used `ecf868b31593d7fd317e831268d10671dfbb0523fd7ab41358860019e3b080ca` from the
unmodified revision.

Visual judgement — whether the result actually reads as cleaner — is a human
review. The captures are retained under `work/phaseA/{before,after}` and
`work/phaseA/native-{before,after}`; they are git-ignored working evidence, and
no claim of visual quality is made from automation.

## Open work

1. Read the before/after captures by eye and record the visual verdict; the
   measured contracts are green but taste is not machine-checked.
2. Split the remaining Settings stack (device facts, application settings,
   per-system settings, licenses) if the reviewed captures still read as
   cluttered.
3. Generate the bundled-asset `?v=` cache-buster from the package version;
   `native-offline/web/index.html` still pins `?v=3.2.0` against a 3.2.5 package.
4. Close `docs/QUALITY.md` gap 2 with a second browser-lane pass over the admin
   and library update-notice surfaces so the dense desktop tier is measured
   rather than documented.
5. Re-run this pass on macOS and Windows through their builders; nothing here is
   a macOS or Windows acceptance claim.

## Related

- [ui-shell](../features/ui-shell.md), [design-system](../design-system.md),
  [ui-page-contract](../ui-page-contract.md),
  [native-app](../features/native-app.md), [android](../features/android.md),
  [switch-eden](../features/switch-eden.md), [lan-sync](../features/lan-sync.md),
  [phone-controller](../features/phone-controller.md)
- [native-linux-journey](native-linux-journey.md) — the packaged native tracker
