# Checkpoint — GPLv3 licensing + Eden integration (2026-09-16)

Recovery point before the GPLv3 transition and any Switch/Eden work.

## Starting state

- Workspace: `<repo-root>` (branch `apps-web`).
- Starting commit: `c10ab03` (`docs(vibe): record LAN transfer progress in the roadmap`).
- `git status`: clean (no uncommitted changes) at the checkpoint.
- Remote `origin` is a local path (`/Users/meomeo/Documents/Codex/2026-08-11/an3-arcade`);
  there is **no** configured public repository URL. The release README/repo URL
  must not be invented; the GPL notices use the local origin until the owner
  provides a public URL.
- Existing license situation: **no `LICENSE` file** existed; the app had no
  license declaration in `tauri.conf.json`. `docs/vibe-coded-platform.md` said
  the native app was distributed as `LicenseRef-proprietary`, while
  `native-offline/THIRD_PARTY_NOTICES.md` already documented bundled GPL/MPL
  cores and linked their corresponding source.

## Release/version state at the checkpoint

| Platform | Version | Artifact |
| --- | --- | --- |
| macOS | 1.4.1 | vibecodedemulator-1.4.1-macos-aarch64.dmg |
| Android | 1.4.0 | vibecodedemulator-1.4.0-android-arm64-staging.apk |
| Linux DEB | 1.4.1 | vibecodedemulator-1.4.1-linux-amd64.deb |
| Linux Flatpak | 1.4.1 | an3-offline-1.4.1-linux-amd64-staging.flatpak |
| Windows | 1.4.1 | vibecodedemulator-1.4.1-windows-x64-staging.exe |

- Staging: `http://192.168.1.8:8092`, asset `e792e8578089`, release
  `staging-290e3e764ac5a294`. Production is untouched.
- Test suite: 264 tests, 0 failures.

## Planned changes

1. Apply **GPL-3.0-or-later** to the original AN3/Vibe Coded Emulator code
   (`LICENSE`, README, SPDX headers, notices).
2. Add a consolidated `THIRD_PARTY_NOTICES.md` and a Licenses UI surface.
3. Audit every bundled/linked dependency; produce
   `docs/licensing/license-audit.md` and
   `docs/licensing/distribution-compliance.md`.
4. Investigate eden-emu/eden and pin an exact commit; document the direct
   integration architecture and any concrete blocker
   (`docs/licensing/eden-integration-feasibility.md`).
5. Version bump for the packaged apps after the notices/UI land.

## Licensing risks

- The app already bundles **GPL-2.0-or-later** (Azahar), **GPL-3.0-or-later**
  (melonDS DS) and **GPL-3.0** (EmulatorJS) components, so the combined app was
  already subject to GPL distribution duties before this transition. The GPLv3
  transition makes the app's own terms consistent with those duties.
- Corresponding source must accompany the GPL binaries. The notices already link
  pinned upstream sources; the release process must keep that true.
- Android's GPLv3 "Installation Information" (§6) applies to User Products; the
  app is sideloaded, not preinstalled. Documented, not a blocker.
- Eden's tree is per-file licensed (GPL-2.0-or-later and GPL-3.0-or-later).
  Anything Eden-derived must keep its upstream notices.

## Verification requirements

- Full test suite before/after; `node --check` for changed JS.
- `tools/verify-release-catalog.py` after any catalog change.
- Staging deploy only; confirm the notices are served and the source links
  resolve.
- Do not claim Eden integration is complete unless a real Switch title runs.

## Recovery instructions

- This checkpoint is a plain commit range; nothing was rewritten and no
  force-push occurred. To undo the licensing transition:
  `git revert <commit>` for the licensing commits, or check out `c10ab03` for the
  file set. No production binaries were changed by the checkpoint itself.
