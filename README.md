# openclawdocs

LLM-agent-optimized CLI for syncing, searching, and browsing [OpenClaw](https://openclaw.ai) documentation locally.

[![npm](https://img.shields.io/npm/v/openclawdocs)](https://www.npmjs.com/package/openclawdocs)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support-ff5e5b?logo=ko-fi)](https://ko-fi.com/H2H815OTBU)

## What It Does

Downloads all OpenClaw documentation from [docs.openclaw.ai](https://docs.openclaw.ai), indexes it locally with SQLite FTS5, and exposes it through a CLI designed for LLM agent consumption. All output follows **Minimum Viable Information (MVI)** and **Progressive Disclosure (PD)** patterns to minimize token cost.

**Not for humans.** Every command is structured for machine parsing. Agents get exactly the tokens they need, nothing more.

## Install

### npm (recommended)

```bash
npm install -g openclawdocs
openclawdocs sync
```

Requires Python 3.12+. The npm postinstall creates a venv and installs Python dependencies automatically.

### pip (manual)

```bash
git clone https://github.com/kryptobaseddev/openclawdocs.git
cd openclawdocs
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
openclaw-docs sync
```

## Quick Start

```bash
# Download all documentation
openclawdocs sync

# Search for a topic
openclawdocs search "gateway authentication"

# View topic summary (MVI)
openclawdocs show gateway/authentication

# View one section only (Progressive Disclosure)
openclawdocs show gateway/authentication --section "Troubleshooting"

# View full content
openclawdocs show gateway/authentication --full
```

## Commands

| Command | Purpose | Token Cost |
|---------|---------|------------|
| `sync` | Download/update docs idempotently | N/A |
| `sync --force` | Force re-download, bypass cache | N/A |
| `search <query>` | FTS5 BM25 + fuzzy search | ~120 tokens |
| `search <query> -v` | Search with snippets | ~300 tokens |
| `show <path>` | Topic summary + section list | ~150 tokens |
| `show <path> -s <section>` | Single section content | ~500-1500 tokens |
| `show <path> --full` | Complete topic content | ~2K-15K tokens |
| `list` | All categories with counts | ~100 tokens |
| `list -c <category>` | Topics within a category | ~200 tokens |
| `status` | Sync health check | ~50 tokens |
| `diff` | Compare local vs remote | ~100 tokens |

## Progressive Disclosure Levels

An agent looking up "Discord setup" spends tokens proportional to what it needs:

```
Level 0: search "discord"                        →   120 tokens  (find the page)
Level 1: show channels/discord                   →   150 tokens  (summary + sections)
Level 2: show channels/discord -s "quick setup"  → 1,000 tokens  (just that section)
Level 3: show channels/discord --full            → 10,800 tokens  (everything)
```

Most agent tasks complete at Level 1 or 2.

## Agent Integration

### Claude Code / MCP

Add to your `CLAUDE.md` or agent instructions:

```
When working with OpenClaw features, ALWAYS verify behavior against local docs:
  openclaw-docs search "<topic>"
  openclaw-docs show <path>
  openclaw-docs show <path> --section "<section name>"
Never assume API behavior from training data.
```

### Programmatic

```python
from openclaw_docs.storage import DocsStorage
from openclaw_docs.search import SearchEngine
from openclaw_docs.config import get_db_path, get_topics_dir

storage = DocsStorage(get_db_path())
engine = SearchEngine(storage, get_topics_dir())
results = engine.search("gateway authentication", limit=5)
```

## Architecture

```
docs.openclaw.ai
       │
       ├── llms-full.txt ──→ parser.py (regex split) ──→ 362 topics
       │                                                       │
       ├── llms.txt ────────→ parser.py (index) ──────→ index_entries
       │                                                       │
       └── /page HTML ──────→ trafilatura.extract() ──→  8 topics
                                                               │
                                                   ┌───────────┘
                                                   ▼
                                            SQLite + FTS5
                                     (content-sync + triggers)
                                                   │
                                        ┌──────────┼──────────┐
                                        ▼          ▼          ▼
                                     search      show       list
                                    (BM25 +    (PD L1-3)  (categories)
                                     fuzzy)
```

- **Primary source**: `llms-full.txt` — pre-formatted markdown dump (362 pages)
- **Secondary source**: Direct page scraping via trafilatura for ~8 pages missing from the dump
- **Search**: SQLite FTS5 with BM25 ranking + rapidfuzz fuzzy title matching
- **Parsing**: markdown-it-py AST for section extraction
- **Storage**: SQLite with FTS5 external content table, auto-synced via triggers

## Coverage

370 topics across 19 categories. 100% of published English content on docs.openclaw.ai.

13 pages listed in the site navigation return HTTP 404 (unpublished experiments/plans). These are automatically skipped.

## Configuration

| Env Variable | Purpose |
|---|---|
| `OPENCLAW_DOCS_DATA_DIR` | Override data storage directory (default: `./data/`) |

## Contributing

1. Fork and clone
2. `python3 -m venv .venv && source .venv/bin/activate && pip install -e .`
3. Make changes
4. Run `openclawdocs sync && openclawdocs search "test query"` to verify
5. Submit a PR

### Versioning

This project uses [CalVer](https://calver.org/) (`YYYY.M.MICRO`) enforced by [VersionGuard](https://github.com/kryptobaseddev/versionguard).

### Code Style

- Python: ruff (`ruff check src/`)
- No emojis in code or output
- All CLI output must be machine-parseable, not prose

## Support

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/H2H815OTBU)

## License

[MIT](LICENSE)
