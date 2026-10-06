from __future__ import annotations

import math
import re
from collections import Counter

from pydantic import BaseModel, ConfigDict

from app.claims.schemas import Claim
from app.evidence.chunking import EvidenceChunk
from app.evidence.source_metadata import SourceType

_TOKEN = re.compile(r"\w+", re.UNICODE)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in _TOKEN.findall(text)]


class RankingCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk: EvidenceChunk
    source_type: SourceType
    is_primary_source: bool
    temporal_match: bool | None


class RankedEvidence(BaseModel):
    chunk: EvidenceChunk
    score: float
    factors: dict[str, float]


class EvidenceRanker:
    def rank(
        self,
        claim: Claim,
        candidates: list[RankingCandidate],
        limit: int = 5,
        *,
        official_required: bool = False,
    ) -> list[RankedEvidence]:
        if not candidates or limit <= 0:
            return []
        query_tokens = _tokens(" ".join([claim.text, *claim.entities]))
        documents = [_tokens(candidate.chunk.text) for candidate in candidates]
        average_length = sum(map(len, documents)) / len(documents) or 1
        document_frequency = Counter(token for document in documents for token in set(document))
        claim_numbers = set(_NUMBER.findall(claim.text))
        claim_year = str(claim.event_date.year) if claim.event_date else None

        ranked: list[RankedEvidence] = []
        for candidate, document_tokens in zip(candidates, documents, strict=True):
            counts = Counter(document_tokens)
            bm25 = 0.0
            for token in set(query_tokens):
                frequency = counts[token]
                if not frequency:
                    continue
                inverse = math.log(
                    1
                    + (len(documents) - document_frequency[token] + 0.5)
                    / (document_frequency[token] + 0.5)
                )
                denominator = frequency + 1.5 * (
                    1 - 0.75 + 0.75 * len(document_tokens) / average_length
                )
                bm25 += inverse * frequency * 2.5 / denominator
            lower_text = candidate.chunk.text.casefold()
            entity_match = 0.5 * sum(
                1 for entity in claim.entities if entity.casefold() in lower_text
            )
            evidence_numbers = set(_NUMBER.findall(candidate.chunk.text))
            number_match = float(len(claim_numbers & evidence_numbers))
            date_match = 1.0 if claim_year and claim_year in candidate.chunk.text else 0.0
            title_tokens = set(_tokens(candidate.chunk.source_title))
            title_match = 0.5 * len(set(query_tokens) & title_tokens)
            temporal = (
                -2.0
                if candidate.temporal_match is False
                else (0.5 if candidate.temporal_match is True else 0.0)
            )
            official = (
                1.0 if official_required and candidate.source_type is SourceType.OFFICIAL else 0.0
            )
            factors = {
                "bm25": bm25,
                "entity_match": entity_match,
                "number_match": number_match,
                "date_match": date_match,
                "title_match": title_match,
                "temporal_match": temporal,
                "official_source": official,
            }
            ranked.append(
                RankedEvidence(
                    chunk=candidate.chunk,
                    score=sum(factors.values()),
                    factors=factors,
                )
            )
        ranked.sort(key=lambda item: (-item.score, item.chunk.evidence_id))
        selected: list[RankedEvidence] = []
        groups: set[str] = set()
        for item in ranked:
            if item.chunk.independence_group in groups:
                continue
            selected.append(item)
            groups.add(item.chunk.independence_group)
            if len(selected) == limit:
                break
        return selected
