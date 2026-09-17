# conf/priv-key.pem — REDACTED

The firmware image contains `conf/priv-key.pem` (an RSA private key) plus
`conf/server-cert.pem` (self-signed TP-Link SDMP certificate, expired 2017).
The same key material ships in every unit of this model.

It is **excluded from this public repo** (and would be rejected by GitHub
secret scanning). Anyone can reproduce the finding from the official vendor
firmware linked in `analysis/ARTIFACT_MANIFEST.md` using
`analysis/minifs_extract.py`. See `analysis/SECURITY_REVIEW.md`.
