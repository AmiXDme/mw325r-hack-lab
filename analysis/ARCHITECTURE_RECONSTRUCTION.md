# ARCHITECTURE_RECONSTRUCTION.md

```text
Hardware (Ralink MIPS24KEc-class SoC [INFERRED], SPI flash, 2.4GHz radio, switch)
  ↓
U-Boot 1.1.3 [EXACT] (TFTP recovery, imgFileEnc/LZMA loader)
  ↓
VxWorks 5.5 monolith [banner EXACT] (no ELF, no BusyBox, static link)
  ├── httpd/TDDP task (:80) — opcodes 0–11, block model 0–59 [EXACT client sources]
  ├── UPnP task (:1900 TCP) — IGDv1 + WFAWLANConfig, no auth [OBSERVED]
  ├── dhcpd / dns-relay / wlan driver+registrar (WPS ON [OBSERVED])
  └── config manager — modelDesc.bin schema, flash-backed [INFERRED store]
  ↓
MINIFS (read-only web+conf, LZMA chunks) [EXACT — fully extracted]
  ↓
Browser SPA (Quary/DM/model/ajax/verify/zepto, en_US+zh_TW) [EXACT]
```

- Boot: BOOT_ANALYSIS.md. Services: NETWORK_SERVICES.md. Storage: FLASH_NVRAM_ANALYSIS.md.
- Privilege boundaries: everything runs in one VxWorks image (flat memory, no processes/containers) [INFERRED standard VxWorks] — a single RCE = full device.
- IPC: not observable statically; TDDP task presumably serves blocks from shared config memory [INFERRED].
