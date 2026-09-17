# SOURCE_RECONSTRUCTION.md

Status: JS = [EXACT] source (shipped uncompiled). C/server side = [RECONSTRUCTED] behavior only. Nothing below is claimed as vendor original C.

## 1. `securityEncode(f, d, k)` — [EXACT] (`web/lib/Quary.js`)

```js
// per-char XOR into charset; l,i reset to 187 each iteration
out[g] = k[ (f[g] ^ d[g]) % len(k) ]   // f/nonce side, d/password side
```

Reversible: given output + charset + other side, each position yields 1–2 candidates (`%255` folds 0/255; duplicate charset chars widen it). Forward model reimplemented in Python and verified **byte-identical** against the live page. One captured login narrows the stored credential to ~8,640 candidates; two independent logins narrow to ~2 (proven by simulation) — and the stored value logs in directly (pass-the-hash shape), plaintext never needed.

## 2. Login / session — [RECONSTRUCTED from Quary.js + live traffic]

```text
orgAuthPwd(pw)  = securityEncode(pw, "RDpbLfCPsJZ7fiv", KEY2[255])
session         = securityEncode(server_nonce, orgAuthPwd(pw), server_charset[255])
POST ?code=7&asyn=0&id=<session>  ->  errno 0 | 7
server stores orgAuthPwd(pw)  (SYSTEM.authKey / FACTORY.authKey)
10 failures -> 2-hour lockout (server-side) [OBSERVED]
server_nonce observed STATIC across reads+failed logins [OBSERVED] (= replay-friendly)
```

## 3. TDDP opcodes — [EXACT] (`web/lib/DM.js`)

`INSTRUCT=0 WRITE=1 READ=2 UPLOAD=3 DOWNLOAD=4 RESET=5 REBOOT=6 AUTH=7 GETPEERMAC=8 CONFIG=9 CHGPWD=10 LOGOUT=11`.

## 4. Config-block access pattern — [RECONSTRUCTED]

`readEx(id) = READ(id) + findBlock(id)` over 60 `dataBlocks`; `WRITE` posts a block blob; `CHGPWD` posts `&auth=<old-enc>` + new block. Schema per `modelDesc.bin` TLVs mirrored by `model.js`.

## 5. What cannot be reconstructed here

Server-side C (auth compare, lockout counter, UPnP handlers, config flash I/O, WPS registrar): method unknown — packed region + no MIPS disassembler in this environment. Reconstructible with Ghidra+MIPS on the unpacked image (see UNKNOWN_FINDINGS.md).
