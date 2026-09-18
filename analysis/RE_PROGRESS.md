# Firmware Reversing Progress

## 2026-09-18 Offline Pass

This pass used only the published `MW325R_EU_V2_201116.zip`; no router writes,
flashing, or live exploitation were performed.

### Reproduced facts

- Firmware payload: `987412` bytes.
- SHA-256: `629df1f68e315c2e336f3ef451f6006d5750fe2d11d24ebf7f535e077d438c44`.
- `IMG0` headers: real outer header at `0x14`; an inner occurrence at `0xd094`
  is inside packed data and is not a second firmware container.
- `MINIFS` starts at `0xbb094`.
- Bootloader region is approximately `0x100-0xd000`, MIPS32 little-endian.
- Packed native region is `0xe000-0xbb094`, 708,756 bytes, entropy `7.9997`.
- MINIFS/tail region is `0xbb094-0xf1114`, 221,312 bytes, entropy `7.9566`.
- Plaintext loader strings are present at `0xb847` (`Booting image`), `0xb89c`
  (`imgFileEnc`), and `0xb8c4` (`LZMA ERROR`).

### New reversing observation

A Capstone MIPS32LE pass over the bootloader found no simple `lui` + `ori/addiu`
materialization of the three loader-string addresses. The bootloader contains
large pointer tables around `0xc000`, including entries pointing into the
`0xbc...` image address space, and the early code uses indirect/GOT-style
transfers. This explains why a plain string cross-reference scan misses the
image-loader routine.

The table at `0xc3e8` is a real function-pointer table: entries include
`0xbc002848`, `0xbc002f6c`, `0xbc003a34`, and many other addresses inside the
plaintext bootloader. The nearby entry at `0xc3d4` points to `0xbc00b8cc`,
which is four bytes into the `LZMA ERROR` string. This confirms that the
loader's format-string references use table/offset indirection rather than
direct references to the beginning of each string. The code at `0xbc001084`
through `0xbc001174` is cache/TLB and SoC initialization, not the image
transform; it should not be mistaken for the decryptor.

The table-target classifier shows three useful classes:

- `0xbc0016cc`, `0xbc00121c`, and `0xbc000c20` are initialization/helper
  routines with repeated MMIO/cache activity.
- `0xbc003a18`, `0xbc003a28`, and `0xbc003a34` are compiled helper routines
  with stack frames and indirect calls through saved function/GOT slots.
- Many other table values are not valid instruction boundaries under a naïve
  linear decode, indicating that the table is broader than a simple flat
  function-pointer array or contains mixed entry types/offsets.

No table target yet contains a defensible `imgFileEnc` transform signature.
The next pass must reconstruct entry boundaries and the relocation/copy step
before classifying all table values as functions.

### Reusable tooling

`analysis/mips_loader_refs.py` now reproduces the pointer-table scan and emits
valid bootloader targets, string-near table entries, and target windows. Example:

```sh
python3 analysis/mips_loader_refs.py /path/to/mw325rv2-eu-up-boot_*.bin
```

The tool deliberately does not modify the image or execute extracted native
code.

### Current boundary

The web UI, TDDP model, blocks, MINIFS codec, and bootloader layout are decoded.
The native VxWorks/radio/TDDP implementation remains unavailable until the
indirect pointer-table and loader dispatch are resolved. No claim is made that
the radio silicon is incapable of monitor mode or injection; only that the
stock firmware/API has not exposed those capabilities.

### Next offline steps

1. Reconstruct U-Boot pointer/GOT tables and resolve indirect calls.
2. Identify the routine consuming `imgFileEnc`, offset, and length.
3. Recover the transform and validate output as LZMA/VxWorks code.
4. Load the recovered image into a MIPS-aware disassembler and locate the
   wireless task/driver command table.
5. Search that native code for raw receive, monitor, management-frame transmit,
   WDS, and packet-forwarding paths.

The encrypted region must not be replaced with guessed bytes, and the router
must not be flashed as part of this analysis.
