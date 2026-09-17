# Checkpoint — Direct LAN controller (AN3 Controller LAN v1)

Updated: 2026-09-17. Read this before continuing; it records the exact protocol
and what is already implemented so completed work is not repeated.

## Status

| Milestone | Status |
| --- | --- |
| A — persistent memory + AGENTS blocker rule + private skill | Implemented and verified |
| B — six-digit CSPRNG pairing code | Implemented and verified |
| C — direct LAN discovery (UDP announce on the host) | Implemented and unit-testable; not yet consumed by a phone app |
| D — secure persistent direct TCP transport (desktop Rust host) | Implemented and verified (integration test) |
| E — APK in-app Controller Mode | Not started |
| F/G — GBA/NDS/3DS landscape controller UI | Not started |
| H — cross-device direct verification (MacBook host ↔ AVD controller) | Not started |
| I — staging/regression verification | Partially (staging path untouched; suite green) |

## Private infrastructure created (outside the repo)

- `~/.config/opencode/project-memory/vibe-coded-emulator.md` — device/test matrix.
- `~/.config/opencode/skills/vibe-coded-verification/SKILL.md` — verification workflow.
- Global `~/.config/opencode/AGENTS.md` — project-memory rule + Blocker discipline.

## Protocol — AN3 Controller LAN v1

- UDP discovery: port **47831**, host broadcasts every 2s:
  `{"an3":"ctrl","v":1,"id":"<hex8>","name":"<label>","port":47832}` (no secrets).
- Control: TCP port **47832**, persistent stream, frames = 4-byte big-endian length + body.
- Plaintext handshake:
  - phone → host: `{"k":"hello","v":1,"pub":"<b64 SEC1 uncompressed P-256>","name":"<phone label>"}`
  - host → phone: `{"k":"hello","v":1,"pub":"<b64>","id":"<hex8>","name":"<host label>"}`
- Key exchange: ephemeral **P-256 ECDH**; shared secret = x-coordinate.
  `salt = SHA256("an3-ctrl-v1|" + secret)` where `secret` is the **6-digit pairing code**
  (first pairing) or the **32-byte session token** (reconnect). `key = HKDF-SHA256(ikm=shared, salt, info="an3-ctrl|v1|session", L=32)`.
  The code/token is never transmitted.
- Encrypted frames: `[12-byte nonce || AES-256-GCM ciphertext+tag]`.
  nonce = 4-byte direction (`0x00000001` phone→host, `0x00000002` host→phone) + 8-byte counter.
  Counter starts at 0 per direction; TCP ordering makes gaps impossible on a live connection.
- Message kinds (**`k`**, never `t` — `t` is reserved for the touch tuple so
  `frame_input` keeps working):
  - `auth` (phone→host, counter 0) — proves the code/token by AEAD success.
  - `ready` (host→phone) — `{"k":"ready","token":"<b64 32B|null>","system":"gba"}`; the
    host issues a new token and invalidates the code on first pairing.
  - `state` (phone→host) — `{"k":"state","s":seq,"b":[names],"a":[lx,ly,rx,ry],"t":[x,y]?}`.
  - `ack` (host→phone) — `{"k":"ack","s":seq,"inputActive":bool,"system":"gba"}`.
- Security properties: encryption + authentication via standard primitives
  (p256 ECDH, HKDF-SHA256, AES-256-GCM). Pairing is local-network only,
  rate-limited (6 failures/IP/minute), the code expires after 120s, is
  invalidated after one successful pairing, and never becomes the session
  credential.

## Implemented files

- `native-offline/src-tauri/src/lan_host.rs` — the whole host (discovery,
  listener, handshake, framing, input, ack, release-all). Reuses
  `controller_host::frame_input` and `azahar::set_native_input`.
- `native-offline/src-tauri/src/lib.rs` — commands
  `native_controller_lan_start|stop|status|refresh`.
- `native-offline/src-tauri/build.rs` + `capabilities/default.json` — ACL entries
  for the four commands (required; see RG-093).
- `native-offline/src-tauri/Cargo.toml` — `aes-gcm`, `base64`, `getrandom`,
  `hkdf`, `hmac`, `p256`, `sha2`.
- `netcode.py` — `generate_pairing_code` now numeric CSPRNG; `is_pairing_code`.
- Tests: `lan_host::tests::{pairing_codes_are_six_digits_including_leading_zeroes,
  key_derivation_depends_on_the_pairing_code, aead_frames_round_trip_and_bind_direction_and_counter,
  direct_transport_pairs_and_injects_input}`, `tests.test_netcode` (CodeTests).
- The staging path (`controller_host.rs`, `ControllerClient.kt`, `/api/controller/*`,
  `static/controller.js`) is untouched and remains the development fallback (§26).

## Verification commands

```bash
# Rust (includes the direct-transport integration test)
cargo test --manifest-path native-offline/src-tauri/Cargo.toml --lib
# Python
PYTHONPYCACHEPREFIX="$PWD/work/pycache" python3 -m unittest discover -s tests
```

Recorded result: Rust 17 passed / 1 ignored; Python 285 passed.

## Remaining work (in order)

1. **Kotlin controller client** (`LanControllerClient.kt`): UDP discovery
   listener + TCP connect + the same ECDH/HKDF/AES-GCM handshake
   (Android: `KeyAgreement("ECDH")`, HKDF via `Mac("HmacSHA256")`, `Cipher("AES/GCM/NoPadding")`),
   same `k`/`t` field rules, latest-state-wins, heartbeat, reconnect with the
   token, release-all on loss.
2. **Android in-app Controller Mode**: a native landscape Activity (not a
   browser page, not `/controller/join`) with nearby-device list + six
   digit-slot code entry; both roles (host + controller) share `An3ControllerHost`.
3. **Android LAN host**: UDP announce + TCP listener in Kotlin, feeding the
   existing `ControllerHostService` (`:game` process).
4. **Landscape gamepad UI**: GBA (dpad/AB/LR/Start/Select, no sticks), NDS
   (center touch surface + dpad + ABXY + shoulders), 3DS (+ Circle Pad, C-stick
   where supported), responsive to 16:9 … 20:9, no scroll, safe areas, minimal
   top status strip, reuse the in-game pad visual tokens.
5. **Cross-device verification**: MacBook host ↔ AVD controller (use the AVD
   alias `10.0.2.2` to reach the host loopback for the direct test; discovery
   will not traverse the emulator NAT), then internet-offline test.
6. Remove the staging server URL from normal controller UI (move to Advanced
   Diagnostics); keep the staging path as an internal fallback.

## Gotchas already learned

- Accepted TCP sockets inherit the listener's non-blocking mode on Unix — call
  `set_nonblocking(false)` before `set_read_timeout`.
- The message kind must be `k`; `t` is the touch tuple.
- The Windows Tauri build breaks if macOS `._*` AppleDouble files are copied
  into the source tree (exclude `._*` from sync tarballs).
- Android `NativeGameActivity` runs in `:game`; the controller host lives in the
  main process and forwards input through `ControllerHostService`.
