from __future__ import annotations

from ipaddress import ip_address

import httpx
import pytest

from app.core.errors import RedirectLimitError, UnsafeUrlError
from app.scraping.transport import PinnedHttpTransport
from app.scraping.url_policy import UrlPolicy


class ChangingResolver:
    def __init__(self) -> None:
        self.calls = 0

    def resolve_public(self, hostname: str):
        del hostname
        self.calls += 1
        if self.calls == 1:
            return (ip_address("93.184.216.34"),)
        raise AssertionError("DNS foi consultado novamente durante a conexão")


class MappingResolver:
    def resolve_public(self, hostname: str):
        if hostname == "private.example":
            raise UnsafeUrlError("Destino não público")
        return (ip_address("93.184.216.34"),)


def test_fetch_uses_validated_ip_not_second_dns_answer() -> None:
    resolver = ChangingResolver()
    policy = UrlPolicy(resolver)
    target = policy.validate("https://example.org/news")
    seen: list[tuple[str, str]] = []

    def connector(target, address, method, headers, content):
        del method, headers, content
        seen.append((target.hostname, str(address)))
        return httpx.Response(200, text="ok", request=httpx.Request("GET", target.url))

    response = PinnedHttpTransport(policy, connector=connector).request(target)

    assert response.status_code == 200
    assert seen == [("example.org", "93.184.216.34")]
    assert resolver.calls == 1


def test_redirect_to_private_destination_is_blocked() -> None:
    policy = UrlPolicy(MappingResolver())
    target = policy.validate("https://example.org/news")

    def connector(target, address, method, headers, content):
        del address, method, headers, content
        return httpx.Response(
            302,
            headers={"location": "http://private.example/admin"},
            request=httpx.Request("GET", target.url),
        )

    with pytest.raises(UnsafeUrlError):
        PinnedHttpTransport(policy, connector=connector).request(target)


def test_cross_origin_redirect_strips_credentials() -> None:
    policy = UrlPolicy(MappingResolver())
    target = policy.validate("https://example.org/news")
    observed_headers: list[dict[str, str]] = []

    def connector(target, address, method, headers, content):
        del address, method, content
        observed_headers.append(dict(headers))
        if target.hostname == "example.org":
            return httpx.Response(
                302,
                headers={"location": "https://other.example/news"},
                request=httpx.Request("GET", target.url),
            )
        return httpx.Response(200, request=httpx.Request("GET", target.url))

    PinnedHttpTransport(policy, connector=connector).request(
        target,
        headers={"Authorization": "Bearer secret", "Cookie": "session=x", "Accept": "text/html"},
    )

    assert observed_headers[0]["Authorization"] == "Bearer secret"
    assert "Authorization" not in observed_headers[1]
    assert "Cookie" not in observed_headers[1]
    assert observed_headers[1]["Accept"] == "text/html"


def test_redirect_limit_is_enforced() -> None:
    policy = UrlPolicy(MappingResolver())
    target = policy.validate("https://example.org/0")

    def connector(target, address, method, headers, content):
        del address, method, headers, content
        number = int(target.path.rsplit("/", 1)[-1])
        return httpx.Response(
            302,
            headers={"location": f"https://example.org/{number + 1}"},
            request=httpx.Request("GET", target.url),
        )

    with pytest.raises(RedirectLimitError):
        PinnedHttpTransport(policy, connector=connector, max_redirects=2).request(target)
