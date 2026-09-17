# THIRD_PARTY_COMPONENTS.md

| Component | Version | License | Evidence |
|---|---|---|---|
| U-Boot | 1.1.3 (Nov 10 2020) | GPL-2.0 | Version string [EXACT]; source: denx.de (generic; vendor board port is proprietary) |
| LZMA SDK (decompressor) | unknown | public-domain (Igor Pavlov) | `LZMA ERROR`, `0x5D000080` streams [EXACT] |
| Zepto.js | minified, version [UNKNOWN] | MIT | `web/lib/zepto.min.js` shipped [EXACT]; source: zeptojs.com |
| TP-Link SDMP PKI | self-signed cert 2014–2017 | proprietary | `server-cert.pem` [EXACT] |
| Ralink SPI/ETH/WLAN drivers | unknown | proprietary (Ralink/MTK) | `raspi_*` strings [EXACT]; no version string found |
| VxWorks | 5.5 (banner) | proprietary (Wind River) | UPnP banner + `vxWorks Image` string [EXACT] |

No BusyBox, glibc/musl/uClibc, OpenWrt, hostapd, dnsmasq, dropbear, lighttpd/boa binaries or strings anywhere in the image [EXACT — searched].
