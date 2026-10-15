---
name: an3-control-plane
description: Use for VCE target discovery, process control, emulator input/save-state or deterministic runtime capture. The Web compatibility adapter delegates to Playwright; use platform-native mechanisms for native UI claims. Do not load for ordinary browser testing already grounded in Playwright.
---

# an3-control-plane

`an3ctl` retains project-specific target/process control and deterministic
emulator evidence. Read `docs/UI_TESTING.md` and choose evidence for the claim:
Playwright for browser semantics/interactions, screenshots for appearance,
native tooling for the actual desktop/Android app, and emulator probes for
gameplay. Do not route every UI question through an3ctl.

Launcher: `tools/an3ctl/bin/an3ctl` (repo root). All commands accept `--json`.

## Preconditions and boundaries

Do not load for documentation, packaging-only work or ordinary backend edits.
Read project guidance and the CLI contract; inspect `targets --json` before
choosing a target. Availability and bridges are current runtime observations,
not promises from this document. Bounded Web/Linux checks are authorized under
AGENTS.md resource limits; no AVD, VM or heavy release build. Missing targets
are BLOCKED/UNVERIFIED, never a simulated native pass.
Track any process started by this task and stop only processes this task owns.

## The loop

1. **Read state** — `an3ctl ui tree --target <t> --json`. Web `ariaSnapshot`
   is Playwright browser evidence; legacy compact `nodes` is only a compatibility
   approximation. Android WebView CDP is not the native Android accessibility tree.
2. **Act** — `ui click|fill|press|select|check --target <t> --testid <id>`.
3. **Assert** — `ui value|text|query`, `app state`, `emulator status`; check the
   process exit code (0 ok, 2 usage, 3 unavailable, 4 not found, 5 timeout,
   6 action failed, 7 state).
4. **Diagnose** — `logs --target <t>`; use a screenshot only for a
   rendering-specific problem.

## Targets

```bash
an3ctl targets --json                       # availability + reasons per target
```

- `web` — the Python server. `app start --target web` boots it and records state.
- `android` — adb + WebView CDP for exposed Web content. Use Android-native
  accessibility/instrumentation for native controls; do not launch a local AVD.
- `emulator` — the native player's deterministic test mode.
- `macos` / `linux` / `windows` — desktop Tauri shells; structured bridge not
  enabled yet, so `ui` returns `E_TARGET_UNAVAILABLE` with the exact requirement.

## Web

```bash
an3ctl app start --target web [--port 8099]
an3ctl app state --target web
an3ctl ui tree  --target web --path /games --limit 60
an3ctl ui query --target web --path /games --id gameSearch
an3ctl ui fill  --target web --path /games --id gameSearch --value emerald
an3ctl ui value --target web --path /games --id gameSearch
an3ctl ui click --target web --path /games --role link --name Games
an3ctl ui wait  --target web --path /games --testid open-rom --timeout 8000
an3ctl logs --target web --tail 50
an3ctl app stop --target web
```

Navigation happens only when the requested page differs from the current one, so
multi-step flows keep form state. Pass `--path`/`--url` on every command that
needs a specific page.

## Android

```bash
an3ctl app start --target android          # launches MainActivity
an3ctl app state --target android
an3ctl ui tree  --target android --limit 40
an3ctl ui click --target android --role button --name Settings
an3ctl ui fill  --target android --id nativeSearch --value emerald
an3ctl ui value --target android --id nativeSearch
an3ctl logs --target android --tail 100
an3ctl rom load /abs/path/fixture.3ds --target android --system 3ds
an3ctl app stop --target android
```

The adapter resolves the PID, finds `webview_devtools_remote_<pid>`, forwards it,
talks CDP, and removes the forward. Do not reproduce that by hand. A release APK
only exposes the socket when WebView debugging is enabled; the error message says
so.

## Emulator control plane (deterministic, no screenshots)

```bash
an3ctl emulator status --rom fixture.gba --system gba --frames 120
an3ctl emulator snapshot --rom fixture.gba --frames 120          # png + raw + hashes
an3ctl emulator baseline --name gba-boot --rom fixture.gba --frames 120
an3ctl emulator diff --name gba-boot --rom fixture.gba --frames 120
an3ctl emulator state --rom fixture.gba --path s.state --save|--load
an3ctl emulator input --rom fixture.gba --seq 'A@0-30;Start@40-45' --frames 60
```

Player selection: `AN3_PLAYER` (local path) or
`--player-target linux|windows [--player PATH] [--libdir DIR]`. The verdict is
JSON, e.g. `{"match":false,"differentPixels":37327,"differentPercent":97.2057,"maxChannelError":255}`.

Hardware-rendered 3DS capture requires a verified supported adapter. Bounded
windowed runs under Xvfb/SwiftShader belong to an authorized capable builder;
otherwise report capture UNVERIFIED rather than starting local heavy workloads.

## Tests

```bash
an3ctl test smoke --target web|android|emulator
node --test tests/an3ctl.test.mjs
```

## Rules

- Prefer user-facing role/name or label locators for browser semantics; stable
  test IDs support controls without a useful user-facing locator. CSS/IDs are
  structural fallbacks, not accessibility evidence. Never use layout paths.
- Use structured assertions for machine PASS/FAIL. Screenshots support rendering
  diagnosis and manual UX evidence; they do not prove semantic state by themselves.
- Use `an3ctl rom load` / the emulator CLI for deterministic gameplay setup.
  This bypass cannot accept the native file picker; test that separately when
  the claim requires it.
- Debug bridges are test-only and loopback/SSH-forwarded; never expose them.
- Report `UNVERIFIED` rather than `GOOD` when a runtime was not actually run.

Stop when the requested interaction has structured evidence, or a concrete target
is unavailable. Report target, source/runtime identity, commands and exit codes,
observed state, task-owned process cleanup and unverified visual/runtime claims.

See `docs/agent-control-plane.md` for the full contract.
