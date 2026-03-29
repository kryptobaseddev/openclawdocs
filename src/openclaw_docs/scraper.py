"""Direct page scraper for docs missing from llms-full.txt.

The llms-full.txt dump covers ~362 pages, but the Mintlify docs.json
navigation lists ~640+ pages. Most of the gap is i18n translations
(zh-CN, ja-JP) which we skip. The remaining ~20 English pages are
fetched individually and parsed into Topics.
"""

from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import httpx

from openclaw_docs.config import DOCS_BASE_URL
from openclaw_docs.models import Topic
from openclaw_docs.parser import generate_summary

# Paths to skip (i18n, non-content)
_SKIP_PREFIXES = ("zh-CN/", "ja-JP/", "api-reference/")
_SKIP_EXACT = {"mintlify.com", "api-reference/openapi.json"}

# Path to docs.json navigation config. Checked in multiple locations.
_DOCS_JSON_CANDIDATES = [
    Path("/mnt/projects/openclaw-bot/.tmp-openclaw-docs.json"),
    Path("/mnt/projects/openclaw/docs/docs.json"),
]


class _ContentExtractor(HTMLParser):
    """Extract article content from Mintlify HTML, converting to markdown.

    Targets the prose div (class containing 'prose' + data-page-title attr)
    which is Mintlify's main content area. Ignores all chrome (nav, header,
    footer, sidebar).
    """

    def __init__(self) -> None:
        super().__init__()
        self._result: list[str] = []
        self._skip_tags = {"script", "style", "noscript"}
        self._in_skip = 0
        self._in_prose = False
        self._prose_depth = 0
        self._tag_stack: list[str] = []
        self._page_title: str = ""
        # Skip anchor wrapper divs inside headings (Mintlify navigation anchors)
        self._in_heading_anchor = False
        self._in_heading = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)

        if tag in self._skip_tags:
            self._in_skip += 1
            return

        # Detect the Mintlify prose content div
        cls = attr_dict.get("class", "")
        if tag == "div" and "prose" in cls and attr_dict.get("data-page-title"):
            self._in_prose = True
            self._prose_depth = 1
            self._page_title = attr_dict["data-page-title"]
            return

        # Track div nesting while in prose
        if self._in_prose and tag == "div":
            self._prose_depth += 1

        if not self._in_prose:
            return

        self._tag_stack.append(tag)

        # Skip the absolute-positioned anchor div inside headings
        if tag == "div" and "absolute" in cls:
            self._in_heading_anchor = True
            return
        if tag == "a" and self._in_heading_anchor:
            return

        # Convert HTML to markdown
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            self._result.append(f"\n\n{'#' * level} ")
            self._in_heading = True
        elif tag == "p":
            self._result.append("\n\n")
        elif tag == "li":
            self._result.append("\n- ")
        elif tag == "br":
            self._result.append("\n")
        elif tag == "code":
            if "pre" not in self._tag_stack:
                self._result.append("`")
        elif tag == "pre":
            lang = ""
            if cls:
                m = re.search(r"language-(\w+)", cls)
                if m:
                    lang = m.group(1)
            self._result.append(f"\n\n```{lang}\n")
        elif tag == "a" and not self._in_heading_anchor and not self._in_heading:
            self._result.append("[")
        elif tag in ("strong", "b"):
            self._result.append("**")
        elif tag in ("em", "i"):
            self._result.append("*")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._skip_tags:
            self._in_skip = max(0, self._in_skip - 1)
            return

        if self._in_prose and tag == "div":
            self._prose_depth -= 1
            if self._prose_depth <= 0:
                self._in_prose = False
                return
            # End of heading anchor div
            if self._in_heading_anchor:
                self._in_heading_anchor = False
                return

        if not self._in_prose:
            return

        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

        if tag == "pre":
            self._result.append("\n```\n")
        elif tag == "code" and "pre" not in self._tag_stack:
            self._result.append("`")
        elif tag in ("strong", "b"):
            self._result.append("**")
        elif tag in ("em", "i"):
            self._result.append("*")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._result.append("\n")
            self._in_heading = False
        elif tag == "a" and not self._in_heading_anchor and not self._in_heading:
            # We don't track href for simplicity — just close the link text
            self._result.append("]")

    def handle_data(self, data: str) -> None:
        if self._in_skip > 0 or not self._in_prose or self._in_heading_anchor:
            return
        self._result.append(data)

    def get_content(self) -> str:
        raw = "".join(self._result)
        # Clean up excessive whitespace and zero-width chars
        raw = raw.replace("\u200b", "")  # zero-width space from Mintlify anchors
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()

    def get_title(self) -> str:
        return self._page_title


def _extract_markdown_from_html(html: str) -> tuple[str, str]:
    """Extract content from Mintlify HTML page.

    Returns (content_markdown, page_title).
    Uses the prose div with data-page-title as the content boundary.
    Falls back to full-page extraction if prose div not found.
    """
    parser = _ContentExtractor()
    parser.feed(html)
    content = parser.get_content()
    title = parser.get_title()

    # If prose extraction found nothing, fall back to regex extraction
    if not content:
        # Try extracting between the prose div boundaries with regex
        match = re.search(
            r'<div[^>]*class="[^"]*prose[^"]*"[^>]*data-page-title="([^"]+)"[^>]*>(.*?)(?=<footer|</body)',
            html, re.DOTALL,
        )
        if match:
            title = match.group(1)
            raw_html = match.group(2)
            # Strip all HTML tags for a basic text extraction
            content = re.sub(r"<[^>]+>", " ", raw_html)
            content = re.sub(r"\s+", " ", content).strip()

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
    """Fetch a single page and convert to a Topic.

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

    content, page_title = _extract_markdown_from_html(resp.text)
    if not content or len(content) < 50:
        return None

    # Use title from data-page-title attr, fall back to first heading, then slug
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

    sections = re.findall(r"^## (.+)$", content, re.MULTILINE)
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
