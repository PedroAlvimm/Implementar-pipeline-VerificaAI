"""Auxiliary BERT result, separate from factual verdicts."""

# Django Meta constraints are intentionally class-level lists.
# ruff: noqa: RUF012

from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from .analysis import AuditModel


class BERTState(models.TextChoices):
    PENDING = "PENDING"
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


class BERTLabel(models.TextChoices):
    FALSA = "FALSA"
    VERDADEIRA = "VERDADEIRA"


class BERTAnalysis(AuditModel):
    run = models.OneToOneField(
        "analyses.AnalysisRun", on_delete=models.PROTECT, related_name="bert_analysis"
    )
    state = models.CharField(max_length=16, choices=BERTState.choices, default=BERTState.PENDING)
    label = models.CharField(max_length=12, choices=BERTLabel.choices, null=True, blank=True)
    score = models.FloatField(null=True, blank=True)
    model_name = models.CharField(max_length=255, null=True, blank=True)
    model_version = models.CharField(max_length=255, null=True, blank=True)
    error_code = models.CharField(max_length=100, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    updated_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(state__in=BERTState.values), name="bert_state_valid"
            ),
            models.CheckConstraint(
                condition=Q(started_at__isnull=True)
                | Q(finished_at__isnull=True)
                | Q(finished_at__gte=F("started_at")),
                name="bert_timestamps_ordered",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        state=BERTState.AVAILABLE,
                        label__isnull=False,
                        label__in=BERTLabel.values,
                        score__isnull=False,
                        score__gte=0,
                        score__lte=1,
                        model_name__isnull=False,
                        model_version__isnull=False,
                    )
                    & ~Q(model_name="")
                    & ~Q(model_version="")
                )
                | (~Q(state=BERTState.AVAILABLE) & Q(label__isnull=True, score__isnull=True)),
                name="bert_result_matches_state",
            ),
        ]
