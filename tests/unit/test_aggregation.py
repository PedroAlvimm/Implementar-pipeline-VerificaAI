from __future__ import annotations

from app.claims.schemas import Claim, ClaimPriority, ClaimType
from app.core.enums import ConfidenceLevel, Verdict
from app.fact_checking.aggregation import DecisionSource, aggregate_analysis, aggregate_claim
from app.fact_checking.judgment import EvidenceDecision
from app.reports.schemas import OverallResult


def claim(identifier: str = "claim_01") -> Claim:
    return Claim(
        id=identifier,
        text="O município comprou 10 milhões de doses.",
        original_excerpt="O município comprou 10 milhões de doses.",
        claim_type=ClaimType.QUANTITATIVE,
        checkable=True,
        priority=ClaimPriority.HIGH,
        entities=["município", "10 milhões", "doses"],
    )


def decision(evidence_id: str, label: Verdict) -> EvidenceDecision:
    return EvidenceDecision(
        claim_id="claim_01",
        evidence_id=evidence_id,
        label=label,
        reason="Decisão baseada no documento.",
        quoted_excerpt="Trecho literal.",
        limitations=[],
    )


def source(
    evidence_id: str,
    group: str,
    *,
    primary: bool = False,
    temporal: bool | None = True,
) -> DecisionSource:
    return DecisionSource(
        evidence_id=evidence_id,
        independence_group=group,
        is_primary_source=primary,
        temporal_match=temporal,
    )


def test_direct_primary_support_and_refutation_decide_with_high_confidence() -> None:
    supported = aggregate_claim(
        claim(), [decision("ev_1", Verdict.SUPPORTED)], {"ev_1": source("ev_1", "g1", primary=True)}
    )
    refuted = aggregate_claim(
        claim(), [decision("ev_2", Verdict.REFUTED)], {"ev_2": source("ev_2", "g2", primary=True)}
    )

    assert (supported.verdict, supported.confidence_level) == (
        Verdict.SUPPORTED,
        ConfidenceLevel.HIGH,
    )
    assert (refuted.verdict, refuted.confidence_level) == (Verdict.REFUTED, ConfidenceLevel.HIGH)


def test_no_or_only_unrelated_evidence_is_nei() -> None:
    empty = aggregate_claim(claim(), [], {})
    unrelated = aggregate_claim(
        claim(), [decision("ev_1", Verdict.NEI)], {"ev_1": source("ev_1", "g1")}
    )

    assert empty.verdict is Verdict.NEI
    assert unrelated.verdict is Verdict.NEI
    assert empty.confidence_level is ConfidenceLevel.INSUFFICIENT


def test_independent_disagreement_is_conflicting() -> None:
    result = aggregate_claim(
        claim(),
        [decision("ev_1", Verdict.SUPPORTED), decision("ev_2", Verdict.REFUTED)],
        {"ev_1": source("ev_1", "g1"), "ev_2": source("ev_2", "g2")},
    )

    assert result.verdict is Verdict.CONFLICTING


def test_copied_disagreement_and_stale_evidence_do_not_decide() -> None:
    copied = aggregate_claim(
        claim(),
        [decision("ev_1", Verdict.SUPPORTED), decision("ev_2", Verdict.REFUTED)],
        {"ev_1": source("ev_1", "copy"), "ev_2": source("ev_2", "copy")},
    )
    stale = aggregate_claim(
        claim(),
        [decision("ev_3", Verdict.REFUTED)],
        {"ev_3": source("ev_3", "old", primary=True, temporal=False)},
    )

    assert copied.verdict is Verdict.NEI
    assert stale.verdict is Verdict.NEI


def test_technical_error_never_becomes_refuted() -> None:
    result = aggregate_claim(claim(), [], {}, technical_errors=["SEARCH_TIMEOUT"])

    assert result.verdict is Verdict.NEI
    assert "SEARCH_TIMEOUT" in result.limitations


def test_overall_result_uses_deterministic_statuses() -> None:
    supported = aggregate_claim(
        claim(), [decision("ev_1", Verdict.SUPPORTED)], {"ev_1": source("ev_1", "g1", primary=True)}
    )
    refuted = aggregate_claim(
        claim(), [decision("ev_2", Verdict.REFUTED)], {"ev_2": source("ev_2", "g2", primary=True)}
    )

    assert aggregate_analysis([refuted]) is OverallResult.CONTAINS_REFUTED_CLAIM
    assert aggregate_analysis([supported]) is OverallResult.MAIN_CLAIMS_SUPPORTED
    assert aggregate_analysis([supported, refuted]) is OverallResult.MIXED
