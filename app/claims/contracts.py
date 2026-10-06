from __future__ import annotations

from typing import Protocol

from app.claims.schemas import Claim, QuerySet


class ClaimExtractor(Protocol):
    def extract(self, text: str) -> list[Claim]: ...


class QueryGenerator(Protocol):
    def generate(self, claim: Claim) -> QuerySet: ...
