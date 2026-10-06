from __future__ import annotations

import http.client
import socket
import ssl
from collections.abc import Callable, Mapping
from ipaddress import IPv4Address, IPv6Address
from urllib.parse import urljoin

import httpx

from app.core.errors import RedirectLimitError
from app.scraping.url_policy import UrlPolicy, ValidatedTarget

Connector = Callable[
    [ValidatedTarget, IPv4Address | IPv6Address, str, Mapping[str, str], bytes | None],
    httpx.Response,
]


def _default_connector(
    target: ValidatedTarget,
    address: IPv4Address | IPv6Address,
    method: str,
    headers: Mapping[str, str],
    content: bytes | None,
) -> httpx.Response:
    request_headers = dict(headers)
    request_headers.setdefault("Host", target.hostname)
    connection = http.client.HTTPConnection(str(address), target.port, timeout=20)
    if target.scheme == "https":
        raw_socket = socket.create_connection((str(address), target.port), timeout=20)
        connection.sock = ssl.create_default_context().wrap_socket(
            raw_socket, server_hostname=target.hostname
        )
    connection.request(method, target.request_target, body=content, headers=request_headers)
    response = connection.getresponse()
    body = response.read()
    result = httpx.Response(
        response.status,
        headers=dict(response.getheaders()),
        content=body,
        request=httpx.Request(method, target.url),
    )
    connection.close()
    return result


class PinnedHttpTransport:
    def __init__(
        self,
        policy: UrlPolicy,
        *,
        connector: Connector = _default_connector,
        max_redirects: int = 5,
    ) -> None:
        self._policy = policy
        self._connector = connector
        self._max_redirects = max_redirects

    def request(
        self,
        target: ValidatedTarget,
        *,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
    ) -> httpx.Response:
        current = target
        current_headers = dict(headers or {})
        for redirect_count in range(self._max_redirects + 1):
            response = self._connector(
                current, current.addresses[0], method, current_headers, content
            )
            if response.status_code not in {301, 302, 303, 307, 308}:
                return response
            location = response.headers.get("location")
            if not location:
                return response
            if redirect_count == self._max_redirects:
                raise RedirectLimitError("Limite de redirecionamentos excedido")
            next_target = self._policy.validate(urljoin(current.url, location))
            if next_target.origin != current.origin:
                current_headers = {
                    key: value
                    for key, value in current_headers.items()
                    if key.casefold() not in {"authorization", "cookie", "proxy-authorization"}
                }
            if response.status_code == 303:
                method, content = "GET", None
            current = next_target
        raise RedirectLimitError("Limite de redirecionamentos excedido")
