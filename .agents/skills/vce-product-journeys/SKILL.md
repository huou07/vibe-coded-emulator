---
name: vce-product-journeys
description: Use when completing or reviewing a user-visible VCE flow such as local ROM import, library search and launch, settings, saves, direct-LAN controller or save transfer. Do not use for backend-only changes or isolated style edits with no flow impact.
---

# VCE product journeys

Use this procedure to finish one coherent user outcome on its real supported
surface. Unit tests prove components; they do not prove that a person can
discover, complete and recover from the flow.

## Preconditions

- Resolve the repository, branch, exact source/artifact identity and applicable
  product/platform scope in `AGENTS.md`, `docs/README.md` and the active
  checkpoint. Preserve in-flight edits and existing saves.
- Define one observable starting state, successful outcome and recovery path.
  State which system/core, platform and network condition are included.
- Use lawful user-owned fixtures. Keep ROMs, saves, keys and credentials out of
  the repository and evidence.
- Load `an3-control-plane` for app interaction. Read
  `docs/REGRESSION_GUARDS.md` and `docs/player-layering.md` before changing
  player input, canvas, menus, saves or renderer behavior.

## Procedure

1. Inspect available targets with the structured control plane. Prefer semantic
   state and selectors. Do not start unsupported local emulators or a replacement
   web server. Record unavailable targets explicitly.
2. Exercise the user path from its real entry point: open/install, import a local
   file using the actual file picker when applicable, observe core readiness,
   find the game in the library, launch it and relaunch offline.
3. Exercise the relevant controls and recovery states: settings/layout, keyboard,
   touch or gamepad where supported, resize/fullscreen, pause/resume, exit, and
   loading/error/empty states. For NDS/3DS, preserve screen mapping and menu input
   precedence.
4. For save work, cover each in-scope slot/action, round-trip, autosave choice,
   restart persistence and safe recovery without overwriting unrelated saves.
5. For direct-LAN controller or save transfer, use two real peers on the same LAN
   with internet disconnected. Cover discovery, pairing, transfer/input, integrity,
   conflict choice, reconnect, focus/network loss and release-all. Server tests
   alone do not prove direct-peer acceptance.
6. Review relevant viewport sizes, landscape safe areas, keyboard navigation,
   focus, touch target size, contrast, status feedback and error recovery. Apply
   the same vocabulary and placement across Web/native surfaces while respecting
   platform file-dialog and back-button conventions.
7. Run the existing relevant guards before/after changes. Record exact commands,
   exit codes and observable UI state. Use screenshots only to answer a rendering
   question; semantic assertions alone do not prove visual quality.
8. Update the existing checkpoint with completed and open platform/core rows,
   evidence identity, procedure used, friction found and next discriminating
   action. Do not create a competing roadmap.

## Authority and recovery

Use only targets permitted by the active session and host policy. Owner authorization
for accepted releases/deployments applies only within its gates; it does not grant
protected credentials or privileged host access. If a flow risks overwriting or
losing user data, stop writes and preserve the existing store. Use the product's
recovery/conflict choices, and revert the isolated code change if it caused the
failure; verify retained data and rerun the relevant guards before acceptance.

## Acceptance and limits

Mark a journey GOOD only when the real target completed the user outcome and its
recovery path with the required evidence. If browser automation, device, second
peer, renderer, file picker or runtime is unavailable, record the affected leg
as UNVERIFIED and keep independent source checks separate. Hiding an unfinished
in-scope feature is not completion. Google cloud sync and the blocked Rust
gateway cutover remain out of scope.

Skip this procedure for backend-only work, isolated CSS/token values or a source
gate with no user-flow change. Report tested surfaces, exact source/artifact,
observed outcome, recovery result and unverified legs.
