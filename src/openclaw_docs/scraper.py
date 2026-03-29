"""Direct page scraper for docs missing from llms-full.txt.

Uses trafilatura for high-accuracy content extraction (F1 0.958).
The llms-full.txt dump covers ~362 pages, but the Mintlify docs.json
navigation lists ~640+ pages. Most of the gap is i18n translations
(zh-CN, ja-JP) which we skip. The remaining ~20 English pages are
fetched individually via httpx and extracted via trafilatura.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import httpx
import trafilatura

from openclaw_docs.config import DOCS_BASE_URL
from openclaw_docs.models import Topic
from openclaw_docs.parser import generate_summary, extract_sections

# Paths to skip (i18n, non-content)
_SKIP_PREFIXES = ("zh-CN/", "ja-JP/", "api-reference/")
_SKIP_EXACT = {"mintlify.com", "api-reference/openapi.json"}

# Path to docs.json navigation config. Checked in multiple locations.
_DOCS_JSON_CANDIDATES = [
    Path("/mnt/projects/openclaw-bot/.tmp-openclaw-docs.json"),
    Path("/mnt/projects/openclaw/docs/docs.json"),
]

# Page title regex for Mintlify HTML data-page-title attribute
_PAGE_TITLE_RE = re.compile(r'data-page-title="([^"]+)"')


def _extract_page_title(html: str) -> str:
    """Extract the data-page-title from Mintlify HTML."""
    match = _PAGE_TITLE_RE.search(html)
    return match.group(1) if match else ""


def extract_content(html: str) -> tuple[str, str]:
    """Extract markdown content and title from HTML using trafilatura.

    Returns (content_markdown, page_title).
    Uses httpx for fetching (handles redirects), trafilatura for extraction.
    """
    title = _extract_page_title(html)

    content = trafilatura.extract(
        html,
        output_format="markdown",
        include_links=True,
        include_tables=True,
        include_images=False,
        no_fallback=False,
    )

    if not content:
        return "", title

    return content, title


def get_navigation_pages() -> set[str]:
    """Extract all page paths from the docs.json Mintlify navigation config."""
    docs_json = None
    for candidate in _DOCS_JSON_CANDIDATES:
        if candidate.exists():
            docs_json = candidate
            break

    if not docs_json:
        return set()

    with open(docs_json) as f:
        data = json.load(f)

    pages: set[str] = set()

    def _extract(obj: object) -> None:
        if isinstance(obj, str):
            pages.add(obj)
        elif isinstance(obj, list):
            for item in obj:
                _extract(item)
        elif isinstance(obj, dict):
            if "pages" in obj:
                _extract(obj["pages"])
            if "page" in obj:
                _extract(obj["page"])
            for v in obj.values():
                if isinstance(v, (list, dict)):
                    _extract(v)

    nav = data.get("navigation") or data.get("tabs", [])
    _extract(nav)
    return pages


def find_missing_pages(known_paths: set[str]) -> list[str]:
    """Find English pages in docs.json nav that aren't in known_paths."""
    all_pages = get_navigation_pages()
    missing = []
    for page in sorted(all_pages):
        if page in known_paths:
            continue
        if any(page.startswith(prefix) for prefix in _SKIP_PREFIXES):
            continue
        if page in _SKIP_EXACT:
            continue
        missing.append(page)
    return missing


def scrape_page(client: httpx.Client, page_path: str) -> Topic | None:
    """Fetch a single page and extract content with trafilatura.

    Returns None if the page doesn't exist (404) or can't be parsed.
    """
    url = f"{DOCS_BASE_URL}/{page_path}"
    try:
        resp = client.get(url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except httpx.HTTPError:
        return None

    content, page_title = extract_content(resp.text)
    if not content or len(content) < 50:
        return None

    # Use title from data-page-title, fall back to first heading, then slug
    if page_title:
        title = page_title
    else:
        title_match = re.match(r"^#\s+(.+?)$", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else page_path.split("/")[-1].title()

    # Category and slug from path
    parts = page_path.split("/")
    if len(parts) >= 2:
        category, slug = parts[0], parts[-1]
    else:
        category, slug = "general", parts[0]

    sections = extract_sections(content)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    word_count = len(content.split())
    summary = generate_summary(content)

    return Topic(
        title=title,
        source_url=url,
        path=page_path,
        category=category,
        slug=slug,
        content=content,
        content_hash=content_hash,
        sections=sections,
        word_count=word_count,
        summary=summary,
    )


def scrape_missing_pages(
    client: httpx.Client,
    known_paths: set[str],
    on_progress: callable | None = None,
) -> list[Topic]:
    """Find and scrape all pages missing from the known set.

    Args:
        client: httpx.Client for HTTP requests
        known_paths: Set of paths already in the local store
        on_progress: Optional callback(current, total, path) for progress
    """
    missing = find_missing_pages(known_paths)
    if not missing:
        return []

    topics = []
    for i, page_path in enumerate(missing):
        if on_progress:
            on_progress(i + 1, len(missing), page_path)
        topic = scrape_page(client, page_path)
        if topic:
            topics.append(topic)
    return topics
