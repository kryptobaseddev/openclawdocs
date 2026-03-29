---
"openclawdocs": patch
---

Exit codes, related topics, dep updates, CI fixes

- Exit codes: 0=success, 1=not found, 2=error
- Related topics extracted from content cross-references in show output
- Dependency minimums updated to latest versions
- Fixed version script: use own CalVer calc instead of vg bump --apply (picks wrong option in CI)
- Fixed release workflow: OIDC trusted publishing, no NPM_TOKEN needed
- Added CI changeset check on PRs
