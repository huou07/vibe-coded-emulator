# AN3 / Vibe Coded Emulator — durable project state

Last updated: 2026-10-07. Branch of record: `product/3.3.3-release`
(public PR huou07/vibe-coded-emulator#6). This file is the resume point; it
replaces reading the historical checkpoint documents.

## Objective

Ship Vibe Coded Emulator as a product an ordinary user can download, install,
run and update on macOS / Windows / Linux / Android with GBA, NDS and 3DS,
keeping Switch/Eden on its existing path. Not "tests green" — the install and
playback journey.

## Current state

| Item | State |
| --- | --- |
| Public `main` | `7110fc3` = `v3.3.2` (released, artifacts on the v3.3.2 release) |
| 3.3.3 candidate | `b699233` on `product/3.3.3-release`, PR #6 open |
| Runtime-unification commits | on the branch: async save worker, portable core owner, bounded frame handoff, bounded SDL audio, AAudio negotiation, Android `run_return` |
| CI at `4665a7c` (pre-merge head) | `ci` 36537160069 success, `native-build` 36537159639 success incl. 10/10 Android settings teardown |
| CI at `b699233` | `ci` 37514698458 success; `native-build` 37514698459 in progress |

## Product defects found and fixed (b699233)

1. `scripts/install/install-{deb,flatpak}.sh` were absent from the published
   tree while `app.py` served them from that path. The download page's Linux
   install buttons raised `FileNotFoundError` and dropped the connection;
   `deploy/package-production.sh` tared a non-existent `scripts` directory, so
   production packaging could not run. Restored + pinned by
   `tests/test_install_scripts.py`.
2. `mod ui_control;` in `native-offline/src-tauri/src/lib.rs` was unconditional,
   so `AN3_UI_CONTROL_FILE` was compiled into every distribution binary. The
   existing macOS automation guard asserts the opposite and was failing. Now
   gated behind the `ui-control` feature, together with its Tauri command
   registration in `build.rs`.
3. Fresh checkouts could not build the native fixtures: the tests hardcoded one
   untracked MoltenVK header path. Now resolved like the build does, with an
   actionable skip.
4. Three packaged-macOS guards asserted against stale worktree bundles. They now
   skip a bundle whose version is not the current source, or that was staged
   without the out-of-tree Eden companion.
5. README source-repository placeholder `YOUR_GITHUB_USER`.

## Known open items

- **Tracked `native-offline/releases/catalog.json` still describes 3.3.0**
  while the published release catalog describes 3.3.2. The catalog is the
  download page's only artifact source and the Linux installers' only source of
  truth, so it must be regenerated from the real 3.3.3 artifacts and committed
  before the release. `tools/verify-release-catalog.py` currently fails on a
  clean checkout for exactly this reason (installer bytes are gitignored).
- **v3.3.3 has never been tagged or released.** Native installers for this merge
  do not exist yet.
- **Packaged-runtime acceptance for 3.3.3 is UNVERIFIED.** Nothing here claims a
  DMG/APK/DEB/Flatpak/EXE runtime pass; the tag build must produce that.
- **Web surface**: `app.py` is the authoritative server; the native apps are the
  primary client. Core-only product decision stands (no cloud, account, LAN
  sync, peer discovery).

## Verification commands

```bash
python3 -m unittest discover -s tests
node --test tests/*.test.js tests/*.test.mjs native-offline/tests/*.test.mjs
cargo test --locked --manifest-path native-offline/src-tauri/Cargo.toml --lib
npm --prefix native-offline run check
```

Local C++ fixtures need `npm --prefix native-offline run prepare-moltenvk`
plus `prepare-native-cores` and `prepare-azahar`; they are fetched build inputs,
not tracked source.

## Release path

`native-release.yml` is tag-triggered, builds the five platforms through the
reusable read-only `native-build.yml`, and creates a **draft** release. A human
publishes it. Do not tag until the catalog and per-platform acceptance for this
exact merge are in place.

## Exact next step

Wait for `native-build` 37514698459 on PR #6. If green, merge PR #6 to `main`,
regenerate `releases/catalog.json` from the tag-built artifacts with matching
`.sha256` sidecars, then tag `v3.3.3` and review the draft release before
publishing.