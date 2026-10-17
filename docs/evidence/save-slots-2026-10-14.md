# Web save-slot storage probe (2026-10-14)

## Scope and identity

The `vce-product-journeys` and `an3-player-regression` procedures were used at
HEAD `f67b32885fc02d852a4f211f941d8ccee24de092` on
`feature/semantic-ui-inspection`. Existing local edits in `app.py`,
`static/site.css`, and `tests/test_integration.py` were preserved. The probe
uses a lawful-fixture label only; it contains no ROM, save, or private data.

## Evidence

Before adding the guard, the relevant player guard baseline passed:

```text
python3 -m unittest tests.test_regression_invariants tests.test_web_nds_touch_behavior tests.test_native_regression_guards tests.test_shared_player_ui
Ran 52 tests — OK
node tests/web_nds_touch_behavior.test.js — ok
node tests/web_renderer_behavior.test.js — 11 passed
node --check static/player.js — exit 0
```

The new `node tests/player_save_storage.test.js` invokes the repository's actual
`QuickSaveManager` with an in-memory IndexedDB API model. It verifies raw byte
round-trips through ten stable slots after constructing a new manager, rejects
slot numbers outside 1–10, preserves timestamps, keeps autosave separate, and
retains prior data when an autosave transaction aborts. Result: **2 tests passed**.

## Acceptance limits and next action

The deterministic storage behavior is **GOOD** at this modeled API boundary.
Actual IndexedDB behavior in a browser, player UI actions, OS restart, game
state round-trip, and recovery with pre-existing real saves remain
**UNVERIFIED**. Browser automation and local player targets are unavailable in
this worker; Android devices and packaged desktop runtimes are also unavailable.
Next discriminating action: run the ten-slot/autosave/restart journey on a
browser target with Playwright, then repeat against each accepted packaged core
using a lawful save-capable fixture without replacing unrelated saves.

The modeled write abort tests QuickSaveManager's rejection handling and the
expected atomic record contract; it does not prove the browser's IndexedDB engine
or EmulatorJS core state compatibility.

## Real-browser IndexedDB round-trip (2026-10-17)

Source `68ca5c5f0065bdca424fb3281ab02aa304dfd880`, with the RG-152 change to
`tests/web-runtime.test.mjs` (the run below also carried that uncommitted test
edit). The `vce-product-journeys` procedure and the canonical Chromium lane were
used against the local test server:

```sh
AN3_WEB_RUNTIME=1 AN3_PLAYWRIGHT_BROWSER=chromium XDG_CACHE_HOME=<tmp> \
  node --test tests/web-runtime.test.mjs
```

The lane loads the actual `static/player-runtime.js` into the live page and calls
the real `QuickSaveManager`. Observed: all ten slots wrote and round-tripped
byte-for-byte (`roundTripMatches: true`); a freshly constructed manager read slot
7 back (`restartedSlot7Matches: true`), standing in for a restart; slots 0 and 11
raised `RangeError` (`rangeRejected: true`); autosave wrote its own record
(`autoMatches`, `autoFlag`) without touching manual slot 1 (`autoIsSeparate`).
Result: **1 test passed**, retained as `quickSave` in
`work/ui-runtime/evidence.json` with zero page errors.

Acceptance limits: browser-engine quick-save/autosave storage is now **GOOD**.
Game-level save/load inside a running EmulatorJS core, a real page reload during
gameplay, and the packaged native save journey remain **UNVERIFIED**; no ROM or
core was launched.
