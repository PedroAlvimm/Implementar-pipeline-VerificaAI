from __future__ import annotations

from app.search.canonical import canonicalize_url
from app.search.contracts import SearchResult
from app.search.filtering import deduplicate_results, exclude_fact_checkers


def result(url: str, rank: int = 1) -> SearchResult:
    return SearchResult(
        title="Resultado",
        url=url,
        snippet="Trecho",
        domain="ignored.example",
        published_at=None,
        query="consulta",
        rank=rank,
    )


def test_canonical_url_removes_tracking_fragment_and_default_port() -> None:
    url = "HTTPS://Example.Org:443/news?utm_source=x&id=2&fbclid=y#section"

    assert canonicalize_url(url) == "https://example.org/news?id=2"


def test_same_and_canonical_urls_are_deduplicated_by_best_rank() -> None:
    items = [
        result("https://example.org/news?utm_campaign=x", rank=2),
        result("https://example.org/news", rank=1),
        result("https://other.example/news", rank=3),
    ]

    deduplicated = deduplicate_results(items)

    assert [item.url for item in deduplicated] == [
        "https://example.org/news",
        "https://other.example/news",
    ]


def test_known_and_configured_fact_check_domains_are_excluded() -> None:
    items = [
        result("https://lupa.uol.com.br/check"),
        result("https://aosfatos.org/noticia"),
        result("https://g1.globo.com/fato-ou-fake/x"),
        result("https://projetocomprova.com.br/x"),
        result("https://checamos.afp.com/x"),
        result("https://custom-check.example/x"),
        result("https://gov.br/documento"),
    ]

    filtered = exclude_fact_checkers(items, additional_domains={"custom-check.example"})

    assert [item.domain for item in filtered] == ["gov.br"]
