"""Configuration constants and path resolution."""

from __future__ import annotations

import os
from pathlib import Path

DOCS_BASE_URL = "https://docs.openclaw.ai"
LLMS_TXT_URL = f"{DOCS_BASE_URL}/llms.txt"
LLMS_FULL_URL = f"{DOCS_BASE_URL}/llms-full.txt"

# Default data directory is sibling to src/
_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

def get_data_dir() -> Path:
    """Resolve data directory, respecting OPENCLAW_DOCS_DATA_DIR env override."""
    env = os.environ.get("OPENCLAW_DOCS_DATA_DIR")
    return Path(env) if env else _DEFAULT_DATA_DIR

def get_raw_dir() -> Path:
    return get_data_dir() / "raw"

def get_topics_dir() -> Path:
    return get_data_dir() / "topics"

def get_db_path() -> Path:
    return get_data_dir() / "docs.db"
