# Development workflows

VCE contains two user-facing products. The browser application is served by the
root Python server; the installed emulator application lives under
`native-offline/`. They share product concepts and selected UI models, but have
separate runtime and packaging paths.

## Browser product

The browser app uses Python's standard library for its server and checked-in
static assets. From the repository root:

```sh
python3 app.py
python3 -m unittest discover -s tests
```

The test suite covers HTTP/API behavior, sync and multiplayer logic, packaging
invariants, and source-level runtime contracts. Use lawful local fixtures only.
For a real browser journey, start the server on loopback and verify the library,
import, and player flow in a browser; unit tests alone do not prove that journey.

## Native application

`native-offline/` contains the Tauri shell and native runtime. The portable
runtime, platform adapters, native web bridge, Android host, generated settings
model, and packaging scripts are separated there. Useful checks from the repo
root are:

```sh
node --test --test-concurrency=1 tests/*.test.mjs tests/*.test.js
npm --prefix native-offline run check
```

`npm run check` is a source syntax check, not a Tauri package build. A package
build needs the matching OS toolchain and pinned runtime/core artifacts. Read
`native-offline/docs` and the platform build scripts before building. On a
source-only or cross-platform host, mark unavailable package/runtime acceptance
as unverified; do not fabricate a binary or reuse a package from another SHA.

## Combined deterministic source gate

Run `bash tools/verify-project.sh` to execute the Python suite, Node behavior
suite, and native JavaScript syntax checks. It runs each gate, reports each
result, and exits nonzero if any gate fails. In sparse source checkouts, small
tracked metadata and legal notices required by tests should be present, while
large release binaries and platform core payloads may remain omitted. The
artifact manifest marks missing or hash-mismatched binaries as blocked, and the
download route must return 404 for them; this is not proof of an installable
package. Browser automation that needs `playwright-cli`, Android device tests,
and native package/runtime acceptance are unverified when their prerequisites
are absent.

## Protected player and release work

Before editing shared player/render/input/audio/save behavior, read
`docs/REGRESSION_GUARDS.md` and `docs/player-layering.md` and run the applicable
behavioral and live guards before and after the edit. For Android changes, use
`docs/android-regression.md`. Use the existing staging workflow for runtime
changes. Production deployment and public publication require explicit approval.
