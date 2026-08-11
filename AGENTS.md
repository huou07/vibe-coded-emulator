# AN3 Arcade session rules

- This is the new development workspace for the 2026-08-11 session.
- Treat `/Users/meomeo/Documents/Codex/2026-08-08/v/outputs/an3-arcade` as read-only legacy reference.
- Preserve the handoff invariants: client-side emulation, melonDS with auto-start, NDS touch bridge, EmulatorJS IndexedDB core contract, report-first core selection, persistent core cache, NDS ZIP delivery, and offline browser-local data.
- Never expose secrets or production data. Do not mix staging and production paths.
- Runtime changes require local baseline/tests and staging verification before any production consideration. Production deployment requires explicit approval.

