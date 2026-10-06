from __future__ import annotations

import socket
from collections.abc import Callable, Sequence
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Any

from app.core.errors import UnsafeUrlError

IPAddress = IPv4Address | IPv6Address
Lookup = Callable[[str, int], Sequence[tuple[Any, Any, Any, Any, tuple[Any, ...]]]]


def _system_lookup(hostname: str, port: int):
    return socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)


def ensure_public(address: IPAddress) -> None:
    if (
        not address.is_global
        or address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise UnsafeUrlError(f"Endereço não público bloqueado: {address}")


class DnsResolver:
    def __init__(self, lookup: Lookup = _system_lookup) -> None:
        self._lookup = lookup

    def resolve_public(self, hostname: str) -> tuple[IPAddress, ...]:
        try:
            answers = self._lookup(hostname, 0)
        except OSError as exc:
            raise UnsafeUrlError(f"Falha ao resolver o domínio: {hostname}") from exc
        addresses: list[IPAddress] = []
        for answer in answers:
            address = ip_address(answer[4][0])
            ensure_public(address)
            if address not in addresses:
                addresses.append(address)
        if not addresses:
            raise UnsafeUrlError(f"Domínio sem endereço utilizável: {hostname}")
        return tuple(addresses)
