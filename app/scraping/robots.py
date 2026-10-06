from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser


class RobotsDecision(StrEnum):
    ALLOWED = "ALLOWED"
    DISALLOWED = "DISALLOWED"
    UNKNOWN = "UNKNOWN"

    @property
    def allowed(self) -> bool:
        return self is RobotsDecision.ALLOWED


@dataclass(frozen=True)
class RobotsResponse:
    status_code: int
    text: str


@dataclass(frozen=True)
class _CachedRules:
    response: RobotsResponse | None
    expires_at: datetime


class RobotsPolicy:
    def __init__(
        self,
        fetch: Callable[[str], RobotsResponse],
        *,
        ttl: timedelta = timedelta(hours=1),
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._fetch = fetch
        self._ttl = ttl
        self._clock = clock
        self._cache: dict[str, _CachedRules] = {}

    def can_fetch(self, url: str, user_agent: str) -> RobotsDecision:
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        cached = self._cache.get(origin)
        now = self._clock()
        if cached is None or cached.expires_at <= now:
            try:
                response = self._fetch(f"{origin}/robots.txt")
            except Exception:
                response = None
            cached = _CachedRules(response, now + self._ttl)
            self._cache[origin] = cached
        response = cached.response
        if response is None:
            return RobotsDecision.UNKNOWN
        if response.status_code == 404:
            return RobotsDecision.ALLOWED
        if response.status_code in {401, 403}:
            return RobotsDecision.DISALLOWED
        if response.status_code != 200:
            return RobotsDecision.UNKNOWN
        parser = RobotFileParser()
        parser.set_url(f"{origin}/robots.txt")
        parser.parse(response.text.splitlines())
        return (
            RobotsDecision.ALLOWED
            if parser.can_fetch(user_agent, url)
            else RobotsDecision.DISALLOWED
        )
