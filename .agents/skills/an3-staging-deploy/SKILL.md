---
name: an3-staging-deploy
description: Use when deploying or smoke-testing the AN3 Arcade / Vibe Coded Emulator web app on staging, checking the staging SSH key, or verifying deployed assets and installer URLs. Triggers on "deploy staging", "deploy-stage.sh", "check-staging-key", "staging health", "is staging up", "rollback staging".
---

# Deploy and verify AN3 staging

Staging is `http://192.168.1.8:8092` (host `huou07@192.168.1.8`). Production is
`192.168.1.8:8091` and **must never be touched without explicit owner
approval**.

## Deploy (from any worktree that has `tools/ssh/staging-env.sh`)

```bash
cd "$(git rev-parse --show-toplevel)"
source tools/ssh/staging-env.sh
tools/ssh/check-staging-key.sh          # must print STAGING_SSH_KEY_AUTH=PASS
./deploy-stage.sh                       # packages, scp, root release helper, switches current
```

`deploy-stage.sh` prints:

```
STAGING_DEPLOY=PASS
STAGING_ASSET=<asset-version>
STAGING_RELEASE_PATH=/opt/an3-arcade-staging/releases/<stamp>-<asset>
STAGING_ROLLBACK_TARGET=/opt/an3-arcade-staging/releases/<previous>
```

SSH is key-only (owner-installed verified key, strict host checking, no
password auth). Never create an SSH password helper.

## Smoke after deploy

```bash
curl -s http://192.168.1.8:8092/health                     # {"ok":true,"environment":"staging",...}
curl -s http://192.168.1.8:8092/download-app/artifacts.json
# Each installer URL in the catalog must return 200 with the expected size:
curl -s -o /dev/null -w "%{http_code} %{size_download}\n" "<artifact-url>"
python3 tools/verify-release-catalog.py                    # RELEASE_CATALOG=PASS
```

Staging-only surfaces (production returns 404 by design): `/multiplayer`,
`/controller`, `/controller/join`, `/api/multiplayer/*`, `/api/controller/*`.
The netplay relay is `http://192.168.1.8:8094` (LAN only).

## Rollback

Roll back by pointing `current` at `STAGING_ROLLBACK_TARGET` using the
root-owned staging release helper — never by editing files in place.

## Rules

- Keep the compact dark-violet minimal design.
- Record the asset version, active release, browser/runtime, ROM identity, and
  console errors for any runtime verification.
- Never mix staging and production paths or expose secrets.
- If a browser or packaged runtime was not exercised, record `UNVERIFIED`.
