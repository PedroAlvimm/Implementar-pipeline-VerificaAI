from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from app.scraping.extraction import CollectedPage


class BlockReason(StrEnum):
    PAYWALL = "PAYWALL"
    LOGIN = "LOGIN"
    CAPTCHA = "CAPTCHA"


class BlockDetector:
    _PATTERNS: ClassVar[dict[BlockReason, tuple[str, ...]]] = {
        BlockReason.PAYWALL: (
            "assine para continuar",
            "conteúdo exclusivo para assinantes",
            "subscribe to continue",
        ),
        BlockReason.LOGIN: ("faça login para continuar", "sign in to continue"),
        BlockReason.CAPTCHA: ("captcha", "verifique que você é humano"),
    }

    def detect(self, page: CollectedPage) -> BlockReason | None:
        normalized = page.html.casefold()
        for reason, patterns in self._PATTERNS.items():
            if any(pattern in normalized for pattern in patterns):
                return reason
        return None
