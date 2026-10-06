from __future__ import annotations

from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

import httpx

from app.core.enums import OperationStatus
from app.scraping.client import DomainRateLimiter, SafeCollector
from app.scraping.robots import RobotsDecision
from app.scraping.url_policy import UrlPolicy


class Resolver:
    def resolve_public(self, hostname: str):
        del hostname
        return (ip_address("93.184.216.34"),)


class Robots:
    def __init__(self, decision: RobotsDecision = RobotsDecision.ALLOWED) -> None:
        self.decision = decision

    def can_fetch(self, url: str, user_agent: str) -> RobotsDecision:
        del url, user_agent
        return self.decision


class Transport:
    def __init__(self, response: httpx.Response | Exception) -> None:
        self.response = response
        self.calls = 0

    def request(self, target, **kwargs):
        del kwargs
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        self.response.request = httpx.Request("GET", target.url)
        return self.response


def collector(response: httpx.Response | Exception, **kwargs) -> SafeCollector:
    return SafeCollector(
        UrlPolicy(Resolver()),
        Transport(response),
        Robots(),
        max_bytes=20,
        **kwargs,
    )


def test_collector_returns_technical_error_on_timeout() -> None:
    result = collector(httpx.TimeoutException("timeout")).collect("https://example.org/news")

    assert result.status is OperationStatus.TECHNICAL_ERROR
    assert result.error_code == "COLLECTION_TIMEOUT"


def test_collector_rejects_non_html_and_oversized_content() -> None:
    non_html = collector(
        httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"pdf")
    ).collect("https://example.org/file")
    oversized = collector(
        httpx.Response(200, headers={"content-type": "text/html"}, content=b"x" * 21)
    ).collect("https://example.org/news")

    assert non_html.error_code == "UNSUPPORTED_CONTENT_TYPE"
    assert oversized.error_code == "DOWNLOAD_TOO_LARGE"


def test_collector_blocks_unknown_robots_and_guides_user_to_paste_text() -> None:
    service = SafeCollector(
        UrlPolicy(Resolver()),
        Transport(httpx.Response(200, content=b"unused")),
        Robots(RobotsDecision.UNKNOWN),
    )

    result = service.collect("https://example.org/news")

    assert result.status is OperationStatus.BLOCKED
    assert "cole o texto" in result.error_message.casefold()


def test_collector_reuses_bounded_cache() -> None:
    transport = Transport(
        httpx.Response(200, headers={"content-type": "text/html"}, content=b"<p>noticia</p>")
    )
    service = SafeCollector(UrlPolicy(Resolver()), transport, Robots(), max_bytes=100)

    first = service.collect("https://example.org/news")
    second = service.collect("https://example.org/news")

    assert first.data == second.data
    assert transport.calls == 1


def test_domain_rate_limiter_waits_one_second_between_requests() -> None:
    now = datetime(2026, 10, 6, tzinfo=UTC)
    sleeps: list[float] = []

    def clock() -> datetime:
        return now

    def sleep(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += timedelta(seconds=seconds)

    limiter = DomainRateLimiter(requests_per_second=1, concurrency=2, clock=clock, sleep=sleep)
    with limiter.slot("example.org"):
        pass
    with limiter.slot("example.org"):
        pass

    assert sleeps == [1.0]
