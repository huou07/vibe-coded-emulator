# Regression invariants

- Emulation stays client-side; server stores and serves data.
- NDS uses melonDS and `EJS_startOnLoaded = true`; no DeSmuME/manual-start workaround.
- NDS touch bridge and custom virtual pad remain intact.
- EmulatorJS core contract remains `EmulatorJS-core` / `core` / `?EJS_KEYS!`, with `version` and `ArrayBuffer` data.
- Core selection is report-first, then browser capability/binary selection.
- Core cache `an3-arcade-cores-v1` persists independently of PWA shell versions.
- NDS serves original ZIP where appropriate; Range and chunk upload remain supported.
- Offline ROM/save data remains browser-local.

