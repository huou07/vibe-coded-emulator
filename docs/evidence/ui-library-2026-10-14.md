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
