# BLOCKMAP.md — all 60 TDDP data blocks decoded

Status: live-read from the owner's unit (authenticated `readEx`), purposes
[RECOVERED] from `modelDesc.bin` names + page sources + observed values.

| ID | Name [INFERRED] | Key fields | Writable |
|---|---|---|---|
| 0 | DEVICE | fullName/facturer/modelName/Ver, softVer/hardVer, prodId, hw/firmware IDs | no |
| 1 | SYSTEM | authKey (admin cred), setWzd, mode, logLevel, mac[2] | via CHGPWD only |
| 2 | SYSLOG | num + list(level/days/hours/msg) — 83 entries live | no |
| 3 | (empty log buffer) | 8 blank msgs | no |
| 4 | LAN-IFACE | ip/mask/mode | [UNKNOWN path] |
| 5 | REMOTE-MGMT | port 80 | [UNKNOWN] |
| 6 | REMOTE-MGMT-ACL | enableAll + 4 MAC slots | [UNKNOWN] |
| 7 | REMOTE-MGMT-RULE | port 8888, rule, addr | [UNKNOWN] |
| 8 | DHCP-SERVER | enable, poolStart/End, leaseTime, dns, gateway | **yes (UI)** |
| 9 | DHCP-LEASES | lease list | no |
| 10 | DDNS | enable=1, name=mwlogin.net | [UNKNOWN] |
| 11 | LAN-NET | lanIp/lanMask + authKey | **yes (UI)** |
| 12 | CLIENT-ADMIN (legacy view) | ip/mac/name/blocked/up/down/limits | no (use 13) |
| 13 | STA-MGMT | ip/mac/type/online/**blocked**/up/down/**upLimit/downLimit**/name | via `staMgt` instr |
| 14–15 | TABLES | generic lists | [UNKNOWN] |
| 16 | ROUTE-TABLE | net/mask/gateway/netif | no |
| 17 | ALG | ftp/pptp/rtsp/sip/ipsec/h323 enables | [UNKNOWN] |
| 18 | DMZ | dmzEnable/dmzClient | **yes (UI)** |
| 19 | UPNP-IGD | igdEnable | **yes (UI)** |
| 20 | UPNP-MAPPINGS | port-mapping list | via UPnP SOAP / `forward` |
| 21 | VSERVER-RULES | 16 slots (enable/lclIp/ports/ptc) | via `forward` instr |
| 22 | WAN-LINK | linkMode/linkType | [UNKNOWN] |
| 23 | WAN-STATUS | ip/mask/gateway/dns/upTime/inOut pkts+octets | no (counters) |
| 24 | WAN-STATIC | ip/mask/gateway/dns/mtu | [UNKNOWN] |
| 25 | WAN-DNS | name/mtu/ucast/**manualDns**/**dns[2]**/lastIp | **yes (UI)** |
| 26 | PPPOE | name/**paswd**, fixip, dns, mtu | view masked; write w/ care |
| 27 | PPPOE-SESS | acMac/sessionid/dialMode | no |
| 28–29 | TIME | timeZone + clock/sntp status | [UNKNOWN] |
| 30 | PARENTAL | enable/weekdays + mac list | [UNKNOWN] |
| 31 | ACCESS-CTRL | rList/hList/tList/sList rule tables | [UNKNOWN] |
| 32 | WLAN-RADIO | enable/mode/region/**channel**/width/adv/apc | **yes (UI)** |
| 33 | WLAN-MAIN | **cSsid/cPskSecret**/bcast/security/**wps{enable,PIN}** | **yes (UI)** |
| 34–35 | WLAN-GUEST/VAP | same shape as 33 (guest inet — **verified live**) | **yes (UI)** |
| 36 | AP-SURVEY | apEntry (BSSID/SSID/RSSI/channel) | no (scan results) |
| 37 | VLAN/IPTV | uMode/ports/service table | [UNKNOWN] |
| 38–39 | L2TP/PPTP-WAN | userName/**passwd**/domainIp/ip/dns/mtu | view masked |
| 40 | SERVICES | mode + serviceList | [UNKNOWN] |
| 41 | STATUS | status pair | no |
| 42–43, 51 | IPv6-MODES | mode/interfaceType/ipGetMethod | [UNKNOWN] |
| 44–50 | IPv6-ADDRS | all `::` (unused) | — |
| 52–54 | RADIO-SLOTS | same shape as 32/33, disabled | [UNKNOWN] |
| 55 | LOCALE | en_US,zh_TW | [UNKNOWN] |
| 56 | ? | enable=0 | [UNKNOWN] |
| 57 | SCHEDULE | enable/type/weekday/hour/min/sec/remainTime | [UNKNOWN] |
| 58 | MISC | authKey empty, option66Disable=1 | [UNKNOWN] |
| 59 | ISP-STATS | bIspReset/wUrlTimes/curTicks | no |

Secrets seen live (kept OFF GitHub): PPPoE/L2TP/PPTP passwords, WPS PIN, SYSTEM+FACTORY authKeys.
