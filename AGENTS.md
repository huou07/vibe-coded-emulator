# VCE Development Guide

Vibe Coded Emulator is a cross-platform emulator front end with a Python-served
browser product and a native Tauri application. Keep product behavior and
platform limits truthful; the repository root, `docs/`, and their linked source
are authoritative when this file is opened independently of the Hub.

## Project map

- `app.py`, top-level Python modules, and `static/`: browser library, player,
  account/sync endpoints, and local web UI.
- `native-offline/`: Tauri application, shared player UI, Rust/C++ runtime, web
  bridge, Android Kotlin/JNI host, and per-platform packaging.
- `tests/`: Python server/runtime tests and Node browser/native-model tests.
- `tools/`, `native-offline/scripts/`, and `deploy/`: verification, build, and
  staging/release operations. Read a script before using it.

## Verification

- `bash tools/verify-project.sh` runs the deterministic Web, application-source,
  and JavaScript checks available in this checkout.
- Web only: `python3 -m unittest discover -s tests`.
- Web/native JavaScript behavior: `node --test --test-concurrency=1 tests/*.test.mjs tests/*.test.js`.
- Native application glue: `npm --prefix native-offline run check`.
- Native packages require the matching platform toolchain and pinned core
  artifacts; source checks do not prove an installable package or gameplay.

## Invariants and safety

- Preserve client-side emulation, offline browser-local data, the EmulatorJS
  IndexedDB core contract, report-first core selection, persistent core cache,
  NDS ZIP delivery, melonDS auto-start, and the NDS touch bridge.
- Player canvas, input, layering, save, audio, and renderer changes require the
  relevant guards in `docs/REGRESSION_GUARDS.md` and interaction contracts in
  `docs/player-layering.md` before and after the change.
- Use only lawful fixtures. Do not add ROMs, firmware, keys, saves, or other
  copyrighted/private data to source control. Preserve third-party notices.
- Check `docs/native-offline.md`, `docs/android-regression.md`,
  `docs/agent-control-plane.md`, and `docs/licensing/` for the relevant area.
- Work staging-first. Do not push publicly, publish a release, or deploy to
  production without explicit human approval. Never rewrite release history.
