# UI and runtime verification

Read [design-system](design-system.md) and [page contracts](ui-page-contract.md)
for UI work, [player layering](player-layering.md) for the protected player, and
[development workflows](development-workflows.md) for source gates.
The shared evidence vocabulary applies to new claims; legacy GOOD means only
what the cited guard establishes. Static PASS is VERIFIED_SOURCE, never a
browser/native acceptance result. CI configuration is not an executed CI result.

## Cheapest adequate tool

| Claim | Authority |
|---|---|
| Rendered-markup preflight | tools/inspect-ui.py, stdlib approximation only |
| Web role/name/state, interaction, keyboard and geometry | Playwright in an actual browser |
| Layout/appearance | Target screenshots plus measurements and review |
| Native shell/package | Actual Tauri app with supported WebDriver/native driver |
| Android controls | Existing Android accessibility/instrumentation and device/CI tooling |
| Gameplay/audio/input/save/performance | Existing emulator runtime guards, lawful fixture, frame/state/audio/timing evidence |

The static inspector does not run CSS or JavaScript or implement a full browser
accessibility/name algorithm. Keep its CLI for fast preflight compatibility.
It cannot establish focus, contrast, responsive layout or runtime accessibility.

## Canonical Web lane

```sh
AN3_WEB_RUNTIME=1 node --test tests/web-runtime.test.mjs
```

Requires playwright-cli on PATH and its Chromium installation. The test uses a
private browser configuration, loopback server, temporary SQLite data and a
synthetic catalog with no game ROM. It verifies real search/no-results recovery,
keyboard clear, detail navigation and 360/390/1440px geometry, retains three
screenshots plus source identity, and saves a trace on failure. Browser/profile
and server are closed; generated script files and fixture data are removed.
Artifacts are bounded to the selected states under ignored work/ui-runtime.
GitHub's browser job is the independent execution lane. Exact product source
`a8a26e711b3b38a8d322220e95e852d1efa0ff7a` passed all three jobs in
[run 38680843043](https://github.com/huou07/vibe-coded-emulator/actions/runs/38680843043):
project verification, actual Chromium journey and fail-closed publication gate.
The earlier exact f11567c local worktree passed 478 Python tests (20 explicit
skips), 92 JavaScript tests (four explicit skips), source checks and a separate
Chromium journey. Legacy Web CLI compatibility also passed with a private
Chromium configuration. The original WIP working tree's disk-preflight assertion
still fails against its pre-existing packaging wrapper; that WIP was preserved
and is outside the clean-commit result. No skipped platform became a PASS.

The confirmed dynamic accessible-name defect (Search games became Search games
Clear while typing) is guarded in the runtime test. The label now references
only its own text. Static preflight alone did not catch this browser defect.

## an3ctl audit and compatibility

Keep target lifecycle, Android/WebView access, emulator control, deterministic
capture/hash and core-specific runtime evidence. They provide product-specific
capabilities. Web actions/query/value now delegate to Playwright locators,
accessible-name computation, click/fill/press/selectOption/setChecked and
actionability checks, replacing injected DOM clicks/value changes and unstable
indexes. Role/name matching is case-insensitive substring matching; CSS, IDs,
test IDs and nth selection remain supported. Name queries now use actual labels
and common interactive roles; prefer an explicit role for precision.

ui tree preserves legacy compact nodes for existing consumers, marks them
legacyNodes, and adds the canonical Playwright ariaSnapshot. The compact
DOM approximation remains only for compatibility and the Android WebView adapter;
it is not a second Web semantics authority. No Android behavior was removed
without replacement evidence. Unavailable targets and skipped tests stay UNVERIFIED.
AN3_PLAYWRIGHT_CONFIG selects a native CLI JSON configuration; when supplied it
controls the browser instead of the default system Chrome channel.

CI also exposed two source-evidence defects hidden by the local sparse checkout:
retired root handoffs are now labelled archives, with original bodies preserved;
and the scanner CLI is pinned to 8.30.1. The old global path allowlists skipped
entire files. Rule-scoped AND conditions now allow only the two known identifiers,
with positive/negative regressions proving adjacent synthetic secrets still fail.
No real credential or live permission fixture was used.

## Actual Tauri desktop lane: BLOCKED locally

Official [Tauri guidance](https://v2.tauri.app/develop/tests/webdriver/) recommends
[WebdriverIO's Tauri service](https://webdriver.io/docs/desktop-testing/tauri).
Embedded mode requires optional test-only WebDriver plugins in the actual app;
external mode uses tauri-driver and the platform driver on Linux/Windows.
Renderer/browser mode does not establish native execution. Do not add embedded
automation to distribution builds or mock IPC to claim native bridge acceptance.

Inspected on 2026-10-15: Tauri CLI 2.11.4 is installed. WebdriverIO/service,
tauri-driver, WebKitWebDriver, the Linux shell binary and prepared Linux emulator
player are absent. The locked CLI is a build tool, not an installed app.
These are concrete missing prerequisites; no native shell or package ran.
No core downloads, cross-platform builds, VM or Android emulator were launched.

Small unblock path, without replacing the existing native control plane:
prepare the Linux binary/player on an authorized builder, install a locked WDIO
test dependency set and the chosen official driver, then run one isolated
Xvfb journey: launch → offline library → actual native_capabilities IPC →
settings → keyboard cancel/recovery → exit. Assert real backend state and retain
one screenshot/log. Use a synthetic app-data directory and lawful fixtures.
Before adopting embedded mode, review its plugin versions/features and ensure
they are absent from release builds. The existing external driver route avoids
adding a debug server to the app; OS driver installation remains an owner action
when unavailable to the worker.

Bound local Linux work to one job, one compilation worker, a timeout and fresh
memory/storage checks; share /tmp/aeh-native-ui-UID.lock with OR and the optional
H07P guest. No uncontrolled compile, GPU workload, VM, AVD or release matrix.
CI remains authoritative for cross-platform/native/package acceptance.
A shell smoke cannot establish gameplay, media correctness or latency.
