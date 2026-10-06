from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.scraping.robots import RobotsDecision, RobotsPolicy, RobotsResponse


def test_robots_rules_allow_and_disallow_configured_agent() -> None:
    body = "User-agent: VerificaAI\nDisallow: /privado\nAllow: /publico\n"
    policy = RobotsPolicy(lambda _url: RobotsResponse(200, body))

    assert policy.can_fetch("https://example.org/publico", "VerificaAI") is RobotsDecision.ALLOWED
    assert (
        policy.can_fetch("https://example.org/privado", "VerificaAI") is RobotsDecision.DISALLOWED
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (404, RobotsDecision.ALLOWED),
        (401, RobotsDecision.DISALLOWED),
        (403, RobotsDecision.DISALLOWED),
    ],
)
def test_robots_status_has_conservative_semantics(status: int, expected: RobotsDecision) -> None:
    policy = RobotsPolicy(lambda _url: RobotsResponse(status, ""))

    assert policy.can_fetch("https://example.org/news", "VerificaAI") is expected


def test_robots_network_failure_is_unknown_and_fail_closed() -> None:
    def fail(_url: str) -> RobotsResponse:
        raise httpx.TimeoutException("timeout")

    policy = RobotsPolicy(fail)

    assert policy.can_fetch("https://example.org/news", "VerificaAI") is RobotsDecision.UNKNOWN
    assert not RobotsDecision.UNKNOWN.allowed


def test_robots_cache_expires() -> None:
    now = datetime(2026, 10, 6, tzinfo=UTC)
    calls = 0

    def fetch(_url: str) -> RobotsResponse:
        nonlocal calls
        calls += 1
        return RobotsResponse(404, "")

    def clock() -> datetime:
        return now

    policy = RobotsPolicy(fetch, ttl=timedelta(minutes=5), clock=clock)
    policy.can_fetch("https://example.org/one", "VerificaAI")
    policy.can_fetch("https://example.org/two", "VerificaAI")
    assert calls == 1

    now += timedelta(minutes=6)
    policy.can_fetch("https://example.org/three", "VerificaAI")
    assert calls == 2
