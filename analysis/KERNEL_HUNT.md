# KERNEL_HUNT.md — unpacking the 0xE000–0xBAFFF region (IN PROGRESS)

Status: **OPEN**. Everything below is verified method + negative result. No findings invented.

## Target

~700 KB high-entropy region (`0xE000–0xBAFFF`, entropy ~7.8 uniform, zero
printable strings ≥5 chars). Presumed packed VxWorks kernel+app. U-Boot
string `imgFileEnc=0x%x, offset=0x%x, len=0x%x` proves an encryption flag
exists in the loader; `LZMA ERROR %d - must RESET board to recover` proves
LZMA follows.

## Proven infrastructure (all [EXACT], reproducible with `capstone`)

- MIPS32 little-endian, XIP base `0xBC000000 + file_offset` — proven 5× over
  (independent `lui $gp` prologues all resolve `$gp` to `0xBC00C3E4`).
- GOT mapped (file `0xC3E8+`); 180 gp-relative refs resolved to slots.
- String-ref engine: `GOT_slot - C` pattern cracked (e.g. `0xBC010000 - 0x58BC`
  = `"loadaddr"`); 30 call sites resolved to boot-menu/TFTP/cache strings.
- Boot-menu dispatcher disassembled (choices `'1'`–`'9'`, `Y/N` confirms).
- Pointer tables (`0xC3E8+`) hold real code pointers (e.g. `0xBC002848`).
- IMG0 header parsed (MD5-like sig, `IMG0`, BE section lens, MIPS load addrs).

## Exhausted blind attacks (all FAILED, documented so nobody repeats them)

| # | Method | Result |
|---|---|---|
| 1 | Raw DEFLATE (`wbits` -15, 47) at 0xE000 | fail |
| 2 | Raw LZMA, 225 lc/lp/pb combos × dict-8M × 6 offsets | fail |
| 3 | Raw LZMA, 11 starts × 15 dict sizes (64 KB–64 MB) | fail (165 combos) |
| 4 | Single-byte XOR → LZMA-header (256 keys, strict + relaxed) | fail |
| 5 | Header-signature XOR/SUB, `IMG0`-magic XOR/SUB | fail |
| 6 | MIPS-code / text heuristics on transforms | fail |
| 7 | U-Boot command-table hunt (24 B records) | 1 false positive |
| 8 | XOR-loop hunt in disassembly | 2 `xor` insns, both memcmp-style, no decrypt loop |

## Key anomaly (leads welcome)

The `B83C–B940` loader strings (`imgFileEnc`, `LZMA ERROR`, `Not VxWorks
Image`, `Booting image`) are referenced by **neither** absolute immediates
**nor** gp-relative GOT slots anywhere in `0x94–0xD000` (verified by exhaustive
4-byte word search). Either dead strings, or referenced through an unresolved
indirection. The `0xC3D4` slot points 8 bytes *into* `LZMA ERROR…`, implying
slot±delta addressing the current engine doesn't yet follow.

## Resume instructions

1. Resolve slot±delta references (extend engine §above).
2. Disassemble the loader fully; find the `imgFileEnc` branch.
3. Extract transform + key; apply; expect LZMA-alone (`0x5D000080`) or raw stream.
4. Validate by VxWorks string recovery (`vxWorks`, `WRS`, `Copyright`).
5. Tools: `capstone` (`pip install --user --break-system-packages capstone`),
   MIPS32LE, base `0xBC000000`, gp `0xBC00C3E4`.
