from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.claims.schemas import Claim, ClaimPriority, ClaimType
from app.core.enums import AnalysisStatus, ConfidenceLevel, Verdict
from app.fact_checking.aggregation import ClaimResult
from app.fact_checking.judgment import JudgmentEvidence
from app.reports.builder import ReportBuilder, ReportValidationError
from app.reports.schemas import OverallResult
from app.risk_analysis.disabled import DisabledRiskAnalyzer


def claim() -> Claim:
    return Claim(
        id="claim_01",
        text="O município comprou 10 milhões de doses.",
        original_excerpt="O município comprou 10 milhões de doses.",
        claim_type=ClaimType.QUANTITATIVE,
        checkable=True,
        priority=ClaimPriority.HIGH,
        entities=["município", "10 milhões", "doses"],
    )


def evidence() -> JudgmentEvidence:
    return JudgmentEvidence(
        evidence_id="ev_001",
        text="O contrato prevê oito milhões de doses.",
        source_title="Contrato oficial",
        source_url="https://gov.example/contrato",
        source_domain="gov.example",
        published_at=datetime(2026, 1, 15, tzinfo=UTC),
        retrieved_at=datetime(2026, 10, 6, tzinfo=UTC),
        independence_group="grp_primary",
        is_primary_source=True,
        temporal_match=True,
    )


def result(evidence_ids: list[str] | None = None) -> ClaimResult:
    return ClaimResult(
        claim_id="claim_01",
        verdict=Verdict.REFUTED,
        confidence_level=ConfidenceLevel.HIGH,
        evidence_ids=evidence_ids or ["ev_001"],
        reason="O contrato registra oito milhões, não dez milhões.",
        limitations=[],
    )


def test_report_contains_only_stored_evidence_and_exact_risk_copy() -> None:
    report = ReportBuilder().build(
        analysis_id="analysis-1",
        status=AnalysisStatus.COMPLETED,
        original_input="O município comprou 10 milhões de doses.",
        title=None,
        claims=[claim()],
        claim_results=[result()],
        evidence_by_id={"ev_001": evidence()},
        risk=DisabledRiskAnalyzer().analyze("texto"),
        analyzed_at=datetime(2026, 10, 6, tzinfo=UTC),
    )

    assert report.overall_result is OverallResult.CONTAINS_REFUTED_CLAIM
    assert report.risk_message == "Análise linguística: aguardando integração do BERTimbau."
    assert report.claims[0].evidence[0].url == "https://gov.example/contrato"
    assert report.claims[0].evidence[0].published_at.isoformat() == "2026-01-15T00:00:00+00:00"
    assert report.claims[0].evidence[0].retrieved_at.isoformat() == "2026-10-06T00:00:00+00:00"


def test_report_exposes_available_risk_as_auxiliary_not_as_factual_verdict() -> None:
    risk_message = (
        "Análise linguística auxiliar: FALSA (97,00%). "
        "Este resultado não determina a veracidade factual."
    )
    report = ReportBuilder().build(
        analysis_id="analysis-1",
        status=AnalysisStatus.COMPLETED,
        original_input="O município comprou 10 milhões de doses.",
        title=None,
        claims=[claim()],
        claim_results=[result()],
        evidence_by_id={"ev_001": evidence()},
        risk={
            "status": "available",
            "label": "FALSA",
            "score": 0.97,
            "model_name": "bucket",
            "model_version": "version",
            "message": risk_message,
        },
        analyzed_at=datetime(2026, 10, 6, tzinfo=UTC),
    )

    assert report.risk_message == risk_message
    assert report.claims[0].verdict is Verdict.REFUTED


def test_report_rejects_unknown_evidence_url_or_identifier() -> None:
    with pytest.raises(ReportValidationError, match="ev_unknown"):
        ReportBuilder().build(
            analysis_id="analysis-1",
            status=AnalysisStatus.COMPLETED,
            original_input="texto",
            title=None,
            claims=[claim()],
            claim_results=[result(["ev_unknown"])],
            evidence_by_id={"ev_001": evidence()},
            risk=DisabledRiskAnalyzer().analyze("texto"),
            analyzed_at=datetime.now(UTC),
        )


def test_partial_report_exposes_limitations() -> None:
    partial = result()
    partial.limitations.append("claim_02: SEARCH_TIMEOUT")
    report = ReportBuilder().build(
        analysis_id="analysis-1",
        status=AnalysisStatus.COMPLETED_WITH_LIMITATIONS,
        original_input="texto",
        title="Análise parcial",
        claims=[claim()],
        claim_results=[partial],
        evidence_by_id={"ev_001": evidence()},
        risk=DisabledRiskAnalyzer().analyze("texto"),
        analyzed_at=datetime.now(UTC),
    )

    assert report.status is AnalysisStatus.COMPLETED_WITH_LIMITATIONS
    assert "claim_02: SEARCH_TIMEOUT" in report.limitations
