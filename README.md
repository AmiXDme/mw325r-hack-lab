# mw325r-hack-lab

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![verify](https://github.com/AmiXDme/mw325r-hack-lab/actions/workflows/verify.yml/badge.svg)](actions/workflows/verify.yml)
![authorized research only](https://img.shields.io/badge/testing-authorized%20devices%20only-red.svg)

A complete, honest case file: attacking, analyzing, and rebuilding the admin experience of a **Mercusys MW325R v2** (FW 2.2.1) — on the owner's own device and network. Every step from first probe to final forensic report, including the mistakes.

> **Scope & ethics.** All work was done by/with the device owner on their own router. No third-party systems were touched. This repo deliberately does **not** ship the brute-force runner or wordlist — the writeup (`HISTORY.md`) describes the method and its outcome; turnkey credential-guessing tooling is left out. Do not use anything here against devices you don't own or lack explicit permission to test.

## What's inside

| Path | Contents |
|---|---|
| `HISTORY.md` | Full chronological story, first probe to last report (start here) |
| `analysis/` | 23 forensic reports + master `REVERSE_ENGINEERING_REPORT.md` (53 sections) + `minifs_extract.py` |
| `extracted-minifs/` | 105/106 firmware files recovered from the MINIFS partition |
| `firmware/` | Official vendor firmware zip (MW325R EU V2 201116 — see version note) |
| `dashboard/` | Live hack dashboard + modern replacement admin panel + localhost backend |

## Quickstart (modern panel)

```bash
cd dashboard
python3 -m http.server 8099 &          # serves index.html + control.html
python3 router_api.py &                # localhost-only TDDP backend (:8100)
# open http://localhost:8099/control.html, log in with YOUR admin password
```

Password lives in backend RAM only, never on disk. Read-only v1.

## Version note

The device runs build **201115**; Mercusys publishes only **201116** (one month newer). Analysis was done on 201116 and cross-verified against the live unit wherever possible (4 firmware files proven byte-identical to live-served copies). Anything version-sensitive is labeled in the reports.

## Redactions

Public repo hygiene: the owner's passwords, full device MAC (`38-6b-1c-XX-XX-XX`), client hostnames, and the firmware's shipped **private RSA key** (`conf/priv-key.pem` — identical in every unit, downloadable from the vendor anyway, and blocked by GitHub push protection) are excluded. See `KEY-NOTE.md`.
