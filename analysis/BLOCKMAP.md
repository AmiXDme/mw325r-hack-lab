# BLOCKMAP.md — all 60 TDDP data blocks decoded

Status: live-read from the owner's unit (authenticated `readEx`), purposes
[RECOVERED] from `modelDesc.bin` names + page sources + observed values.

| ID | Name [INFERRED] | Key fields | Writable |
|---|---|---|---|
| 0 | DEVICE | fullName/facturer/modelName/Ver, softVer/hardVer, prodId, hw/firmware IDs | no |
| 1 | SYSTEM | authKey (admin cred), setWzd, mode, logLevel, **mac[0]=LAN/mac[1]=WAN, wanMacType** (MAC-clone page) | mac[1]+wanMacType via UI |
| 2 | SYSLOG | num + list(level/days/hours/msg) — 83 entries live | no |
| 3 | (empty log buffer) | 8 blank msgs | no |
| 4 | LAN-IFACE | ip/mask/mode | [UNKNOWN path] |
| 5 | REMOTE-MGMT (LCLPORT) | local web port 80 | view |
| 6 | LOCAL-ADMIN-ACL (LCLHOST) | enableAll + 4 manager MACs | **yes (UI)** |
| 7 | REMOTE-ADMIN (RMTHOST) | rule 0=off/1=all/2=one-IP + port(1024-65535) + addr | **yes (UI)** |
| 8 | DHCP-SERVER | enable, poolStart/End, leaseTime, dns, gateway | **yes (UI)** |
| 9 | DHCP-LEASES | lease list | no |
| 10 | DDNS | enable=1, name=mwlogin.net | [UNKNOWN] |
| 11 | LAN-NET | lanIp/lanMask + authKey | **yes (UI)** |
| 12 | STACTRLTBL (IP-MAC bind view) | list(ip/mac/name/**bindEntry**/staMgtEntry/blocked/limits) | binds via `main staMgt -add/-delete bind` instr |
| 13 | STA-MGMT | ip/mac/type/online/**blocked**/up/down/**upLimit/downLimit**/name | via `staMgt` instr |
| 14 | STATIC-ROUTES | list(enable/net/mask/gateway) via `main route -stc -add/-delete/-clr` | **yes (UI)** |
| 15 | TABLES | generic list | [UNKNOWN] |
| 16 | ROUTE-TABLE (effective) | net/mask/gateway (computed view) | no (view in UI) |
| 17 | ALG | **ftp/pptp/rtsp/sip/ipsec/h323AlgEnable** | **yes (UI)** |
| 18 | DMZ | dmzEnable/dmzClient | **yes (UI)** |
| 19 | UPNP-IGD | igdEnable | **yes (UI)** |
| 20 | UPNP-MAPPINGS | auto port maps (ext/int port, client, desc) | no (view in UI) |
| 20 | UPNP-MAPPINGS | port-mapping list | via UPnP SOAP / `forward` |
| 21 | VSERVER-RULES | 16 slots (enable/lclIp/ports/ptc) | via `forward` instr |
| 22 | WAN-LINK | linkMode/linkType 0=DHCP 1=static 2=PPPoE 3=L2TP 4=PPTP | **yes (UI, +linkDown/linkUp bounce)** |
| 23 | WAN-STATUS | ip/mask/gateway/dns/upTime/inOut pkts+octets | no (counters) |
| 24 | WAN-STATIC | ip/mask/gateway/dns[2]/mtu | **yes (UI)** |
| 25 | WAN-DNS | name/mtu/ucast/**manualDns**/**dns[2]**/lastIp | **yes (UI)** |
| 26 | PPPOE | name/**paswd**(blank=keep), fixipEnb/fixip, manualDns/dns, **lcpMru**=MTU(576-1492), dialMode | **yes (UI, masked)** |
| 27 | PPPOE-SESS | acMac/sessionid/dialMode | no |
| 28–29 | TIME (SNTPC_CONFIG / SNTPC_TIME) | 28:**timeZone** (stored = UI_select − 720); 29: year/month/day/hour/min/sec/**sntpcSuccess** | tz via UI; clock read-only |
| 30 | PARENTAL (PARENT_CTL) | enable + mon..sun + mac list | **yes (UI editor)** |
| 31 | ACCESS-CTRL (BEHAVMANG) | **bhavEnable**/bhavRule + r/h/t/s rule tables | master switch via UI; tables in stock UI |
| 32 | WLAN-RADIO (WLAN_BASIC) | enable/mode/region/**channel**/width/adv + **apc{bBridgeEnabled,cBridgedSsid,cBridgedBssid,uSecurityType,cPassWD}** (WDS bridge) | **yes (UI)** |
| 33 | WLAN-MAIN (MBSSID_MAIN) | **cSsid/cPskSecret**/bcast/security/**wps{enable,PIN}** | **yes (UI)** |
| 34 | WLAN-IPTV (MBSSID_IPTV) | ⚠️ NOT guest — panel previously misused it as guest (fixed) | — |
| 35 | WLAN-GUEST (MBSSID_GUESTNET) | **bEnable/cSsid/bSecurityEnable/cPskSecret/bLanAccess/uMaxUp/uMaxDown/bSetOpenTime/uDuration/uAllowTimeMode/uTimeTable** (+wps block) | **yes (UI)** |
| 36 | AP-SURVEY (WLAN_AP_LIST) | apEntry (BSSID/SSID/RSSI/channel/auth/width) via `wlan scan` → poll `wlan scanStatus` → read | no (scan results; `wlan wdsstatus` = link state) |
| 37 | VLAN/IPTV | **uMode** 0=off/1=manual/2=auto + uService[] table | mode via UI; table view |
| 38–39 | L2TP/PPTP-WAN | userName/**passwd**(blank=keep)/domainIp/bDhcp/ip/mask/gateway/dns/mtu | **yes (UI, masked)** |
| 40 | DDNS | mode + serviceList[2]{enable,username,**password**(blank=keep),domainName,ip,status} | **yes (UI, masked)** |
| 41 | STATUS | status pair | no |
| 42–43, 51 | IPv6-MODES | mode/interfaceType/ipGetMethod | [UNKNOWN] |
| 44–50 | IPv6-ADDRS | all `::` (unused) | — |
| 52–54 | RADIO-SLOTS | same shape as 32/33, disabled | [UNKNOWN] |
| 55 | LOCALE | en_US,zh_TW | [UNKNOWN] |
| 56 | ? | enable=0 | [UNKNOWN] |
| 57 | SCHEDULE (SCHEDULE_REBOOT) | enable/type/weekday/hour/min/sec/remainTime — ⚠️ **ARMED on owner's unit (enable=1, recurring Mon 03:30); NOT clearable via TDDP (writes errno 2, no instr verb, survives reboot). Factory reset is the only known disarm; needs owner consent.** | no — hands off |
| 58 | MISC | authKey empty, option66Disable=1 | [UNKNOWN] |
| 59 | ISP-STATS | bIspReset/wUrlTimes/curTicks | no |

Secrets seen live (kept OFF GitHub): PPPoE/L2TP/PPTP passwords, WPS PIN, SYSTEM+FACTORY authKeys.
