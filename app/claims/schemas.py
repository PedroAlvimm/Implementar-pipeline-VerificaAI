from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClaimType(StrEnum):
    QUANTITATIVE = "quantitative"
    EVENT = "event"
    ATTRIBUTION = "attribution"
    TEMPORAL = "temporal"
    OTHER = "other"


class ClaimPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Claim(StrictModel):
    id: str = Field(pattern=r"^claim_[A-Za-z0-9_-]+$")
    text: str = Field(min_length=1)
    original_excerpt: str = Field(min_length=1)
    claim_type: ClaimType
    checkable: bool
    priority: ClaimPriority
    entities: list[str]
    event_date: date | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    temporal_scope: str | None = None


class ClaimBatch(StrictModel):
    claims: list[Claim]


class QuerySet(StrictModel):
    claim_id: str
    queries: list[str] = Field(min_length=2, max_length=4)


class RejectedClaim(StrictModel):
    claim_id: str
    reason: str


class ClaimValidationResult(StrictModel):
    accepted: list[Claim]
    rejected: list[RejectedClaim]
