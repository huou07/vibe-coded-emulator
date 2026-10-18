# VCE project skills

Purpose: route to one project-specific procedure. A skill body is a procedure the
code cannot teach; this table is only the routing decision.
Authority: navigation. `AGENTS.md`, `docs/AGENT-AUTHORITY.md` and the host/tool
boundaries govern execution; a skill never authorizes a privileged action.
Last reviewed: 2026-10-18.

## Route by task

| Skill | Use for | Entry document | Skip / boundary |
|---|---|---|---|
| `an3-build` | Building, versioning and cataloguing a packaged app; artifact identity and sidecars | `docs/development-workflows.md` | Web-only change or diagnosis; a package build is not a release |
| `vce-release` | The whole release: preflight, exact-SHA CI, GitHub release, web production, rollback | `docs/release.md` | Routine local build; staging-only deploy; public source snapshot |
| `public-release-security` | A public publication candidate and the fail-closed publication gate (RG-155) | `docs/QUALITY.md` | Internal status or edits; a PASS is gate evidence, not authorization |
| `an3-staging-deploy` | A named staging deploy, smoke, health check or staging rollback | `docs/staging.md` | Local source edits; a health read never redeploys |
| `an3-control-plane` | `an3ctl` target discovery, structured UI, deterministic captures, save/input assertions | `docs/agent-control-plane.md` | Browser work already grounded in Playwright; documentation-only work |
| `an3-player-regression` | Before/after a player-surface edit: canvas, input, layering, touch, renderer | `docs/REGRESSION_GUARDS.md` | Unrelated backend or prose; select only the relevant guards |
| `vce-product-journeys` | Completing one user-visible flow end to end on its real surface | `docs/features/README.md` | Backend-only change; isolated style edit with no flow effect |
| `vce-ui-ux` | Visual/interaction design across Web, native and Android; clutter, tokens, entry points | `docs/features/ui-shell.md` | Emulation, transport or storage; a token the browser lane already asserts |
| `vce-web-3ds` | Making 3DS playable in the browser, or diagnosing why it presents no frame | `docs/features/web-3ds.md` | Native 3DS; Eden/Switch; general player UI |
| `vce-lan-peer` | LAN Sync and Phone Controller: transport, pairing, conflict, reconnect, two-peer evidence | `docs/features/lan-sync.md` | Server-only API work; cloud sync (removed) |
| `vce-eden-native` | Eden/Switch companion integration, per-host builds, packaged acceptance | `docs/features/switch-eden.md` | The Web (never carries Eden); GBA/NDS/3DS cores |
| `vce-gameplay-performance` | Sustained gameplay frame pacing, latency, audio, thermals on supported hardware | `docs/QUALITY.md` | Packaging-only work, CI frame counters, boot smoke, speculative optimization |
| `vce-android-device` | Dedicated VCE AVD, Android build lane, committed asset mirror, device runs | `docs/features/android.md` | Desktop or Web-only change; other platforms' packaging |

## Dependencies and ordering

- A user-visible journey loads `vce-product-journeys` **and** delegates target
  interaction to `an3-control-plane`. Loading the journey skill alone is not
  enough to drive a target.
- A player-surface edit loads `an3-player-regression` before and after; a
  `static/` edit is also an unreleased native change and an Android-mirror
  change.
- A release is `an3-build` (artifact) → exact-SHA CI → `vce-release`; a public
  source snapshot adds `public-release-security` and never substitutes for the
  CI gate.
- The 2026-10-18 product track runs in this order: UI/UX baseline → Web 3DS →
  LAN Sync and Phone Controller → Eden/Switch → Android device acceptance →
  release. A later step may start only when its own evidence exists.

## Routing examples

- Positive: "the Linux library screen feels cluttered; make launch obvious" →
  `vce-ui-ux` (and `an3-control-plane` to drive the packaged UI).
- Neighboring negative: "add a violet border to the game card" that the browser
  lane already asserts → no skill; use the shared verification procedure.
- Positive: "3DS in the browser shows a black canvas" → `vce-web-3ds`.
- Neighboring negative: "3DS on Android hands off to Azahar but the companion
  will not start" → `vce-android-device` (and `vce-product-journeys`), not
  `vce-web-3ds`.
- Positive: "send this save to the other laptop over Wi-Fi with no internet" →
  `vce-lan-peer`.
- Positive: "Switch homebrew launches but input never reaches Eden" →
  `vce-eden-native`.
- Neighboring negative: "package the next version and update the catalog" →
  `an3-build`, not `vce-release`.
- Positive: "ship 3.2.6 to GitHub and production after CI" → `vce-release`, with
  `an3-build` and `public-release-security` as required steps.

## Rules

- Inspect targets, scripts and source identity before executing them.
- Keep authored instructions in English; keep the owner's conversation language
  for reports.
- Real runtime, automated checks and manual UX review are separate evidence;
  preserve `GOOD`/`UNVERIFIED` exactly.
- A skip is never `GOOD`. A skill's example command is an example, not proof it
  ran.
- New skill? Add its row here in the same change, wire the matching feature page,
  and keep the description a routing sentence, not a procedure.
