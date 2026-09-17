# Contributing

Small, honest contributions welcome: corrections, reproductions on other
firmware builds, better docs.

## Ground rules

1. **Evidence labels.** Technical claims use `[EXACT]` / `[RECOVERED]` /
   `[RECONSTRUCTED]` / `[OBSERVED]` / `[INFERRED]` / `[UNKNOWN]`. Don't present
   a guess as a fact.
2. **No secrets.** Never commit passwords, MACs, private keys, pcaps, or
   screenshots containing them. CI rejects private-key blocks automatically.
3. **No attack tooling.** Research describes methods; this repo does not ship
   credential brute-forcers or weaponized exploits.
4. **Don't touch the packed region claims lightly.** The kernel/app codec is
   `[UNKNOWN]` — a PR claiming otherwise needs a reproducible decode.

## Workflow

- Fork → branch → PR with a clear description of what you verified and how.
- `HISTORY.md` is append-only narrative: add dated entries, don't rewrite it.
