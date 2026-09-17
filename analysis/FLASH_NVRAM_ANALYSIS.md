# FLASH_NVRAM_ANALYSIS.md

Status: image layout [EXACT]; on-flash partitions [INFERRED]; NVRAM [UNKNOWN].

## Image → flash map [RECONSTRUCTED from offsets + entropy + U-Boot strings]

```text
file 0x00000 (IMG0 hdr+U-Boot)      -> flash boot partition (Ralink SPI, "raspi_*" driver)
file 0x0E000 + ~700 KB packed blob  -> kernel+app partition ("Boot system code via Flash")
file 0xBB094 + MINIFS (web+conf)    -> web/config partition (mounted read-only at runtime)
file 0xF0000+ padding               -> alignment to erase-block size
```

Flash chip ID/jejdec, exact MTD names/sizes: [UNKNOWN] (would need live `/proc/mtd` or SPI dump; not accessed).

## NVRAM

No `nvram_*` symbols, no `nvram` strings, no NVRAM partition markers found [EXACT search]. Configuration almost certainly lives in a dedicated flash region read/written by the config manager (WRITE=1 path) — layout [UNKNOWN].

## Write-safety notes (for the owner)

- U-Boot offers TFTP write paths for bootloader AND system code, with Y/N confirm for erases [EXACT strings] — misflash = brick without serial recovery.
- `SysUpgrade.htm` flow + `UPLOAD=3/DOWNLOAD=4` (backup/restore) are the only vendor-supported write paths; signature/checksum enforcement inside the packed image [UNKNOWN] — do not downgrade/forge images.
- No flash writes were performed in this investigation.
