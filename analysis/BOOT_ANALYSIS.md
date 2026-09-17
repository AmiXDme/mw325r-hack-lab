# BOOT_ANALYSIS.md

Status: strings [EXACT] (U-Boot 1.1.3 plaintext in image); sequence [RECONSTRUCTED] from strings + observed behavior.

## Layout on flash (file offsets) [EXACT]

| Range | Content | Entropy |
|---|---|---|
| `0x00000–0x000FF` | IMG0 header (magic `IMG0` @0x16, MD5-like signature, MIPS load addrs `0x80000000`/`0x80100F00`) | low |
| `0x00100–0x00CFFF` | U-Boot 1.1.3 code + strings (Ralink `raspi_*` SPI driver) | 4.8–7.0 |
| `0x00D000–0x00DFFF` | Zero padding | 0 |
| `0x00E000–0x0BAFFF` | Packed VxWorks kernel+app (~700 KB, method [UNKNOWN] — not raw LZMA/deflate; `imgFileEnc` flag exists) | 7.95 |
| `0x0BB094+` | MINIFS web partition (magic `MINIFS`, 106 files, LZMA chunks) | mixed |
| `0x0F0000–EOF` | Zero padding | ~0 |

## Reconstructed boot chain

```text
POWER ON → U-Boot 1.1.3 (SPI flash init, DRAM relocate)
  → autoboot menu (bootdelay=1; options: TFTP load / flash boot / TFTP+write)
  → "Booting image at 0x…": checks "vxWorks Image", reads imgFileEnc/offset/len
  → LZMA-decompress kernel to SDRAM (loadaddr 0x80001000-class)
  → VxWorks 5.5 boots → mounts MINIFS (web UI) → starts httpd/TDDP, UPnP, DHCP, wireless
  → login page on :80, UPnP on :1900
```

## Recovery facilities [EXACT strings]

- U-Boot autoboot menu with TFTP load/write paths (`serverip=192.168.1.10` default, `uboot.bin`/`bootfile` names).
- `bootcmd=tftp`, `bootdelay=1` — 1-second window for serial/TFTP recovery [INFERRED standard U-Boot behavior].
- Serial console implied by baudrate strings; header pins [UNKNOWN] (no hardware inspection performed).
