from __future__ import annotations

from ipaddress import ip_address

import pytest

from app.core.errors import UnsafeUrlError
from app.scraping.dns import DnsResolver
from app.scraping.url_policy import UrlPolicy


class StubResolver:
    def __init__(self, *addresses: str) -> None:
        self.addresses = tuple(ip_address(value) for value in addresses)

    def resolve_public(self, hostname: str):
        del hostname
        return self.addresses


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/news",
        "http://user:pass@example.org/news",
        "file:///etc/passwd",
        "http://example.org:22/news",
        "http://2130706433/news",
        "http://0x7f000001/news",
        "http://0177.0.0.1/news",
    ],
)
def test_url_policy_rejects_unsafe_url_forms(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        UrlPolicy(StubResolver("93.184.216.34")).validate(url)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.1.1",
        "0.0.0.0",
        "224.0.0.1",
        "192.0.2.1",
        "::1",
        "fc00::1",
        "fe80::1",
        "2001:db8::1",
    ],
)
def test_dns_resolver_rejects_every_non_public_address(address: str) -> None:
    resolver = DnsResolver(lookup=lambda _host, _port: [(None, None, None, None, (address, 0))])

    with pytest.raises(UnsafeUrlError, match="não público"):
        resolver.resolve_public("example.org")


def test_dns_resolver_rejects_mixed_public_and_private_answers() -> None:
    answers = [
        (None, None, None, None, ("93.184.216.34", 0)),
        (None, None, None, None, ("10.0.0.7", 0)),
    ]

    with pytest.raises(UnsafeUrlError):
        DnsResolver(lookup=lambda _host, _port: answers).resolve_public("example.org")


def test_url_policy_returns_normalized_target_and_all_pinned_addresses() -> None:
    target = UrlPolicy(StubResolver("93.184.216.34", "2606:2800:220:1::1")).validate(
        "HTTPS://Example.Org/noticia?q=1#fragment"
    )

    assert target.url == "https://example.org/noticia?q=1"
    assert target.hostname == "example.org"
    assert target.port == 443
    assert tuple(str(value) for value in target.addresses) == (
        "93.184.216.34",
        "2606:2800:220:1::1",
    )
