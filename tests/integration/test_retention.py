from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.schemas import AnalysisCreate
from app.database.base import Base
from app.database.models import AuditEvent, DocumentRecord
from app.database.repositories import AnalysisRepository
from app.database.retention import RetentionService
from app.database.session import build_engine, build_session_factory


def test_retention_removes_expired_analysis_and_raw_artifact(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'retention.sqlite3'}")
    Base.metadata.create_all(engine)
    sessions = build_session_factory(engine)
    repository = AnalysisRepository(sessions)
    now = datetime.now(UTC)

    old_analysis = repository.create(AnalysisCreate(input_type="text", content="Antigo."))
    current_analysis = repository.create(AnalysisCreate(input_type="text", content="Atual."))
    artifact = tmp_path / "page.html.gz"
    artifact.write_bytes(b"compressed")

    with sessions() as session:
        stored_old = session.get(type(old_analysis), old_analysis.id)
        stored_old.created_at = now - timedelta(days=31)
        session.add(
            DocumentRecord(
                analysis_id=current_analysis.id,
                source_url="https://example.org/noticia",
                artifact_path=str(artifact),
                artifact_sha256="abc123",
                retrieved_at=now - timedelta(days=8),
            )
        )
        session.add(
            AuditEvent(
                analysis_id=current_analysis.id,
                event_type="artifact_saved",
                payload_hash="hash-only",
            )
        )
        session.commit()

    result = RetentionService(sessions).cleanup(now)

    assert result.analyses_deleted == 1
    assert result.artifacts_deleted == 1
    assert not artifact.exists()
    with sessions() as session:
        audit = session.query(AuditEvent).one()
        assert audit.payload_hash == "hash-only"
        assert not hasattr(audit, "content")
