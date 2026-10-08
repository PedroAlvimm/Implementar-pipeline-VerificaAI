from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from app.core.config import Settings
from app.core.enums import OperationStatus
from app.core.errors import CollectionError, RedirectLimitError, UnsafeUrlError
from app.core.outcomes import OperationOutcome
from app.scraping.client import DomainRateLimiter, SafeCollector
from app.scraping.dns import DnsResolver
from app.scraping.extraction import ArticleExtractor, CollectedPage
from app.scraping.robots import RobotsPolicy, RobotsResponse
from app.scraping.transport import PinnedHttpTransport
from app.scraping.url_policy import UrlPolicy


class LoadedUrl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    title: str | None
    canonical_url: str
    final_url: str


class UrlInputFailure(CollectionError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PageCollector(Protocol):
    def collect(self, url: str) -> OperationOutcome[CollectedPage]: ...


class UrlInputLoader:
    def __init__(self, collector: PageCollector, extractor: ArticleExtractor) -> None:
        self._collector = collector
        self._extractor = extractor

    def __call__(self, url: str) -> LoadedUrl:
        try:
            outcome = self._collector.collect(url)
        except UnsafeUrlError as exc:
            raise UrlInputFailure("UNSAFE_URL", str(exc)) from exc
        except RedirectLimitError as exc:
            raise UrlInputFailure("REDIRECT_LIMIT", str(exc)) from exc
        except (TimeoutError, OSError) as exc:
            raise UrlInputFailure(
                "COLLECTION_TECHNICAL_ERROR",
                "A página não respondeu no tempo permitido.",
            ) from exc
        if outcome.status is not OperationStatus.SUCCESS or outcome.data is None:
            raise UrlInputFailure(
                outcome.error_code or "COLLECTION_FAILED",
                outcome.error_message or "Não foi possível coletar a página.",
            )
        try:
            article = self._extractor.extract(outcome.data)
        except CollectionError as exc:
            raise UrlInputFailure("EXTRACTION_FAILED", str(exc)) from exc
        return LoadedUrl(
            text=article.clean_text,
            title=article.title,
            canonical_url=article.canonical_url,
            final_url=outcome.data.final_url,
        )


def build_safe_url_loader(settings: Settings) -> UrlInputLoader:
    policy = UrlPolicy(DnsResolver())
    transport = PinnedHttpTransport(policy, max_redirects=settings.max_redirects)

    def fetch_robots(url: str) -> RobotsResponse:
        target = policy.validate(url)
        response = transport.request(
            target,
            headers={"User-Agent": "VerificaAI/0.1 (+local-research)"},
        )
        return RobotsResponse(status_code=response.status_code, text=response.text)

    robots = RobotsPolicy(fetch_robots)
    collector = SafeCollector(
        policy,
        transport,
        robots,
        max_bytes=settings.max_download_bytes,
        rate_limiter=DomainRateLimiter(
            requests_per_second=settings.domain_requests_per_second,
            concurrency=settings.domain_concurrency,
        ),
    )
    return UrlInputLoader(collector, ArticleExtractor())
