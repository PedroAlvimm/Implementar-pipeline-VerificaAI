from __future__ import annotations

from datetime import datetime

from app.claims.schemas import Claim
from app.core.enums import AnalysisStatus, Verdict
from app.fact_checking.aggregation import ClaimResult, aggregate_analysis
from app.fact_checking.judgment import JudgmentEvidence
from app.reports.schemas import (
    AnalysisReport,
    ClaimReport,
    EvidenceCitation,
)
from app.risk_analysis.base import RiskAnalysisResult


class ReportValidationError(ValueError):
    pass


class ReportBuilder:
    def build(
        self,
        *,
        analysis_id: str,
        status: AnalysisStatus,
        original_input: str,
        title: str | None,
        claims: list[Claim],
        claim_results: list[ClaimResult],
        evidence_by_id: dict[str, JudgmentEvidence],
        risk: RiskAnalysisResult,
        analyzed_at: datetime,
    ) -> AnalysisReport:
        claims_by_id = {claim.id: claim for claim in claims}
        report_claims: list[ClaimReport] = []
        all_limitations: list[str] = []
        for result in claim_results:
            claim = claims_by_id.get(result.claim_id)
            if claim is None:
                raise ReportValidationError(f"Claim desconhecida: {result.claim_id}")
            citations: list[EvidenceCitation] = []
            for evidence_id in result.evidence_ids:
                evidence = evidence_by_id.get(evidence_id)
                if evidence is None:
                    raise ReportValidationError(f"Evidência desconhecida: {evidence_id}")
                citations.append(
                    EvidenceCitation(
                        evidence_id=evidence.evidence_id,
                        title=evidence.source_title,
                        url=evidence.source_url,
                        excerpt=evidence.text,
                        published_at=evidence.published_at,
                        retrieved_at=evidence.retrieved_at,
                    )
                )
            factual_verdicts = {Verdict.SUPPORTED, Verdict.REFUTED, Verdict.CONFLICTING}
            if result.verdict in factual_verdicts and not citations:
                raise ReportValidationError(f"Conclusão factual sem evidência: {result.claim_id}")
            all_limitations.extend(result.limitations)
            report_claims.append(
                ClaimReport(
                    claim_id=claim.id,
                    text=claim.text,
                    verdict=result.verdict,
                    confidence_level=result.confidence_level,
                    reason=result.reason,
                    evidence=citations,
                    limitations=result.limitations,
                )
            )
        return AnalysisReport(
            analysis_id=analysis_id,
            status=status,
            original_input=original_input,
            title=title,
            risk_status=dict(risk),
            risk_message=(
                "Análise linguística: aguardando integração do BERTimbau."
                if risk["status"] == "modelo_indisponivel"
                else risk["message"]
            ),
            overall_result=aggregate_analysis(claim_results),
            claims=report_claims,
            limitations=list(dict.fromkeys(all_limitations)),
            analyzed_at=analyzed_at,
        )
