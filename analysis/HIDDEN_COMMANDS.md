# HIDDEN_COMMANDS.md — TDDP INSTRUCT command inventory

Status: strings [EXACT] (extracted `.htm`/`.js`); live-tested ones marked ✅.

## Verified live ✅

```text
systool ping   code:0 target:<h|ip> size:<B> metric:<count> timeout:<ms>
systool ping   code:2 icmpId:<id>          # poll -> "finished\r\ndata"
systool ping   code:1 icmpId:<id>          # stop
systool tracert code:0 target:<h|ip> metric:<hops>   (+ code:2/1 poll/stop)
forward vs -add lip:<ip> lport:<p> start:<s> end:<e> ptc:<0|1|2> valid
forward vs -edit index:<i> lip:<ip> ...    # (parsed, not live-tested)
forward vs -delete index:<i>               # ✅ tested (add+delete round-trip)
forward vs -clr
main staMgt -add mac:<MAC> name:<urlenc> upload:<B> download:<B>[ blocked]
main staMgt -delete bind mac:<MAC>         # (parsed)
main staMgt -clr bind                      # (parsed)
main staMgt -get arp                       # (parsed)
```

## Parsed from sources, not live-tested ⚠️

```text
advanced bm host|target|schedule|rule -add|-edit|-delete index:|-clr
advanced pc -enable|-disable|-get|-set time:|-delete index:|-clr
advanced ddns -configChanged ddnsId:<id>
main route -stc [-clr|-delete index:] (+ `-add index:0 net: mask: gateway: valid` — verified live)
main staMgt -get arp | -add/-delete bind ip: mac: name: | -add mac: name: upload: download: [blocked]
systool sntpc -getGmtStatus
systool syslog -clean   (ERASES the log — same as stock page button)
systool ping code:0 target: size: metric: timeout: | systool tracert code:0 target: metric:
systool ping/tracert code:1 icmpId: (stop) | code:2 icmpId: (poll result)
wan -linkUp | wan -linkDown (+IPv6 variants)
wlan checkSsid ssid:<s> | wlan wdsstatus | wlan scan | wlan scanStatus
wlan lanIpConflictStatus -> poll till "2" -> wlan lanIpConflictResult ("0"=clear)
wlan dhcpsDetectStatus -> poll till "2" -> wlan dhcpsDetectResult ("0"=no rogue DHCP)
arpMap (ip:/mac:/name: builders for staMgt add)
```

## No-go: CPU/RAM/storage meters (proven absent)

- All 60 TDDP blocks read live: no processor, memory, or storage counters
  anywhere (closest: block 23 uptime+octet counters, block 59 zeros).
- Probed `systool version/uptime`, `advanced/main/wlan status` → errno 9
  (unknown). The packed firmware image yields no extra verbs.
- Panel shows the honest substitutes: uptime, WAN GB totals, HW-NAT state,
  conflict/rogue-DHCP checks (Status tab → health card, `/api/detect`).

## Notes

- `$.instr(cmd)` → `{errorno, data}`; unknown verbs drop the connection [OBSERVED].
- Block WRITE (code 1) is **refused (errno 6)** for blocks 13 and 21 — those subsystems
  only accept INSTRUCT verbs. Generic `write_fields` works for plain config blocks
  (8, 11, 18, 19, 25, 32, 33, 34).
- Changing anything WAN/ISP-related can drop connectivity — use the UI confirms.
