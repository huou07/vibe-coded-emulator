# Agent Interaction Capability Audit

Date: 2026-09-17
Agent: opencode 1.18.31 (model opencode-go/deepseek-v4.1-flash)
Scope: what this agent can actually control and inspect across the Vibe Coded
Emulator (AN3 Arcade) web app, desktop packages, Android app, emulators, remote
build hosts, browsers, dev servers, and build/test/debug tooling.

Method: configuration inspection **plus** live, non-destructive capability
probes. Every "Verified" claim below was exercised in this session unless marked
otherwise. No tools were installed, no project configuration was changed, and no
persistent system changes were made.

Legend for matrices: ✅ verified working · ⚠️ partial/limited · ❌ not available ·
❓ unable to verify safely.

---

## Executive Summary

The project is unusually well instrumented for an agent, and most of the
hard-to-get capabilities already exist:

- **Web**: strong. `playwright-cli` 0.1.20 drives system Chrome with structured
  accessibility snapshots, console, network, storage, viewport control, and
  screenshots. Level 3–4.
- **Android emulator**: surprising strength. `adb` plus a **Chrome DevTools
  Protocol socket exposed by the app's WebView** gives full structured DOM
  control, and `screencap` gives visual verification. Level 3.
- **macOS desktop app**: launch/quit, real GUI click-through (synthesized
  CGEvents), screenshots, and a verified 3DS/Vulkan gameplay render. But no
  structured UI tree (the Tauri WebView is not exposed), so it is visual-guided
  coordinate control, not structured.
- **Linux**: headless Xvfb + `xdotool` (XTEST) + `scrot` on the authorized
  Debian builder gave verified gameplay rendering and input.
- **Windows VM**: reachable and controllable over SSH; strong process/PowerShell
  control and message-level window input; **no UI Automation tree** (session 0)
  and **no reliable visual capture** of composited surfaces.
- **Physical Android device**: none attached — Level 0.

The single biggest structural gap is **determinism**: the bundled native player
has no headless/frame-stepped/screenshot/save-state CLI, so no platform can run
a byte-comparable, frame-exact regression automatically. That is the highest-
leverage thing to add.

---

## Environment Inventory

| Name | OS / Arch | Physical / Virtual | Local / Remote | Connection | Control interface | Debug interface | Visual inspection | Limitations |
|---|---|---|---|---|---|---|---|---|
| Mac host (this machine) | macOS 26.6.2 (25G83), arm64 (Apple M5) | physical | local | shell | shell, `osascript`/System Events, CGEvent, `open`, `pkill` | `lldb`, `dtrace`, unified logs | `screencapture` (granted), `ffmpeg` | no full Xcode (no Instruments/GPU capture); system `python3` 3.9.6 without pytest/PIL/numpy; Docker daemon not running |
| `an3-dell` (private LAN host) | Debian 13 (trixie), x86_64 | physical | remote | SSH key-only + passwordless sudo | shell, Xvfb, `xdotool` (XTEST), Docker, libvirt | gdb not confirmed present; journald | `scrot`, `xwd`, `ffmpeg` (Xvfb framebuffer) | headless; Vulkan is software `llvmpipe`; libvirt needs `sudo` |
| `an3-win11-build` | Windows 11 build 26200, x64 | virtual (QEMU/KVM on Dell) | remote | SSH key-only via ProxyJump `an3-dell` | PowerShell 5.1, `Start-Process`, Win32 `EnumWindows`, `PostMessage` | none configured (no debugger/UIA) | ❌ none reliable (PrintWindow blank, no interactive desktop) | session 0 only; no interactive desktop; started/stopped with `sudo virsh` on the Dell |
| Android AVD `codex-nds-api35` | Android 15 (API 35), arm64 | virtual (local AVD) | local | `adb` (emulator-5554) | adb (install/launch/input/root) + WebView CDP | `logcat`, crash/ANR buffers, CDP | `adb exec-out screencap` | arm64 with Google APIs; contains the owner's existing test ROMs/saves (do not disturb) |
| Physical Android device | — | physical | — | — | — | — | — | **none connected** (`adb devices` empty) |
| Dell Docker daemon | Linux containers | virtual | remote | `sudo docker` | `docker ps/exec/...` | container logs | n/a | Daemon runs on the Dell only |

Not detected / not available in this environment: any additional VM,
Kubernetes cluster, or container runtime beyond the Dell Docker engine; no
physical Android hardware; no iOS targets (out of scope).

---

## Existing OpenCode Capabilities

- **Version**: opencode 1.18.31.
- **MCP servers** (from `~/.config/opencode/opencode.jsonc`):
  - `codegraph` — local, `/Users/meomeo/.local/bin/codegraph serve --mcp`,
    version 1.6.0, enabled for the main agent. Used throughout this session.
  - `chrome-devtools` — `npx -y chrome-devtools-mcp@latest`, enabled as a server
    but its tools are **disabled for the main agent** (`"chrome-devtools_*": false`)
    and enabled only on the `browser-debug` subagent. Verified the package
    resolves (`npx -y chrome-devtools-mcp@latest --help` printed its options).
- **Project skills** (`.opencode/skills/`): `an3-build`, `an3-codegraph-first`,
  `an3-player-regression`, `an3-staging-deploy`, `public-release-security`.
- **Global skills**: `~/.config/opencode/skills/vibe-coded-verification`
  (private device/test matrix), `~/.agents/skills/playwright-cli`,
  `~/.agents/skills/find-docs`.
- **Agents** (`.opencode/agent/`): `staging-browser-verify` (Playwright web
  verification), `player-verifier` (player regression + AVD smoke),
  `release-coordinator` (five-platform release). Global: `browser-debug`
  (Chrome DevTools MCP).
- **Project memory** (private, not reproduced): `~/.config/opencode/project-memory/vibe-coded-emulator.md`.
- **Codegraph index**: `.codegraph/` (db ~29 MB, live daemon, auto-sync).
- **No CI**: no `.github/workflows` or equivalent pipeline exists.

---

## Existing Tools and Integrations

Verified on the Mac host:

| Tool | Version / path |
|---|---|
| node / npm / npx | v24.19.0 / 11.17.0 / present |
| python3 | 3.9.6 (`/usr/bin/python3`; no pytest, PIL, numpy) |
| cargo / rustc | 1.98.0 |
| cmake / ninja / clang / gcc | present |
| git / gh / jq / curl | 2.50.1 / 2.101.0 / present / present |
| ffmpeg | 9.0.1 |
| lldb | 2100.0.17.203 |
| screencapture / sips / osascript | present |
| xcrun / codesign / hdiutil | present (CommandLineTools only) |
| dtrace | present |
| nc / tmux / ssh / scp / rsync | present |
| playwright-cli | 0.1.20 (`@playwright/cli`) |
| Google Chrome | 152.0.7977.83 |
| adb | 1.0.41 (platform-tools 37.0.1) |
| Docker client | present, daemon **not running** |

Android SDK (`~/Library/Android/sdk`): `build-tools`, `emulator`, `ndk`,
`platform-tools`, `platforms`, `system-images`; project `gradlew` present.

Verified on `an3-dell`: `ffmpeg`, `ffprobe`, `xdotool`, `scrot`, `xwd`, `Xvfb`,
`openbox`, `weston`, `node` 20.19.2, `cargo` 1.85.0, `docker` (daemon running),
`sudo -n` (passwordless), libvirt/QEMU.

Verified on `an3-win11-build`: PowerShell 5.1, node 24.21.0, npm 11.19.0,
cargo 1.98.1, CMake, Ninja, VS Build Tools, MSYS2 UCRT64, LunarG Vulkan SDK
1.4.357.0, plus the registered Microsoft-signed SwiftShader ICD
(`C:\AN3\swiftshader\vk_swiftshader_icd.json`).

**Not present** on the Mac (checked, absent): `chromium`, `scrcpy`, `maestro`,
`appium`, `renderdoc`/`renderdoccmd`, `apitrace`, `tshark`/`wireshark`,
`mitmproxy`, `tesseract`, `cliclick`, `perf`, `instruments`,
`imagemagick`/`magick`, `pngcheck`, `socat`, `watchman`. On the Dell:
`renderdoccmd`/`apitrace` absent.

---

## Web Interaction

Mechanism: **`playwright-cli`** (system Chrome via `--browser=chrome`) against a
locally started dev server. No project test suite exists for the web player as a
browser E2E suite; `tests/*.py` and `tests/*.test.js` are Python/Node unit and
DOM-contract tests only.

Evidence commands (all run, all succeeded):

```bash
AN3_PORT=8099 AN3_ENVIRONMENT=development nohup python3 app.py &
curl -s http://127.0.0.1:8099/health
playwright-cli open --browser=chrome http://127.0.0.1:8099/
playwright-cli snapshot
playwright-cli console            # "Total messages: 0 (Errors: 0)"
playwright-cli resize 390 844
playwright-cli screenshot --filename=/tmp/pw-390.png
playwright-cli requests
playwright-cli localstorage-list
playwright-cli eval "document.title + ' | links=' + document.querySelectorAll('a').length"
```

| Web operation | Possible? | How |
|---|---|---|
| start app / detect URL | ✅ | `python3 app.py` (default port 8091, override `AN3_PORT`); `/health` returns `asset_version`, `release_id`, `environment` |
| open browser / navigate | ✅ | `playwright-cli open/goto` |
| DOM / accessibility tree | ✅ | `playwright-cli snapshot` (YAML with `ref=` handles) |
| click / fill / type / press / hover / select / upload / drag-drop | ✅ | `click`, `fill`, `type`, `press`, `hover`, `select`, `upload`, `drop`, `drag` |
| scroll / mouse / keyboard modifiers | ✅ | `mousewheel`, `mousemove/down/up`, `keydown/keyup` |
| resize / mobile viewport | ✅ | `resize 390 844` (verified, screenshot captured) |
| reload / back / forward / tabs | ✅ | `reload`, `go-back`, `go-forward`, `tab-*` |
| dialogs | ✅ | `dialog-accept` / `dialog-dismiss` |
| console + JS errors | ✅ | `console` (caught a 404 on `/multiplayer`) |
| network requests / status | ✅ | `requests` (static hidden by default), `route` for mock/fault injection |
| localStorage / sessionStorage / cookies | ✅ | `localstorage-*`, `sessionstorage-*`, `cookie-*` |
| screenshots / PDF | ✅ | `screenshot`, `pdf` (agent can read the PNG) |
| traces / video / action recording | ✅ | `tracing-start/stop`, `video-start/stop`, `recording-start/stop`, `video-show-actions` |
| performance info | ⚠️ | not a first-class command; reachable via `run-code` (CDP `Performance`), not verified here |
| automated repeatable tests | ⚠️→✅ | `run-code --filename=script.js` can script assertions; no committed suite yet |

---

## Android Physical Device

**Level 0.** `adb devices -l` returned no rows. No physical device is attached,
so none of install/launch/input/logs/screenshots could be exercised on real
hardware. All Android findings below are **emulator-only** and must not be
reported as physical-device evidence.

---

## Android Emulator

Mechanism: `adb` (emulator-5554) **plus** a Chrome DevTools Protocol socket the
app's WebView exposes. The AVD `codex-nds-api35` is Android 15 / API 35 / arm64.

Evidence commands (all succeeded):

```bash
emulator -avd codex-nds-api35 -no-window -no-audio -no-boot-anim -gpu swiftshader_indirect &
adb wait-for-device && adb shell getprop sys.boot_completed
adb install -r -d native-offline/releases/vibecodedemulator-2.2.0-android-arm64-staging.apk
adb shell am start -n space.an3tocom.offline/.MainActivity
adb shell uiautomator dump /sdcard/an3.xml        # only an opaque WebView node
adb shell cat /proc/net/unix | grep webview_devtools_remote_<pid>
adb forward tcp:9222 localabstract:webview_devtools_remote_<pid>
curl -s http://127.0.0.1:9222/json/list           # page: appassets.androidplatform.net/index.html
# Node 24 native WebSocket -> Runtime.evaluate read title, URL, 40 interactive nodes, body text
adb shell input tap 360 1220
adb shell input text "emerald"                    # read back "emerald" via CDP
adb shell input swipe 360 900 360 400 200
adb shell input keyevent KEYCODE_BACK
adb shell settings put system user_rotation 1     # observed ROTATION_90, then restored
adb shell screenrecord --time-limit 3 /sdcard/rec-audit.mp4 && adb pull ...
adb push probe.txt /sdcard/Download/ && adb shell cat /sdcard/Download/probe.txt
adb root && adb shell ls /data/data/space.an3tocom.offline/an3-roms/
adb shell am force-stop space.an3tocom.offline
adb unroot
```

| Android emulator operation | Possible? | How |
|---|---|---|
| detect device / model / ABI / SDK | ✅ | `adb devices -l`, `getprop ro.product.*`, `ro.build.version.sdk` |
| SDK / adb / Gradle | ✅ | SDK at `~/Library/Android/sdk`; `gradlew` in the Tauri Android project |
| install / update APK | ✅ | `adb install -r -d <apk>` |
| launch / stop / restart | ✅ | `adb shell am start`, `am force-stop` |
| clear logs / capture / filter logcat | ✅ | `adb logcat -c`, `adb logcat -d`, `-b crash` |
| crashes / ANRs | ✅ | `logcat -b crash`, `/data/anr/` accessible (empty at test time) |
| process / package info | ✅ | `pidof`, `dumpsys window`, `dumpsys package` |
| tap / text / swipe / nav keys | ✅ | `input tap/text/swipe/keyevent` |
| rotate / orientation | ✅ | `settings put system user_rotation` (verified ROTATION_90, restored) |
| screenshots / record screen | ✅ | `exec-out screencap`, `screenrecord` + `pull` |
| retrieve app-produced files | ✅ | `adb root` + read `files/`, `an3-roms/`, `shared_prefs/` |
| push test files | ✅ | `adb push` (verified to `/sdcard/Download`) |
| **UI hierarchy / accessibility tree** | ⚠️ | `uiautomator` returns **only one `android.webkit.WebView` node** (`NAF="true"`, no children) — the app UI is invisible to it |
| **structured app UI control** | ✅ | **WebView CDP** over `adb forward` — read DOM, click, focus, read back values |
| automated UI flows | ✅ | adb + CDP scripting (verified primitives) |
| capture frame/rendering output | ⚠️ | screen-level `screencap` only; no in-engine framebuffer |
| GPU/rendering logs | ✅ | `logcat` (`Gralloc4`, EGL/Vulkan tags) |

**Important accuracy note:** on this app `uiautomator` is nearly useless because
the UI is a single WebView. Structured control comes from CDP, which requires
`adb root` (or a debuggable build) to reach `webview_devtools_remote_<pid>`.
That socket was present on the 2.2.0 release APK **as installed on the AVD**;
do not assume it is present on every build/device.

**Not exercised (deliberately):** launching `NativeGameActivity` with a ROM. The
AVD already contains the owner's commercial-sized `.3ds`/`.nds` test files
(e.g. 1.8 GB titles) plus saves; pushing a new ROM or touching that directory
risks confusing protected state. The capability exists (`adb root` reaches the
`an3-roms/` dir and the activity is defined) and is documented by the
`player-verifier` agent, but it was left **UNVERIFIED in this audit**.

---

## macOS Desktop

Mechanism: `open -a` to launch; **System Events** (Accessibility, granted) for
window geometry; **CGEvent** synthesis for real GUI clicks; `screencapture` for
visual capture.

Verified earlier in this session (RG-114): launched the packaged 2.2.0 `.app`,
screenshotted the window, drove the real GUI with synthesized clicks
(`Open ROM` → native file picker → `Open` → `Play 3DS native`), and observed the
3DS Homebrew Launcher rendering at **60.0–60.3 FPS · Vulkan**.

| macOS desktop operation | Possible? | How / evidence |
|---|---|---|
| build / launch / kill | ✅ | `npm run build:macos`; `open -a`; `pkill`/`kill` |
| stdout/stderr / logs | ✅ | shell redirection; `log stream`/`log show` available |
| attach debugger | ✅ | `lldb` (verified loading `/bin/ls`) |
| GUI click / keyboard | ⚠️ | CGEvent clicks and `osascript` **work**, but System Events keystrokes go to the *frontmost* app — a `Cmd+Q` was misrouted and the app had to be `pkill`ed |
| identify UI elements | ❌ | System Events sees only the window (title/bounds); the Tauri WebView exposes **no** AX tree to it |
| window manipulation / resize | ✅ | `System Events` set `position`/`size`, `activate` |
| screenshots / screen recording | ✅ | `screencapture -R` (permission granted); `ffmpeg`/`screencapture -v` for video |
| accessibility info | ⚠️ | Accessibility is granted, but only window-level info is available |
| automated repeatable UI tests | ⚠️ | coordinate + screenshot verification is possible; no structured locators |

There is **no CLI `--rom` path** for the macOS app: the 3DS host is linked
in-process (`azahar_host.mm`), so headless/CI gameplay is not possible without
GUI automation.

---

## Windows

Mechanism: SSH (ProxyJump through `an3-dell`) into the `an3-win11-build` VM;
`sudo virsh` on the Dell starts/stops it.

| Windows operation | Possible? | How / evidence |
|---|---|---|
| build / deploy / launch / kill | ✅ | PowerShell + `Start-Process`; verified in the 2.2.0 build cycle |
| stdout/stderr / logs | ✅ | PowerShell redirection; `Get-Content`; no ETW configured |
| window enumeration | ✅ | Win32 `EnumWindows` found 3 windows for the Tauri app (`VibeCodedEmulator`, etc.) |
| GUI input | ⚠️ | `PostMessage` (message-level) works — earlier drove pause/resume on the native runtime; `WM_CLOSE` had no effect (Tauri close path) |
| structured UI (UIA) | ❌ | `System.Windows.Automation` found **no window** (session 0 isolation) |
| screenshots / visual | ❌ | `PrintWindow` returned blank for the composited/Vulkan surface; no interactive desktop |
| debugger | ❌ | no WinDbg/VS debugger configured |
| playback/GPU | ⚠️ | SwiftShader software Vulkan (`vulkaninfo` → SwiftShader Device, 1.3.0, CPU) |

Windows is the weakest desktop target for autonomous testing: strong process and
message-level control, no structured UI and no reliable visual verification.

---

## Linux

Mechanism: SSH to `an3-dell`; headless X via `Xvfb` + `openbox`; `xdotool`
(XTEST — the real input path, not synthetic `XSendEvent`); `scrot` for the Xvfb
framebuffer; the DEB bundles a CLI player that accepts `--rom … --system 3ds
--renderer vulkan`.

Verified earlier in this session (RG-114): ran `boot.3dsx` on `llvmpipe` Vulkan,
screenshotted the fully rendered 3DS Homebrew Launcher, and confirmed input
(F4 toggled fullscreen 1280×720↔1280×900; F1 changed layout; `z`/B/Cancel
changed the emulated screen).

| Linux operation | Possible? | How / evidence |
|---|---|---|
| build / launch / kill | ✅ | `build-linux-staging.sh`; CLI player; `pkill` |
| logs / stdout / stderr | ✅ | shell; `journald` |
| GUI input | ✅ | `xdotool` XTEST (keys, mouse) |
| structured UI | ❌ | GTK/SDL widget tree is not exposed to the agent; only X window geometry |
| screenshots / video | ✅ | `scrot`, `xwd`, `ffmpeg` on the Xvfb framebuffer |
| Docker | ✅ | daemon running; staging containers visible via `sudo docker ps` |
| debugger | ❓ | `gdb` presence not confirmed; not tested |
| GPU | ⚠️ | software `llvmpipe`; no RenderDoc/apitrace |

Two environment prerequisites were required and are reusable findings:
`AN3_OFFLINE_LIBDIR=<runtime dir>` (an uninstalled extracted DEB resolves cores
from the absolute `/usr/lib/an3-offline-native/libretro`) and
`SDL_AUDIODRIVER=dummy` (the headless host has no ALSA device).

---

## Remote Machines / SSH

- `~/.ssh/config` defines `192.168.1.8`, `an3-dell`, `an3-win11-build`
  (the last via `ProxyJump an3-dell`).
- Verified: `ssh an3-dell` (Debian 13) and `ssh an3-win11-build` (Windows, when
  the VM is running). Key-only auth; strict host-key checking; no password.
- File transfer: `scp` and `rsync` verified (build artifacts, source archives,
  dependency cache).
- Lifecycle: `sudo -n virsh -c qemu:///system start|list` verified; the Windows
  VM was started and gracefully shut down twice.
- Staging deploy: `tools/ssh/check-staging-key.sh` prints
  `STAGING_SSH_KEY_AUTH=PASS`; `./deploy-stage.sh` completed
  `STAGING_DEPLOY=PASS` (asset `f2c429f14adc`).
- Production host reachable but **out of scope / never touched** without owner
  approval.

---

## Browser Automation

- **Verified**: `playwright-cli` 0.1.20 with system Chrome 152. Structured
  snapshots, refs, click/fill/type/press, console, network, storage, viewport,
  screenshots, tracing/video, `run-code`.
- **Configured but not exercised for the app**: `chrome-devtools` MCP
  (`npx -y chrome-devtools-mcp@latest`) — server config present, package
  resolves; tools are disabled for the main agent and available to the
  `browser-debug` subagent. It also supports `--browserUrl`/`--wsEndpoint`, so it
  could attach to the same CDP endpoint used for Android.
- **Project agent** `staging-browser-verify` documents the intended Playwright
  flow for the staging surfaces (`/`, `/multiplayer`, `/controller`,
  `/controller/join`, `/play/<slug>`).
- Not present: Puppeteer, Selenium, WebDriver, Maestro, Appium.

---

## GUI Automation

| Surface | Mechanism | Level |
|---|---|---|
| Web | playwright-cli (a11y refs) | structured |
| Android emulator | CDP DOM + adb input | structured |
| macOS app | System Events + CGEvent + screencapture | visual-guided coordinate |
| Linux app | xdotool XTEST + scrot | visual-guided coordinate |
| Windows app | Win32 `EnumWindows` + `PostMessage` | message/coordinate |

Cross-cutting limitation observed on macOS: System Events `keystroke` is
delivered to the frontmost application, which caused a misrouted `Cmd+Q`; a
robust desktop automation loop needs explicit per-app activation and
window-ID-scoped capture (the working `screencapture -R` approach used window
geometry from System Events).

---

## Visual Inspection

- The agent can **read images** (screenshots, PNG captures) directly — verified
  repeatedly this session (Android UI, macOS app, macOS game frame, web mobile
  screenshot, Linux 3DS frames).
- Capture sources: `screencapture` (macOS, granted), `scrot`/`xwd`/`ffmpeg`
  (Linux Xvfb), `adb exec-out screencap` (Android), `ffmpeg` (both).
- **No OCR CLI** (`tesseract` absent) and **no image-diff tooling** (no
  ImageMagick, no Python PIL/numpy). Visual comparison is therefore agent-vision
  based, not pixel-metric based.
- Windows: no working composited-surface capture.

---

## Logging and Debugging

| Capability | macOS | Windows | Linux (Dell) | Android (AVD) |
|---|---|---|---|---|
| stdout/stderr | ✅ | ✅ | ✅ | ✅ (logcat) |
| app logs | ✅ | ✅ | ✅ | ✅ |
| crash buffers | ⚠️ (`lldb`/crash reports) | ❌ | ⚠️ (core dumps) | ✅ `logcat -b crash`, `/data/anr/` |
| stack traces | ✅ `lldb` | ❌ | ❓ | ✅ (tombstones if they occur) |
| process state | ✅ `ps`/`pgrep` | ✅ PowerShell | ✅ | ✅ `dumpsys`, `pidof` |
| CPU / memory | ⚠️ `top`/`ps` | ⚠️ `Get-Process` | ⚠️ `top` | ⚠️ `dumpsys meminfo` |
| GPU/rendering | ⚠️ Eden/Azahar logs | ⚠️ SwiftShader logs | ⚠️ llvmpipe logs | ⚠️ logcat EGL/Gralloc |
| screenshots | ✅ | ❌ | ✅ | ✅ |
| frame capture | ❌ in-engine | ❌ | ❌ | ❌ |
| UI state | ⚠️ window-level | ❌ | ⚠️ window-level | ✅ CDP DOM |
| network | ⚠️ `curl`; browser request list | ⚠️ | ⚠️ | ⚠️ |

No packet capture (`tshark`/`mitmproxy` absent) and no profilers
(`perf`/Instruments absent) are available.

---

## Rendering / GPU Debugging

- Eden (Switch bridge) logs rich Vulkan creation detail; Azahar logs device,
  extension, swapchain, and present-window lines; both were used this session.
- Android `logcat` carries EGL/Gralloc/`swiftshader` tags.
- **No GPU frame capture**: RenderDoc, apitrace, and Xcode Metal/GPU capture are
  all absent. Vulkan layer `VK_LAYER_LUNARG_api_dump` ships with the installed
  LunarG SDK on the Windows VM and could be used for API tracing, but that was
  not exercised.
- **No in-engine framebuffer readback**: only whole-screen capture.

---

## Build / Deploy Automation

| Target | Build command (verified/known) | Host | Automated? |
|---|---|---|---|
| macOS DMG | `npm run build:macos` | Mac | ✅ (verified 2.2.0) |
| Android APK | `scripts/build-android-staging.sh` | Mac | ✅ (verified 2.2.0) |
| Linux DEB | `scripts/build-linux-staging.sh deb` | Dell | ✅ (verified 2.2.0) |
| Linux Flatpak | `scripts/build-linux-staging.sh flatpak` | Dell | ✅ (verified 2.2.0) |
| Windows EXE | `build-windows-runtime.ps1` + `build-windows-staging.ps1` | Windows VM | ✅ (verified 2.2.0) |
| Staging deploy | `./deploy-stage.sh` | Mac → staging | ✅ (`STAGING_DEPLOY=PASS`) |
| Catalog check | `tools/verify-release-catalog.py` | Mac | ✅ (`RELEASE_CATALOG=PASS`) |

`tools/release-train.sh --coordinated` exists but its artifact-copy step still
hard-codes **0.4.5** filenames, so the coordinated matrix path is stale and
would fail at collection; per-platform builders were used directly instead.

---

## Reproducible Testing

- Python: `python3 -m unittest discover -s tests` → **285 tests, OK**.
- Node DOM/contract tests: `node tests/*.test.js` (3 files) → pass.
- Native harnesses: `tests/native/*` (C++ host harness, fake libretro symbols).
- Eden bridge smoke: `an3_eden_bridge_smoke` (null 38, Eden error-path 39,
  Eden + NRO 50 checks).
- Player regression package: `.opencode/skills/an3-player-regression` +
  `player-verifier` agent.
- **Gap**: no cross-platform end-to-end, no frame-deterministic test, no
  screenshot-diff regression, no committed browser E2E suite.

---

## Emulator-Specific Automation

Which steps of the ideal emulator debug loop are currently possible:

| Step | Status | Notes |
|---|---|---|
| 1 build | ✅ | per-platform builders verified |
| 2 deploy | ✅ | adb install / scp / staging deploy |
| 3 launch | ✅ | adb am start / open / Start-Process / CLI player |
| 4 load a ROM | ⚠️ | Linux/Windows CLI `--rom`; macOS GUI only; Android needs app-data write (not exercised) |
| 5 load a save state | ⚠️ | runtime has F5/F9 quick slots; no CLI flag; trigger only via synthesized input |
| 6 navigate to a scene | ⚠️ | via input, but no scripted/deterministic input sequence |
| 7 run a fixed number of frames | ❌ | no headless/frame-step mode |
| 8 capture framebuffer | ❌ | screen capture only |
| 9 capture logs | ✅ | all platforms |
| 10 renderer/GPU diagnostics | ⚠️ | core logs only; no API trace |
| 11 compare to known-good | ❌ | no image/metric diff tooling |
| 12 identify a regression | ❌ | manual/visual only |
| 13 modify code | ✅ | agent edits |
| 14 rebuild | ✅ | verified |
| 15 rerun the exact same test | ⚠️ | manual repeat; not deterministic |

---

## Capability Matrix

| Target | Detect | Build | Launch | Structured UI Control | Visual Inspection | Logs | Screenshot | Automated Test | Debug |
|---|---|---|---|---|---|---|---|---|---|
| Web app | ✅ | n/a | ✅ | ✅ (playwright refs) | ✅ | ✅ | ✅ | ⚠️ (primitives; no suite) | ✅ |
| macOS desktop | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ⚠️ | ✅ (lldb) |
| Windows desktop | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ | ⚠️ (build only) | ❌ |
| Linux desktop | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ⚠️ | ❓ |
| Android app (emulator) | ✅ | ✅ | ✅ | ✅ (CDP) | ✅ | ✅ | ✅ | ⚠️ (primitives; no script) | ✅ |
| Android app (physical) | ❌ | n/a | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Android system UI | ✅ | n/a | n/a | ✅ (uiautomator) | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| Eden Switch bridge | ✅ | ✅ | ✅ | n/a (CLI) | ✅ | ✅ | ⚠️ (screen) | ✅ (smoke) | ✅ |
| Remote Dell | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ⚠️ | ❓ |
| Remote Windows VM | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ | ⚠️ | ❌ |
| Docker (Dell) | ✅ | n/a | ✅ | n/a | n/a | ✅ | n/a | ⚠️ | ⚠️ |

---

## Interaction-Level Matrix

| Target | Level | Actual mechanism | Evidence |
|---|---:|---|---|
| Web | **3** (4 achievable) | playwright-cli: a11y snapshot refs + console/network/storage + screenshots + `run-code`/tracing | `snapshot` refs, `console` (404 caught), `resize`+`screenshot`, `localstorage-list` |
| Android physical | **0** | none | `adb devices` empty |
| Android emulator | **3** (4 achievable) | WebView CDP DOM + adb input + screencap | CDP `Runtime.evaluate` → title/URL/40 nodes; `input text`+CDP read-back; `screencap` |
| macOS desktop app | **2** (visual-guided coordinate; no structured tree) | System Events window info + CGEvent clicks + `screencapture` | file picker driven by clicks; 60 FPS Vulkan frame captured |
| Windows desktop app | **1** | Win32 `EnumWindows` + `PostMessage` | 3 windows found; message input drove pause/resume; UIA found none |
| Linux desktop app | **2** (visual-guided coordinate; no structured tree) | `xdotool` XTEST + `scrot` on Xvfb | F4/F1/z input; rendered 3DS frames captured |

Level definitions: 0 none · 1 blind coordinate/message · 2 structured **or**
visual (this audit reports the hybrid explicitly) · 3 structured + visual · 4
automated reproducible. Levels are **not** inflated: macOS/Linux have no
structured UI tree, and Windows has no reliable visual.

---

## What You Can Do Right Now

Web (verified):

```bash
AN3_PORT=8099 AN3_ENVIRONMENT=development python3 app.py &
playwright-cli open --browser=chrome http://127.0.0.1:8099/
playwright-cli snapshot && playwright-cli console && playwright-cli requests
playwright-cli resize 390 844 && playwright-cli screenshot --filename=/tmp/m.png
```

Android emulator (verified):

```bash
emulator -avd codex-nds-api35 -no-window -gpu swiftshader_indirect &
adb install -r -d native-offline/releases/vibecodedemulator-<v>-android-arm64-staging.apk
adb shell am start -n space.an3tocom.offline/.MainActivity
adb shell uiautomator dump /sdcard/u.xml && adb pull /sdcard/u.xml
adb exec-out screencap -p > /tmp/an3.png
adb shell input tap <x> <y> && adb shell input text "hello"
# structured DOM control:
adb root; adb forward tcp:9222 localabstract:webview_devtools_remote_$(adb shell pidof space.an3tocom.offline)
curl -s http://127.0.0.1:9222/json/list
```

macOS desktop (verified):

```bash
open -a ".../VibeCodedEmulator.app"
osascript -e 'tell application "System Events" to tell process "an3-offline-native" to get {position, size} of window 1'
screencapture -R<x>,<y>,<w>,<h> -x /tmp/app.png     # agent reads the PNG
```

Linux desktop (verified):

```bash
ssh an3-dell   # then
export DISPLAY=:96 AN3_OFFLINE_LIBDIR=<runtime-dir> SDL_AUDIODRIVER=dummy
Xvfb :96 -screen 0 1280x900x24 & openbox &
<runtime>/an3-offline-native --rom /tmp/boot.3dsx --system 3ds --renderer vulkan &
xdotool key F4 ; scrot -o /tmp/shot.png
```

Remote/build/debug (verified): `ssh an3-dell`, `ssh an3-win11-build`,
`sudo -n virsh … start|list an3-win11-build`, `rsync`/`scp`, `sudo docker ps`,
`lldb`, `ffmpeg`, `./deploy-stage.sh`, `python3 tools/verify-release-catalog.py`.

---

## What You Cannot Do Right Now

- No physical Android device control (none attached).
- No structured UI control of the **macOS**, **Windows**, or **Linux** desktop
  apps (no DOM/AX/UIA tree for the native or Tauri surfaces).
- No reliable visual verification on **Windows** (composited/Vulkan capture
  blank; session 0).
- No in-engine framebuffer capture or frame-stepped/headless emulation on any
  platform.
- No deterministic save-state load via CLI (F5/F9 only, input-driven).
- No image-diff / pixel-comparison regression tooling.
- No GPU frame capture (RenderDoc/apitrace/Instruments absent).
- No packet capture for netplay debugging.
- No CI; the coordinated release-train path is stale (hardcoded 0.4.5).
- No committed browser E2E suite (only interactive `playwright-cli`).
- No CLI entry point for the macOS app (GUI-only).
- No profiling (CPU/GPU) beyond coarse `ps`/`top`.

---

## Current Debugging Workflow

The best loop using only what exists today:

1. **Understand** — `codegraph_explore` (indexed, mandatory by repo policy).
2. **Unit/contract** — `python3 -m unittest discover -s tests` (285) and
   `node tests/*.test.js`.
3. **Build** — the appropriate per-platform builder (Mac/Dell/Windows).
4. **Deploy/launch** — `adb install/am start`, `open -a`, CLI player, or
   `Start-Process`.
5. **Observe** — logs (shell/logcat/PowerShell), `screencap`/`screencapture`/
   `scrot`, and for web/Android the CDP devtools (console/network/DOM).
6. **Interact** — playwright-cli (web), CDP + `adb input` (Android), CGEvent
   (macOS), `xdotool` (Linux), `PostMessage` (Windows).
7. **Compare** — agent vision on screenshots against expectations.
8. **Fix + rebuild + repeat** — manual rerun of the same commands.

This works, but steps 7–8 are manual and non-deterministic.

---

## Major Bottlenecks

1. **No deterministic emulator harness** (headless frames/screenshot/save-state)
   — blocks frame-exact regression on all five platforms.
2. **No structured UI for desktop apps** — desktop verification is coordinate +
   screenshot at best, impossible on Windows.
3. **Android structured control depends on an undocumented CDP forwarding step**
   — powerful but not packaged or documented in the repo.
4. **No CI and a stale coordinated release path** — builds are manual across
   three hosts and can silently drift.
5. **No GPU/frame-level debugging or image diffing** — renderer regressions can
   only be judged by eye.
6. **Windows is a blind target** (no UIA, no composited capture).
7. **No physical Android device** in this environment.

---

## Recommended Improvements

**P0 — strongly recommended**

1. **Headless deterministic mode for the native player.**
   Add flags such as `--headless --frames N --no-audio --screenshot out.png`
   and `--load-state <path>` to `an3-native-runtime` (and the bundled
   per-platform players), emitting a JSON status line. *Solves:* frame-stepped,
   reproducible, screenshot-based regression on every platform. *Overlap:*
   reuses `libretro_host`/`renderer_contract`; overlaps nothing external.
   *Benefit:* the largest single gain for autonomous debugging.
   *Complexity:* medium. *Maintenance:* low. *Token cost:* low (one CLI).
   *Scope:* project-local. *Cost:* none.
2. **A committed Android UI automation helper.**
   A small `tools/android-ui.*` that resolves the app PID, forwards
   `webview_devtools_remote_<pid>`, and exposes `eval/click/screenshot/logcat`
   over CDP, plus a README note. *Solves:* structured Android app control is
   currently tribal knowledge. *Overlap:* complements `adb`/`uiautomator`.
   *Benefit:* repeatable Android UI flows without a heavy framework.
   *Complexity:* low. *Maintenance:* low. *Token cost:* low. *Scope:*
   project-local. *Cost:* none.
3. **Screenshot-diff regression harness.**
   Drive the headless player (P0-1) to emit frames and compare against committed
   baselines with a small pixel-diff (Node `pixelmatch`+`pngjs`, or Python
   Pillow in a venv). *Solves:* no automated visual regression today.
   *Overlap:* builds on P0-1. *Benefit:* catches renderer/layout regressions.
   *Complexity:* medium. *Maintenance:* medium (baseline churn). *Token cost:*
   low. *Scope:* project-local. *Cost:* none.
4. **Fix `tools/release-train.sh --coordinated`** (stale 0.4.5 filenames) and
   add a single "verify all" local job. *Solves:* manual, drift-prone releases.
   *Overlap:* the per-platform builders already exist. *Benefit:* one-command
   cross-host release. *Complexity:* low. *Maintenance:* low. *Scope:*
   project-local. *Cost:* none.

**P1 — useful**

5. **Committed Playwright suite** for the web player surfaces, using the
   installed `playwright-cli`/`@playwright/test` (or `run-code` scripts).
   *Overlap:* `playwright-cli` already verified; this adds assertions/CI.
   *Benefit:* deterministic web regression. *Complexity:* low-medium.
   *Maintenance:* low. *Token cost:* low. *Scope:* project-local. *Cost:* none.
6. **GPU API tracing via the installed LunarG layer** (`VK_LAYER_LUNARG_api_dump`
   on the Windows VM) and/or RenderDoc on the Dell. *Overlap:* supplements core
   logs. *Benefit:* diagnose renderer bugs. *Complexity:* medium.
   *Maintenance:* low. *Cost:* none (RenderDoc is a free download).
7. **A macOS deep-link/CLI launch path** (`open -a … --args --rom <path>` or a
   custom URL scheme) so macOS gameplay is testable without GUI automation.
   *Solves:* macOS has no headless entry point. *Complexity:* low-medium.
   *Scope:* project-local.
8. **Add `gdb` and confirm core-dump handling on the Dell** for Linux crash
   triage. *Complexity:* low. *Scope:* global (builder image).

**P2 — optional**

9. Maestro/Appium for Android — only if the native Android UI grows beyond the
   WebView; overlaps the lighter CDP approach and adds maintenance.
10. `scrcpy` — useful for physical-device visual control, but no device is
    attached today.
11. `tesseract`/OCR — largely redundant because the agent already reads images.
12. Playwright MCP — overlaps the verified `playwright-cli`; add only if a
    structured in-agent tool surface is preferred over shell calls.
13. `tshark`/`mitmproxy` — only if netplay transport debugging becomes routine.

---

## P0 / P1 / P2 Roadmap

- **P0**: headless deterministic player mode; Android CDP helper; screenshot-diff
  harness; refresh the coordinated release script.
- **P1**: committed Playwright suite; GPU API tracing; macOS CLI/deep-link; Dell
  `gdb`.
- **P2**: Maestro/Appium, scrcpy, OCR, Playwright MCP, packet capture.

---

## Suggested Ideal Architecture

```
opencode
  → code intelligence        (codegraph MCP — verified)
  → build                    (per-platform builders; refresh release-train)
  → deploy                   (adb / scp / deploy-stage.sh)
  → structured UI automation (playwright-cli web · WebView CDP Android
                              · xdotool macOS/Linux desktop)
  → visual verification      (screencapture / scrot / adb screencap
                              · agent vision on PNGs)
  → headless + frame-stepped (NEW native player mode — P0)
  → logs / GPU diagnostics   (core logs + Vulkan api_dump / RenderDoc)
  → deterministic regression (NEW screenshot-diff harness — P0)
  → code review              (git diff + regression guards)
```

---

## Exact Next Steps

1. Add the headless player mode (`--headless --frames --screenshot
   --load-state --no-audio`) and a machine-readable status line; document it in
   `docs/` and `native/eden-bridge/README.md`-style files.
2. Commit `tools/android-ui.*` wrapping the CDP forwarding and DOM eval/click;
   add a short README and one smoke script.
3. Build the screenshot-diff harness on top of the headless mode with committed
   baselines for GBA/NDS/3DS on at least macOS and Linux.
4. Repair `tools/release-train.sh --coordinated` to derive filenames from the
   version field instead of hard-coded `0.4.5`, then add a local "verify all" job.
5. Add a committed Playwright spec set for the web surfaces and wire it into the
   existing release verification.
6. Add RenderDoc (Dell) and/or use `VK_LAYER_LUNARG_api_dump` (Windows SDK) to
   capture a Vulkan frame for the 3DS path.
7. Add a macOS CLI/deep-link ROM launch path to remove GUI-only testing.
8. When physical Android hardware is available, add `scrcpy` and extend the AVD
   smoke to the device.

No installations or project modifications were performed during this audit;
these are proposals only.
