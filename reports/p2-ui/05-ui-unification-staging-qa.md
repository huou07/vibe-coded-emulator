# P2.6–P2.11 — UI unification staging QA

## Design-system and page contracts

`docs/design-system.md` records the shared dark-retro language derived from the approved dashboard, login, and offline visual references. `docs/ui-page-contract.md` records the required IDs, API hooks, data semantics, and player boundary. `AGENTS.md` now points future work to these documents.

The existing shared consumer/admin styling is already scoped away from `.player-page`, and no P2 change modifies the player’s canvas, touch mapping, overlay ordering, virtual-pad geometry, core storage, or script contract.

## Staging review

The isolated staging asset `9cf7de4b8d0b` was reviewed for the public library, login shell, offline library/readiness surface, and admin dashboard. The library, login, offline, and admin documents did not have page-level horizontal overflow at the available browser viewport.

- Library: cover-first shelves, bounded system rail, desktop navigation, clear lime primary action, and a non-blocking library-update notice.
- Login: focused dark authentication panel with labeled fields, visible errors, and no idle progress display. The reference’s social and recovery controls were not invented because they are not backed by current application behavior.
- Offline: device facts, local ROM library, private-ROM import, and expandable core manager remain distinct and truthful.
- Admin: compact task navigation, CSP-safe native progress/table analytics, current metrics, and explicit unavailable telemetry status.

## Remaining approval boundary

This is staging-only evidence. Production has not been deployed or restarted. Production deployment remains blocked until the user gives explicit approval after reviewing the release scope.
