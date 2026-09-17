# Agent control plane (`an3ctl`)

Status: **implemented and verified for web, Android emulator, and the native
emulator runtime; desktop shells designed with a concrete unblock path.**
See the phase table at the end for exact per-phase status.

This document is the design contract behind `tools/an3ctl/`. It exists so an
agent can operate, inspect, test, debug, fix, rebuild, and re-test the project
through structured CLI output — without screenshot interpretation, coordinate
guessing, native file dialogs, or a human clicking.

## 1. Goal and non-goals

**Goal.** One consistent, machine-readable interface to every target:

```bash
an3ctl targets --json
an3ctl app start|stop|state --target web|android
an3ctl ui tree|query|click|fill|press|wait|text|value --target web|android ...
an3ctl logs --target web|android
an3ctl rom load <path> --target android
an3ctl emulator status|snapshot|baseline|diff|state|input --rom <fixture> ...
an3ctl test smoke --target web|android|emulator
```

**Non-goals.** Screenshot interpretation, coordinate clicking, OCR, Finder/Open
dialogs, and `xdotool`/CGEvent/`PostMessage` are **not** part of the normal path.
They remain optional diagnostics only.

## 2. Principles

1. Real application APIs/protocols over GUI simulation.
2. DOM/accessibility/test IDs over coordinates.
3. JSON over prose parsing.
4. One-shot deterministic commands.
5. Every command returns a meaningful exit status.
6. Errors carry stable machine-readable codes.
7. Compact, LLM-sized output — never a raw DOM dump.
8. `--json` for every command an agent uses.
9. No secrets in output.
10. Debug/control interfaces never ship enabled in production.
11. Reuse existing application logic; the CLI does not duplicate it.
12. Platform specifics live behind adapters.
13. No heavy framework where a verified protocol already works.

### Exit codes

| Code | Meaning |
| ---: | --- |
| 0 | success |
| 1 | internal error |
| 2 | usage error |
| 3 | target unavailable |
| 4 | element/entity not found |
| 5 | timeout |
| 6 | action failed |
| 7 | invalid state |

### Envelope

```json
{"ok":true,"command":"ui query","target":"android","data":{...}}
{"ok":false,"command":"ui query","target":"android",
 "error":{"code":"E_NOT_FOUND","message":"No element matched testid=nope"}}
```

## 3. Architecture

```
tools/an3ctl/
  bin/an3ctl                 launcher
  an3ctl.mjs                 argv parsing, dispatch, envelope/exit codes
  lib/core.mjs               envelope, exit codes, run(), selectors, CDP client, sha256
  lib/domtree.mjs            page-side compact semantic tree + locator (shared)
  adapters/web.mjs           Playwright (playwright-cli) — structured only
  adapters/android.mjs       adb + WebView CDP (auto forward/cleanup)
  adapters/emulator.mjs      native player deterministic test mode
  adapters/desktop.mjs       macOS/Linux/Windows structured-bridge status + probes
```

### Shared control boundary (the important part)

The emulator control plane does **not** invent a new surface. It drives the
existing `NativeCoreHost` boundary in `native-offline/native-runtime`:

- `status()` → `NativeCoreStatus{system, core_name, core_version, core_fps, core_frames, last_message, hardware_render_rejected}`
- `save_state/load_state/export_state/import_state`, `save_auto/load_auto`
- `set_core_option`, `set_screen_layout`
- `input()` → `NativeInput{set_button,set_buttons,set_pointer,set_analog,clear}`
- `run_one()` — one emulated frame

The player gained a **test-only deterministic mode** rather than a parallel API:

```
--headless --no-audio --no-controls --frames N
--capture out.png --capture-raw out.rgba --status-json
--load-state PATH --save-state PATH --input-seq "A@0-30;Start@40-45"
```

It emits one machine-readable line:

```
AN3CTL_STATUS {"system":"gba","renderer":"headless","core":"mGBA",...,"frames":120,"fps":59.7275,"width":240,"height":160,"captured":true,...}
```

`--headless` uses `video/capture/capture_backend.h` (a windowless, GPU-free
`NativeVideoBackend`) and `core/png_writer.h` (dependency-free, deterministic
PNG). Hardware-rendered 3DS content is **rejected** headless rather than faked
with a prohibited readback — see §7.

### Adapter: web

`playwright-cli` with a private session (`-s=an3-web`) against system Chrome.
`lib/domtree.mjs` builds a compact semantic tree and locator in the page; the
adapter navigates only when the requested document differs from the current one,
so `fill → value → click` flows keep state.

### Adapter: Android

Reuses the audit's verified path:
detect device → resolve PID → find `webview_devtools_remote_<pid>` → `adb
forward` → CDP → evaluate/act → **remove the forward**. Emulator-first; the same
code targets a physical device when a test/debug build exposes the socket.

### Adapter: emulator

Spawns the packaged/local player in deterministic mode (local or over SSH),
fetches the capture, hashes it, and diffs against a stored baseline. PASS/FAIL is
a machine verdict, never an image a human must read.

## 4. Structured UI contract

`ui tree` returns only interactive, relevant nodes:

```json
{"url":"…","title":"…","truncated":false,
 "nodes":[{"role":"button","name":"Open ROM","testId":"open-rom","id":null,
           "enabled":true,"visible":true}]}
```

Selection supports `--testid`, `--id`, `--role` (+`--name`), `--name`, `--text`,
`--css`, and `--nth`. Stable identifiers exist today in two equivalent forms:

- `data-testid` — added to the native shell's primary controls
  (`nav-play`, `nav-library`, `nav-settings`, `nav-help`, `nav-about`,
  `quick-*`, `open-rom`, `choose-rom`, `import-rom`, `search`, `game-grid`).
- Existing stable `id`s and `data-nav` attributes on the web and native
  surfaces (e.g. `gameSearch`, `modeSwitch`, `nativeAddRom`).

Prefer `--testid`/`--id`; never key off layout paths or coordinates.

## 5. Security

- Debug/control surfaces are **test-only**: the headless flags are opt-in CLI
  switches, the Android adapter requires a WebView devtools socket (release
  builds only expose it when the app enables WebView debugging), and the Windows
  probe expects a loopback-only debugging port on a test build.
- Remote debugging must bind **127.0.0.1** and be reached through **SSH
  forwarding**, never exposed on the LAN.
- No command prints tokens, keys, or credentials.

## 6. Verified evidence (this workspace)

| Capability | Evidence |
| --- | --- |
| `targets --json` | lists web/android/emulator/macos/linux/windows with reasons |
| web lifecycle | `app start/state/stop` on :8099 with correct PID tracking and health |
| web structured UI | `ui tree/query/click/fill/value/wait/press`; `fill`→`value` = `emerald`; missing element = exit 4; wait timeout = exit 5 |
| android structured UI | `ui tree` over WebView CDP (auto-forward); `click Settings`; `fill`/`value nativeSearch`; logs |
| emulator deterministic plane | `--headless --frames 120 --capture` → 240×160 GBA frame (PNG + raw RGBA); 3 runs → identical SHA-256 `395ba192…`; `diff` same = `match:true`; frames 1 vs 120 = `match:false, differentPixels:37327, differentPercent:97.21, maxChannelError:255` |
| exit codes | 0 ok / 4 not found / 5 timeout / 6 action failed observed |

## 7. Known limits

- **3DS headless capture** is not implemented: the Azahar core renders through
  Vulkan, and `capture_backend.h` refuses hardware frames rather than doing a
  GPU readback. Windowed bounded runs (`--frames N`) work on Linux/Windows under
  Xvfb/SwiftShader; a diffable 3DS capture needs a Vulkan swapchain readback
  (Phase 6b) or the GL path.
- **Desktop shells** (macOS/Linux/Windows Tauri apps) have no structured bridge
  yet — see Phase 3.
- The GBA fixture is used for the deterministic proof; NDS/3DS fixtures plus
  committed baselines are follow-up work.

## 8. Phase status

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | contract, adapters, reusable APIs, minimal changes | **done** (this doc) |
| 2 | web adapter + Android CDP adapter | **done and verified** |
| 3 | desktop structured adapters | **designed, blocked on a test-only bridge** |
| 4 | direct ROM load (no native dialog) | **partial**: `rom load --target android` and `--target emulator` implemented; web/desktop next |
| 5 | emulator status/load-state/step/headless/input | **done for software cores**; 3DS GPU capture outstanding |
| 6 | framebuffer hash/diff regression | **done for software cores** |
| 7 | committed suites + skill + docs | **in progress** (self-tests + skill landed) |

## 9. Phase 3 — desktop adapters (exact unblock)

The desktop shells are Tauri apps. Structured control must come from a WebView
devtools bridge, never coordinates.

- **Windows (WebView2, preferred):** enable remote debugging **only in a
  test/debug build**, bound to `127.0.0.1`. Then
  `ssh -L 9222:127.0.0.1:9222 an3-win11-build` and `an3ctl ui … --target windows`
  over CDP. `adapters/desktop.mjs` already probes this and returns the exact
  instruction when it is closed.
- **Linux:** run the Tauri app with WebKitGTK WebDriver
  (`WEBKIT_WEB_DRIVER`/`webkit2gtk-driver`) under Xvfb and expose the WebDriver
  endpoint on loopback.
- **macOS:** the current official Tauri WebDriver path is the first choice; if it
  cannot expose the required semantic tree, add a **test-only in-app automation
  bridge** (loopback HTTP or a Unix socket) that shares the app's command layer
  and returns JSON. It must be compiled out of release builds.

## 10. Exact next steps

1. Add `--capture` GPU readback (or a GL capture path) so 3DS frames are
   diffable; add committed NDS/3DS baselines.
2. Land the Windows WebView2 test-build flag (loopback only) and wire
   `--target windows` to CDP.
3. Implement the macOS test-only automation bridge and the Linux WebKitWebDriver
   path.
4. Extend `rom load` to web (dev-only route) and the desktop bridge, sharing one
   application command.
5. Wire `an3ctl test e2e` per platform into the release verification.
