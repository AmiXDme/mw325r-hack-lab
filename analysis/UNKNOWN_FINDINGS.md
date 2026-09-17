# UNKNOWN_FINDINGS.md

1. **Kernel/app region codec.** `0xE000–0xBAFFF` (~700 KB, entropy 7.95) is not raw LZMA/deflate/XOR-single-byte; `imgFileEnc` flag exists. Tried: raw deflate (2 modes), raw LZMA (225 lc/lp/pb × dict-8M, 6 offsets), single-byte-XOR→LZMA-header (256 keys).
   - Needed: MIPS disassembly of U-Boot's image loader to recover the transform/key.
2. **Exact on-device build 201115.** Mercusys publishes only 201116. All findings here are 201116 unless labeled live-observed.
3. **RAM/flash sizes, chipset stepping, MTD map.** Need live `/proc` (no shell) or SPI dump (no hardware work performed).
4. **Server-side C logic** (auth compare, lockout counter, UPnP/TDDP handlers). Needs unpacked image + Ghidra/MIPS.
5. **modelDesc/mcbDesc full grammars.** Mostly decoded; some TLV type codes + mcbDesc row semantics unverified.
6. **ToC `decomp` field semantics.** Chunk table parses structurally but third-field values don't match observed decompressed sizes — flagged, not load-bearing (boundaries came from LZMA headers + ToF ground truth instead).
7. **TR-069/SDMP active use.** PKI present; no port-7547 observed; ACS behavior unknown.
8. **WPS PIN handling path.** `wps.cUsrPIN` readable post-auth; registrar internals in packed region.
