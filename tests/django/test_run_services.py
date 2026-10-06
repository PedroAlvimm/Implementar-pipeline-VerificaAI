"""Run creation and state changes preserve audit history."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest

from analyses.models import Analysis, AnalysisRun, RunState

pytestmark = pytest.mark.django_db


def services():
    from analyses.services import runs

    return runs


def test_create_analysis_starts_queued_run_with_input_hash():
    analysis, run, created = services().create_analysis("text", "  Uma afirmação.  ", None, uuid4())
    assert created is True
    assert analysis.original_input == "  Uma afirmação.  "
    assert len(analysis.input_hash) == 64
    assert run.analysis_id == analysis.pk
    assert (run.ordinal, run.state) == (1, RunState.QUEUED)


def test_same_idempotency_key_and_hash_returns_original_pair():
    key = "request-1"
    first = services().create_analysis("text", "  Uma afirmação.  ", key, uuid4())
    second = services().create_analysis("text", "Uma afirmação.", key, uuid4())
    assert first[2] is True and second[2] is False
    assert (first[0].pk, first[1].pk) == (second[0].pk, second[1].pk)
    assert Analysis.objects.count() == AnalysisRun.objects.count() == 1


def test_idempotency_key_reuse_with_different_input_conflicts():
    runs = services()
    runs.create_analysis("text", "Uma afirmação.", "request-1", uuid4())
    with pytest.raises(runs.RunConflictError):
        runs.create_analysis("text", "Outra afirmação.", "request-1", uuid4())


@pytest.mark.django_db(transaction=True)
def test_concurrent_same_key_returns_one_analysis_and_first_run():
    runs = services()
    barrier = Barrier(2)

    def attempt():
        barrier.wait(timeout=5)
        return runs.create_analysis("text", "Uma afirmação.", "shared-key", uuid4())

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _number: attempt(), range(2)))

    assert sorted(result[2] for result in results) == [False, True]
    assert len({result[0].pk for result in results}) == 1
    assert len({result[1].pk for result in results}) == 1
    assert results[0][1].ordinal == results[1][1].ordinal == 1
    assert Analysis.objects.count() == AnalysisRun.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_same_key_with_different_content_conflicts():
    runs = services()
    barrier = Barrier(2)

    def attempt(content):
        barrier.wait(timeout=5)
        try:
            return runs.create_analysis("text", content, "shared-key", uuid4())
        except runs.RunConflictError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ("Uma afirmação.", "Outra afirmação.")))

    assert sum(result is None for result in results) == 1
    assert Analysis.objects.count() == AnalysisRun.objects.count() == 1


@pytest.mark.parametrize("input_type,content", [("pdf", "Texto"), ("text", "   ")])
def test_invalid_input_does_not_create_rows(input_type, content):
    with pytest.raises(ValueError):
        services().create_analysis(input_type, content, None, uuid4())
    assert Analysis.objects.count() == 0


def test_rerun_requires_terminal_predecessor_and_increments_ordinal():
    runs = services()
    analysis, first, _ = runs.create_analysis("text", "Uma afirmação.", None, uuid4())
    with pytest.raises(runs.RunConflictError):
        runs.create_rerun(analysis.pk, uuid4())
    runs.transition_run(first.pk, RunState.RUNNING)
    runs.transition_run(first.pk, RunState.COMPLETED)
    second = runs.create_rerun(analysis.pk, uuid4())
    assert (second.ordinal, second.state) == (2, RunState.QUEUED)
    first.refresh_from_db()
    assert first.state == RunState.COMPLETED


def test_transition_table_and_timestamps():
    runs = services()
    _, run, _ = runs.create_analysis("text", "Uma afirmação.", None, uuid4())
    with pytest.raises(ValueError):
        runs.transition_run(run.pk, RunState.COMPLETED)
    running = runs.transition_run(run.pk, RunState.RUNNING)
    assert running.started_at is not None and running.finished_at is None
    completed = runs.transition_run(
        run.pk, RunState.COMPLETED_WITH_LIMITATIONS, limitations=["Fonte indisponível"]
    )
    assert completed.finished_at >= completed.started_at
    assert completed.limitations == ["Fonte indisponível"]


def test_failure_records_safe_error_and_terminal_run_is_immutable():
    runs = services()
    _, run, _ = runs.create_analysis("text", "Uma afirmação.", None, uuid4())
    failed = runs.transition_run(
        run.pk, RunState.FAILED, error_code="PROVIDER_ERROR", error_message="Falha na busca"
    )
    assert failed.error_code == "PROVIDER_ERROR"
    assert failed.error_message == "Falha na busca"
    assert failed.finished_at is not None
    with pytest.raises(ValueError):
        runs.transition_run(run.pk, RunState.RUNNING)
    failed.refresh_from_db()
    assert failed.state == RunState.FAILED


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_reruns_cannot_duplicate_active_run():
    runs = services()
    analysis, first, _ = runs.create_analysis("text", "Uma afirmação.", None, uuid4())
    runs.transition_run(first.pk, RunState.FAILED)
    barrier = Barrier(2)

    def attempt():
        barrier.wait(timeout=5)
        try:
            return runs.create_rerun(analysis.pk, uuid4())
        except runs.RunConflictError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _number: attempt(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert list(analysis.runs.order_by("ordinal").values_list("ordinal", flat=True)) == [1, 2]
    assert analysis.runs.filter(state__in=[RunState.QUEUED, RunState.RUNNING]).count() == 1
