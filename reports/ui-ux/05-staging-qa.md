# Phase 5 — Staging QA

Status: **BLOCKED — candidate not deployed**

Recorded 2026-08-13 for branch `ui/production-ux-refresh`, release candidate `a9d5269ca6176dbf19af0d77720cd0a783b4e58e`.

## Deployment evidence

`./deploy-stage.sh` was invoked for the committed candidate. SSH authentication failed during `scp` before a release archive was transferred. A proposed retry using an askpass helper located in another workspace was rejected because reuse of that credential source is not explicitly authorized for this task; the retry did not execute.

The deployment script therefore did not create a staging release, change the staging `current` symlink, restart the staging service, or contact production.

## Read-only post-failure check

The staging health endpoint remained healthy and separate:

```text
URL=http://192.168.1.11:8092
ENVIRONMENT=staging
ASSET_VERSION=def955887c68
```

The root document also referenced `site.css` and `site.js` at `def955887c68`. This proves staging is unchanged and still serves the pre-candidate asset. It does **not** validate release candidate `a9d5269`.

## Candidate gates that remain open

- populated staging library at 1440, 1280, 768, 390, and 360 CSS px;
- active search/filter/no-results with real staging artwork density;
- populated detail media/community state;
- ready GBA player and ready NDS player in portrait and landscape;
- fullscreen, menu, save slots, virtual pad, player failure recovery, and NDS touchscreen/pointer regression;
- online preparation → app shell/core/local ROM readiness → disconnected restart → offline play;
- native admin upload/bulk-upload progress under the normal CSP;
- staging accessibility and request/runtime performance observations.

Installed-PWA restart after network loss also remains a separate secure-origin gate. LAN HTTP staging cannot prove it, and production must not be used as the design-review environment.

## Required unblock

Use one staging authentication method explicitly authorized for this AN3 task. Once available, rerun `./deploy-stage.sh`, verify `/health` reports the candidate asset, then complete the staging matrix above. Do not deploy production until those gates pass and the user explicitly approves the final release block.
