# DATA_FLOW.md

Conventions: `[EXACT]` = observed in source/traffic, `[INFERRED]` = reasoned.

## Login

```text
Browser --POST ?code=2--> httpd: EUNAUTH + [un,counter,NONCE,CHARSET]
Browser: enc=orgAuthPwd(pw) [EXACT JS]
Browser --POST ?code=7&id=XOR(NONCE,enc,CHARSET)--> httpd compares vs stored enc
  match -> errno 0, enc cached in sessionStorage lgKey [EXACT]
  miss  -> errno 7 (x10 -> 2h lockout) [OBSERVED]
```

## WiFi change (representative config write)

```text
Page JS -> model.js block 33 -> POST ?code=1 (WRITE) block blob
  -> postUnAuthHandle re-auths if needed -> config manager -> flash -> wlan driver applies
```

## Password change

```text
changeSysPwd(old,new): POST ?code=10&auth=orgAuthPwd(old) + body orgAuthPwd(new) [EXACT JS]
```

## Firmware upgrade [INFERRED from SysUpgrade.htm + UPLOAD=3 + U-Boot strings]

```text
SysUpgrade.htm --POST ?code=3 (UPLOAD) .bin--> staged -> IMG0 sig check? -> flash write
  -> reboot -> U-Boot verifies ("vxWorks Image"/imgFileEnc/LZMA) -> boot
```

## Backup/restore

`SysBakNRestore.htm` via DOWNLOAD=4 / UPLOAD=3 [EXACT opcode use in JS; payload format UNKNOWN].

## UPnP action (no auth)

```text
LAN client --SOAP /ipc--> AddPortMapping -> iptables/nat -> applied, no login [OBSERVED live]
```
