# Continue VCE product development

Complete VCE's next unverified end-user journey, beginning with a reproducible Linux native library/import/player flow and preserving the existing offline and save contracts.

## Establish the current source

Work in /home/huou07/Projects/VCE. Read AGENTS.md and docs/README.md, then use
docs/UI_TESTING.md, docs/REGRESSION_GUARDS.md and the relevant active checkpoint
under docs/checkpoints/ to select work. Load only matching skills through the
current harness. Establish branch, HEAD and dirty changes before changing files.

Dated inspection, 2026-10-15: branch feature/semantic-ui-inspection, HEAD
f9e96fec7596fee4613861f027c8372f6fc6a017. Pre-existing WIP spans app.py,
static/site.css, tests/test_integration.py, tools/an3ctl/adapters/web.mjs and
several development/evidence docs. Platform-aware npm routing was also WIP;
handoff preparation repaired the disk-guard test to follow its real delegates.
Recheck the actual tree and preserve unrelated changes. The public Actions API
returned no runs for that inspected HEAD. Historical passes do not accept WIP.

Dated update, 2026-10-17: the an3ctl web self-test failure is resolved (RG-151 —
isolated `AN3_STATE_DIR`/ephemeral port, no orphaned server, Chrome→bundled
Chromium fallback when no browser is selected). `bash tools/verify-project.sh`
is `PROJECT_VERIFY=PASS` (479 Python tests/20 skipped, 96 JS tests/3 skipped).
The canonical browser lane now also covers admin comment moderation (RG-152).
Native Linux remains parked (no vendored player, `vce-linux` disabled); Android,
macOS and Windows remain hosted-CI/device only; the direct-LAN two-peer journey
still needs two real peers and an Android build. None of those platform legs were
run here.

## Product outcome

First retain a passing existing source gate. Then establish the actual Linux
Tauri shell and native player prerequisites from docs/UI_TESTING.md and the
existing native-offline build paths. Do not treat tauri-driver compilation,
--help, browser screenshots or static inspection as native application evidence.

Use the existing an3ctl adapters and lawful synthetic/homebrew fixtures to
exercise library navigation, local import, actual player launch, input, save/
load, Exit Game and reopen. Preserve user data and demonstrate error/recovery
when the player or a supported core is unavailable. Repair the first observed
gap and add the narrow regression/journey evidence it needs. If the real native
journey is already accepted for the current source, continue the next unverified
boundary in the active checkpoints, including direct-LAN controller discovery,
pairing, input release and reconnect with two real peers.

Preserve the invariants in the repository contracts: browser-local offline
ROM/saves; NDS melonDS startup and touch bridge; EmulatorJS core contract and
cache key; layering/input precedence; ten quick slots, autosave and Exit Game.
static changes affect both Web and native UI. The Rust shadow gateway cutover
remains permanently blocked. Do not bundle ROMs, firmware, keys or user saves,
revive removed Google sync, or claim server-relayed multiplayer.

## Authority, tools and resource boundaries

The owner authorizes coherent commits, scoped pushes and stable releases to
registered GitHub/production destinations after exact-source required CI,
licensing/publication, version/artifact, health and rollback gates. This current
authorization supersedes older task-specific blanket release/AVD prohibitions;
it does not grant credentials, general sudo or blanket permission changes.
Permission changes must be scoped to a worker and target and applied through the
owner-authenticated H07P Permissions page.

The former `/usr/local/bin/aehctl` and `agents-worker` capability bundle is
retired; do not reinstall it or run its archived installers. H07P is the current
owner control surface. This host has `dsh-worker`, `codex-worker` and
`opencode-worker`, but no `vce-web` profile. For a browser job, assign the VCE
workspace and read-only shared Playwright/Chromium runtime access to the selected
existing worker in H07P. Keep native harness credential stores private to their
matching worker; no worker gets sudo. The canonical browser test uses only a
temporary local test password and local fixture data; it is not credential
detection evidence. `vce-linux` remains disabled until a real binary/player and
bounded journey are registered. Android still needs reviewed SDK/image/APK
inputs. Never execute archived source ops installers or substitute browser
evidence for native.

Serialize heavy jobs, check current RAM/disk headroom, use bounded compilation,
timeouts and cleanup of the entire test process group. Keep fixtures isolated
from owner HOME, credentials, production endpoints and live product data.

## Gates and completion

Use bash tools/verify-project.sh, the matching player guards and meaningful
runtime journeys. The source gate includes Python unittest, serial Node behavior
tests, native JS syntax and documentation references. Native packaging and
platform claims additionally require the existing exact-source GitHub/dedicated
builder gates. tools/publication-check.sh fails closed; do not bypass missing
scanners or licence notices.

Keep findings literally GOOD or UNVERIFIED in the existing guard/checkpoint
authorities, with exact source, run, artifact, platform and scope. Preserve
licences and historical evidence. Commit each coherent outcome without sweeping
unrelated WIP; never rewrite published history or force-push. Investigate failed
gates using a falsifiable hypothesis after two speculative repairs.

Continue until the chosen real journey and its required exact-source CI pass,
then select the next justified product outcome. Report implemented, locally
verified, CI-accepted, blocked and unverified separately. If a provisioned native
lane, lawful fixture or publication route is missing, identify that precise
boundary and continue independent implementation; do not mark it passed.
