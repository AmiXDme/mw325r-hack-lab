# EXECUTABLE_ANALYSIS.md

## ELF executables: NONE in shipped artifacts [EXACT]

- The downloadable `.bin` contains **no ELF headers** (`\x7fELF` count = 0 across 987,412 bytes).
- The 106 MINIFS records are web assets + 5 conf files — no executables, no `.so`, no kernel modules.
- All device code ships inside the packed VxWorks region (`0xE000–0xBAFFF`), format [UNKNOWN] (not raw LZMA/deflate/XOR; `imgFileEnc` encryption flag present in bootloader).

## What this means

This is a **monolithic VxWorks image**, not a Linux distribution: there is no `/bin`, no BusyBox, no ELF to dissect with readelf/objdump. Application logic (HTTP/TDDP server, UPnP, DHCP, wireless driver glue) is statically linked into one image.

## Executable-adjacent artifacts actually recovered

| Artifact | Type | Notes |
|---|---|---|
| U-Boot 1.1.3 | MIPS32LE machine code + strings (`0x100–0xCFFF`) | LE-MIPS prologues confirmed; **no MIPS disassembler in this environment** → disassembly [UNAVAILABLE] |
| `web/lib/*.js`, `web/dynaform/*.js` (12 files, ~183 KB) | JavaScript source [EXACT] | Full client framework: Quary (auth/TDDP), DM (opcodes), model, ajax, verify |
| 58× `.htm` + `str.js`/`Help.htm` (en_US + zh_TW) | UI source [EXACT] | Complete admin interface |
| `conf/*.bin` | Binary descriptors (modelDesc magic `12345678`) | DM schema block [RECOVERED], full semantics [INFERRED] |

## Prioritized targets IF kernel region is ever unpacked

1. HTTP/TDDP handler (auth compare, lockout counter, `securityEncode` server twin)
2. UPnP server (port 1900, no-auth SOAP surface)
3. Configuration manager (block IDs 0–59, NVRAM/flash layout)
4. WPS registrar (`wps.cUsrPIN` handling)
