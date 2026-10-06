from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.enums import AnalysisStatus
from app.core.schemas import AnalysisCreate
from app.database.models import AnalysisRecord
from app.database.state_machine import validate_transition


class IdempotencyConflict(ValueError):
    pass


class AnalysisRepository:
    def __init__(self, sessions: sessionmaker) -> None:
        self._sessions = sessions

    @staticmethod
    def _hash_request(request: AnalysisCreate) -> str:
        canonical = f"{request.input_type}\0{request.content}".encode()
        return hashlib.sha256(canonical).hexdigest()

    def create(self, request: AnalysisCreate, idempotency_key: str | None = None) -> AnalysisRecord:
        request_hash = self._hash_request(request)
        with self._sessions.begin() as session:
            if idempotency_key:
                existing = session.scalar(
                    select(AnalysisRecord).where(AnalysisRecord.idempotency_key == idempotency_key)
                )
                if existing:
                    if existing.input_hash != request_hash:
                        raise IdempotencyConflict(
                            "A chave de idempotência já foi usada com outro conteúdo"
                        )
                    return existing
            record = AnalysisRecord(
                input_type=request.input_type,
                original_input=request.content,
                input_hash=request_hash,
                idempotency_key=idempotency_key,
            )
            session.add(record)
            session.flush()
            return record

    def get(self, analysis_id: str) -> AnalysisRecord:
        with self._sessions() as session:
            record = session.get(AnalysisRecord, analysis_id)
            if record is None:
                raise KeyError(analysis_id)
            session.expunge(record)
            return record

    def transition(self, analysis_id: str, target: AnalysisStatus) -> AnalysisRecord:
        with self._sessions.begin() as session:
            record = session.get(AnalysisRecord, analysis_id)
            if record is None:
                raise KeyError(analysis_id)
            validate_transition(record.status, target)
            record.status = target
            session.flush()
            return record

    def fail(self, analysis_id: str, code: str, message: str) -> AnalysisRecord:
        with self._sessions.begin() as session:
            record = session.get(AnalysisRecord, analysis_id)
            if record is None:
                raise KeyError(analysis_id)
            validate_transition(record.status, AnalysisStatus.FAILED)
            record.status = AnalysisStatus.FAILED
            record.error_code = code
            record.error_message = message
            session.flush()
            return record

    def complete_with_limitations(self, analysis_id: str, limitations: list[str]) -> AnalysisRecord:
        with self._sessions.begin() as session:
            record = session.get(AnalysisRecord, analysis_id)
            if record is None:
                raise KeyError(analysis_id)
            validate_transition(record.status, AnalysisStatus.COMPLETED_WITH_LIMITATIONS)
            record.status = AnalysisStatus.COMPLETED_WITH_LIMITATIONS
            record.limitations = list(limitations)
            session.flush()
            return record

    def fail_interrupted(self) -> int:
        active = {
            AnalysisStatus.COLLECTING,
            AnalysisStatus.EXTRACTING_CLAIMS,
            AnalysisStatus.SEARCHING,
            AnalysisStatus.CHECKING,
        }
        with self._sessions.begin() as session:
            records = list(
                session.scalars(select(AnalysisRecord).where(AnalysisRecord.status.in_(active)))
            )
            for record in records:
                record.status = AnalysisStatus.FAILED
                record.error_code = "PROCESS_INTERRUPTED"
                record.error_message = "A análise foi interrompida por reinício do processo."
            return len(records)
