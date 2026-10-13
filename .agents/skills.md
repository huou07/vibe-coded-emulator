# VCE project skills

Purpose: route to one project-specific procedure.
Authority: navigation; project AGENTS and host/tool boundaries govern execution.
Last reviewed: 2026-10-13.

| Skill | Use for | Skip / boundary |
|---|---|---|
| an3-build | Package/version/catalog and builder artifact evidence | Web-only work, ordinary diagnosis; no local VM/toolchain or automatic release |
| an3-control-plane | Structured app state, interaction and renderer assertions | Documentation or packaging-only work; unavailable targets are UNVERIFIED |
| an3-player-regression | Input/canvas/layering and shared player behaviour | Unrelated backend or prose; select relevant guards |
| an3-staging-deploy | Explicit named staging operation or health check | Local status/source edits; health-only never redeploys |
| public-release-security | Exact public publication candidate and fail-closed gate | Internal status/edits; PASS does not authorize publication |

Bodies live in [skills](skills/). Verify current session discovery before claiming
a skill was loaded. Inspect targets, scripts and source identity before executing
them. This workstation must not run VMs or heavy platform builds. Protected
owner credentials and root release helpers remain operator boundaries.

Use shared investigation, diagnosis and security procedures where they fit.
Keep authored instructions in English. Real runtime, automated checks and manual
UX review are separate evidence; preserve GOOD/UNVERIFIED labels exactly.
