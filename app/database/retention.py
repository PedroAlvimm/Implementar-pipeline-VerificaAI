from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from app.database.models import AnalysisRecord, DocumentRecord


@dataclass(frozen=True)
class CleanupResult:
    analyses_deleted: int
    artifacts_deleted: int


class RetentionService:
    def __init__(self, sessions: sessionmaker) -> None:
        self._sessions = sessions

    def cleanup(self, now: datetime) -> CleanupResult:
        analysis_cutoff = now - timedelta(days=30)
        artifact_cutoff = now - timedelta(days=7)
        artifacts_deleted = 0

        with self._sessions.begin() as session:
            documents = list(
                session.scalars(
                    select(DocumentRecord).where(
                        DocumentRecord.artifact_path.is_not(None),
                        DocumentRecord.retrieved_at < artifact_cutoff,
                    )
                )
            )
            for document in documents:
                path = Path(document.artifact_path or "")
                if path.is_file():
                    path.unlink()
                    artifacts_deleted += 1
                document.artifact_path = None

            result = session.execute(
                delete(AnalysisRecord).where(AnalysisRecord.created_at < analysis_cutoff)
            )

        return CleanupResult(
            analyses_deleted=result.rowcount or 0,
            artifacts_deleted=artifacts_deleted,
        )
