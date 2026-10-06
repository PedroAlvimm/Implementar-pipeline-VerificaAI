from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.claims.schemas import QuerySet


def test_query_set_keeps_two_to_four_queries_and_official_source_query() -> None:
    result = QuerySet(
        claim_id="claim_01",
        queries=[
            "município compra 10 milhões doses janeiro 2026",
            "site:gov.br contrato aquisição doses município 2026",
        ],
    )

    assert len(result.queries) == 2
    assert any("site:gov.br" in query for query in result.queries)


@pytest.mark.parametrize("queries", [["uma"], ["1", "2", "3", "4", "5"]])
def test_query_set_rejects_out_of_range_query_counts(queries: list[str]) -> None:
    with pytest.raises(ValidationError):
        QuerySet(claim_id="claim_01", queries=queries)
