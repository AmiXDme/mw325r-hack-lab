#!/usr/bin/env python3
"""Offline MIPS32LE pointer/reference report for the MW325R bootloader.

This is a locator, not a decompiler. It reports valid code pointers and
simple address-building sequences without changing the firmware image.
"""
import argparse
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32


def words(data, start, end):
    for off in range(start, min(end, len(data) - 3), 4):
        yield off, struct.unpack_from("<I", data, off)[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path)
    ap.add_argument("--base", type=lambda x: int(x, 0), default=0xBC000000)
    ap.add_argument("--boot-start", type=lambda x: int(x, 0), default=0x100)
    ap.add_argument("--boot-end", type=lambda x: int(x, 0), default=0xD000)
    ap.add_argument("--table-start", type=lambda x: int(x, 0), default=0xC3D0)
    ap.add_argument("--table-end", type=lambda x: int(x, 0), default=0xC500)
    args = ap.parse_args()

    data = args.image.read_bytes()
    base = args.base
    lo, hi = base + args.boot_start, base + args.boot_end
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
    ins = list(md.disasm(data[args.boot_start:args.boot_end], lo))
    by_addr = {i.address: i for i in ins}

    print(f"image={args.image} bytes={len(data)} base={base:#x}")
    print(f"boot={args.boot_start:#x}-{args.boot_end:#x}")
    print("\nPOINTERS")
    for off, value in words(data, args.table_start, args.table_end):
        if lo <= value < hi:
            print(f"{off:#06x} -> {value:#010x}")

    print("\nDIRECT CALLS INTO POINTER TARGETS")
    targets = {value for _, value in words(data, args.table_start, args.table_end)
               if lo <= value < hi}
    for i in ins:
        if i.mnemonic in ("jal", "bal"):
            op = i.op_str.strip()
            try:
                target = int(op, 0)
            except ValueError:
                continue
            if target in targets:
                print(f"{i.address:#010x}: {i.mnemonic} {op}")

    print("\nSTRING-NEAR DATA POINTERS")
    for needle in (b"Booting image", b"imgFileEnc", b"LZMA ERROR"):
        pos = data.find(needle)
        addr = base + pos
        print(f"{needle!r} file={pos:#x} addr={addr:#010x}")
        for off, value in words(data, args.table_start, args.table_end):
            if abs(value - addr) <= 0x40:
                print(f"  table {off:#06x} -> {value:#010x} delta={value-addr:+#x}")

    print("\nTARGET FUNCTION WINDOWS")
    for target in sorted(targets):
        if target not in by_addr:
            continue
        print(f"\n-- {target:#010x} --")
        start = target
        for i in ins:
            if start <= i.address < start + 0x30:
                print(f"{i.address:#010x}: {i.mnemonic:8} {i.op_str}")


if __name__ == "__main__":
    main()
