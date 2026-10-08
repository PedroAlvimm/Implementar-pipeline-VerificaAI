"""Django persistence adapter around the existing factual domain services.

Only QUEUED runs can be started here. Terminal replay is read-only; RUNNING
runs belong to their original worker and cannot be adopted or retried.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from threading import Lock
from urllib.parse import urlsplit
from uuid import UUID

from django.conf import settings as django_settings
from django.db import transaction
from django.utils import timezone
from pydantic import BaseModel, ValidationError

from analyses.models import AnalysisRun, Claim, Evidence, RunState
from analyses.services.artifacts import ArtifactLimitExceeded, FilesystemArtifactStore
from analyses.services.runs import RunConflictError, transition_run
from app.claims.schemas import ClaimValidationResult, QuerySet
from app.claims.validation import validate_claims
from app.core.config import Settings
from app.core.enums import AnalysisStatus
from app.evidence.chunking import EvidenceDocument, chunk_document
from app.evidence.ranking import RankingCandidate
from app.evidence.service import EvidenceService
from app.evidence.source_metadata import SourceType
from app.fact_checking.aggregation import DecisionSource, aggregate_claim
from app.fact_checking.judgment import (
    EvidenceDecision,
    JudgmentEvidence,
    JudgmentValidationError,
    validate_decision,
)
from app.fact_checking.quotation import normalize_evidence_text
from app.ingestion.url_loader import LoadedUrl, UrlInputFailure, build_safe_url_loader
from app.reports.builder import ReportBuilder
from app.scraping.extraction import source_identity_url
from app.search.canonical import canonicalize_url
from app.search.contracts import SearchResult
from app.search.deduplication import DocumentCandidate, group_document_independence

_START_LOCK = Lock()
_PRIORITIES = {"high": 3, "medium": 2, "low": 1}
_LLM_OUTPUT_BYTES = 32 * 1024
_QUERY_OUTPUT_BYTES = 4 * 1024
_TRACE_BYTES = 64 * 1024


class PipelineBudgetExceeded(RuntimeError):
    """A factual run exceeded a local resource limit."""


def _check_json_size(value, maximum):
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > maximum:
        raise JudgmentValidationError("Structured output exceeds the JSON byte limit")


def _validated(schema, value, *, max_json_bytes=None):
    # Revalidate model instances too: providers may construct or copy unchecked models.
    validated = schema.model_validate(value.model_dump() if isinstance(value, BaseModel) else value)
    if max_json_bytes is not None:
        _check_json_size(validated.model_dump(mode="json"), max_json_bytes)
    return validated


@dataclass
class _Budget:
    settings: Settings
    clock: Callable[[], float]
    started: float
    calls: int = 0
    tokens: int = 0
    artifact_bytes: int = 0

    def check(self):
        if self.clock() - self.started > self.settings.analysis_timeout_seconds:
            raise PipelineBudgetExceeded

    def llm(self, text):
        self.check()
        self.calls += 1
        self.tokens += math.ceil(len(text) / 4)
        if self.calls > self.settings.max_llm_calls or self.tokens > self.settings.max_llm_tokens:
            raise PipelineBudgetExceeded

    def artifact(self, content):
        self.check()
        self.artifact_bytes += len(content)
        if self.artifact_bytes > self.settings.max_artifact_bytes_per_analysis:
            raise PipelineBudgetExceeded


class SafeEvidenceDocumentLoader:
    """Load search sources through the same SSRF/robots boundary as URL inputs."""

    def __init__(self, url_loader):
        self.url_loader = url_loader

    def load(self, result: SearchResult) -> EvidenceDocument:
        loaded = _validated(LoadedUrl, self.url_loader(result.url))
        url = source_identity_url(loaded.final_url, loaded.canonical_url)
        return EvidenceDocument(
            id=sha256(url.encode()).hexdigest(),
            text=loaded.text,
            title=loaded.title or result.title,
            url=url,
            domain=urlsplit(url).hostname or "",
            published_at=result.published_at,
            independence_group="",
        )


def persist_evidence(run_id: UUID, rows: list[Evidence]) -> None:
    """Validate cross-table ownership and literal citations before the whole batch writes."""
    with transaction.atomic():
        run = AnalysisRun.objects.get(pk=run_id)
        if run.state != RunState.RUNNING:
            raise RunConflictError("Evidence requires a RUNNING run")
        owned_claims = set(
            Claim.objects.filter(
                run_id=run_id,
                pk__in=[row.claim_id for row in rows],
            ).values_list("pk", flat=True)
        )
        for row in rows:
            if row.run_id != run.pk or row.claim_id not in owned_claims:
                raise ValueError("Evidence and claim must belong to the same run")
            row.excerpt = normalize_evidence_text(row.excerpt)
            row.quotation = normalize_evidence_text(row.quotation)
            if row.quotation and row.quotation not in row.excerpt:
                raise ValueError("Citação não encontrada no trecho normalizado")
            if row.factual_relation in ("SUPPORTED", "REFUTED") and not row.quotation:
                raise ValueError("Citação factual vazia")
        Evidence.objects.bulk_create(rows)


class DjangoAnalysisPipeline:
    def __init__(
        self,
        *,
        claim_extractor,
        query_generator,
        search_provider,
        judge,
        document_loader=None,
        url_loader=None,
        artifact_store=None,
        evidence_service=None,
        report_builder=None,
        settings: Settings | None = None,
        clock=time.monotonic,
    ):
        self.settings = settings or django_settings.APP_SETTINGS
        self.claim_extractor = claim_extractor
        self.query_generator = query_generator
        self.search_provider = search_provider
        self.judge = judge
        self.url_loader = url_loader or build_safe_url_loader(self.settings)
        self.document_loader = document_loader or SafeEvidenceDocumentLoader(self.url_loader)
        self.artifact_store = artifact_store or FilesystemArtifactStore(
            self.settings.artifacts_dir,
            max_bytes=self.settings.max_artifact_bytes_per_analysis,
        )
        self.evidence_service = evidence_service or EvidenceService()
        self.report_builder = report_builder or ReportBuilder()
        self.clock = clock

    def run(self, run_id: UUID) -> AnalysisRun:
        # One local process: serialize start checks, then release before external work.
        with _START_LOCK:
            run = AnalysisRun.objects.select_related("analysis").get(pk=run_id)
            if run.state == RunState.RUNNING:
                raise RunConflictError("Run is already owned by another worker")
            if run.state != RunState.QUEUED:
                return run
            transition_run(run.pk, RunState.RUNNING)
        providers = {
            "claims": self.claim_extractor,
            "queries": self.query_generator,
            "search": self.search_provider,
            "documents": self.document_loader,
            "judge": self.judge,
        }
        if any(provider is None for provider in providers.values()):
            return self._fail(run, "PROVIDER_DISABLED", "Um provedor obrigatório está desativado.")
        budget = _Budget(self.settings, self.clock, self.clock())
        trace = {"schema_version": 1, "queries": [], "documents": []}
        limitations = []
        try:
            versions = {
                name: {
                    "name": type(provider).__name__,
                    "version": str(getattr(provider, "version", "unknown"))[:100],
                }
                for name, provider in providers.items()
            }
            self._update(run.pk, provider_versions=versions)
            if run.analysis.input_type == "url":
                loaded = _validated(LoadedUrl, self.url_loader(run.analysis.original_input))
                text, title = loaded.text, loaded.title
            else:
                text, title = run.analysis.original_input.strip(), None
            if not text.strip():
                raise UrlInputFailure("EXTRACTION_FAILED", "Empty input")
            trace["input"] = self._artifact(run.pk, "input.txt", text, budget)
            self._update(run.pk, trace=trace)

            budget.llm(text)
            batch = _validated(
                ClaimValidationResult,
                self.claim_extractor.extract(text),
                max_json_bytes=_LLM_OUTPUT_BYTES,
            )
            checked = validate_claims(text, batch.accepted, limit=self.settings.max_claims)
            claims = [claim for claim in checked.accepted if claim.checkable]
            if len({claim.id for claim in claims}) != len(claims):
                raise JudgmentValidationError("Duplicate claim IDs")
            limitations.extend(
                f"{item.claim_id}:{item.reason}" for item in [*batch.rejected, *checked.rejected]
            )
            rows = [
                Claim(
                    run_id=run.pk,
                    claim_key=claim.id,
                    position=index,
                    text=claim.text,
                    priority=_PRIORITIES[claim.priority],
                    claim_type=claim.claim_type,
                    entities=claim.entities,
                )
                for index, claim in enumerate(claims, 1)
            ]
            with transaction.atomic():
                Claim.objects.bulk_create(rows)

            documents_by_claim = {}
            for claim in claims:
                documents_by_claim[claim.id] = self._discover(
                    run.pk,
                    claim,
                    budget,
                    trace,
                    limitations,
                )
                self._update(run.pk, trace=trace, limitations=list(dict.fromkeys(limitations)))
            grouping = group_document_independence(
                [
                    DocumentCandidate(id=doc.id, url=doc.url, title=doc.title, text=doc.text)
                    for documents in documents_by_claim.values()
                    for doc in documents
                ]
            )
            groups = {doc.id: doc.independence_group for doc in grouping.documents}
            for document_trace in trace["documents"]:
                document_id = document_trace["document_id"]
                document_trace["independence_group"] = groups[document_id]
                document_trace["grouping_reason"] = grouping.reasons[document_id]
            self._update(run.pk, trace=trace)

            claim_results, all_evidence = [], {}
            for claim, row in zip(claims, rows, strict=True):
                ranked = self._select(claim, documents_by_claim[claim.id], groups)
                decisions, sources, evidence_rows = [], {}, []
                for rank, item in enumerate(ranked, 1):
                    chunk = item.chunk
                    primary = chunk.source_domain == "gov.br" or chunk.source_domain.endswith(
                        ".gov.br"
                    )
                    evidence = JudgmentEvidence(
                        evidence_id=chunk.evidence_id,
                        text=chunk.text,
                        source_title=chunk.source_title,
                        source_url=chunk.source_url,
                        source_domain=chunk.source_domain,
                        published_at=chunk.published_at,
                        retrieved_at=datetime.now(UTC),
                        independence_group=chunk.independence_group,
                        is_primary_source=primary,
                        temporal_match=None,
                    )
                    budget.llm(f"{claim.text}\n{evidence.text}")
                    decision = validate_decision(
                        _validated(
                            EvidenceDecision,
                            self.judge.judge(claim.id, claim.text, evidence),
                            max_json_bytes=_LLM_OUTPUT_BYTES,
                        ),
                        claim.id,
                        evidence,
                    )
                    decisions.append(decision)
                    limitations.extend(f"{claim.id}:{item}" for item in decision.limitations)
                    all_evidence[evidence.evidence_id] = evidence
                    sources[evidence.evidence_id] = DecisionSource(
                        evidence_id=evidence.evidence_id,
                        independence_group=evidence.independence_group,
                        is_primary_source=primary,
                        temporal_match=None,
                    )
                    evidence_rows.append(
                        Evidence(
                            run_id=run.pk,
                            claim=row,
                            evidence_key=f"{claim.id}:{evidence.evidence_id}",
                            canonical_url=evidence.source_url,
                            title=evidence.source_title,
                            domain=evidence.source_domain,
                            excerpt=evidence.text,
                            quotation=decision.quoted_excerpt,
                            bm25_score=item.factors["bm25"],
                            rank=rank,
                            independence_group=evidence.independence_group,
                            factual_relation=decision.label,
                            published_at=evidence.published_at,
                            retrieved_at=evidence.retrieved_at,
                        )
                    )
                result = aggregate_claim(
                    claim,
                    decisions,
                    sources,
                    technical_errors=[
                        item for item in limitations if item.startswith(f"{claim.id}:")
                    ],
                )
                limitations.extend(result.limitations)
                with transaction.atomic():
                    persist_evidence(run.pk, evidence_rows)
                    Claim.objects.filter(pk=row.pk, run_id=run.pk).update(
                        verdict=result.verdict,
                        explanation=result.reason,
                    )
                claim_results.append(result)

            budget.check()
            limitations = list(dict.fromkeys(limitations))
            state = RunState.COMPLETED_WITH_LIMITATIONS if limitations else RunState.COMPLETED
            report = self.report_builder.build(
                analysis_id=str(run.analysis_id),
                status=AnalysisStatus(state),
                original_input=run.analysis.original_input,
                title=title,
                claims=claims,
                claim_results=claim_results,
                evidence_by_id=all_evidence,
                risk={"status": "pending", "message": ""},
                analyzed_at=datetime.now(UTC),
            ).model_dump(mode="json")
            # The shared report builder predates separate BERT persistence. Its auxiliary
            # fields are removed here; factual work neither invokes nor interprets BERT.
            report.pop("risk_status", None)
            report.pop("risk_message", None)
            report["run_id"] = str(run.pk)
            report["limitations"] = limitations
            with transaction.atomic():
                self._update(run.pk, trace=trace, report=report)
                return transition_run(run.pk, state, limitations=limitations)
        except (PipelineBudgetExceeded, ArtifactLimitExceeded):
            return self._fail(
                run, "RESOURCE_BUDGET_EXCEEDED", "O limite de recursos da análise foi excedido."
            )
        except (ValidationError, JudgmentValidationError):
            return self._fail(
                run,
                "INVALID_LLM_OUTPUT",
                "Um provedor retornou uma saída estruturada ou citação inválida.",
            )
        except UrlInputFailure as exc:
            return self._fail(
                run, exc.code, "Não foi possível coletar a URL de entrada com segurança."
            )
        except TimeoutError:
            return self._fail(
                run, "COLLECTION_TECHNICAL_ERROR", "A coleta da entrada excedeu o tempo permitido."
            )
        except Exception:
            return self._fail(run, "PIPELINE_ERROR", "A análise falhou por um erro técnico.")

    def _discover(self, run_id, claim, budget, trace, limitations):
        budget.llm(claim.text)
        queries = _validated(
            QuerySet,
            self.query_generator.generate(claim),
            max_json_bytes=_QUERY_OUTPUT_BYTES,
        )
        if len(queries.queries) > self.settings.max_queries_per_claim:
            raise JudgmentValidationError("Query count exceeds the configured limit")
        if queries.claim_id != claim.id or any(not query.strip() for query in queries.queries):
            raise JudgmentValidationError("Invalid query references or content")
        trace["queries"].append(queries.model_dump(mode="json"))
        self._update(run_id, trace=trace)
        results = {}
        for query in queries.queries:
            budget.check()
            try:
                found = self.search_provider.search(query, self.settings.max_results_per_query)
                for raw in found[: self.settings.max_results_per_query]:
                    result = _validated(SearchResult, raw)
                    results.setdefault(canonicalize_url(result.url), result)
            except Exception:
                limitations.append(f"{claim.id}:search_unavailable")
        documents_by_url = {}
        for result in list(results.values())[: self.settings.max_documents_per_claim]:
            budget.check()
            try:
                doc = _validated(EvidenceDocument, self.document_loader.load(result))
                url = canonicalize_url(doc.url)
                doc = doc.model_copy(
                    update={
                        "id": sha256(url.encode()).hexdigest(),
                        "url": url,
                        "domain": urlsplit(url).hostname or "",
                        "text": normalize_evidence_text(doc.text),
                    }
                )
                if not doc.text:
                    raise ValueError("Empty document")
            except Exception:
                limitations.append(f"{claim.id}:document_unavailable")
                continue
            documents_by_url.setdefault(doc.url, doc)
        documents = list(documents_by_url.values())
        for document in documents:
            name = f"document-{sha256(claim.id.encode()).hexdigest()[:12]}-{document.id}.txt"
            artifact = self._artifact(run_id, name, document.text, budget)
            trace["documents"].append(
                {
                    "claim_id": claim.id,
                    "document_id": document.id,
                    "url": document.url,
                    "artifact": artifact,
                }
            )
        return documents

    def _select(self, claim, documents, groups):
        candidates = []
        for document in documents:
            document = document.model_copy(update={"independence_group": groups[document.id]})
            primary = document.domain == "gov.br" or document.domain.endswith(".gov.br")
            candidates.extend(
                RankingCandidate(
                    chunk=chunk,
                    source_type=SourceType.OFFICIAL if primary else SourceType.UNKNOWN,
                    is_primary_source=primary,
                    temporal_match=None,
                )
                for chunk in chunk_document(
                    document,
                    max_chars=self.settings.evidence_chunk_chars,
                    overlap_chars=self.settings.evidence_chunk_overlap_chars,
                )
            )
        return self.evidence_service.select(claim, candidates)[
            : self.settings.max_evidence_per_claim
        ]

    def _artifact(self, run_id, name, text, budget):
        content = text.encode("utf-8")
        budget.artifact(content)
        return asdict(self.artifact_store.store(run_id, name, content, "text/plain; charset=utf-8"))

    @staticmethod
    def _update(run_id, **fields):
        if "trace" in fields:
            _check_json_size(fields["trace"], _TRACE_BYTES)
        updated = AnalysisRun.objects.filter(pk=run_id, state=RunState.RUNNING).update(
            **fields,
            updated_at=timezone.now(),
        )
        if not updated:
            raise RunConflictError("Run is no longer RUNNING")

    @staticmethod
    def _fail(run, code, message):
        return transition_run(run.pk, RunState.FAILED, error_code=code, error_message=message)
