"""Database constraints for the five version 1.0 models."""

from datetime import timedelta
from math import inf, nan
from uuid import UUID, uuid4

import pytest
from django.apps import apps
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from analyses.models import Analysis, AnalysisRun, BERTAnalysis, Claim, Evidence, RunState

pytestmark = pytest.mark.django_db


def make_rows():
    analysis = Analysis.objects.create(
        input_type="text", original_input="Uma afirmação verificável.", input_hash="a" * 64
    )
    run = AnalysisRun.objects.create(analysis=analysis, ordinal=1, request_id=uuid4())
    claim = Claim.objects.create(
        run=run, claim_key="C1", position=1, text="Uma afirmação.", priority=1
    )
    evidence = Evidence.objects.create(
        run=run,
        claim=claim,
        evidence_key="E1",
        canonical_url="https://example.org",
        domain="example.org",
        excerpt="Um trecho verificável.",
        rank=1,
    )
    bert = BERTAnalysis.objects.create(run=run)
    return analysis, run, claim, evidence, bert


def test_only_simplified_models_are_registered():
    assert {model.__name__ for model in apps.get_app_config("analyses").get_models()} == {
        "Analysis",
        "AnalysisRun",
        "Claim",
        "Evidence",
        "BERTAnalysis",
    }


def test_public_identifiers_are_uuids():
    assert all(isinstance(row.pk, UUID) for row in make_rows())


def test_run_states_are_exactly_supported_lifecycle():
    assert set(RunState.values) == {
        "QUEUED",
        "RUNNING",
        "COMPLETED",
        "COMPLETED_WITH_LIMITATIONS",
        "FAILED",
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("input_type", "pdf"),
        ("original_input", ""),
        ("original_input", None),
        ("input_hash", ""),
        ("input_hash", "a" * 63),
        ("input_hash", "a" * 65),
    ],
)
def test_invalid_analysis_values_fail_at_database(field, value):
    analysis, *_ = make_rows()
    with pytest.raises(IntegrityError), transaction.atomic():
        Analysis.objects.filter(pk=analysis.pk).update(**{field: value})


def test_idempotency_key_optional_and_unique_when_present():
    first, *_ = make_rows()
    second = Analysis.objects.create(
        input_type="text", original_input="Outra frase.", input_hash="b" * 64
    )
    assert first.idempotency_key is None and second.idempotency_key is None
    first.idempotency_key = "same-key"
    first.save(update_fields=["idempotency_key"])
    with pytest.raises(IntegrityError), transaction.atomic():
        Analysis.objects.filter(pk=second.pk).update(idempotency_key="same-key")


@pytest.mark.parametrize("state", ["PENDING", "INTERRUPTED", "INVALID"])
def test_unsupported_run_states_fail_at_database(state):
    _, run, *_ = make_rows()
    with pytest.raises(IntegrityError), transaction.atomic():
        AnalysisRun.objects.filter(pk=run.pk).update(state=state)


@pytest.mark.parametrize("ordinal", [0, -1])
def test_run_ordinal_positive(ordinal):
    _, run, *_ = make_rows()
    with pytest.raises(IntegrityError), transaction.atomic():
        AnalysisRun.objects.filter(pk=run.pk).update(ordinal=ordinal)


def test_run_ordinal_unique_per_analysis():
    analysis, run, *_ = make_rows()
    AnalysisRun.objects.filter(pk=run.pk).update(state="COMPLETED")
    with pytest.raises(IntegrityError), transaction.atomic():
        AnalysisRun.objects.create(analysis=analysis, ordinal=1, request_id=uuid4())


@pytest.mark.parametrize("state", ["QUEUED", "RUNNING"])
def test_only_one_active_run_per_analysis(state):
    analysis, *_ = make_rows()
    with pytest.raises(IntegrityError), transaction.atomic():
        AnalysisRun.objects.create(analysis=analysis, ordinal=2, state=state, request_id=uuid4())


def test_terminal_run_allows_new_queued_run():
    analysis, run, *_ = make_rows()
    AnalysisRun.objects.filter(pk=run.pk).update(state="FAILED")
    newer = AnalysisRun.objects.create(analysis=analysis, ordinal=2, request_id=uuid4())
    assert newer.state == "QUEUED"


@pytest.mark.parametrize("model_index", [1, 4])
def test_timestamps_cannot_finish_before_start(model_index):
    row = make_rows()[model_index]
    now = timezone.now()
    with pytest.raises(IntegrityError), transaction.atomic():
        type(row).objects.filter(pk=row.pk).update(
            started_at=now, finished_at=now - timedelta(seconds=1)
        )


def test_claim_and_evidence_keys_unique_within_run():
    _, run, claim, evidence, _ = make_rows()
    with pytest.raises(IntegrityError), transaction.atomic():
        Claim.objects.create(run=run, claim_key=claim.claim_key, position=2, text="Outra")
    with pytest.raises(IntegrityError), transaction.atomic():
        Evidence.objects.create(
            run=run,
            claim=claim,
            evidence_key=evidence.evidence_key,
            canonical_url="https://other.org",
            domain="other.org",
            excerpt="Outro",
            rank=2,
        )


@pytest.mark.parametrize("score", [-0.1, 1.1, inf, -inf, nan, None])
def test_available_bert_requires_finite_unit_score(score):
    *_, bert = make_rows()
    with pytest.raises(IntegrityError), transaction.atomic():
        BERTAnalysis.objects.filter(pk=bert.pk).update(
            state="AVAILABLE",
            label="FALSA",
            score=score,
            model_name="bertimbau",
            model_version="v1",
        )


@pytest.mark.parametrize("label,score", [("FALSA", 0), ("VERDADEIRA", 1)])
def test_available_bert_accepts_boundary_scores(label, score):
    *_, bert = make_rows()
    BERTAnalysis.objects.filter(pk=bert.pk).update(
        state="AVAILABLE",
        label=label,
        score=score,
        model_name="bertimbau",
        model_version="v1",
    )
    bert.refresh_from_db()
    assert (bert.label, bert.score) == (label, score)


@pytest.mark.parametrize(
    "changes",
    [
        {"label": None},
        {"model_name": ""},
        {"model_version": ""},
        {"state": "UNAVAILABLE", "label": "FALSA", "score": 0.5},
    ],
)
def test_bert_result_must_match_state(changes):
    *_, bert = make_rows()
    values = {
        "state": "AVAILABLE",
        "label": "FALSA",
        "score": 0.5,
        "model_name": "bertimbau",
        "model_version": "v1",
        **changes,
    }
    with pytest.raises(IntegrityError), transaction.atomic():
        BERTAnalysis.objects.filter(pk=bert.pk).update(**values)


@pytest.mark.parametrize("model_index", [0, 1, 2])
def test_audit_parents_protected(model_index):
    row = make_rows()[model_index]
    with pytest.raises(ProtectedError):
        row.delete()
