# DEPENDENCY_GRAPH.md

```text
mw325rv2-...bin (IMG0)
├── U-Boot 1.1.3 ──depends──> SPI flash (raspi_*), DRAM, TFTP (recovery)
├── packed VxWorks image ──depends──> U-Boot loader (imgFileEnc/LZMA) [UNKNOWN codec]
│   ├── httpd/TDDP task ──serves──> MINIFS web/* (106 files)
│   │     └── Quary/DM/model/ajax ──drives──> TDDP opcodes 0-11
│   ├── UPnP task ──serves──> MINIFS web/upnp/*.xml
│   ├── wlan/dhcp/dns tasks ──read──> config store (modelDesc.bin schema)
│   └── TLS/SDMP role ──uses──> conf/priv-key.pem + server-cert.pem
└── MINIFS ──depends──> LZMA-alone (0x5D000080) [EXACT, extracted]
```

Build/optimum direction for reimplementation: replace bottom-up — OpenWrt (Linux) + uhttpd + new SPA reusing the *protocol semantics* in SOURCE_RECONSTRUCTION.md (not the code).
