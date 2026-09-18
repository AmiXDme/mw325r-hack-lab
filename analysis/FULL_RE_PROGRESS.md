# Full Offline Reversing Pass

Date: 2026-09-18

This report records the broad offline pass over the published MW325R V2
firmware and the recovered web/configuration layer. No firmware was flashed,
no native code was executed, and no router writes were made.

## Artifact

- Archive: `firmware/MW325R_EU_V2_201116.zip`
- ZIP SHA-256: `7b2ba0e0e66ca3a6011e149d06f9879117eef8918f1d5b45a187cbe0b2fa9cb9`
- Firmware: `mw325rv2-eu-up-boot_2020-11-16_13.57.58.bin`
- Firmware size: `987,412` bytes (`0xF10F4`)
- Firmware SHA-256: `629df1f68e315c2e336f3ef451f6006d5750fe2d11d24ebf7f535e077d438c44`

The image is custom `IMG0`, not a standard TRX/uImage/SquashFS/ELF bundle.

## Region Map

| Range | Result |
|---|---|
| `0x0000-0x00FF` | Outer header/signature/tables |
| `0x0100-0xCFFF` | MIPS32LE U-Boot 1.1.3 and plaintext strings |
| `0xD000-0xDFFF` | Padding plus an inner `IMG0` false positive at `0xD094` |
| `0xE000-0xBB093` | 708,756-byte high-entropy packed native image, entropy ~7.9997 |
| `0xBB094-EOF` | MINIFS web/config partition, 221,312 bytes |

## MINIFS

`analysis/minifs_extract.py` reproduced the filesystem extraction:

- MINIFS base: `0xBB094`
- 106 file records
- 7 LZMA-alone chunks
- All 106 records extracted successfully
- Extracted content includes 58 HTML pages, 12 JavaScript files, UPnP XML,
  language files, model descriptors, certificates, and configuration assets

The repository intentionally omits `conf/KEY-NOTE.md`, so the checked-in
recovered tree has 93 files while a raw extraction has 106. That is expected
public-repository redaction, not an extraction failure.

## Native/Bootloader Analysis

Confirmed from plaintext U-Boot:

- MIPS32 little-endian code
- Ralink/MediaTek APSoC strings
- MT7628-related bootloader strings
- SPI flash support and flash-chip tables
- TFTP boot/write recovery paths
- Default boot variables including `bootcmd=tftp`, `bootdelay=1`,
  `ipaddr=192.168.1.2`, and `serverip=192.168.1.10`
- VxWorks image check and LZMA error path
- `imgFileEnc`, offset, and length fields used by the image-loader path

The table around `0xC3E8` is a genuine function-pointer table with numerous
valid U-Boot addresses. Entry `0xC3D4` points to `0xBC00B8CC`, four bytes into
the LZMA error string. This confirms indirect/table-offset string references.

Reusable analysis tool:

```sh
python3 analysis/mips_loader_refs.py firmware.bin
```

The packed native region has not been decrypted. Existing and new offline
tests tried raw LZMA/deflate and simple XOR-style transforms without success.
The next required step is resolving the U-Boot indirect loader dispatch and
recovering the `imgFileEnc` transform.

## Web/TDDP Layer

The recovered JavaScript provides original source for:

- TDDP opcodes 0-11: instruct, write, read, upload, download, reset, reboot,
  auth, peer MAC, config, change password, logout
- Reversible login challenge encoding
- Session/auth flow
- Data-block serialization and parsing
- Configuration schema for 60 blocks
- Wireless scan/WDS commands and block access

Important wireless surface:

- `wlan scan`
- `wlan scanStatus`
- `wlan wdsstatus`
- Block 32: radio/channel/WDS configuration
- Block 33: main SSID/security/WPS
- Block 35: guest SSID/security
- Block 36: AP survey records

These are high-level router operations. No raw 802.11 receive or transmit API
was found in the recovered web/TDDP layer.

## Security/Services

Evidence in the repository documents:

- HTTP-only admin interface on TCP 80
- UPnP SOAP on TCP 1900 without authentication
- DHCP/DNS/NAT services inferred or observed through blocks and behavior
- WPS registrar enabled on the analyzed live unit
- Reversible login protocol encoding
- Packed native server/radio implementation still unavailable

The panel blocks `advanced bm`, associated with CVE-2023-52162. This pass did
not test or develop an exploit.

## Current Conclusions

1. The entire web/configuration/protocol description layer is substantially
   recovered and reproducible.
2. The native VxWorks image and radio driver are not decoded yet.
3. The repository does not prove that the MT7628 radio silicon is incapable of
   monitor mode or injection; it proves only that the stock firmware and
   exposed TDDP API do not provide those operations.
4. Full monitor-mode, deauthentication, handshake capture, or credential
   interception research requires recovering the native image or using
   separate compatible research hardware.

## Verification

The pass completed offline with:

- Firmware hash and region checks
- MINIFS extraction: 106/106 records
- Python compilation of analysis/backend scripts
- JavaScript syntax check of the panel
- Function-presence checks for all major panel tabs
- Git whitespace/diff checks
