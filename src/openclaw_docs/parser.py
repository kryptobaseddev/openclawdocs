"""Parse llms.txt and llms-full.txt into structured data.

Uses markdown-it-py for AST-based section extraction instead of fragile regex.
"""

from __future__ import annotations

import hashlib
import re

from markdown_it import MarkdownIt

from openclaw_docs.models import IndexEntry, Topic

# Pattern for llms.txt entries: - [Title](URL)
_INDEX_PATTERN = re.compile(r"-\s+\[([^\]]+)\]\(([^)]+)\)")

# Pattern for llms-full.txt section boundaries: # Title\nSource: URL
_SECTION_PATTERN = re.compile(
    r"^# (.+)\nSource: (https://docs\.openclaw\.ai/.+)$",
    re.MULTILINE,
)

_DOCS_BASE = "https://docs.openclaw.ai/"

# Shared markdown-it parser instance (stateless, safe to reuse)
_md = MarkdownIt()


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


def extract_sections(content: str) -> list[str]:
    """Extract ## heading titles from markdown using AST parsing.

    Uses markdown-it-py token stream to correctly identify headings,
    ignoring headings inside code blocks or other non-heading contexts.
    """
    tokens = _md.parse(content)
    sections = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open" and tok.tag == "h2":
            # The next token is heading content (inline)
            if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                heading_text = tokens[i + 1].content.strip()
                if heading_text:
                    sections.append(heading_text)
        i += 1
    return sections


def generate_summary(content: str) -> str:
    """Extract first meaningful paragraph as summary (<=200 chars).

    Uses markdown-it-py AST to find the first paragraph token,
    skipping headings, code blocks, and component tags.
    """
    tokens = _md.parse(content)
    for i, tok in enumerate(tokens):
        if tok.type == "paragraph_open":
            # Next token should be inline content
            if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                text = tokens[i + 1].content.strip()
                # Skip Mintlify MDX component lines
                if text.startswith("<") and not text.startswith("<a"):
                    continue
                if not text:
                    continue
                if len(text) > 200:
                    text = text[:197] + "..."
                return text
    return ""


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
    """Parse llms-full.txt into individual Topic objects.

    The llms-full.txt format uses section boundaries of:
        # Title
        Source: https://docs.openclaw.ai/path

    Each section's content runs until the next boundary or EOF.
    """
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

        # AST-based section and summary extraction
        sections = extract_sections(section_content)
        summary = generate_summary(section_content)

        content_hash = hashlib.sha256(section_content.encode("utf-8")).hexdigest()
        word_count = len(section_content.split())

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
