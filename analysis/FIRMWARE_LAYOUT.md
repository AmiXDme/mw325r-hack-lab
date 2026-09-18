# FIRMWARE_LAYOUT.md — `mw325rv2-eu-up-boot_2020-11-16_13.57.58.bin` (987,412 B)

File: `firmware/MW325R_EU_V2_201116.zip` → the 987,412-byte `.bin`.
Work done with Python+strings only (no binwalk/MIPS toolchain on this box).

## Outer header (plaintext, offsets in file)

```
0x00: 16 bytes signature/checksum: 00142fc0 0ca4d940 7ff26bf8 7d746e5a
0x10: "IMG0" + u16s: 000f 1100 0325 0303 | 0000 0001 6a02 0201
0x20: 8 dwords (LE): 01000000 102026a 00000001 ... 01000000 00d00000 ...
0x94: descending u16 table: ff00 fd00 3403 3203 3003 ... 1e03, each +0010
```

Exact field semantics need the bootloader parser; bytes above are observed,
not decoded. (`IMG0` = Mercusys image magic.)

## Region map (entropy + magics, verified)

| Offset | Size | Entropy | Content |
|---|---|---|---|
| 0x0000–0x3FFF | 16 KB | 5.9 | outer header + tables |
| 0x4000–0xB800 | ~30 KB | 6.6–7.1 | **U-Boot 1.1.3** (plaintext MIPS code+strings) |
| 0x10000–0xB8000 | 672 KB | **8.000 flat** | **ENCRYPTED system code** (kernel+rootfs+TDDP server) |
| 0xBB094–EOF | ~220 KB | ~7.9 | **MINIFS** webfs+conf, 7× LZMA-alone streams, fully extracted (106/106 files) |
| 0xF0000–EOF | — | — | NOT padding: encrypted/MINIFS data runs to 0xF10D4 |

Notes:
- `IMG0` at 0xD094 is a FALSE POSITIVE (bytes inside a MINIFS LZMA stream).
- `gzip`/`JFFS2`/`lzma-alone` hits outside MINIFS are noise in encrypted data
  (all trial decompressions fail).
- Tail is not erased-flash padding: image is a packed upgrade file, not a
  raw flash dump.

## U-Boot 1.1.3 (Nov 10 2020, Ralink APSoC = MT7628)

- Standard MediaTek/Ralink SDK menu: TFTP load / flash boot / bootloader
  burn / SDRAM boot, `bootdelay=1`, `baudrate=57600`.
- Default env: `bootcmd=tftp ipaddr=192.168.1.2 serverip=192.168.1.10`.
- **UART + TFTP = unbrick path** (1 s window, 57600 baud).
- SPI flash driver table (Winbond/MXIC/GigaDevice/etc.).
- No backdoor/credential strings found.
- Key print: `imgFileEnc=0x%x, offset=0x%x, len=0x%x` immediately followed by
  `LZMA ERROR %d - must RESET board to recover` → the encrypted blob feeds
  an LZMA decoder after de-obfuscation. **No AES S-box anywhere** (not AES).

## MINIFS (web UI + conf) — fully open

- Extracts 106/106 with `analysis/minifs_extract.py`; `web/` code files are
  **byte-identical to the live router** (only `*_me.png` theme images were
  skipped by the earlier extraction).
- `conf/` holds: `modelDesc.bin` (TDDP data model — true block names, see
  below), `mcbDesc.bin`, `server-cert.pem`, `2048_newroot.cer` (stock
  VeriSign G5 root, boring), **`priv-key.pem` — KEPT OFF GITHUB**.

## Security findings (local only, never published)

- Shipped private key: **512-bit RSA** (`openssl rsa -check` OK) — factorable
  in hours on a PC — self-signed TP-Link SDMP cert (2014, **expired 2017**),
  identical in every unit. `server-cert.pem` matches it.
- Login crypto is reversible XOR (see DIRECT_TDDP.md). Admin page HTTP-only.
  UPnP answers unauthenticated. (All previously reported.)

## True block names (`conf/modelDesc.bin`)

ALLCAPS model names in file order (ids confirmed where live data agrees):

```
DEVICE SYSTEM SYSTEM_LOG EXCEPT_LOG [4:LAN] LCLPORT LCLHOST RMTHOST DHCPS
DHCPS_LEASE TPDOMAIN FACTORY STACTRLTBL STARTTABLE STATIC_ROUTE
DYNAMIC_ROUTE SYSTEM_ROUTE NAPT_ALG NAPT_DMZ NAPT_IGD NAPT_IGD_MAPPING
NAPT_VSERVER LINK_STATUS TSTATIC_IP DHCPC TPPPOE PPPOE_LASTDIAL
SNTPC_CONFIG SNTPC_TIME PARENT_CTL BEHAVMANG_CONFIG DWLAN_BASIC
MBSSID_MAIN MBSSID_IPTV MBSSID_GUESTNET LWLAN_AP_LIST DDNS_STATUS
IPV6_* MANUFACTURE_MODE WLAN_BASIC_5G MBSSID_MAIN_5G MBSSID_GUESTNET_5G
LLANGUAGE HW_NAT SCHEDULE_REBOOT ISPPRESET ISP_RUNTIMEDATA
```

Corrections applied to BLOCKMAP.md: 24 TSTATIC_IP, 25 DHCPC (=WAN DHCP
client block), 26 TPPPOE, 32 DWLAN_BASIC, 36 LWLAN_AP_LIST, 41 DDNS_STATUS
(live value `status:["0","0"]` = the 2 DDNS slots' status — confirms it),
55 LLANGUAGE. 5G blocks are dormant (2.4 GHz-only SoC).

## The wall (honest)

The 672 KB system-code blob (kernel + rootfs + TDDP daemon) is encrypted
with an unknown `imgFileEnc` transform (not AES, not XOR-FF, not
byte-swaps; no MIPS disassembler on this box to read the U-Boot routine).
Next step needs Ghidra + MIPS on a PC: load U-Boot @ its link address,
find xrefs to the `imgFileEnc=` format string, read the transform + key,
decrypt 0x10000–0xB8000. Everything else on this device is already open.
