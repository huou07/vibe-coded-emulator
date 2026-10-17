#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a lawful, synthetic GBA ROM fixture for native/runtime journeys.

The repository bundles no ROMs, firmware, keys or saves. This script writes its
own 32 KiB GBA cartridge image from the published cartridge-header layout plus a
hand-assembled ARM stub; it copies no Nintendo logo, BIOS or game data. The
generated file is *not* committed — only this generator is — so the journey stays
reproducible without the repository carrying a ROM.

The stub is deliberately animated so a frame-diff journey has something to
detect:

  * set DISPCNT = 0x0403 (mode 3 bitmap, BG2 enabled),
  * then, in a tight loop, increment a register and write its low halfword to the
    first pixel of the mode-3 frame buffer at 0x06000000.

That is deterministic in mGBA: the same `--frames N` executes the same number of
instructions, so two runs at the same frame count render identical bytes, while
frame 1 and frame 120 render different pixels. A static stub cannot satisfy the
`an3ctl emulator diff` contract, which is why the earlier ad-hoc fixture made the
deterministic native journey vacuous.

Usage:
  python3 tools/make-synthetic-gba-fixture.py [--output PATH] [--force]

Default output: work/fixtures/an3-synthetic-gba.gba (git-ignored work tree).
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import struct
import sys

ROM_SIZE = 32 * 1024
TITLE = b"AN3TESTROM  "  # 12 bytes at 0xA0
GAME_CODE = b"AN3T"  # 4 bytes at 0xAC
MAKER_CODE = b"01"  # 2 bytes at 0xB0
FIXED_VALUE = 0x96  # required at 0xB2
HEADER_START = 0xA0  # complement check covers 0xA0..0xBC inclusive
HEADER_END = 0xBC
COMPLEMENT_OFFSET = 0xBD
ENTRY_OFFSET = 0xC0  # where the ARM entry branch lands; header ends at 0xBF
ARM_BRANCH = 0xEA000000  # ARM `b`, signed 24-bit word offset, PC = address + 8

# --- The ARM stub at 0xC0 ----------------------------------------------------
# Literal pool follows the code at 0xDC; each `ldr` is PC-relative so no 32-bit
# immediate encoding is needed for the addresses.
DISPCNT_ADDRESS = 0x04000000
DISPCNT_VALUE = 0x00000403  # mode 3 (16-bit bitmap) + BG2 enable
VRAM_BASE = 0x06000000
CODE_OFFSET = 0x10  # (0xDC, 0xE0, 0xE4) - (instruction address + 8)
PROGRAM = (
    0xE59F0014,  # 0xC0: ldr r0, [pc, #0x14]  ; r0 = &DISPCNT
    0xE59F1014,  # 0xC4: ldr r1, [pc, #0x14]  ; r1 = DISPCNT_VALUE
    0xE59F2014,  # 0xC8: ldr r2, [pc, #0x14]  ; r2 = VRAM_BASE
    0xE1C010B0,  # 0xCC: strh r1, [r0]        ; display on, mode 3
    0xE2833001,  # 0xD0: add r3, r3, #1        ; advance the counter
    0xE1C230B0,  # 0xD4: strh r3, [r2]        ; paint pixel 0 with the counter
    0xEAFFFFFC,  # 0xD8: b 0xD0                ; loop forever
)
LITERALS = (DISPCNT_ADDRESS, DISPCNT_VALUE, VRAM_BASE)


def arm_branch_to(from_address: int, to_address: int) -> bytes:
    offset = (to_address - (from_address + 8)) // 4
    if not -0x800000 <= offset <= 0x7FFFFF:
        raise ValueError(f"branch out of range: {from_address:#x} -> {to_address:#x}")
    return struct.pack("<I", ARM_BRANCH | (offset & 0xFFFFFF))


def complement_check(header: bytes) -> int:
    """GBA complement check: -(sum(0xA0..0xBC) + 0x19) modulo 256."""
    return (-(sum(header) + 0x19)) & 0xFF


def build_rom() -> bytes:
    rom = bytearray(ROM_SIZE)
    rom[0x00:0x04] = arm_branch_to(0x00, ENTRY_OFFSET)
    # 0x04..0x9F (the logo area) stays zero: no Nintendo logo bytes are copied,
    # and mGBA's HLE BIOS does not require them to boot a cartridge.
    rom[HEADER_START : HEADER_START + len(TITLE)] = TITLE
    cursor = HEADER_START + len(TITLE)
    rom[cursor : cursor + len(GAME_CODE)] = GAME_CODE
    cursor += len(GAME_CODE)
    rom[cursor : cursor + len(MAKER_CODE)] = MAKER_CODE
    rom[0xB2] = FIXED_VALUE
    # 0xB3..0xBB (main unit code, device type, reserved) and 0xBC (version) stay 0,
    # so the complement check is computed over exactly the header bytes above.
    rom[COMPLEMENT_OFFSET] = complement_check(bytes(rom[HEADER_START : HEADER_END + 1]))

    for index, instruction in enumerate(PROGRAM):
        start = ENTRY_OFFSET + index * 4
        rom[start : start + 4] = struct.pack("<I", instruction)
    literal_start = ENTRY_OFFSET + len(PROGRAM) * 4
    for index, literal in enumerate(LITERALS):
        start = literal_start + index * 4
        rom[start : start + 4] = struct.pack("<I", literal)
    return bytes(rom)


def main(argv: list[str]) -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default=str(root / "work" / "fixtures" / "an3-synthetic-gba.gba"))
    parser.add_argument("--force", action="store_true", help="overwrite an existing different file")
    args = parser.parse_args(argv)

    output = pathlib.Path(args.output)
    rom = build_rom()
    digest = hashlib.sha256(rom).hexdigest()

    if output.exists():
        existing = output.read_bytes()
        if existing == rom:
            print(f"SYNTHETIC_GBA={output} bytes={len(rom)} sha256={digest} (unchanged)")
            return 0
        if not args.force:
            print(f"ERROR: {output} exists and differs; pass --force to replace it", file=sys.stderr)
            return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rom)
    print(f"SYNTHETIC_GBA={output} bytes={len(rom)} sha256={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
