"""Data models for openclaw-docs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class IndexEntry:
    """A single entry from llms.txt."""
    title: str
    url: str
    path: str       # relative path without .md, e.g. "channels/discord"
    category: str   # first path segment, e.g. "channels"
    slug: str       # last path segment, e.g. "discord"


@dataclass
class Topic:
    """A parsed documentation topic from llms-full.txt."""
    title: str
    source_url: str
    path: str
    category: str
    slug: str
    content: str
    content_hash: str
    sections: list[str] = field(default_factory=list)
    word_count: int = 0
    summary: str = ""


@dataclass
class SearchResult:
    """A single search result."""
    title: str
    path: str
    category: str
    score: float
    snippet: str = ""
    match_type: str = "content"


@dataclass
class SyncReport:
    """Result of a sync operation."""
    added: int = 0
    updated: int = 0
    removed: int = 0
    unchanged: int = 0
    total: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class SyncStatus:
    """Status of the local documentation sync."""
    last_sync: datetime | None = None
    total_topics: int = 0
    total_categories: int = 0
    index_entries: int = 0
    db_size_bytes: int = 0
    data_dir: str = ""
