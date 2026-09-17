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
main route -stc [-clr|-delete index:]
systool sntpc -getGmtStatus
wan -linkUp | wan -linkDown (+IPv6 variants)
wlan checkSsid ssid:<s> | wlan wdsstatus
arpMap (ip:/mac:/name: builders for staMgt add)
```

## Notes

- `$.instr(cmd)` → `{errorno, data}`; unknown verbs drop the connection [OBSERVED].
- Block WRITE (code 1) is **refused (errno 6)** for blocks 13 and 21 — those subsystems
  only accept INSTRUCT verbs. Generic `write_fields` works for plain config blocks
  (8, 11, 18, 19, 25, 32, 33, 34).
- Changing anything WAN/ISP-related can drop connectivity — use the UI confirms.
