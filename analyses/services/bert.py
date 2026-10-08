"""Persist auxiliary BERT output only after factual completion.

The time budget covers initialization, download and inference together. It is
cooperative: a late return is discarded, but a stuck call retains its existing
worker until process restart. No inference thread or second pool is created.
"""

import time
from uuid import UUID

from django.conf import settings
from django.utils import timezone
from pydantic import BaseModel, ValidationError

from analyses.models import AnalysisRun, BERTAnalysis, BERTState, RunState
from app.risk_analysis.base import BERTResult, RiskAnalyzer

AUXILIARY_MESSAGE = "Análise linguística auxiliar; não determina a veracidade factual."
_ERROR_MESSAGE = "Análise linguística auxiliar indisponível; não altera o resultado factual."


def record_bert_error(run_id: UUID, code: str) -> BERTAnalysis:
    """Record a safe auxiliary failure without touching the factual aggregate."""
    now = timezone.now()
    row, _ = BERTAnalysis.objects.update_or_create(
        run_id=run_id,
        defaults={
            "state": BERTState.ERROR,
            "label": None,
            "score": None,
            "model_name": None,
            "model_version": None,
            "error_code": code,
            "error_message": _ERROR_MESSAGE,
            "finished_at": now,
            "updated_at": now,
        },
    )
    return row


def run_bert(run_id: UUID, text: str, analyzer: RiskAnalyzer) -> BERTAnalysis:
    if AnalysisRun.objects.get(pk=run_id).state in (RunState.QUEUED, RunState.RUNNING):
        raise ValueError("BERT requires a terminal factual run")
    row, created = BERTAnalysis.objects.get_or_create(
        run_id=run_id, defaults={"started_at": timezone.now()}
    )
    # A pending row is already owned by its original worker; never retry a run.
    if not created:
        return row
    started = time.monotonic()
    try:
        result = analyzer.analyze(text)
        if time.monotonic() - started > settings.APP_SETTINGS.external_timeout_seconds:
            raise TimeoutError
        result = BERTResult.model_validate(
            result.model_dump() if isinstance(result, BaseModel) else result
        )
    except TimeoutError:
        return record_bert_error(run_id, "BERT_TIMEOUT")
    except ValidationError:
        return record_bert_error(run_id, "BERT_INVALID_OUTPUT")
    except Exception:
        return record_bert_error(run_id, "BERT_ERROR")
    if result.status == "technical_error":
        return record_bert_error(run_id, "BERT_ERROR")
    row.state = BERTState.AVAILABLE if result.status == "available" else BERTState.UNAVAILABLE
    row.label, row.score = result.label, result.score
    row.model_name, row.model_version = result.model_name, result.model_version
    row.finished_at = row.updated_at = timezone.now()
    row.save(
        update_fields=[
            "state",
            "label",
            "score",
            "model_name",
            "model_version",
            "finished_at",
            "updated_at",
        ]
    )
    return row
