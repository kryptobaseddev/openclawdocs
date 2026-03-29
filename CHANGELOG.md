# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [CalVer](https://calver.org/) (`YYYY.M.MICRO`).

## [Unreleased]

## [2026.3.3] - 2026-03-29

### Fixed

- Simplify version pipeline with VG 1.1.0 fixes

  - VG 1.1.0 fixes sync corruption of package.json scripts.version (#10)
  - package.json re-added to VG sync files (manual sync removed)
  - version.js simplified: only calcNextCalVer workaround remains (VG #9)
  - Updated @codluv/versionguard to 1.1.0


## [2026.3.3] - 2026-03-29

### Fixed

- Exit codes, related topics, dependency updates

  - Exit codes for agent error handling (0=success, 1=not found, 2=error)
  - Related topics extracted from cross-references in show output
  - Dependency minimums updated to latest versions

- Exit codes, related topics, dep updates, CI fixes

  - Exit codes: 0=success, 1=not found, 2=error
  - Related topics extracted from content cross-references in show output
  - Dependency minimums updated to latest versions
  - Fixed version script: use own CalVer calc instead of vg bump --apply (picks wrong option in CI)
  - Fixed release workflow: OIDC trusted publishing, no NPM_TOKEN needed
  - Added CI changeset check on PRs

## 2026.3.1

### Fixed

- Version correction: 2026.3.0 was the initial release, this is the first patch

## [2026.3.3] - 2026-03-29

### Added

- Agent-optimized output modes and content cleanup

  - Add --json flag to all commands (search, show, list, status, diff, sync)
  - Add --code-only flag to show command (extract only code blocks)
  - Add --compact flag to search and list (TSV, pipeable)
  - Strip Mintlify MDX components to clean markdown (Steps, Tabs, Accordion, Cards, Notes)
  - Strip theme={} metadata from code fences
  - Fix search ranking (BM25 normalization, fuzzy cutoff raised to 75%)
  - Add --section/-s flag for section-level progressive disclosure
  - Replace hand-rolled HTMLParser with trafilatura (F1 0.958)
  - Replace regex section splitting with markdown-it-py AST
  - Cross-platform data paths via platformdirs
  - npm package with three aliases: openclawdocs, openclaw-docs, ocdocs
  - Changesets + VersionGuard CalVer release pipeline
  - GitHub Actions release workflow

## [2026.3.3] - 2025-03-29

### Added

- Initial release of openclawdocs CLI
- `sync` command: idempotent download/update from docs.openclaw.ai with ETag caching
- `sync --force`: bypass cache, full re-download and FTS rebuild
- `search <query>`: FTS5 BM25 full-text search with rapidfuzz fuzzy title fallback
- `search -v`: verbose mode with content snippets
- `search -c <category>`: filter results by category
- `show <path>`: topic summary with section list (MVI default)
- `show --section/-s <name>`: single section retrieval (fuzzy matched)
- `show --full`: complete topic content
- `list`: category listing with topic counts
- `list -c <category>`: topics within a category
- `status`: sync health check (last sync time, topic/category counts, DB size)
- `diff`: compare local docs against remote, show added/changed/removed
- SQLite FTS5 with external content table and auto-sync triggers
- trafilatura-based HTML content extraction for pages missing from llms-full.txt
- markdown-it-py AST-based section and summary extraction
- Progressive Disclosure: search (120t) -> summary (150t) -> section (1Kt) -> full (10Kt)
- npm package wrapper with automatic Python venv setup
- 370 topics across 19 categories (100% published English content)

[Unreleased]: https://github.com/kryptobaseddev/openclawdocs/compare/2025.3.0...HEAD
[2025.3.0]: https://github.com/kryptobaseddev/openclawdocs/releases/tag/2025.3.0
