# AN3 lawful test fixtures

Developer-generated emulator regression fixtures for AN3. They contain **no
commercial game content, ROM collections, firmware, BIOS or keys**, and no
Nintendo trademarks or artwork beyond ordinary platform names used to identify
compatibility.

## GBA — `an3-homebrew-test.gba`

Generated from source by `gba_homebrew_test.py` (GPL-3.0-or-later, part of this
project). It is a 512-byte GBA ROM that:

- switches to bitmap mode 3 and fills the screen;
- fills **red while the A button is held**, blue otherwise (visible input
  response, usable for Phone Controller latency checks);
- reads and writes cartridge SRAM with **8-bit accesses** (the only width real
  GBA SRAM supports). The first byte read resolves mGBA's save type to SRAM, so
  the emulator exposes a battery save; it then writes an `AN3B` signature plus a
  boot counter at SRAM[4] that increments on every boot;
- shows **green when a persisted save was restored** at boot, red on a fresh
  boot;
- spins in a stable loop.

Build:

```sh
python3 tools/testrom/gba_homebrew_test.py an3-homebrew-test.gba
```

For isolated cross-device tests, pass a distinct 1–12 character uppercase
alphanumeric title; the executable body stays identical and the header checksum
is regenerated:

```sh
python3 tools/testrom/gba_homebrew_test.py an3-sync-test.gba AN3SYNCROM5
```

The generator is the source of truth; regenerate the binary rather than editing
it. The default fixture's expected size and SHA-256 are recorded in
`fixtures.json`; a titled variant has the same code and size but its own hash.

## NDS / 3DS / Switch

These require the devkitPro toolchains (libnds, libctru, libnx) to build from
source. They are **environment-blocked** on the current hosts and are recorded
as such in `fixtures.json`. The AN3 importer already accepts `.nds`, `.3dsx`
and `.nro`, so once a devkitPro toolchain is available the fixtures can be
generated without app changes. Do not obtain commercial ROMs, firmware or keys
to work around the missing toolchain.
