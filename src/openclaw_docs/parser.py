"""Parse llms.txt and llms-full.txt into structured data."""

from __future__ import annotations

import hashlib
import re

from openclaw_docs.models import IndexEntry, Topic

# Pattern for llms.txt entries: - [Title](URL)
_INDEX_PATTERN = re.compile(r"-\s+\[([^\]]+)\]\(([^)]+)\)")

# Pattern for llms-full.txt section boundaries: # Title\nSource: URL
_SECTION_PATTERN = re.compile(
    r"^# (.+)\nSource: (https://docs\.openclaw\.ai/.+)$",
    re.MULTILINE,
)

_DOCS_BASE = "https://docs.openclaw.ai/"


def _path_from_url(url: str) -> str:
    """Extract relative path from a docs URL, stripping base and .md suffix."""
    path = url.replace(_DOCS_BASE, "")
    if path.endswith(".md"):
        path = path[:-3]
    return path


def _category_and_slug(path: str) -> tuple[str, str]:
    """Split path into (category, slug)."""
    parts = path.split("/")
    if len(parts) >= 2:
        return parts[0], parts[-1]
    return "general", parts[0]


def parse_index(content: str) -> list[IndexEntry]:
    """Parse llms.txt into IndexEntry objects."""
    entries = []
    for match in _INDEX_PATTERN.finditer(content):
        title = match.group(1).strip()
        url = match.group(2).strip()
        path = _path_from_url(url)
        category, slug = _category_and_slug(path)
        entries.append(IndexEntry(
            title=title,
            url=url,
            path=path,
            category=category,
            slug=slug,
        ))
    return entries


def parse_full_content(content: str) -> list[Topic]:
    """Parse llms-full.txt into individual Topic objects."""
    matches = list(_SECTION_PATTERN.finditer(content))
    if not matches:
        return []

    topics = []
    for i, match in enumerate(matches):
        title = match.group(1).strip()
        source_url = match.group(2).strip()

        # Content starts after the Source line
        content_start = match.end()

        # Content ends at the next section boundary (or EOF)
        if i + 1 < len(matches):
            content_end = matches[i + 1].start()
        else:
            content_end = len(content)

        section_content = content[content_start:content_end].strip()

        path = _path_from_url(source_url)
        category, slug = _category_and_slug(path)

        # Extract ## headings for section list
        sections = re.findall(r"^## (.+)$", section_content, re.MULTILINE)

        # Compute content hash
        content_hash = hashlib.sha256(section_content.encode("utf-8")).hexdigest()

        word_count = len(section_content.split())

        summary = generate_summary(section_content)

        topics.append(Topic(
            title=title,
            source_url=source_url,
            path=path,
            category=category,
            slug=slug,
            content=section_content,
            content_hash=content_hash,
            sections=sections,
            word_count=word_count,
            summary=summary,
        ))

    return topics


def generate_summary(content: str) -> str:
    """Extract first meaningful paragraph as summary (<=200 chars)."""
    lines = content.split("\n")
    paragraph: list[str] = []
    in_paragraph = False

    for line in lines:
        stripped = line.strip()
        # Skip headings
        if stripped.startswith("#"):
            if in_paragraph:
                break
            continue
        # Skip code blocks
        if stripped.startswith("```"):
            if in_paragraph:
                break
            continue
        # Blank line ends a paragraph
        if not stripped:
            if in_paragraph:
                break
            continue
        # Skip Mintlify components
        if stripped.startswith("<") and not stripped.startswith("<a"):
            if in_paragraph:
                break
            continue
        in_paragraph = True
        paragraph.append(stripped)

    summary = " ".join(paragraph)
    if len(summary) > 200:
        summary = summary[:197] + "..."
    return summary
