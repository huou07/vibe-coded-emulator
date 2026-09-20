# LAN multiplayer capability audit

AN3 exposes only the multiplayer interface that the embedded core already
supports. Multiplayer packets do not use the AN3 Sync, Phone Controller, or
Internet/server transports.

| Core | Embedded version/source | Desktop | Android | Current AN3 result |
| --- | --- | --- | --- | --- |
| mGBA | `0.11-219-e31759b`, mGBA commit `e31759b24e7a4e3899285ff720d7b573ac328ae7`, `vendor/libretro/*/mgba_libretro*` | **UNAVAILABLE** — the upstream network link cable is not present in this core | **UNAVAILABLE** — same core limitation | No network link implementation; local same-process link behavior is untouched |
| melonDS DS | `1.3.1`, `JesseTG/melonds-ds` commit `bc4e4b67d2d470d7c682810a1e892cafd6f9082b`, `vendor/libretro/*/melondsds_libretro*` | **INTEGRATABLE** — native bridge compiles; direct transport and official callback probe pass; full gameplay still needs a legal ROM and two runtime endpoints | **BLOCKED** — JNI bridge is wired, but this host has no JDK/Android Studio JBR for a fresh APK build; no physical device is connected | Uses official libretro `RETRO_ENVIRONMENT_SET_NETPACKET_INTERFACE` and a melonDS-only direct framed LAN transport |
| Azahar3DS | `2126.1.1`, pinned release archives, `vendor/azahar/*/azahar_libretro*` | **UNAVAILABLE** in the current libretro bridge — no private-room host/join API is exposed | **UNAVAILABLE** in the current libretro bridge — no private-room host/join API is exposed | Public room APIs are deliberately not used; adding them would require a separate core bridge/upgrade |
| EdenSwitch | Eden commit `7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c`, `vendor/switch/macos-arm64` and `native/eden-bridge` | **UNAVAILABLE** in the shipped companion bridge | **UNAVAILABLE** — no Android companion is shipped | The bridge exposes lifecycle/input/save operations, not Eden LDN or a local room server |

## melonDS frontend contract

The frontend starts the callback session with client `0` for a host and client
`1` for a joiner. The direct transport validates the fixed melonDS core id, the
core-supplied protocol version, and a deterministic identity of the complete
ROM bytes before delivering any game packet. It forwards the core's packet
flags and player ids without translating them through another AN3 protocol.

The UI intentionally requires a current LAN address for Join and does not
claim automatic room discovery. Host and Join are configuration for the next
NDS launch; each participant launches the same local ROM and keeps independent
save data.

## LAN-only boundary

The native runtime binds a local TCP listener for Host or connects directly to
the entered private, loopback, or link-local IPv4 endpoint for Join. A host
also rejects peers outside those address ranges. It does not contact
`an3tocom.space`, the development server, a lobby API, or
`/api/multiplayer/*`. The older HTTP multiplayer implementation remains a
staging/web fixture and is not reachable from the installed native multiplayer
path. IPv6 and automatic LAN discovery are outside this first frontend slice;
Join therefore requires a current local IPv4 address.
