#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate a minimal, lawful homebrew GBA test ROM.

Developer-created test content for AN3 regression work. It contains no
third-party game code or assets (the Nintendo logo is deliberately omitted).
The ROM is deterministic and lets an emulator exercise the full pipeline:

* sets bitmap mode 3 and fills the screen;
* fills red while the A button is held, blue otherwise (visible input response);
* reads and writes cartridge SRAM with 8-bit accesses (the only width real GBA
  SRAM supports) so mGBA detects an SRAM save, writing a deterministic "AN3B"
  signature plus a boot counter byte at SRAM[4] that increments on every boot;
* shows green when a persisted save was restored at boot, red on a fresh boot;
* spins in a stable loop.

This gives LAN Sync, Phone Controller and save tests the same real ROM identity
on two devices without shipping any copyrighted content.

Usage:
    python3 tools/testrom/gba_homebrew_test.py [output.gba [title]]
"""
import struct
import sys
from pathlib import Path

ENTRY_OFFSET = 0xC0  # code starts after the 0xC0-byte header
TITLE = b"AN3HOMEBREW"
GAME_CODE = b"AN3H"
MAKER_CODE = b"01"

# Register/constant pool (addresses and values referenced by the code).
LITERALS = [
    0x04000000,  # 0: DISPCNT
    0x00000403,  # 1: mode 3 | BG2 enable
    0x0E000000,  # 2: SRAM base
    0x00000041,  # 3: 'A' — first byte of the "AN3B" save signature
    0x0000001F,  # 4: red (BGR555)
    0x000003E0,  # 5: green (BGR555)
    0x00000041,  # 6: 'A'
    0x0000004E,  # 7: 'N'
    0x00000033,  # 8: '3'
    0x00000042,  # 9: 'B'
    0x04000130,  # 10: KEYINPUT (active low)
    0x00007C00,  # 11: blue
    0x06000000,  # 12: VRAM (bitmap mode 3)
]


# The program is emitted as a fixed list of words; the PC-relative offsets for
# the ldr instructions are computed from the final layout so the literal pool
# stays in sync.
CODE_WORDS_BEFORE_POOL = 35  # instructions before the literal pool


def _pool_base() -> int:
    return ENTRY_OFFSET + CODE_WORDS_BEFORE_POOL * 4


def _strb(rd: int, rn: int, imm: int) -> int:
    """strb rd, [rn, #imm] — 8-bit SRAM write (SRAM only supports bytes)."""
    return 0xE5C00000 | (rn << 16) | (rd << 12) | (imm & 0xFFF)


def _ldrb(rd: int, rn: int, imm: int) -> int:
    """ldrb rd, [rn, #imm] — 8-bit SRAM read."""
    return 0xE5D00000 | (rn << 16) | (rd << 12) | (imm & 0xFFF)


def _add(rd: int, rn: int, imm: int) -> int:
    return 0xE2800000 | (rn << 16) | (rd << 12) | (imm & 0xFFF)


def build_code() -> bytes:
    pool = _pool_base()

    def ldr_at(index: int, reg: int, literal: int) -> int:
        """ldr reg, [pc, #imm] pointing at a literal pool entry."""
        pc = ENTRY_OFFSET + index * 4 + 8
        return 0xE59F0000 | (reg << 12) | ((pool + literal * 4 - pc) & 0xFFF)

    words = [
        ldr_at(0, 0, 0),   # ldr r0, DISPCNT
        ldr_at(1, 1, 1),   # ldr r1, mode 3 | BG2
        0xE5801000,        # str r1, [r0]
        ldr_at(3, 0, 2),   # ldr r0, SRAM base
        _ldrb(1, 0, 0),    # ldrb r1, [r0]   (8-bit read resolves SRAM save type)
        ldr_at(5, 2, 3),   # ldr r2, 'A'
        0xE1510002,        # cmp r1, r2      (was a save restored?)
        ldr_at(7, 8, 4),   # ldr r8, red
        ldr_at(8, 9, 5),   # ldr r9, green
        0x01A08009,        # moveq r8, r9    (restored -> green base colour)
        ldr_at(10, 2, 6),  # ldr r2, 'A'
        _strb(2, 0, 0),    # strb r2, [r0]     "AN3B" signature
        ldr_at(12, 2, 7),  # ldr r2, 'N'
        _strb(2, 0, 1),    # strb r2, [r0, #1]
        ldr_at(14, 2, 8),  # ldr r2, '3'
        _strb(2, 0, 2),    # strb r2, [r0, #2]
        ldr_at(16, 2, 9),  # ldr r2, 'B'
        _strb(2, 0, 3),    # strb r2, [r0, #3]
        _ldrb(10, 0, 4),   # ldrb r10, [r0, #4] boot counter
        _add(10, 10, 1),   # add r10, r10, #1
        _strb(10, 0, 4),   # strb r10, [r0, #4]
        ldr_at(21, 7, 10), # ldr r7, KEYINPUT
        ldr_at(22, 6, 11), # ldr r6, blue
        ldr_at(23, 2, 12), # loop: ldr r2, VRAM (reset after each fill)
        0xE1D710B0,        # loop: ldrh r1, [r7]
        0xE3110001,        # tst r1, #1        (A held?)
        0x01A05008,        # moveq r5, r8      (base colour)
        0x11A05006,        # movne r5, r6      (blue)
        0xE3A03C96,        # mov r3, #0x9600   (240*160 pixels)
        0xE0C250B2,        # fill: strh r5, [r2], #2
        0xE2533001,        # subs r3, r3, #1
        0x1AFFFFFC,        # bne fill
        0xEAFFFFF5,        # b loop (reload VRAM before the next frame)
        0xE1A00000,        # nop (pool alignment)
        0xE1A00000,        # nop
    ]
    assert len(words) == CODE_WORDS_BEFORE_POOL, len(words)
    code = b"".join(struct.pack("<I", word) for word in words)
    code += b"".join(struct.pack("<I", literal) for literal in LITERALS)
    return code


def build(title: bytes = TITLE) -> bytes:
    if not 1 <= len(title) <= 12 or any(
        not (ord("A") <= byte <= ord("Z") or ord("0") <= byte <= ord("9"))
        for byte in title
    ):
        raise ValueError("GBA title must contain 1–12 uppercase ASCII letters or digits")
    header = bytearray(0xC0)
    branch_offset = (ENTRY_OFFSET - 8) // 4
    header[0:4] = struct.pack("<I", 0xEA000000 | branch_offset)
    # 0x04..0x9F: Nintendo logo intentionally left zero (no third-party asset).
    header[0xA0:0xAC] = title.ljust(12, b"\0")[:12]
    header[0xAC:0xB0] = GAME_CODE[:4]
    header[0xB0:0xB2] = MAKER_CODE[:2]
    header[0xB2] = 0x96
    checksum = 0
    for byte in header[0xA0:0xBD]:
        checksum = (checksum - byte) & 0xFF
    header[0xBD] = (checksum - 0x19) & 0xFF
    body = bytes(header) + build_code()
    padding = (-len(body)) % 0x200
    return body + b"\0" * padding


def main() -> int:
    if len(sys.argv) > 3:
        print("usage: gba_homebrew_test.py [output.gba [TITLE]]", file=sys.stderr)
        return 2
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("an3-homebrew-test.gba")
    title = TITLE
    if len(sys.argv) > 2:
        try:
            title = sys.argv[2].encode("ascii")
        except UnicodeEncodeError:
            print("GBA title must be ASCII", file=sys.stderr)
            return 2
    try:
        data = build(title)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    out.write_bytes(data)
    print(f"wrote {out} ({len(data)} bytes, title={title.decode('ascii')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
