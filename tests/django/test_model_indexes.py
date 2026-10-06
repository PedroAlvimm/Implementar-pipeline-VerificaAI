"""Explicit indexes match the version 1.0 read paths."""

from uuid import uuid4

import pytest
from django.db import connection

from analyses.models import Analysis, AnalysisRun, Claim, Evidence

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "model,index,columns",
    [
        (Analysis, "analysis_created_idx", ["created_at"]),
        (Analysis, "analysis_input_hash_idx", ["input_hash"]),
        (AnalysisRun, "run_analysis_ordinal_idx", ["analysis_id", "ordinal"]),
        (AnalysisRun, "run_state_updated_idx", ["state", "updated_at"]),
        (Claim, "claim_run_position_idx", ["run_id", "position"]),
        (Evidence, "evidence_claim_rank_idx", ["claim_id", "rank"]),
        (Evidence, "evidence_independence_idx", ["run_id", "independence_group"]),
    ],
)
def test_explicit_indexes_exist(model, index, columns):
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, model._meta.db_table)
    assert constraints[index]["index"] is True
    assert constraints[index]["columns"] == columns


def test_sqlite_uses_four_critical_read_paths():
    for number in range(32):
        analysis = Analysis.objects.create(
            input_type="text",
            original_input=f"Afirmação {number}",
            input_hash="a" * 64,
        )
        run = AnalysisRun.objects.create(analysis=analysis, ordinal=1, request_id=uuid4())
        claim = Claim.objects.create(
            run=run,
            claim_key="C1",
            position=1,
            text="Afirmação",
            priority=1,
        )
        Evidence.objects.create(
            run=run,
            claim=claim,
            evidence_key="E1",
            canonical_url="https://example.org",
            domain="example.org",
            excerpt="Trecho",
            rank=1,
            independence_group="example.org",
        )
    queries = [
        (
            AnalysisRun.objects.filter(analysis=analysis).order_by("ordinal"),
            "run_analysis_ordinal_idx",
        ),
        (
            AnalysisRun.objects.filter(state="QUEUED").order_by("updated_at"),
            "run_state_updated_idx",
        ),
        (Claim.objects.filter(run=run).order_by("position"), "claim_run_position_idx"),
        (Evidence.objects.filter(claim=claim).order_by("rank"), "evidence_claim_rank_idx"),
    ]
    for query, index in queries:
        plan = query.explain()
        assert index in plan, plan
        assert "USE TEMP B-TREE" not in plan, plan
