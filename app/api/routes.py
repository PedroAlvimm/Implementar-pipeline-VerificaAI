from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Response, status
from sqlalchemy import select

from app.api.dependencies import AppContainer
from app.api.schemas import AnalysisAccepted, AnalysisRequest, AnalysisStatusResponse
from app.core.errors import InputValidationError
from app.core.schemas import AnalysisCreate
from app.database.models import ClaimRecord, ReportRecord
from app.database.repositories import IdempotencyConflict
from app.ingestion.validation import validate_analysis_input
from app.services.jobs import JobCapacityError


def build_router(container: AppContainer) -> APIRouter:
    router = APIRouter(prefix="/api/v1/analyses", tags=["analyses"])

    def analysis_or_404(analysis_id: str):
        try:
            return container.repository.get(analysis_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Análise não encontrada") from exc

    @router.post("", response_model=AnalysisAccepted, status_code=status.HTTP_202_ACCEPTED)
    def create_analysis(
        request: AnalysisRequest,
        response: Response,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> AnalysisAccepted:
        if container.settings.provider_mode == "real" and not request.external_processing_consent:
            raise HTTPException(
                status_code=403,
                detail="É necessário consentimento para processamento externo.",
            )
        try:
            validated = validate_analysis_input(
                request.input_type,
                request.content,
                max_chars=container.settings.max_input_chars,
            )
            record = container.repository.create(
                AnalysisCreate(input_type=validated.input_type, content=validated.content),
                idempotency_key,
            )
            container.executor.submit(record.id)
        except InputValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except IdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except JobCapacityError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        response.headers["Location"] = f"/api/v1/analyses/{record.id}"
        return AnalysisAccepted(analysis_id=record.id, status=record.status)

    @router.get("/{analysis_id}", response_model=AnalysisStatusResponse)
    def get_analysis(analysis_id: str) -> AnalysisStatusResponse:
        record = analysis_or_404(analysis_id)
        return AnalysisStatusResponse(
            analysis_id=record.id,
            status=record.status,
            error_code=record.error_code,
            error_message=record.error_message,
            limitations=record.limitations,
        )

    @router.get("/{analysis_id}/claims", response_model=list[dict[str, Any]])
    def get_claims(analysis_id: str) -> list[dict[str, Any]]:
        analysis_or_404(analysis_id)
        with container.sessions() as session:
            records = session.scalars(
                select(ClaimRecord)
                .where(ClaimRecord.analysis_id == analysis_id)
                .order_by(ClaimRecord.created_at, ClaimRecord.id)
            )
            return [record.payload for record in records]

    @router.get("/{analysis_id}/report", response_model=dict[str, Any])
    def get_report(analysis_id: str) -> dict[str, Any]:
        analysis_or_404(analysis_id)
        with container.sessions() as session:
            report = session.scalar(
                select(ReportRecord)
                .where(ReportRecord.analysis_id == analysis_id)
                .order_by(ReportRecord.created_at.desc())
            )
            if report is None:
                raise HTTPException(status_code=409, detail="Relatório ainda não disponível")
            return report.payload

    return router
