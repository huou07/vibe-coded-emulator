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

## Debian development after a macOS checkout

Do not transfer `node_modules`, Rust `target`, Tauri `dist` or native build
directories between operating systems. Keep checked-in lockfiles, legal notices,
source and user data. Reinstall npm dependencies with `npm ci` in
`native-offline` only when native tooling is needed; the Python web server and
the lightweight gate do not need npm packages.

The default desktop commands now select the host:

| Command in native-offline | Linux | macOS | Windows |
| --- | --- | --- | --- |
| `npm run build` | Complete Linux staging DEB script | macOS app build | Windows staging script |
| `npm run dev` | Prepared Linux player + Tauri shell | macOS preparation + Tauri shell | Prepared Windows player + Tauri shell |

`npm run build:deb` uses `native-offline/scripts/build-linux-staging.sh deb`, which fetches
the pinned Linux cores, builds and stages the native player and then packages
the shell. Calling Tauri's DEB bundler alone omits that preparation. Linux and
Windows dev commands stop with a diagnostic when the native player is absent.
The build routing can be inspected without compiling or downloading anything:

```sh
npm --prefix native-offline run build -- --print-plan
npm --prefix native-offline run dev -- --print-plan
```

On the inspected Debian x86_64 worker (2026-10-15), Python 3.13.5, Node 24.21.0,
npm 11.19.0 and SDL2/Vulkan/GTK3/WebKitGTK 4.1 development metadata are present.
The checkout initially lacked `@tauri-apps/cli`. Reinstalling with
`npm ci --ignore-scripts --no-audit --no-fund` selected the locked Linux CLI;
`npm run tauri -- --version` returned 2.11.4 and the lockfile was unchanged.
The lightweight gate passed on baseline `f97bb7c534a0` with the six pre-existing
working-tree edits retained. After the routing patch, native syntax checks,
documentation references and the Node suite passed (92 passed, 3 skipped).
Routing checks covered build/dev selection for all three desktop systems and
refusal to launch dev without a prepared player; these do not execute the
platform builders. Python 3.13 also emitted SQLite connection ResourceWarnings
in the existing suite; these were not treated as package installation failures.
Browser automation, device tests and native runtime/package acceptance remain UNVERIFIED. Continue web/source work
with the local gate; perform native compilation and packaging on the dedicated
builders under the existing host policy. Do not install macOS frameworks or
reuse Mach-O libraries on Linux.

## Combined deterministic source gate

Run `bash tools/verify-project.sh` to execute the Python suite, Node behavior
suite, and native JavaScript syntax checks. It runs each gate, reports each
result, and exits nonzero if any gate fails. It ends with
`VERIFY_SKIPS=<json>` (`tools/verify-skip-manifest.py`), which names every
skipped test with its reason so a green run cannot hide what it did not run; the
per-suite logs are kept under `work/verify-logs/`. In sparse source checkouts,
small
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
changes. The active owner mandate dated 2026-10-14 authorizes public source
publication, suitable GitHub releases and deployment of accepted versions through
the existing production path after its checks pass; see `AGENTS.md` for scope and
host boundaries.
