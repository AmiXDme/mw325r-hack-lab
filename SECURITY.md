# Security Policy

This is **authorized own-device security research**. Everything here was produced
against the owner's own router on their own network.

## Please do NOT

- Use anything in this repo against devices you don't own or lack explicit,
  written permission to test.
- Open issues/PRs containing real credentials, MACs, or private keys.
  They will be removed.

## Reporting a vulnerability

- **In this repo's code** (dashboard, backend, extractor): open a GitHub issue
  with steps to reproduce. No private data, please.
- **In Mercusys hardware/firmware** (e.g., the no-auth UPnP surface or the
  shipped device key documented in `analysis/SECURITY_REVIEW.md`): report it
  to the vendor (Mercusys support) first and give them time to respond before
  publishing details. If you confirm something new, document evidence the way
  this repo does: exact bytes, versions, and `[EXACT]`/`[OBSERVED]` labels.
