from __future__ import annotations

from urllib.parse import urlsplit

from app.search.canonical import canonicalize_url
from app.search.contracts import SearchResult

_FACT_CHECK_DOMAINS = {
    "lupa.uol.com.br",
    "aosfatos.org",
    "projetocomprova.com.br",
    "checamos.afp.com",
}
_FACT_CHECK_PATHS = {("g1.globo.com", "/fato-ou-fake/")}


def _matches_domain(domain: str, blocked: set[str]) -> bool:
    return any(domain == item or domain.endswith(f".{item}") for item in blocked)


def exclude_fact_checkers(
    results: list[SearchResult], additional_domains: set[str] | None = None
) -> list[SearchResult]:
    blocked = _FACT_CHECK_DOMAINS | {item.casefold() for item in (additional_domains or set())}
    filtered: list[SearchResult] = []
    for result in results:
        parsed = urlsplit(result.url)
        domain = (parsed.hostname or "").casefold()
        path = parsed.path.casefold()
        if _matches_domain(domain, blocked):
            continue
        if any(domain == host and marker in path for host, marker in _FACT_CHECK_PATHS):
            continue
        filtered.append(result.model_copy(update={"domain": domain}))
    return filtered


def deduplicate_results(results: list[SearchResult]) -> list[SearchResult]:
    by_url: dict[str, SearchResult] = {}
    for result in sorted(results, key=lambda item: item.rank):
        canonical = canonicalize_url(result.url)
        if canonical not in by_url:
            domain = urlsplit(canonical).hostname or ""
            by_url[canonical] = result.model_copy(update={"url": canonical, "domain": domain})
    return list(by_url.values())
