# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [CalVer](https://calver.org/) (`YYYY.M.MICRO`).

## [Unreleased]

## [2025.3.0] - 2025-03-29

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
