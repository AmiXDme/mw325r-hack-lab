# SECURITY_REVIEW.md

Defensive review of the owner's device. No exploits developed; no bypasses used. Findings are identification + remediation.

## Confirmed issues (with evidence)

1. **Unauthenticated UPnP control (HIGH).** `AddPortMapping`/`DeletePortMapping` executed with zero credentials [OBSERVED live]. Any LAN malware can rewrite firewall rules. FIX: disable UPnP (UpnpCfg.htm) unless needed.
2. **Reversible login "encryption" (HIGH).** Static-XOR challenge-response with hardcoded keys/charsets [EXACT source]; nonce observed static [OBSERVED]. One sniffed login over plaintext HTTP → credential recovery (proven: 1 login → ~8.6k candidates, 2 → ~2). FIX: vendor needs real SRP/HTTPS; user mitigation: never log in over untrusted LAN, keep LAN membership tight.
3. **Plaintext admin interface (MEDIUM).** HTTP only, no TLS option [OBSERVED]. FIX: none available on device; manage only from trusted wired host.
4. **Same-device private TLS key (MEDIUM).** `conf/priv-key.pem` (RSA) + `server-cert.pem` (TP-Link SDMP, self-signed, **expired 2017**) ship identically in every unit [EXACT]. Any unit's key impersonates the PKI role. FIX: vendor should per-device keys; user: nothing actionable.
5. **WPS enabled (MEDIUM).** Registrar on; PIN attacks are a known class; UPnP WFA surface also exposed [OBSERVED]. FIX: disable WPS.
6. **EOL firmware (LOW-MED).** 201115/201116 (Nov–Dec 2020); latest published ≈ installed. No patch path for the above. FIX: plan replacement for security-sensitive use.

## Strengths (credit)

- 10-try/2-hour lockout genuinely defeats online guessing [OBSERVED]; unique admin password held [OBSERVED].
- No telnet/SSH/WAN-side admin; minimal port footprint (80+1900) [OBSERVED].
- `imgFileEnc` + signature-shaped IMG0 header suggest update-path integrity checks [INFERRED — not tested, never bypass].

## Out of scope / not attempted

Lockout bypass, firmware-signature defeat, RCE development, wireless attacks, third-party targets.
