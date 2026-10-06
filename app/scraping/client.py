from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import httpx

from app.core.enums import OperationStatus
from app.core.outcomes import OperationOutcome
from app.scraping.block_detection import BlockDetector
from app.scraping.extraction import CollectedPage
from app.scraping.robots import RobotsDecision, RobotsPolicy
from app.scraping.transport import PinnedHttpTransport
from app.scraping.url_policy import UrlPolicy


class DomainRateLimiter:
    def __init__(
        self,
        requests_per_second: int = 1,
        concurrency: int = 2,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._interval = 1 / requests_per_second
        self._concurrency = concurrency
        self._clock = clock
        self._sleep = sleep
        self._last: dict[str, datetime] = {}
        self._semaphores: dict[str, threading.BoundedSemaphore] = {}
        self._lock = threading.Lock()

    @contextmanager
    def slot(self, domain: str) -> Iterator[None]:
        with self._lock:
            semaphore = self._semaphores.setdefault(
                domain, threading.BoundedSemaphore(self._concurrency)
            )
        with semaphore:
            previous = self._last.get(domain)
            now = self._clock()
            if previous is not None:
                remaining = self._interval - (now - previous).total_seconds()
                if remaining > 0:
                    self._sleep(remaining)
            self._last[domain] = self._clock()
            yield


class SafeCollector:
    def __init__(
        self,
        policy: UrlPolicy,
        transport: PinnedHttpTransport,
        robots: RobotsPolicy,
        *,
        max_bytes: int = 5 * 1024 * 1024,
        user_agent: str = "VerificaAI/0.1 (+local-research)",
        rate_limiter: DomainRateLimiter | None = None,
        cache_size: int = 128,
        cache_ttl: timedelta = timedelta(minutes=10),
    ) -> None:
        self._policy = policy
        self._transport = transport
        self._robots = robots
        self._max_bytes = max_bytes
        self._user_agent = user_agent
        self._limiter = rate_limiter or DomainRateLimiter()
        self._cache_size = cache_size
        self._cache_ttl = cache_ttl
        self._cache: OrderedDict[str, tuple[datetime, CollectedPage]] = OrderedDict()
        self._block_detector = BlockDetector()

    def collect(self, url: str) -> OperationOutcome[CollectedPage]:
        now = datetime.now(UTC)
        cached = self._cache.get(url)
        if cached and now - cached[0] <= self._cache_ttl:
            return OperationOutcome(status=OperationStatus.SUCCESS, data=cached[1])
        target = self._policy.validate(url)
        robots = self._robots.can_fetch(target.url, self._user_agent)
        if robots is not RobotsDecision.ALLOWED:
            return OperationOutcome(
                status=OperationStatus.BLOCKED,
                error_code=f"ROBOTS_{robots.value}",
                error_message="A coleta não foi permitida; cole o texto para continuar.",
            )
        try:
            with self._limiter.slot(target.hostname):
                response = self._transport.request(
                    target, headers={"User-Agent": self._user_agent, "Accept": "text/html"}
                )
        except httpx.TimeoutException:
            return OperationOutcome(
                status=OperationStatus.TECHNICAL_ERROR,
                error_code="COLLECTION_TIMEOUT",
                error_message="A página não respondeu no tempo permitido.",
            )
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type.casefold():
            return OperationOutcome(
                status=OperationStatus.BLOCKED,
                error_code="UNSUPPORTED_CONTENT_TYPE",
                error_message="A URL não retornou uma página HTML.",
            )
        declared = response.headers.get("content-length")
        declared_too_large = bool(declared and int(declared) > self._max_bytes)
        body_too_large = len(response.content) > self._max_bytes
        if declared_too_large or body_too_large:
            return OperationOutcome(
                status=OperationStatus.BLOCKED,
                error_code="DOWNLOAD_TOO_LARGE",
                error_message="A página excede o limite de download.",
            )
        encoding = response.encoding or "utf-8"
        page = CollectedPage(
            requested_url=url,
            final_url=str(response.url),
            html=response.content.decode(encoding, errors="replace"),
            content_type=content_type,
        )
        block = self._block_detector.detect(page)
        if block is not None:
            return OperationOutcome(
                status=OperationStatus.BLOCKED,
                error_code=block.value,
                error_message="O conteúdo está bloqueado; cole o texto para continuar.",
            )
        self._cache[url] = (now, page)
        self._cache.move_to_end(url)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return OperationOutcome(status=OperationStatus.SUCCESS, data=page)
