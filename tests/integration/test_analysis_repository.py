from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.enums import AnalysisStatus
from app.core.schemas import AnalysisCreate
from app.database.base import Base
from app.database.repositories import AnalysisRepository, IdempotencyConflict
from app.database.session import build_engine, build_session_factory


@pytest.fixture
def repository(tmp_path: Path) -> AnalysisRepository:
    engine = build_engine(f"sqlite:///{tmp_path / 'test.sqlite3'}")
    Base.metadata.create_all(engine)
    return AnalysisRepository(build_session_factory(engine))


def test_repository_creates_uuid_analysis_and_replays_same_key(
    repository: AnalysisRepository,
) -> None:
    request = AnalysisCreate(input_type="text", content="O município comprou oito doses.")

    first = repository.create(request, "request-1")
    replay = repository.create(request, "request-1")

    assert first.id == replay.id
    assert first.status == AnalysisStatus.PENDING
    assert first.created_at.tzinfo is not None


def test_idempotency_key_payload_mismatch_is_conflict(
    repository: AnalysisRepository,
) -> None:
    repository.create(AnalysisCreate(input_type="text", content="Primeiro texto."), "same")

    with pytest.raises(IdempotencyConflict):
        repository.create(AnalysisCreate(input_type="text", content="Outro texto."), "same")


def test_repository_transitions_and_recovers_interrupted_analysis(
    repository: AnalysisRepository,
) -> None:
    analysis = repository.create(AnalysisCreate(input_type="text", content="Texto."))
    repository.transition(analysis.id, AnalysisStatus.COLLECTING)

    recovered = repository.fail_interrupted()
    stored = repository.get(analysis.id)

    assert recovered == 1
    assert stored.status == AnalysisStatus.FAILED
    assert stored.error_code == "PROCESS_INTERRUPTED"


def test_repository_records_failure_and_partial_completion(
    repository: AnalysisRepository,
) -> None:
    failed = repository.create(AnalysisCreate(input_type="text", content="Falha."))
    repository.fail(failed.id, "SEARCH_TIMEOUT", "Busca indisponível")
    assert repository.get(failed.id).status == AnalysisStatus.FAILED

    partial = repository.create(AnalysisCreate(input_type="text", content="Parcial."))
    repository.transition(partial.id, AnalysisStatus.COLLECTING)
    repository.transition(partial.id, AnalysisStatus.EXTRACTING_CLAIMS)
    repository.transition(partial.id, AnalysisStatus.SEARCHING)
    repository.transition(partial.id, AnalysisStatus.CHECKING)
    repository.complete_with_limitations(partial.id, ["claim_02: timeout"])
    stored = repository.get(partial.id)
    assert stored.status == AnalysisStatus.COMPLETED_WITH_LIMITATIONS
    assert stored.limitations == ["claim_02: timeout"]


def test_sqlite_file_database_enables_wal(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'wal.sqlite3'}")

    with engine.connect() as connection:
        mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()

    assert mode.casefold() == "wal"
