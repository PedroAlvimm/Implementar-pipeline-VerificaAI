"""Stable analysis identities and immutable run history."""

# Django Meta constraints and indexes are intentionally class-level lists.
# ruff: noqa: RUF012

from uuid import uuid4

from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Length
from django.db.models.lookups import Exact
from django.utils import timezone


class AuditModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    # Defaults permit the legacy importer to preserve source timestamps.
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        abstract = True


class InputType(models.TextChoices):
    TEXT = "text"
    URL = "url"


class Analysis(AuditModel):
    input_type = models.CharField(max_length=8, choices=InputType.choices)
    original_input = models.TextField()
    input_hash = models.CharField(
        max_length=64,
        validators=[RegexValidator(r"\A[0-9a-f]{64}\Z", "Expected a lowercase SHA-256 digest.")],
    )
    idempotency_key = models.CharField(max_length=255, null=True, blank=True, unique=True)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(input_type__in=InputType.values), name="analysis_input_type_valid"
            ),
            models.CheckConstraint(condition=~Q(original_input=""), name="analysis_input_nonempty"),
            models.CheckConstraint(
                condition=Exact(Length(F("input_hash")), 64), name="analysis_input_hash_length"
            ),
        ]
        indexes = [
            models.Index(fields=["created_at"], name="analysis_created_idx"),
            models.Index(fields=["input_hash"], name="analysis_input_hash_idx"),
        ]


class RunState(models.TextChoices):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_LIMITATIONS = "COMPLETED_WITH_LIMITATIONS"
    FAILED = "FAILED"


ACTIVE_RUN_STATES = (RunState.QUEUED, RunState.RUNNING)


class AnalysisRun(AuditModel):
    analysis = models.ForeignKey(Analysis, on_delete=models.PROTECT, related_name="runs")
    ordinal = models.PositiveIntegerField()
    request_id = models.UUIDField(default=uuid4, editable=False)
    state = models.CharField(max_length=32, choices=RunState.choices, default=RunState.QUEUED)
    pipeline_version = models.CharField(max_length=100, default="1.0")
    provider_versions = models.JSONField(default=dict)
    trace = models.JSONField(default=dict)
    report = models.JSONField(default=dict)
    limitations = models.JSONField(default=list)
    error_code = models.CharField(max_length=100, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    updated_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(state__in=RunState.values), name="run_state_valid"),
            models.CheckConstraint(condition=Q(ordinal__gte=1), name="run_ordinal_positive"),
            models.UniqueConstraint(
                fields=["analysis", "ordinal"], name="run_analysis_ordinal_unique"
            ),
            models.UniqueConstraint(
                fields=["analysis"],
                condition=Q(state__in=ACTIVE_RUN_STATES),
                name="run_one_active_per_analysis",
            ),
            models.CheckConstraint(
                condition=Q(started_at__isnull=True)
                | Q(finished_at__isnull=True)
                | Q(finished_at__gte=F("started_at")),
                name="run_timestamps_ordered",
            ),
        ]
        indexes = [
            models.Index(fields=["analysis", "ordinal"], name="run_analysis_ordinal_idx"),
            models.Index(fields=["state", "updated_at"], name="run_state_updated_idx"),
        ]
