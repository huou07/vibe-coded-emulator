# AN3 environment facts (single source)

Volatile environment facts live here only. Do not copy these into worker prompts;
link this file and pass only the affected-platform lines.

## Hosts and platforms

- macOS development host: primary orchestrator + macOS/Android builds + CodeGraph.
- Android: local SDK/ADB/AVD (`codex-nds-api35`, `an3qa-api35`).
- Linux: authorized Debian builder (`an3-dell`) for DEB/Flatpak.
- Windows: build VM (`an3-win11-build`, ProxyJump via `an3-dell`), start on demand.
- Staging: `http://192.168.1.8:8092` (host `huou07@192.168.1.8`).
- Production: `192.168.1.8:8091` — **forbidden** without explicit owner approval.

Source/edits/deploys repo root: `/Users/meomeo/Documents/edit an3tocom apps&web`
(`native-offline/` holds packages). The legacy checkout is read-only reference.

## Systems

GBA, NDS (melonDS), 3DS (Azahar), Switch (Eden bridge / separate-process companion),
phone Controller, LAN/multiplayer netplay. `gba` and `nds` are the broadly verified
native systems; 3DS/Switch have per-guard caveats — read `docs/REGRESSION_GUARDS.md`
before claiming any of them.

## Shared resources (lease names)

`android-avd:codex-nds-api35`, `android-avd:an3qa-api35`,
`windows-vm:an3-win11-build`, `linux-builder:an3-dell`, `staging:8092`,
`port-range:8110-8119` / `8130-8139` / `8140-8149` / `8150-8159`,
`artifact-dir:native-offline/releases`.

## Reuse existing skills (do not duplicate)

- `an3-codegraph-first` — mandatory before source investigation/edits.
- `an3-player-regression` — player-surface guards.
- `an3-control-plane` — `an3ctl` for any app interaction/runtime control.
- `an3-build` — per-platform build, version bump, catalog.
- `an3-staging-deploy` — staging deploy/smoke, SSH via verified key only.
- `public-release-security` — mandatory before any public push/release.
- `playwright-cli`, `vibe-coded-verification` — browser and private verification rules.

## Tooling

- CodeGraph index: `.codegraph/` (query with an explicit project path).
- `an3ctl`: `tools/an3ctl/bin/an3ctl` (structured JSON; no screenshots for control).
- Release catalog verifier: `tools/verify-release-catalog.py`.
- Release train: `tools/release-train.sh`.
- Staging SSH env: `tools/ssh/staging-env.sh` + `tools/ssh/check-staging-key.sh`.

## Run-state access

Orchestration run state lives in the shared Git common dir, which is **outside**
the project worktree (`$(git rev-parse --git-common-dir)/opencode-orchestrator/`).
Non-interactive sessions auto-reject unapproved external paths, so the `an3-*`
agents grant `external_directory` for the narrow pattern
`*/.git/opencode-orchestrator/*`. Keep that pattern narrow; do not broaden it to
the whole `.git` or the checkout parent.

## Rules

- Never expose secrets, tokens, keys, staging SSH material, or production data.
- Never mix staging and production paths. Never root devices or record serials.
- Do not add SSH password helpers. Do not enable production debug interfaces.
- Do not hard-code today's version numbers or paths in this skill; read them from
  the repo at run time.
