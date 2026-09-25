# 🧪 Hack Lab — ESP32WifiPhisher, no ESP32 needed

The whole WifiPhisher-for-ESP32 feature set, rebuilt on your PC + MW325R.
Analysis source: `/home/mint/Desktop/ESP32WifiPhisher` (firmware `src/`, `data/`).

## The idea

The ESP32 did two jobs: **RF** (broadcast AP, deauth frames, promiscuous sniff)
and **brain** (portal server, DNS, API, capture, verify). Your PC has no
monitor-mode adapter — but your **router can do the RF** and your **PC can do
the brain**, so the lab splits the work:

| Job | ESP32WifiPhisher | This lab |
|---|---|---|
| Broadcast the twin SSID | ESP32 SoftAP | MW325R WiFi block 33 (real radio) |
| Kick clients off the real AP | raw deauth frames | channel-squat (beacon war) via block 32 |
| Give victims IPs | ESP32 DHCP | router DHCP (block 8) — real leases |
| DNS → capture every lookup | dns_server_start() | PC UDP :5354 (any name → this PC) |
| Captive-portal 302 hijack | redirect_handler() | identical probe-URL list |
| Phishing pages | SPIFFS data/ | **the very same files** in `dashboard/portal/` |
| Portal ⇄ firmware protocol | WS `/ws` JSON cmds | PC WebSocket bridge, same cmds 0–32 |
| Capture passwords | password_manager → SPIFFS | PC RAM ring buffer (+ optional file) |
| Verify a submitted key | on-device 4-way-handshake MIC | **router WDS-joins the real AP with it** — `wdsstatus 5` = key correct |
| Recon (APs/clients) | promiscuous sniffer | router site survey + DHCP/station tables |
| Host discovery / port scan | ARP sweep + TCP scan | real — PC ARP sweep, mDNS, SSDP, TCP connect |
| Sniffer stream | RF frames → WS 'packet' | tcpdump on the LAN → WS 'packet' (same JSON) |
| Handshake pcap export | synthesized pcap over WS | synthesized pcap over WS (same format) |
| Karma | RF probe responses | open twin lures probe-happy devices (no RF inject) |
| BLE scan/spam | NimBLE sniffer | bluetoothctl scan (adapter optional) |

The original `admin.html` console works **unmodified** against this backend:
open it from the portal and you get the ESP32 UI (status, scan, deauther,
karma, sniffer, aircrack, host/port/BLE scans) driven by the PC engine.

## Run

```bash
./launch-panel.sh   # starts EVERYTHING and opens the panel app window:
                    #   headless Chrome CDP :9222 (router session)
                    #   router_api  :8100 (TDDP backend)
                    #   hacklab_api :8101 (portal :8080, DNS :5354, WS :8765)
                    #   dashboard   http://localhost:8099/control.html
```

One login unlocks everything: both backends drive the same headless Chrome,
and the lab engine adopts the router session from the live page (`$.pwd`) —
log in once in the panel (or the lab) and scan/twin/verify work everywhere,
including the ESP32 `admin.html` console on the portal port.

Ports: unprivileged defaults (8080/5354). For the classic captive-portal ports
run the lab engine as root: `sudo python3 hacklab_api.py` (binds :80/:53 and
tcpdump sees the whole LAN).

## Tab walkthrough

1. **Target** — Scan pulls the router's real site survey; pick an AP.
2. **Launch** — choose the phishing scheme (fwupgrade / netmng / oauth / admin)
   and whether submitted passwords are verified. LAUNCH: snapshots your WiFi
   config, broadcasts the twin, hijacks DNS, arms the portal.
3. **Victims** — live joins/leaves (router leases + stations, polled).
4. **Credentials** — every portal submission, with the WDS-verify verdict.
5. **Recon** — real ARP/mDNS/SSDP host discovery, twin detector, tcpdump stream.
6. **Verify + pcap** — test any candidate key against the real AP; download the
   session pcap (wireshark-ready radiotap).
7. **Deauther/Karma** — channel-squat the target (router-assisted beacon war).
8. **BLE** — scan/list if an adapter exists.
9. **Event log** — the engine's full activity feed.

## Victim flow (what actually happens)

```
victim joins twin SSID (router radio, real beacons)
  → DHCP: real lease from your router
  → every DNS query answered by THIS PC (:5354) → phishing page IP
  → OS captive check (/generate_204, /hotspot-detect.html, …) → 302 → portal
  → victim types the WiFi password into the (original) phishing page
  → POST /post or WS cmd 7 → captured (RAM)
  → lab WDS-joins the REAL AP with that password
      wdsstatus 5  → ✅ key correct  → alert + credential marked CORRECT
      otherwise    → ❌ wrong        → next try
```

## What is honestly NOT possible without extra hardware

- Real 802.11 deauth/disassoc frame injection (needs monitor+inject adapter;
  the lab substitutes the router's channel-squat).
- RF-level Karma probe responses (same constraint).
- Over-the-air handshake capture (substituted by the WDS association test,
  which is strictly stronger as a verifier: it logs in or it doesn't).

Everything else is the genuine mechanism, just executed by PC+router.

## Legal

Own or written-authorization networks only — the UI gates the lab behind
"I OWN THIS NETWORK" and every destructive action confirms. Captured
credentials live in RAM only (or `--cred-file` if you explicitly pass one).
