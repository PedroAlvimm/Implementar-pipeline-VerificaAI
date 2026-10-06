from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import sessionmaker

from app.claims.schemas import Claim
from app.core.enums import AnalysisStatus
from app.database.models import (
    AnalysisRecord,
    ClaimRecord,
    DecisionRecord,
    EvidenceRecord,
    QueryRecord,
    ReportRecord,
    SearchResultRecord,
)
from app.database.repositories import AnalysisRepository
from app.evidence.chunking import EvidenceDocument, chunk_document
from app.evidence.ranking import RankingCandidate
from app.evidence.service import EvidenceService
from app.evidence.source_metadata import SourceType
from app.fact_checking.aggregation import DecisionSource, aggregate_claim
from app.fact_checking.judgment import JudgmentEvidence, validate_decision
from app.ingestion.url_loader import UrlInputFailure
from app.risk_analysis.base import RiskAnalysisResult


class LoadedInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    title: str | None
    canonical_url: str | None


class PipelineLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: float = 300
    max_llm_calls: int = 20
    max_llm_tokens: int = 100_000
    max_artifact_bytes: int = 25 * 1024 * 1024
    max_results_per_query: int = 10


class PipelineBudgetExceeded(RuntimeError):
    pass


class InputCollectionError(RuntimeError):
    pass


@dataclass
class _Budget:
    limits: PipelineLimits
    started: float
    clock: Callable[[], float]
    calls: int = 0
    tokens: int = 0
    artifact_bytes: int = 0

    def check_time(self) -> None:
        if self.clock() - self.started > self.limits.timeout_seconds:
            raise PipelineBudgetExceeded("analysis_timeout")

    def llm(self, content: str) -> None:
        self.check_time()
        self.calls += 1
        self.tokens += math.ceil(len(content) / 4)
        if self.calls > self.limits.max_llm_calls:
            raise PipelineBudgetExceeded("llm_call_budget")
        if self.tokens > self.limits.max_llm_tokens:
            raise PipelineBudgetExceeded("llm_token_budget")

    def artifact(self, content: str) -> None:
        self.check_time()
        self.artifact_bytes += len(content.encode())
        if self.artifact_bytes > self.limits.max_artifact_bytes:
            raise PipelineBudgetExceeded("artifact_storage_budget")


class AnalysisPipeline:
    def __init__(
        self,
        *,
        repository: AnalysisRepository,
        sessions: sessionmaker,
        claim_extractor: Any,
        query_generator: Any,
        search_provider: Any,
        document_loader: Any,
        judge: Any,
        report_builder: Any,
        risk_analyzer: Any,
        url_loader: Callable[[str], LoadedInput] | None = None,
        evidence_service: EvidenceService | None = None,
        limits: PipelineLimits | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.repository = repository
        self.sessions = sessions
        self.claim_extractor = claim_extractor
        self.query_generator = query_generator
        self.search_provider = search_provider
        self.document_loader = document_loader
        self.judge = judge
        self.report_builder = report_builder
        self.risk_analyzer = risk_analyzer
        self.url_loader = url_loader
        self.evidence_service = evidence_service or EvidenceService()
        self.limits = limits or PipelineLimits()
        self.clock = clock

    def run(self, analysis_id: str) -> AnalysisRecord:
        record = self.repository.get(analysis_id)
        if record.status != AnalysisStatus.PENDING:
            return record
        if any(
            dependency is None
            for dependency in (
                self.claim_extractor,
                self.query_generator,
                self.search_provider,
                self.document_loader,
                self.judge,
            )
        ):
            return self.repository.fail(
                analysis_id, "PROVIDER_DISABLED", "Um provedor obrigatório está desativado."
            )

        budget = _Budget(self.limits, self.clock(), self.clock)
        try:
            self.repository.transition(analysis_id, AnalysisStatus.COLLECTING)
            loaded = self._load_input(record)
            self._store_clean_text(analysis_id, loaded.text)

            self.repository.transition(analysis_id, AnalysisStatus.EXTRACTING_CLAIMS)
            budget.llm(loaded.text)
            claim_batch = self.claim_extractor.extract(loaded.text)
            claims = [claim for claim in claim_batch.accepted if claim.checkable]
            self._store_many(ClaimRecord, analysis_id, claims)

            self.repository.transition(analysis_id, AnalysisStatus.SEARCHING)
            evidence_by_claim: dict[str, list[JudgmentEvidence]] = {}
            limitations: list[str] = [
                f"{item.claim_id}:{item.reason}" for item in claim_batch.rejected
            ]
            for claim in claims:
                evidence_by_claim[claim.id] = self._discover_evidence(
                    analysis_id, claim, budget, limitations
                )

            self.repository.transition(analysis_id, AnalysisStatus.CHECKING)
            claim_results = []
            all_evidence: dict[str, JudgmentEvidence] = {}
            for claim in claims:
                evidences = evidence_by_claim[claim.id]
                decisions = []
                sources = {}
                for evidence in evidences:
                    budget.llm(f"{claim.text}\n{evidence.text}")
                    decision = validate_decision(
                        self.judge.judge(claim.id, claim.text, evidence), claim.id, evidence
                    )
                    decisions.append(decision)
                    all_evidence[evidence.evidence_id] = evidence
                    sources[evidence.evidence_id] = DecisionSource(
                        evidence_id=evidence.evidence_id,
                        independence_group=evidence.independence_group,
                        is_primary_source=evidence.is_primary_source,
                        temporal_match=evidence.temporal_match,
                    )
                self._store_many(EvidenceRecord, analysis_id, evidences)
                self._store_many(DecisionRecord, analysis_id, decisions)
                claim_limitations = [
                    item for item in limitations if item.startswith(f"{claim.id}:")
                ]
                claim_results.append(
                    aggregate_claim(
                        claim,
                        decisions,
                        sources,
                        technical_errors=claim_limitations,
                    )
                )

            final_status = (
                AnalysisStatus.COMPLETED_WITH_LIMITATIONS
                if limitations
                else AnalysisStatus.COMPLETED
            )
            risk = self._analyze_risk(loaded.text)
            report = self.report_builder.build(
                analysis_id=analysis_id,
                status=final_status,
                original_input=record.original_input,
                title=loaded.title,
                claims=claims,
                claim_results=claim_results,
                evidence_by_id=all_evidence,
                risk=risk,
                analyzed_at=datetime.now(UTC),
            )
            self._store_many(ReportRecord, analysis_id, [report])
            if limitations:
                return self.repository.complete_with_limitations(analysis_id, limitations)
            return self.repository.transition(analysis_id, AnalysisStatus.COMPLETED)
        except PipelineBudgetExceeded as exc:
            return self.repository.fail(analysis_id, "RESOURCE_BUDGET_EXCEEDED", str(exc))
        except InputCollectionError:
            return self.repository.fail(
                analysis_id,
                "COLLECTION_TECHNICAL_ERROR",
                "A coleta da entrada falhou por indisponibilidade técnica.",
            )
        except UrlInputFailure as exc:
            return self.repository.fail(analysis_id, exc.code, str(exc))
        except Exception as exc:
            return self.repository.fail(analysis_id, "PIPELINE_ERROR", str(exc))

    def _load_input(self, record: AnalysisRecord) -> LoadedInput:
        if record.input_type == "text":
            return LoadedInput(text=record.original_input, title=None, canonical_url=None)
        if self.url_loader is None:
            raise RuntimeError("Coletor da URL de entrada não configurado")
        try:
            return self.url_loader(record.original_input)
        except TimeoutError as exc:
            raise InputCollectionError from exc

    def _analyze_risk(self, text: str) -> RiskAnalysisResult:
        try:
            return self.risk_analyzer.analyze(text)
        except Exception:
            return {
                "status": "technical_error",
                "label": None,
                "score": None,
                "model_name": None,
                "model_version": None,
                "message": (
                    "Análise linguística auxiliar indisponível por falha técnica; "
                    "isso não altera o resultado factual."
                ),
            }

    def _discover_evidence(
        self,
        analysis_id: str,
        claim: Claim,
        budget: _Budget,
        limitations: list[str],
    ) -> list[JudgmentEvidence]:
        budget.llm(claim.text)
        query_set = self.query_generator.generate(claim)
        self._store_many(QueryRecord, analysis_id, [query_set])
        results_by_url = {}
        for query in query_set.queries:
            budget.check_time()
            try:
                results = self.search_provider.search(query, self.limits.max_results_per_query)
            except Exception:
                limitations.append(f"{claim.id}:search_unavailable")
                continue
            self._store_many(SearchResultRecord, analysis_id, results)
            for result in results:
                results_by_url.setdefault(result.url, result)

        candidates: list[RankingCandidate] = []
        retrieved_at = datetime.now(UTC)
        for result in results_by_url.values():
            try:
                document: EvidenceDocument = self.document_loader.load(result)
            except Exception:
                limitations.append(f"{claim.id}:document_unavailable")
                continue
            budget.artifact(document.text)
            primary = document.domain.endswith(".gov.br") or document.domain == "gov.br"
            for chunk in chunk_document(document):
                candidates.append(
                    RankingCandidate(
                        chunk=chunk,
                        source_type=SourceType.OFFICIAL if primary else SourceType.UNKNOWN,
                        is_primary_source=primary,
                        temporal_match=None,
                    )
                )
        ranked = self.evidence_service.select(claim, candidates)
        candidate_by_id = {item.chunk.evidence_id: item for item in candidates}
        return [
            JudgmentEvidence(
                evidence_id=item.chunk.evidence_id,
                text=item.chunk.text,
                source_title=item.chunk.source_title,
                source_url=item.chunk.source_url,
                source_domain=item.chunk.source_domain,
                published_at=item.chunk.published_at,
                retrieved_at=retrieved_at,
                independence_group=item.chunk.independence_group,
                is_primary_source=candidate_by_id[item.chunk.evidence_id].is_primary_source,
                temporal_match=candidate_by_id[item.chunk.evidence_id].temporal_match,
            )
            for item in ranked
        ]

    def _store_clean_text(self, analysis_id: str, text: str) -> None:
        with self.sessions.begin() as session:
            record = session.get(AnalysisRecord, analysis_id)
            if record is None:
                raise KeyError(analysis_id)
            record.clean_text = text

    def _store_many(self, model: type, analysis_id: str, values: list[Any]) -> None:
        with self.sessions.begin() as session:
            for value in values:
                if hasattr(value, "model_dump"):
                    payload = value.model_dump(mode="json")
                else:
                    payload = dict(value)
                session.add(model(analysis_id=analysis_id, payload=payload))
