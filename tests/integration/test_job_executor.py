from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from app.core.enums import AnalysisStatus
from app.core.schemas import AnalysisCreate
from app.database.base import Base
from app.database.repositories import AnalysisRepository
from app.database.session import build_engine, build_session_factory
from app.services.jobs import JobCapacityError, JobExecutor, JobStatus
from app.services.recovery import RecoveryService


def test_executor_bounds_two_active_and_ten_queued_and_deduplicates() -> None:
    release = threading.Event()
    started: list[str] = []

    def run(analysis_id: str) -> None:
        started.append(analysis_id)
        release.wait(2)

    executor = JobExecutor(run, max_workers=2, max_queued=10)
    try:
        for index in range(12):
            executor.submit(f"analysis-{index}")
        executor.submit("analysis-0")
        with pytest.raises(JobCapacityError):
            executor.submit("overflow")
        deadline = time.monotonic() + 1
        while len(started) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(started) == 2
        assert executor.status("analysis-0") in {JobStatus.RUNNING, JobStatus.QUEUED}
    finally:
        release.set()
        executor.shutdown()
    assert executor.status("analysis-11") is JobStatus.COMPLETED


def test_executor_records_worker_exception() -> None:
    executor = JobExecutor(lambda analysis_id: (_ for _ in ()).throw(RuntimeError(analysis_id)))
    try:
        executor.submit("broken")
        executor.wait("broken", timeout=2)
        assert executor.status("broken") is JobStatus.FAILED
        assert "broken" in (executor.error("broken") or "")
    finally:
        executor.shutdown()


def test_recovery_fails_interrupted_process_without_relabeling_evidence(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'recovery.sqlite3'}")
    Base.metadata.create_all(engine)
    repository = AnalysisRepository(build_session_factory(engine))
    record = repository.create(AnalysisCreate(input_type="text", content="Texto em análise"))
    repository.transition(record.id, AnalysisStatus.COLLECTING)

    count = RecoveryService(repository).fail_interrupted_analyses()
    recovered = repository.get(record.id)

    assert count == 1
    assert recovered.status == AnalysisStatus.FAILED
    assert recovered.error_code == "PROCESS_INTERRUPTED"
