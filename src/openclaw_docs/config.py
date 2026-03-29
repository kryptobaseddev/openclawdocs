"""Configuration constants and cross-platform path resolution.

Data directory resolution order:
1. OPENCLAW_DOCS_DATA_DIR env var (explicit override)
2. platformdirs.user_data_dir("openclawdocs") (OS standard location)
   - Linux:   ~/.local/share/openclawdocs
   - macOS:   ~/Library/Application Support/openclawdocs
   - Windows: C:\\Users\\<user>\\AppData\\Local\\openclawdocs
"""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir

DOCS_BASE_URL = "https://docs.openclaw.ai"
LLMS_TXT_URL = f"{DOCS_BASE_URL}/llms.txt"
LLMS_FULL_URL = f"{DOCS_BASE_URL}/llms-full.txt"

APP_NAME = "openclawdocs"


def get_data_dir() -> Path:
    """Resolve data directory using OS-standard paths.

    Checks OPENCLAW_DOCS_DATA_DIR env first, falls back to platformdirs.
    """
    env = os.environ.get("OPENCLAW_DOCS_DATA_DIR")
    if env:
        return Path(env)
    return Path(user_data_dir(APP_NAME))


def get_raw_dir() -> Path:
    return get_data_dir() / "raw"


def get_topics_dir() -> Path:
    return get_data_dir() / "topics"


def get_db_path() -> Path:
    return get_data_dir() / "docs.db"
