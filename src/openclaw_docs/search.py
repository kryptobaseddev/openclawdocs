"""Multi-strategy search: FTS5 BM25 + fuzzy title matching."""

from __future__ import annotations

import re
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

        # Strategy 1: FTS5 BM25 (primary)
        fts_results = self.storage.fts_search(query, limit=limit * 2)

        # Strategy 2: Fuzzy title match (secondary)
        fuzzy_results = self._fuzzy_search(query, limit=limit * 2)

        # Merge and score
        merged = self._merge_results(fts_results, fuzzy_results, query)

        # Filter by category if specified
        if category:
            merged = [r for r in merged if r.category == category]

        # Trim to limit
        merged = merged[:limit]

        # Add snippets if requested
        if include_snippets:
            for result in merged:
                result.snippet = self._extract_snippet(result.path, query)

        return merged

    def _fuzzy_search(self, query: str, limit: int = 20) -> list[SearchResult]:
        """Fuzzy search over topic titles using rapidfuzz."""
        titles = self.storage.get_all_titles()
        if not titles:
            return []

        title_list = [t[0] for t in titles]
        path_map = {t[0]: t[1] for t in titles}

        matches = process.extract(
            query, title_list, scorer=fuzz.WRatio, limit=limit, score_cutoff=50.0
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
        """Merge FTS5 and fuzzy results with weighted scoring."""
        scored: dict[str, SearchResult] = {}

        # FTS5 results (weight 0.6)
        for r in fts_results:
            scored[r.path] = SearchResult(
                title=r.title,
                path=r.path,
                category=r.category,
                score=round(r.score * 0.6, 2),
                match_type=r.match_type,
            )

        # Fuzzy results (weight 0.3)
        for r in fuzzy_results:
            if r.path in scored:
                scored[r.path].score = round(scored[r.path].score + r.score * 0.3, 2)
                if r.match_type == "title":
                    scored[r.path].match_type = "title+content"
            else:
                scored[r.path] = SearchResult(
                    title=r.title,
                    path=r.path,
                    category=r.category,
                    score=round(r.score * 0.3, 2),
                    match_type=r.match_type,
                )

        # Category boost (weight 0.1)
        query_lower = query.lower().strip()
        for path, result in scored.items():
            if result.category.lower() == query_lower:
                result.score = round(result.score + 0.1, 2)

        # Sort by score descending, cap at 1.0
        results = sorted(scored.values(), key=lambda r: r.score, reverse=True)
        for r in results:
            r.score = min(1.0, r.score)
        return results

    def _extract_snippet(self, path: str, query: str, context_chars: int = 150) -> str:
        """Extract a context window around the best match in topic content."""
        content = self.storage.get_topic_content(path, self.topics_dir)
        if not content:
            return ""

        # Find the best position for the query terms
        terms = query.lower().split()
        content_lower = content.lower()

        best_pos = -1
        for term in terms:
            pos = content_lower.find(term)
            if pos != -1:
                best_pos = pos
                break

        if best_pos == -1:
            # Return first chunk as fallback
            return content[:context_chars].strip() + "..."

        start = max(0, best_pos - context_chars // 2)
        end = min(len(content), best_pos + context_chars // 2)

        snippet = content[start:end].strip()
        # Clean up partial lines at boundaries
        if start > 0:
            snippet = "..." + snippet[snippet.find(" ") + 1:]
        if end < len(content):
            last_space = snippet.rfind(" ")
            if last_space > 0:
                snippet = snippet[:last_space] + "..."

        return snippet
