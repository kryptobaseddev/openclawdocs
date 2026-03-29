"""Sync engine: fetch, parse, and update local documentation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx

from openclaw_docs.config import LLMS_FULL_URL, LLMS_TXT_URL, get_raw_dir, get_topics_dir
from openclaw_docs.models import SyncReport
from openclaw_docs.parser import parse_full_content, parse_index
from openclaw_docs.scraper import scrape_missing_pages
from openclaw_docs.storage import DocsStorage


class DocsSyncer:
    def __init__(self, storage: DocsStorage):
        self.storage = storage
        self.client = httpx.Client(timeout=60.0, follow_redirects=True)

    def _fetch(self, url: str, etag_key: str, force: bool = False) -> tuple[str | None, bool]:
        """Fetch a URL with optional ETag caching.

        Returns (content, changed). content is None if 304 Not Modified.
        """
        headers = {}
        if not force:
            etag = self.storage.get_meta(etag_key)
            if etag:
                headers["If-None-Match"] = etag

        resp = self.client.get(url, headers=headers)

        if resp.status_code == 304:
            return None, False

        resp.raise_for_status()

        # Store ETag for next time
        new_etag = resp.headers.get("ETag")
        if new_etag:
            self.storage.set_meta(etag_key, new_etag)

        return resp.text, True

    def sync(self, force: bool = False) -> SyncReport:
        """Full idempotent sync. Returns a report of what changed."""
        report = SyncReport()
        raw_dir = get_raw_dir()
        topics_dir = get_topics_dir()
        raw_dir.mkdir(parents=True, exist_ok=True)
        topics_dir.mkdir(parents=True, exist_ok=True)

        # Fetch llms.txt (index)
        try:
            index_content, index_changed = self._fetch(
                LLMS_TXT_URL, "llms_txt_etag", force
            )
        except httpx.HTTPError as e:
            report.errors.append(f"Failed to fetch llms.txt: {e}")
            return report

        if index_content is not None:
            (raw_dir / "llms.txt").write_text(index_content, encoding="utf-8")
            entries = parse_index(index_content)
            self.storage.clear_index_entries()
            for entry in entries:
                self.storage.upsert_index_entry(entry)
            self.storage.commit()

        # Fetch llms-full.txt (content)
        try:
            full_content, full_changed = self._fetch(
                LLMS_FULL_URL, "llms_full_etag", force
            )
        except httpx.HTTPError as e:
            report.errors.append(f"Failed to fetch llms-full.txt: {e}")
            return report

        if full_content is None and not force:
            # Neither file changed
            report.total = self.storage.count_topics()
            report.unchanged = report.total
            return report

        if full_content is not None:
            (raw_dir / "llms-full.txt").write_text(full_content, encoding="utf-8")
        else:
            # Force mode but server returned 304 — use cached raw file
            raw_path = raw_dir / "llms-full.txt"
            if raw_path.exists():
                full_content = raw_path.read_text(encoding="utf-8")
            else:
                report.errors.append("No cached llms-full.txt and server returned 304")
                return report

        # Parse topics
        topics = parse_full_content(full_content)

        # Upsert topics and write markdown files
        current_paths: set[str] = set()
        for topic in topics:
            current_paths.add(topic.path)
            is_new = self.storage.get_topic_hash(topic.path) is None
            changed = self.storage.upsert_topic(topic)
            if changed:
                if is_new:
                    report.added += 1
                else:
                    report.updated += 1

                # Write topic markdown file
                topic_file = topics_dir / topic.category / f"{topic.slug}.md"
                topic_file.parent.mkdir(parents=True, exist_ok=True)
                topic_file.write_text(topic.content, encoding="utf-8")

        # Scrape pages missing from llms-full.txt but present in docs.json nav.
        # Uses the docs.json Mintlify navigation as the authoritative page list.
        def _scrape_progress(current: int, total: int, path: str) -> None:
            pass  # Silent by default; CLI can override via callback

        scraped = scrape_missing_pages(self.client, current_paths, _scrape_progress)
        for topic in scraped:
            current_paths.add(topic.path)
            is_new = self.storage.get_topic_hash(topic.path) is None
            changed = self.storage.upsert_topic(topic)
            if changed:
                if is_new:
                    report.added += 1
                else:
                    report.updated += 1
                topic_file = topics_dir / topic.category / f"{topic.slug}.md"
                topic_file.parent.mkdir(parents=True, exist_ok=True)
                topic_file.write_text(topic.content, encoding="utf-8")

        # Remove topics no longer in the source
        removed = self.storage.remove_topics_not_in(current_paths)
        report.removed = len(removed)
        for path in removed:
            parts = path.split("/")
            if len(parts) >= 2:
                fp = topics_dir / parts[0] / f"{parts[-1]}.md"
            else:
                fp = topics_dir / "general" / f"{parts[0]}.md"
            if fp.exists():
                fp.unlink()

        self.storage.commit()

        # FTS index is kept in sync automatically via triggers on the topics
        # table (content-sync FTS5). A full rebuild is only needed for repair.
        # We run it here on force-sync to guarantee consistency.
        if force:
            self.storage.rebuild_fts()

        report.total = self.storage.count_topics()
        report.unchanged = report.total - report.added - report.updated

        # Update sync timestamp
        self.storage.set_meta(
            "last_sync_time",
            datetime.now(timezone.utc).isoformat(),
        )

        return report

    def check_remote(self) -> tuple[str | None, str | None]:
        """Fetch remote content for diff comparison without updating local state.

        Returns (llms_txt_content, llms_full_content).
        """
        llms_txt = None
        llms_full = None
        try:
            resp = self.client.get(LLMS_TXT_URL)
            resp.raise_for_status()
            llms_txt = resp.text
        except httpx.HTTPError:
            pass
        try:
            resp = self.client.get(LLMS_FULL_URL)
            resp.raise_for_status()
            llms_full = resp.text
        except httpx.HTTPError:
            pass
        return llms_txt, llms_full
