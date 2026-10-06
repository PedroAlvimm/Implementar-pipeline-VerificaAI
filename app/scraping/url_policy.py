from __future__ import annotations

import re
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, ip_address
from urllib.parse import SplitResult, urlsplit, urlunsplit

from app.core.errors import UnsafeUrlError
from app.scraping.dns import DnsResolver, IPAddress, ensure_public

_NUMERIC_HOST = re.compile(r"^(?:0x[0-9a-f]+|[0-9x.]+)$", re.IGNORECASE)


@dataclass(frozen=True)
class ValidatedTarget:
    url: str
    scheme: str
    hostname: str
    port: int
    path: str
    query: str
    addresses: tuple[IPAddress, ...]

    @property
    def origin(self) -> tuple[str, str, int]:
        return self.scheme, self.hostname, self.port

    @property
    def request_target(self) -> str:
        return self.path + (f"?{self.query}" if self.query else "")


class UrlPolicy:
    def __init__(self, resolver: DnsResolver | object) -> None:
        self._resolver = resolver

    def validate(self, url: str) -> ValidatedTarget:
        try:
            parsed = urlsplit(url.strip())
            port = parsed.port
        except ValueError as exc:
            raise UnsafeUrlError("URL malformada") from exc
        scheme = parsed.scheme.casefold()
        if scheme not in {"http", "https"} or not parsed.hostname:
            raise UnsafeUrlError("Somente URLs HTTP e HTTPS são permitidas")
        if parsed.username is not None or parsed.password is not None:
            raise UnsafeUrlError("Credenciais embutidas na URL não são permitidas")
        hostname = parsed.hostname.rstrip(".").casefold()
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise UnsafeUrlError("Localhost não é permitido")
        if _NUMERIC_HOST.fullmatch(hostname):
            try:
                literal = ip_address(hostname)
            except ValueError as exc:
                raise UnsafeUrlError("Representação numérica ambígua de IP") from exc
            ensure_public(literal)
            addresses: tuple[IPv4Address | IPv6Address, ...] = (literal,)
        else:
            try:
                literal = ip_address(hostname)
            except ValueError:
                ascii_hostname = hostname.encode("idna").decode("ascii")
                addresses = self._resolver.resolve_public(ascii_hostname)
                hostname = ascii_hostname
            else:
                ensure_public(literal)
                addresses = (literal,)
        effective_port = port or (443 if scheme == "https" else 80)
        if effective_port not in {80, 443}:
            raise UnsafeUrlError("Porta não permitida")
        path = parsed.path or "/"
        netloc = hostname
        if effective_port != (443 if scheme == "https" else 80):
            netloc = f"{hostname}:{effective_port}"
        normalized = urlunsplit(SplitResult(scheme, netloc, path, parsed.query, ""))
        return ValidatedTarget(
            url=normalized,
            scheme=scheme,
            hostname=hostname,
            port=effective_port,
            path=path,
            query=parsed.query,
            addresses=addresses,
        )
