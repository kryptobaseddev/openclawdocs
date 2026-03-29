"""SQLite storage with FTS5 full-text search."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from openclaw_docs.models import IndexEntry, SearchResult, SyncStatus, Topic

_SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    slug TEXT NOT NULL,
    source_url TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    word_count INTEGER NOT NULL DEFAULT 0,
    sections TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL DEFAULT '',
    file_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS index_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    path TEXT NOT NULL,
    category TEXT NOT NULL,
    slug TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# FTS5 external content table: reads from topics table, synced via triggers.
# Columns must match topics table columns used for search.
_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS topics_fts USING fts5(
    title,
    category,
    sections,
    content,
    content='topics',
    content_rowid='id',
    tokenize='porter unicode61'
);
"""

# Triggers keep FTS index in sync with topics table automatically.
# Pattern from official SQLite FTS5 docs: https://www.sqlite.org/fts5.html#external_content_tables
_FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS topics_ai AFTER INSERT ON topics BEGIN
    INSERT INTO topics_fts(rowid, title, category, sections, content)
    VALUES (new.id, new.title, new.category, new.sections, new.content);
END;

CREATE TRIGGER IF NOT EXISTS topics_ad AFTER DELETE ON topics BEGIN
    INSERT INTO topics_fts(topics_fts, rowid, title, category, sections, content)
    VALUES ('delete', old.id, old.title, old.category, old.sections, old.content);
END;

CREATE TRIGGER IF NOT EXISTS topics_au AFTER UPDATE ON topics BEGIN
    INSERT INTO topics_fts(topics_fts, rowid, title, category, sections, content)
    VALUES ('delete', old.id, old.title, old.category, old.sections, old.content);
    INSERT INTO topics_fts(rowid, title, category, sections, content)
    VALUES (new.id, new.title, new.category, new.sections, new.content);
END;
"""


class DocsStorage:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(_SCHEMA)
        self.conn.executescript(_FTS_SCHEMA)
        self.conn.executescript(_FTS_TRIGGERS)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # --- Sync meta ---

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM sync_meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO sync_meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    # --- Index entries ---

    def upsert_index_entry(self, entry: IndexEntry) -> None:
        self.conn.execute(
            "INSERT INTO index_entries (title, url, path, category, slug) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(url) DO UPDATE SET title=excluded.title, path=excluded.path, "
            "category=excluded.category, slug=excluded.slug",
            (entry.title, entry.url, entry.path, entry.category, entry.slug),
        )

    def clear_index_entries(self) -> None:
        self.conn.execute("DELETE FROM index_entries")

    def count_index_entries(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM index_entries").fetchone()[0]

    # --- Topics ---

    def get_topic_hash(self, path: str) -> str | None:
        row = self.conn.execute(
            "SELECT content_hash FROM topics WHERE path = ?", (path,)
        ).fetchone()
        return row["content_hash"] if row else None

    def upsert_topic(self, topic: Topic) -> bool:
        """Insert or update a topic. Returns True if content changed."""
        now = datetime.now(timezone.utc).isoformat()
        existing_hash = self.get_topic_hash(topic.path)

        if existing_hash == topic.content_hash:
            return False

        sections_json = json.dumps(topic.sections)
        file_path = f"{topic.category}/{topic.slug}.md"

        if existing_hash is None:
            self.conn.execute(
                "INSERT INTO topics (title, path, category, slug, source_url, "
                "content_hash, content, word_count, sections, summary, file_path, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (topic.title, topic.path, topic.category, topic.slug, topic.source_url,
                 topic.content_hash, topic.content, topic.word_count, sections_json,
                 topic.summary, file_path, now, now),
            )
        else:
            self.conn.execute(
                "UPDATE topics SET title=?, category=?, slug=?, source_url=?, "
                "content_hash=?, content=?, word_count=?, sections=?, summary=?, "
                "file_path=?, updated_at=? WHERE path=?",
                (topic.title, topic.category, topic.slug, topic.source_url,
                 topic.content_hash, topic.content, topic.word_count, sections_json,
                 topic.summary, file_path, now, topic.path),
            )
        return True

    def remove_topics_not_in(self, paths: set[str]) -> list[str]:
        """Remove topics whose paths are not in the given set. Returns removed paths."""
        rows = self.conn.execute("SELECT path FROM topics").fetchall()
        removed = [r["path"] for r in rows if r["path"] not in paths]
        if removed:
            placeholders = ",".join("?" for _ in removed)
            self.conn.execute(f"DELETE FROM topics WHERE path IN ({placeholders})", removed)
        return removed

    def commit(self) -> None:
        self.conn.commit()

    def get_topic(self, path: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM topics WHERE path = ?", (path,)).fetchone()
        return dict(row) if row else None

    def get_topic_content(self, path: str, topics_dir: Path) -> str | None:
        """Read full content. Primary: DB content column. Fallback: topic file."""
        topic = self.get_topic(path)
        if not topic:
            return None
        # Prefer DB content (always in sync via triggers)
        if topic.get("content"):
            return topic["content"]
        # Fallback to file if DB content is empty (shouldn't happen normally)
        fp = topics_dir / topic["file_path"]
        if fp.exists():
            return fp.read_text(encoding="utf-8")
        return None

    def list_categories(self) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT category, COUNT(*) as cnt FROM topics GROUP BY category ORDER BY category"
        ).fetchall()
        return [(r["category"], r["cnt"]) for r in rows]

    def list_topics(self, category: str | None = None) -> list[dict]:
        if category:
            rows = self.conn.execute(
                "SELECT path, title, category, word_count FROM topics "
                "WHERE category = ? ORDER BY slug",
                (category,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT path, title, category, word_count FROM topics ORDER BY category, slug"
            ).fetchall()
        return [dict(r) for r in rows]

    def count_topics(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]

    def count_categories(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(DISTINCT category) FROM topics"
        ).fetchone()[0]

    # --- FTS5 Search ---

    def rebuild_fts(self) -> None:
        """Rebuild the FTS index from the topics content column.

        With content-sync FTS5 (content='topics'), triggers keep the index
        in sync automatically. This method is a repair tool that fully
        rebuilds from the source table if the index gets corrupted.
        """
        self.conn.execute("INSERT INTO topics_fts(topics_fts) VALUES ('rebuild')")
        self.conn.commit()

    def fts_search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Full-text search using FTS5 BM25 ranking."""
        # Escape special FTS5 characters and add implicit AND
        terms = query.strip().split()
        if not terms:
            return []
        fts_query = " AND ".join(f'"{t}"' for t in terms)

        try:
            rows = self.conn.execute(
                "SELECT t.title, t.path, t.category, "
                "bm25(topics_fts, 10.0, 5.0, 3.0, 1.0) as rank "
                "FROM topics_fts f "
                "JOIN topics t ON t.id = f.rowid "
                "WHERE topics_fts MATCH ? "
                "ORDER BY rank "
                "LIMIT ?",
                (fts_query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

        results = []
        for row in rows:
            score = min(1.0, max(0.0, -row["rank"] / 20.0))
            results.append(SearchResult(
                title=row["title"],
                path=row["path"],
                category=row["category"],
                score=round(score, 2),
                match_type="content",
            ))
        return results

    def get_all_titles(self) -> list[tuple[str, str]]:
        """Return (title, path) pairs for fuzzy matching."""
        rows = self.conn.execute("SELECT title, path FROM topics ORDER BY title").fetchall()
        return [(r["title"], r["path"]) for r in rows]

    # --- Status ---

    def get_status(self, data_dir: Path) -> SyncStatus:
        last_sync_str = self.get_meta("last_sync_time")
        last_sync = datetime.fromisoformat(last_sync_str) if last_sync_str else None

        db_size = self.db_path.stat().st_size if self.db_path.exists() else 0

        return SyncStatus(
            last_sync=last_sync,
            total_topics=self.count_topics(),
            total_categories=self.count_categories(),
            index_entries=self.count_index_entries(),
            db_size_bytes=db_size,
            data_dir=str(data_dir),
        )
