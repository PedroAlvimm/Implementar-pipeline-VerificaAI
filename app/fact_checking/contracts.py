from __future__ import annotations

from typing import Protocol

from app.fact_checking.judgment import EvidenceDecision, JudgmentEvidence


class EvidenceJudge(Protocol):
    def judge(
        self, claim_id: str, claim_text: str, evidence: JudgmentEvidence
    ) -> EvidenceDecision: ...
