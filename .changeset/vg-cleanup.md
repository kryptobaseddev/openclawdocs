---
"openclawdocs": patch
---

Simplify version pipeline with VG 1.1.0 fixes

- VG 1.1.0 fixes sync corruption of package.json scripts.version (#10)
- package.json re-added to VG sync files (manual sync removed)
- version.js simplified: only calcNextCalVer workaround remains (VG #9)
- Updated @codluv/versionguard to 1.1.0
