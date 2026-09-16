# Linux 1.4.0 runtime + controller host verification (2026-09-16)

Closes the Linux side of the 1.4.0 rollout on the Dell builder.

## 1.4.0 DEB runtime smoke (VERIFIED)

Extracted `vibecodedemulator-1.4.0-linux-amd64.deb` and ran the bundled player
under Xvfb:

```
xvfb-run -a env SDL_AUDIODRIVER=dummy LIBGL_ALWAYS_SOFTWARE=1 \
  AN3_OFFLINE_LIBDIR=<extracted runtime dir> \
  timeout 25s <runtime>/an3-offline-native \
  --rom ~/an3-verify/legal-gba.gba --system gba --renderer opengl
```

Result **EXIT=124** (still running after 25 s; only the benign `dbind` AT-SPI
warning). Same method as the 1.3.0 smoke, which also printed
`AN3_NATIVE_STATUS core=<n> present=<n> drops=0 renderer=opengl`.

## Controller UI is packaged (VERIFIED)

The installed app binary (`usr/bin/an3-offline-native`) contains
`nativeControllerCard`, so the Settings → Phone controller surface ships in the
Linux 1.4.0 build.

## Controller client on Linux (VERIFIED)

The shared Rust host was synced to the Dell and tested against staging:

- `cargo test --lib controller_host` → 6/6 (builds and passes on Linux too).
- Ignored live probe with `AN3_CONTROLLER_TEST_BASE=http://192.168.1.8:8092`
  → **passed** (real session `FY5554`, paired as a phone, submitted a frame,
  input reached the sink).

## Runtime INPUT path drives the core (VERIFIED, headless)

The runtime was started under Xvfb with `--control-stdin`, and the exact lines
the shell writes for the controller were fed to its stdin (GBA `start` = bit 3):

```
INPUT 8 0 0 0 0 0   /   INPUT 0 0 0 0 0 0   (x6)
```

Screenshots before and after differ: the GBA went from the Game Freak logo to
its menu. Evidence:
`reports/staging/linux-1.4.0-input-before.png`,
`reports/staging/linux-1.4.0-input-after.png`.

This proves the Linux runtime's `INPUT` → core path for the controller's button
bit. The Rust shell writes these lines through the same `input()` the app's
on-screen controls use.

## UNVERIFIED

- The Tauri app itself writing `INPUT` while polling (not driven end to end);
  the runtime side and the client side are each verified separately.
- Windows 1.4.0 runtime (built only; the 1.3.0 EXE had a launch smoke).
- A real phone driving a running Linux/Windows/macOS game.

## Addendum: shell → runtime write path unit-tested

`linux_runtime::tests::input_writes_the_control_stdin_protocol` spawns a fake
child (`cat`), installs it as the session, calls `input(NativeInput { buttons: 8,
circle_x: 1234, circle_y: -1234, touch_x: 7, touch_y: 9, touch_pressed: true })`
and asserts the child receives exactly `INPUT 8 1234 -1234 7 9 1`. Passes on the
Dell. `tests.test_native_input_contract` pins the same line format for both the
Linux and Windows adapters so they cannot drift.

## GUI end-to-end attempt (not obtained)

The Linux Tauri app was launched under bare Xvfb with its extracted 1.4.0
resources; the process stayed alive but the WebKitGTK surface rendered nothing
(blank screenshot), and no window manager is installed on the Dell, so the app
could not be driven. This is why the app-level GUI glue remains UNVERIFIED:
every logic link is verified, the UI automation is not available in this
environment. No packages were installed on the staging host.
