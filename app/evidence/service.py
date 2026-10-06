from __future__ import annotations

from app.claims.schemas import Claim
from app.evidence.ranking import EvidenceRanker, RankedEvidence, RankingCandidate


class EvidenceService:
    def __init__(self, ranker: EvidenceRanker | None = None) -> None:
        self._ranker = ranker or EvidenceRanker()

    def select(
        self,
        claim: Claim,
        candidates: list[RankingCandidate],
        *,
        official_required: bool = False,
    ) -> list[RankedEvidence]:
        return self._ranker.rank(claim, candidates, limit=5, official_required=official_required)
