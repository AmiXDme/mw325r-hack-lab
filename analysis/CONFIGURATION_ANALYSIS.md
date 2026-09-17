# CONFIGURATION_ANALYSIS.md

Status: schema [RECOVERED] (`conf/modelDesc.bin`); live values [OBSERVED]; flash layout [INFERRED].

## Schema descriptor: `conf/modelDesc.bin` [EXACT bytes]

- Magic `12 34 56 78`, version 1.
- TLV records, e.g. `[count=1][type=0x40=str?][len][offset][name]` for `fullName`, `facturer`, `modelName`, `modelVer`, `softVer`, `hardVer`, `prodId`, `languId`, `countryId`, … — the exact fields of TDDP block 0 (DEVICE) seen live.
- This file IS the Data-Model schema the `lib/model.js` client mirrors. Full TLV grammar: mostly decoded, some type codes [UNKNOWN].

## `conf/mcbDesc.bin`

Binary table, magic-ish `11 24 53 FA`, structured u16/u32 rows — probable MINIFS/chunk or memory-config descriptor. Purpose [INFERRED], grammar [UNKNOWN].

## Runtime model [OBSERVED + RECOVERED]

- 60 data blocks (IDs 0–59): DEVICE(0), SYSTEM(1, `authKey`=stored admin enc), LAN, MBSSID_MAIN(33: `cSsid`,`cPskSecret`,WPS), FACTORY(11: `authKey`), DHCP leases(9), … Full ID→name map: `SYMBOL_INDEX.md` + live `dataBlocks`.
- Read/write via TDDP READ(2)/WRITE(1); password change via CHGPWD(10) carrying old/new **encoded** values (pass-the-hash shape).
- Persistence: flash config region (no `nvram` strings; exact MTD map [UNKNOWN] — kernel region unpacked needed).

## Defaults & secrets posture

- Factory admin enc `"WaQ7xbhc9TefbwK"` embedded in `Quary.js` [EXACT].
- No plaintext `admin`/`MW325R` strings anywhere in image [EXACT — searched].
- Stored credential = `orgAuthPwd(plaintext)` (reversible transform, static keys) — anyone reading flash config recovers it [INFERRED from transform analysis].
