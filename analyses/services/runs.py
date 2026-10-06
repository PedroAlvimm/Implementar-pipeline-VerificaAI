"""Transactional creation and state transitions for analysis runs."""

from hashlib import sha256
from uuid import UUID

from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Max
from django.utils import timezone

from analyses.models import Analysis, AnalysisRun, InputType, RunState


class RunConflictError(ValueError):
    """A request conflicts with an existing idempotency key or active run."""


_TRANSITIONS = {
    RunState.QUEUED: frozenset((RunState.RUNNING, RunState.FAILED)),
    RunState.RUNNING: frozenset(
        (
            RunState.COMPLETED,
            RunState.COMPLETED_WITH_LIMITATIONS,
            RunState.FAILED,
        )
    ),
}


def create_analysis(
    input_type: str, content: str, idempotency_key: str | None, request_id: UUID
) -> tuple[Analysis, AnalysisRun, bool]:
    """Return the original pair for a matching idempotent request."""
    if input_type not in InputType.values or not isinstance(content, str) or not content.strip():
        raise ValueError("A nonempty text or URL input is required")
    normalized = content.strip()
    input_hash = sha256(normalized.encode("utf-8")).hexdigest()

    with transaction.atomic():
        if idempotency_key is not None:
            existing = (
                Analysis.objects.select_for_update().filter(idempotency_key=idempotency_key).first()
            )
            if existing is not None:
                if existing.input_type != input_type or existing.input_hash != input_hash:
                    raise RunConflictError("Idempotency key belongs to a different input")
                return existing, existing.runs.order_by("ordinal").first(), False

        try:
            with transaction.atomic():
                analysis = Analysis.objects.create(
                    input_type=input_type,
                    original_input=content,
                    input_hash=input_hash,
                    idempotency_key=idempotency_key,
                )
                run = AnalysisRun.objects.create(
                    analysis=analysis, ordinal=1, request_id=request_id
                )
        except IntegrityError as exc:
            raise RunConflictError("Analysis creation conflicts with existing data") from exc
        return analysis, run, True


def create_rerun(analysis_id: UUID, request_id: UUID) -> AnalysisRun:
    """Append a queued run only after all earlier runs are terminal."""
    try:
        with transaction.atomic():
            analysis = Analysis.objects.select_for_update().get(pk=analysis_id)
            # SQLite ignores SELECT FOR UPDATE; this write serializes competing reruns.
            Analysis.objects.filter(pk=analysis.pk).update(updated_at=timezone.now())
            if analysis.runs.filter(state__in=(RunState.QUEUED, RunState.RUNNING)).exists():
                raise RunConflictError("Analysis already has an active run")
            ordinal = (analysis.runs.aggregate(highest=Max("ordinal"))["highest"] or 0) + 1
            try:
                with transaction.atomic():
                    return AnalysisRun.objects.create(
                        analysis=analysis, ordinal=ordinal, request_id=request_id
                    )
            except IntegrityError as exc:
                raise RunConflictError("Analysis already has an active run") from exc
    except OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        raise RunConflictError("Analysis already has an active run") from exc


def transition_run(
    run_id: UUID,
    target: RunState,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
    limitations: list[str] | None = None,
) -> AnalysisRun:
    """Apply only the approved lifecycle transitions and timestamp the result."""
    with transaction.atomic():
        run = AnalysisRun.objects.select_for_update().get(pk=run_id)
        if target not in _TRANSITIONS.get(run.state, frozenset()):
            raise ValueError(f"Invalid run transition: {run.state} -> {target}")
        now = timezone.now()
        run.state = target
        run.updated_at = now
        update_fields = ["state", "updated_at"]
        if target == RunState.RUNNING:
            run.started_at = now
            update_fields.append("started_at")
        else:
            run.finished_at = now
            update_fields.append("finished_at")
        if target == RunState.FAILED:
            run.error_code = error_code
            run.error_message = error_message
            update_fields.extend(("error_code", "error_message"))
        if limitations is not None:
            run.limitations = limitations
            update_fields.append("limitations")
        run.save(update_fields=update_fields)
        return run
