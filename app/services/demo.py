from __future__ import annotations

from datetime import UTC, datetime

from app.claims.schemas import (
    Claim,
    ClaimPriority,
    ClaimType,
    ClaimValidationResult,
    QuerySet,
)
from app.core.enums import Verdict
from app.evidence.chunking import EvidenceDocument
from app.fact_checking.judgment import EvidenceDecision
from app.search.contracts import SearchResult


class DemoServices:
    """Deterministic fictional provider set for local demonstrations."""

    def extract(self, text: str) -> ClaimValidationResult:
        claim = Claim(
            id="claim_demo",
            text=text,
            original_excerpt=text,
            claim_type=ClaimType.OTHER,
            checkable=True,
            priority=ClaimPriority.HIGH,
            entities=["Município Alfa"],
        )
        return ClaimValidationResult(accepted=[claim], rejected=[])

    def generate(self, claim: Claim) -> QuerySet:
        return QuerySet(
            claim_id=claim.id,
            queries=[f"demo oficial {claim.text}", f"demo independente {claim.text}"],
        )

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        count = 2 if "diverg" in query.casefold() else 1
        return [
            SearchResult(
                title=f"Fonte fictícia {index}",
                url=f"https://demo{index}.example/evidencia",
                snippet="Resultado fictício para demonstração local.",
                domain=f"demo{index}.example",
                published_at=datetime(2024, 1, index, tzinfo=UTC),
                query=query,
                rank=index,
            )
            for index in range(1, count + 1)
        ][:limit]

    def load(self, result: SearchResult) -> EvidenceDocument:
        query = result.query.casefold()
        if "universidade" in query:
            text = "A prefeitura publicou apenas o calendário escolar de 2026."
        elif "diverg" in query and result.domain.startswith("demo2"):
            text = "O relatório fictício registra somente 8 ambulâncias."
        else:
            text = (
                "O contrato fictício de 2024 confirma a compra de "
                "10 ambulâncias pelo Município Alfa."
            )
        return EvidenceDocument(
            id=f"doc_{result.domain}",
            text=text,
            title=result.title,
            url=result.url,
            domain=result.domain,
            published_at=result.published_at,
            independence_group=f"group_{result.domain}",
        )

    def judge(self, claim_id: str, claim_text: str, evidence) -> EvidenceDecision:
        claim_lower = claim_text.casefold()
        evidence_lower = evidence.text.casefold()
        if "universidade" in claim_lower:
            label = Verdict.NEI
        elif "20 ambulâncias" in claim_lower or "somente 8" in evidence_lower:
            label = Verdict.REFUTED
        else:
            label = Verdict.SUPPORTED
        return EvidenceDecision(
            claim_id=claim_id,
            evidence_id=evidence.evidence_id,
            label=label,
            reason="Decisão produzida pelo cenário fictício local.",
            quoted_excerpt="" if label is Verdict.NEI else evidence.text,
            limitations=["demo_ficticio"],
        )
