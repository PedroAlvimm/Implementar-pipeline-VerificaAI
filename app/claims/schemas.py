from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# Provider outputs are bounded before they can become trace, rows or reports.
ClaimId = Annotated[str, Field(min_length=1, max_length=128)]
ShortText = Annotated[str, Field(min_length=1, max_length=512)]
EntityText = Annotated[str, Field(min_length=1, max_length=256)]


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
    id: ClaimId = Field(pattern=r"^claim_[A-Za-z0-9_-]+$")
    text: str = Field(min_length=1, max_length=4096)
    original_excerpt: str = Field(min_length=1, max_length=8192)
    claim_type: ClaimType
    checkable: bool
    priority: ClaimPriority
    entities: list[EntityText] = Field(max_length=20)
    event_date: date | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    temporal_scope: ShortText | None = None


class ClaimBatch(StrictModel):
    claims: list[Claim] = Field(max_length=32)


class QuerySet(StrictModel):
    claim_id: ClaimId
    queries: list[ShortText] = Field(min_length=2, max_length=4)


class RejectedClaim(StrictModel):
    claim_id: ClaimId
    reason: ShortText


class ClaimValidationResult(StrictModel):
    accepted: list[Claim] = Field(max_length=32)
    rejected: list[RejectedClaim] = Field(max_length=32)
