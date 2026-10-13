---
name: an3-build
description: Use when building, versioning, or publishing a packaged Vibe Coded Emulator (AN3 Arcade) app for macOS, Android, Linux DEB/Flatpak, or Windows — including version bumps, the per-platform build commands, artifact/sidecar collection, catalog updates, and release verification. Triggers on "build the DMG/APK/DEB/Flatpak/EXE", "publish version", "bump the app version", "update the release catalog". Do not use for a Web-only change, ordinary test diagnosis or a status-only request.
---

# Build and publish a VCE packaged app

Repo root for source, edits and builds: this repository — resolve it with
`git rev-parse --show-toplevel`, never a hardcoded path. `native-offline/`
holds the packages.

**This host cannot build them.** Packaging needs the pinned core artifacts and a
per-platform toolchain on the dedicated builders. Locally you may only edit
version fields, `native-offline/releases/catalog.json`, and the packaging
scripts; `bash tools/verify-project.sh` and GitHub Actions do the rest.

## Preconditions and authority

Inspect source identity, the affected package and its current version/catalog.
Read packaging scripts before execution. This procedure prepares source and
artifact evidence; release/publication requires explicit owner authorization.
Builder commands below are references for authorized dedicated builders, not
permission to start local VMs, install toolchains or access protected credentials.

## Version-bump rule (owner-mandated)

Every change to a packaged app bumps that app's version, sized by change type:

- Bug fix → patch `X.X.X+1`
- New feature / small update → minor `X.X+1.X`
- Refactor / big update → major `X+1.X.X`

Apply the bump to the version fields the app actually uses: Android
`src-tauri/tauri.android.conf.json` `version`, desktop
`src-tauri/tauri.conf.json` / `package.json` when rebuilt, the artifact
filename, `releases/catalog.json`, and the sidecar. **Never republish changed
bytes under an already-published version + filename.**

## Per-platform commands

```bash
# macOS (ad-hoc signed, not notarized — staging only; no Apple credentials)
cd native-offline && npm run build:macos

# Android (staging signing) -> releases/vibecodedemulator-<v>-android-arm64-staging.apk
cd native-offline && bash scripts/build-android-staging.sh

# Linux (Dell builder, x86_64; user-level rustup stable)
#   ssh an3-dell; export CARGO_HOME=$HOME/.cargo RUSTUP_HOME=$HOME/.rustup
#   . "$HOME/.cargo/env"; cd ~/an3-verify/native-offline
#   PATH="$HOME/.cargo/bin:$PATH" bash scripts/build-linux-staging.sh deb
#   PATH="$HOME/.cargo/bin:$PATH" bash scripts/build-linux-staging.sh flatpak

# Windows (two-step; VM an3-win11-build, ProxyJump via an3-dell; start on demand)
#   1) powershell -File scripts\build-windows-runtime.ps1   # when any manifest source changed
#   2) powershell -File scripts\build-windows-staging.ps1
```

Rebuild the Windows native runtime whenever any file listed in
`vendor/runtime/windows-x64/manifest.json` changes — that list includes
`native-runtime/platform/linux/*`, so Linux/GTK/SDL edits invalidate it.

## Collect artifacts + sidecars

Each published artifact needs exact size, SHA-256, and a `.sha256` sidecar:

```bash
shasum -a 256 native-offline/releases/<artifact>
# sidecar: "<sha256>  <filename>"
```

Update `native-offline/releases/catalog.json` (version, filename, size,
sha256), then:

```bash
python3 tools/verify-release-catalog.py     # must print RELEASE_CATALOG=PASS
```

## Verify

```bash
PYTHONPYCACHEPREFIX="$PWD/work/pycache" python3 -m unittest discover -s tests
node --check static/player.js
```

## Windows VM lifecycle

On an explicitly authorized dedicated builder only, start `an3-win11-build` when
needed and shut it down gracefully from Windows (`shutdown /s` over SSH; ACPI
shutdown alone may not complete). Preserve disabled autostart. This workstation
must not run the VM. Do not root devices or record serials.

## Stop and report

Report package/platform, source SHA, version changes, artifact size/hash/catalog,
checks and missing builder/runtime evidence. Stop at the reviewable source or
artifact result when release authorization is absent. A build proves compilation;
packaged runtime acceptance must be independently recorded.

## Rules

- Staging first. Production requires explicit owner approval and is never
  automatic.
- No UX/audio/input "fixed" claim from compilation alone; exercise the
  packaged runtime.
- Version bumps and release records must match the bytes actually published.
