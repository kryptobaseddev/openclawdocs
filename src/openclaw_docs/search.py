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
        """Combined path + FTS5 BM25 + fuzzy title search."""
        if not query.strip():
            return []

        # Strategy 1: FTS5 BM25 (primary — full content search)
        fts_results = self.storage.fts_search(query, limit=limit * 3)

        # Strategy 1b: Exact-ish path/slug/category matching for common agent queries
        path_results = self._path_search(query, limit=limit * 2)

        # Strategy 2: Fuzzy title match (secondary — typo tolerance only)
        # High cutoff (75%) to avoid "discord" matching "discovery"
        fuzzy_results = self._fuzzy_search(query, limit=limit)

        # Merge with FTS5 dominant, but preserve strong path/title intent.
        merged = self._merge_results(fts_results, fuzzy_results, path_results, query)

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

        query_norm = query.lower().strip()
        results = []
        for title, score, _idx in matches:
            path = path_map[title]
            category = path.split("/")[0] if "/" in path else "general"
            match_type = "title"
            if query_norm == title.lower().strip():
                score = max(score, 100.0)
                match_type = "exact-title"
            results.append(SearchResult(
                title=title,
                path=path,
                category=category,
                score=round(score / 100.0, 2),
                match_type=match_type,
            ))
        return results

    def _path_search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Exact-ish path/slug/category matching for agent-oriented queries."""
        q = query.lower().strip()
        if not q:
            return []

        results = []
        for topic in self.storage.list_topics():
            path = topic["path"]
            title = topic["title"]
            category = topic["category"]
            slug = path.split("/")[-1]
            score = None
            match_type = "path"

            if q == path.lower():
                score = 1.0
                match_type = "exact-path"
            elif q == slug.lower() or q == category.lower():
                score = 0.95
                match_type = "exact-slug"
            elif path.lower().startswith(q + "/") or path.lower().endswith("/" + q):
                score = 0.9
                match_type = "path-prefix"
            elif q in path.lower() or q in title.lower():
                score = 0.75

            if score is not None:
                results.append(SearchResult(
                    title=title,
                    path=path,
                    category=category,
                    score=score,
                    match_type=match_type,
                ))

        results.sort(key=lambda r: (-r.score, len(r.path), r.title.lower()))
        return results[:limit]

    def _merge_results(
        self,
        fts_results: list[SearchResult],
        fuzzy_results: list[SearchResult],
        path_results: list[SearchResult],
        query: str,
    ) -> list[SearchResult]:
        """Merge results. FTS5 dominates, with strong boosts for exact agent intent."""
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

        # Add exact-ish path/title intent, heavily weighted for agent workflows.
        for r in path_results:
            path_contrib = round(r.score * 0.8, 3)
            if r.path in scored:
                scored[r.path].score = round(max(scored[r.path].score, path_contrib), 3)
                if scored[r.path].match_type == "content":
                    scored[r.path].match_type = r.match_type + "+content"
            else:
                scored[r.path] = SearchResult(
                    title=r.title,
                    path=r.path,
                    category=r.category,
                    score=path_contrib,
                    match_type=r.match_type,
                )

        # Add fuzzy (only high-confidence title matches)
        for r in fuzzy_results:
            fuzzy_contrib = round(r.score * 0.3, 3)
            if r.path in scored:
                scored[r.path].score = round(max(scored[r.path].score, scored[r.path].score + fuzzy_contrib), 3)
                if "content" in scored[r.path].match_type:
                    scored[r.path].match_type = "title+content"
                elif scored[r.path].match_type.startswith("exact") or scored[r.path].match_type.startswith("path"):
                    scored[r.path].match_type = scored[r.path].match_type + "+title"
                else:
                    scored[r.path].match_type = "title"
            else:
                scored[r.path] = SearchResult(
                    title=r.title,
                    path=r.path,
                    category=r.category,
                    score=fuzzy_contrib,
                    match_type=r.match_type,
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
