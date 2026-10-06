from __future__ import annotations

from datetime import date

from app.claims.schemas import Claim, ClaimPriority, ClaimType
from app.claims.validation import validate_claims


def claim(identifier: str, excerpt: str, text: str | None = None) -> Claim:
    return Claim(
        id=identifier,
        text=text or excerpt,
        original_excerpt=excerpt,
        claim_type=ClaimType.QUANTITATIVE,
        checkable=True,
        priority=ClaimPriority.HIGH,
        entities=["Município", "10 milhões", "doses"],
        event_date=date(2026, 1, 1),
        temporal_scope="janeiro de 2026",
    )


def test_valid_claim_preserves_excerpt_numbers_negation_and_temporal_fields() -> None:
    source = "O município não comprou 10 milhões de doses em janeiro de 2026."

    result = validate_claims(source, [claim("claim_01", source)])

    assert result.accepted[0].original_excerpt == source
    assert "não" in result.accepted[0].text
    assert "10 milhões" in result.accepted[0].text
    assert result.accepted[0].event_date == date(2026, 1, 1)
    assert result.rejected == []


def test_invented_excerpt_is_rejected_with_auditable_reason() -> None:
    result = validate_claims(
        "O texto original não contém isso.",
        [claim("claim_01", "Trecho inventado")],
    )

    assert result.accepted == []
    assert result.rejected[0].claim_id == "claim_01"
    assert result.rejected[0].reason == "original_excerpt_not_found"


def test_only_first_three_valid_claims_are_accepted() -> None:
    source = "A. B. C. D."
    candidates = [claim(f"claim_{index:02d}", letter) for index, letter in enumerate("ABCD", 1)]

    result = validate_claims(source, candidates)

    assert [item.id for item in result.accepted] == ["claim_01", "claim_02", "claim_03"]
    assert result.rejected[-1].reason == "claim_limit_exceeded"
