from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    url: str
    snippet: str
    domain: str
    published_at: datetime | None
    query: str
    rank: int


class SearchProvider(Protocol):
    def search(self, query: str, limit: int = 10) -> list[SearchResult]: ...
