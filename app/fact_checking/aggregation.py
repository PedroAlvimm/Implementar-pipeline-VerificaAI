from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, ConfigDict

from app.claims.schemas import Claim
from app.core.enums import ConfidenceLevel, Verdict
from app.fact_checking.judgment import EvidenceDecision
from app.reports.schemas import OverallResult


class DecisionSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    independence_group: str
    is_primary_source: bool
    temporal_match: bool | None


class ClaimResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    verdict: Verdict
    confidence_level: ConfidenceLevel
    evidence_ids: list[str]
    reason: str
    limitations: list[str]


def aggregate_claim(
    claim: Claim,
    decisions: list[EvidenceDecision],
    sources: dict[str, DecisionSource],
    *,
    technical_errors: list[str] | None = None,
) -> ClaimResult:
    limitations = list(technical_errors or [])
    groups: dict[str, list[EvidenceDecision]] = defaultdict(list)
    valid_sources: dict[str, DecisionSource] = {}
    for decision in decisions:
        source = sources.get(decision.evidence_id)
        if source is None:
            limitations.append(f"unknown_source:{decision.evidence_id}")
            continue
        if source.temporal_match is False:
            limitations.append(f"temporal_mismatch:{decision.evidence_id}")
            continue
        groups[source.independence_group].append(decision)
        valid_sources[decision.evidence_id] = source

    supporting: list[EvidenceDecision] = []
    refuting: list[EvidenceDecision] = []
    for group_decisions in groups.values():
        labels = {item.label for item in group_decisions if item.label is not Verdict.NEI}
        if labels == {Verdict.SUPPORTED}:
            supporting.append(group_decisions[0])
        elif labels == {Verdict.REFUTED}:
            refuting.append(group_decisions[0])
        elif len(labels) > 1:
            limitations.append("conflicting_copies_same_origin")

    if supporting and refuting:
        chosen = supporting + refuting
        return ClaimResult(
            claim_id=claim.id,
            verdict=Verdict.CONFLICTING,
            confidence_level=ConfidenceLevel.MEDIUM,
            evidence_ids=[item.evidence_id for item in chosen],
            reason="Fontes relevantes e independentes apresentam conclusões incompatíveis.",
            limitations=limitations,
        )
    chosen = refuting or supporting
    if chosen:
        verdict = Verdict.REFUTED if refuting else Verdict.SUPPORTED
        primary = any(valid_sources[item.evidence_id].is_primary_source for item in chosen)
        confidence = (
            ConfidenceLevel.HIGH
            if primary
            else ConfidenceLevel.MEDIUM
            if len(chosen) >= 2
            else ConfidenceLevel.LOW
        )
        action = "contradizem" if verdict is Verdict.REFUTED else "sustentam"
        return ClaimResult(
            claim_id=claim.id,
            verdict=verdict,
            confidence_level=confidence,
            evidence_ids=[item.evidence_id for item in chosen],
            reason=f"As evidências selecionadas {action} diretamente a claim.",
            limitations=limitations,
        )
    return ClaimResult(
        claim_id=claim.id,
        verdict=Verdict.NEI,
        confidence_level=ConfidenceLevel.INSUFFICIENT,
        evidence_ids=[],
        reason="As evidências disponíveis não permitem concluir sobre a claim.",
        limitations=limitations,
    )


def aggregate_analysis(results: list[ClaimResult]) -> OverallResult:
    verdicts = {item.verdict for item in results}
    if Verdict.CONFLICTING in verdicts:
        return OverallResult.CONFLICTING_EVIDENCE
    if Verdict.SUPPORTED in verdicts and Verdict.REFUTED in verdicts:
        return OverallResult.MIXED
    if Verdict.REFUTED in verdicts:
        return OverallResult.CONTAINS_REFUTED_CLAIM
    if results and verdicts == {Verdict.SUPPORTED}:
        return OverallResult.MAIN_CLAIMS_SUPPORTED
    return OverallResult.INSUFFICIENT_EVIDENCE
