from __future__ import annotations

import socket

import pytest


@pytest.fixture(autouse=True)
def block_unmocked_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_connect(_socket: socket.socket, address: object) -> None:
        raise AssertionError(f"A suíte tentou acessar a rede sem mock: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)

