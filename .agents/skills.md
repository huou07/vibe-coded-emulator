# VCE project skills

Purpose: route to one project-specific procedure.
Authority: navigation; project AGENTS and host/tool boundaries govern execution.
Last reviewed: 2026-10-14.

| Skill | Use for | Skip / boundary |
|---|---|---|
| an3-build | Package/version/catalog and builder artifact evidence | Web-only work or ordinary diagnosis; this host cannot run VMs/toolchains; publication still needs its gates |
| an3-control-plane | Structured app state, interaction and renderer assertions | Documentation or packaging-only work; unavailable targets are UNVERIFIED |
| an3-player-regression | Input/canvas/layering and shared player behaviour | Unrelated backend or prose; select relevant guards |
| vce-gameplay-performance | Repeatable sustained gameplay evidence on supported hardware | Packaging-only, CI counters, boot smoke or speculative optimization |
| vce-product-journeys | User-visible flows and recovery on actual Web/native surfaces | Backend-only changes or isolated style edits without a flow impact |
| an3-staging-deploy | Explicit named staging operation or health check | Local status/source edits; health-only never redeploys |
| public-release-security | Exact public publication candidate and fail-closed gate | Internal status/edits; PASS is gate evidence, not authorization by itself |

Bodies live in [skills](skills/). Verify current session discovery before claiming
a skill was loaded. Inspect targets, scripts and source identity before executing
them. The active owner mandate dated 2026-10-14 authorizes commits, pushes, public
publication, suitable GitHub releases, CI/CD build/test/release and accepted
production deployment within its stated gates. This does not grant protected
credentials or override tool/OS permissions. This workstation must not run VMs
or heavy platform builds; root release helpers remain operator boundaries.

## Routing examples

- Positive: compare sustained GBA frame pacing on a physical Android device →
  `vce-gameplay-performance`.
- Neighboring negative: produce an APK with no gameplay measurements → `an3-build`.
- Positive: complete local import, library search, launch and offline relaunch →
  `vce-product-journeys`.
- Neighboring negative: repair a server-only LAN payload parser → no journey skill;
  use the shared investigation/verification procedure.
- No project skill: a formatting-only edit in an unrelated Python helper.

Use shared investigation, diagnosis and security procedures where they fit.
Keep authored instructions in English. Real runtime, automated checks and manual
UX review are separate evidence; preserve GOOD/UNVERIFIED labels exactly. Current
DSH discovery confirmed the two new skill names and their descriptions; this
connection can load them, while other harnesses must verify their own routing.
