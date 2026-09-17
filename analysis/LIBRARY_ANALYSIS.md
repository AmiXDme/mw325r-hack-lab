# LIBRARY_ANALYSIS.md

## Shared libraries: NONE shipped [EXACT]

No `.so` files, no `/lib` tree — consistent with a statically-linked VxWorks monolith (see EXECUTABLE_ANALYSIS.md). There is nothing to `ldd`.

## Client-side "libraries" (shipped as source) [EXACT]

| File | Size | Role |
|---|---|---|
| `web/lib/Quary.js` | ~47 KB (in `class.js` bundle flow) | Auth + TDDP client (`securityEncode`, `orgAuthPwd`, `auth`, `read/write/instr/reboot/reset/changePwd/logout`) |
| `web/lib/DM.js` | 3,335 B | TDDP opcode constants (see below) |
| `web/lib/model.js` | 10,541 B | Data-block model definitions |
| `web/lib/ajax.js` | 7,454 B | Transport layer |
| `web/lib/verify.js` | 5,286 B | Input validation |
| `web/lib/zepto.min.js` | (vendored) | DOM utility (Zepto, MIT; referenced by `class.js`) |

## TDDP opcode table [EXACT — `web/lib/DM.js`]

```text
INSTRUCT=0  WRITE=1  READ=2  UPLOAD=3  DOWNLOAD=4  RESET=5
REBOOT=6    AUTH=7   GETPEERMAC=8  CONFIG=9  CHGPWD=10  LOGOUT=11
```

Live-verified: unknown opcodes (133/255) drop the connection; `CHGPWD(10)` without params → errno 3.

## Third-party / open-source components [RECOVERED strings + files]

- U-Boot 1.1.3 (GPL) — bootloader, version string [EXACT].
- LZMA SDK (decompressor referenced by `LZMA ERROR`, config `0x5D000080`) — public-domain-ish [INFERRED].
- Zepto / jQuery 1.10.1 (MIT) — vendored in web UI [RECOVERED files].
- OpenSSL-format PKI (`priv-key.pem`, `server-cert.pem`, `2048_newroot.cer`) — key material, not library code.
- No BusyBox / glibc / musl / OpenWrt traces anywhere [EXACT — zero hits].
