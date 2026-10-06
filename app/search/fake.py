from __future__ import annotations

from app.search.contracts import SearchResult


class FakeSearchProvider:
    def __init__(self, results_by_query: dict[str, list[SearchResult]]) -> None:
        self._results = results_by_query

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        return self._results.get(query, [])[:limit]
