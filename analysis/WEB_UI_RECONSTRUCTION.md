# WEB_UI_RECONSTRUCTION.md

Status: sources [EXACT] (106/106 MINIFS files; 4 byte-verified against live unit). Behavior [OBSERVED] live + [RECOVERED] source.

## Stack

Single-page TDDP app. `Index.htm` (826 B, served as `/`) loads `dynaform/class.js` + `class.css`; every admin page is an `.htm` fragment driven by `lib/Quary.js` (auth/TDDP), `lib/DM.js` (opcodes), `lib/model.js` (block schemas), `lib/ajax.js` (transport), `lib/verify.js` (validation), `lib/zepto.min.js` (DOM). Locales: `en_US` + `zh_TW` (`str.js` ×2, `Help.htm` ×2, `locale.css` ×2).

## Pages present (58 `.htm` in `web/common/`)

Login, LoginChgPwd, SysChangeLgPwd, SysBakNRestore, SysUpgrade, SysReboot, Wizard*, Basic* (Network/Wireless/PPPoE/StaticIp/DynamicIp/Pptp/L2tp), Wlan*, WAN/LAN/DHCP/DNS/RouteTable/IPMACBind/MacClone/ParentControl/AccessCtrl/DMZ/VirtualServer/DDNS/IPTV/IPv6/Diagnostic/SystemLog/ManageSettingUp + error.htm. No mobile/Phone* pages in this build (unlike WR841N trees).

## Auth flow [EXACT source + OBSERVED]

```text
Browser --POST ?code=2-->  router returns EUNAUTH + [un, counter, NONCE, CHARSET]
Browser: enc = securityEncode(plaintext, "RDpbLfCPsJZ7fiv", KEY2)   # orgAuthPwd
Browser --POST ?code=7&asyn=0&id=securityEncode(NONCE, enc, CHARSET)--> router
Router: recompute with stored enc; match -> errno 0 (+10-try/2h lockout on failures)
Client stores enc (NOT plaintext) in sessionStorage `lgKey`.
```

`securityEncode(f,d,k)`: per-char `k[(f[g]^d[g]) % len(k)]`, defaults 187 — **reversible XOR** [RECOVERED + mathematically verified]. `KEY2` (255 chars) and nonce `"RDpbLfCPsJZ7fiv"` are hardcoded in `Quary.js`. `changeDefaultPwd` embeds factory-default enc `"WaQ7xbhc9TefbwK"`.

## API inventory (all POST, `?code=<TDDP_*>&asyn=<0|1>`)

READ=2 (block IDs 0–59+, response `\r\n`-separated + `dataBlocks`), WRITE=1, AUTH=7, CHGPWD=10 (`&auth=<old-enc>`, body=new block), REBOOT=6, RESET=5, LOGOUT=11, UPLOAD=3, DOWNLOAD=4 (config backup/restore), CONFIG=9, GETPEERMAC=8, INSTRUCT=0. Unknown codes → connection dropped [OBSERVED].

## Pre-auth exposure [OBSERVED]

- `/`, `dynaform/*`, `css/*`, `images/*`, UPnP XML served without auth.
- Every TDDP READ pre-auth returns empty blocks; every config URL without session → 404/challenge.
