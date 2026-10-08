# Storage preflight continuation handoff — 2026-10-09

## Workspace and preservation

- Active workspace: `/Users/meomeo/Documents/edit an3tocom apps&web`
- Branch/HEAD at continuation start: `feature/phone-controller-cross-platform` / `ad71997613d0fd143266355be7b68f238f5e587f`
- The workspace had extensive pre-existing modified and untracked files. They were preserved; no broad cleanup or reset occurred. Only the explicitly listed files were staged for local commits.
- The sibling `an3-333-runtime-unification` checkout remains outside this change. Its newer source/version state must not be silently copied into this older active branch.

## Change completed

Added a non-destructive disk-space preflight before local macOS, Windows, Linux DEB/Flatpak, and Android package builds. Defaults warn below 40 GiB and stop below a 25 GiB reserve. The check only reads available space and never deletes files.

- POSIX helper: `tools/disk-preflight.sh`
- Windows helper: `tools/disk-preflight.ps1`
- Wired through `native-offline/package.json`, the Android and Linux staging scripts, and the Windows staging script.
- Added pass/warning/stop/invalid-threshold coverage and entrypoint-order assertions in `tests/test_disk_preflight.py`.
- Added the workflow guard to `docs/REGRESSION_GUARDS.md`.
- The same guard was adapted to the current public 3.3.3 source line, preserving its Android path remapping and Mac/Windows companion build entrypoints.

## Verification

- `python3 -m unittest tests.test_disk_preflight tests.test_native_staging_contract tests.test_release_train_versions`: **15 passed**.
- Prior active-workspace baseline for native runtime/input/renderer/menu/staging guards: **75 passed** before these workflow edits.
- `bash -n` on the POSIX preflight and modified shell entrypoints: passed.
- `git diff --check`: passed.
- `native-offline/package.json` JSON parse: passed.
- On the current 3.3.3 source line, `python3 -m unittest tests.test_disk_preflight tests.test_native_staging_contract tests.test_release_train_versions`: **22 passed**.
- Clean public snapshot overlay on current public `main`: **556 Python tests passed; 35 skipped**.
- Current host reports 143 GiB available; no build or emulator process was active at the recorded snapshot.
- PowerShell is unavailable on this Mac, but the Windows helper executed successfully inside the hosted Windows x64 package build below. This is build-path verification, not packaged-app gameplay acceptance.

## Public snapshot, CI, and review

- Local safeguard commit on the older active branch: `3d5f3a2`.
- The development branch was not pushed. The public repo received a sanitized source snapshot at `72a7a57305e1a9db657913fc2dba7aa0040bcd69`; no development history was published.
- Candidate security scan: **0 Gitleaks findings**, personal-data/infra scan clean. Existing public `main` history scan: **0 findings**.
- Hosted native matrix for that public source SHA, run `37815594596`: **success** for Linux DEB, Linux Flatpak, Windows x64 installer, Android APK/instrumentation plus three Android UI/save checks, and macOS ARM64 DMG/regressions.
- That first snapshot exposed stale publication templates. The follow-up PR [#9](https://github.com/huou07/vibe-coded-emulator/pull/9), branch `codex/storage-preflight-ci-fix`, head `82d2d596e322a656171f84038b44f5a335605029`, fixes the current CI workflow and the retired settings in `.env.example`. Required CI run `37820290837` passed all Python, Node, Rust, and static-security jobs. Its diff is limited to `.github/workflows/ci.yml` and `.env.example`.
- The duplicate native workflow for PR #9 was canceled because its native source is unchanged from the successful base SHA. Branch protection now requires the `test` check. PR #9 remains open; it has not been merged. Public `main` therefore still needs that PR to clear the first snapshot's failing CI run.
- The hosted workflow uploaded build artifacts for verification. No GitHub Release, staging deployment, or production deployment was created.

## Cross-platform acceptance snapshot

| Platform | Package evidence at public SHA `72a7a573` | Runtime evidence | Remaining acceptance |
| --- | --- | --- | --- |
| macOS | ARM64 DMG build and native regression job passed. | Existing 3.3.12 candidate test imported the lawful fixture and advanced presented frames. | Pixel correctness, input, audio, saves, and long-session behavior remain unverified for that candidate. The 3.3.3 DMG was not installed and exercised interactively. |
| Windows | x64 installer and native build job passed. | None for an installed game session. | Install/launch, library import, gameplay, audio/input, saves, and exit/relaunch. |
| Linux | x86_64 DEB and Flatpak builds passed. | None for installed DEB/Flatpak UI. | Install/launch, library import, gameplay, audio/input, saves, and exit/relaunch. |
| Android | APK/instrumentation build passed; API 35 SRAM restore, library UI, and settings UI jobs passed. | Automated emulator UI/save acceptance. | Physical-device and long-session acceptance remain separate. |

This is package and focused regression evidence, not full platform parity or a completion claim. The next product phase should verify desktop user journeys on the supported runtimes and record feature gaps before changing player or shared-host behavior.

## Related runtime evidence and limits

The installed VCE 3.3.1 app was closed by the user, freeing loopback port 38471. The existing durable candidate handoff records that the VCE 3.3.12 candidate test-only flow passed import of the lawful fixture, native session stayed running, and the presented-frame counter advanced. Candidate pixel correctness, input, audio, and save behavior remain unverified. Do not repeat the candidate run unless needed; use that handoff evidence and its exact artifact identity.

The active branch is older than the public 3.3.3 checkpoint and the newer sibling checkout. Do not package or bump this branch until source lineage is reconciled. The user closed the installed 3.3.1 app; the existing 3.3.12 candidate flow evidence remains as recorded above.

## Next work

1. Reconcile the authorized source lineage and choose the correct continuation checkout without disturbing dirty work.
2. Merge PR #9 only after the user reviews it; its required CI check is green.
3. Continue the requested cross-platform product audit from the matrix above, distinguishing package-build evidence from live gameplay evidence.
4. Keep the disposable Android AVD lifecycle item explicitly **UNVERIFIED** until safely exercised or implemented with evidence.
