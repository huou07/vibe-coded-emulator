---
name: an3-staging-deploy
description: Use when deploying or smoke-testing the AN3 Arcade / Vibe Coded Emulator web app on staging, checking the staging SSH key, or verifying deployed assets and installer URLs. Triggers on "deploy staging", "deploy-stage.sh", "check-staging-key", "staging health", "is staging up", "rollback staging".
---

# Deploy and verify AN3 staging

Staging is `http://192.168.1.8:8092` (host `huou07@192.168.1.8`). Production is
`192.168.1.8:8091`. The active owner mandate dated 2026-10-14 authorizes deploying
accepted VCE versions through the existing production path after its checks pass;
other production changes still require explicit owner authorization.

## Preconditions and authority

Skip ordinary source edits and local status questions. A deployment request
permits only the named scope within host/tool permissions. The active owner mandate
authorizes accepted VCE production promotion through the existing path; it does
not grant protected owner keys, sudo, DNS/router changes or unrelated host control.
First read the deployment scripts and current endpoint/rollback configuration. Do
not run a root helper with model-controlled arguments or access protected owner
keys. If the available identity cannot use the approved operator path, prepare the
candidate and report the exact boundary for the operator. Never improvise sudo or
a credential helper.
For health-only requests, use read-only health checks; do not redeploy.

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
approved operator release path within explicit authorization. Agents must not
invoke a root helper with model-controlled arguments or edit deployment files in
place; hand the validated rollback target to the operator when privileges are needed.

## Stop and report

Stop after the requested staging operation and relevant health/asset checks.
Report source/asset identity, environment, observed health, rollback target,
commands/results and unverified browser/installer acceptance. Neither a deployment
marker nor an HTTP 200 proves the full user journey.

## Rules

- Keep the compact dark-violet minimal design.
- Record the asset version, active release, browser/runtime, ROM identity, and
  console errors for any runtime verification.
- Never mix staging and production paths or expose secrets.
- If a browser or packaged runtime was not exercised, record `UNVERIFIED`.
