from __future__ import annotations

from datetime import date

from app.claims.schemas import Claim, ClaimPriority, ClaimType
from app.evidence.chunking import EvidenceChunk
from app.evidence.ranking import EvidenceRanker, RankingCandidate
from app.evidence.source_metadata import SourceType


def claim() -> Claim:
    return Claim(
        id="claim_01",
        text="O município comprou 10 milhões de doses em janeiro de 2026.",
        original_excerpt="O município comprou 10 milhões de doses em janeiro de 2026.",
        claim_type=ClaimType.QUANTITATIVE,
        checkable=True,
        priority=ClaimPriority.HIGH,
        entities=["município", "10 milhões", "doses"],
        event_date=date(2026, 1, 1),
        temporal_scope="janeiro de 2026",
    )


def candidate(
    identifier: str,
    text: str,
    *,
    title: str = "Documento",
    group: str | None = None,
    source_type: SourceType = SourceType.NEWS,
    temporal_match: bool | None = True,
) -> RankingCandidate:
    chunk = EvidenceChunk(
        evidence_id=identifier,
        document_id=f"doc_{identifier}",
        index=0,
        text=text,
        source_title=title,
        source_url=f"https://source.example/{identifier}",
        source_domain="source.example",
        published_at=None,
        independence_group=group or f"grp_{identifier}",
    )
    return RankingCandidate(
        chunk=chunk,
        source_type=source_type,
        is_primary_source=source_type is SourceType.OFFICIAL,
        temporal_match=temporal_match,
    )


def test_ranking_exposes_bm25_entity_number_date_and_title_factors() -> None:
    candidates = [
        candidate(
            "ev_relevant",
            "Em janeiro de 2026 o município adquiriu 10 milhões de doses.",
            title="Contrato de doses do município",
        ),
        candidate("ev_other", "Pesquisa sobre educação municipal em 2020."),
    ]

    ranked = EvidenceRanker().rank(claim(), candidates)

    assert ranked[0].chunk.evidence_id == "ev_relevant"
    assert ranked[0].factors["bm25"] > ranked[1].factors["bm25"]
    assert ranked[0].factors["entity_match"] > 0
    assert ranked[0].factors["number_match"] > 0
    assert ranked[0].factors["date_match"] > 0
    assert ranked[0].factors["title_match"] > 0
    assert "truth_probability" not in ranked[0].factors


def test_temporal_mismatch_is_penalized() -> None:
    matching = candidate("ev_current", "10 milhões de doses em 2026", temporal_match=True)
    stale = candidate("ev_stale", "10 milhões de doses em 2026", temporal_match=False)

    ranked = EvidenceRanker().rank(claim(), [stale, matching])

    assert ranked[0].chunk.evidence_id == "ev_current"
    assert ranked[1].factors["temporal_match"] < 0


def test_official_source_boost_requires_explicit_official_need() -> None:
    official = candidate(
        "ev_official",
        "Documento sobre vacinação.",
        source_type=SourceType.OFFICIAL,
    )
    news = candidate("ev_news", "Documento sobre vacinação.")

    without_requirement = EvidenceRanker().rank(claim(), [official, news])
    with_requirement = EvidenceRanker().rank(claim(), [official, news], official_required=True)

    assert without_requirement[0].factors["official_source"] == 0
    assert with_requirement[0].chunk.evidence_id == "ev_official"
    assert with_requirement[0].factors["official_source"] > 0


def test_ranking_is_deterministic_diverse_and_limited_to_five() -> None:
    candidates = [
        candidate(
            f"ev_{index}",
            "município doses contrato",
            group="grp_copy" if index < 3 else None,
        )
        for index in range(8)
    ]

    first = EvidenceRanker().rank(claim(), candidates, limit=5)
    second = EvidenceRanker().rank(claim(), candidates, limit=5)

    assert [item.chunk.evidence_id for item in first] == [item.chunk.evidence_id for item in second]
    assert len(first) == 5
    assert len({item.chunk.independence_group for item in first}) == 5
