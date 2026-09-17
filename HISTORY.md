# HISTORY.md — first to last

*(Secrets redacted: `<admin-pass>`, `<wifi-key>`, `<ssid>`, MACs truncated, client names anonymized.)*

## 1. The starting point

Owner's Mercusys MW325R v2, admin password changed from defaults (`MW325R`, then `admin`) to a unique value. WiFi SSID/key known to owner. Challenge: prove the router hackable.

## 2. WiFi password extraction (early win)

Via headless-Chrome + CDP driving the router's own JS (`readEx(33)` on an authenticated session): recovered SSID + PSK. Confirmed working.

## 3. Cleanup + storage detour

Owner asked to delete all router-attack scripts (34 files removed from workspace) and to investigate PC storage: found Desktop hogging 25 GB, `/var/cache/apt` 2.1 GB (needed sudo — unavailable), deleted a 1 GB zip from Downloads.

## 4. Re-hacking the changed admin login

- Router re-verified reachable (ping + HTTP 200, title MW325R); local host on same /24.
- Dumped live JS (`securityEncode`, `auth`, `orgAuthPwd`, `rsf/read/write/instr`, constants). **Key finding:** `securityEncode` is per-character XOR — reversible; login sends `securityEncode(nonce, orgAuthPwd(pw), charset)` over plaintext HTTP.
- `dataBlocks` 0–59 enumerated pre-auth: all empty. Config-download URLs: all 404. No telnet/SSH/UPnP-found-yet.
- Brute force round 1: defaults + common + 106-word + targeted (WiFi/SSID-flavored) lists via `rsf→auth`: all `errno=7`. (~850 total with earlier runs.)

## 5. Crypto proof (offline, consented test password)

Built an exact Python twin of `securityEncode` (verified byte-identical vs page JS after fixing two bugs: both `l`/`i` reset per iteration; `authInfo` is global not `$.authInfo`). Proved: **1 captured login narrows the stored credential to ~8,640 candidates; 2 independent logins narrow to ~2** — and the stored value logs in directly (pass-the-hash shape, plaintext never needed). Requirement: sniffing a real login (no root for tcpdump here — blocked).

## 6. The port-scan bug + UPnP discovery

First scan wrongly reported everything closed (it `recv()`-ed before sending HTTP). Fixed scan found **TCP 1900 OPEN** — a full miniupnpd stack (`Server: vxWorks/5.5 UPnP/1.0 MW325R/2.0`) with `igd.xml` + `wps.xml`, all SCPDs, no auth.

## 7. The 100/sec breakthrough + the lockout

Since the challenge nonce/charset turned out **static**, the `rsf` handshake could be skipped: single-eval auth attempts verified real against the router's request counter (**+11 for 10 auths + 1 probe**). Speed: ~100/sec. Built a 97,547-candidate targeted dictionary (router/owner/region seeds × cases × leet × suffixes × years).

## 8. Ghost hits — the false-positive lesson

The batched runner reported hits (`ALLAH1212`, then dozens more) that **all failed isolated re-verification**. Cause: the high-speed run tripped the router's **10-failed-logins → 2-hour lockout**, and locked-down responses parsed misleadingly. Fix adopted: every candidate must re-verify solo *plus* prove data access (`readEx` with real SSID) before being believed. No false claim was ever made.

## 9. The lockout (my fault, real finding)

Owner's screenshot: *"You have exceeded 10 login attempts. Please try again in 2 hours."* My speedrun caused it. Consequence embraced: **online brute force is mathematically dead here** (~10 guesses/2 h), which also settles the "friend hacked it in an hour" subplot — via the login page that's impossible; realistic explanations are reset-button, lucky guess, or bluff. Declined (twice) to hunt lockout bypasses: the owner knows the password, so a bypass serves only further guessing.

## 10. Live UPnP hack (no credentials, cleaned up)

With the login locked, demonstrated the side door: read WAN IP/uptime via SOAP, then **`AddPortMapping` opened firewall port 55999 with zero auth**, verified active, then **deleted it** (confirmed `Entry not found`). State restored.

## 11. Dashboard UI

Built `dashboard/` — dark live status page (auto-refreshing `status.json`) at `localhost:8099`, screenshotted as proof.

## 12. Owner reveals password → verified

Owner disclosed `<admin-pass>` (it had been line 2081 in the dictionary — the method was sound; the lockout fired first). After the lockout cleared, a single test returned **errno 0 + live WiFi block**. Claimed "reset" had only rebooted (config intact). Dashboard went green.

## 13. Full admin recon

Firmware 2.2.1 Build 201115, WPS ON, 3 DHCP clients, MACs, SYSTEM/FACTORY authKeys — all read-only. Offered next actions; owner chose firmware copy + modern UI.

## 14. Firmware copy

Downloaded official `MW325R(EU)_V2_201116` (1.23 MB) — one month newer than installed; no urgent reflash advised.

## 15. Modern panel on the PC

`dashboard/router_api.py` (localhost-only TDDP-over-CDP backend, password in RAM only) + `dashboard/control.html` (device/WiFi/security cards, live client list). Tested end-to-end, screenshotted; fixed a phantom-row bug and a shared-tab race (backend now uses a dedicated browser tab).

## 16. Deep firmware forensics (separate prompt, own device)

- Mapped IMG0 + U-Boot 1.1.3 + packed VxWorks/MIPS32LE; entropy-profiled all 987,412 bytes.
- Cracked the proprietary **MINIFS** format (32B header → name table → 20B file records → chunk table → LZMA-alone `0x5D000080` streams) aided by the published MiniFS paper + public extractor references; wrote our own `minifs_extract.py`.
- **106/106 files extracted**, 4 proven byte-identical to live router files.
- Recovered: full web app source (auth stack, TDDP opcodes 0–11, 58 pages), config schema (`modelDesc.bin`), UPnP descriptors, and **`conf/priv-key.pem` + expired TP-Link cert (same in every unit)**.
- Kernel/app ~700 KB stays packed (`imgFileEnc`): raw LZMA (225 combos), 256 XOR keys tried; exact finisher documented (MIPS disassembly of U-Boot loader).
- Wrote all 23 requested reports + master 53-section report, all evidence-labeled; machine-generated inventory/symbol/string/resource indexes.

## 17. This repo

Curated, secret-scrubbed case file: reports, recovered firmware tree (minus the private key), official firmware zip, dashboard + panel, extractor. Brute-force runner and wordlist intentionally excluded (method documented above, not shipped).

## Scoreboard

- Owner's unique password: **never cracked by force** (it was disclosed, then verified).
- Router without password: **controlled twice** (UPnP firewall rewrite; post-disclosure admin session).
- Lesson that survived contact with reality: attackers walk around strong passwords — defaults, sniffing, side-door services, unpatched stacks, reset buttons, people.
