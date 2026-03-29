"""Multi-strategy search: FTS5 BM25 + fuzzy title matching.

Scoring strategy:
- FTS5 BM25 is the primary signal (full-text content + weighted columns)
- Fuzzy title matching is secondary (catches typos, only high-confidence matches)
- Category boost when query matches a category name exactly
- FTS5 results dominate; fuzzy only contributes for high-confidence title matches
"""

from __future__ import annotations

from pathlib import Path

from rapidfuzz import fuzz, process

from openclaw_docs.models import SearchResult
from openclaw_docs.storage import DocsStorage


class SearchEngine:
    def __init__(self, storage: DocsStorage, topics_dir: Path):
        self.storage = storage
        self.topics_dir = topics_dir

    def search(
        self,
        query: str,
        limit: int = 10,
        category: str | None = None,
        include_snippets: bool = False,
    ) -> list[SearchResult]:
        """Combined FTS5 BM25 + fuzzy title search."""
        if not query.strip():
            return []

        # Strategy 1: FTS5 BM25 (primary — full content search)
        fts_results = self.storage.fts_search(query, limit=limit * 3)

        # Strategy 2: Fuzzy title match (secondary — typo tolerance only)
        # High cutoff (75%) to avoid "discord" matching "discovery"
        fuzzy_results = self._fuzzy_search(query, limit=limit)

        # Merge with FTS5 dominant
        merged = self._merge_results(fts_results, fuzzy_results, query)

        if category:
            merged = [r for r in merged if r.category == category]

        merged = merged[:limit]

        if include_snippets:
            for result in merged:
                result.snippet = self._extract_snippet(result.path, query)

        return merged

    def _fuzzy_search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Fuzzy search over topic titles. High cutoff for precision."""
        titles = self.storage.get_all_titles()
        if not titles:
            return []

        title_list = [t[0] for t in titles]
        path_map = {t[0]: t[1] for t in titles}

        # WRatio with 75% cutoff — only genuine title matches, not substring noise
        matches = process.extract(
            query, title_list, scorer=fuzz.WRatio, limit=limit, score_cutoff=75.0
        )

        results = []
        for title, score, _idx in matches:
            path = path_map[title]
            category = path.split("/")[0] if "/" in path else "general"
            results.append(SearchResult(
                title=title,
                path=path,
                category=category,
                score=round(score / 100.0, 2),
                match_type="title",
            ))
        return results

    def _merge_results(
        self,
        fts_results: list[SearchResult],
        fuzzy_results: list[SearchResult],
        query: str,
    ) -> list[SearchResult]:
        """Merge results. FTS5 dominates (0.7 weight), fuzzy supplements (0.3)."""
        scored: dict[str, SearchResult] = {}

        # Normalize FTS5 scores relative to the best hit
        max_fts = max((r.score for r in fts_results), default=0.0) or 1.0
        for r in fts_results:
            normalized = r.score / max_fts  # best hit = 1.0
            scored[r.path] = SearchResult(
                title=r.title,
                path=r.path,
                category=r.category,
                score=round(normalized * 0.7, 3),
                match_type="content",
            )

        # Add fuzzy (only high-confidence title matches)
        for r in fuzzy_results:
            fuzzy_contrib = round(r.score * 0.3, 3)
            if r.path in scored:
                scored[r.path].score = round(scored[r.path].score + fuzzy_contrib, 3)
                scored[r.path].match_type = "title+content"
            else:
                scored[r.path] = SearchResult(
                    title=r.title,
                    path=r.path,
                    category=r.category,
                    score=fuzzy_contrib,
                    match_type="title",
                )

        # Category boost
        query_lower = query.lower().strip()
        for result in scored.values():
            if result.category.lower() == query_lower:
                result.score = round(result.score + 0.1, 3)

        results = sorted(scored.values(), key=lambda r: r.score, reverse=True)
        for r in results:
            r.score = min(1.0, round(r.score, 2))
        return results

    def _extract_snippet(self, path: str, query: str, context_chars: int = 150) -> str:
        """Extract a context window around the best match in topic content."""
        content = self.storage.get_topic_content(path, self.topics_dir)
        if not content:
            return ""

        terms = query.lower().split()
        content_lower = content.lower()

        best_pos = -1
        for term in terms:
            pos = content_lower.find(term)
            if pos != -1:
                best_pos = pos
                break

        if best_pos == -1:
            return content[:context_chars].strip() + "..."

        start = max(0, best_pos - context_chars // 2)
        end = min(len(content), best_pos + context_chars // 2)

        snippet = content[start:end].strip()
        if start > 0:
            first_space = snippet.find(" ")
            if first_space > 0:
                snippet = "..." + snippet[first_space + 1:]
        if end < len(content):
            last_space = snippet.rfind(" ")
            if last_space > 0:
                snippet = snippet[:last_space] + "..."

        return snippet
