"""Output formatting with MVI and progressive disclosure for LLM agents."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from openclaw_docs.models import SearchResult, SyncReport, SyncStatus


def fmt_sync_report(report: SyncReport) -> str:
    """Format sync results."""
    lines = ["Sync complete."]
    lines.append(f"  Added:     {report.added}")
    lines.append(f"  Updated:   {report.updated}")
    lines.append(f"  Removed:   {report.removed}")
    lines.append(f"  Unchanged: {report.unchanged}")
    lines.append(f"  Total:     {report.total}")
    if report.errors:
        lines.append("")
        lines.append("Errors:")
        for err in report.errors:
            lines.append(f"  ! {err}")
    return "\n".join(lines)


def fmt_search_results(results: list[SearchResult], verbose: bool = False) -> str:
    """Format search results with MVI default."""
    if not results:
        return "No results found."

    lines = []
    for i, r in enumerate(results, 1):
        line = f"[{i}] {r.path:<35} {r.title:<40} {r.score:.2f}"
        lines.append(line)
        if verbose and r.snippet:
            # Indent snippet under the result
            lines.append(f"    {r.snippet}")

    lines.append("")
    lines.append(f"{len(results)} results | -v for snippets | show <path> for full")
    return "\n".join(lines)


def fmt_topic_summary(topic: dict, content: str | None = None) -> str:
    """Format topic with progressive disclosure Level 1 (default)."""
    sections = json.loads(topic["sections"]) if isinstance(topic["sections"], str) else topic["sections"]

    lines = [f"# {topic['title']}"]
    lines.append(
        f"Category: {topic['category']} | "
        f"{topic['word_count']:,} words | "
        f"{topic['source_url']}"
    )
    lines.append("")

    if topic.get("summary"):
        lines.append(topic["summary"])
        lines.append("")

    if sections:
        lines.append(f"## Sections ({len(sections)})")
        for s in sections:
            lines.append(f"- {s}")
        lines.append("")

    lines.append(f"> openclaw-docs show {topic['path']} --full")
    return "\n".join(lines)


def fmt_topic_full(topic: dict, content: str) -> str:
    """Format topic with full content (Level 2)."""
    lines = [f"# {topic['title']}"]
    lines.append(
        f"Category: {topic['category']} | "
        f"{topic['word_count']:,} words | "
        f"{topic['source_url']}"
    )
    lines.append("")
    lines.append(content)
    return "\n".join(lines)


def fmt_categories(categories: list[tuple[str, int]]) -> str:
    """Format category listing."""
    if not categories:
        return "No topics synced. Run `openclaw-docs sync` first."

    lines = []
    total_topics = 0
    # Display in columns of 3
    row: list[str] = []
    for cat, count in categories:
        total_topics += count
        entry = f"{cat:<15} {count:>3}"
        row.append(entry)
        if len(row) == 3:
            lines.append("    ".join(row))
            row = []
    if row:
        lines.append("    ".join(row))

    lines.append("")
    lines.append(f"Total: {total_topics} topics across {len(categories)} categories")
    return "\n".join(lines)


def fmt_topic_list(topics: list[dict]) -> str:
    """Format topic listing within a category."""
    if not topics:
        return "No topics found."

    lines = []
    for t in topics:
        lines.append(f"{t['path']:<40} {t['title']}")
    lines.append("")
    lines.append(f"{len(topics)} topics")
    return "\n".join(lines)


def fmt_status(status: SyncStatus) -> str:
    """Format sync status."""
    if status.last_sync:
        now = datetime.now(timezone.utc)
        delta = now - status.last_sync.replace(tzinfo=timezone.utc) if status.last_sync.tzinfo is None else now - status.last_sync
        ago = _fmt_timedelta(delta)
        sync_line = f"{status.last_sync.isoformat()} ({ago} ago)"
    else:
        sync_line = "Never synced"

    db_size = f"{status.db_size_bytes / 1024:.1f} KB" if status.db_size_bytes else "0 KB"

    lines = [
        f"Last sync:    {sync_line}",
        f"Topics:       {status.total_topics}",
        f"Categories:   {status.total_categories}",
        f"Index entries: {status.index_entries}",
        f"DB size:      {db_size}",
        f"Data dir:     {status.data_dir}",
    ]
    return "\n".join(lines)


def fmt_diff(added: list[str], changed: list[str], removed: list[str]) -> str:
    """Format diff report."""
    if not added and not changed and not removed:
        return "No changes detected. Local docs are up to date."

    lines = []
    if added:
        lines.append(f"  Added:   {len(added)} topics")
        for p in added:
            lines.append(f"    + {p}")
    if changed:
        lines.append(f"  Changed: {len(changed)} topics")
        for p in changed:
            lines.append(f"    ~ {p}")
    if removed:
        lines.append(f"  Removed: {len(removed)} topics")
        for p in removed:
            lines.append(f"    - {p}")

    lines.append("")
    lines.append("Run `openclaw-docs sync` to apply changes.")
    return "\n".join(lines)


def _fmt_timedelta(delta) -> str:
    """Format a timedelta to a human-readable string."""
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds}s"
    if total_seconds < 3600:
        return f"{total_seconds // 60}m"
    if total_seconds < 86400:
        return f"{total_seconds // 3600}h"
    return f"{total_seconds // 86400}d"
