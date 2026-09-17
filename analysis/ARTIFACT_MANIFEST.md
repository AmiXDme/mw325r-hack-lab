# ARTIFACT_MANIFEST.md

Status convention: `[EXACT]` = byte-verified fact · `[RECOVERED]` = extracted artifact · `[INFERRED]` = reasoned conclusion.

## Device under test [EXACT — live observation]

| Field | Value |
|---|---|
| Manufacturer | MERCUSYS |
| Model | MW325R |
| Hardware revision | 2.0 (`modelVer 2.0`, `hardVer MW325R 2.0`) |
| Firmware (on device) | 2.2.1 Build 201115 Rel.70272n |
| MAC | 38-6b-1c-XX-XX-XX |
| CPU arch | MIPS32 little-endian [INFERRED — LE-MIPS prologues in bootloader: 11× `addiu sp`, 24× `jr ra`; Ralink SPI strings; U-Boot 1.1.3] |
| OS | VxWorks (Server header `vxWorks/5.5`; `vxWorks Image` string in bootloader) [EXACT strings, version from banner] |
| Bootloader | U-Boot 1.1.3 (Nov 10 2020) [EXACT string] |
| RAM / Flash / chipset | [UNKNOWN] — no readable SPD/MTD strings; not probed on live unit |

## Firmware artifact analyzed [RECOVERED]

> ⚠️ The exact on-device build (**201115**) is **[UNAVAILABLE]** for download — Mercusys publishes only the next build. Everything below is the **201116** image, one month newer, same V2 hardware. Findings about file *formats, protocols and mechanisms* transfer; exact bytes may differ.

| Field | Value |
|---|---|
| URL | https://static.mercusys.com/software/MW325R(EU)_V2_20111620201211065426.zip |
| Page | https://www.mercusys.com/en/download/mw325r/v2/ |
| Filename | `mw325rv2-eu-up-boot_2020-11-16_13.57.58.bin` (+ upgrade PDF) |
| Version | MW325R(EU)_V2_201116 (English), 2020-12-11 |
| Size | 987,412 bytes (`0xF10F4`) |
| SHA256 | `629df1f68e315c2e336f3ef451f6006d5750fe2d11d24ebf7f535e077d438c44` |
| MD5 | `333f7de70730f323c71a9b6dae00c205` |
| Container | Custom `IMG0` + U-Boot + packed VxWorks image + MINIFS web partition |
| Downloaded | 2026-09-17 |

## Searched, not found [UNAVAILABLE]

- `MW325R(EU)_V2_201115*` on mercusys.com (en/bd/br/mx mirrors), static.mercusys.com — only 201116 / 200824 / 180206 / 171106 listed.
- GPL source portal publishes no MW325R v2 package found during this session.
