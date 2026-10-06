from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit

import httpx

from app.search.contracts import SearchResult


class SearchProviderError(RuntimeError):
    pass


class BraveSearchProvider:
    endpoint = "https://api.search.brave.com/res/v1/web/search"

    def __init__(
        self,
        *,
        api_key: str,
        client: httpx.Client | None = None,
        timeout: float = 20,
    ) -> None:
        if not api_key:
            raise SearchProviderError("BRAVE_SEARCH_API_KEY não foi configurada")
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=timeout, trust_env=False)

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        try:
            response = self._client.get(
                self.endpoint,
                params={"q": query, "count": limit, "country": "BR", "ui_lang": "pt-BR"},
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": self._api_key,
                },
            )
        except httpx.TimeoutException as exc:
            raise SearchProviderError("Timeout no provedor de busca") from exc
        if response.status_code == 429:
            raise SearchProviderError("Quota ou rate limit do provedor de busca")
        if response.is_error:
            raise SearchProviderError(f"Falha no provedor de busca: HTTP {response.status_code}")
        try:
            raw_results = response.json()["web"]["results"]
            if not isinstance(raw_results, list):
                raise TypeError
        except (KeyError, TypeError, ValueError) as exc:
            raise SearchProviderError("Resposta malformada do provedor de busca") from exc
        results: list[SearchResult] = []
        for rank, item in enumerate(raw_results[:limit], 1):
            try:
                url = str(item["url"])
                title = str(item["title"])
            except (KeyError, TypeError) as exc:
                raise SearchProviderError("Resultado de busca malformado") from exc
            published = item.get("page_age")
            published_at = (
                datetime.fromisoformat(str(published).replace("Z", "+00:00")) if published else None
            )
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=str(item.get("description", "")),
                    domain=urlsplit(url).hostname or "",
                    published_at=published_at,
                    query=query,
                    rank=rank,
                )
            )
        return results
