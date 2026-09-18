# DIRECT_TDDP.md — the router's private protocol, fully decoded

Source: `extracted-minifs/web/lib/{DM,Quary,ajax}.js` + `dynaform/class.js`,
proven live against the owner's unit (60/60 blocks byte-identical vs the
browser stack; only live counters and client-side icon defaults differ).

## Transport

Plain HTTP POST to the router (default `http://192.168.1.1/`):

```
POST /?code=N&asyn=0[&id=<session>]      body = command text (may be empty)
```

- `code` = operation (lib/DM.js): 0 INSTRUCT, 1 WRITE, 2 READ, 4 DOWNLOAD,
  5 RESET, 6 REBOOT, 7 AUTH, 8 GETPEERMAC, 9 CONFIG(restore), 10 CHGPWD,
  11 LOGOUT.
- Auth state is a URL parameter `id=<session>` (lib/ajax.js `orgURL`),
  **not a cookie**.
- Reply is `<errno>\r\n<data>` (`ENONE=0`, `EUNAUTH=7`). The first AUTH
  call answers HTTP 401 with the challenge in the BODY — the stock page
  reads it anyway.

## Login (lib/Quary.js)

```
1. POST ?code=7&asyn=0                     -> 401 + 4 challenge lines L[0..3]
2. enc   = securityEncode(password, "RDpbLfCPsJZ7fiv", "yLwVl0zK...<long>")
3. sess  = securityEncode(L[2], enc, L[3])
4. POST ?code=7&asyn=0&id=<sess>            -> errno 0 = logged in
```

`securityEncode(f, d, k)`: per character `k.charAt((ord(f[i]) ^ ord(d[i])) % len(k))`,
missing chars count as 187. (Yes — reversible XOR against static strings;
one sniffed login recovers the password. See SECURITY_REVIEW.md.)

## Block text format (lib/DM.js `toText` / `parser`)

```
id 33
cSsid <url-encoded>
dns 0 8.8.8.8          <- list field: "name index value"
dns 1 8.8.4.4
```

- Scalars: `key value`. List items: `key index value`. Nested objects
  (block 32 `apc`/`adv`, block 33/35 `wps`) are flattened to scalars.
- Values are `encodeURIComponent`-escaped.
- The stock parser needs the client-side model to regroup repeated keys;
  `dashboard/tddp.py` ships the empirically captured schema (`LIST_FIELDS`,
  `ROW_ORDER`, `NESTED`).

## Operations

| Op | Request | Notes |
|---|---|---|
| READ | POST `?code=2`, body=`<blockid>` | all 60 blocks documented in BLOCKMAP.md |
| WRITE | POST `?code=1`, body=`toText(block)` | read-modify-write; errno 0 = applied |
| INSTRUCT | POST `?code=0`, body=`<verb>` | e.g. `wlan scan`, `main staMgt -get arp`, `wan -linkUp` |
| GETPEERMAC | POST `?code=8` | MAC of the admin PC (MAC-clone feature) |
| CHGPWD | POST `?code=10&auth=<encOld>`, body=`<encNew>` | both `orgAuthPwd`-encoded |
| DOWNLOAD | GET `<name>.bin?code=0` (+session) | official config backup |
| CONFIG | multipart POST `?code=9`, field `fileName` | config restore (reboots) |
| REBOOT/RESET | POST `?code=6` / `?code=5` | reset wipes everything |

## Reference implementation

`dashboard/tddp.py` — pure-stdlib client (login/session/read/write/instr/
peerMac/reboot/reset/chgpwd/backup). `dashboard/travel_api.py` — drop-in
portable panel backend on top of it (Termux/Raspberry Pi friendly).
