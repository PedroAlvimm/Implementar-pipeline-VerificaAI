from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import AnalysisStatus
from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class AnalysisRecord(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    input_type: Mapped[str] = mapped_column(String(8))
    original_input: Mapped[str] = mapped_column(Text)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    status: Mapped[AnalysisStatus] = mapped_column(String(40), default=AnalysisStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitations: Mapped[list[str]] = mapped_column(JSON, default=list)
    clean_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class OwnedRecord:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ClaimRecord(OwnedRecord, Base):
    __tablename__ = "claims"


class QueryRecord(OwnedRecord, Base):
    __tablename__ = "queries"


class SearchResultRecord(OwnedRecord, Base):
    __tablename__ = "search_results"


class EvidenceRecord(OwnedRecord, Base):
    __tablename__ = "evidence"


class DecisionRecord(OwnedRecord, Base):
    __tablename__ = "decisions"


class ReportRecord(OwnedRecord, Base):
    __tablename__ = "reports"


class DocumentRecord(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    source_url: Mapped[str] = mapped_column(Text)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(100))
    payload_hash: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
