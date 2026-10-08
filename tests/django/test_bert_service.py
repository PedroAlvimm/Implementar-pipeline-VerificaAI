"""Auxiliary failures must never rewrite a completed factual run."""

from uuid import uuid4

import pytest

from analyses.models import BERTAnalysis, RunState
from analyses.services.runs import create_analysis, transition_run
from app.risk_analysis.base import BERTResult
from app.risk_analysis.disabled import DisabledRiskAnalyzer

pytestmark = pytest.mark.django_db


def service():
    import importlib.util

    assert importlib.util.find_spec("analyses.services.bert"), "BERT persistence service missing"
    from analyses.services.bert import run_bert

    return run_bert


def completed_run():
    run = create_analysis("text", "Texto factual", None, uuid4())[1]
    transition_run(run.pk, RunState.RUNNING)
    return transition_run(run.pk, RunState.COMPLETED)


class Analyzer:
    def __init__(self, output=None, error=None):
        self.output, self.error = output, error

    def analyze(self, text):
        assert text == "Texto factual"
        if self.error:
            raise self.error
        return self.output


def prediction():
    return BERTResult(
        status="available",
        label="VERDADEIRA",
        score=0.8,
        model_name="fixture",
        model_version="v1",
        message="Auxiliar",
    )


def test_available_prediction_is_persisted_once_and_does_not_change_factual_run():
    run = completed_run()
    before = (run.state, run.finished_at, run.updated_at, run.report)
    row = service()(run.pk, "Texto factual", Analyzer(prediction()))
    assert (row.state, row.label, row.score) == ("AVAILABLE", "VERDADEIRA", 0.8)
    assert (row.model_name, row.model_version) == ("fixture", "v1")
    assert row.started_at <= row.finished_at
    again = service()(run.pk, "Texto factual", Analyzer(error=AssertionError("no rerun")))
    assert again.pk == row.pk
    assert again.state == "AVAILABLE"
    assert BERTAnalysis.objects.filter(run=run).count() == 1
    run.refresh_from_db()
    assert (run.state, run.finished_at, run.updated_at, run.report) == before


@pytest.mark.parametrize(
    "analyzer,state,code",
    [
        (DisabledRiskAnalyzer(), "UNAVAILABLE", None),
        (Analyzer(error=RuntimeError("SECRET")), "ERROR", "BERT_ERROR"),
        (Analyzer(error=TimeoutError("SECRET")), "ERROR", "BERT_TIMEOUT"),
        (Analyzer({"status": "unknown"}), "ERROR", "BERT_INVALID_OUTPUT"),
        (
            Analyzer(prediction().model_copy(update={"score": float("nan")})),
            "ERROR",
            "BERT_INVALID_OUTPUT",
        ),
    ],
)
def test_auxiliary_failures_are_safe_and_never_carry_predictions(analyzer, state, code):
    run = completed_run()
    row = service()(run.pk, "Texto factual", analyzer)
    assert row.state == state
    assert row.error_code == code
    assert row.label is None and row.score is None
    assert "SECRET" not in (row.error_message or "")
    if state == "ERROR":
        assert "auxiliar" in row.error_message
    run.refresh_from_db()
    assert run.state == RunState.COMPLETED


def test_late_result_is_a_timeout_without_creating_a_second_worker(monkeypatch):
    run_bert = service()
    from analyses.services import bert

    ticks = iter([0, 1000])
    monkeypatch.setattr(bert.time, "monotonic", lambda: next(ticks))
    row = run_bert(completed_run().pk, "Texto factual", Analyzer(prediction()))
    assert row.state == "ERROR" and row.error_code == "BERT_TIMEOUT"
    assert row.label is None and row.score is None


def test_auxiliary_service_refuses_to_run_before_factual_completion():
    run = create_analysis("text", "Texto factual", None, uuid4())[1]
    with pytest.raises(ValueError, match="terminal"):
        service()(run.pk, "Texto factual", Analyzer(prediction()))
    assert not BERTAnalysis.objects.filter(run=run).exists()
