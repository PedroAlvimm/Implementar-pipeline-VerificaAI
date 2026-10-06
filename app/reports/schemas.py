from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.core.enums import AnalysisStatus, ConfidenceLevel, Verdict


class OverallResult(StrEnum):
    CONTAINS_REFUTED_CLAIM = "CONTAINS_REFUTED_CLAIM"
    MAIN_CLAIMS_SUPPORTED = "MAIN_CLAIMS_SUPPORTED"
    MIXED = "MIXED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"


class EvidenceCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    title: str
    url: str
    excerpt: str
    published_at: datetime | None
    retrieved_at: datetime


class ClaimReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    text: str
    verdict: Verdict
    confidence_level: ConfidenceLevel
    reason: str
    evidence: list[EvidenceCitation]
    limitations: list[str]


class AnalysisReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: str
    status: AnalysisStatus
    original_input: str
    title: str | None
    risk_status: dict[str, object]
    risk_message: str
    overall_result: OverallResult
    claims: list[ClaimReport]
    limitations: list[str]
    analyzed_at: datetime
