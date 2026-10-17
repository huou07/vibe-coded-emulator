# Library action review (2026-10-14)

## Source and preserved work

Reviewed at base HEAD `df4c4ec116157f1b0be564823a41041bbbc885e4` on
`feature/semantic-ui-inspection`. Existing local edits in `app.py` and
`static/site.css` were present before this review and were preserved. Their
original author is not recorded in Git metadata; this evidence does not attribute
them to the reviewer. The preserved UI changes add a Play action to compact
collection cards, improve comment-delete semantics and sizing, and enlarge
mobile library controls. This review added a 44px mobile minimum for the new
compact-card Play action and a regression assertion in `tests/test_integration.py`.

## Journey and observed result

Used the `vce-product-journeys`, `an3-control-plane`, and `ui-ux-review`
procedures. Checked the `an3-player-regression` boundary; player-specific
guards were not applicable because these scoped site styles do not touch player
canvas, input, or layers. The control plane found a Web target but no
Playwright bridge; Android, local player, macOS and Switch targets were
unavailable. Started the local Web app on port 8099 with `an3ctl`, inspected
`/games` using `tools/inspect-ui.py --check`, and stopped the task-owned server.
The live server-rendered page showed a named Game library heading, named search
box, expanded-state menu button, and “Get the offline app” link; the inspector
reported no unnamed operable controls. The local library had no games, so a
compact card and comment-delete row could not be inspected on that live page.

The integration fixture creates an NDS collection entry and checks that its
library response includes a direct `/play/<slug>` action and that the mobile
Play action has a 44px minimum. It also checks the admin comment-delete control
has `type=button` and the accessible name `Delete comment`, and that the same
control is absent from the guest page. `python3 -m unittest tests.test_integration`
passed 12/12 tests after those assertions. This is server-rendered route and
source-CSS evidence, not a browser interaction or visual check.

## Acceptance limits and next action

Library empty-state semantics, compact-card link generation, and role-gated
comment-delete markup: **GOOD** at the source/test level. Compact-card appearance,
360/390px overflow, actual tap/focus, comment deletion, ROM import, core readiness,
gameplay, and offline relaunch: **UNVERIFIED**. The direct Play route fixture
uses test data and does not establish that a lawful ROM boots. Repeat visual and
interaction checks on a browser with Playwright and a populated lawful test
library; exercise the import/play/save/offline flow on each accepted platform.

## Offline local-ROM flow trace

The `vce-product-journeys` follow-up distinguished the server catalog from the
actual offline import flow. `/games` is a server-rendered catalog surface; it is
not the native device-local library. The packaged local-ROM entry point is
`native-offline/web/index.html` (`Open ROM`, `Add ROM`, and the platform picker).
`native-offline/web/native-app.js` routes Play/Open ROM into that library, while
`static/offline.js::setupLibrary` invokes the native file picker, checks the
reported system, writes the game record to the local library, and rerenders it.
Launch dispatch then passes through `native-offline/web/native-bootstrap.js` to
the native host. `tests/test_offline_consolidation.py` checks source wiring and
invariants, but does not operate the OS file picker or prove an actual ROM launch.

Friction found: the initial live `/games` inspection could easily be mistaken for
the offline library journey. Outcome: traced the actual packaged entry points and
corrected the evidence boundary; no local-ROM acceptance claim was added. The
offline import, core readiness, launch, restart persistence and relaunch without
internet remain **UNVERIFIED** until a packaged Android or desktop runtime and a
lawful fixture are available.

## Native import-path follow-up (source `4f01bf53da501f4b719150c75bee9c7dc7537114`)

The `vce-product-journeys` and `an3-control-plane` procedures were dogfooded
again against the offline-first local-ROM flow. A fresh
`tools/an3ctl/bin/an3ctl targets --json` returned exit 0: Web is available but
has no Playwright bridge; Android has no connected device; the deterministic
emulator has no local player; Switch has no harness; macOS has no active UI
bridge; Linux lacks WebKitGTK WebDriver/display; Windows is unreachable.
No application process was started in this follow-up.

Source trace: `native-app.js::openRom` opens Library/Add ROM and clicks the
native picker when configured, otherwise the browser file input. In
`offline.js::setupLibrary`, the native path reports busy status, awaits the
platform import, validates the reported system, removes an unsupported import
when possible, and only then stores the local game record and rerenders the
library. A later missing-native-ROM launch failure exposes **Re-import ROM**.
These branches and the platform bridge wiring are covered by
`tests/test_offline_consolidation.py`, but the test does not invoke a real OS
picker or native host.

Outcome: no reproducible source defect was established, so no import code was
changed. The import, cancellation/error recovery, capability readiness, launch,
offline relaunch, and preservation of an existing library remain **UNVERIFIED**.
The concrete next requirement is a reachable packaged test target with its real
file picker and a lawful fixture; the current worker exposes none of the targets
needed to complete that journey.

## Refreshed target and fixture check (source `f97bb7c534a026f70e5b901e1c244a22e41d4153`)

At this source on 2026-10-14, `an3ctl targets --json` exited 0. Web is listed
but has no Playwright bridge; Android has no connected device; the emulator
adapter has no local player and lists configured Linux and Windows SSH targets;
Switch has no harness; macOS has no UI bridge; Linux desktop lacks WebKitGTK
WebDriver/display; and the Windows builder is unreachable. A repository glob for
`**/*.gba` and `tools/testrom/**` returned no files, so this checkout also has no
lawful GBA fixture or fixture generator available to launch. No app or emulator
process was started, and no gameplay or performance metric was collected.

The offline import and relaunch journey remains **UNVERIFIED**. Its next
acceptance prerequisites are a reachable packaged Android or desktop target with
a real file picker, plus a lawful system-compatible fixture. Gameplay-performance
acceptance separately needs an authorized physical device or capable builder, a
pinned core and renderer, and the workload/telemetry listed in the performance
procedure; configured SSH target names alone do not establish reachability.

## Fresh control-plane recheck (2026-10-14)

- The bare `an3ctl targets --json` command was not on this shell's `PATH`
  (exit 127). The documented project-local entry point,
  `tools/an3ctl/bin/an3ctl targets --json`, ran successfully (exit 0); its
  structured report matches the target limits above.
- A fresh repository glob for `**/*.{gba,nds,3ds,zip}` returned no files.
  This checks only this checkout; it cannot establish that a user has no lawful
  fixture elsewhere.
- No app, emulator or build process was started. The offline import/relaunch
  journey and gameplay-performance result remain **UNVERIFIED**. The concrete
  next action is to provide an authorized reachable Android or desktop test
  target and a lawful compatible fixture outside the repository; performance
  acceptance additionally needs physical hardware or an authorized capable
  builder with intended renderer and telemetry.

## Admin comment-moderation browser journey (2026-10-17)

Source `68ca5c5f0065bdca424fb3281ab02aa304dfd880`, updated by the RG-152 change
to `tests/web-runtime.test.mjs` (the run below also carried that uncommitted test
edit). The `vce-product-journeys` procedure was used with the canonical
Chromium lane:

```sh
AN3_WEB_RUNTIME=1 AN3_PLAYWRIGHT_BROWSER=chromium XDG_CACHE_HOME=<tmp> \
  node --test tests/web-runtime.test.mjs
```

Observed: the seeded anonymous library journey still passes; the script clicks
the GBA, NDS and All system filters and asserts the opposite card hides and
restores and the live count reads `1 matching game` (RG-153). After signing in as
the seeded admin on `/login`, `/game/fixture-gba` renders exactly one
`Delete comment` control. The app calls `window.confirm("Delete this comment?")`;
a dismissed prompt leaves the comment row in place, and an accepted prompt
detaches it and the reloaded page no longer contains it (server deletion
reached). Result: **1 test passed**, `work/ui-runtime/evidence.json` carries
`commentModeration: "confirm prompt, dismiss keeps, accept deletes and persists"`
with zero page errors.

Acceptance limits: admin comment deletion is now **GOOD** in an actual browser on
this host. Native dialog chrome is not asserted (the lane spies on
`window.confirm`); compact-card appearance, ROM import, core readiness, gameplay,
and offline relaunch remain **UNVERIFIED**, and this does not establish native
packaged moderation. The native lane is shared because `static/site.js` is copied
into the Tauri bundle.
