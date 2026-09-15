# EmulatorJS Netplay relay — staging only

This is a separate Rust Socket.IO signalling relay for EmulatorJS native
Netplay. It is built from the official Apache-2.0-licensed
`EmulatorJS/EmulatorJS-Netplay` Rust branch at commit
`4090ca7bda795a8b7a7596f4d41a4605b515d9c5`. The Docker image retains the
upstream license at `/usr/share/doc/an3-emulatorjs-netplay/`.

## Scope and safety

- The relay has no volume and does not mount AN3 source, SQLite, sessions,
  ROMs, saves, uploads, or production paths.
- It publishes only `192.168.1.8:8094`, never `0.0.0.0`, and is a staging LAN
  service. Do not add a public route, Cloudflare route, or production unit.
- AN3's player only passes `EJS_netplayServer` to EmulatorJS when
  `AN3_NETPLAY_ORIGIN=http://192.168.1.8:8094` is configured in the staging
  app environment. Production rejects the configuration by design.
- Every player must open the same AN3 game: the player supplies a stable game
  and system identifier to EmulatorJS. The native EmulatorJS menu provides
  host/join room flow.
- Netplay is not a claim of cable/link support for every core. NDS LAN relies
  on the melonDS core's network-emulation support and needs a low-latency LAN.
  The current Azahar WebAssembly build has no verified network-emulation path,
  so do not advertise 3DS cable/link as available.

## Staging deployment after key-only SSH access is available

Run only on the verified staging host, from a reviewed release directory:

```bash
export AN3_NETPLAY_STAGE_BIND=192.168.1.8
docker compose -f compose.rust-netplay.staging.yml up --build -d
docker compose -f compose.rust-netplay.staging.yml exec -T netplay \
  curl --fail --silent --show-error http://127.0.0.1:4000/games
```

The staging firewall must permit TCP 8094 only from `192.168.1.0/24`; install
that narrow rule through an owner-reviewed staging change, not a production
script. Then set the following value in `/etc/an3-arcade-staging.env` and
restart **only** `an3-arcade-staging.service`:

```text
AN3_NETPLAY_ORIGIN=http://192.168.1.8:8094
```

Verify `http://192.168.1.8:8094/games` from a different device on that LAN.
On the staging host itself, Docker/UFW may reject a hairpin request to its own
LAN address even though peers can reach the published port.

Verify `/offline` or a player page has that origin in `connect-src`, then
create and join an EmulatorJS Netplay room with two staging LAN browsers using
the same game. Test GBA and NDS separately; do not infer 3DS support.

To stop the relay without deleting any unrelated Docker resource:

```bash
docker compose -f compose.rust-netplay.staging.yml stop
```

Do not run this compose project in production.
