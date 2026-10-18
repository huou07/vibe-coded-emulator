# VCE product track — owner instruction 2026-10-18

Mission: finish the product on its real surfaces — complete the UI/UX, make 3DS
playable in the browser, finish LAN Sync and Phone Controller, add first-class
Switch/Eden support to the installed app — then release what actually passed CI.

Read `AGENTS.md` first, then this prompt. It is an owner instruction; it grants
what `docs/AGENT-AUTHORITY.md` allows and nothing more.

## Current source and baseline

- Repository: the VCE checkout (resolve it with `git rev-parse --show-toplevel`),
  branch `feature/semantic-ui-inspection` at the time of writing.
- Establish the real state yourself: `git status --short --branch`,
  `git rev-parse HEAD`, `git log -1`. Do not trust a SHA written in this prompt.
- The local source gate is `bash tools/verify-project.sh`; GitHub Actions is the
  authoritative remote gate. Hosted `verify.yml` must be green for the exact SHA
  you release.
- Current product gaps, as recorded in the feature pages: 3DS is not playable in
  the browser; the packaged Linux player's Exit Game does not exit the process;
  NDS/3DS native journeys are unexercised; LAN Sync and Phone Controller have
  source and fixtures but no two-peer/device acceptance; Eden exists as a macOS
  companion only and is not a first-class surface; the Linux native UI is
  owner-reported as cluttered.

## Authority and limits

Authorized by the owner on 2026-10-18:

- Complete the UI/UX; add Eden/Switch support to the installed app (never the
  Web); finish LAN Sync and Phone Controller; make 3DS playable in the browser.
- Build and test Linux, Web and Android on this Debian host, with **one Android
  AVD dedicated to VCE**; OR's AVD is off limits.
- Build and test macOS and Windows through free GitHub CI and their dedicated
  builders.
- Release versions that pass the gates to GitHub and the web production path.

Never granted: credentials or keys, privilege escalation, history rewrite, branch
protection bypass, ROMs/firmware/keys/saves in the repository, a server relay for
local play, or a claim that CI does not support.

## Platform matrix

| Platform | Build and test | Acceptance evidence |
| --- | --- | --- |
| Web | This host (browser lane) + hosted CI | Lane run on the exact SHA |
| Linux native | This host, one bounded build at a time | Packaged journey, recorded in the native tracker |
| Android | Hosted arm64 build lane + VCE AVD `vce-api36` on this host | AVD install-and-play run; build lane is not acceptance |
| macOS / Windows | GitHub CI and dedicated builders only | The builder's run; never a claim from Linux |

## Order of work

Do them in this order. A later phase may start only when the earlier one has its
own evidence; phases B–E are independent of each other once A is accepted.

### A. UI/UX baseline (start here)

Goal: the product looks and reads as one product, and every feature has one
obvious entry point. Owner's report: the Linux native UI is cluttered; Android and
macOS are an acceptable baseline; Switch, LAN Sync and Phone Controller have no
coherent place yet.

- Read `docs/features/ui-shell.md`, `docs/ARCHITECTURE.md`,
  `docs/design-system.md`, `docs/ui-page-contract.md`.
- Load `vce-ui-ux`; use `an3-control-plane` to drive the packaged UI.
- Start with the Web shell (cheap iteration), then the Linux native shell, then
  check the Android mirror. Do not restyle everything in one change.
- Deliver: (1) a short written UX backlog of concrete friction per journey —
  library, launch, in-game controls, settings, saves, new-feature entry points;
  (2) one bounded change per journey with before/after captures; (3) one entry
  pattern reused for Switch, LAN Sync and Phone Controller.
- Acceptance: each changed journey reviewed on its real surface; the browser
  lane, the accessibility check and `bash tools/verify-project.sh` green; the
  Android mirror synced (`tools/check-native-mirror.py`).

### B. Web: make 3DS playable

Goal: a lawful 3DS game reaches the first presented frame in the browser.

- Read `docs/features/web-3ds.md` and `docs/features/core-selection.md`; load
  `vce-web-3ds`.
- First action is a retest, not a code change: reproduce with `?debug3ds=1` and
  capture the failing stage. RG-078 forbids reintroducing a browser-only 3DS lock
  and records a 2026-09-15 upstream video limitation; the repaired `data-v2`
  Azahar runtime postdates that record.
- Acceptance: the canonical browser lane presents 3DS frames with a lawful
  fixture, recorded (command, exit code, observable state), then hosted CI green.
  If the core still cannot present video, record the dated upstream blocker with
  evidence and stop — do not hide 3DS and do not claim it works.
- Keep the EmulatorJS contract and the cache key unchanged; the Web product stays
  stdlib-only and never carries Eden.

### C. LAN Sync and Phone Controller

Goal: two real peers, internet disconnected, transfer a save and play with a
phone, without the server in the path.

- Read `docs/features/lan-sync.md`, `docs/features/phone-controller.md`,
  `docs/LAN_PEER_ARCHITECTURE.md`; load `vce-lan-peer`.
- Peers may be the VCE AVD plus a desktop on this host; record that they are not
  physical devices. Physical-device acceptance stays `UNVERIFIED` unless the
  owner supplies devices.
- LAN Sync acceptance: discovery → transfer → hash match → conflict choice
  (never a silent overwrite) → reconnect, with the gameplay effect measured.
- Controller acceptance: fresh pairing code → play → release-all on focus loss,
  explicit stop and transport loss → reconnect or re-pair; no held input.
- Deliver discoverable entry points in the native UI (coordinated with phase A).

### D. Eden/Switch in the installed app

Goal: Switch is a first-class library surface on every host that can ship a
companion — not a libretro core and never a Web feature.

- Read `docs/features/switch-eden.md`,
  `docs/checkpoints/eden-native-integration.md`,
  `docs/licensing/eden-integration-feasibility.md`; load `vce-eden-native`.
- Decide and record the platform matrix first: macOS has a pinned companion
  resource; Linux, Windows and Android need their own companion build and
  evidence. A host without a companion must not advertise Switch.
- Acceptance per host: packaged launch → render → input → save → reload → exit
  with a lawful homebrew fixture, no orphan process, recorded with source SHA and
  artifact hash. Rows without that evidence stay `UNVERIFIED`.

### E. Android device lane

Goal: the Android app is proven on a device-class target, not only compiled.

- Read `docs/features/android.md`; load `vce-android-device`.
- Create one AVD dedicated to VCE (`vce-api36`); never attach to or disturb OR's.
  One heavy job at a time, memory/disk checked, bounded timeout, cleanup.
- Acceptance: install the recorded artifact, run the library → import → play →
  touch → save/load → exit journey, record AVD name/API/image and artifact hash.
  The staging APK is debug-signed; a production identity is an owner action.

### F. Release

Goal: ship what passed, and only what passed.

- Read `docs/release.md`; load `vce-release`, with `an3-build` for artifacts and
  `public-release-security` for any public snapshot.
- Acceptance: clean tree → local gate → artifact with recorded SHA-256 → push →
  exact-SHA hosted CI including `release-gate` → recorded acceptance per claimed
  surface → GitHub release and/or web production deploy → recorded health and
  rollback command.
- A red or pending CI run, a dirty tree, a mismatched artifact or a missing
  acceptance row blocks the release. Say so instead of shipping.

## Working rules

- One coherent change per commit, with the gate result in the message; update the
  feature page and its tracker in the same change.
- Serialize heavy jobs (one build, one emulator, one AVD); check memory and disk;
  share the native lock; clean up whole process groups.
- Lawful fixtures only. Nothing user-owned is committed or published.
- Evidence words: `GOOD` (the named live check is current), `UNVERIFIED` (no live
  check), `BROKEN` (a live check failed). A skip is never `GOOD`.
- Do not weaken a gate, scanner or assertion to obtain a green run.
- Do not publish, deploy or release from a green local run alone.

## Reporting contract

After each phase, report separately:

1. **Implemented** — what changed, with paths.
2. **Verified locally** — command, exit code, observable outcome.
3. **CI-accepted** — run URL and exact SHA.
4. **Blocked / UNVERIFIED** — the precise missing prerequisite and what it would
   take to obtain it.
5. **Next action** — one, with its observable completion.

## Stop conditions

- All five workstreams have evidence at a named SHA, the hosted CI gate is green,
  and the release is recorded with its rollback — or each unfinished item is
  reported with its exact missing capability.
- Do not continue into unspecified refactors, cloud sync, a relay, the
  `rust-gateway` cutover, or Eden on the Web because the gates are green.
