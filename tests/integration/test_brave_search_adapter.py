from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.search.brave import BraveSearchProvider, SearchProviderError

FIXTURE = Path(__file__).parents[1] / "fixtures" / "search" / "results.json"


def test_brave_adapter_requires_key() -> None:
    with pytest.raises(SearchProviderError, match="BRAVE_SEARCH_API_KEY"):
        BraveSearchProvider(api_key="")


def test_brave_adapter_maps_rank_query_domain_and_parameters() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        assert request.headers["X-Subscription-Token"] == "secret"
        return httpx.Response(200, json=json.loads(FIXTURE.read_text()))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    results = BraveSearchProvider(api_key="secret", client=client).search("contrato doses", 10)

    assert seen == {"q": "contrato doses", "count": "10", "country": "BR", "ui_lang": "pt-BR"}
    assert [item.rank for item in results] == [1, 2]
    assert results[0].query == "contrato doses"
    assert results[0].domain == "transparencia.example.gov.br"
    assert results[0].published_at.isoformat() == "2026-01-15T12:00:00+00:00"


@pytest.mark.parametrize(
    "failure",
    [httpx.TimeoutException("timeout"), httpx.Response(429), httpx.Response(200, json={"bad": []})],
)
def test_brave_adapter_reports_timeout_quota_and_malformed_response(failure) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(failure, Exception):
            raise failure
        failure.request = request
        return failure

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(SearchProviderError):
        BraveSearchProvider(api_key="secret", client=client).search("consulta")
