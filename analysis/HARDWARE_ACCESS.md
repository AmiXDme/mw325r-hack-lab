# HARDWARE_ACCESS.md — flash layout, UART shell, CVE note

Credit: independent researcher k4m1ll0 (vicarius.io RE series, CVE-2023-46297 /
CVE-2023-52162 on this exact model). Findings below cross-checked against our
own firmware image and live unit. No exploit code is kept here.

## Flash layout (1 MB SPI, e.g. EN25QH16B) — via UART `flash -layout`

```
0x000000 BOOTIMG   52K   (U-Boot 1.1.3 + header + MINIFS web UI)
0x00D000 FIRMWARE 948K   (TPOS image, imgFileEnc-encrypted, offset=0x80)
0x0FA000 CONFIG     8K   (live settings incl. armed block-57 schedule)
0x0FC000 EXPLOG     8K   (exception log)
0x0FE000 PROFILE    4K
0x0FF000 RADIO      4K   (WiFi calibration / ART)
```

Our upgrade file (987,412 B) = BOOTIMG + FIRMWARE regions. Its MINIFS
extracts 106/106, byte-identical to the live router (see FIRMWARE_LAYOUT.md).

## UART shell (root, VxWorks tasks — not Linux)

- 4-pin header: RX / TX / GND / VCC(square). **115200 baud** (ours: 57600 is
  the *bootloader*; OS shell is 115200 per the researcher).
- Interrupts to U-Boot menu; `flash -read <off> <len> <memaddr>` +
  `mem -dump` reads arbitrary flash (how the researcher dumped it).
- Live RAM holds the DECRYPTED system (decryption happens at boot), so a
  serial shell sees what static analysis cannot. Requires opening the case +
  USB-TTL adapter + (usually) soldering. Do this only if you accept the
  hardware risk.

## CVE-2023-52162 (authenticated RCE, fixed nowhere — all versions affected)

- Stack overflow in the `advanced bm ...` INSTRUCT verb parser (behavior
  management). Needs an admin session, i.e. the admin password.
- **Our panel hard-blocks `advanced bm`** in both backends
  (`blocked-cve-2023-52162`) while keeping the safe `advanced pc` parental
  verbs. Verified live on both ports.
- Practical meaning: never type/paste `advanced bm` commands from the
  internet into any console, and never share router admin access.

## CVE-2023-46297 (language-switch page blanking, unauthenticated nuisance)

- Setting `currentLanguage` to garbage blanks the stock UI for everyone
  (fix: set it back via TDDP block write). Our panel is unaffected
  (separate UI), and could repair a blanked unit by rewriting the language
  fields — noted, not implemented (no live case).
