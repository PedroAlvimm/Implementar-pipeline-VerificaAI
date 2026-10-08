"""Explicit local lifecycle, capacity and factual-before-auxiliary ordering."""

import importlib.util
import subprocess
import sys
import threading
from dataclasses import asdict
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from analyses.models import AnalysisRun, BERTAnalysis, RunState
from analyses.services.artifacts import FilesystemArtifactStore
from analyses.services.runs import create_analysis, transition_run
from app.risk_analysis.disabled import DisabledRiskAnalyzer

pytestmark = pytest.mark.django_db(transaction=True)


def module():
    assert importlib.util.find_spec("analyses.services.executor"), "Local executor missing"
    from analyses.services import executor

    return executor


def new_run():
    return create_analysis("text", "Texto factual", None, uuid4())[1]


@pytest.fixture
def executors():
    instances = []
    releases = []

    def make(runner, **kwargs):
        executor = module().LocalAnalysisExecutor(runner, **kwargs)
        instances.append(executor)
        return executor

    yield make, releases
    for event in releases:
        event.set()
    for executor in instances:
        executor.shutdown()
        for thread in executor._pool._threads:
            thread.join(timeout=5)
            assert not thread.is_alive(), "Executor fixture leaked a worker"


def finish(run_id):
    transition_run(run_id, RunState.RUNNING)
    transition_run(run_id, RunState.FAILED, error_code="FIXTURE")


def test_capacity_duplicates_and_release_after_runner_exception(executors):
    make, releases = executors
    entered, release = threading.Event(), threading.Event()
    releases.append(release)
    calls = []

    def runner(run_id):
        calls.append(run_id)
        entered.set()
        assert release.wait(5)
        raise RuntimeError("SECRET")

    runs = [new_run() for _ in range(3)]
    executor = make(runner, max_workers=1, max_queued=1)
    executor.submit(runs[0].pk)
    assert entered.wait(5)
    executor.submit(runs[0].pk)
    executor.submit(runs[1].pk)
    with pytest.raises(module().ExecutorCapacityError):
        executor.submit(runs[2].pk)
    futures = list(executor._futures.values())
    release.set()
    for future in futures:
        future.result(timeout=5)
    assert calls == [runs[0].pk, runs[1].pk]
    for run in runs[:2]:
        run.refresh_from_db()
        assert run.state == "FAILED" and run.error_code == "EXECUTOR_ERROR"
        assert "SECRET" not in run.error_message
    executor.submit(runs[0].pk)  # Terminal runs are never replayed.
    executor.submit(runs[2].pk)
    for future in list(executor._futures.values()):
        future.result(timeout=5)
    assert calls == [run.pk for run in runs]


def test_factual_is_queryable_while_bert_blocks_on_same_worker(tmp_path, executors):
    from tests.django.test_django_pipeline import make_pipeline

    make, releases = executors
    entered, release = threading.Event(), threading.Event()
    releases.append(release)
    pipeline = make_pipeline(tmp_path)
    worker_ids = []

    def runner(run_id):
        worker_ids.append(threading.get_ident())
        return pipeline.run(run_id)

    class BlockedAnalyzer:
        def analyze(self, text):
            assert text == "Texto factual"
            worker_ids.append(threading.get_ident())
            entered.set()
            assert release.wait(5)
            return DisabledRiskAnalyzer().analyze(text)

    run = new_run()
    executor = make(runner, analyzer=BlockedAnalyzer(), artifact_store=pipeline.artifact_store)
    executor.submit(run.pk)
    future = executor._futures[run.pk]
    assert entered.wait(5)
    run.refresh_from_db()
    assert run.state == "COMPLETED" and run.finished_at is not None
    assert run.report["claims"]
    assert BERTAnalysis.objects.get(run=run).state == "PENDING"
    assert worker_ids[0] == worker_ids[1] != threading.get_ident()
    saved_report, saved_finish = run.report, run.finished_at
    release.set()
    future.result(timeout=5)
    run.refresh_from_db()
    assert (run.report, run.finished_at) == (saved_report, saved_finish)
    assert BERTAnalysis.objects.get(run=run).state == "UNAVAILABLE"


@pytest.mark.parametrize("tamper", ["absolute", "traversal", "symlink", "hash", "owner"])
def test_input_artifact_rejects_unsafe_paths_and_tampering(tmp_path, executors, tamper):
    make, _ = executors
    run = new_run()
    store = FilesystemArtifactStore(tmp_path / "artifacts")
    ref = asdict(store.store(run.pk, "input.txt", b"Texto factual", "text/plain"))
    outside = tmp_path / "secret.txt"
    outside.write_text("SECRET")
    if tamper == "absolute":
        ref["relative_path"] = str(outside)
    elif tamper == "traversal":
        ref["relative_path"] = "../secret.txt"
    elif tamper == "symlink":
        target = store.root / ref["relative_path"]
        target.unlink()
        target.symlink_to(outside)
    elif tamper == "hash":
        (store.root / ref["relative_path"]).write_text("Tamper")
    else:
        ref = asdict(store.store(uuid4(), "input.txt", b"Texto factual", "text/plain"))

    def runner(run_id):
        transition_run(run_id, RunState.RUNNING)
        AnalysisRun.objects.filter(pk=run_id).update(trace={"input": ref})
        transition_run(run_id, RunState.COMPLETED)

    class NeverAnalyze:
        def analyze(self, text):
            pytest.fail("Unsafe input must never reach BERT")

    executor = make(runner, analyzer=NeverAnalyze(), artifact_store=store)
    executor.submit(run.pk)
    for future in list(executor._futures.values()):
        future.result(timeout=5)
    run.refresh_from_db()
    assert run.state == "COMPLETED"
    row = BERTAnalysis.objects.get(run=run)
    assert row.state == "ERROR" and row.error_code == "BERT_INPUT_ERROR"
    assert "SECRET" not in row.error_message


def test_recovery_is_one_update_and_preserves_terminal_runs():
    runs = [new_run() for _ in range(3)]
    transition_run(runs[1].pk, RunState.RUNNING)
    finish(runs[2].pk)
    terminal = AnalysisRun.objects.values().get(pk=runs[2].pk)
    with CaptureQueriesContext(connection) as queries:
        assert module().recover_interrupted_runs() == 2
    assert len(queries) == 1 and queries[0]["sql"].startswith("UPDATE")
    for run in runs[:2]:
        run.refresh_from_db()
        assert run.state == "FAILED" and run.error_code == "PROCESS_INTERRUPTED"
        assert run.finished_at is not None
    assert AnalysisRun.objects.values().get(pk=runs[2].pk) == terminal
    assert module().recover_interrupted_runs() == 0


def test_import_ready_and_lazy_get_create_no_threads_or_database_queries():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import os, threading
os.environ['DJANGO_SETTINGS_MODULE'] = 'verificaai.settings.test'
def forbidden(*args, **kwargs):
    raise AssertionError('implicit thread or database access')
threading.Thread.start = forbidden
from django.db.backends.base.base import BaseDatabaseWrapper
BaseDatabaseWrapper.ensure_connection = forbidden
import django
django.setup()
from analyses.services.executor import get_executor, shutdown_executor
first = get_executor()
assert get_executor() is first
shutdown_executor()
shutdown_executor()
""",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_initialize_runtime_recovers_once_before_new_runs(monkeypatch):
    mod = module()
    monkeypatch.setattr(mod, "_initialized", False)
    monkeypatch.setattr(mod, "_executor", None)
    stale = new_run()
    try:
        first = mod.initialize_runtime()
        stale.refresh_from_db()
        assert stale.error_code == "PROCESS_INTERRUPTED"
        fresh = new_run()
        assert mod.initialize_runtime() is first
        fresh.refresh_from_db()
        assert fresh.state == "QUEUED"
    finally:
        mod.shutdown_executor()


def test_shutdown_cancels_queued_work_and_returns_while_worker_is_blocked(executors):
    make, releases = executors
    entered, release = threading.Event(), threading.Event()
    releases.append(release)

    def runner(run_id):
        entered.set()
        assert release.wait(5)
        finish(run_id)

    executor = make(runner, max_workers=1, max_queued=1)
    first, queued = new_run(), new_run()
    executor.submit(first.pk)
    assert entered.wait(5)
    executor.submit(queued.pk)
    waiting = executor._futures[queued.pk]
    executor.shutdown()
    assert waiting.cancelled()
    assert not release.is_set()
    executor.shutdown()
    with pytest.raises(RuntimeError, match="shut"):
        executor.submit(new_run().pk)
