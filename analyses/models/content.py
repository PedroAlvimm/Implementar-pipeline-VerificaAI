"""Factual claims and their source evidence for one run."""

# Django Meta constraints and indexes are intentionally class-level lists.
# ruff: noqa: RUF012

from django.db import models
from django.db.models import Q

from .analysis import AuditModel


class Claim(AuditModel):
    run = models.ForeignKey("analyses.AnalysisRun", on_delete=models.PROTECT, related_name="claims")
    claim_key = models.CharField(max_length=255)
    position = models.PositiveIntegerField()
    text = models.TextField()
    priority = models.PositiveIntegerField(default=0)
    verdict = models.CharField(max_length=32, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    explanation = models.TextField(blank=True)
    claim_type = models.CharField(max_length=100, blank=True)
    entities = models.JSONField(default=list)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "claim_key"], name="claim_run_key_unique"),
            models.CheckConstraint(condition=Q(position__gte=1), name="claim_position_positive"),
            models.CheckConstraint(condition=Q(priority__gte=0), name="claim_priority_nonnegative"),
        ]
        indexes = [models.Index(fields=["run", "position"], name="claim_run_position_idx")]


class Evidence(AuditModel):
    run = models.ForeignKey(
        "analyses.AnalysisRun", on_delete=models.PROTECT, related_name="evidence"
    )
    claim = models.ForeignKey(Claim, on_delete=models.PROTECT, related_name="evidence")
    evidence_key = models.CharField(max_length=255)
    canonical_url = models.TextField()
    title = models.TextField(blank=True)
    domain = models.CharField(max_length=255)
    excerpt = models.TextField()
    quotation = models.TextField(blank=True)
    bm25_score = models.FloatField(null=True, blank=True)
    rank = models.PositiveIntegerField(default=0)
    independence_group = models.CharField(max_length=255, blank=True)
    factual_relation = models.CharField(max_length=32, blank=True)
    available = models.BooleanField(default=True)
    published_at = models.DateTimeField(null=True, blank=True)
    retrieved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "evidence_key"], name="evidence_run_key_unique"),
            models.CheckConstraint(condition=Q(rank__gte=0), name="evidence_rank_nonnegative"),
        ]
        indexes = [
            models.Index(fields=["claim", "rank"], name="evidence_claim_rank_idx"),
            models.Index(fields=["run", "independence_group"], name="evidence_independence_idx"),
        ]
