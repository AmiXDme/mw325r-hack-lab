# NETWORK_SERVICES.md

Status: ports [OBSERVED] (connect-scan from LAN); configs [RECOVERED] (`web/upnp/*.xml`); processes [INFERRED] (no shell on device).

## Listening services (LAN)

| Port | Proto | Service | Auth | Evidence |
|---|---|---|---|---|
| 80 | TCP | TDDP-over-HTTP admin + static assets | TDDP session for data; assets open | curl + CDP sessions [OBSERVED] |
| 1900 | TCP | UPnP SOAP (IGDv1 + WFAWLANConfig) | **None** — `igd.xml`/`wfa.xml`/SCPDs open; `AddPortMapping` + `DeletePortMapping` executed without credentials | live SOAP [OBSERVED] |
| 1900 | UDP | SSDP | M-SEARCH unicast unanswered [OBSERVED] | — |
| 21/22/23/53/443/8080/… | — | — | CLOSED [OBSERVED] | — |

Banner: `Server: vxWorks/5.5 UPnP/1.0 MW325R/2.0` [EXACT].

## UPnP tree [RECOVERED from `web/upnp/`]

`igd.xml` → Layer3Forwarding(`/l3f`), WANCommonInterfaceConfig(`/ifc`), WANIPConnection(`/ipc`); `wps.xml` → WFAWLANConfig(`/wfa`: GetDeviceInfo/GetAPSettings/SetAPSettings/PutMessage/… — `GetDeviceInfo` returns 401 Invalid Action [OBSERVED]).

## LAN services (inferred from blocks/strings)

DHCP server (block 9 leases [OBSERVED]), DNS relay, NAT/firewall (iptables-style, no direct evidence — [INFERRED] standard), wireless AP (WPA2-PSK, WPS **enabled** [OBSERVED]), TR-069/SDMP PKI present (`server-cert.pem` TP-Link SDMP, self-signed, **expired 2017**) — active TR-069 use [UNKNOWN].

## SERVICE MATRIX (condensed)

| Service | Process [INFERRED] | Port | Startup [INFERRED] | Purpose |
|---|---|---|---|---|
| httpd/TDDP | VxWorks task (monolith) | 80 | boot services | admin UI + config API |
| upnpd | VxWorks task | 1900 | boot services | IGD + WPS-UPnP |
| dhcpd | VxWorks task | 67/udp | with LAN | leases (block 9) |
| dns relay | VxWorks task | 53/udp | with WAN | forwarding (closed to scan — filtered or bound selectively) |
| wlan driver | driver + task | — | boot | AP, WPA2, WPS registrar |
