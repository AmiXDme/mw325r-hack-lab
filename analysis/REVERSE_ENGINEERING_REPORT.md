# REVERSE_ENGINEERING_REPORT.md — MERCUSYS MW325R v2

> Evidence labels used throughout: `[EXACT]` byte-verified · `[RECOVERED]` extracted artifact · `[RECONSTRUCTED]` reasoned model · `[OBSERVED]` live behavior · `[INFERRED]` best explanation · `[UNKNOWN]`/`[UNAVAILABLE]` explicit gaps. Detail files sit next to this report; this master file summarizes each required section.

## 01 Executive Summary

Official firmware `MW325R(EU)_V2_201116` (987,412 B, SHA256 `629df1f6…438c44`) for the owner's MW325R v2 (on-device build 201115) was fully mapped: U-Boot 1.1.3 → packed VxWorks 5.5 monolith (MIPS32LE) → **MINIFS web partition 100% extracted (106/106 files, 4 byte-verified against the live router)**. The entire admin web application (auth, TDDP API, all pages) is recovered as original source. Kernel/app code remains packed (`imgFileEnc`) — the single hard gap, with a precise path to close it (MIPS disassembly of the U-Boot loader). Two live-demonstrated weaknesses (no-auth UPnP control; reversible login crypto) plus one shipped private TLS key are documented defensively in SECURITY_REVIEW.md.

## 02 Target Identification

MERCUSYS MW325R 2.0, FW 2.2.1 Build 201115 Rel.70272n, MAC 38-6b-1c-XX-XX-XX [EXACT live]. MIPS32LE [INFERRED], VxWorks 5.5 [banner EXACT]. RAM/flash/chipset [UNKNOWN]. Full table: ARTIFACT_MANIFEST.md.

## 03 Firmware Acquisition

Official Mercusys CDN zip (URL + hashes in ARTIFACT_MANIFEST.md). Exact on-device build 201115 is [UNAVAILABLE] (not published); analyzed 201116, one month newer — version skew is labeled everywhere it matters.

## 04 Artifact Verification

SHA256/MD5 recorded; `file(1)` misdetects it ("G3 FAX") — actually custom IMG0 container [RECONSTRUCTED]. No vendor checksum published to verify against.

## 05 Firmware Format

`IMG0` magic @0x16; 16-byte signature; MIPS load addrs `0x80000000`/`0x80100F00`; BE section-length fields (boot `0xD000` verified). Not TRX/uImage/SquashFS/UBI (all magic scans negative) [EXACT].

## 06 Extraction

Bootloader strings (plaintext) + MINIFS fully extracted via custom `minifs_extract.py` (included): header→ToN→ToF(20 B)→ToC→LZMA-alone (`0x5D000080`) chunks. Kernel region: attempted raw deflate/LZMA (225 param combos), single-byte-XOR (256 keys) — still packed [UNKNOWN codec].

## 07 Filesystem Inventory

FILESYSTEM_INVENTORY.md — all 106 files with size + SHA256 + type (58 HTML, 12 JS, images, 6 UPnP XML, 5 conf).

## 08 Hardware/Architecture

MIPS32LE [INFERRED from opcodes + Ralink SPI strings]; peripherals via strings only; full spec [UNKNOWN]. ARCHITECTURE_RECONSTRUCTION.md.

## 09 Boot Process

U-Boot 1.1.3 → TFTP/flash menu → VxWorks image check → LZMA → services. BOOT_ANALYSIS.md.

## 10 Kernel

VxWorks 5.5 monolith [banner+strings]; internals packed [UNKNOWN].

## 11 Drivers

Ralink SPI (`raspi_*`) [EXACT strings]; WLAN/switch drivers inside packed region [UNKNOWN].

## 12 Executables

Zero ELF in shipped artifacts [EXACT]; logic is monolith + JS. Targets for future unpacking listed in EXECUTABLE_ANALYSIS.md.

## 13 Libraries

No `.so` shipped [EXACT]; client libs are JS source incl. vendored Zepto (MIT). Opcode table recovered. LIBRARY_ANALYSIS.md.

## 14 Symbols

214 JS symbols indexed (SYMBOL_INDEX.md). C symbols [UNAVAILABLE]. Bootloader `raspi_*`/`U-Boot` names from strings.

## 15 Strings

1,879 printable runs; only bootloader + MINIFS names are plaintext; kernel region has none. STRING_INDEX.md (122 curated rows).

## 16 Resources

106/106 extracted (RESOURCE_INDEX.md): complete admin SPA (en_US + zh_TW), UPnP descriptors, PKI files.

## 17–18 Web UI + CGI/API

Reconstructed end-to-end: page inventory, POST `?code=` API (opcodes 0–11), auth flow, pre-auth exposure. WEB_UI_RECONSTRUCTION.md.

## 19–20 Configuration + NVRAM/Flash

Schema descriptor `modelDesc.bin` decoded (magic `12345678`, TLV field records matching live block 0); 60 TDDP blocks; flash map reconstructed; NVRAM markers absent. CONFIGURATION_ANALYSIS.md, FLASH_NVRAM_ANALYSIS.md.

## 21 Network Services

Ports 80 + 1900/TCP only; UPnP fully open (demonstrated); full matrix in NETWORK_SERVICES.md.

## 22–23 Processes + IPC

Single-image VxWorks task model [INFERRED]; no per-process evidence obtainable statically. ARCHITECTURE_RECONSTRUCTION.md.

## 24–26 Routing/Firewall, Wireless, Update

Mechanisms inferred from JS + blocks (WPA2-PSK, WPS ON, port-forwarding via UPnP [OBSERVED]); update path via UPLOAD=3 + U-Boot checks (untested by design). DATA_FLOW.md.

## 27–28 Reset/Recovery, Logging

U-Boot TFTP menu + reset-button behavior (observed: short press = reboot); log surface = SystemLog.htm (server side unknown).

## 29–30 Disassembly / Decompilation

JS: source already (no decompilation needed). Native: blocked — no MIPS-capable disassembler in this environment + packed image. Reconstructed behaviors: SOURCE_RECONSTRUCTION.md (securityEncode proven byte-identical in Python).

## 31 Code Recovery Assessment

See §51 + FINAL SOURCE-CODE QUESTION below.

## 32 Web Source Reconstruction

Complete: framework roles, endpoint↔handler map, validation, i18n. WEB_UI_RECONSTRUCTION.md + `extracted-minifs/` tree.

## 33 Database/Storage

No SQLite; schema = `modelDesc.bin` TLVs; values = flash config region (layout unknown). CONFIGURATION_ANALYSIS.md.

## 34–36 Hardware/Software, Architecture, Data Flows

ARCHITECTURE_RECONSTRUCTION.md, DATA_FLOW.md (login, WiFi change, password change, upgrade, backup/restore, reset, UPnP action).

## 37–42 Service/File/Function/Resource/Feature matrices

NETWORK_SERVICES.md, FILESYSTEM_INVENTORY.md, FUNCTION_INDEX.md (+SYMBOL_INDEX.md), RESOURCE_INDEX.md; feature matrix: §16 page list + §21 services + WPS/UPnP/DDNS/IPTV/IPv6 pages present [EXACT filenames].

## 43–46 Unknowns, Security, Third-party, Licenses

UNKNOWN_FINDINGS.md (8 items), SECURITY_REVIEW.md (6 issues + strengths, defensive), THIRD_PARTY_COMPONENTS.md (U-Boot/GPL, LZMA, Zepto/MIT, Ralink, VxWorks, SDMP PKI).

## 47–50 Confirmed / Reconstructed / Inferred / Unknown

Confirmed: MINIFS codec + 106 files, JS auth stack, opcodes, UPnP openness, lockout, PKI files, U-Boot version. Reconstructed: boot chain, flash map, data flows, modelDesc grammar. Inferred: MIPS SoC class, monolith task model, update checks. Unknown: kernel codec/key, MTD map, server C logic (see UNKNOWN_FINDINGS.md).

## 51 Original Source Recovery Assessment

- Web UI + all JS logic: **100% original source** (shipped as source).
- PKI/config descriptors: **original bytes**.
- C code: **0%** (packed; symbols stripped by design of monolith shipping).
- Loss causes: compilation + packing/encryption + static linking, in that order.

## 52 Independent Reimplementation Blueprint

Target OpenWrt + uhttpd + fresh SPA reusing only *protocol semantics* (opcodes, block IDs, XOR-auth documented here — not vendor code); schema from `modelDesc.bin`; hardware needs MTD/radio mapping from a live unit. No replacement firmware written in this phase (per instructions).

## 53 Appendix

- `minifs_extract.py` (extractor), `extracted-minifs/` (106 files), `ARTIFACT_MANIFEST.md` (hashes/URLs).

---

# FINAL SOURCE-CODE QUESTION — ORIGINAL SOURCE RECOVERY

1. **Was original source found?** YES for the entire web application (HTML/CSS/JS ship as source); NO for C code.
2. **Directly recoverable files?** All 106 MINIFS records (58 pages, 12 JS incl. full auth stack, 6 UPnP XML, images, locales, 2 PKI files + 2 cert/desc binaries + cert).
3. **Binaries decompiled?** None (no ELF/unpacked native code available; no MIPS disassembler in environment).
4. **Functions reconstructed?** `securityEncode`, `orgAuthPwd`, `auth`, `read/write/instr/reboot/reset/changePwd/logout`, TDDP opcode dispatch — behaviorally exact (Python twin byte-verified).
5. **Classes/structures reconstructed?** JS classes (`Quary`, `Load`/`TDDP`, menu/DataGrid/macFactory); MINIFS on-disk structs (header/ToN/ToF-20B/ToC-12B/LZMA chunks); `modelDesc.bin` TLV schema (mostly).
6. **Directly readable web resources?** All of them (see `extracted-minifs/`).
7. **Surviving source paths/symbols/debug info?** JS identifiers intact; MINIFS path strings intact; native symbols: none observable.
8. **Cannot realistically be recovered?** Vendor C source; exact compiler flags; private build system; kernel-internal logic (without unpacking + Ghidra/MIPS work).
9. **What would improve recovery?** MIPS-capable Ghidra + unpacked image (via U-Boot loader RE); SPI flash dump (MTD map, config layout); serial console (boot log, load addresses); vendor GPL drop if it exists.
