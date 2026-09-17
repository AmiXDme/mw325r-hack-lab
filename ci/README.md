# CI

`verify.yml` re-runs the MINIFS extraction in GitHub Actions and asserts 106/106 files.
It could not be pushed via API token (needs `workflow` scope), so it lives here.
To activate: upload it to `.github/workflows/` using the GitHub web UI, or push from a
checkout authenticated with a token that has `workflow` scope.
