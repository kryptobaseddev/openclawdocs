"""Output formatting with MVI and progressive disclosure for LLM agents.

All content is cleaned via cleaner.clean_content() before display:
- Mintlify MDX components converted to standard markdown
- Code fence theme metadata stripped
- Excessive whitespace normalized
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from openclaw_docs.cleaner import clean_content, extract_code_blocks
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
    """Format topic with full content (Level 2). Cleans Mintlify MDX."""
    lines = [f"# {topic['title']}"]
    lines.append(
        f"Category: {topic['category']} | "
        f"{topic['word_count']:,} words | "
        f"{topic['source_url']}"
    )
    lines.append("")
    lines.append(clean_content(content))
    return "\n".join(lines)


def fmt_code_only(topic: dict, content: str) -> str:
    """Extract and return only code blocks from topic content.

    Returns each code block with its language tag, stripped of theme metadata.
    Optimized for agents that need config examples without surrounding prose.
    """
    blocks = extract_code_blocks(content)
    if not blocks:
        return f"No code blocks found in {topic['path']}."

    lines = [f"# {topic['title']} — code blocks ({len(blocks)})"]
    for i, block in enumerate(blocks, 1):
        lines.append(f"\n```{block['language']}")
        lines.append(block["content"])
        lines.append("```")
    return "\n".join(lines)


def fmt_topic_section(topic: dict, content: str, section_query: str) -> str:
    """Extract and display a single section from topic content (PD Level 1.5).

    Fuzzy-matches section_query against ## headings, extracts content between
    the matched heading and the next heading of same or higher level.
    """
    import re
    from rapidfuzz import fuzz, process

    # Find all ## headings with their positions
    heading_pattern = re.compile(r"^(#{2,6})\s+(.+)$", re.MULTILINE)
    headings = [(m.start(), m.end(), len(m.group(1)), m.group(2)) for m in heading_pattern.finditer(content)]

    if not headings:
        return f"No sections found in {topic['path']}."

    # Fuzzy match the query against heading titles
    heading_titles = [h[3] for h in headings]
    matches = process.extract(section_query, heading_titles, scorer=fuzz.WRatio, limit=1, score_cutoff=40.0)

    if not matches:
        lines = [f"No section matching '{section_query}' in {topic['path']}."]
        lines.append("Available sections:")
        for h in headings:
            if h[2] == 2:  # only ## headings
                lines.append(f"  - {h[3]}")
        return "\n".join(lines)

    matched_title, _score, matched_idx = matches[0]
    matched_heading = headings[matched_idx]
    start_pos = matched_heading[1]  # end of heading line
    matched_level = matched_heading[2]

    # Find the end: next heading of same or higher level
    end_pos = len(content)
    for h in headings[matched_idx + 1:]:
        if h[2] <= matched_level:
            end_pos = h[0]
            break

    section_content = clean_content(content[start_pos:end_pos].strip())

    lines = [f"# {topic['title']} > {matched_title}"]
    lines.append(f"Category: {topic['category']} | Section of {topic['word_count']:,} word topic")
    lines.append("")
    lines.append(section_content)
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
